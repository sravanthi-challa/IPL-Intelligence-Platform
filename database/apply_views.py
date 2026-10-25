import os
import psycopg2
from pathlib import Path

def apply_views():
    sql_file = Path(__file__).resolve().parent / "views.sql"
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    conn = psycopg2.connect(
        host="localhost",
        database="cricket_intelligence",
        user="postgres",
        password=os.environ.get("DB_PASSWORD", "")
    )
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    print("All views created successfully in PostgreSQL.")
    
    cur.execute("""
        SELECT table_name 
        FROM information_schema.views 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    views = cur.fetchall()
    print(f"Active views ({len(views)}):")
    for v in views:
        print(f"  - {v[0]}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    apply_views()
