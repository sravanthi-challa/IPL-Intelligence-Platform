import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from lexical_search import LexicalSearcher
from hybrid_retrieval import HybridRetriever
from pipeline import BaselineRAGPipeline

def test_query_alias_expansion():
    # Team alias expansion
    exp1 = LexicalSearcher.expand_query("CSK vs RCB match summary")
    assert "Chennai Super Kings" in exp1
    assert "Royal Challengers Bangalore" in exp1

    # Player alias expansion
    exp2 = LexicalSearcher.expand_query("How many runs did Thala score?")
    assert "MS Dhoni" in exp2

    exp3 = LexicalSearcher.expand_query("What is Hitman strike rate?")
    assert "RG Sharma" in exp3

def test_lexical_search_exact_match():
    searcher = LexicalSearcher()
    results = searcher.search("Tell me about match 335982", top_k=2)
    assert len(results) > 0
    top = results[0]
    assert "335982" in top["chunk_id"] or "335982" in top["doc_id"]
    assert top["score"] == 1.0

def test_metadata_filtering():
    searcher = LexicalSearcher()
    # Search with season filter
    results = searcher.search(
        query="Kolkata Knight Riders",
        season="2016",
        doc_type="match",
        top_k=3
    )
    for r in results:
        assert r["doc_type"] == "match"
        assert r["metadata"]["season"] == "2016"

def test_reciprocal_rank_fusion_boosting():
    retriever = HybridRetriever(k_rrf=60)
    query = "Tie Super Over match rules"
    results = retriever.retrieve(query, top_k=5)
    assert len(results) > 0
    top = results[0]
    # Check that top result has an RRF score
    assert "rrf_score" in top
    assert top["rrf_score"] > 0
    # The glossary document about Super Overs should rank at the top
    assert any("Super Overs" in r["title"] or "Tie" in r["title"] for r in results[:2])

def test_hybrid_pipeline_execution():
    pipeline = BaselineRAGPipeline(use_hybrid=True)
    res = pipeline.answer_question(
        query="Explain the rules for Ties and Super Overs in IPL",
        doc_type="glossary",
        top_k=2
    )
    assert res["route"] in ("RAG_HYBRID", "RAG_HYBRID_RERANKED")
    assert len(res["retrieved_chunks"]) > 0
    assert len(res["sources"]) > 0
    assert "Super Over" in res["answer"] or "tie" in res["answer"].lower()
