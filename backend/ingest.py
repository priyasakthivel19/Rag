"""Build the FAISS index from PDFs in ./data   ->   python ingest.py"""

from src.ingestion import build_index, collect_pdfs

if __name__ == "__main__":
    pdfs = collect_pdfs()
    if not pdfs:
        raise SystemExit("No PDFs found in ./data - add some and run again.")
    print(f"Found {len(pdfs)} PDF(s). Parsing, chunking, embedding ...")
    stats = build_index()
    print(f"Done: {stats['files']} files | {stats['pages']} pages | {stats['chunks']} chunks")
    if stats["pages"] == 0:
        print("Warning: no text extracted. Scanned PDFs need OCR.")
