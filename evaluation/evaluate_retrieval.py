import json
import time
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from vector_store import VectorStore
from lexical_search import LexicalSearcher
from hybrid_retrieval import HybridRetriever
from reranker import Reranker
from embeddings import get_embedding_provider

BENCHMARK_FILE = PROJECT_ROOT / "evaluation" / "datasets" / "evaluation_cases.json"

def calculate_metrics(target_ranks: List[Optional[int]]) -> Dict[str, float]:
    n = len(target_ranks)
    if n == 0:
        return {"MRR": 0.0, "Recall@1": 0.0, "Recall@3": 0.0, "Recall@5": 0.0}

    reciprocal_ranks = [1.0 / r if r is not None and r > 0 else 0.0 for r in target_ranks]
    mrr = sum(reciprocal_ranks) / n
    recall_at_1 = sum(1 for r in target_ranks if r == 1) / n
    recall_at_3 = sum(1 for r in target_ranks if r is not None and r <= 3) / n
    recall_at_5 = sum(1 for r in target_ranks if r is not None and r <= 5) / n

    return {
        "MRR": round(mrr, 4),
        "Recall@1": round(recall_at_1 * 100, 1),
        "Recall@3": round(recall_at_3 * 100, 1),
        "Recall@5": round(recall_at_5 * 100, 1)
    }

def run_retrieval_evaluation():
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Filter cases with specific target document ID
    retrieval_cases = [c for c in cases if c.get("expected_source_id") and not c["expected_source_id"].startswith("postgres_sql")]
    print(f"Evaluating {len(retrieval_cases)} retrieval benchmark cases across 4 configurations...")

    store = VectorStore()
    embedder = get_embedding_provider()
    lexical = LexicalSearcher()
    hybrid = HybridRetriever()
    reranker = Reranker(enabled=True)

    configs = ["Vector Only", "Lexical Only", "Hybrid (RRF)", "Hybrid + Reranker"]
    results = {cfg: {"ranks": [], "times": []} for cfg in configs}

    for case in retrieval_cases:
        query = case["question"]
        target = case["expected_source_id"]

        # 1. Vector Only
        t0 = time.time()
        q_vec = embedder.embed_text(query)
        v_res = store.similarity_search(query_embedding=q_vec, top_k=5)
        results["Vector Only"]["times"].append((time.time() - t0) * 1000)
        v_rank = next((idx for idx, r in enumerate(v_res, 1) if target in r["doc_id"]), None)
        results["Vector Only"]["ranks"].append(v_rank)

        # 2. Lexical Only
        t0 = time.time()
        l_res = lexical.search(query=query, top_k=5)
        results["Lexical Only"]["times"].append((time.time() - t0) * 1000)
        l_rank = next((idx for idx, r in enumerate(l_res, 1) if target in r["doc_id"]), None)
        results["Lexical Only"]["ranks"].append(l_rank)

        # 3. Hybrid (RRF)
        t0 = time.time()
        h_res = hybrid.retrieve(query=query, top_k=5)
        results["Hybrid (RRF)"]["times"].append((time.time() - t0) * 1000)
        h_rank = next((idx for idx, r in enumerate(h_res, 1) if target in r["doc_id"]), None)
        results["Hybrid (RRF)"]["ranks"].append(h_rank)

        # 4. Hybrid + Reranker
        t0 = time.time()
        h_cand = hybrid.retrieve(query=query, top_k=8)
        rr_res = reranker.rerank(query=query, chunks=h_cand, top_k=5)
        results["Hybrid + Reranker"]["times"].append((time.time() - t0) * 1000)
        rr_rank = next((idx for idx, r in enumerate(rr_res, 1) if target in r["doc_id"]), None)
        results["Hybrid + Reranker"]["ranks"].append(rr_rank)

    # Output formatted report
    print("\n" + "=" * 75)
    print("                 RETRIEVAL EVALUATION BENCHMARK REPORT                 ")
    print("=" * 75)
    print(f"{'Configuration':<22} | {'MRR':<8} | {'Recall@1':<10} | {'Recall@3':<10} | {'Recall@5':<10} | {'Latency':<8}")
    print("-" * 75)

    summary_metrics = {}
    for cfg in configs:
        metrics = calculate_metrics(results[cfg]["ranks"])
        avg_time = sum(results[cfg]["times"]) / len(results[cfg]["times"])
        summary_metrics[cfg] = metrics
        summary_metrics[cfg]["latency_ms"] = round(avg_time, 2)
        print(f"{cfg:<22} | {metrics['MRR']:<8} | {metrics['Recall@1']:<9}% | {metrics['Recall@3']:<9}% | {metrics['Recall@5']:<9}% | {avg_time:.1f}ms")

    print("=" * 75)
    return summary_metrics

if __name__ == "__main__":
    run_retrieval_evaluation()
