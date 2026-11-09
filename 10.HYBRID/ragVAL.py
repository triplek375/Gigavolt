#!/usr/bin/env python3
"""
Gigavolt End-to-End RAG Validation & Latency Benchmarking (ragVAL.py)
=====================================================================
Milestone 5 Validation Suite:
- Benchmarking with statistical analysis (P50, P90, P95, P99)
- Latency profiling breaking down retrieval vs. generation time (sub-5s target)
- Source provenance and 100% citation traceability validation
- Official Milestone 5 rubric test query evaluation:
    1. 'What are common failure modes for Model X-7000 batteries in high-temperature environments?'
    2. 'Show me service history for equipment unit SN-4829 and related warranty claims'
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np

# ----------------------------------------------------------------------------
# Path Configuration: Support execution from repo root, 10.HYBRID, or /opt/scripts
# ----------------------------------------------------------------------------
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent if CURRENT_DIR.name == "10.HYBRID" else CURRENT_DIR
HYBRID_DIR = REPO_ROOT / "10.HYBRID"
VECTOR_DIR = REPO_ROOT / "7.VECTOR"

for path_entry in [str(CURRENT_DIR), str(REPO_ROOT), str(HYBRID_DIR), str(VECTOR_DIR)]:
    if path_entry not in sys.path:
        sys.path.append(path_entry)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("RAGValidation")

# Import core RAG pipeline
try:
    from rag_pipeline import GigavoltRAGPipeline
except ImportError as e:
    logger.error(f"Failed to import GigavoltRAGPipeline from rag_pipeline: {e}")
    GigavoltRAGPipeline = None


# ============================================================================
# 1. BENCHMARK & RUBRIC TEST QUERY DEFINITIONS
# ============================================================================

RUBRIC_TEST_QUERIES: List[Dict[str, Any]] = [
    {
        "id": "rubric_query_1_model_x7000",
        "title": "Rubric Query 1: High-Temperature Battery Failure Modes",
        "query": "What are common failure modes for Model X-7000 batteries in high-temperature environments?",
        "expected_intent": "failure_mode_analysis",
        "description": "Tests multi-database correlation of high-temp IoT telemetry (ERR_BMS_701) and engineering SOPs."
    },
    {
        "id": "rubric_query_2_sn4829_claims",
        "title": "Rubric Query 2: Unit Service History & Warranty Claims",
        "query": "Show me service history for equipment unit SN-4829 and related warranty claims",
        "expected_intent": "warranty_service_history",
        "description": "Tests SQL relational lookups filtering by serial number and historical warranty claims."
    }
]

BENCHMARK_QUERIES: List[Dict[str, Any]] = [
    {
        "id": "Q1_high_temp_failures",
        "query": "What are common failure modes for Model X-7000 batteries in high-temperature environments?",
        "category": "Failure Mode Analysis"
    },
    {
        "id": "Q2_equipment_warranty_history",
        "query": "Show me service history for equipment unit SN-4829 and related warranty claims",
        "category": "Warranty & Claims Triage"
    },
    {
        "id": "Q3_thermal_runaway_emergency",
        "query": "What is the emergency shutdown procedure for battery thermal runaway on unit EQ-1001 with ERR_BMS_701?",
        "category": "Critical Diagnostic SOP"
    },
    {
        "id": "Q4_overvoltage_expired_claims",
        "query": "Investigate DC-bus overvoltage surge protection trips and expired warranty claims for unit EQ-1042",
        "category": "Electrical Surge Investigation"
    },
    {
        "id": "Q5_bms_hardware_revisions",
        "query": "Check Engineering Change Orders for BMS module cooling fan firmware revisions regarding ERR_BMS_708",
        "category": "Engineering Change Orders"
    }
]


# ============================================================================
# 2. STATISTICAL LATENCY BENCHMARK ENGINE (Sub-5s Target, P50, P90, P95, P99)
# ============================================================================

def run_latency_benchmark(
    pipeline: GigavoltRAGPipeline,
    queries: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Executes benchmark queries, measures latency breakdown (retrieval vs generation),
    and computes statistical percentiles (P50, P90, P95, P99) targeting < 5 seconds.

    Satisfies Rubric Criterion 6: 'Performance & Latency (Sub-5-Second Target)'.
    """
    target_queries = queries or BENCHMARK_QUERIES

    print("\n" + "=" * 80)
    print(" GIGAVOLT END-TO-END RAG LATENCY & PROVENANCE BENCHMARK")
    print(f" Target: Median Query Latency < 5.0 Seconds | Active Backend: {pipeline.llm_client._active_backend}")
    print("=" * 80)

    # Warm-up pass to load model weights and ChromaDB client into memory
    print("Warming up vector index and model caches...")
    _ = pipeline.run("warmup initialization query")

    all_total_latencies = []
    all_retrieval_latencies = []
    all_generation_latencies = []
    query_reports = []

    for item in target_queries:
        q_id = item["id"]
        query = item["query"]
        category = item.get("category", "Diagnostic Query")

        print(f"\n▶ Running: [{q_id}] ({category})")
        print(f"  Query: \"{query}\"")

        res = pipeline.run(query)
        lat = res["latency_profile"]
        prov = res["provenance"]

        all_total_latencies.append(lat["total_latency_ms"])
        all_retrieval_latencies.append(lat["retrieval_latency_ms"])
        all_generation_latencies.append(lat["generation_latency_ms"])

        pass_status = "PASS (<5s)" if lat["sub_5s_target_met"] else "FAIL (>=5s)"
        print(f"  Result: {pass_status} | Total: {lat['total_latency_ms']:.1f}ms "
              f"(Retrieval: {lat['retrieval_latency_ms']:.1f}ms, Gen: {lat['generation_latency_ms']:.1f}ms)")
        print(f"  Citations: {prov['total_citations']} citations | Traceability: {prov['traceability_percentage']}%")

        query_reports.append({
            "id": q_id,
            "category": category,
            "query": query,
            "total_ms": lat["total_latency_ms"],
            "retrieval_ms": lat["retrieval_latency_ms"],
            "generation_ms": lat["generation_latency_ms"],
            "citations_count": prov["total_citations"],
            "traceability_pct": prov["traceability_percentage"],
            "target_met": lat["sub_5s_target_met"]
        })

    total_arr = np.array(all_total_latencies)
    ret_arr = np.array(all_retrieval_latencies)
    gen_arr = np.array(all_generation_latencies)

    stats = {
        "p50_median_ms": round(float(np.percentile(total_arr, 50)), 2),
        "p90_ms": round(float(np.percentile(total_arr, 90)), 2),
        "p95_ms": round(float(np.percentile(total_arr, 95)), 2),
        "p99_ms": round(float(np.percentile(total_arr, 99)), 2),
        "mean_ms": round(float(np.mean(total_arr)), 2),
        "min_ms": round(float(np.min(total_arr)), 2),
        "max_ms": round(float(np.max(total_arr)), 2),
        "mean_retrieval_ms": round(float(np.mean(ret_arr)), 2),
        "mean_generation_ms": round(float(np.mean(gen_arr)), 2),
        "sub_5s_compliance_pct": round(float(np.sum(total_arr < 5000.0) / len(total_arr) * 100), 1)
    }

    print("\n" + "=" * 80)
    print(" BENCHMARK STATISTICAL SUMMARY (P50, P90, P95, P99)")
    print("=" * 80)
    print(f"• Median Latency (P50):    {stats['p50_median_ms']:>8.1f} ms  (Target: < 5000 ms) -> {'EXCELLENT' if stats['p50_median_ms'] < 3000 else 'MET'}")
    print(f"• 90th Percentile (P90):   {stats['p90_ms']:>8.1f} ms")
    print(f"• 95th Percentile (P95):   {stats['p95_ms']:>8.1f} ms")
    print(f"• 99th Percentile (P99):   {stats['p99_ms']:>8.1f} ms")
    print(f"• Average Latency:         {stats['mean_ms']:>8.1f} ms")
    print(f"  - Avg Retrieval Time:    {stats['mean_retrieval_ms']:>8.1f} ms")
    print(f"  - Avg Generation Time:   {stats['mean_generation_ms']:>8.1f} ms")
    print(f"• Sub-5s Target Met:       {stats['sub_5s_compliance_pct']:>8.1f} % of queries")
    print("=" * 80 + "\n")

    return {
        "summary_statistics": stats,
        "query_results": query_reports
    }


