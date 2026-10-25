#!/usr/bin/env python3
"""
Gigavolt Vector Database Schema & Collection Definition (ChromaDB + HNSW)
========================================================================
Deploys an embedded ChromaDB vector database with configurable HNSW indexing
specifically tuned for sub-20ms retrieval over Gigavolt technical documentation.

Key Features:
- ChromaDB embedded deployment (no external server required)
- Strict collection metadata schema (doc_type, doc_id, pages, token_count)
- Tunable HNSW parameters:
    * M: Max outgoing connections per node in graph (default: 32)
    * ef_construction: Build-time search accuracy/depth (default: 100)
    * ef_search: Query-time search depth controlling latency vs recall (default: 40)
    * space: Distance metric ('cosine', 'l2', or 'ip')
- Sub-20ms latency benchmark validation utility
- Filtering by document metadata (e.g., doc_type='INC', source_file)
"""

import os
import sys
import time
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("GigavoltVectorDB")

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    logger.error("ChromaDB is not installed. Install with: pip install chromadb")
    raise


# ============================================================================
# COLLECTION SCHEMA DEFINITION
# ============================================================================

SCHEMA_SPEC = {
    "collection_name": "gigavolt_technical_docs",
    "embedding_model": "all-MiniLM-L6-v2",
    "vector_dimension": 384,
    "distance_metric": "cosine",
    "hnsw_defaults": {
        "M": 32,                 # Bidirectional links per node (8 - 64)
        "ef_construction": 100,  # Construction beam search size (50 - 200)
        "ef_search": 40,         # Query beam search size (10 - 150)
        "space": "cosine"        # Metric: 'cosine', 'l2', or 'ip'
    },
    "metadata_fields": {
        "doc_id": "str (e.g. GV-INC-2024-104)",
        "doc_type": "str (ECO | INC | MAN | SOP | SPEC | SUP | OTHER)",
        "doc_category": "str (e.g. Field Incident Investigation)",
        "doc_title": "str",
        "source_file": "str (PDF filename)",
        "source_path": "str (Full filepath)",
        "page_start": "int",
        "page_end": "int",
        "chunk_index": "int",
        "token_count": "int",
        "char_count": "int",
        "has_overlap": "bool"
    }
}


def sanitize_metadata_for_chroma(metadata: Dict[str, Any]) -> Dict[str, Union[str, int, float, bool]]:
    """Ensure all metadata values conform to ChromaDB supported primitive types"""
    clean_meta = {}
    for k, v in metadata.items():
        if isinstance(v, (str, int, float, bool)):
            clean_meta[k] = v
        elif v is None:
            clean_meta[k] = ""
        else:
            clean_meta[k] = str(v)
    return clean_meta


# ============================================================================
# GIGAVOLT VECTOR DATABASE WRAPPER
# ============================================================================

