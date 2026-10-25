#!/usr/bin/env python3
"""
Technical Document Chunking & Vector Search Engine
===================================================
Fulfills criteria:
1. Chunking Engine:
   - Splits technical documents into chunks within target token range (e.g., 256-512 tokens).
   - Sentence-boundary awareness to eliminate mid-sentence splits.
   - Overlapping window mechanism to preserve context across chunk boundaries.
2. Embedding Generation:
   - Supports local models (e.g., all-MiniLM-L6-v2 via SentenceTransformers)
   - Supports cloud APIs (e.g., OpenAI's text-embedding-3-small)
   - Generates dense vector representations for all chunks in batches.
3. Vector Database (ChromaDB):
   - Embedded persistent storage using ChromaDB.
   - Comprehensive chunk metadata (source, tokens, index, sentence count).
   - Semantic similarity search, document filtering, stats, and interactive CLI.
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from abc import ABC, abstractmethod

# ----------------------------------------------------------------------------
# PDF Library Import (Supports either pypdf or PyPDF2)
# ----------------------------------------------------------------------------
try:
    import pypdf as pdf_lib
except ImportError:
    try:
        import PyPDF2 as pdf_lib
    except ImportError:
        pdf_lib = None

# ----------------------------------------------------------------------------
# ChromaDB Import
# ----------------------------------------------------------------------------
try:
    import chromadb
except ImportError:
    chromadb = None

# ----------------------------------------------------------------------------
# SentenceTransformers Import
# ----------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

# ----------------------------------------------------------------------------
# Optional OpenAI & Tiktoken Imports
# ----------------------------------------------------------------------------
try:
    import openai
except ImportError:
    openai = None

try:
    import tiktoken
except ImportError:
    tiktoken = None


# ============================================================================
# TOKEN COUNTER & ESTIMATOR
# ============================================================================

class TokenCounter:
    """
    Token counter supporting:
    1. HuggingFace / SentenceTransformer tokenizers (exact)
    2. Tiktoken for OpenAI models (exact)
    3. Robust subword-aware heuristic estimation fallback (~1.3 tokens/word)
    """

    def __init__(self, tokenizer: Optional[Any] = None, model_name: Optional[str] = None):
        self.tokenizer = tokenizer
        self.tiktoken_encoding = None

        if model_name and ("openai" in model_name.lower() or "text-embedding" in model_name.lower()):
            if tiktoken is not None:
                try:
                    self.tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
                except Exception:
                    self.tiktoken_encoding = None

    def count(self, text: str) -> int:
        """Count tokens in text using the best available method."""
        if not text:
            return 0

        # Method 1: HuggingFace / SentenceTransformer tokenizer
        if self.tokenizer is not None:
            try:
                # Fast tokenizer encode
                if hasattr(self.tokenizer, "encode"):
                    return len(self.tokenizer.encode(text, add_special_tokens=False))
                elif hasattr(self.tokenizer, "tokenize"):
                    return len(self.tokenizer.tokenize(text))
            except Exception:
                pass

        # Method 2: Tiktoken for OpenAI models
        if self.tiktoken_encoding is not None:
            try:
                return len(self.tiktoken_encoding.encode(text))
            except Exception:
                pass

        # Method 3: Subword-aware token estimator
        return self._estimate_tokens(text)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Subword-aware token estimator for English/technical text.
        Accurately estimates BPE / WordPiece token counts (~4 chars / 0.75 words per token).
        """
        words_and_symbols = re.findall(r"\w+|[^\w\s]", text)
        count = 0
        for item in words_and_symbols:
            length = len(item)
            if length <= 4:
                count += 1
            else:
                # Long words / technical identifiers split into multiple subwords
                count += 1 + ((length - 4) // 4)
        return max(1, count)


# ============================================================================
# SENTENCE BOUNDARY DETECTION
# ============================================================================

# Common abbreviations in technical, academic, and business documentation
COMMON_ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.",
    "vs.", "etc.", "eg.", "ie.", "e.g.", "i.e.", "fig.", "figs.",
    "ref.", "refs.", "eq.", "eqs.", "app.", "vol.", "dept.",
    "sec.", "al.", "no.", "approx.", "min.", "max.", "inc.",
    "ltd.", "corp.", "co.", "cf.", "stat.", "misc.", "est.",
    "avg.", "para.", "univ.", "v.", "vs."
}


