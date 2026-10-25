import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg2
from embeddings import get_embedding_provider
from vector_store import VectorStore

def check_chunks():
    store = VectorStore()
    embedder = get_embedding_provider()
    
    conn = psycopg2.connect(host="localhost", database="cricket_intelligence", user="postgres", password=os.environ.get("DB_PASSWORD", ""))
    cur = conn.cursor()
    cur.execute("SELECT chunk_id, title FROM document_chunks WHERE doc_type = 'player' LIMIT 10;")
    rows = cur.fetchall()
    print("Sample player chunks in DB:")
    for r in rows:
        print(" ", r)

    # Check if V Kohli is in the table
    cur.execute("SELECT chunk_id, title FROM document_chunks WHERE title ILIKE '%Kohli%';")
    kohli_rows = cur.fetchall()
    print("Kohli rows in DB:", kohli_rows)

    if kohli_rows:
        chunk_id = kohli_rows[0][0]
        cur.execute("SELECT content FROM document_chunks WHERE chunk_id = %s;", (chunk_id,))
        print("\nKohli chunk content sample:\n", cur.fetchone()[0][:200])

    # Run query
    query = "V Kohli batting career profile"
    q_vec = embedder.embed_text(query)
    results = store.similarity_search(q_vec, top_k=5, doc_type="player")
    print("\nSearch results for query:", query)
    for res in results:
        print(f"  Score: {res['score']} | Title: {res['title']}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    check_chunks()
