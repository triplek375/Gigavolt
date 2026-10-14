"""
Simple PDF Vector Search - Multi-Document Version
Extract text from all PDFs in a directory, chunk, store in vector DB, and search
pip install chromadb sentence-transformers pypdf2
"""

import os
import re
from typing import List, Dict
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

# Install required packages:
# pip install chromadb sentence-transformers pypdf2

try:
    import PyPDF2
except ImportError:
    print("Installing PyPDF2...")
    os.system("pip install PyPDF2")
    import PyPDF2


# ============================================================================
# PDF EXTRACTION
# ============================================================================

def find_pdfs_in_directory(directory: str) -> List[str]:
    """Find all PDF files in a directory"""
    pdf_files = []
    directory = Path(directory)
    
    if not directory.exists():
        print(f"❌ Error: Directory not found: {directory}")
        return []
    
    for file_path in directory.rglob("*.pdf"):
        pdf_files.append(str(file_path))
    
    # Also check for .PDF extension
    for file_path in directory.rglob("*.PDF"):
        pdf_files.append(str(file_path))
    
    return sorted(pdf_files)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                text += page_text
            
            return text
    except Exception as e:
        print(f"  ⚠️  Error reading {pdf_path}: {e}")
        return ""


def process_all_pdfs(pdf_paths: List[str]) -> Dict[str, str]:
    """Extract text from multiple PDF files"""
    print(f"\n{'='*60}")
    print(f"Processing {len(pdf_paths)} PDF files")
    print(f"{'='*60}\n")
    
    documents = {}
    
    for i, pdf_path in enumerate(pdf_paths, 1):
        filename = os.path.basename(pdf_path)
        print(f"[{i}/{len(pdf_paths)}] Extracting: {filename}")
        
        text = extract_text_from_pdf(pdf_path)
        
        if text.strip():
            documents[pdf_path] = text
            print(f"  ✓ Extracted {len(text)} characters")
        else:
            print(f"  ⚠️  No text extracted")
    
    print(f"\n✓ Successfully processed {len(documents)}/{len(pdf_paths)} PDFs\n")
    return documents


# ============================================================================
# CHUNKING METHODS
# ============================================================================

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


def chunk_by_paragraph(text: str) -> List[Dict]:
    """Chunk text by paragraphs (double newlines)"""
    # Split by double newlines or multiple spaces
    paragraphs = re.split(r'\n\s*\n', text)
    
    chunks = []
    char_position = 0
    
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if para and len(para) > 20:  # Skip very short paragraphs
            chunks.append({
                "id": f"para_{i}",
                "text": para,
                "method": "paragraph",
                "size": len(para),
                "char_start": char_position,
                "char_end": char_position + len(para)
            })
        char_position += len(para) + 2  # Account for paragraph breaks
    
    return chunks


def chunk_documents(documents: Dict[str, str], method: str = "fixed") -> List[Dict]:
    """Chunk all documents using specified method"""
    print(f"Chunking documents using '{method}' method...")
    
    all_chunks = []
    
    for pdf_path, text in documents.items():
        filename = os.path.basename(pdf_path)
        
        if method == "fixed":
            chunks = chunk_by_fixed_size(text, chunk_size=500, overlap=50)
        elif method == "paragraph":
            chunks = chunk_by_paragraph(text)
        elif method == "both":
            chunks = chunk_by_fixed_size(text, chunk_size=500, overlap=50)
            chunks += chunk_by_paragraph(text)
        else:
            chunks = chunk_by_fixed_size(text, chunk_size=500, overlap=50)
        
        # Add source document info to each chunk
        for chunk in chunks:
            chunk["source_file"] = filename
            chunk["source_path"] = pdf_path
            chunk["id"] = f"{filename}_{chunk['id']}"
        
        all_chunks.extend(chunks)
        print(f"  {filename}: {len(chunks)} chunks")
    
    print(f"\n✓ Total chunks created: {len(all_chunks)}\n")
    return all_chunks


# ============================================================================
# VECTOR DATABASE
# ============================================================================

