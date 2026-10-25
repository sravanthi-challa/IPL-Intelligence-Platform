import os
import psycopg2

def fix():
    conn = psycopg2.connect(
        host="localhost",
        database="cricket_intelligence",
        user="postgres",
        password=os.environ.get("DB_PASSWORD", "")
    )
    cur = conn.cursor()
    cur.execute("UPDATE document_chunks SET doc_type = 'glossary' WHERE chunk_id LIKE 'dict_%' OR doc_id LIKE 'dict_%';")
    conn.commit()
    print("Updated glossary rows:", cur.rowcount)
    cur.close()
    conn.close()

if __name__ == "__main__":
    fix()
