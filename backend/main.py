"""
FastAPI backend - one command runs the whole app (API + web UI).

  uvicorn main:app --reload
  then open http://localhost:8000
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import MIN_SCORE, TOP_K
from src.engine import RAGEngine
from src.ingestion import collect_pdfs, delete_pdf, save_upload

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="RAG Chatbot API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

engine: RAGEngine | None = None


@app.on_event("startup")
def _startup():
    global engine
    engine = RAGEngine()  # loads existing storage/ index if present


# ------------------------------ schemas -------------------------------------
class AskRequest(BaseModel):
    question: str
    history: list[dict] = []
    min_score: float | None = None
    top_k: int | None = None


# ------------------------------ API routes -----------------------------------
@app.get("/api/status")
def status():
    return {
        "has_index": engine.has_index,
        "files": [Path(p).name for p in collect_pdfs()],
        "default_min_score": MIN_SCORE,
        "default_top_k": TOP_K,
    }


@app.post("/api/upload")
async def upload(files: list[UploadFile]):
    saved = []
    for f in files:
        data = await f.read()
        save_upload(f.filename, data)
        saved.append(f.filename)
    return {"saved": saved}


@app.delete("/api/files/{filename}")
def remove_file(filename: str):
    ok = delete_pdf(filename)
    if not ok:
        raise HTTPException(404, "File not found")
    return {"deleted": filename}


@app.post("/api/build_index")
def build_index():
    try:
        stats = engine.rebuild()
    except Exception as e:
        raise HTTPException(500, str(e))
    return stats


@app.post("/api/ask")
def ask(req: AskRequest):
    try:
        kwargs = {}
        if req.min_score is not None:
            kwargs["min_score"] = req.min_score
        if req.top_k is not None:
            kwargs["top_k"] = req.top_k
        return engine.ask(req.question, req.history, **kwargs)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/ask_stream")
def ask_stream(req: AskRequest):
    """Server-Sent Events: 'meta' event first, then 'token' events, then 'done' (or 'error')."""
    kwargs = {}
    if req.min_score is not None:
        kwargs["min_score"] = req.min_score
    if req.top_k is not None:
        kwargs["top_k"] = req.top_k

    def gen():
        for event in engine.ask_stream(req.question, req.history, **kwargs):
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------------ serve the frontend ---------------------------
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
