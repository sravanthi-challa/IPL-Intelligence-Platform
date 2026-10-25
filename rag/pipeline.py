import os
from typing import Dict, Any, Optional, List
from embeddings import get_embedding_provider
from vector_store import VectorStore
from lexical_search import LexicalSearcher
from hybrid_retrieval import HybridRetriever
from query_transformer import QueryTransformer
from reranker import Reranker
from context_builder import ContextBuilder
from generator import RAGGenerator

class BaselineRAGPipeline:
    """
    Production-grade conversational RAG pipeline integrating:
    1. Query Transformation (pronoun resolution, alias expansion, filter extraction)
    2. Hybrid Retrieval (Vector Similarity + PostgreSQL Lexical FTS via RRF)
    3. Cross-Encoder Reranking (optional contextual relevance scoring)
    4. Evidence Assembly & Grounded Generation with Citations
    """
    def __init__(self, use_hybrid: bool = True, use_reranker: Optional[bool] = None):
        self.use_hybrid = use_hybrid
        if use_reranker is not None:
            self.use_reranker = use_reranker
        else:
            self.use_reranker = os.environ.get("RERANKER_ENABLED", "false").lower() in ("true", "1")
            
        self.store = VectorStore()
        self.embedder = get_embedding_provider()
        self.lexical = LexicalSearcher()
        self.hybrid_retriever = HybridRetriever()
        self.reranker = Reranker(enabled=self.use_reranker)
        self.generator = RAGGenerator()

    def answer_question(
        self,
        query: str,
        top_k: int = 4,
        doc_type: Optional[str] = None,
        season: Optional[str] = None,
        team: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        use_hybrid: Optional[bool] = None,
        use_reranker: Optional[bool] = None
    ) -> Dict[str, Any]:
        # 1. Transform Query & Extract Filters
        transformed_obj = QueryTransformer.transform(query, conversation_history)
        search_query = transformed_obj.transformed_query
        effective_season = season or transformed_obj.season
        effective_team = team or transformed_obj.team
        effective_doc_type = doc_type or transformed_obj.doc_type

        is_hybrid = self.use_hybrid if use_hybrid is None else use_hybrid
        should_rerank = self.use_reranker if use_reranker is None else use_reranker

        # Fetch extra candidates for reranking
        fetch_k = top_k * 2 if should_rerank else top_k

        if is_hybrid:
            # 2. Hybrid Retrieval (RRF)
            raw_chunks = self.hybrid_retriever.retrieve(
                query=search_query,
                top_k=fetch_k,
                doc_type=effective_doc_type,
                season=effective_season,
                team=effective_team
            )
            route_name = "RAG_HYBRID"
        else:
            # 2. Pure Vector Search
            query_vector = self.embedder.embed_text(search_query)
            raw_chunks = self.store.similarity_search(
                query_embedding=query_vector,
                top_k=fetch_k,
                doc_type=effective_doc_type,
                filter_metadata=filter_metadata
            )
            route_name = "RAG_VECTOR"

        # 3. Optional Reranking
        if should_rerank and raw_chunks:
            reranker_instance = Reranker(enabled=True)
            chunks = reranker_instance.rerank(search_query, raw_chunks, top_k=top_k)
            route_name += "_RERANKED"
        else:
            chunks = raw_chunks[:top_k]

        # 4. Assemble Context with Provenance
        context_res = ContextBuilder.build_context(chunks)

        # 5. Generate Grounded Answer
        answer = self.generator.generate_answer(
            question=query,
            context_text=context_res["context_text"],
            conversation_history=conversation_history
        )

        return {
            "query": query,
            "transformed_query": search_query,
            "answer": answer,
            "route": route_name,
            "sources": context_res["sources"],
            "retrieved_chunks": [
                {
                    "chunk_id": c["chunk_id"],
                    "doc_id": c["doc_id"],
                    "title": c["title"],
                    "score": c.get("score"),
                    "original_rank": c.get("original_rank"),
                    "rerank_rank": c.get("rerank_rank"),
                    "rrf_score": c.get("rrf_score")
                }
                for c in chunks
            ]
        }
