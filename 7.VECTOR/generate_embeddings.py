#!/usr/bin/env python3
"""
Gigavolt Dense Embedding Generation Script
===========================================
Generates 384-dimensional dense vector embeddings for technical document chunks
using SentenceTransformers ('all-MiniLM-L6-v2') optimized for sub-20ms retrieval.

Key Features:
- Hugging Face / SentenceTransformers 'all-MiniLM-L6-v2' (384-dim dense vectors)
- Configurable batch inference with progress tracking
- Automatic device detection (CUDA GPU / multi-threaded CPU)
- L2-normalized embeddings for fast cosine similarity and inner product search
- Supports input from pre-chunked JSON or direct execution on PDF directories
- Programmatic API and CLI interface
"""

import os
import sys
import json
import time
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
logger = logging.getLogger("GigavoltEmbedder")


# ============================================================================
# EMBEDDING GENERATOR CLASS
# ============================================================================

class EmbeddingGenerator:
    """
    Wrapper for SentenceTransformers embedding generation.
    Generates normalized dense vector representations for document chunks.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    VECTOR_DIM = 384

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: Optional[str] = None,
        normalize_embeddings: bool = True
    ):
        """
        Args:
            model_name: SentenceTransformers model identifier (default: all-MiniLM-L6-v2)
            device: 'cuda', 'cpu', 'mps', or None (auto-detect)
            normalize_embeddings: Whether to L2-normalize vectors for cosine similarity
        """
        self.model_name = model_name
        self.normalize_embeddings = normalize_embeddings
        self.device = self._resolve_device(device)
        self.model = self._load_model()

    def _resolve_device(self, user_device: Optional[str]) -> str:
        """Auto-detect optimal inference device"""
        if user_device:
            return user_device.lower()

        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA GPU detected. Using GPU for embedding generation.")
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                logger.info("Apple Silicon MPS detected. Using MPS for embedding generation.")
                return "mps"
            else:
                # Optimize CPU multi-threading
                num_cores = os.cpu_count() or 4
                torch.set_num_threads(min(num_cores, 8))
                logger.info(f"Using CPU with {torch.get_num_threads()} threads for embedding generation.")
                return "cpu"
        except ImportError:
            return "cpu"

    def _load_model(self):
        """Load the SentenceTransformer model"""
        logger.info(f"Loading SentenceTransformer model '{self.model_name}' on {self.device}...")
        start_t = time.perf_counter()
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self.model_name, device=self.device)
            load_elapsed = time.perf_counter() - start_t
            logger.info(f"Model loaded successfully in {load_elapsed:.2f}s (dim={self.VECTOR_DIM})")
            return model
        except ImportError as e:
            logger.error("SentenceTransformers is not installed. Install with: pip install sentence-transformers")
            raise e

    def generate_embeddings(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = True
    ) -> np.ndarray:
        """
        Generate dense vector embeddings for a list of text strings.

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts per forward pass
            show_progress: Display progress bar or logging

        Returns:
            np.ndarray of shape (len(texts), 384) with float32 embeddings
        """
        if not texts:
            return np.empty((0, self.VECTOR_DIM), dtype=np.float32)

        start_time = time.perf_counter()
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True
        )

        elapsed = time.perf_counter() - start_time
        throughput = len(texts) / max(elapsed, 1e-4)
        logger.info(
            f"Encoded {len(texts)} texts in {elapsed:.2f}s "
            f"({throughput:.1f} texts/sec, shape: {embeddings.shape})"
        )
        return embeddings.astype(np.float32)

    def embed_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 32,
        show_progress: bool = True
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Generate embeddings for a list of document chunk dictionaries.
        Enriches each chunk with embedding metadata.

        Args:
            chunks: List of chunk dictionaries (output of chunking_engine.py)
            batch_size: Batch size for forward inference
            show_progress: Display progress

        Returns:
            Tuple of (embeddings array of shape [N, 384], updated chunks list)
        """
        if not chunks:
            return np.empty((0, self.VECTOR_DIM), dtype=np.float32), []

        texts = [c["text"] for c in chunks]
        embeddings = self.generate_embeddings(texts, batch_size=batch_size, show_progress=show_progress)

        enriched_chunks = []
        for idx, chunk in enumerate(chunks):
            c_copy = dict(chunk)
            c_copy["embedding_model"] = self.model_name
            c_copy["embedding_dim"] = self.VECTOR_DIM
            c_copy["is_normalized"] = self.normalize_embeddings
            enriched_chunks.append(c_copy)

        return embeddings, enriched_chunks

    def embed_query(self, query: str) -> np.ndarray:
        """
        Generate a single query vector.

        Args:
            query: User search text

        Returns:
            1D np.ndarray of shape (384,)
        """
        vec = self.model.encode(
            query,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True
        )
        return vec.astype(np.float32)


