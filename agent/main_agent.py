import asyncio
import logging
import shutil
from pathlib import Path

import aiosqlite
from deepagents import create_deep_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent.llm import model
from agent.prompts import main_agent_content
from agent.subagents.database_query_agent import database_query_agent
from agent.subagents.knowledge_base_agent import knowledge_base_agent
from agent.subagents.network_search_agent import network_search_agent
from api.context import session_context
from api.monitor import monitor
from tools.markdown_tools import generate_markdown
from tools.pdf_tools import convert_md_to_pdf
from tools.upload_file_read_tool import read_file_content
from utils.logger import get_logger

logger = get_logger("agent.main_agent")

project_root_path = Path(__file__).parents[1].resolve()

# 持久化 checkpointer：多轮对话记忆落盘（data/checkpoints.sqlite），服务重启不丢失。
# 单进程够用；要跨多个 uvicorn worker 共享状态时，再换 RedisSaver。
_checkpoint_db = project_root_path / "data" / "checkpoints.sqlite"
_checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

# AsyncSqliteSaver 的构造依赖运行中的事件循环（asyncio.get_running_loop()），
# 无法像同步 SqliteSaver 那样在 import 时初始化，改为首次异步调用时懒加载并缓存。
_main_agent = None
_init_lock = asyncio.Lock()


async def _get_main_agent():
    """懒加载并缓存编译好的 main_agent（内含 AsyncSqliteSaver），并发调用用锁串行化初始化。"""
    global _main_agent
    if _main_agent is None:
        async with _init_lock:
            if _main_agent is None:
                conn = await aiosqlite.connect(str(_checkpoint_db))
                checkpointer = AsyncSqliteSaver(conn)
                await checkpointer.setup()
                _main_agent = create_deep_agent(
                    model=model,
                    system_prompt=main_agent_content['system_prompt'],
                    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
                    checkpointer=checkpointer,
                    subagents=[
                        database_query_agent,
                        network_search_agent,
                        knowledge_base_agent,
                    ],
                )
                logger.info("main_agent + AsyncSqliteSaver 初始化完成: %s", _checkpoint_db)
    return _main_agent


async def run_deep_agent(task_query, session_id):
    """
    流式 + 异步执行主智能体。
    执行过程中经 monitor 推送：会话目录 / 子智能体调用 / 工具调用 / 最终结果。
    对话状态由持久化 checkpointer 按 thread_id 保存，重启后同 thread_id 可续聊。
    """
    logger.info("当前会话 main_agent 开始执行: %s", session_id)

    # 准备工作：会话专属目录 + 上传文件提示词
    session_dir = project_root_path / "output" / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_dir_str = str(session_dir).replace("\\", "/")
    relative_session_dir_str = str(session_dir.relative_to(project_root_path)).replace("\\", "/")

    updated_dir_path = project_root_path / "updated" / f"session_{session_id}"
    updated_info_prompt = ""
    if updated_dir_path.exists():
        files = [f.name for f in updated_dir_path.iterdir() if f.is_file()]
        if files:
            for filename in files:
                shutil.copy2(updated_dir_path / filename, session_dir / filename)
            updated_info_prompt = (
                "\n    [已上传文件] 已加载到工作目录:\n"
                + "\n".join(f"    - {f}" for f in files)
                + "\n    请优先使用工具（read_file_content）读取并参考这些文件。"
            )

    main_agent = await _get_main_agent()

    # 用上下文管理器写入 ContextVar（会话目录 / thread_id），退出时自动恢复，避免 token 泄漏
    with session_context(session_dir_str, session_id):
        monitor.report_session_dir(session_dir_str)  # 当前会话对应的文件夹地址推送给前端

        config = {"configurable": {"thread_id": session_id}}

        # 构建提示词
        path_instruction = f"""
    【工作环境指令】
    工作目录: {relative_session_dir_str}
    {updated_info_prompt}

    规则：
    1. 新生成文件必须保存到工作目录：'{relative_session_dir_str}/filename'
    2. 读取已上传的文件时，请直接将文件名（例如：'开篇.txt'）作为 filename 参数传入（read_file_content）读取工具，不要带上任何目录前缀。
    3. 使用相对路径，禁止使用绝对路径
    4. 若存在上传文件，请先分析内容
    """

        try:
            async for chunk in main_agent.astream(
                {"messages": [{"role": "user", "content": task_query + path_instruction}]},
                config=config,
            ):
                # chunk 形如 {"model"|"tools": {messages:[...]}}
                for node_name, state in chunk.items():
                    if not state or "messages" not in state:
                        continue
                    messages = state["messages"]
                    if messages and isinstance(messages, list):
                        last_msg = messages[-1]
                        if node_name == 'model':
                            if last_msg.tool_calls:
                                for tool_call in last_msg.tool_calls:
                                    # tool_call = {name:'task', args:{subagent_type, description}}
                                    if tool_call['name'] == 'task':
                                        monitor.report_assistant(
                                            tool_call['args']['subagent_type'],
                                            {'description': tool_call['args']['description']},
                                        )
                            elif last_msg.content:
                                logger.info("主智能体执行结果（前100字）：%s", last_msg.content[:100])
                                monitor.report_task_result(last_msg.content)
        except Exception as e:
            # 报错推送错误信息给前端
            monitor._emit("error", f"执行主智能体发生异常：{str(e)}")