class SimpleVectorDB:
    """Simple vector database wrapper"""
    
    def __init__(self, collection_name: str = "pdf_docs", reset: bool = True):
        print("Initializing vector database...")
        self.client = chromadb.PersistentClient(path="./simple_vectordb")
        
        # Reset collection if requested
        if reset:
            try:
                self.client.delete_collection(name=collection_name)
                print("  Cleared existing collection")
            except:
                pass
        
        self.collection = self.client.create_collection(name=collection_name)
        
        print("Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        print("✓ Vector database ready\n")
    
    def add_chunks(self, chunks: List[Dict]):
        """Add chunks to the database"""
        print(f"Adding {len(chunks)} chunks to database...")
        
        texts = [c["text"] for c in chunks]
        ids = [c["id"] for c in chunks]
        metadatas = [{
            "method": c["method"],
            "size": c["size"],
            "source_file": c["source_file"],
            "source_path": c["source_path"]
        } for c in chunks]
        
        # Generate embeddings in batches
        print("Generating embeddings...")
        batch_size = 32
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embedder.encode(batch, show_progress_bar=False)
            all_embeddings.extend(embeddings.tolist())
            print(f"  Progress: {min(i + batch_size, len(texts))}/{len(texts)}")
        
        # Add to database
        print("Storing in vector database...")
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=all_embeddings,
            metadatas=metadatas
        )
        
        print(f"✓ Added {len(chunks)} chunks\n")
    
    def search(self, query: str, n_results: int = 5, filter_file: str = None) -> Dict:
        """Search the database"""
        # Generate query embedding
        query_embedding = self.embedder.encode(query)
        
        # Build filter if specified
        where = None
        if filter_file:
            where = {"source_file": filter_file}
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where
        )
        
        return results
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        all_data = self.collection.get()
        
        # Count documents by source file
        source_files = {}
        for metadata in all_data['metadatas']:
            source = metadata.get('source_file', 'Unknown')
            source_files[source] = source_files.get(source, 0) + 1
        
        return {
            "total_chunks": len(all_data['ids']),
            "source_files": source_files,
            "num_documents": len(source_files)
        }


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║     Simple PDF Vector Search - Multi-Document            ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Get directory path
    directory = input("Enter directory path (or press Enter for current directory): ").strip()
    
    if not directory:
        directory = "."
    
    # Remove quotes if user wrapped path in quotes
    directory = directory.strip('"').strip("'")
    
    # Find all PDFs
    pdf_paths = find_pdfs_in_directory(directory)
    
    if not pdf_paths:
        print(f"\n❌ No PDF files found in: {directory}")
        return
    
    print(f"\nFound {len(pdf_paths)} PDF files:")
    for i, pdf_path in enumerate(pdf_paths, 1):
        print(f"  {i}. {os.path.basename(pdf_path)}")
    
    # Extract text from all PDFs
    documents = process_all_pdfs(pdf_paths)
    
    if not documents:
        print("❌ No text extracted from any PDFs")
        return
    
    # Choose chunking method
    print("\nWhich chunking method do you want to use?")
    print("  [1] Fixed size (500 chars with 50 char overlap)")
    print("  [2] Paragraph-based")
    print("  [3] Both (combined)")
    
    choice = input("\nEnter choice (1, 2, or 3) [default: 1]: ").strip()
    
    if choice == "2":
        method = "paragraph"
    elif choice == "3":
        method = "both"
    else:
        method = "fixed"
    
    # Chunk all documents
    chunks = chunk_documents(documents, method=method)
    
    # Initialize vector database
    db = SimpleVectorDB()
    
    # Add chunks to database
    db.add_chunks(chunks)
    
    # Show statistics
    stats = db.get_stats()
    print("="*60)
    print("DATABASE STATISTICS")
    print("="*60)
    print(f"Total chunks: {stats['total_chunks']}")
    print(f"Documents indexed: {stats['num_documents']}")
    print("\nChunks per document:")
    for source_file, count in stats['source_files'].items():
        print(f"  {source_file}: {count} chunks")
    
    # Query loop
    print("\n" + "="*60)
    print("Database ready! Enter queries to search")
    print("="*60)
    print("\nCommands:")
    print("  - Type a query to search all documents")
    print("  - Type 'filter:filename.pdf query text' to search specific file")
    print("  - Type 'stats' to see database statistics")
    print("  - Type 'list' to list all documents")
    print("  - Type 'quit' to exit")
    print("="*60)
    
    while True:
        print()
        query = input("🔍 Query: ").strip()
        
        if query.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Goodbye!")
            break
        
        if not query:
            continue
        
        if query.lower() == 'stats':
            stats = db.get_stats()
            print(f"\nTotal chunks: {stats['total_chunks']}")
            print(f"Documents: {stats['num_documents']}")
            for source_file, count in stats['source_files'].items():
                print(f"  {source_file}: {count} chunks")
            continue
        
        if query.lower() == 'list':
            stats = db.get_stats()
            print("\nIndexed documents:")
            for i, source_file in enumerate(stats['source_files'].keys(), 1):
                print(f"  {i}. {source_file}")
            continue
        
        # Check for filter
        filter_file = None
        if query.startswith('filter:'):
            parts = query.split(' ', 1)
            if len(parts) == 2:
                filter_file = parts[0].replace('filter:', '')
                query = parts[1]
                print(f"(Filtering by: {filter_file})")
        
        # Search
        try:
            results = db.search(query, n_results=5, filter_file=filter_file)
            
            if not results['ids'][0]:
                print("\n⚠️  No results found")
                continue
            
            # Display results
            print(f"\n{'='*60}")
            print(f"Top {len(results['ids'][0])} Results")
            print(f"{'='*60}")
            
            for i in range(len(results['ids'][0])):
                doc_id = results['ids'][0][i]
                document = results['documents'][0][i]
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                similarity = 1 - distance
                
                print(f"\n[{i+1}] 📄 {metadata['source_file']}")
                print(f"    Similarity: {similarity:.3f} | Method: {metadata['method']} | Size: {metadata['size']} chars")
                print(f"    {document[:250]}{'...' if len(document) > 250 else ''}")
        
        except Exception as e:
            print(f"\n❌ Search error: {e}")


