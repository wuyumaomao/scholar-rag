# Decision Log

| Date | Decision | Reason | Evidence |
| --- | --- | --- | --- |
| 2026-09-24 | Use multi-document Agent handoff memory. | Keep current state fast to read while preserving decisions, validation, backlog, and risks in dedicated files. | Bootstrap action. |
| 2026-09-24 | Keep the learning implementation under `learning-implementation/` and use a separate PostgreSQL Compose service on host port `55432`. | Preserve the original project as a reference and avoid colliding with its PostgreSQL port `5432` or database. | `learning-implementation/docker-compose.yml`; learning backend connects to `localhost:55432`. |
| 2026-09-24 | Store learning sessions and messages in PostgreSQL through `database.py` and `store.py`; keep routers focused on HTTP. | Demonstrate the separation between API routing, persistence logic, and the database before adding PDF and retrieval features. | `learning-implementation/backend/app/store.py`, `chat.py`, `sessions.py`; API persistence flow passed. |

## Decision Guidelines

- Record durable decisions only.
- Include reason and evidence.
- Do not record guesses as decisions.
- If evidence is missing, mark it as `UNKNOWN`.
