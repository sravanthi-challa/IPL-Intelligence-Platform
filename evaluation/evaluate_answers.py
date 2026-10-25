import json
import time
import sys
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from orchestrator import ConversationalOrchestrator

BENCHMARK_FILE = PROJECT_ROOT / "evaluation" / "datasets" / "evaluation_cases.json"

def run_answers_evaluation() -> Dict[str, Any]:
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    orchestrator = ConversationalOrchestrator()

    total_cases = len(cases)
    route_matches = 0
    keyword_hits = 0
    citation_hits = 0
    refusal_hits = 0
    total_latency = 0.0

    print(f"Running end-to-end answer evaluation on {total_cases} benchmark test cases...")

    eval_results = []

    for c in cases:
        q = c["question"]
        expected_route = c["expected_route"]
        expected_kws = c.get("expected_keywords", [])

        t0 = time.time()
        res = orchestrator.process_query(q)
        lat = (time.time() - t0) * 1000
        total_latency += lat

        route_match = res["route"] == expected_route or (expected_route == "RAG_ONLY" and "RAG" in res["route"])
        if route_match:
            route_matches += 1

        # Check keyword support
        answer_text = res["answer"].lower()
        kw_found = any(kw.lower() in answer_text for kw in expected_kws) if expected_kws else True
        if kw_found:
            keyword_hits += 1

        # Check citations
        has_citations = len(res.get("sources", [])) > 0 or "[Doc:" in res["answer"] or "[Source:" in res["answer"]
        if has_citations or expected_route in ("CLARIFICATION", "INSUFFICIENT_DATA"):
            citation_hits += 1

        # Check refusal on out-of-scope
        if expected_route == "INSUFFICIENT_DATA":
            if res["route"] == "INSUFFICIENT_DATA":
                refusal_hits += 1

        eval_results.append({
            "id": c["id"],
            "question": q,
            "expected_route": expected_route,
            "actual_route": res["route"],
            "route_match": route_match,
            "keywords_grounded": kw_found,
            "latency_ms": round(lat, 2)
        })

    route_accuracy = (route_matches / total_cases) * 100
    grounding_rate = (keyword_hits / total_cases) * 100
    citation_rate = (citation_hits / total_cases) * 100
    avg_latency = total_latency / total_cases

    print("\n" + "=" * 70)
    print("            END-TO-END SYSTEM & GENERATION EVALUATION REPORT            ")
    print("=" * 70)
    print(f"Total Benchmark Cases Evaluated : {total_cases}")
    print(f"Routing Classification Accuracy : {route_accuracy:.1f}% ({route_matches}/{total_cases})")
    print(f"Evidence Grounding / Key Facts : {grounding_rate:.1f}% ({keyword_hits}/{total_cases})")
    print(f"Citation Attribution Rate      : {citation_rate:.1f}% ({citation_hits}/{total_cases})")
    print(f"Average Request Latency        : {avg_latency:.1f}ms")
    print("=" * 70)

    return {
        "total_cases": total_cases,
        "route_accuracy": route_accuracy,
        "grounding_rate": grounding_rate,
        "citation_rate": citation_rate,
        "avg_latency_ms": round(avg_latency, 2),
        "details": eval_results
    }

if __name__ == "__main__":
    run_answers_evaluation()