# ============================================================================
# PERSISTENCE HELPERS
# ============================================================================

def save_embeddings_and_metadata(
    embeddings: np.ndarray,
    chunks: List[Dict[str, Any]],
    output_prefix: Union[str, Path] = "gigavolt_embeddings"
) -> Tuple[Path, Path]:
    """
    Save embeddings as NumPy .npy file and chunks as JSON.

    Args:
        embeddings: Float32 NumPy array of vectors
        chunks: List of chunk metadata dictionaries
        output_prefix: Base path without extension

    Returns:
        Tuple of (npy_path, json_path)
    """
    prefix = Path(output_prefix)
    npy_path = prefix.with_suffix(".npy")
    json_path = prefix.with_suffix(".json")

    np.save(npy_path, embeddings)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    logger.info(f"Embeddings saved to: {npy_path.resolve()} ({embeddings.nbytes / (1024 * 1024):.2f} MB)")
    logger.info(f"Chunk metadata saved to: {json_path.resolve()}")
    return npy_path, json_path


def load_embeddings_and_metadata(
    input_prefix: Union[str, Path] = "gigavolt_embeddings"
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """Load pre-computed embeddings (.npy) and chunk metadata (.json)"""
    prefix = Path(input_prefix)
    npy_path = prefix.with_suffix(".npy")
    json_path = prefix.with_suffix(".json")

    if not npy_path.exists() or not json_path.exists():
        raise FileNotFoundError(f"Missing {npy_path} or {json_path}")

    embeddings = np.load(npy_path)
    with open(json_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    logger.info(f"Loaded embeddings matrix: {embeddings.shape} and {len(chunks)} chunk records")
    return embeddings, chunks


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Gigavolt Dense Embedding Generator (all-MiniLM-L6-v2)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--input-chunks",
        type=str,
        default=None,
        help="Path to pre-generated chunks JSON file (from chunking_engine.py)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="/opt/undata",
        help="Path to PDF documents directory if chunk file is not provided"
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="gigavolt_embeddings",
        help="Base filename prefix for output .npy and .json"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Inference batch size"
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Inference device: 'cpu', 'cuda', 'mps' (default: auto-detect)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=384,
        help="Chunk size in tokens (if running direct chunking)"
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=64,
        help="Chunk overlap in tokens (if running direct chunking)"
    )

    args = parser.parse_args()

    # Step 1: Load or produce chunks
    chunks = []
    if args.input_chunks and Path(args.input_chunks).exists():
        logger.info(f"Loading chunks from existing file: {args.input_chunks}")
        with open(args.input_chunks, "r", encoding="utf-8") as f:
            chunks = json.load(f)
    else:
        logger.info(f"No chunk file specified. Invoking chunking engine on {args.data_dir}...")
        try:
            from chunking_engine import process_directory, resolve_data_directory
            target_dir = resolve_data_directory(args.data_dir)
            chunks = process_directory(target_dir, chunk_size=args.chunk_size, overlap=args.overlap)
        except ImportError:
            logger.error("Could not import chunking_engine.py. Please provide --input-chunks.")
            sys.exit(1)

    if not chunks:
        logger.error("No chunks available to embed. Exiting.")
        sys.exit(1)

    # Step 2: Initialize generator and produce embeddings
    generator = EmbeddingGenerator(device=args.device)
    embeddings, enriched_chunks = generator.embed_chunks(chunks, batch_size=args.batch_size)

    # Step 3: Persist results
    save_embeddings_and_metadata(embeddings, enriched_chunks, output_prefix=args.output_prefix)
    print("\n" + "=" * 60)
    print("EMBEDDING GENERATION COMPLETE")
    print("=" * 60)
    print(f"Total Chunks Embedded  : {len(chunks)}")
    print(f"Embedding Dimension    : {embeddings.shape[1]}")
    print(f"Embedding Matrix Shape : {embeddings.shape}")
    print(f"L2-Normalized          : True")
    print(f"Saved Files            : {args.output_prefix}.npy, {args.output_prefix}.json")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

