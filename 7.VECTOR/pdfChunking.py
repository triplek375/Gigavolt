#!/usr/bin/env python3
"""
Simplified PDF Vector Search
Reads all PDF files from the Unstructured Data folder unzipped in setup.sh (/opt/data), chunks using fixed-size chunking,
stores embeddings in ChromaDB, and provides an interactive query search.
"""

import os
from pathlib import Path
from typing import List, Dict

try:
    import PyPDF2
except ImportError:
    import sys
    print("PyPDF2 is required. Please install it with: pip install PyPDF2")
    sys.exit(1)

import chromadb
from sentence_transformers import SentenceTransformer


# ============================================================================
# PDF EXTRACTION & CHUNKING
# ============================================================================

def find_pdfs_in_directory(directory: Path) -> List[str]:
    """Find all PDF files in directory (case-insensitive)"""
    if not directory.exists():
        print(f"❌ Error: Directory not found: {directory}")
        return []
    
    pdf_files = list(directory.rglob("*.pdf")) + list(directory.rglob("*.PDF"))
    # Deduplicate and sort
    return sorted(list({str(p.resolve()) for p in pdf_files}))


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
    except Exception as e:
        print(f"  ⚠️  Error reading {pdf_path}: {e}")
        return ""


def chunk_by_fixed_size(text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
    """Chunk text by fixed character count with overlap"""
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
                "char_end": end
            })
            chunk_id += 1
        
        start = end - overlap
    
    return chunks


def process_and_chunk_pdfs(pdf_paths: List[str], chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
    """Extract text from PDFs and chunk using fixed-size chunking"""
    print(f"\n{'='*60}")
    print(f"Processing {len(pdf_paths)} PDF files (Fixed-size: {chunk_size} chars, Overlap: {overlap})")
    print(f"{'='*60}\n")
    
    all_chunks = []
    
    for i, pdf_path in enumerate(pdf_paths, 1):
        filename = os.path.basename(pdf_path)
        print(f"[{i}/{len(pdf_paths)}] Extracting: {filename}")
        
        text = extract_text_from_pdf(pdf_path)
        if not text.strip():
            print(f"  ⚠️  No text extracted from {filename}")
            continue
        
        chunks = chunk_by_fixed_size(text, chunk_size=chunk_size, overlap=overlap)
        for chunk in chunks:
            chunk["source_file"] = filename
            chunk["source_path"] = pdf_path
            chunk["id"] = f"{filename}_{chunk['id']}"
        
        all_chunks.extend(chunks)
        print(f"  ✓ Extracted {len(text)} chars -> {len(chunks)} chunks")
    
    print(f"\n✓ Total chunks created: {len(all_chunks)}\n")
    return all_chunks


# ============================================================================
# VECTOR DATABASE
# ============================================================================

class SimpleVectorDB:
    """Vector database wrapper using ChromaDB and SentenceTransformer"""
    
    def __init__(self, collection_name: str = "pdf_docs", db_path: str = "./simple_vectordb"):
        print("Initializing vector database...")
        self.client = chromadb.PersistentClient(path=db_path)
        
        try:
            self.client.delete_collection(name=collection_name)
            print("  Cleared existing collection")
        except Exception:
            pass
        
        self.collection = self.client.create_collection(name=collection_name)
        
        print("Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        print("✓ Vector database ready\n")
    
    def add_chunks(self, chunks: List[Dict], batch_size: int = 32):
        """Generate embeddings and store chunks in ChromaDB"""
        if not chunks:
            print("No chunks to add.")
            return
        
        print(f"Adding {len(chunks)} chunks to vector database...")
        texts = [c["text"] for c in chunks]
        ids = [c["id"] for c in chunks]
        metadatas = [{
            "method": c["method"],
            "size": c["size"],
            "source_file": c["source_file"],
            "source_path": c["source_path"]
        } for c in chunks]
        
        print("Generating embeddings...")
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embedder.encode(batch, show_progress_bar=False)
            all_embeddings.extend(embeddings.tolist())
            print(f"  Progress: {min(i + batch_size, len(texts))}/{len(texts)}")
        
        print("Storing in vector database...")
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=all_embeddings,
            metadatas=metadatas
        )
        print(f"✓ Stored {len(chunks)} chunks in vector database\n")
    
    def search(self, query: str, n_results: int = 5, filter_file: str = None) -> Dict:
        """Search the database using query text"""
        query_embedding = self.embedder.encode(query)
        where = {"source_file": filter_file} if filter_file else None
        
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where
        )
        return results
    
    def get_stats(self) -> Dict:
        """Get statistics about the indexed documents"""
        all_data = self.collection.get()
        source_files = {}
        for metadata in all_data.get('metadatas', []):
            source = metadata.get('source_file', 'Unknown')
            source_files[source] = source_files.get(source, 0) + 1
        
        return {
            "total_chunks": len(all_data.get('ids', [])),
            "source_files": source_files,
            "num_documents": len(source_files)
        }


