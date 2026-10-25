import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "evaluation"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))

from evaluate_retrieval import calculate_metrics, run_retrieval_evaluation
from evaluate_answers import run_answers_evaluation

def test_calculate_metrics_edge_cases():
    # Empty
    empty_res = calculate_metrics([])
    assert empty_res["MRR"] == 0.0
    assert empty_res["Recall@1"] == 0.0

    # Perfect ranking: all rank 1
    perf = calculate_metrics([1, 1, 1])
    assert perf["MRR"] == 1.0
    assert perf["Recall@1"] == 100.0
    assert perf["Recall@3"] == 100.0

    # Mixed ranking: [1, 2, None, 4]
    # reciprocal ranks: 1/1=1, 1/2=0.5, 0, 1/4=0.25 -> sum = 1.75 / 4 = 0.4375
    # recall@1: 1/4 = 25%
    # recall@3: 2/4 = 50%
    # recall@5: 3/4 = 75%
    res = calculate_metrics([1, 2, None, 4])
    assert res["MRR"] == 0.4375
    assert res["Recall@1"] == 25.0
    assert res["Recall@3"] == 50.0
    assert res["Recall@5"] == 75.0

def test_retrieval_evaluation_benchmarks():
    metrics = run_retrieval_evaluation()
    assert "Vector Only" in metrics
    assert "Lexical Only" in metrics
    assert "Hybrid (RRF)" in metrics
    assert "Hybrid + Reranker" in metrics

    hybrid_rr = metrics["Hybrid + Reranker"]
    assert hybrid_rr["MRR"] >= 0.70, f"Expected MRR >= 0.70, got {hybrid_rr['MRR']}"
    assert hybrid_rr["Recall@3"] >= 75.0, f"Expected Recall@3 >= 75%, got {hybrid_rr['Recall@3']}%"
    assert hybrid_rr["Recall@1"] >= 60.0, f"Expected Recall@1 >= 60%, got {hybrid_rr['Recall@1']}%"

def test_answers_evaluation_benchmarks():
    results = run_answers_evaluation()
    assert results["total_cases"] >= 10
    assert results["route_accuracy"] >= 90.0, f"Route accuracy too low: {results['route_accuracy']}%"
    assert results["grounding_rate"] >= 80.0, f"Grounding rate too low: {results['grounding_rate']}%"
    assert results["citation_rate"] >= 90.0, f"Citation rate too low: {results['citation_rate']}%"
    assert results["avg_latency_ms"] < 2000.0, f"Average latency too high: {results['avg_latency_ms']}ms"
