import re
import os
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "database": os.environ.get("DB_NAME", "cricket_intelligence"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "port": int(os.environ.get("DB_PORT", 5432)),
}

# Standard IPL Franchise Aliases
TEAM_ALIASES = {
    "csk": "Chennai Super Kings",
    "rcb": "Royal Challengers Bangalore",
    "mi": "Mumbai Indians",
    "kkr": "Kolkata Knight Riders",
    "dc": "Delhi Capitals",
    "rr": "Rajasthan Royals",
    "srh": "Sunrisers Hyderabad",
    "pbks": "Punjab Kings",
    "kxip": "Kings XI Punjab",
    "lsg": "Lucknow Super Giants",
    "gt": "Gujarat Titans",
}

# Prominent Player Nicknames / Aliases
PLAYER_ALIASES = {
    "thala": "MS Dhoni",
    "msd": "MS Dhoni",
    "virat": "V Kohli",
    "kohli": "V Kohli",
    "king kohli": "V Kohli",
    "hitman": "RG Sharma",
    "rohit": "RG Sharma",
    "bumrah": "JJ Bumrah",
    "chahal": "YS Chahal",
    "bhuvi": "B Kumar",
    "abd": "AB de Villiers",
    "mr 360": "AB de Villiers",
}

class LexicalSearcher:
    """
    PostgreSQL Full-Text Search retriever enhanced with IPL cricket alias expansions,
    exact match identifier lookups, and metadata filtering.
    """
    def __init__(self):
        pass

    def _get_connection(self):
        return psycopg2.connect(**DB_CONFIG)

    @staticmethod
    def expand_query(query: str) -> str:
        """Expands known team abbreviations and player aliases into standard names."""
        expanded_query = query
        words = re.findall(r"\b\w+\b", query.lower())

        # Check multi-word aliases
        query_lower = query.lower()
        for alias, full_name in PLAYER_ALIASES.items():
            if " " in alias and alias in query_lower:
                expanded_query = re.sub(rf"\b{re.escape(alias)}\b", full_name, expanded_query, flags=re.IGNORECASE)

        # Check single-word aliases
        for w in words:
            if w in TEAM_ALIASES:
                expanded_query = re.sub(rf"\b{re.escape(w)}\b", TEAM_ALIASES[w], expanded_query, flags=re.IGNORECASE)
            elif w in PLAYER_ALIASES:
                expanded_query = re.sub(rf"\b{re.escape(w)}\b", PLAYER_ALIASES[w], expanded_query, flags=re.IGNORECASE)

        return expanded_query

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_type: Optional[str] = None,
        season: Optional[str] = None,
        team: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        expanded = self.expand_query(query)
        conn = self._get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Check for direct match ID query
            match_id_match = re.search(r"\b(\d{6,7})\b", query)
            if match_id_match:
                mid = match_id_match.group(1)
                cur.execute("""
                    SELECT chunk_id, doc_id, doc_type, title, content, metadata, 1.0 AS score
                    FROM document_chunks
                    WHERE doc_id = %s OR chunk_id ILIKE %s
                    LIMIT %s;
                """, (f"match_{mid}", f"%{mid}%", top_k))
                rows = cur.fetchall()
                if rows:
                    return [dict(r) for r in rows]
                
                # Dynamic On-Demand Indexing for any match in the 1,241 database
                try:
                    from document_builder import DocumentBuilder
                    from chunking import SemanticDocumentChunker
                    from embeddings import get_embedding_provider
                    from vector_store import VectorStore
                    m_doc = DocumentBuilder.build_match_document(int(mid))
                    if m_doc:
                        chunker = SemanticDocumentChunker()
                        embedder = get_embedding_provider()
                        store = VectorStore()
                        chunks = chunker.chunk_document(m_doc)
                        embs = embedder.embed_batch([c["content"] for c in chunks])
                        store.upsert_chunks(chunks, embs, embedder.model_name)
                        return [
                            {
                                "chunk_id": c["chunk_id"],
                                "doc_id": c["doc_id"],
                                "doc_type": c["doc_type"],
                                "title": c["title"],
                                "content": c["content"],
                                "metadata": c["metadata"],
                                "score": 1.0
                            }
                            for c in chunks[:top_k]
                        ]
                except Exception:
                    pass

            # Construct full-text query
            where_clauses = ["to_tsvector('english', content) @@ plainto_tsquery('english', %s)"]
            params: List[Any] = [expanded]

            if doc_type:
                where_clauses.append("doc_type = %s")
                params.append(doc_type)

            if season:
                where_clauses.append("metadata->>'season' = %s")
                params.append(str(season))

            if team:
                where_clauses.append("(metadata->'teams' ? %s OR metadata->>'player_name' = %s)")
                params.append(team)
                params.append(team)

            sql = f"""
                SELECT 
                    chunk_id, doc_id, doc_type, title, content, metadata,
                    ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', %s)) AS score
                FROM document_chunks
                WHERE {' AND '.join(where_clauses)}
                ORDER BY score DESC
                LIMIT %s;
            """
            params.append(top_k)
            cur.execute(sql, [expanded] + params)
            results = cur.fetchall()

            return [
                {
                    "chunk_id": r["chunk_id"],
                    "doc_id": r["doc_id"],
                    "doc_type": r["doc_type"],
                    "title": r["title"],
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "score": round(float(r["score"]), 4)
                }
                for r in results
            ]
        finally:
            cur.close()
            conn.close()
