"""内存会话存储。"""

from uuid import uuid4

sessions: dict[str, dict[str, str]] = {}


def create_session() -> dict[str, str]:
    session_id = str(uuid4())
    session = {"session_id": session_id}
    sessions[session_id] = session
    return session


def list_sessions() -> list[dict[str, str]]:
    return list(sessions.values())


def get_session(session_id: str) -> dict[str, str] | None:
    return sessions.get(session_id)
