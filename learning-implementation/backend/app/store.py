"""PostgreSQL 会话与消息存储。"""

import time
from uuid import uuid4

from app.database import get_connection


def _session_from_row(row: tuple[object, ...]) -> dict[str, object]:
    """将 PostgreSQL 查询结果转换为 API 使用的会话字典。"""
    return {
        "session_id": row[0],
        "title": row[1],
        "created_at": row[2].timestamp(),
        "updated_at": row[3].timestamp(),
    }


def create_session(title: str = "") -> dict[str, object]:
    """创建会话并写入 sessions 表。"""
    session_id = str(uuid4())
    now = time.time()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (session_id, title, created_at, updated_at)
                VALUES (%s, %s, to_timestamp(%s), to_timestamp(%s))
                """,
                (session_id, title, now, now),
            )

    return {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }


def list_sessions() -> list[dict[str, object]]:
    """按最近更新时间倒序返回所有会话。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id, title, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                """
            )
            rows = cur.fetchall()

    return [_session_from_row(row) for row in rows]


def get_session(session_id: str) -> dict[str, object] | None:
    """按 ID 查询一个会话；没有匹配记录时返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id, title, created_at, updated_at
                FROM sessions
                WHERE session_id = %s
                """,
                (session_id,),
            )
            row = cur.fetchone()

    return _session_from_row(row) if row is not None else None


def touch_session(session_id: str) -> None:
    """记录会话最新活动时间。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET updated_at = NOW() WHERE session_id = %s",
                (session_id,),
            )


def delete_session(session_id: str) -> bool:
    """删除会话；数据库外键会自动删除其消息。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE session_id = %s",
                (session_id,),
            )
            return cur.rowcount == 1


def add_message(session_id: str, role: str, content: str) -> None:
    """将一条用户或助手消息写入 messages 表。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (session_id, role, content)
                VALUES (%s, %s, %s)
                """,
                (session_id, role, content),
            )


def list_messages(session_id: str) -> list[dict[str, str]]:
    """按插入顺序返回指定会话的聊天历史。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = %s
                ORDER BY message_id
                """,
                (session_id,),
            )
            rows = cur.fetchall()

    return [{"role": row[0], "content": row[1]} for row in rows]


def _file_from_row(row: tuple[object, ...]) -> dict[str, object]:
    """将文件表查询结果转换为 API 使用的字典。"""
    return {
        "file_id": row[0],
        "filename": row[1],
        "size_bytes": row[2],
        "created_at": row[3].timestamp(),
    }


def create_file(file_id: str, filename: str, size_bytes: int) -> dict[str, object]:
    """保存已上传文件的元数据。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO files (file_id, filename, size_bytes)
                VALUES (%s, %s, %s)
                RETURNING file_id, filename, size_bytes, created_at
                """,
                (file_id, filename, size_bytes),
            )
            row = cur.fetchone()

    return _file_from_row(row)


def list_files() -> list[dict[str, object]]:
    """按创建时间倒序返回文件元数据。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_id, filename, size_bytes, created_at
                FROM files
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()

    return [_file_from_row(row) for row in rows]


def get_file(file_id: str) -> dict[str, object] | None:
    """按 ID 查询文件元数据。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_id, filename, size_bytes, created_at
                FROM files
                WHERE file_id = %s
                """,
                (file_id,),
            )
            row = cur.fetchone()

    return _file_from_row(row) if row is not None else None


def delete_file(file_id: str) -> bool:
    """删除文件元数据。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM files WHERE file_id = %s", (file_id,))
            return cur.rowcount == 1
