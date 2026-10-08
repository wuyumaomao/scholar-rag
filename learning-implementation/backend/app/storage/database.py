"""PostgreSQL 数据库连接。"""

import psycopg
from psycopg import Connection

DATABASE_URL = (
    "postgresql://postgres:postgres@localhost:55432/learning_rag"
)


def get_connection() -> Connection:
    """创建并返回一个 PostgreSQL 连接。"""
    return psycopg.connect(DATABASE_URL)