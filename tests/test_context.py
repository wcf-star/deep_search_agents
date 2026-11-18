import asyncio

from api.context import get_session_context, get_thread_context, session_context


async def _task(name, path):
    with session_context(path, f"thread_{name}"):
        await asyncio.sleep(0.05)
        return get_session_context(), get_thread_context()


def test_context_isolation_across_tasks():
    async def run():
        return await asyncio.gather(
            _task("张三", "/data/zhangsan"),
            _task("李四", "/data/lisi"),
        )

    (d1, t1), (d2, t2) = asyncio.run(run())
    assert (d1, t1) == ("/data/zhangsan", "thread_张三")
    assert (d2, t2) == ("/data/lisi", "thread_李四")


def test_context_cleared_after_with_block():
    with session_context("/data/x", "thread_x"):
        assert get_session_context() == "/data/x"
        assert get_thread_context() == "thread_x"
    assert get_session_context() is None
    assert get_thread_context() is None


def test_context_without_thread():
    with session_context("/data/y"):
        assert get_session_context() == "/data/y"
        assert get_thread_context() is None
    assert get_session_context() is None
