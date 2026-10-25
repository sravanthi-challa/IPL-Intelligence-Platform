import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from query_transformer import QueryTransformer
from reranker import Reranker, ScoredCrossEncoder
from pipeline import BaselineRAGPipeline

def test_query_transformer_pronoun_resolution():
    history = [
        {"role": "user", "content": "Who scored the most runs in IPL 2024?"},
        {"role": "assistant", "content": "Virat Kohli scored the most runs in IPL 2024 with 741 runs for Royal Challengers Bangalore."}
    ]
    followup_query = "How did he perform against CSK?"
    transformed = QueryTransformer.transform(followup_query, conversation_history=history)

    assert transformed.is_conversational_followup is True
    assert "Virat Kohli" in transformed.transformed_query
    assert "he" not in transformed.transformed_query.lower().split()
    assert transformed.season == "2024"
    assert transformed.team == "Chennai Super Kings"

def test_query_transformer_intent_extraction():
    q1 = "What are the cricket rules for tie and super overs?"
    t1 = QueryTransformer.transform(q1)
    assert t1.doc_type == "glossary"

    q2 = "Show me the career batting stats and profile of Rohit Sharma"
    t2 = QueryTransformer.transform(q2)
    assert t2.doc_type == "player"

    q3 = "Summarize the match between CSK and KKR in 2021"
    t3 = QueryTransformer.transform(q3)
    assert t3.doc_type == "match"
    assert t3.season == "2021"

def test_cross_encoder_scoring():
    scorer = ScoredCrossEncoder()
    query = "Tie Super Over rules"
    relevant_chunk = {
        "title": "Cricket Glossary: Ties, Super Overs, and No Results",
        "content": "When both teams score the exact same runs, the match is tied and resolved by a Super Over.",
        "metadata": {"doc_type": "glossary"}
    }
    irrelevant_chunk = {
        "title": "Match 100: Delhi vs Punjab",
        "content": "Delhi won the toss and elected to field on a sunny afternoon.",
        "metadata": {"doc_type": "match"}
    }

    score_rel = scorer.score_pair(query, relevant_chunk)
    score_irrel = scorer.score_pair(query, irrelevant_chunk)
    assert score_rel > score_irrel
    assert score_rel >= 0.5

def test_reranker_reordering():
    reranker = Reranker(enabled=True)
    query = "Virat Kohli century milestone"
    chunks = [
        {"chunk_id": "c1", "doc_id": "d1", "title": "Random Match", "content": "A match in 2012 with low scores.", "score": 0.5},
        {"chunk_id": "c2", "doc_id": "d2", "title": "Player Profile: V Kohli", "content": "Virat Kohli achieved multiple centuries and milestones in his IPL career.", "score": 0.4}
    ]
    reranked = reranker.rerank(query, chunks)
    # The chunk matching "Virat Kohli century milestone" should be promoted to rank 1
    assert reranked[0]["chunk_id"] == "c2"
    assert reranked[0]["original_rank"] == 2
    assert reranked[0]["rerank_rank"] == 1
    assert reranked[0]["rank_delta"] == 1

def test_pipeline_reranking_toggle():
    pipeline = BaselineRAGPipeline()
    # 1. Without reranking
    res1 = pipeline.answer_question(
        query="Explain the rules for Ties and Super Overs in IPL",
        doc_type="glossary",
        use_reranker=False
    )
    assert res1["route"] == "RAG_HYBRID"

    # 2. With reranking
    res2 = pipeline.answer_question(
        query="Explain the rules for Ties and Super Overs in IPL",
        doc_type="glossary",
        use_reranker=True
    )
    assert res2["route"] == "RAG_HYBRID_RERANKED"
    assert len(res2["retrieved_chunks"]) > 0
    assert "rerank_rank" in res2["retrieved_chunks"][0]
