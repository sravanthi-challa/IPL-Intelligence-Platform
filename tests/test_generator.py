import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from context_builder import ContextBuilder
from generator import OfflineGroundedGenerator, RAGGenerator
from pipeline import BaselineRAGPipeline

def test_context_builder_deduplication():
    chunks = [
        {"chunk_id": "c1", "doc_id": "doc_1", "title": "IPL Match 1", "content": "Text A"},
        {"chunk_id": "c2", "doc_id": "doc_1", "title": "IPL Match 1", "content": "Text B"},
        {"chunk_id": "c3", "doc_id": "doc_2", "title": "IPL Match 2", "content": "Text C"},
    ]
    res = ContextBuilder.build_context(chunks)
    assert res["chunks_used"] == 2  # doc_1 deduplicated
    assert len(res["sources"]) == 2
    assert "doc_1" in res["context_text"]
    assert "doc_2" in res["context_text"]

def test_context_builder_with_sql():
    sql_data = [
        {"player_name": "V Kohli", "total_runs": 9271, "strike_rate": 134.6}
    ]
    res = ContextBuilder.build_context([], sql_data=sql_data)
    assert "VERIFIED DATABASE SQL RESULTS" in res["context_text"]
    assert "V Kohli" in res["context_text"]
    assert "9271" in res["context_text"]

def test_offline_grounded_generator():
    generator = OfflineGroundedGenerator()
    user_prompt = (
        "=== RETRIEVED CRICKET EVIDENCE ===\n"
        "[Evidence Block 1]\n"
        "Document ID: dict_bowling_metrics\n"
        "Title: Cricket Glossary: Bowling Statistics & Wicket Rules\n"
        "Content:\nOnly dismissals caused by the bowler are credited as bowler wickets: bowled, caught, lbw, stumped.\n"
        "===================================\n\n"
        "USER QUESTION: Which dismissals count as bowler wickets?"
    )
    answer = generator.generate(user_prompt)
    assert "[Doc: dict_bowling_metrics]" in answer
    assert "bowled" in answer or "bowler wickets" in answer

def test_offline_grounded_generator_insufficient_evidence():
    generator = OfflineGroundedGenerator()
    user_prompt = "USER QUESTION: What will be the price of cricket bats in 2035?"
    answer = generator.generate(user_prompt)
    assert "do not contain sufficient evidence" in answer

def test_baseline_rag_pipeline():
    pipeline = BaselineRAGPipeline()
    res = pipeline.answer_question(
        query="Cricket Glossary: Bowling Statistics & Wicket Rules",
        top_k=2
    )
    assert res["query"] is not None
    assert len(res["retrieved_chunks"]) > 0
    assert len(res["sources"]) > 0
    assert len(res["answer"]) > 0
    assert res["route"] in ("RAG_BASELINE", "RAG_HYBRID", "RAG_HYBRID_RERANKED")
