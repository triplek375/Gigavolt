#!/usr/bin/env python3
"""
Gigavolt Technical Document Chunking Engine
============================================
Splits Gigavolt technical documentation and service records into token-bounded,
sentence-boundary-aware chunks with configurable overlapping context windows.

Key Features:
- Token-bounded chunking (configurable 256 - 512 tokens, default: 384)
- Sentence-boundary awareness to avoid mid-sentence truncation
- Context-preserving overlapping sliding windows (default: 64 tokens)
- Handles technical abbreviations, decimals, and Gigavolt document codes
- Rich metadata extraction (doc type, doc ID, page numbers, token count)
- Configurable via CLI arguments or programmatic API
"""

import os
import re
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("GigavoltChunker")


# ============================================================================
# TOKENIZER UTILITY (SentenceTransformers / HuggingFace with Robust Fallback)
# ============================================================================

class DocumentTokenizer:
    """
    Tokenizer wrapper that aligns token counts with all-MiniLM-L6-v2.
    Uses Hugging Face / SentenceTransformers tokenizer when available,
    with an accurate wordpiece-approximation fallback for offline/isolated runs.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._tokenizer = None
        self._init_tokenizer()

    def _init_tokenizer(self):
        try:
            from transformers import AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            logger.debug(f"Loaded HuggingFace tokenizer: {self.model_name}")
        except Exception:
            try:
                from sentence_transformers import SentenceTransformer
                st = SentenceTransformer(self.model_name)
                self._tokenizer = st.tokenizer
                logger.debug("Loaded tokenizer from SentenceTransformer instance")
            except Exception:
                self._tokenizer = None
                logger.debug("Using fallback regex-based subword tokenizer")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if not text or not text.strip():
            return 0
        if self._tokenizer is not None:
            try:
                return len(self._tokenizer.encode(text, add_special_tokens=False))
            except Exception:
                pass
        # Accurate fallback: Words + punctuation + subword expansion (~1.3 tokens/word)
        tokens = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
        return max(1, int(len(tokens) * 1.15))

    def split_tokens(self, text: str) -> List[str]:
        """Split text into raw tokens (for splitting oversized sentences)"""
        if self._tokenizer is not None and hasattr(self._tokenizer, "tokenize"):
            try:
                return self._tokenizer.tokenize(text)
            except Exception:
                pass
        return re.findall(r"\w+|[^\w\s]", text, re.UNICODE)


# ============================================================================
# SENTENCE BOUNDARY DETECTOR FOR TECHNICAL DOCUMENTATION
# ============================================================================

# Common abbreviations in technical documentation that should NOT trigger splits
PROTECTED_ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "vs.", "fig.", "figs.", "ref.", "refs.",
    "rev.", "no.", "nos.", "approx.", "est.", "min.", "max.", "sec.",
    "dept.", "div.", "vol.", "vols.", "para.", "art.", "spec.", "sop.",
    "eco.", "inc.", "cal.", "comm.", "firm.", "hvac.", "war.", "bms.",
    "deg.", "dia.", "avg.", "temp.", "dc.", "ac.", "std.", "kw.", "mw.",
    "kwh.", "mwh.", "v.", "kv.", "a.", "ka.", "hz.", "khz.", "mhz."
}

# Regex for decimals, units, and document identifiers: e.g., 3.14, 1.5kV, GV-ECO-2024-019
DECIMAL_REGEX = re.compile(r"\b\d+\.\d+\b")
DOC_CODE_REGEX = re.compile(r"\bGV-[A-Z]+-\d{4}-\d+\b")


def clean_technical_text(raw_text: str) -> str:
    """Normalize whitespace and formatting while preserving technical symbols"""
    if not raw_text:
        return ""
    # Normalize unicode spaces & dashes
    text = raw_text.replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "--")
    # Replace carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple blank lines to at most two
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove control characters except standard whitespace
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or (ch.isprintable() and ord(ch) >= 32))
    return text.strip()


def split_into_sentences(text: str) -> List[str]:
    """
    Split technical text into sentences with boundary awareness:
    - Protects technical abbreviations (e.g., i.e., Fig., Rev., min., max.)
    - Protects numerical decimals (e.g., 3.3V, 0.05%)
    - Protects Gigavolt document codes (e.g., GV-ECO-2024-019)
    - Treats bullet points and numbered list items as distinct sentence units
    """
    cleaned = clean_technical_text(text)
    if not cleaned:
        return []

    # Mask known abbreviations and decimals temporarily to avoid false splits
    placeholders = {}
    counter = 0

    def mask_match(match):
        nonlocal counter
        token = f"__TOKEN_{counter}__"
        placeholders[token] = match.group(0)
        counter += 1
        return token

    # Mask decimals (e.g. 12.5, 0.001)
    masked_text = DECIMAL_REGEX.sub(mask_match, cleaned)

    # Mask abbreviations case-insensitively
    for abbr in PROTECTED_ABBREVIATIONS:
        pattern = re.compile(re.escape(abbr), re.IGNORECASE)
        masked_text = pattern.sub(mask_match, masked_text)

    # Mask Gigavolt document codes
    masked_text = DOC_CODE_REGEX.sub(mask_match, masked_text)

    # Boundary split patterns:
    # 1. Period, question mark, exclamation point followed by whitespace + capital letter
    # 2. Hard line breaks followed by bullet points, numbers, or section titles
    # 3. Semicolon followed by newline (frequent in technical specifications)
    raw_splits = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9\(\[\"\'])|"      # Standard punctuation + capital/bracket
        r"\n(?=\s*[-*•▪]\s+)|"                     # Bullet points
        r"\n(?=\s*\d+[\.\)]\s+)|"                  # Numbered lists (1. or 1))
        r"(?<=[;:])\n+(?=[A-Z0-9])|"               # Semicolon/colon before newline
        r"\n{2,}",                                 # Paragraph breaks
        masked_text
    )

    sentences = []
    for chunk in raw_splits:
        if not chunk:
            continue
        # Unmask placeholders
        for token, original in placeholders.items():
            chunk = chunk.replace(token, original)
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if chunk:
            sentences.append(chunk)

    return sentences


# ============================================================================
# GIGAVOLT DOCUMENT METADATA PARSER
# ============================================================================

def parse_gigavolt_filename(filename: str) -> Dict[str, str]:
    """
    Extract structured metadata from Gigavolt standardized document filenames.
    Examples:
    - 'GV-ECO-2024-019 Engineering Change Order.pdf' -> type='ECO', code='GV-ECO-2024-019'
    - 'GV-INC-2024-104 Field Incident Report Contactor Flashover.pdf' -> type='INC'
    - 'GV-SOP-COMM-201 SOP Megapack X-7000 SAT.pdf' -> type='SOP'
    - 'GV-SPEC-CELL-LFP-08 Datasheet.pdf' -> type='SPEC'
    - 'GV-MAN-X7000-001 Manual.pdf' -> type='MAN'
    - 'GV-SUP-REP-401 Supply Chain Integration Brief.pdf' -> type='SUP'
    """
    name = Path(filename).stem
    metadata = {
        "doc_code": name,
        "doc_type": "OTHER",
        "doc_category": "Documentation",
        "doc_title": name
    }

    type_mapping = {
        "ECO": ("ECO", "Engineering Change Order"),
        "INC": ("INC", "Field Incident Investigation"),
        "MAN": ("MAN", "System Operation Manual"),
        "SOP": ("SOP", "Standard Operating Procedure"),
        "SPEC": ("SPEC", "Component & Technical Specification"),
        "SUP": ("SUP", "Supplier & Quality Audit Report")
    }

    match = re.match(r"^(GV-[A-Z]+(?:-[A-Z0-9]+)+)\s*(.*)$", name)
    if match:
        code = match.group(1)
        title = match.group(2).strip() or code
        metadata["doc_code"] = code
        metadata["doc_title"] = title

        # Extract primary type prefix: GV-ECO, GV-INC, GV-SOP, etc.
        parts = code.split("-")
        if len(parts) >= 2:
            prefix = parts[1]
            if prefix in type_mapping:
                metadata["doc_type"] = type_mapping[prefix][0]
                metadata["doc_category"] = type_mapping[prefix][1]

    return metadata


# ============================================================================
# CHUNKING ENGINE IMPLEMENTATION
# ============================================================================

class DocumentChunker:
    """
    Sentence-boundary-aware, token-bounded document chunker.
    Splits technical documents into chunks of 256-512 tokens with overlapping context.
    """

    def __init__(
        self,
        chunk_size: int = 384,
        overlap: int = 64,
        min_chunk_size: int = 64,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        """
        Args:
            chunk_size: Target maximum tokens per chunk (default 384, recommended 256-512)
            overlap: Overlapping context in tokens between adjacent chunks (default 64)
            min_chunk_size: Minimum token threshold to prevent trailing fragments
            model_name: Tokenizer model to align token counts
        """
        if chunk_size < 128:
            raise ValueError(f"chunk_size must be at least 128 tokens, got {chunk_size}")
        if overlap >= chunk_size:
            raise ValueError(f"overlap ({overlap}) must be strictly less than chunk_size ({chunk_size})")

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size
        self.tokenizer = DocumentTokenizer(model_name=model_name)

    def _split_long_sentence(self, sentence: str) -> List[str]:
        """
        Gracefully sub-splits an abnormally long sentence (exceeding chunk_size)
        using clause boundaries (colons, semicolons, commas) or words.
        """
        clauses = re.split(r"(?<=[,;:])\s+", sentence)
        sub_sentences = []
        current = []
        current_len = 0

        for clause in clauses:
            c_len = self.tokenizer.count_tokens(clause)
            if current_len + c_len <= self.chunk_size:
                current.append(clause)
                current_len += c_len
            else:
                if current:
                    sub_sentences.append(" ".join(current))
                # If a single clause still exceeds chunk_size, split by words
                if c_len > self.chunk_size:
                    words = clause.split()
                    word_sub = []
                    word_len = 0
                    for w in words:
                        w_t = self.tokenizer.count_tokens(w)
                        if word_len + w_t > self.chunk_size:
                            if word_sub:
                                sub_sentences.append(" ".join(word_sub))
                            word_sub = [w]
                            word_len = w_t
                        else:
                            word_sub.append(w)
                            word_len += w_t
                    if word_sub:
                        current = word_sub
                        current_len = word_len
                else:
                    current = [clause]
                    current_len = c_len

        if current:
            sub_sentences.append(" ".join(current))

        return sub_sentences

    def chunk_document_pages(
        self,
        pages: List[Tuple[int, str]],
        doc_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Chunk document text across pages while tracking page numbers and sentence boundaries.

        Args:
            pages: List of (page_number, page_text) tuples
            doc_metadata: Dictionary with document-level metadata (doc_code, doc_type, etc.)

        Returns:
            List of chunk dictionaries with metadata and context bounds
        """
        if not pages:
            return []

        doc_meta = doc_metadata or {}
        doc_code = doc_meta.get("doc_code", "DOC")

        # Step 1: Extract all sentences with their source page number
        annotated_sentences: List[Dict[str, Any]] = []
        for page_num, page_text in pages:
            page_sentences = split_into_sentences(page_text)
            for s in page_sentences:
                token_len = self.tokenizer.count_tokens(s)
                if token_len > self.chunk_size:
                    # Sub-split oversized sentences
                    subs = self._split_long_sentence(s)
                    for sub in subs:
                        sub_len = self.tokenizer.count_tokens(sub)
                        annotated_sentences.append({
                            "text": sub,
                            "tokens": sub_len,
                            "page": page_num
                        })
                else:
                    annotated_sentences.append({
                        "text": s,
                        "tokens": token_len,
                        "page": page_num
                    })

        if not annotated_sentences:
            return []

        # Step 2: Assemble chunks using sentence-aware sliding window
        chunks = []
        chunk_idx = 0
        current_sentences: List[Dict[str, Any]] = []
        current_tokens = 0
        has_overlap = False

        i = 0
        n_sentences = len(annotated_sentences)

        while i < n_sentences:
            sent = annotated_sentences[i]
            sent_tokens = sent["tokens"]

            # If adding this sentence would exceed chunk_size, emit current chunk
            if current_sentences and (current_tokens + sent_tokens > self.chunk_size):
                # Emit current chunk
                chunk_record = self._build_chunk_record(
                    current_sentences=current_sentences,
                    chunk_idx=chunk_idx,
                    doc_code=doc_code,
                    doc_meta=doc_meta,
                    has_overlap=has_overlap
                )
                chunks.append(chunk_record)
                chunk_idx += 1

                # Calculate overlap: retain trailing sentences up to overlap tokens
                overlap_sentences: List[Dict[str, Any]] = []
                overlap_tokens_count = 0

                for s_rev in reversed(current_sentences):
                    if overlap_tokens_count + s_rev["tokens"] <= self.overlap:
                        overlap_sentences.insert(0, s_rev)
                        overlap_tokens_count += s_rev["tokens"]
                    else:
                        break

                current_sentences = list(overlap_sentences)
                current_tokens = overlap_tokens_count
                has_overlap = len(current_sentences) > 0

            # Append current sentence
            current_sentences.append(sent)
            current_tokens += sent_tokens
            i += 1

        # Emit final remaining chunk
        if current_sentences:
            # If the last chunk is too small and we already have prior chunks, merge if possible
            if current_tokens < self.min_chunk_size and chunks:
                last_chunk = chunks[-1]
                combined_tokens = last_chunk["token_count"] + current_tokens
                if combined_tokens <= int(self.chunk_size * 1.25):
                    # Safely merge into previous chunk
                    extra_text = " " + " ".join(s["text"] for s in current_sentences)
                    last_chunk["text"] += extra_text
                    last_chunk["token_count"] = self.tokenizer.count_tokens(last_chunk["text"])
                    last_chunk["char_count"] = len(last_chunk["text"])
                    last_chunk["page_end"] = current_sentences[-1]["page"]
                else:
                    chunks.append(self._build_chunk_record(
                        current_sentences, chunk_idx, doc_code, doc_meta, has_overlap
                    ))
            else:
                chunks.append(self._build_chunk_record(
                    current_sentences, chunk_idx, doc_code, doc_meta, has_overlap
                ))

        return chunks

    def _build_chunk_record(
        self,
        current_sentences: List[Dict[str, Any]],
        chunk_idx: int,
        doc_code: str,
        doc_meta: Dict[str, Any],
        has_overlap: bool
    ) -> Dict[str, Any]:
        """Construct the standardized chunk record dictionary"""
        combined_text = " ".join(s["text"] for s in current_sentences)
        token_count = sum(s["tokens"] for s in current_sentences)
        start_page = current_sentences[0]["page"]
        end_page = current_sentences[-1]["page"]

        chunk_id = f"{doc_code}_chunk_{chunk_idx:04d}"

        return {
            "id": chunk_id,
            "text": combined_text,
            "doc_id": doc_code,
            "doc_type": doc_meta.get("doc_type", "OTHER"),
            "doc_category": doc_meta.get("doc_category", "Documentation"),
            "doc_title": doc_meta.get("doc_title", doc_code),
            "source_file": doc_meta.get("source_file", ""),
            "source_path": doc_meta.get("source_path", ""),
            "page_start": start_page,
            "page_end": end_page,
            "chunk_index": chunk_idx,
            "token_count": token_count,
            "char_count": len(combined_text),
            "has_overlap": has_overlap,
            "sentence_count": len(current_sentences)
        }


