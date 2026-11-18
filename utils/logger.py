"""统一日志配置：格式里带会话 thread_id，多用户异步并发下可追踪。"""
import logging
import sys

_CONFIGURED = False


class _ThreadIdFilter(logging.Filter):
    """把当前请求的 thread_id 注入每条日志，便于按会话 grep。"""

    def filter(self, record):
        tid = "-"
        try:
            from api.context import get_thread_context
            tid = get_thread_context()
        except Exception:
            pass
        record.thread_id = tid or "-"
        return True


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(thread_id)s] %(name)s: %(message)s"
        ))
        handler.addFilter(_ThreadIdFilter())
        root.addHandler(handler)
        root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