# ============================================================================
# INTERACTIVE QUERY LOOP
# ============================================================================

def run_query_loop(db: SimpleVectorDB):
    """Run interactive query prompt"""
    stats = db.get_stats()
    print("="*60)
    print("DATABASE READY - ENTER QUERIES TO SEARCH")
    print("="*60)
    print(f"Indexed documents: {stats['num_documents']} ({stats['total_chunks']} chunks)")
    print("\nCommands:")
    print("  - Type a query to search across all PDF documents")
    print("  - Type 'filter:<filename.pdf> <query>' to search a specific file")
    print("  - Type 'stats' to view collection statistics")
    print("  - Type 'list' to view all indexed documents")
    print("  - Type 'quit' (or 'exit', 'q') to exit")
    print("="*60)
    
    while True:
        try:
            print()
            query = input("🔍 Query: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break
        
        if not query:
            continue
        
        if query.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Goodbye!")
            break
        
        if query.lower() == 'stats':
            current_stats = db.get_stats()
            print(f"\nTotal chunks: {current_stats['total_chunks']}")
            print(f"Documents: {current_stats['num_documents']}")
            for source_file, count in current_stats['source_files'].items():
                print(f"  {source_file}: {count} chunks")
            continue
        
        if query.lower() == 'list':
            current_stats = db.get_stats()
            print("\nIndexed documents:")
            for i, source_file in enumerate(current_stats['source_files'].keys(), 1):
                print(f"  {i}. {source_file}")
            continue
        
        # Check for optional filename filter
        filter_file = None
        if query.startswith('filter:'):
            parts = query.split(' ', 1)
            if len(parts) == 2:
                filter_file = parts[0].replace('filter:', '').strip()
                query = parts[1].strip()
                print(f"(Filtering by: {filter_file})")
        
        try:
            results = db.search(query, n_results=5, filter_file=filter_file)
            ids = results.get('ids', [[]])[0]
            if not ids:
                print("\n⚠️  No results found.")
                continue
            
            print(f"\n{'='*60}")
            print(f"Top {len(ids)} Results for: \"{query}\"")
            print(f"{'='*60}")
            
            for i in range(len(ids)):
                doc_text = results['documents'][0][i]
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                similarity = 1 - distance
                
                print(f"\n[{i+1}] 📄 {metadata['source_file']}")
                print(f"    Similarity: {similarity:.3f} | Size: {metadata['size']} chars")
                print(f"    {doc_text[:250]}{'...' if len(doc_text) > 250 else ''}")
        except Exception as e:
            print(f"\n❌ Search error: {e}")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    target_dir = Path('/opt/data/Unstructured Data/')
    print(f"Target PDF directory: {target_dir}")
    
    pdf_paths = find_pdfs_in_directory(target_dir)
    if not pdf_paths:
        print(f"❌ No PDF files found in {target_dir}")
        return
    
    print(f"Found {len(pdf_paths)} PDF files:")
    for i, p in enumerate(pdf_paths, 1):
        print(f"  {i}. {os.path.basename(p)}")
    
    # chunks = process_and_chunk_pdfs(pdf_paths, chunk_size=500, overlap=50)
    # if not chunks:
    #     print("❌ No chunks created from PDFs.")
    #     return
    
    # db_path = str(target_dir / "simple_vectordb")
    # db = SimpleVectorDB(db_path=db_path)
    # db.add_chunks(chunks)
    
    # run_query_loop(db)


if __name__ == "__main__":
    main()