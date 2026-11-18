"""SQL 只读安全辅助：标识符引用 + 只读语句白名单。

独立成模块便于无重依赖地单测（不 import mysql.connector）。
"""
import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")

# 仅放行的只读关键字（含 CTE 的 WITH）
_READONLY_KEYWORDS = frozenset({"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"})


def quote_identifier(name: str) -> str:
    """把表名/列名安全地用反引号引用，拒绝含非法字符的标识符，防 SQL 注入。"""
    name = (name or "").strip().strip("`")
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"非法标识符: {name!r}")
    return f"`{name}`"


def ensure_readonly(query: str) -> str:
    """仅放行只读 SQL（SELECT/SHOW/DESCRIBE/EXPLAIN/WITH），拒绝写操作。"""
    stripped = (query or "").strip().lstrip("(").strip()
    first_word = stripped.split(None, 1)[0].upper() if stripped else ""
    if first_word and first_word not in _READONLY_KEYWORDS:
        raise ValueError(
            f"仅允许只读查询（SELECT/SHOW/DESCRIBE/EXPLAIN/WITH），收到: {first_word or '(空)'}"
        )
    return query
