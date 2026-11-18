import asyncio

import aiosqlite

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def test_async_sqlite_saver_creates_schema(tmp_path):
    """冒烟测试：AsyncSqliteSaver 能建连接、建表，作为持久化 checkpointer 可用。"""

    async def _run():
        db = tmp_path / "checkpoints.sqlite"
        conn = await aiosqlite.connect(str(db))
        saver = AsyncSqliteSaver(conn)
        await saver.setup()  # 不抛异常即建表成功

        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in await cursor.fetchall()]
        await conn.close()
        return tables

    tables = asyncio.run(_run())
    assert tables, "checkpoint 数据库应至少建一张表"
