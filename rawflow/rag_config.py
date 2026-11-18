import os
from typing import Optional, Tuple

from utils.env import load_env


def _load_ragflow_env() -> Tuple[Optional[str], Optional[str]]:
    """
    加载 RAGFlow 环境变量（统一走项目根 .env）。
    返回值：(api_key, base_url) → 缺失则返回 None
    """
    load_env()
    api_key = os.getenv("RAGFLOW_API_KEY")
    base_url = os.getenv("RAGFLOW_API_URL")
    return api_key, base_url
