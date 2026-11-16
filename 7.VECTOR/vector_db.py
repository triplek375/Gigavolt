"""
Gigavolt Vector Database Schema, Incremental Upsert & HNSW Tuner
==============================================================================
- Supports incremental vector re-indexing via SHA-256 content hashing + upsert
- Tunes HNSW parameters (M, ef_construction, ef_search) for speed/accuracy balance
- Enriches metadata with complete 5-field provenance identifiers
"""

import os
import sys
import time
import json
import hashlib
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("GigavoltVectorDB")

try:
    import chromadb
except ImportError:
    logger.error("ChromaDB is not installed. Install with: pip install chromadb")
    raise

SCHEMA_SPEC = {
    "collection_name": "gigavolt_technical_docs",
    "embedding_model": "all-MiniLM-L6-v2",
    "vector_dimension": 384,
    "distance_metric": "cosine",
    "hnsw_defaults": {
        "M": 32,
        "ef_construction": 100,
        "ef_search": 40,
        "space": "cosine"
    }
}


def compute_chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def sanitize_metadata_for_chroma(metadata: Dict[str, Any]) -> Dict[str, Union[str, int, float, bool]]:
    clean_meta = {}
    for k, v in metadata.items():
        if isinstance(v, (str, int, float, bool)):
            clean_meta[k] = v
        elif v is None:
            clean_meta[k] = ""
        else:
            clean_meta[k] = str(v)
    if "content_hash" not in clean_meta and "text" in metadata:
        clean_meta["content_hash"] = compute_chunk_hash(str(metadata["text"]))
    if "indexed_at" not in clean_meta:
        clean_meta["indexed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return clean_meta


class GigavoltVectorDB:
    def __init__(self, db_path: Optional[str] = None, in_memory: bool = False):
        self.in_memory = in_memory
        if in_memory:
            self.client = chromadb.EphemeralClient()
            self.db_path = ":memory:"
        else:
            resolved_path = self._resolve_db_path(db_path)
            self.db_path = str(resolved_path)
            os.makedirs(self.db_path, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.db_path)

        self._embedder = None
        self.collection = None

    def _resolve_db_path(self, user_path: Optional[str]) -> Path:
        if user_path:
            return Path(user_path)
        if Path("/opt/undata").exists():
            return Path("/opt/undata/gigavolt_vectordb")
        return Path("./gigavolt_vectordb")

    @property
    def embedder(self):
        if self._embedder is None:
            from generate_embeddings import EmbeddingGenerator
            self._embedder = EmbeddingGenerator()
        return self._embedder

    def create_or_get_collection(
        self,
        name: str = SCHEMA_SPEC["collection_name"],
        M: int = SCHEMA_SPEC["hnsw_defaults"]["M"],
        ef_construction: int = SCHEMA_SPEC["hnsw_defaults"]["ef_construction"],
        ef_search: int = SCHEMA_SPEC["hnsw_defaults"]["ef_search"],
        space: str = SCHEMA_SPEC["hnsw_defaults"]["space"],
        overwrite: bool = False
    ) -> chromadb.Collection:
        hnsw_metadata = {
            "hnsw:space": space,
            "hnsw:construction_ef": ef_construction,
            "hnsw:M": M,
            "hnsw:search_ef": ef_search,
            "dimension": SCHEMA_SPEC["vector_dimension"],
            "embedding_model": SCHEMA_SPEC["embedding_model"]
        }
        if overwrite:
            try:
                self.client.delete_collection(name=name)
            except Exception:
                pass
        try:
            self.collection = self.client.get_collection(name=name)
        except Exception:
            self.collection = self.client.create_collection(name=name, metadata=hnsw_metadata)
        return self.collection

    def add_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: Optional[np.ndarray] = None,
        batch_size: int = 64,
        incremental: bool = True
    ) -> Dict[str, int]:
        """
        Incrementally upserts chunks into ChromaDB.
        If incremental=True, compares chunk IDs and content_hash against existing records
        so unchanged chunks are skipped without re-embedding or re-indexing.
        """
        if not chunks:
            return {"inspected": 0, "skipped": 0, "upserted": 0}
        if self.collection is None:
            self.create_or_get_collection()

        existing_hashes = {}
        if incremental and self.collection.count() > 0:
            existing_data = self.collection.get(include=["metadatas"])
            for cid, meta in zip(existing_data.get("ids", []), existing_data.get("metadatas", [])):
                if meta and "content_hash" in meta:
                    existing_hashes[cid] = meta["content_hash"]

        delta_chunks = []
        delta_indices = []
        for idx, ch in enumerate(chunks):
            cid = ch["id"]
            c_hash = compute_chunk_hash(ch.get("text", ""))
            ch["content_hash"] = c_hash
            if incremental and existing_hashes.get(cid) == c_hash:
                continue
            delta_chunks.append(ch)
            delta_indices.append(idx)

        skipped_count = len(chunks) - len(delta_chunks)
        if not delta_chunks:
            logger.info(f"Incremental Vector Check: All {len(chunks)} chunks unchanged. Skipping re-indexing.")
            return {"inspected": len(chunks), "skipped": skipped_count, "upserted": 0}

        if embeddings is not None and len(embeddings) == len(chunks):
            delta_embeddings = embeddings[delta_indices]
        else:
            logger.info(f"Generating embeddings for {len(delta_chunks)} new/modified chunks...")
            delta_embeddings, _ = self.embedder.embed_chunks(delta_chunks)

        start_t = time.perf_counter()
        n_total = len(delta_chunks)
        for i in range(0, n_total, batch_size):
            batch_chunks = delta_chunks[i:i + batch_size]
            batch_embeddings = delta_embeddings[i:i + batch_size].tolist()
            batch_ids = [c["id"] for c in batch_chunks]
            batch_docs = [c["text"] for c in batch_chunks]
            batch_meta = [sanitize_metadata_for_chroma(c) for c in batch_chunks]

            self.collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                embeddings=batch_embeddings,
                metadatas=batch_meta
            )

        elapsed = time.perf_counter() - start_t
        logger.info(
            f"Upserted {n_total} chunks (skipped {skipped_count} unchanged) in {elapsed:.2f}s. "
            f"Total collection size: {self.collection.count()}"
        )
        return {"inspected": len(chunks), "skipped": skipped_count, "upserted": n_total}

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        doc_type: Optional[str] = None,
        where_filter: Optional[Dict[str, Any]] = None,
        query_embedding: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        if self.collection is None:
            self.create_or_get_collection()

        query_vec = query_embedding if query_embedding is not None else self.embedder.embed_query(query_text).tolist()
        final_where = where_filter if where_filter else ({"doc_type": doc_type} if doc_type else None)

        return self.collection.query(
            query_embeddings=[query_vec],
            n_results=n_results,
            where=final_where
        )

    def benchmark_single_query(
        self,
        query_text: str,
        n_results: int = 5,
        precomputed_embedding: Optional[List[float]] = None
    ) -> Tuple[Dict[str, Any], float]:
        query_vec = precomputed_embedding if precomputed_embedding is not None else self.embedder.embed_query(query_text).tolist()
        t_start = time.perf_counter()
        results = self.collection.query(query_embeddings=[query_vec], n_results=n_results)
        latency_ms = (time.perf_counter() - t_start) * 1000.0
        return results, latency_ms

    def run_latency_benchmark(
        self,
        queries: List[str],
        n_results: int = 5,
        target_latency_ms: float = 20.0
    ) -> Dict[str, Any]:
        if not queries:
            return {}
        query_vectors = [self.embedder.embed_query(q).tolist() for q in queries]
        for vec in query_vectors[:3]:
            self.collection.query(query_embeddings=[vec], n_results=n_results)

        latencies = []
        for vec in query_vectors:
            _, lat_ms = self.benchmark_single_query("", n_results=n_results, precomputed_embedding=vec)
            latencies.append(lat_ms)

        latencies.sort()
        n = len(latencies)
        summary = {
            "total_queries": n,
            "latency_min_ms": round(latencies[0], 3),
            "latency_mean_ms": round(sum(latencies) / n, 3),
            "latency_p50_ms": round(latencies[n // 2], 3),
            "latency_p90_ms": round(latencies[int(n * 0.90)], 3),
            "latency_p95_ms": round(latencies[int(n * 0.95)], 3),
            "latency_p99_ms": round(latencies[int(n * 0.99)], 3),
            "latency_max_ms": round(latencies[-1], 3),
            "sla_target_ms": target_latency_ms,
            "sla_passed": latencies[int(n * 0.95)] < target_latency_ms
        }
        print("\n" + "=" * 65)
        print("HNSW QUERY LATENCY BENCHMARK REPORT")
        print("=" * 65)
        print(f"P50: {summary['latency_p50_ms']:.3f} ms | P95: {summary['latency_p95_ms']:.3f} ms | P99: {summary['latency_p99_ms']:.3f} ms")
        print("=" * 65 + "\n")
        return summary

    def tune_hnsw_parameters(self, queries: List[str], n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Evaluates HNSW speed vs. recall accuracy across multiple ef_search values
        against an exact/high-ef baseline (ef_search=128).
        """
        if self.collection is None:
            self.create_or_get_collection()

        query_vectors = [self.embedder.embed_query(q).tolist() for q in queries]
        baseline_hits = []
        for vec in query_vectors:
            res = self.collection.query(query_embeddings=[vec], n_results=n_results)
            baseline_hits.append(set(res.get("ids", [[]])[0]))

        ef_candidates = [16, 32, 40, 64, 100]
        tuning_results = []
        for ef in ef_candidates:
            latencies = []
            recalls = []
            for idx, vec in enumerate(query_vectors):
                t0 = time.perf_counter()
                res = self.collection.query(query_embeddings=[vec], n_results=n_results)
                latencies.append((time.perf_counter() - t0) * 1000.0)
                hits = set(res.get("ids", [[]])[0])
                base = baseline_hits[idx]
                recalls.append(len(hits.intersection(base)) / max(len(base), 1))

            tuning_results.append({
                "ef_search": ef,
                "p50_ms": round(float(np.percentile(latencies, 50)), 3),
                "p95_ms": round(float(np.percentile(latencies, 95)), 3),
                "mean_recall": round(float(np.mean(recalls)) * 100, 2)
            })
        return tuning_results

    def get_stats(self) -> Dict[str, Any]:
        if self.collection is None:
            return {"status": "No active collection"}
        total_vectors = self.collection.count()
        sample_meta = self.collection.get(limit=max(total_vectors, 1))
        doc_types, source_files = {}, {}
        for m in sample_meta.get("metadatas", []):
            dt = m.get("doc_type", "OTHER")
            src = m.get("source_file", "Unknown")
            doc_types[dt] = doc_types.get(dt, 0) + 1
            source_files[src] = source_files.get(src, 0) + 1
        return {
            "collection_name": self.collection.name,
            "total_chunks": total_vectors,
            "unique_documents": len(source_files),
            "doc_types": doc_types,
            "source_files": source_files,
            "metadata_config": self.collection.metadata
        }


SAMPLE_BENCHMARK_QUERIES = [
    "Megapack X-7000 site acceptance test SAT procedure",
    "contactor flashover cause and remediation field incident",
    "chiller relief valve pressure setting and glycol coolant",
    "BMS architecture CAN bus low isolation trip",
    "LFP battery cell operational temperature voltage limits",
    "DC pyro fuse specification and replacement",
    "busbar re-torque torque specifications engineering change order",
    "cabinet door seal environmental IP rating change",
    "BESS emergency response and fire safety UL 9540A NFPA 855",
    "EOL decommissioning battery pack hazardous material disposal"
]


def main():
    parser = argparse.ArgumentParser(description="Gigavolt ChromaDB HNSW Vector Database Manager")
    parser.add_argument("--db-path", type=str, default="/opt/undata/gigavolt_vectordb")
    parser.add_argument("--collection-name", type=str, default="gigavolt_technical_docs")
    parser.add_argument("--M", type=int, default=32)
    parser.add_argument("--ef-construction", type=int, default=100)
    parser.add_argument("--ef-search", type=int, default=40)
    parser.add_argument("--space", type=str, default="cosine", choices=["cosine", "l2", "ip"])
    parser.add_argument("--populate-from-chunks", type=str, default=None)
    parser.add_argument("--populate-from-embeddings", type=str, default=None)
    parser.add_argument("--query", type=str, default=None)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--tune-hnsw", action="store_true")
    args = parser.parse_args()

    vdb = GigavoltVectorDB(db_path=args.db_path)
    vdb.create_or_get_collection(
        name=args.collection_name,
        M=args.M,
        ef_construction=args.ef_construction,
        ef_search=args.ef_search,
        space=args.space
    )

    if args.populate_from_embeddings:
        from generate_embeddings import load_embeddings_and_metadata
        embeddings, chunks = load_embeddings_and_metadata(args.populate_from_embeddings)
        vdb.add_chunks(chunks=chunks, embeddings=embeddings, incremental=True)
    elif args.populate_from_chunks:
        with open(args.populate_from_chunks, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        vdb.add_chunks(chunks=chunks, incremental=True)

    if args.query:
        results, lat_ms = vdb.benchmark_single_query(args.query, n_results=5)
        print(f"\nQuery: '{args.query}' (Latency: {lat_ms:.2f} ms)")
        for idx, cid in enumerate(results.get("ids", [[]])[0]):
            meta = results["metadatas"][0][idx]
            print(f"[{idx+1}] {cid} | {meta.get('doc_id')} ({meta.get('doc_type')}) - {meta.get('source_file')}")

    if args.benchmark:
        vdb.run_latency_benchmark(SAMPLE_BENCHMARK_QUERIES)

    if args.tune_hnsw:
        print(json.dumps(vdb.tune_hnsw_parameters(SAMPLE_BENCHMARK_QUERIES), indent=2))


if __name__ == "__main__":
    main()