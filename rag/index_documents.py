import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from document_builder import DocumentBuilder
from chunking import SemanticDocumentChunker
from embeddings import get_embedding_provider
from vector_store import VectorStore

def index_corpus(match_limit: int = 150):
    """
    Indexes cricket glossary, top player profiles, and high-profile/seasonal matches
    into PostgreSQL document_chunks with semantic embeddings.
    """
    start_time = time.time()
    print("=" * 60)
    print("      INITIALIZING DOCUMENT GENERATION & INDEXING      ")
    print("=" * 60)

    chunker = SemanticDocumentChunker(max_chunk_words=350)
    embedder = get_embedding_provider()
    store = VectorStore()
    
    print(f"Embedding Provider: {embedder.model_name} (Dimensions: {embedder.dimension})")

    documents: List[Dict[str, Any]] = []

    # 1. Data Dictionary / Glossary
    print("\n1. Generating Cricket Glossary Documents...")
    glossary_docs = DocumentBuilder.build_data_dictionary_documents()
    documents.extend(glossary_docs)
    print(f"   Generated {len(glossary_docs)} glossary documents.")

    # 2. Top Player Profiles
    print("\n2. Generating Top Player Career Profiles...")
    conn = psycopg2.connect(
        host="localhost",
        database="cricket_intelligence",
        user="postgres",
        password=os.environ.get("DB_PASSWORD", "")
    )
    cur = conn.cursor()
    # Fetch top 60 batters and top 60 bowlers
    cur.execute("""
        SELECT DISTINCT player_name FROM (
            (SELECT player_name FROM v_batter_summary ORDER BY total_runs DESC LIMIT 60)
            UNION
            (SELECT player_name FROM v_bowler_summary ORDER BY wickets DESC LIMIT 60)
        ) sub;
    """)
    players = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    for p in players:
        p_doc = DocumentBuilder.build_player_document(p)
        if p_doc:
            documents.append(p_doc)
    print(f"   Generated {len(players)} player career documents.")

    # 3. Matches (Finals, Playoffs, and representative historical matches)
    print(f"\n3. Generating Match Documents (sample limit: {match_limit})...")
    conn = psycopg2.connect(
        host="localhost",
        database="cricket_intelligence",
        user="postgres",
        password=os.environ.get("DB_PASSWORD", "")
    )
    cur = conn.cursor()
    # Prioritize finals and playoff matches, then representative matches
    cur.execute("""
        SELECT match_id FROM fact_matches
        ORDER BY match_date DESC
        LIMIT %s;
    """, (match_limit,))
    match_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    for m_id in match_ids:
        m_doc = DocumentBuilder.build_match_document(m_id)
        if m_doc:
            documents.append(m_doc)
    print(f"   Generated {len(match_ids)} match documents.")

    # 4. Chunk Documents
    print(f"\n4. Chunking {len(documents)} documents using SemanticDocumentChunker...")
    all_chunks: List[Dict[str, Any]] = []
    for doc in documents:
        chunks = chunker.chunk_document(doc)
        all_chunks.extend(chunks)
    print(f"   Created {len(all_chunks)} chunks.")

    # 5. Generate Embeddings & Upsert to PostgreSQL
    print("\n5. Generating Embeddings in batches...")
    BATCH_SIZE = 50
    total_chunks = len(all_chunks)
    for i in range(0, total_chunks, BATCH_SIZE):
        batch = all_chunks[i:i+BATCH_SIZE]
        texts = [c["content"] for c in batch]
        embeddings = embedder.embed_batch(texts)
        store.upsert_chunks(batch, embeddings, embedder.model_name)
        print(f"   Indexed [{min(i+BATCH_SIZE, total_chunks)}/{total_chunks}] chunks...")

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"INDEXING COMPLETE in {elapsed:.2f} seconds!")
    print(f"Total Chunks in Vector Store: {store.count()}")
    print("=" * 60)

if __name__ == "__main__":
    index_corpus(match_limit=150)
