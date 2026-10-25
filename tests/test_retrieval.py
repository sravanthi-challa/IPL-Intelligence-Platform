import pytest
import sys
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from document_builder import DocumentBuilder
from chunking import SemanticDocumentChunker, SlidingWindowChunker
from embeddings import get_embedding_provider
from vector_store import VectorStore

def test_build_match_document():
    doc = DocumentBuilder.build_match_document(335982)
    assert doc is not None
    assert doc["doc_id"] == "match_335982"
    assert "Kolkata Knight Riders" in doc["title"]
    assert "BB McCullum" in doc["content"]
    assert doc["metadata"]["winner"] == "Kolkata Knight Riders"

def test_build_player_document():
    doc = DocumentBuilder.build_player_document("Virat Kohli")
    assert doc is not None
    assert doc["doc_type"] == "player"
    assert "Kohli" in doc["title"]
    assert "Total Runs" in doc["content"]
    assert doc["metadata"]["total_runs"] > 7000

def test_chunking_strategies():
    sample_doc = {
        "doc_id": "test_1",
        "doc_type": "test",
        "title": "IPL Championship Overview",
        "content": (
            "Paragraph one introduces the Indian Premier League.\n\n"
            "Paragraph two explains the playoff system and finals.\n\n"
            "Paragraph three covers iconic milestones and awards."
        ),
        "metadata": {"test": True}
    }

    # 1. Semantic Chunker
    sem_chunker = SemanticDocumentChunker(max_chunk_words=10)
    sem_chunks = sem_chunker.chunk_document(sample_doc)
    assert len(sem_chunks) >= 2
    for sc in sem_chunks:
        assert "IPL Championship Overview" in sc["content"]

    # 2. Sliding Window Chunker
    slid_chunker = SlidingWindowChunker(window_size=10, overlap=3)
    slid_chunks = slid_chunker.chunk_document(sample_doc)
    assert len(slid_chunks) >= 2

def test_embedding_generation():
    embedder = get_embedding_provider()
    vec = embedder.embed_text("Who won the IPL in 2016?")
    assert len(vec) == embedder.dimension
    # Test L2 normalization
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-4

def test_vector_similarity_search():
    store = VectorStore()
    embedder = get_embedding_provider()
    
    query = "Cricket Glossary: Bowling Statistics & Wicket Rules"
    q_vec = embedder.embed_text(query)
    
    results = store.similarity_search(q_vec, top_k=3)
    assert len(results) > 0
    top = results[0]
    assert top["score"] > 0
    assert any("Bowling" in r["title"] or "wicket" in r["content"].lower() for r in results)

def test_lexical_full_text_search():
    store = VectorStore()
    results = store.lexical_search("Powerplay fielding restrictions", top_k=3)
    assert len(results) > 0
    # Should retrieve the glossary document for match phases
    assert any("Phase" in r["title"] or "Powerplay" in r["content"] for r in results)

def test_metadata_filtering():
    store = VectorStore()
    embedder = get_embedding_provider()
    q_vec = embedder.embed_text("Cricket batting rules")
    
    # Filter strictly for glossary
    glossary_results = store.similarity_search(q_vec, top_k=3, doc_type="glossary")
    for r in glossary_results:
        assert r["doc_type"] == "glossary"
