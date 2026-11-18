import os
import uuid
import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 注意：agent.main_agent 导入时会初始化 main_agent，这可能需要几秒钟
from agent.main_agent import run_deep_agent
from api.monitor import manager
from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger("api.server")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
UPDATED_DIR = PROJECT_ROOT / "updated"

# 上传限制：单文件 20MB + 扩展名白名单（与 read_file_content 支持范围一致）
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
ALLOWED_UPLOAD_EXTS = {".md", ".txt", ".csv", ".docx", ".pdf", ".xlsx", ".xls"}

# CORS：白名单来源，避免 allow_origins=["*"] + allow_credentials=True 的无效组合。
# 开发环境前端端口不固定（Vite 被占用时会自动顺延 5173→5174→…），
# 故额外用 allow_origin_regex 放行任意 localhost/127.0.0.1 端口。
_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
_LOCAL_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1|\[::1\]):\d+$"

# 后台任务注册表：可追踪、可优雅取消
_background_tasks: set = set()


def _spawn(coro):
    """创建后台任务并登记，异常通过 done 回调记录，不静默丢失。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(_log_task_result)
    return task


def _log_task_result(task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("后台任务异常", exc_info=exc)


def _safe_filename(filename: str) -> str:
    """取 multipart 文件名的纯 basename，防路径穿越 + 扩展名白名单 + 空名拦截。"""
    name = Path(filename or "").name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail=f"非法文件名: {filename!r}")
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '(无扩展名)'}")
    return name


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：绑定事件循环到 WebSocket 管理器
    loop = asyncio.get_running_loop()
    manager.set_loop(loop)
    logger.info("WebSocket Manager bound to loop: %s", id(loop))
    yield
    # 关闭：取消所有后台任务
    for task in list(_background_tasks):
        task.cancel()
    logger.info("后台任务已取消: %d", len(_background_tasks))


app = FastAPI(title="DeepAgents API", lifespan=lifespan)

OUTPUT_DIR.mkdir(exist_ok=True)
UPDATED_DIR.mkdir(exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=_LOCAL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskRequest(BaseModel):
    query: str
    thread_id: str = None


@app.post("/api/task")
async def run_task(request: TaskRequest):
    thread_id = request.thread_id or str(uuid.uuid4())
    _spawn(run_deep_agent(request.query, thread_id))
    return {"status": "started", "thread_id": thread_id}


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
    target_dir = UPDATED_DIR / f"session_{thread_id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file in files:
        safe_name = _safe_filename(file.filename)
        file_path = target_dir / safe_name
        size = 0
        with file_path.open("wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    buffer.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件过大（>{MAX_UPLOAD_SIZE // 1024 // 1024}MB）: {safe_name}",
                    )
                buffer.write(chunk)
        saved_files.append(safe_name)

    return {"status": "uploaded", "files": saved_files}


@app.get("/api/download")
async def download_file(path: str):
    try:
        abs_path = Path(path).resolve()
        output_abs = OUTPUT_DIR.resolve()
        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能下载输出目录下的文件"}
    except Exception:
        return {"error": "无效的路径参数"}
    if not abs_path.exists():
        return {"error": "文件不存在"}
    return FileResponse(abs_path, filename=abs_path.name)


@app.get("/api/files")
async def list_files(path: str):
    logger.debug("请求文件列表: %s", path)
    try:
        abs_path = Path(path).resolve()
        output_abs = OUTPUT_DIR.resolve()
        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能访问输出目录下的文件"}
    except Exception as e:
        return {"error": f"路径无效: {e}"}
    if not abs_path.exists():
        return {"error": "目录不存在"}

    files = []
    try:
        for file_path in abs_path.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "type": "file",
                    "path": str(file_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
    except Exception as e:
        logger.exception("遍历文件失败")
        return {"error": str(e)}

    files.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    return {"files": files}


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    await manager.connect(websocket, thread_id)
    try:
        while True:
            try:
                # 30s 无消息则主动发 ping，防止被中间层/代理掐断
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json({"type": "pong", "message": f"服务端已收到: {data}"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
        logger.info("WebSocket 客户端断开: %s", thread_id)
    except Exception:
        manager.disconnect(websocket, thread_id)
        logger.exception("WebSocket 连接异常: %s", thread_id)


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
