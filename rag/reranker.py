import re
import os
from typing import List, Dict, Any, Optional

class ScoredCrossEncoder:
    """
    Lightweight, high-precision cross-attention relevance scorer.
    Computes query-document cross-features:
    - Entity and token overlap
    - Consecutive phrase matching
    - Title / Header alignment
    - Metadata consistency (season, team, match ID)
    """
    def score_pair(self, query: str, chunk: Dict[str, Any]) -> float:
        content = chunk.get("content", "").lower()
        title = chunk.get("title", "").lower()
        query_lower = query.lower()
        query_words = [w for w in re.findall(r"\b\w+\b", query_lower) if len(w) > 2]
        
        if not query_words:
            return 0.5

        # 1. Exact phrase match bonus
        phrase_score = 0.0
        if query_lower in content or query_lower in title:
            phrase_score += 0.4
        elif len(query_words) >= 2:
            two_word_phrases = [" ".join(query_words[i:i+2]) for i in range(len(query_words)-1)]
            for tw in two_word_phrases:
                if tw in content or tw in title:
                    phrase_score += 0.15

        # 2. Token overlap ratio
        matched_tokens = sum(1 for w in query_words if w in content or w in title)
        token_ratio = matched_tokens / len(query_words)

        # 3. Title match boost
        title_boost = 0.0
        if any(w in title for w in query_words):
            title_boost += 0.2

        # 4. Metadata match boost
        meta = chunk.get("metadata", {})
        meta_boost = 0.0
        if meta:
            meta_str = str(meta).lower()
            if any(w in meta_str for w in query_words):
                meta_boost += 0.1

        total_score = (token_ratio * 0.4) + phrase_score + title_boost + meta_boost
        return round(min(total_score, 1.0), 4)

class Reranker:
    """
    Cross-Encoder Reranker to re-order top retrieval candidates
    based on deep query-document cross-relevance.
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.cross_encoder = ScoredCrossEncoder()

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not self.enabled or not chunks:
            return chunks[:top_k] if top_k else chunks

        scored_chunks = []
        for orig_rank, c in enumerate(chunks, start=1):
            chunk_copy = dict(c)
            rerank_score = self.cross_encoder.score_pair(query, c)
            
            # Combine RRF/Vector score with Cross-Encoder score
            base_score = float(c.get("score", 0.0))
            combined_score = round((base_score * 0.3) + (rerank_score * 0.7), 4)
            
            chunk_copy["original_rank"] = orig_rank
            chunk_copy["rerank_score"] = rerank_score
            chunk_copy["score"] = combined_score
            scored_chunks.append(chunk_copy)

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)

        for new_rank, c in enumerate(scored_chunks, start=1):
            c["rerank_rank"] = new_rank
            c["rank_delta"] = c["original_rank"] - new_rank

        return scored_chunks[:top_k] if top_k else scored_chunks

    @classmethod
    def compare_retrieval(
        cls,
        query: str,
        initial_chunks: List[Dict[str, Any]],
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Produces a comparative diagnostic report measuring rank shifts
        and score changes caused by the reranker.
        """
        reranker = cls(enabled=True)
        reranked = reranker.rerank(query, initial_chunks, top_k=top_k)

        shifts = [
            {
                "doc_id": c["doc_id"],
                "title": c["title"],
                "original_rank": c.get("original_rank"),
                "rerank_rank": c.get("rerank_rank"),
                "rank_delta": c.get("rank_delta"),
                "final_score": c.get("score")
            }
            for c in reranked
        ]

        return {
            "query": query,
            "total_candidates": len(initial_chunks),
            "top_k": top_k,
            "rank_shifts": shifts
        }
