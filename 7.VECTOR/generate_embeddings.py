"""
Gigavolt Dense Embedding Generation Script
===========================================
Generates 384-dimensional dense vector embeddings for technical document chunks
using SentenceTransformers ('all-MiniLM-L6-v2') optimized for sub-20ms retrieval.
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

logging.getConfig = logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# Silence noisy httpx / huggingface_hub logs during CLI runs
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logger = logging.getLogger("GigavoltEmbedder")


class EmbeddingGenerator:
    MODEL_NAME = "all-MiniLM-L6-v2"
    VECTOR_DIM = 384

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: Optional[str] = None,
        normalize_embeddings: bool = True
    ):
        self.model_name = model_name
        self.normalize_embeddings = normalize_embeddings
        self.device = self._resolve_device(device)
        self.model = self._load_model()

    def _resolve_device(self, user_device: Optional[str]) -> str:
        if user_device:
            return user_device.lower()
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            else:
                num_cores = os.cpu_count() or 4
                torch.set_num_threads(min(num_cores, 8))
                return "cpu"
        except ImportError:
            return "cpu"

    def _load_model(self):
        start_t = time.perf_counter()
        try:
            from sentence_transformers import SentenceTransformer
            try:
                # Try fast offline load from local HF cache first (0 network calls)
                model = SentenceTransformer(self.model_name, device=self.device, local_files_only=True)
            except Exception:
                model = SentenceTransformer(self.model_name, device=self.device)
            load_elapsed = time.perf_counter() - start_t
            logger.info(f"Model '{self.model_name}' ready in {load_elapsed:.2f}s (dim={self.VECTOR_DIM})")
            return model
        except ImportError as e:
            logger.error("SentenceTransformers is not installed.")
            raise e

    def generate_embeddings(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False
    ) -> np.ndarray:
        if not texts:
            return np.empty((0, self.VECTOR_DIM), dtype=np.float32)
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True
        )
        return embeddings.astype(np.float32)

    def embed_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 32,
        show_progress: bool = False
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        if not chunks:
            return np.empty((0, self.VECTOR_DIM), dtype=np.float32), []
        texts = [c["text"] for c in chunks]
        embeddings = self.generate_embeddings(texts, batch_size=batch_size, show_progress=show_progress)
        enriched_chunks = []
        for chunk in chunks:
            c_copy = dict(chunk)
            c_copy["embedding_model"] = self.model_name
            c_copy["embedding_dim"] = self.VECTOR_DIM
            c_copy["is_normalized"] = self.normalize_embeddings
            enriched_chunks.append(c_copy)
        return embeddings, enriched_chunks

    def embed_query(self, query: str) -> np.ndarray:
        vec = self.model.encode(
            query,
            show_progress_bar=False,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True
        )
        return vec.astype(np.float32)


def save_embeddings_and_metadata(
    embeddings: np.ndarray,
    chunks: List[Dict[str, Any]],
    output_prefix: Union[str, Path] = "gigavolt_embeddings"
) -> Tuple[Path, Path]:
    prefix = Path(output_prefix)
    npy_path = prefix.with_suffix(".npy")
    json_path = prefix.with_suffix(".json")
    np.save(npy_path, embeddings)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    return npy_path, json_path


def load_embeddings_and_metadata(
    input_prefix: Union[str, Path] = "gigavolt_embeddings"
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    prefix = Path(input_prefix)
    npy_path = prefix.with_suffix(".npy")
    json_path = prefix.with_suffix(".json")
    if not npy_path.exists() or not json_path.exists():
        raise FileNotFoundError(f"Missing {npy_path} or {json_path}")
    embeddings = np.load(npy_path)
    with open(json_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    return embeddings, chunks


def main():
    parser = argparse.ArgumentParser(description="Gigavolt Dense Embedding Generator (all-MiniLM-L6-v2)")
    parser.add_argument("--input-chunks", type=str, default=None)
    parser.add_argument("--data-dir", type=str, default="/opt/undata")
    parser.add_argument("--output-prefix", type=str, default="gigavolt_embeddings")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--chunk-size", type=int, default=256)
    parser.add_argument("--overlap", type=int, default=64)
    args = parser.parse_args()

    chunks = []
    if args.input_chunks and Path(args.input_chunks).exists():
        with open(args.input_chunks, "r", encoding="utf-8") as f:
            chunks = json.load(f)
    else:
        from chunking_engine import process_directory, resolve_data_directory
        target_dir = resolve_data_directory(args.data_dir)
        chunks = process_directory(target_dir, chunk_size=args.chunk_size, overlap=args.overlap)

    if not chunks:
        sys.exit(1)

    generator = EmbeddingGenerator(device=args.device)
    embeddings, enriched_chunks = generator.embed_chunks(chunks, batch_size=args.batch_size)
    save_embeddings_and_metadata(embeddings, enriched_chunks, output_prefix=args.output_prefix)
    print(f"Total Chunks Embedded: {len(chunks)} | Shape: {embeddings.shape}")


if __name__ == "__main__":
    main()