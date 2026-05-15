import psycopg
import os
from core.database import DB_SESSION_OPTIONS

def check_latest():
    conn_str = os.getenv("DATABASE_URL")
    if not conn_str:
        # Try to read from .env if possible, but let's assume it's in env or we can find it
        # Actually database.py might have a way to get the connection string
        from core.config import DATABASE_URL
        conn_str = DATABASE_URL

    with psycopg.connect(conn_str, options=DB_SESSION_OPTIONS) as conn:
        with conn.cursor() as cur:
            for lang in ['MK', 'RS']:
                print(f"Checking latest for {lang}...")
                cur.execute("SELECT source, title, created_at FROM articles WHERE country = %s ORDER BY created_at DESC LIMIT 5", (lang,))
                rows = cur.fetchall()
                for row in rows:
                    print(f"  {row[2]} | {row[0]} | {row[1]}")
                print("-" * 20)

if __name__ == "__main__":
    check_latest()