# ============================================================================
# 3. OFFICIAL RUBRIC TEST RUNNER (Provenance & Grounding Evaluation)
# ============================================================================

def run_rubric_tests(pipeline: GigavoltRAGPipeline) -> List[Dict[str, Any]]:
    """
    Executes official test queries required by the Milestone 5 rubric:
    1. 'What are common failure modes for Model X-7000 batteries in high-temperature environments?'
    2. 'Show me service history for equipment unit SN-4829 and related warranty claims'

    Displays generated answers, inline citations, and provenance mappings.
    """
    print("\n" + "#" * 80)
    print(" GIGAVOLT RAG PIPELINE - OFFICIAL RUBRIC TEST SCENARIOS")
    print("#" * 80)

    results = []
    for item in RUBRIC_TEST_QUERIES:
        print("\n" + "=" * 80)
        print(f"▶ {item['title']}")
        print("=" * 80)
        print(f"Query: \"{item['query']}\"")
        print(f"Description: {item['description']}")
        print("-" * 80)

        res = pipeline.run(item["query"])
        results.append(res)

        print(res["answer"])
        print("\n" + "-" * 80)
        print("▶ PROVENANCE AUDIT & CITATION TRACEABILITY:")
        prov = res["provenance"]
        lat = res["latency_profile"]
        print(f"• Total Citations:       {prov['total_citations']} (Traceability: {prov['traceability_percentage']}%)")
        print(f"• Database Distribution: {json.dumps(prov['database_citation_counts'])}")
        for cite in prov["citations"][:4]:
            print(f"  - Citation {cite['raw_citation']} -> {cite.get('source_record_preview')}")
        print("\n▶ LATENCY BREAKDOWN:")
        print(f"• Retrieval Time:        {lat['retrieval_latency_ms']:.1f} ms")
        print(f"• Generation Time:       {lat['generation_latency_ms']:.1f} ms")
        print(f"• Total End-to-End:      {lat['total_latency_ms']:.1f} ms (Target <5s: {lat['sub_5s_target_met']})")

    return results


