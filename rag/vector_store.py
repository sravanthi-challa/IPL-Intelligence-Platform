import json
import os
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import numpy as np

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "database": os.environ.get("DB_NAME", "cricket_intelligence"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "port": int(os.environ.get("DB_PORT", 5432)),
}

class VectorStore:
    """
    PostgreSQL-backed Vector & Full-Text Retrieval Store for IPL Documents.
    Provides semantic vector similarity search, metadata filtering,
    and PostgreSQL lexical full-text search (FTS).
    """
    def __init__(self):
        self._ensure_table()

    def _get_connection(self):
        return psycopg2.connect(**DB_CONFIG)

    def _ensure_table(self):
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    chunk_id VARCHAR(100) PRIMARY KEY,
                    doc_id VARCHAR(100) NOT NULL,
                    doc_type VARCHAR(50) NOT NULL,
                    title VARCHAR(255),
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL,
                    embedding_model VARCHAR(100) NOT NULL,
                    embedding_dim INT NOT NULL,
                    embedding FLOAT8[] NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_doc_type ON document_chunks(doc_type);
                CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON document_chunks USING gin (metadata);
                CREATE INDEX IF NOT EXISTS idx_chunks_fts ON document_chunks USING gin (to_tsvector('english', content));
            """)
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def count(self) -> int:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM document_chunks;")
            return cur.fetchone()[0]
        finally:
            cur.close()
            conn.close()

    def upsert_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]], model_name: str):
        if not chunks:
            return

        conn = self._get_connection()
        cur = conn.cursor()
        try:
            data = []
            dim = len(embeddings[0])
            for c, emb in zip(chunks, embeddings):
                data.append((
                    c["chunk_id"],
                    c["doc_id"],
                    c.get("doc_type", "general"),
                    c.get("title", ""),
                    c["content"],
                    json.dumps(c.get("metadata", {})),
                    model_name,
                    dim,
                    emb
                ))

            sql = """
                INSERT INTO document_chunks (
                    chunk_id, doc_id, doc_type, title, content, metadata,
                    embedding_model, embedding_dim, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_dim = EXCLUDED.embedding_dim,
                    embedding = EXCLUDED.embedding,
                    created_at = CURRENT_TIMESTAMP;
            """
            execute_batch(cur, sql, data, page_size=500)
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        doc_type: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic vector search using cosine similarity
        with optional metadata and doc_type filters.
        """
        conn = self._get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            where_clauses = []
            params = []

            if doc_type:
                where_clauses.append("doc_type = %s")
                params.append(doc_type)

            if filter_metadata:
                where_clauses.append("metadata @> %s::jsonb")
                params.append(json.dumps(filter_metadata))

            where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            # Fetch candidate chunks and vectors
            sql = f"""
                SELECT 
                    chunk_id, doc_id, doc_type, title, content, metadata, embedding
                FROM document_chunks
                {where_str};
            """
            cur.execute(sql, params)
            rows = cur.fetchall()

            if not rows:
                return []

            # Compute Cosine Similarities with NumPy for sub-millisecond execution
            q_vec = np.array(query_embedding, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            if q_norm > 0:
                q_vec = q_vec / q_norm

            scored = []
            for r in rows:
                doc_vec = np.array(r["embedding"], dtype=np.float32)
                d_norm = np.linalg.norm(doc_vec)
                if d_norm > 0:
                    score = float(np.dot(q_vec, doc_vec / d_norm))
                else:
                    score = 0.0

                scored.append({
                    "chunk_id": r["chunk_id"],
                    "doc_id": r["doc_id"],
                    "doc_type": r["doc_type"],
                    "title": r["title"],
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "score": round(score, 4)
                })

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_k]

        finally:
            cur.close()
            conn.close()

    def lexical_search(
        self,
        query: str,
        top_k: int = 5,
        doc_type: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes PostgreSQL full-text search with ts_rank scoring.
        """
        conn = self._get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            where_clauses = ["to_tsvector('english', content) @@ plainto_tsquery('english', %s)"]
            params = [query]

            if doc_type:
                where_clauses.append("doc_type = %s")
                params.append(doc_type)

            if filter_metadata:
                where_clauses.append("metadata @> %s::jsonb")
                params.append(json.dumps(filter_metadata))

            sql = f"""
                SELECT 
                    chunk_id, doc_id, doc_type, title, content, metadata,
                    ts_rank(to_tsvector('english', content), plainto_tsquery('english', %s)) AS rank_score
                FROM document_chunks
                WHERE {' AND '.join(where_clauses)}
                ORDER BY rank_score DESC
                LIMIT %s;
            """
            params.append(top_k)
            cur.execute(sql, [query] + params)
            results = cur.fetchall()

            return [
                {
                    "chunk_id": r["chunk_id"],
                    "doc_id": r["doc_id"],
                    "doc_type": r["doc_type"],
                    "title": r["title"],
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "score": round(float(r["rank_score"]), 4)
                }
                for r in results
            ]
        finally:
            cur.close()
            conn.close()
