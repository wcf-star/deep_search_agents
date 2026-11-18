import os

from langchain_core.tools import tool
from mysql.connector import connect, Error

from api.monitor import monitor
from utils.env import load_env
from utils.logger import get_logger
from utils.sql_safety import ensure_readonly, quote_identifier

logger = get_logger("tools.db_tools")

load_env()

# 终止标记：数据库异常/无数据时，返回结果以该前缀开头，
# 供两级 agent 识别为「最终结果」，从而停止继续调用其它工具。
TERMINAL_PREFIX = "【数据库结果】"


def get_db_config():
    """从环境变量读取数据库配置，并校验核心配置是否存在。"""
    config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DATABASE"),
        "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
        "collation": os.getenv("MYSQL_COLLATION", "utf8mb4_unicode_ci"),
        "autocommit": True,
        "sql_mode": os.getenv("MYSQL_SQL_MODE", "TRADITIONAL"),
    }
    config = {k: v for k, v in config.items() if v is not None}

    required_keys = ["user", "password", "database"]
    missing_keys = [k for k in required_keys if k not in config]
    if missing_keys:
        raise ValueError(f"缺失数据库核心配置：{', '.join(missing_keys)}")

    return config


def _fetch_as_csv(cursor):
    """把 cursor 当前结果集格式化为 CSV 字符串；无结果集返回 None。"""
    description = cursor.description
    if not description:
        return None
    columns = [desc[0] for desc in description]
    rows = cursor.fetchall()
    header = ",".join(columns)
    data = "\n".join(",".join(map(str, row)) for row in rows)
    return f"{header}\n{data}"


@tool
def list_sql_tables() -> str:
    """查询当前库中所有可用的表，供模型识别可用表名。"""
    monitor.report_tool(tool_name="数据库表名查询工具：list_sql_tables", args={})
    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("show tables")
                tables = cursor.fetchall()
                if not tables:
                    return f"{TERMINAL_PREFIX}没有可用的表"
                table_names = [table[0] for table in tables]
                return f"可用的表有：{', '.join(table_names)}"
    except Error as e:
        return f"{TERMINAL_PREFIX}查询出现异常：{str(e)}"


@tool
def get_table_data(table_name: str) -> str:
    """查询指定表的前 100 行，返回 CSV 文本。调用前需先用 list_sql_tables 确认表名。"""
    monitor.report_tool(tool_name="数据库表数据查询工具：get_table_data", args={"table_name": table_name})

    # 标识符白名单式引用，防 SQL 注入
    try:
        safe_table = quote_identifier(table_name)
    except ValueError as e:
        return f"表名非法：{e}"

    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"select * from {safe_table} limit 100")
                csv_text = _fetch_as_csv(cursor)
                if csv_text is None:
                    return f"{TERMINAL_PREFIX}数据表：{table_name}为空没有数据！"
                return csv_text
    except Error as e:
        return f"{TERMINAL_PREFIX}查询出现异常：{str(e)}"


@tool
def execute_sql_query(query: str) -> str:
    """执行自定义只读 SQL（SELECT/SHOW/DESCRIBE/EXPLAIN），返回 CSV 文本。"""
    monitor.report_tool(tool_name="数据库自定义查询工具：execute_sql_query", args={"query": query})

    # 只读白名单，拒绝写操作（INSERT/UPDATE/DELETE/DROP 等）
    try:
        ensure_readonly(query)
    except ValueError as e:
        return f"查询被拒绝：{e}"

    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                csv_text = _fetch_as_csv(cursor)
                if csv_text is None:
                    return f"{TERMINAL_PREFIX}执行自定义 SQL 没有返回结果集，sql 为：{query}"
                return csv_text
    except Error as e:
        return f"{TERMINAL_PREFIX}查询出现异常：{str(e)}"


if __name__ == "__main__":
    print(execute_sql_query("SELECT * FROM `drugs` dgs join sales_records srd on dgs.drug_id = srd.drug_id"))
    # print(list_sql_tables())
    # print(get_table_data("drugs"))
