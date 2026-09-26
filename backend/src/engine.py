"""
ONLINE PHASE - Query pipeline (runs for every question)

  1. User question
  2. Embed the question
  3. Similarity search in FAISS
  4. Select top-K chunks
  5. Build prompt + context
  6. Generate answer (Groq)

If no chunk is similar enough (score < MIN_SCORE), the PDFs are ignored and
the LLM answers from general knowledge - so ANY question can be asked.
"""

import os
import time

from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.core.llms import ChatMessage
from llama_index.vector_stores.faiss import FaissVectorStore

from . import ingestion
from .config import (
    GENERAL_SYSTEM,
    HISTORY_TURNS,
    MIN_SCORE,
    RAG_SYSTEM,
    STORAGE_DIR,
    TOP_K,
    init_settings,
)


class RAGEngine:
    def __init__(self):
        init_settings()
        self.index = None
        self.load()

    def load(self) -> None:
        self.index = None
        if os.path.isdir(STORAGE_DIR) and os.listdir(STORAGE_DIR):
            try:
                vector_store = FaissVectorStore.from_persist_dir(STORAGE_DIR)
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store, persist_dir=STORAGE_DIR
                )
                self.index = load_index_from_storage(storage_context=storage_context)
            except Exception as e:
                print(f"[warn] could not load index ({e}). Rebuild it.")

    def rebuild(self) -> dict:
        stats = ingestion.build_index()
        self.load()
        return stats

    @property
    def has_index(self) -> bool:
        return self.index is not None

    def _retrieve(self, question: str, top_k: int):
        if self.index is None:
            return []
        return self.index.as_retriever(similarity_top_k=top_k).retrieve(question)

    def ask(
        self,
        question: str,
        history: list[dict] | None = None,
        min_score: float = MIN_SCORE,
        top_k: int = TOP_K,
    ) -> dict:
        t0 = time.time()
        nodes = self._retrieve(question, top_k)
        good = [n for n in nodes if (n.score or 0) >= min_score]

        if good:
            context = "\n\n".join(
                f"[{n.metadata.get('source')} | page {n.metadata.get('page')}]\n{n.get_content()}"
                for n in good
            )
            system = RAG_SYSTEM
            user_msg = f"Document excerpts:\n{context}\n\nQuestion: {question}"
        else:
            system = GENERAL_SYSTEM
            user_msg = question

        messages = [ChatMessage(role="system", content=system)]
        for m in (history or [])[-HISTORY_TURNS:]:
            messages.append(ChatMessage(role=m["role"], content=m["content"]))
        messages.append(ChatMessage(role="user", content=user_msg))

        reply = Settings.llm.chat(messages)

        def as_dict(n):
            return {
                "source": n.metadata.get("source"),
                "page": n.metadata.get("page"),
                "score": round(float(n.score or 0), 3),
            }

        return {
            "answer": reply.message.content,
            "used_docs": bool(good),
            "sources": [as_dict(n) for n in good],
            "retrieved": [as_dict(n) for n in nodes],
            "latency": round(time.time() - t0, 2),
        }

    def ask_stream(
        self,
        question: str,
        history: list[dict] | None = None,
        min_score: float = MIN_SCORE,
        top_k: int = TOP_K,
    ):
        """
        Same as ask(), but yields events as the LLM generates the answer:
          {"type": "meta",  "used_docs", "sources", "retrieved"}   - sent first
          {"type": "token", "text"}                                 - one per chunk
          {"type": "done",  "answer", "latency"}                    - sent last
          {"type": "error", "message"}                              - on failure
        """
        t0 = time.time()

        def as_dict(n):
            return {
                "source": n.metadata.get("source"),
                "page": n.metadata.get("page"),
                "score": round(float(n.score or 0), 3),
            }

        try:
            nodes = self._retrieve(question, top_k)
            good = [n for n in nodes if (n.score or 0) >= min_score]

            if good:
                context = "\n\n".join(
                    f"[{n.metadata.get('source')} | page {n.metadata.get('page')}]\n{n.get_content()}"
                    for n in good
                )
                system = RAG_SYSTEM
                user_msg = f"Document excerpts:\n{context}\n\nQuestion: {question}"
            else:
                system = GENERAL_SYSTEM
                user_msg = question

            messages = [ChatMessage(role="system", content=system)]
            for m in (history or [])[-HISTORY_TURNS:]:
                messages.append(ChatMessage(role=m["role"], content=m["content"]))
            messages.append(ChatMessage(role="user", content=user_msg))

            yield {
                "type": "meta",
                "used_docs": bool(good),
                "sources": [as_dict(n) for n in good],
                "retrieved": [as_dict(n) for n in nodes],
            }

            full = ""
            for chunk in Settings.llm.stream_chat(messages):
                delta = chunk.delta or ""
                if delta:
                    full += delta
                    yield {"type": "token", "text": delta}

            yield {"type": "done", "answer": full, "latency": round(time.time() - t0, 2)}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
