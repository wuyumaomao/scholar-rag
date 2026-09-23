"""内存会话存储。"""

import time
from uuid import uuid4

sessions: dict[str, dict[str, object]] = {}


def create_session(title: str = "") -> dict[str, object]:
    session_id = str(uuid4())
    now = time.time()
    session = {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    sessions[session_id] = session
    return session


def list_sessions() -> list[dict[str, object]]:
    return [
        {
            "session_id": session["session_id"],
            "title": session["title"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
        }
        for session in sorted(
            sessions.values(), key=lambda session: session["updated_at"], reverse=True
        )
    ]


def get_session(
    session_id: str, update_timestamp: bool = False
) -> dict[str, object] | None:
    session = sessions.get(session_id)
    if session is not None and update_timestamp:
        touch_session(session)
    return session


def touch_session(session: dict[str, object]) -> None:
    """记录会话最新活动时间。"""
    session["updated_at"] = time.time()


def delete_session(session_id: str) -> bool:
    """删除会话及其内存中的消息历史。"""
    return sessions.pop(session_id, None) is not None
