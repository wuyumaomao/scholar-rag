"""Run once for existing databases: python scripts/migrate_message_sources.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage.database import get_connection


def main() -> None:
    migration = Path(__file__).resolve().parents[2] / "db/migrations/001_message_sources.sql"
    with get_connection() as connection:
        connection.execute(migration.read_text(encoding="utf-8"))
    print("Message sources migration applied (existing messages preserved).")


if __name__ == "__main__":
    main()