def clean_pdf_text(text: str) -> str:
    """Normalize whitespace and stitch hyphenated line-breaks from PDFs."""
    if not text:
        return ""
    # Normalize carriage returns
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Re-join hyphenated words split across lines (e.g. "perfor-\nmance" -> "performance")
    text = re.sub(r'(\b\w+)-\n(\w+\b)', r'\1\2', text)
    # Collapse multiple horizontal whitespaces
    text = re.sub(r'[ \t]+', ' ', text)
    # Normalize 3+ newlines down to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_paragraph_into_sentences(paragraph: str) -> List[str]:
    """
    Split a paragraph into sentences without splitting on abbreviations,
    decimal numbers (e.g. 3.14), or version strings (v1.2.0).
    """
    paragraph = paragraph.strip()
    if not paragraph:
        return []

    # Regex delimiter: terminal punctuation followed by space and capital letter/quote/bracket
    # Captures the delimiter so we can inspect what preceded it
    raw_parts = re.split(r'([.?!]+["\'\)]?\s+(?=[A-Z0-9"\'\(\[]))', paragraph)

    if len(raw_parts) <= 1:
        return [paragraph]

    sentences = []
    current_sent = ""

    i = 0
    while i < len(raw_parts):
        part = raw_parts[i]
        current_sent += part

        if i + 1 < len(raw_parts):
            delimiter = raw_parts[i + 1]
            words = current_sent.strip().split()
            last_word = words[-1].lower() if words else ""

            # Check if this period belongs to an abbreviation
            is_abbrev = (
                last_word in COMMON_ABBREVIATIONS or
                (last_word.endswith('.') and last_word[:-1] in COMMON_ABBREVIATIONS) or
                re.match(r'^[a-z]\.$', last_word)  # Initial like 'J.'
            )

            # Check if period is part of decimal number or version string (e.g. 3.14 or 2.0)
            is_numeric = bool(re.search(r'\b\d+\s*$', current_sent) and re.match(r'^\.\d+', delimiter))

            if is_abbrev or is_numeric:
                # Merge delimiter into current sentence and continue
                current_sent += delimiter
                i += 2
            else:
                # True sentence boundary
                current_sent += delimiter.rstrip()
                if current_sent.strip():
                    sentences.append(current_sent.strip())
                current_sent = ""
                i += 2
        else:
            i += 1

    if current_sent.strip():
        sentences.append(current_sent.strip())

    return sentences