# ============================================================================
# PDF READER & DIRECTORY PROCESSING
# ============================================================================

def extract_pages_from_pdf(pdf_path: Path) -> List[Tuple[int, str]]:
    """Extract (page_num, text) from a PDF file using PyPDF2 or pypdf"""
    pages = []
    try:
        try:
            import PyPDF2
            reader_class = PyPDF2.PdfReader
        except ImportError:
            import pypdf
            reader_class = pypdf.PdfReader

        with open(pdf_path, "rb") as f:
            reader = reader_class(f)
            for idx, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append((idx, text))
                except Exception as page_err:
                    logger.warning(f"Failed extracting page {idx} from {pdf_path.name}: {page_err}")
    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {e}")

    return pages


def find_pdf_files(directory: Path) -> List[Path]:
    """Find all PDF files in directory and subdirectories"""
    if not directory.exists() or not directory.is_dir():
        logger.error(f"Target directory does not exist: {directory}")
        return []
    pdfs = list(directory.rglob("*.pdf")) + list(directory.rglob("*.PDF"))
    # Deduplicate and sort
    return sorted(list({p.resolve() for p in pdfs}))


def resolve_data_directory(user_specified: Optional[str] = None) -> Path:
    """
    Resolve the technical document directory.
    Priority order:
    1. CLI user-specified path
    2. /opt/undata (standard AWS location per setup.sh)
    3. /undata (alternative AWS root location)
    4. undata (relative directory)
    5. Local project fallback: /home/kaushal/Documents/Gigavolt/Unstructured Data
    """
    if user_specified:
        p = Path(user_specified)
        if p.exists():
            return p
        logger.warning(f"Specified path '{user_specified}' not found, falling back to candidates.")

    candidates = [
        Path("/opt/undata"),
        Path("/undata"),
        Path("undata"),
        Path("./undata"),
        Path("/home/kaushal/Documents/Gigavolt/Unstructured Data"),
        Path("./Unstructured Data")
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    # Default to /opt/undata as per AWS setup
    return Path("/opt/undata")


def process_directory(
    target_dir: Path,
    chunk_size: int = 384,
    overlap: int = 64
) -> List[Dict[str, Any]]:
    """Process all PDF files in directory and return all chunks"""
    pdf_files = find_pdf_files(target_dir)
    if not pdf_files:
        logger.error(f"No PDF files found in {target_dir}")
        return []

    logger.info(f"Discovered {len(pdf_files)} PDF files in: {target_dir}")
    logger.info(f"Chunking parameters: target_tokens={chunk_size}, overlap_tokens={overlap}")

    chunker = DocumentChunker(chunk_size=chunk_size, overlap=overlap)
    all_chunks = []

    for idx, pdf_path in enumerate(pdf_files, start=1):
        filename = pdf_path.name
        doc_meta = parse_gigavolt_filename(filename)
        doc_meta["source_file"] = filename
        doc_meta["source_path"] = str(pdf_path)

        pages = extract_pages_from_pdf(pdf_path)
        if not pages:
            logger.warning(f"[{idx}/{len(pdf_files)}] No text extracted from {filename}")
            continue

        doc_chunks = chunker.chunk_document_pages(pages, doc_metadata=doc_meta)
        all_chunks.extend(doc_chunks)

        total_tokens = sum(c["token_count"] for c in doc_chunks)
        logger.info(
            f"[{idx}/{len(pdf_files)}] {filename[:40]:<40} | "
            f"Pages: {len(pages):>2} | Chunks: {len(doc_chunks):>3} | Tokens: {total_tokens:>5}"
        )

    logger.info(f"Total chunks generated across all documents: {len(all_chunks)}")
    return all_chunks


def compute_chunking_statistics(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics for generated chunks"""
    if not chunks:
        return {}

    token_counts = [c["token_count"] for c in chunks]
    doc_types: Dict[str, int] = {}
    for c in chunks:
        dt = c.get("doc_type", "OTHER")
        doc_types[dt] = doc_types.get(dt, 0) + 1

    token_counts.sort()
    n = len(token_counts)

    return {
        "total_chunks": n,
        "token_min": token_counts[0],
        "token_max": token_counts[-1],
        "token_mean": round(sum(token_counts) / n, 1),
        "token_p50": token_counts[n // 2],
        "token_p90": token_counts[int(n * 0.9)],
        "token_p95": token_counts[int(n * 0.95)],
        "doc_type_distribution": doc_types
    }


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Gigavolt Technical Documentation Chunking Engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="/opt/undata",
        help="Path to directory containing Gigavolt PDF documentation"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=384,
        help="Maximum chunk size in tokens (recommended: 256-512)"
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=64,
        help="Token overlap between adjacent chunks"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="gigavolt_chunks.json",
        help="Output path for JSON chunks file"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print detailed statistical distribution of chunks"
    )

    args = parser.parse_args()

    target_dir = resolve_data_directory(args.data_dir)
    logger.info(f"Using technical data directory: {target_dir}")

    chunks = process_directory(
        target_dir=target_dir,
        chunk_size=args.chunk_size,
        overlap=args.overlap
    )

    if not chunks:
        logger.error("No chunks produced. Exiting.")
        sys.exit(1)

    # Save output
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(chunks)} chunks to: {output_path.resolve()}")

    # Print summary statistics
    stats = compute_chunking_statistics(chunks)
    print("\n" + "=" * 60)
    print("CHUNKING SUMMARY & TOKEN DISTRIBUTION")
    print("=" * 60)
    print(f"Total Chunks Generated : {stats['total_chunks']}")
    print(f"Token Length Min       : {stats['token_min']}")
    print(f"Token Length Mean      : {stats['token_mean']}")
    print(f"Token Length Median    : {stats['token_p50']}")
    print(f"Token Length 90th %ile : {stats['token_p90']}")
    print(f"Token Length 95th %ile : {stats['token_p95']}")
    print(f"Token Length Max       : {stats['token_max']}")
    print("\nDocument Type Breakdown:")
    for dt, cnt in sorted(stats['doc_type_distribution'].items()):
        print(f"  • {dt:<6}: {cnt:>4} chunks")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

