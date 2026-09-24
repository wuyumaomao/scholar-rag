from app.database import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database();")
        print(cur.fetchone())