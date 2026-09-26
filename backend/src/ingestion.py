"""
OFFLINE PHASE - Ingestion pipeline

  1. Collect documents   -> collect_pdfs()
  2. Parse text          -> parse_pdf()         (PyMuPDF)
  3. Split into chunks   -> SentenceSplitter    (LlamaIndex, inside from_documents)
  4. Generate embeddings -> HuggingFace model   (inside from_documents)
  5. Store vectors + metadata -> FAISS + storage/ folder
"""

import glob
import os
import shutil

import faiss
import pymupdf  # PyMuPDF
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.vector_stores.faiss import FaissVectorStore

from .config import DATA_DIR, STORAGE_DIR, embedding_dim, init_settings


def collect_pdfs(folder: str = DATA_DIR) -> list[str]:
    """Step 1 - list every PDF in the data folder."""
    os.makedirs(folder, exist_ok=True)
    return sorted(glob.glob(os.path.join(folder, "*.pdf")))


def save_upload(filename: str, data: bytes, folder: str = DATA_DIR) -> str:
    """Save an uploaded file into the data folder."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, os.path.basename(filename))
    with open(path, "wb") as f:
        f.write(data)
    return path


def delete_pdf(filename: str, folder: str = DATA_DIR) -> bool:
    path = os.path.join(folder, os.path.basename(filename))
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def parse_pdf(path: str) -> list[Document]:
    """Step 2 - extract text page-by-page and keep source + page as metadata."""
    docs = []
    with pymupdf.open(path) as pdf:
        for page_no, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if not text:  # scanned / image-only page (needs OCR, skipped here)
                continue
            docs.append(
                Document(
                    text=text,
                    metadata={"source": os.path.basename(path), "page": page_no},
                    excluded_embed_metadata_keys=["source", "page"],
                )
            )
    return docs


def build_index() -> dict:
    """Run the whole ingestion pipeline. Returns {"files", "pages", "chunks"}."""
    init_settings()

    paths = collect_pdfs()
    docs: list[Document] = []
    for p in paths:
        docs.extend(parse_pdf(p))

    shutil.rmtree(STORAGE_DIR, ignore_errors=True)  # never keep a stale index
    if not docs:
        return {"files": len(paths), "pages": 0, "chunks": 0}

    # IndexFlatIP + normalised embeddings => score = cosine similarity (higher = better)
    vector_store = FaissVectorStore(faiss_index=faiss.IndexFlatIP(embedding_dim()))
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex.from_documents(docs, storage_context=storage_context, show_progress=True)
    index.storage_context.persist(persist_dir=STORAGE_DIR)
    return {"files": len(paths), "pages": len(docs), "chunks": len(index.docstore.docs)}
