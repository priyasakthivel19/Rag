"""Central configuration + one-time model setup (LLM, embeddings, chunker)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---- folders ----
DATA_DIR = str(BASE_DIR / "data")        # PDFs live here
STORAGE_DIR = str(BASE_DIR / "storage")  # FAISS index + metadata are saved here

# ---- models ----
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# ---- retrieval / chunking ----
TOP_K = int(os.getenv("TOP_K", "4"))                # chunks retrieved per question
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.55"))   # cosine-similarity cut-off for using PDFs
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))    # bge-small reads max ~512 tokens
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))
HISTORY_TURNS = 6                                    # last N chat messages sent to the LLM

# ---- prompts ----
GENERAL_SYSTEM = (
    "You are a friendly, knowledgeable AI assistant. Answer any question clearly "
    "and accurately. If you are not sure about something, say so honestly instead "
    "of guessing. Reply in the same language the user writes in "
    "(English, Tamil, or Tanglish)."
)

RAG_SYSTEM = (
    GENERAL_SYSTEM
    + "\n\nThe user's uploaded documents contain excerpts that look relevant to "
    "the question. Use them as the main basis of your answer and mention the "
    "source file and page when you use them. If the excerpts only partly answer "
    "the question, you may add general knowledge, but clearly say which part is "
    "NOT from the documents."
)

_initialised = False


def init_settings() -> None:
    """Configure LlamaIndex global Settings once (LLM + embeddings + chunker)."""
    global _initialised
    if _initialised:
        return

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY missing. Copy .env.example to .env and add your key.")

    from llama_index.core import Settings
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.llms.groq import Groq

    Settings.llm = Groq(model=GROQ_MODEL, api_key=api_key, temperature=0.3)
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)  # normalised vectors
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    _initialised = True


def embedding_dim() -> int:
    """Embedding size differs per model, so detect it instead of hard-coding."""
    from llama_index.core import Settings

    return len(Settings.embed_model.get_text_embedding("dimension probe"))