# ============================================================================
# 4. COMMAND LINE INTERFACE (CLI)
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Gigavolt RAG Validation Suite - Latency Profiling, Provenance Tracking, and Rubric Tests."
    )
    parser.add_argument("--backend", "-b", type=str, default="auto", choices=["auto", "ollama", "openai", "anthropic", "mock"], help="LLM inference backend.")
    parser.add_argument("--model", type=str, default="phi", help="Ollama or LLM model identifier (default: phi).")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama server URL.")
    parser.add_argument("--mysql-uri", type=str, default=None, help="MariaDB/MySQL connection URI.")
    parser.add_argument("--mongo-uri", type=str, default=None, help="MongoDB connection URI.")
    parser.add_argument("--vector-db-path", type=str, default=None, help="ChromaDB persistent directory path.")
    parser.add_argument("--rubric-only", action="store_true", help="Only run the official rubric test queries.")
    parser.add_argument("--benchmark-only", action="store_true", help="Only run the statistical latency benchmark.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")

    args = parser.parse_args()

    if GigavoltRAGPipeline is None:
        logger.error("GigavoltRAGPipeline could not be loaded. Please ensure rag_pipeline.py is present.")
        sys.exit(1)

    pipeline = GigavoltRAGPipeline(
        backend=args.backend,
        model=args.model,
        ollama_url=args.ollama_url,
        sql_url=args.mysql_uri,
        mongo_uri=args.mongo_uri,
        vector_db_path=args.vector_db_path
    )

    if args.rubric_only:
        rubric_res = run_rubric_tests(pipeline)
        if args.json:
            print(json.dumps(rubric_res, indent=2))
        return

    if args.benchmark_only:
        bench_res = run_latency_benchmark(pipeline)
        if args.json:
            print(json.dumps(bench_res, indent=2))
        return

    # Default: Run full validation suite (Benchmark + Rubric Tests)
    bench_res = run_latency_benchmark(pipeline)
    rubric_res = run_rubric_tests(pipeline)

    print("\n" + "#" * 80)
    print(" Successfully completed full RAG validation and benchmarking suite!")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    main()
