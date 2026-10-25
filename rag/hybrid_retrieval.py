from typing import List, Dict, Any, Optional
from embeddings import get_embedding_provider
from vector_store import VectorStore
from lexical_search import LexicalSearcher

class HybridRetriever:
    """
    Production Hybrid Retriever combining dense vector semantic similarity
    with PostgreSQL lexical full-text search using Reciprocal Rank Fusion (RRF).
    """
    def __init__(self, k_rrf: int = 60, vector_weight: float = 1.0, lexical_weight: float = 1.0):
        self.k_rrf = k_rrf
        self.vector_weight = vector_weight
        self.lexical_weight = lexical_weight
        self.store = VectorStore()
        self.embedder = get_embedding_provider()
        self.lexical = LexicalSearcher()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        doc_type: Optional[str] = None,
        season: Optional[str] = None,
        team: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        candidate_pool_size = max(top_k * 3, 15)

        # 1. Dense Semantic Search
        query_vector = self.embedder.embed_text(query)
        vector_filter = {}
        if season:
            vector_filter["season"] = str(season)
        if team:
            vector_filter["teams"] = [team]

        vector_results = self.store.similarity_search(
            query_embedding=query_vector,
            top_k=candidate_pool_size,
            doc_type=doc_type,
            filter_metadata=vector_filter if vector_filter else None
        )

        # 2. Lexical Full-Text Search with Alias Expansion
        lexical_results = self.lexical.search(
            query=query,
            top_k=candidate_pool_size,
            doc_type=doc_type,
            season=season,
            team=team
        )

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF_score(d) = sum( weight / (k + rank) )
        doc_map: Dict[str, Dict[str, Any]] = {}
        rrf_scores: Dict[str, float] = {}

        # Process vector ranks (1-indexed)
        for rank, item in enumerate(vector_results, start=1):
            cid = item["chunk_id"]
            doc_map[cid] = item
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (self.vector_weight / (self.k_rrf + rank))
            item["vector_rank"] = rank
            item["vector_score"] = item["score"]

        # Process lexical ranks (1-indexed)
        for rank, item in enumerate(lexical_results, start=1):
            cid = item["chunk_id"]
            if cid not in doc_map:
                doc_map[cid] = item
                item["vector_rank"] = None
                item["vector_score"] = None
            item["lexical_rank"] = rank
            item["lexical_score"] = item["score"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (self.lexical_weight / (self.k_rrf + rank))

        # Assign final RRF score and sort
        combined = []
        for cid, item in doc_map.items():
            final_score = rrf_scores[cid]
            item_copy = dict(item)
            item_copy["rrf_score"] = round(final_score, 6)
            item_copy["score"] = item_copy["rrf_score"]
            combined.append(item_copy)

        combined.sort(key=lambda x: x["rrf_score"], reverse=True)
        return combined[:top_k]