def split_into_sentences(text: str) -> List[str]:
    """
    Split technical document text into sentences/semantic segments:
    - Preserves bullet points and list items as independent units.
    - Preserves headings and markdown sections.
    - Avoids mid-sentence splits on abbreviations and numbers.
    """
    cleaned_text = clean_pdf_text(text)
    if not cleaned_text:
        return []

    paragraphs = re.split(r'\n\s*\n', cleaned_text)
    all_sentences = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Check for bullet points or numbered lists inside paragraph
        lines = para.split('\n')
        current_block = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Identify bullet lists (*, -, •, 1., 2), etc.) or headings (#, Section)
            is_bullet = bool(re.match(r'^(\*|-|•|\d+[\.)]|#{1,6}|[a-zA-Z]\))\s+', line_str))
            if is_bullet:
                if current_block:
                    all_sentences.extend(_split_paragraph_into_sentences(" ".join(current_block)))
                    current_block = []
                all_sentences.extend(_split_paragraph_into_sentences(line_str))
            else:
                current_block.append(line_str)

        if current_block:
            all_sentences.extend(_split_paragraph_into_sentences(" ".join(current_block)))

    return [s.strip() for s in all_sentences if s and s.strip()]


def subdivide_oversized_sentence(
    sentence: str,
    max_tokens: int,
    token_counter: TokenCounter
) -> List[str]:
    """
    Safety fallback: if a single sentence exceeds max_tokens (e.g. unformatted log,
    giant code line, raw JSON), subdivide along secondary punctuation (;, :, ,, or words).
    """
    if token_counter.count(sentence) <= max_tokens:
        return [sentence]

    # Try secondary punctuation first: semicolons, colons, or dashes
    parts = re.split(r'([;:—–]\s+)', sentence)
    if len(parts) > 1:
        merged = []
        curr = ""
        for p in parts:
            if token_counter.count(curr + p) <= max_tokens:
                curr += p
            else:
                if curr.strip():
                    merged.extend(subdivide_oversized_sentence(curr.strip(), max_tokens, token_counter))
                curr = p
        if curr.strip():
            merged.extend(subdivide_oversized_sentence(curr.strip(), max_tokens, token_counter))
        if all(token_counter.count(m) <= max_tokens for m in merged):
            return merged

    # Secondary fallback: split by commas
    parts = re.split(r'(,\s+)', sentence)
    if len(parts) > 1:
        merged = []
        curr = ""
        for p in parts:
            if token_counter.count(curr + p) <= max_tokens:
                curr += p
            else:
                if curr.strip():
                    merged.extend(subdivide_oversized_sentence(curr.strip(), max_tokens, token_counter))
                curr = p
        if curr.strip():
            merged.extend(subdivide_oversized_sentence(curr.strip(), max_tokens, token_counter))
        if all(token_counter.count(m) <= max_tokens for m in merged):
            return merged

    # Final fallback: word-level windowing
    words = sentence.split()
    chunks = []
    curr_words = []
    for w in words:
        if token_counter.count(" ".join(curr_words + [w])) <= max_tokens:
            curr_words.append(w)
        else:
            if curr_words:
                chunks.append(" ".join(curr_words))
            curr_words = [w]
    if curr_words:
        chunks.append(" ".join(curr_words))

    return chunks


# ============================================================================
# CHUNKING ENGINE (TOKEN-BASED WITH OVERLAPPING WINDOWS & SENTENCE BOUNDARIES)
# ============================================================================

def chunk_text_sentence_aware(
    text: str,
    chunk_size_tokens: int = 384,
    overlap_tokens: int = 64,
    token_counter: Optional[TokenCounter] = None
) -> List[Dict]:
    """
    Splits text into chunks within the target token range (e.g. 256-512 tokens).
    - Preserves sentence boundaries (no mid-sentence cuts).
    - Preserves context across chunk boundaries via complete overlapping sentences.

    Args:
        text: Input document text.
        chunk_size_tokens: Target chunk size in tokens (recommended: 256-512).
        overlap_tokens: Target overlap size in tokens (e.g., 50-100 tokens).
        token_counter: TokenCounter instance for exact or estimated token counts.

    Returns:
        List of chunk dictionaries with metadata.
    """
    if token_counter is None:
        token_counter = TokenCounter()

    # Step 1: Split into sentences
    raw_sentences = split_into_sentences(text)
    if not raw_sentences:
        return []

    # Step 2: Handle any single sentence larger than chunk_size_tokens
    sentences: List[str] = []
    for s in raw_sentences:
        if token_counter.count(s) > chunk_size_tokens:
            sentences.extend(subdivide_oversized_sentence(s, chunk_size_tokens, token_counter))
        else:
            sentences.append(s)

    sentence_token_counts = [token_counter.count(s) for s in sentences]

    chunks: List[Dict] = []
    current_sentence_indices: List[int] = []
    current_token_count = 0
    i = 0
    chunk_id = 0

    while i < len(sentences):
        sent_tokens = sentence_token_counts[i]

        # Add sentence if it fits or if the chunk is currently empty
        if (current_token_count + sent_tokens <= chunk_size_tokens) or not current_sentence_indices:
            current_sentence_indices.append(i)
            current_token_count += sent_tokens
            i += 1
        else:
            # Chunk capacity reached: emit the chunk
            chunk_text = " ".join(sentences[idx] for idx in current_sentence_indices).strip()
            chunks.append({
                "id": f"chunk_{chunk_id:04d}",
                "text": chunk_text,
                "token_count": current_token_count,
                "char_count": len(chunk_text),
                "sentence_count": len(current_sentence_indices),
                "method": "sentence_aware_token_overlap",
                "overlap_with_prev": chunk_id > 0
            })
            chunk_id += 1

            # Compute overlapping window for the subsequent chunk:
            # Take trailing complete sentences from current chunk whose combined tokens <= overlap_tokens
            overlap_indices: List[int] = []
            overlap_tok_sum = 0

            for idx in reversed(current_sentence_indices):
                stok = sentence_token_counts[idx]
                if overlap_tok_sum + stok <= overlap_tokens:
                    overlap_indices.insert(0, idx)
                    overlap_tok_sum += stok
                else:
                    # If nothing included yet and overlap_tokens > 0, include at least 1 sentence
                    if not overlap_indices and stok < chunk_size_tokens:
                        overlap_indices.insert(0, idx)
                        overlap_tok_sum += stok
                    break

            # Safety check: avoid complete overlap stagnation (must make forward progress)
            if len(overlap_indices) >= len(current_sentence_indices):
                overlap_indices = overlap_indices[1:] if len(overlap_indices) > 1 else []
                overlap_tok_sum = sum(sentence_token_counts[idx] for idx in overlap_indices)

            current_sentence_indices = list(overlap_indices)
            current_token_count = overlap_tok_sum

    # Emit final remaining chunk
    if current_sentence_indices:
        chunk_text = " ".join(sentences[idx] for idx in current_sentence_indices).strip()
        if not chunks or chunk_text != chunks[-1]["text"]:
            chunks.append({
                "id": f"chunk_{chunk_id:04d}",
                "text": chunk_text,
                "token_count": current_token_count,
                "char_count": len(chunk_text),
                "sentence_count": len(current_sentence_indices),
                "method": "sentence_aware_token_overlap",
                "overlap_with_prev": chunk_id > 0
            })

    return chunks


# Backwards compatibility alias for character-based chunking
def chunk_by_fixed_size(text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
    """Legacy fixed character count chunking (kept for backwards compatibility)."""
    chunks = []
    start = 0
    chunk_id = 0

    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append({
                "id": f"fixed_{chunk_id}",
                "text": chunk_text,
                "method": "fixed_size",
                "size": len(chunk_text),
                "char_start": start,
                "char_end": end,
                "token_count": TokenCounter._estimate_tokens(chunk_text)
            })
            chunk_id += 1

        start = end - overlap

    return chunks


# ============================================================================
# PDF EXTRACTION & DISCOVERY
# ============================================================================

def find_pdfs_in_directory(directory: Path) -> List[str]:
    """Find all PDF files in directory (case-insensitive, recursive)."""
    if not directory.exists():
        return []

    pdf_files = list(directory.rglob("*.pdf")) + list(directory.rglob("*.PDF"))
    return sorted(list({str(p.resolve()) for p in pdf_files}))


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract and normalize all text from a PDF file."""
    if pdf_lib is None:
        print("  ❌ Neither 'pypdf' nor 'PyPDF2' is installed. Please install: pip install pypdf")
        return ""

    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = pdf_lib.PdfReader(file)
            text_pages = []
            for page_idx, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_pages.append(page_text)
                except Exception as page_err:
                    print(f"  ⚠️  Error extracting page {page_idx + 1} of {pdf_path}: {page_err}")

            raw_text = "\n\n".join(text_pages)
            return clean_pdf_text(raw_text)
    except Exception as e:
        print(f"  ⚠️  Error reading {pdf_path}: {e}")
        return ""


def process_and_chunk_pdfs(
    pdf_paths: List[str],
    chunk_size_tokens: int = 384,
    overlap_tokens: int = 64,
    token_counter: Optional[TokenCounter] = None
) -> List[Dict]:
    """
    Extract text from PDFs and split into sentence-boundary aware token chunks.
    """
    print(f"\n{'='*70}")
    print(f"Processing {len(pdf_paths)} PDF files")
    print(f"Engine: Sentence-Boundary Aware Token Chunker")
    print(f"Target size: {chunk_size_tokens} tokens | Overlap: {overlap_tokens} tokens")
    print(f"{'='*70}\n")

    all_chunks = []
    total_tokens_across_docs = 0

    for i, pdf_path in enumerate(pdf_paths, 1):
        filename = os.path.basename(pdf_path)
        print(f"[{i}/{len(pdf_paths)}] Extracting: {filename}")

        text = extract_text_from_pdf(pdf_path)
        if not text.strip():
            print(f"  ⚠️  No text extracted from {filename}")
            continue

        doc_chunks = chunk_text_sentence_aware(
            text=text,
            chunk_size_tokens=chunk_size_tokens,
            overlap_tokens=overlap_tokens,
            token_counter=token_counter
        )

        doc_tokens = sum(c["token_count"] for c in doc_chunks)
        total_tokens_across_docs += doc_tokens

        for chunk_idx, chunk in enumerate(doc_chunks):
            chunk["source_file"] = filename
            chunk["source_path"] = pdf_path
            chunk["chunk_index"] = chunk_idx
            chunk["total_chunks"] = len(doc_chunks)
            chunk["id"] = f"{filename}_chunk_{chunk_idx:04d}"

        all_chunks.extend(doc_chunks)
        avg_tokens = doc_tokens // len(doc_chunks) if doc_chunks else 0
        print(f"  ✓ {len(text)} chars -> {len(doc_chunks)} chunks ({doc_tokens} tokens, avg {avg_tokens} tok/chunk)")

    print(f"\n{'='*70}")
    print(f"✓ Summary: Created {len(all_chunks)} chunks across {len(pdf_paths)} PDFs")
    if all_chunks:
        avg_all = total_tokens_across_docs // len(all_chunks)
        print(f"✓ Total tokens: {total_tokens_across_docs} | Average chunk size: {avg_all} tokens")
    print(f"{'='*70}\n")
    return all_chunks


# ============================================================================
# EMBEDDING ENGINE ABSTRACTIONS
# ============================================================================

class BaseEmbeddingEngine(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed_documents(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate dense vector embeddings for a list of document chunks."""
        pass

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """Generate a dense vector embedding for a single search query."""
        pass

    @abstractmethod
    def get_token_counter(self) -> TokenCounter:
        """Return a TokenCounter configured with this model's tokenizer."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier string."""
        pass


class SentenceTransformerEmbedder(BaseEmbeddingEngine):
    """
    Local embedding generation using SentenceTransformers.
    Default: 'all-MiniLM-L6-v2' (fast, lightweight, dense 384-d vectors).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install it with: pip install sentence-transformers"
            )

        print(f"Loading local SentenceTransformer model: '{model_name}'...")
        self.model = SentenceTransformer(model_name)
        print(f"✓ Embedding model '{model_name}' ready (dimension: {self.model.get_sentence_embedding_dimension()})")

    @property
    def model_name(self) -> str:
        return self._model_name

    def get_token_counter(self) -> TokenCounter:
        tokenizer = getattr(self.model, "tokenizer", None)
        return TokenCounter(tokenizer=tokenizer, model_name=self._model_name)

    def embed_documents(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        if not texts:
            return []

        all_embeddings = []
        total = len(texts)
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.model.encode(
                batch,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True
            )
            all_embeddings.extend(embeddings.tolist())
            progress = min(i + batch_size, total)
            print(f"  Embedding progress: {progress}/{total} chunks ({(progress/total)*100:.1f}%)")

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        embedding = self.model.encode(query, normalize_embeddings=True)
        return embedding.tolist()


class OpenAIEmbedder(BaseEmbeddingEngine):
    """
    Cloud embedding generation using OpenAI API.
    Default: 'text-embedding-3-small' (1536-d dense vectors).
    """

    def __init__(self, model_name: str = "text-embedding-3-small", api_key: Optional[str] = None):
        self._model_name = model_name
        api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OpenAI API key required for OpenAIEmbedder. "
                "Set the OPENAI_API_KEY environment variable or pass --api-key."
            )

        if openai is None:
            raise ImportError("openai package required. Install with: pip install openai")

        self.client = openai.OpenAI(api_key=api_key)
        print(f"✓ OpenAI client initialized with model '{model_name}'")

    @property
    def model_name(self) -> str:
        return self._model_name

    def get_token_counter(self) -> TokenCounter:
        return TokenCounter(model_name=self._model_name)

    def embed_documents(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        if not texts:
            return []

        all_embeddings = []
        total = len(texts)

        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            response = self.client.embeddings.create(
                model=self._model_name,
                input=batch
            )
            batch_vectors = [item.embedding for item in response.data]
            all_embeddings.extend(batch_vectors)
            progress = min(i + batch_size, total)
            print(f"  OpenAI Embedding progress: {progress}/{total} chunks ({(progress/total)*100:.1f}%)")

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self._model_name,
            input=query
        )
        return response.data[0].embedding


def get_embedding_engine(
    provider: str = "sentence_transformers",
    model_name: str = "all-MiniLM-L6-v2",
    api_key: Optional[str] = None
) -> BaseEmbeddingEngine:
    """Factory to instantiate the chosen embedding engine."""
    provider_clean = provider.lower().replace("-", "_")

    if "openai" in provider_clean or "text-embedding" in model_name.lower():
        return OpenAIEmbedder(model_name=model_name, api_key=api_key)
    else:
        return SentenceTransformerEmbedder(model_name=model_name)


# ============================================================================
# VECTOR DATABASE (CHROMADB)
# ============================================================================

class TechnicalDocVectorDB:
    """
    Vector database wrapper using ChromaDB for dense vector storage and retrieval.
    """

    def __init__(
        self,
        collection_name: str = "technical_documents",
        db_path: str = "./chroma_vectordb",
        embedder: Optional[BaseEmbeddingEngine] = None,
        reindex: bool = False
    ):
        if chromadb is None:
            raise ImportError(
                "chromadb is required. Install it with: pip install chromadb"
            )

        self.db_path = db_path
        self.collection_name = collection_name
        self.embedder = embedder or SentenceTransformerEmbedder('all-MiniLM-L6-v2')

        print(f"Initializing ChromaDB vector database at: {db_path}")
        self.client = chromadb.PersistentClient(path=db_path)

        if reindex:
            try:
                self.client.delete_collection(name=collection_name)
                print(f"  Cleared existing collection '{collection_name}' (reindex=True)")
            except Exception:
                pass

        # Using cosine distance space
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        print(f"✓ ChromaDB collection '{collection_name}' ready\n")

    def add_chunks(self, chunks: List[Dict], batch_size: int = 64):
        """Generate dense embeddings and store chunks + metadata in ChromaDB."""
        if not chunks:
            print("No chunks to add.")
            return

        print(f"\nAdding {len(chunks)} chunks to ChromaDB collection '{self.collection_name}'...")
        texts = [c["text"] for c in chunks]
        ids = [c["id"] for c in chunks]

        # Prepare clean ChromaDB metadata (primitive types only)
        metadatas = [{
            "source_file": str(c.get("source_file", "")),
            "source_path": str(c.get("source_path", "")),
            "chunk_index": int(c.get("chunk_index", 0)),
            "total_chunks": int(c.get("total_chunks", 1)),
            "token_count": int(c.get("token_count", 0)),
            "char_count": int(c.get("char_count", len(c.get("text", "")))),
            "sentence_count": int(c.get("sentence_count", 1)),
            "method": str(c.get("method", "sentence_aware_token_overlap")),
            "model": str(self.embedder.model_name)
        } for c in chunks]

        print("Generating dense vector representations...")
        all_embeddings = self.embedder.embed_documents(texts, batch_size=batch_size)

        print("Upserting vectors and metadata into ChromaDB...")
        # ChromaDB supports upserting in batches
        insert_batch_size = 100
        for i in range(0, len(ids), insert_batch_size):
            end_idx = min(i + insert_batch_size, len(ids))
            self.collection.upsert(
                ids=ids[i:end_idx],
                documents=texts[i:end_idx],
                embeddings=all_embeddings[i:end_idx],
                metadatas=metadatas[i:end_idx]
            )

        print(f"✓ Successfully stored {len(chunks)} chunks in ChromaDB\n")

    def search(self, query: str, n_results: int = 5, filter_file: Optional[str] = None) -> Dict:
        """
        Perform dense semantic vector search with cosine similarity scoring.
        """
        query_embedding = self.embedder.embed_query(query)
        where = {"source_file": filter_file} if filter_file else None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where
        )
        return results

    def get_stats(self) -> Dict:
        """Return comprehensive collection statistics."""
        all_data = self.collection.get()
        source_files: Dict[str, int] = {}
        total_tokens = 0

        for metadata in all_data.get('metadatas', []):
            source = metadata.get('source_file', 'Unknown')
            source_files[source] = source_files.get(source, 0) + 1
            total_tokens += metadata.get('token_count', 0)

        total_chunks = len(all_data.get('ids', []))
        avg_tokens = (total_tokens // total_chunks) if total_chunks > 0 else 0

        return {
            "total_chunks": total_chunks,
            "source_files": source_files,
            "num_documents": len(source_files),
            "total_tokens": total_tokens,
            "avg_tokens_per_chunk": avg_tokens,
            "model_name": self.embedder.model_name
        }


# Backwards compatibility alias
SimpleVectorDB = TechnicalDocVectorDB


# ============================================================================
# INTERACTIVE QUERY LOOP
# ============================================================================

def run_query_loop(db: TechnicalDocVectorDB):
    """Interactive command-line query loop for semantic document search."""
    stats = db.get_stats()
    print("="*70)
    print("VECTOR DATABASE READY - INTERACTIVE SEMANTIC SEARCH")
    print("="*70)
    print(f"Indexed documents : {stats['num_documents']}")
    print(f"Total chunks      : {stats['total_chunks']}")
    print(f"Avg tokens/chunk  : {stats['avg_tokens_per_chunk']}")
    print(f"Embedding model   : {stats['model_name']}")
    print("\nCommands:")
    print("  - <query>                  : Search across all indexed documents")
    print("  - filter:<file.pdf> <query>: Search within a specific document")
    print("  - top:<k> <query>          : Return top-k results (e.g. top:3 transformer)")
    print("  - stats                    : View detailed database statistics")
    print("  - list                     : List all indexed documents")
    print("  - quit (or exit, q)        : Exit interactive search")
    print("="*70)

    while True:
        try:
            print()
            raw_input = input("🔍 Query: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Exiting search. Goodbye!")
            break

        if not raw_input:
            continue

        if raw_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Exiting search. Goodbye!")
            break

        if raw_input.lower() == 'stats':
            current_stats = db.get_stats()
            print(f"\n--- Database Statistics ---")
            print(f"Total chunks     : {current_stats['total_chunks']}")
            print(f"Total documents  : {current_stats['num_documents']}")
            print(f"Avg tokens/chunk : {current_stats['avg_tokens_per_chunk']}")
            print(f"Model            : {current_stats['model_name']}")
            print("\nChunks per document:")
            for source_file, count in sorted(current_stats['source_files'].items()):
                print(f"  • {source_file}: {count} chunks")
            continue

        if raw_input.lower() == 'list':
            current_stats = db.get_stats()
            print("\n--- Indexed Documents ---")
            for i, (source_file, count) in enumerate(sorted(current_stats['source_files'].items()), 1):
                print(f"  {i}. {source_file} ({count} chunks)")
            continue

        # Parse optional filters: filter:<filename.pdf> and top:<k>
        filter_file = None
        n_results = 5
        query = raw_input

        # Check for top:<k>
        top_match = re.match(r'^top:(\d+)\s+(.+)$', query, re.IGNORECASE)
        if top_match:
            n_results = int(top_match.group(1))
            query = top_match.group(2).strip()

        # Check for filter:<file>
        if query.startswith('filter:'):
            parts = query.split(' ', 1)
            if len(parts) == 2:
                filter_file = parts[0].replace('filter:', '').strip()
                query = parts[1].strip()
                print(f"(Scoped to document: '{filter_file}')")

        try:
            results = db.search(query, n_results=n_results, filter_file=filter_file)
            ids = results.get('ids', [[]])[0]

            if not ids:
                print(f"\n⚠️  No results found for: \"{query}\"")
                continue

            print(f"\n{'='*70}")
            print(f"Top {len(ids)} Semantic Matches for: \"{query}\"")
            print(f"{'='*70}")

            for i in range(len(ids)):
                doc_text = results['documents'][0][i]
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]

                # ChromaDB cosine distance: similarity = 1 - cosine_distance
                similarity = max(0.0, 1.0 - distance)

                src = metadata.get('source_file', 'Unknown')
                idx = metadata.get('chunk_index', 0)
                tot = metadata.get('total_chunks', 1)
                tokens = metadata.get('token_count', 0)

                print(f"\n[{i+1}] 📄 {src}  (Chunk {idx+1}/{tot})")
                print(f"    Similarity: {similarity:.4f} ({similarity*100:.1f}%) | Tokens: {tokens}")
                print(f"    {'-'*66}")

                # Display text excerpt with clean indentation
                snippet = doc_text.strip().replace('\n', '\n    ')
                print(f"    {snippet}")

        except Exception as e:
            print(f"\n❌ Search error: {e}")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Technical Document Chunking Engine & ChromaDB Vector Store"
    )
    parser.add_argument(
        "--dir", "-d",
        type=str,
        default=None,
        help="Directory containing PDF files (defaults to candidate locations: /opt/undata/, /opt/data/, ./data/, ./)"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Process a specific single PDF file"
    )
    parser.add_argument(
        "--chunk-size", "-c",
        type=int,
        default=384,
        help="Target chunk size in tokens (recommended: 256-512, default: 384)"
    )
    parser.add_argument(
        "--overlap", "-o",
        type=int,
        default=64,
        help="Context overlap window in tokens (default: 64)"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="all-MiniLM-L6-v2",
        help="Embedding model name (e.g. 'all-MiniLM-L6-v2' or 'text-embedding-3-small')"
    )
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default="sentence_transformers",
        choices=["sentence_transformers", "openai"],
        help="Embedding provider ('sentence_transformers' for local or 'openai' for cloud API)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./chroma_vectordb",
        help="Path for ChromaDB persistent database (default: ./chroma_vectordb)"
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Force re-chunking and re-embedding, wiping any existing collection"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Run a single search query non-interactively and exit"
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Do not launch interactive search loop after processing"
    )

    return parser.parse_args()


def discover_pdf_files(args: argparse.Namespace) -> List[str]:
    """Find PDF files based on user argument or standard candidate directories."""
    # Option 1: Single file specified
    if args.file:
        file_path = Path(args.file)
        if file_path.is_file():
            return [str(file_path.resolve())]
        else:
            print(f"❌ Specified file not found: {args.file}")
            return []

    # Option 2: Directory explicitly passed
    if args.dir:
        dir_path = Path(args.dir)
        pdfs = find_pdfs_in_directory(dir_path)
        if pdfs:
            return pdfs
        else:
            print(f"❌ No PDF files found in specified directory: {dir_path}")
            return []

    # Option 3: Candidate search locations in standard priority
    candidate_dirs = [
        Path('/opt/undata/'),
        Path('/opt/data/'),
        Path('./data/'),
        Path('.')
    ]

    for candidate in candidate_dirs:
        if candidate.exists() and candidate.is_dir():
            pdfs = find_pdfs_in_directory(candidate)
            if pdfs:
                print(f"Found {len(pdfs)} PDF(s) in candidate directory: {candidate.resolve()}")
                return pdfs

    return []


def main():
    args = parse_arguments()

    print("="*70)
    print("TECHNICAL DOCUMENT CHUNKING & VECTOR SEARCH ENGINE")
    print("="*70)

    # 1. Discover PDFs
    pdf_paths = discover_pdf_files(args)
    if not pdf_paths:
        print("❌ No PDF files found.")
        print("Please provide a PDF directory or file via:")
        print("  python3 pdfChunking.py --dir /path/to/pdfs")
        print("  python3 pdfChunking.py --file /path/to/document.pdf")
        return

    print(f"\nDiscovered {len(pdf_paths)} PDF file(s):")
    for i, p in enumerate(pdf_paths, 1):
        print(f"  {i}. {os.path.basename(p)}")

    # 2. Initialize Embedding Engine
    print(f"\nInitializing embedding engine (provider: {args.provider}, model: {args.model})...")
    try:
        embedder = get_embedding_engine(
            provider=args.provider,
            model_name=args.model
        )
    except Exception as e:
        print(f"❌ Failed to initialize embedding engine: {e}")
        return

    # Obtain exact tokenizer from embedder for chunking
    token_counter = embedder.get_token_counter()

    # 3. Initialize ChromaDB
    try:
        db = TechnicalDocVectorDB(
            collection_name="technical_documents",
            db_path=args.db_path,
            embedder=embedder,
            reindex=args.reindex
        )
    except Exception as e:
        print(f"❌ Failed to initialize ChromaDB: {e}")
        return

    # 4. Check if collection already has data (and --reindex not set)
    stats = db.get_stats()
    should_chunk_and_embed = args.reindex or (stats["total_chunks"] == 0)

    if should_chunk_and_embed:
        # Run sentence-aware token chunking
        chunks = process_and_chunk_pdfs(
            pdf_paths=pdf_paths,
            chunk_size_tokens=args.chunk_size,
            overlap_tokens=args.overlap,
            token_counter=token_counter
        )

        if not chunks:
            print("❌ No chunks created from PDFs.")
            return

        # Store dense vectors in ChromaDB
        db.add_chunks(chunks)
    else:
        print(f"ℹ️  Existing ChromaDB collection contains {stats['total_chunks']} chunks from {stats['num_documents']} document(s).")
        print("    (Use --reindex to force re-processing)")

    # 5. Non-interactive single query if specified
    if args.query:
        print(f"\nExecuting search query: \"{args.query}\"")
        results = db.search(args.query, n_results=5)
        ids = results.get('ids', [[]])[0]
        for i in range(len(ids)):
            metadata = results['metadatas'][0][i]
            similarity = max(0.0, 1.0 - results['distances'][0][i])
            doc_text = results['documents'][0][i]
            print(f"\n[{i+1}] {metadata.get('source_file')} | Similarity: {similarity:.4f}")
            print(f"    {doc_text[:300]}...")
        return

    # 6. Interactive search loop
    if not args.no_interactive:
        run_query_loop(db)


if __name__ == "__main__":
    main()

    main()