# ============================================================================
# ALTERNATIVE: BATCH MODE
# ============================================================================

def batch_mode(directory: str, queries: List[str], method: str = "fixed"):
    """Run in batch mode with predefined queries"""
    print(f"\n{'='*60}")
    print(f"BATCH MODE: Processing directory '{directory}'")
    print(f"{'='*60}\n")
    
    # Find and process PDFs
    pdf_paths = find_pdfs_in_directory(directory)
    
    if not pdf_paths:
        print(f"❌ No PDFs found in {directory}")
        return
    
    documents = process_all_pdfs(pdf_paths)
    chunks = chunk_documents(documents, method=method)
    
    # Setup database
    db = SimpleVectorDB()
    db.add_chunks(chunks)
    
    # Show stats
    stats = db.get_stats()
    print(f"Indexed {stats['num_documents']} documents with {stats['total_chunks']} chunks\n")
    
    # Run queries
    print("="*60)
    print("BATCH QUERY RESULTS")
    print("="*60)
    
    for query in queries:
        print(f"\n📋 Query: '{query}'")
        print("-"*60)
        
        results = db.search(query, n_results=3)
        
        for i in range(len(results['ids'][0])):
            document = results['documents'][0][i]
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]
            similarity = 1 - distance
            
            print(f"\n  [{i+1}] {metadata['source_file']} (similarity: {similarity:.3f})")
            print(f"      {document[:200]}...")


# ============================================================================
# QUICK START MODE
# ============================================================================

def quick_start(directory: str = "."):
    """Quick start: automatically process directory and start querying"""
    print("""
╔══════════════════════════════════════════════════════════╗
║          Quick Start Mode - Auto-processing              ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Find PDFs
    pdf_paths = find_pdfs_in_directory(directory)
    
    if not pdf_paths:
        print(f"❌ No PDFs found in {directory}")
        return
    
    print(f"\nAuto-processing {len(pdf_paths)} PDFs from: {directory}\n")
    
    # Process everything automatically
    documents = process_all_pdfs(pdf_paths)
    chunks = chunk_documents(documents, method="fixed")
    
    db = SimpleVectorDB()
    db.add_chunks(chunks)
    
    stats = db.get_stats()
    print("="*60)
    print(f"✓ Ready! Indexed {stats['num_documents']} documents ({stats['total_chunks']} chunks)")
    print("="*60)
    
    # Start query loop
    print("\nEnter queries to search (or 'quit' to exit):\n")
    
    while True:
        query = input("🔍 Query: ").strip()
        
        if query.lower() in ['quit', 'exit', 'q']:
            break
        
        if not query:
            continue
        
        results = db.search(query, n_results=3)
        
        print(f"\n{'='*60}")
        for i in range(len(results['ids'][0])):
            document = results['documents'][0][i]
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]
            
            print(f"\n[{i+1}] 📄 {metadata['source_file']} (score: {1-distance:.3f})")
            print(f"    {document[:200]}...")
        print("="*60 + "\n")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == "--quick" or arg == "-q":
            # Quick start mode with current directory
            directory = sys.argv[2] if len(sys.argv) > 2 else "."
            quick_start(directory)
        
        elif arg == "--batch" or arg == "-b":
            # Batch mode
            if len(sys.argv) < 4:
                print("Usage: python script.py --batch <directory> <query1> <query2> ...")
            else:
                directory = sys.argv[2]
                queries = sys.argv[3:]
                batch_mode(directory, queries)
        
        elif arg == "--help" or arg == "-h":
            print("""
╔══════════════════════════════════════════════════════════╗
║     Simple PDF Vector Search - Multi-Document            ║
╚══════════════════════════════════════════════════════════╝

USAGE:
  python script.py [options]

OPTIONS:
  (no args)              Interactive mode - prompts for directory
  --quick, -q [dir]      Quick start - auto-process directory (default: current)
  --batch, -b <dir> <q1> <q2> ...
                         Batch mode - process directory and run queries
  --help, -h             Show this help message

EXAMPLES:
  # Interactive mode - will prompt for directory
  python script.py

  # Quick start with current directory
  python script.py --quick

  # Quick start with specific directory
  python script.py --quick ./my_pdfs

  # Batch mode with queries
  python script.py --batch ./docs "What is the main topic?" "How does it work?"

QUERY COMMANDS (in interactive mode):
  <your query>           Search all documents
  filter:file.pdf query  Search only in specific file
  stats                  Show database statistics
  list                   List all indexed documents
  quit                   Exit the program

FEATURES:
  ✓ Automatically finds all PDFs in directory
  ✓ Extracts text from all PDFs
  ✓ Chunks by fixed size or paragraphs
  ✓ Stores in ChromaDB vector database
  ✓ Semantic search with similarity scores
  ✓ Filter by specific document
  ✓ Fast sub-second queries

REQUIREMENTS:
  pip install chromadb sentence-transformers pypdf2
            """)
        
        else:
            # Treat as directory path
            directory = arg
            print(f"Processing directory: {directory}\n")
            quick_start(directory)
    
    else:
        # Default: Interactive mode
        main()
