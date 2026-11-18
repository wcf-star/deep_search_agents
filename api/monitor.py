import datetime
import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket

from api.context import get_thread_context

logger = logging.getLogger("api.monitor")

# 尝试导入全局运行时（用于脚本模式下的流式输出）
try:
    import builtins
except ImportError:
    builtins = None


class ToolMonitor:
    """
    工具监控类，用于在工具执行过程中上报进度和状态。
    设计为单例模式，可在任何工具中直接导入使用。
    兼容 FastAPI WebSocket 和 脚本运行时的 stream_writer。

    使用示例:
    from api.monitor import monitor

    def my_tool(arg1):
        monitor.report_tool("my_tool", {"arg1": arg1})
        ...
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolMonitor, cls).__new__(cls)
            cls._instance.websocket_manager = None  # 预留给 FastAPI ConnectionManager
        return cls._instance

    def set_websocket_manager(self, manager):
        """设置 FastAPI 的 WebSocket 管理器"""
        self.websocket_manager = manager

    def _emit(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
        """内部发送方法"""
        payload = {
            "type": "monitor_event",
            "event": event_type,
            "message": message,
            "data": data or {},
            "timestamp": datetime.datetime.now().isoformat(),
        }

        # 1. WebSocket 定向推送（线程安全入队，由每个 thread 的消费者串行发送）
        if self.websocket_manager:
            try:
                thread_id = get_thread_context()
                if thread_id:
                    self.websocket_manager.enqueue(payload, thread_id)
            except Exception as e:
                logger.warning("WebSocket 推送失败: %s", e)

        # 2. 尝试通过全局 runtime 输出（DeepAgents 脚本模式）
        if builtins and hasattr(builtins, "runtime") and hasattr(builtins.runtime, "stream_writer"):
            try:
                builtins.runtime.stream_writer(payload)
            except Exception:
                pass

        # 3. 控制台保底输出（方便调试）
        logger.info("[%s] %s", event_type, message)

    def report_tool(self, tool_name: str, args: Dict[str, Any] = None):
        """报告工具开始执行"""
        self._emit("tool_start", f"开始执行工具: {tool_name}", {"tool_name": tool_name, "args": args})

    def report_assistant(self, assistant_name: str, args: Dict[str, Any] = None):
        """报告正在调用的子智能体进度"""
        self._emit("assistant_call", f"正在调用助手: {assistant_name}",
                   {"assistant_name": assistant_name, "args": args})

    def report_task_result(self, result: str):
        """报告任务最终结果"""
        self._emit("task_result", "任务执行完成", {"result": result})

    def report_session_dir(self, path: str):
        """报告任务工作目录"""
        self._emit("session_created", f"工作目录已创建: {path}", {"path": path})


# 全局单例实例
monitor = ToolMonitor()


class ConnectionManager:
    """
    WebSocket 连接管理器。

    每个 thread_id 对应一个 asyncio.Queue + 一个消费者协程：
    - 发送方（任何线程）只入队，永不阻塞，天然线程安全；
    - 消费者在事件循环里按序发消息，避免 fire-and-forget 造成的任务堆积与消息乱序；
    - 队列有上限，满了丢弃最旧一条，保证新进度优先。
    """

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        # 延迟绑定 loop，防止初始化时 loop 不一致
        self.loop = None
        self._queues: Dict[str, asyncio.Queue] = {}
        self._sender_tasks: Dict[str, asyncio.Task] = {}

    def set_loop(self, loop):
        """显式设置事件循环"""
        self.loop = loop
        monitor.set_websocket_manager(self)
        logger.info("ConnectionManager bound to loop: %s", id(loop))

    async def connect(self, websocket: WebSocket, thread_id: str):
        await websocket.accept()
        # 同一 thread_id 重连时先关闭旧连接，避免连接泄漏
        old = self.active_connections.get(thread_id)
        if old is not None and old is not websocket:
            await self._close_quietly(old)
        self.active_connections[thread_id] = websocket
        self._queues[thread_id] = asyncio.Queue(maxsize=200)
        self._sender_tasks[thread_id] = asyncio.create_task(self._sender(thread_id))
        logger.info("Client connected: %s", thread_id)

    async def _close_quietly(self, websocket: WebSocket):
        try:
            await websocket.close()
        except Exception:
            pass

    async def _sender(self, thread_id: str):
        """单个 thread 的消息消费者：从队列取消息，串行发送。"""
        queue = self._queues[thread_id]
        try:
            while True:
                message = await queue.get()
                websocket = self.active_connections.get(thread_id)
                if websocket is None:
                    continue
                await websocket.send_json(message)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("WebSocket 发送异常: %s", thread_id)

    def _put_nowait(self, thread_id: str, message: dict):
        queue = self._queues.get(thread_id)
        if queue is None:
            return
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # 队列满：丢最旧一条，保证最新进度不被卡住
            try:
                queue.get_nowait()
                queue.put_nowait(message)
            except Exception:
                pass

    def enqueue(self, message: dict, thread_id: str):
        """线程安全入队：无论从哪个线程调用，都投递到事件循环串行发送。"""
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._put_nowait, thread_id, message)

    def disconnect(self, websocket: WebSocket, thread_id: str):
        if self.active_connections.get(thread_id) is websocket:
            self.active_connections.pop(thread_id, None)
        task = self._sender_tasks.pop(thread_id, None)
        if task:
            task.cancel()
        self._queues.pop(thread_id, None)
        logger.info("Client disconnected: %s", thread_id)


manager = ConnectionManager()
