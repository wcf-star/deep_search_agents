"""统一 .env 加载：项目根 .env 只加载一次，避免各模块重复 load_dotenv。"""
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    load_dotenv(_ENV_PATH, override=False)
    _loaded = True