class GigavoltVectorDB:
    """
    ChromaDB wrapper providing collection initialization with explicit HNSW parameters,
    batch document ingestion, sub-20ms queries, and metadata-filtered retrieval.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        in_memory: bool = False
    ):
        """
        Args:
            db_path: Persistent directory for ChromaDB storage.
                     Defaults to /opt/undata/gigavolt_vectordb or ./gigavolt_vectordb.
            in_memory: If True, uses ephemeral in-memory client (ideal for benchmarking).
        """
        self.in_memory = in_memory
        if in_memory:
            logger.info("Initializing in-memory EphemeralClient...")
            self.client = chromadb.EphemeralClient()
            self.db_path = ":memory:"
        else:
            resolved_path = self._resolve_db_path(db_path)
            self.db_path = str(resolved_path)
            logger.info(f"Initializing PersistentClient at: {self.db_path}")
            os.makedirs(self.db_path, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.db_path)

        self._embedder = None
        self.collection = None

    def _resolve_db_path(self, user_path: Optional[str]) -> Path:
        """Resolve persistence directory"""
        if user_path:
            return Path(user_path)

        # Check AWS standard locations
        aws_opt = Path("/opt/undata/gigavolt_vectordb")
        if Path("/opt/undata").exists():
            return aws_opt

        aws_root = Path("/undata/gigavolt_vectordb")
        if Path("/undata").exists():
            return aws_root

        # Local fallback
        return Path("./gigavolt_vectordb")

    @property
    def embedder(self):
        """Lazy load SentenceTransformers embedding model"""
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
        """
        Create or retrieve a collection configured with explicit HNSW parameters.

        HNSW Parameter Reference:
        - M: Maximum number of bidirectional links per node in the graph layers.
             Higher M increases graph connectivity, recall, and memory usage.
        - ef_construction: Size of the dynamic candidate list during graph construction.
             Higher ef_construction improves graph quality at the cost of indexing time.
        - ef_search: Size of the dynamic candidate list during query time.
             Higher ef_search improves recall at the cost of query latency.
        - space: Distance calculation method ('cosine', 'l2', or 'ip').
        """
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
                logger.info(f"Deleted existing collection '{name}'")
            except Exception:
                pass

        try:
            self.collection = self.client.get_collection(name=name)
            logger.info(f"Retrieved existing collection '{name}' (count={self.collection.count()})")
        except Exception:
            logger.info(
                f"Creating collection '{name}' with HNSW params: "
                f"M={M}, ef_construction={ef_construction}, ef_search={ef_search}, space={space}"
            )
            self.collection = self.client.create_collection(
                name=name,
                metadata=hnsw_metadata
            )

        return self.collection

    def add_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: Optional[np.ndarray] = None,
        batch_size: int = 64
    ):
        """
        Ingest document chunks and their dense embeddings into the collection.

        Args:
            chunks: List of chunk dictionaries (from chunking_engine.py)
            embeddings: Optional pre-computed float32 NumPy array [N, 384].
                        If None, will be computed using EmbeddingGenerator.
            batch_size: Ingestion batch size for ChromaDB add operations.
        """
        if not chunks:
            logger.warning("No chunks provided to add.")
            return

        if self.collection is None:
            self.create_or_get_collection()

        # Compute embeddings if not pre-computed
        if embeddings is None:
            logger.info(f"Computing embeddings for {len(chunks)} chunks...")
            embeddings, _ = self.embedder.embed_chunks(chunks)

        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch between chunks ({len(chunks)}) and embeddings ({len(embeddings)})")

        logger.info(f"Ingesting {len(chunks)} vectors into collection '{self.collection.name}'...")
        start_t = time.perf_counter()

        n_total = len(chunks)
        for i in range(0, n_total, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_embeddings = embeddings[i:i + batch_size].tolist()

            batch_ids = [c["id"] for c in batch_chunks]
            batch_docs = [c["text"] for c in batch_chunks]
            batch_meta = [sanitize_metadata_for_chroma(c) for c in batch_chunks]

            self.collection.add(
                ids=batch_ids,
                documents=batch_docs,
                embeddings=batch_embeddings,
                metadatas=batch_meta
            )

        elapsed = time.perf_counter() - start_t
        logger.info(
            f"Successfully indexed {n_total} chunks in {elapsed:.2f}s "
            f"({n_total / max(elapsed, 1e-4):.1f} chunks/sec). Total items in DB: {self.collection.count()}"
        )

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        doc_type: Optional[str] = None,
        where_filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search collection using natural language query string.

        Args:
            query_text: Search query string
            n_results: Number of nearest neighbors to return
            doc_type: Optional document type filter (e.g. 'INC', 'ECO', 'SOP')
            where_filter: Explicit ChromaDB metadata filter dictionary

        Returns:
            ChromaDB query results dictionary
        """
        if self.collection is None:
            raise RuntimeError("Collection not initialized. Call create_or_get_collection() first.")

        query_vec = self.embedder.embed_query(query_text).tolist()

        # Combine filters
        final_where = None
        if where_filter:
            final_where = where_filter
        elif doc_type:
            final_where = {"doc_type": doc_type}

        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=n_results,
            where=final_where
        )
        return results

    def benchmark_single_query(
        self,
        query_text: str,
        n_results: int = 5,
        precomputed_embedding: Optional[List[float]] = None
    ) -> Tuple[Dict[str, Any], float]:
        """
        Execute a search query and measure HNSW index query latency in milliseconds.

        Args:
            query_text: Query text (ignored if precomputed_embedding is provided)
            n_results: Number of results
            precomputed_embedding: Optional pre-computed query embedding to isolate
                                   pure index lookup latency from embedding inference latency.

        Returns:
            Tuple of (results_dict, latency_in_ms)
        """
        if precomputed_embedding is None:
            query_vec = self.embedder.embed_query(query_text).tolist()
        else:
            query_vec = precomputed_embedding

        # Measure pure vector retrieval time
        t_start = time.perf_counter()
        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=n_results
        )
        latency_ms = (time.perf_counter() - t_start) * 1000.0
        return results, latency_ms

    def run_latency_benchmark(
        self,
        queries: List[str],
        n_results: int = 5,
        target_latency_ms: float = 20.0
    ) -> Dict[str, Any]:
        """
        Run latency benchmark across test queries and check sub-20ms requirement.

        Args:
            queries: List of technical search queries
            n_results: Top-k results
            target_latency_ms: Maximum allowable SLA latency (default 20.0 ms)

        Returns:
            Dictionary with latency distribution statistics and SLA pass/fail
        """
        if not queries:
            return {}

        logger.info(f"Pre-computing query vectors for {len(queries)} benchmark queries...")
        query_vectors = [self.embedder.embed_query(q).tolist() for q in queries]

        # Warm-up run (3 queries)
        for vec in query_vectors[:3]:
            self.collection.query(query_embeddings=[vec], n_results=n_results)

        latencies = []
        for vec in query_vectors:
            _, lat_ms = self.benchmark_single_query(
                query_text="",
                n_results=n_results,
                precomputed_embedding=vec
            )
            latencies.append(lat_ms)

        latencies.sort()
        n = len(latencies)
        p50 = latencies[n // 2]
        p90 = latencies[int(n * 0.90)]
        p95 = latencies[int(n * 0.95)]
        p99 = latencies[int(n * 0.99)]
        mean_lat = sum(latencies) / n
        max_lat = latencies[-1]
        min_lat = latencies[0]

        sla_passed = p95 < target_latency_ms

        summary = {
            "total_queries": n,
            "latency_min_ms": round(min_lat, 3),
            "latency_mean_ms": round(mean_lat, 3),
            "latency_p50_ms": round(p50, 3),
            "latency_p90_ms": round(p90, 3),
            "latency_p95_ms": round(p95, 3),
            "latency_p99_ms": round(p99, 3),
            "latency_max_ms": round(max_lat, 3),
            "sla_target_ms": target_latency_ms,
            "sla_passed": sla_passed
        }

        print("\n" + "=" * 65)
        print("HNSW QUERY LATENCY BENCHMARK REPORT")
        print("=" * 65)
        print(f"Total Queries Evaluated : {summary['total_queries']}")
        print(f"Target Latency SLA      : < {target_latency_ms:.1f} ms")
        print(f"P50 (Median) Latency    : {summary['latency_p50_ms']:.3f} ms")
        print(f"P90 Latency             : {summary['latency_p90_ms']:.3f} ms")
        print(f"P95 Latency             : {summary['latency_p95_ms']:.3f} ms")
        print(f"P99 Latency             : {summary['latency_p99_ms']:.3f} ms")
        print(f"Mean Latency            : {summary['latency_mean_ms']:.3f} ms")
        print(f"Max Latency             : {summary['latency_max_ms']:.3f} ms")
        print("-" * 65)
        status_text = "PASSED (Sub-20ms SLA Achieved)" if sla_passed else "FAILED (Exceeds 20ms SLA)"
        print(f"SLA Compliance Status   : {status_text}")
        print("=" * 65 + "\n")

        return summary

    def get_stats(self) -> Dict[str, Any]:
        """Retrieve collection and document statistics"""
        if self.collection is None:
            return {"status": "No active collection"}

        total_vectors = self.collection.count()
        sample_meta = self.collection.get(limit=total_vectors)

        doc_types = {}
        source_files = {}
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


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

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
    parser = argparse.ArgumentParser(
        description="Gigavolt ChromaDB HNSW Vector Database Manager",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--db-path", type=str, default="/opt/undata/gigavolt_vectordb", help="Database directory")
    parser.add_argument("--collection-name", type=str, default="gigavolt_technical_docs", help="Collection name")
    parser.add_argument("--M", type=int, default=32, help="HNSW M parameter (connections per layer)")
    parser.add_argument("--ef-construction", type=int, default=100, help="HNSW ef_construction parameter")
    parser.add_argument("--ef-search", type=int, default=40, help="HNSW ef_search parameter")
    parser.add_argument("--space", type=str, default="cosine", choices=["cosine", "l2", "ip"], help="Distance metric")
    parser.add_argument("--populate-from-chunks", type=str, default=None, help="Path to chunks JSON")
    parser.add_argument("--populate-from-embeddings", type=str, default=None, help="Prefix for embeddings .npy & .json")
    parser.add_argument("--query", type=str, default=None, help="Run a test query")
    parser.add_argument("--filter-type", type=str, default=None, help="Filter query by doc_type (e.g. INC, ECO)")
    parser.add_argument("--benchmark", action="store_true", help="Run latency benchmark with SLA validation")

    args = parser.parse_args()

    vdb = GigavoltVectorDB(db_path=args.db_path)
    vdb.create_or_get_collection(
        name=args.collection_name,
        M=args.M,
        ef_construction=args.ef_construction,
        ef_search=args.ef_search,
        space=args.space
    )

    # Ingestion options
    if args.populate_from_embeddings:
        from generate_embeddings import load_embeddings_and_metadata
        embeddings, chunks = load_embeddings_and_metadata(args.populate_from_embeddings)
        vdb.add_chunks(chunks=chunks, embeddings=embeddings)
    elif args.populate_from_chunks:
        with open(args.populate_from_chunks, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        vdb.add_chunks(chunks=chunks)

    # Search option
    if args.query:
        results, lat_ms = vdb.benchmark_single_query(args.query, n_results=5)
        print(f"\nQuery: '{args.query}' (Latency: {lat_ms:.2f} ms)")
        ids = results.get("ids", [[]])[0]
        for idx in range(len(ids)):
            doc = results["documents"][0][idx]
            meta = results["metadatas"][0][idx]
            dist = results["distances"][0][idx]
            sim = 1.0 - dist if args.space == "cosine" else dist
            print(f"[{idx+1}] Score: {sim:.3f} | {meta.get('doc_id')} ({meta.get('doc_type')}) - {meta.get('source_file')}")
            print(f"    {doc[:200]}...\n")

    # Benchmark option
    if args.benchmark:
        vdb.run_latency_benchmark(SAMPLE_BENCHMARK_QUERIES)

    # Print stats if no action specified
    if not (args.populate_from_chunks or args.populate_from_embeddings or args.query or args.benchmark):
        stats = vdb.get_stats()
        print("\n" + "=" * 60)
        print("GIGAVOLT VECTOR DATABASE STATUS")
        print("=" * 60)
        print(f"DB Path            : {vdb.db_path}")
        print(f"Active Collection  : {stats.get('collection_name')}")
        print(f"Total Chunks       : {stats.get('total_chunks')}")
        print(f"Unique Documents   : {stats.get('unique_documents')}")
        print(f"HNSW Config        : {stats.get('metadata_config')}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

