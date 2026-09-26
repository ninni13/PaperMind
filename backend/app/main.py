import hashlib
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.pdf_utils import extract_pages_from_pdf
from app.chunking import split_pages
from app.embedding import create_embedding, create_embeddings
from app.database import get_connection
from app.repository import create_paper, create_chunks, search_chunks, get_papers, get_chunk, get_paper_by_hash, delete_paper
from app.ask_service import answer_question
from app.rag import CHAT_MODEL
from pydantic import BaseModel, ValidationError
from openai import OpenAIError
from starlette.concurrency import run_in_threadpool
from app.overview import OverviewResponse
from app.overview_service import OverviewGenerationError, overview_model
from app.overview_repository import (
    initialize_overview_storage, get_overview, create_overview,
    PaperNotFound, OverviewBusy, PaperHasNoText,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(initialize_overview_storage)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Research Paper RAG API",
    description="RAG backend for querying research papers",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://papermind-beta.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    paper_id: int
    question: str

@app.get("/")
def root():
    return {"message": "Research Paper RAG API is running"}


@app.get("/test-embedding")
def test_embedding():
    embedding = create_embedding(
        "Skeleton-based action recognition"
    )

    return {
        "dimensions": len(embedding),
        "preview": embedding[:10]
    }

@app.get("/test-database")
def test_database():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()

    return {
        "status": "connected",
        "database": version[0]
    }

@app.get("/papers")
def list_papers():
    return get_papers()

@app.get("/papers/{paper_id}/chunks/{chunk_index}")
def read_chunk(paper_id: int, chunk_index: int):
    chunk = get_chunk(paper_id, chunk_index)

    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail="Chunk not found",
        )

    return chunk

@app.post("/papers/upload")
async def upload_paper(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported.",
        )

    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_paper = get_paper_by_hash(file_hash)

    if existing_paper:
        return {
            "paper_id": existing_paper["id"],
            "filename": existing_paper["filename"],
            "status": "already_indexed",
        }

    # 1. Extract
    pages = extract_pages_from_pdf(file_bytes)

    # 2. Chunk
    chunks = split_pages(pages)

    # 3. Save paper
    paper_id = create_paper(file.filename, file_hash)

    chunk_texts = [
        chunk["content"]
        for chunk in chunks
    ]

    # 4. Batch embedding
    embeddings = create_embeddings(chunk_texts)

    # 5. Batch save chunks
    create_chunks(
        paper_id=paper_id,
        chunks=chunks,
        embeddings=embeddings,
    )

    return {
        "paper_id": paper_id,
        "filename": file.filename,
        "pages": len(pages),
        "characters": sum(
            len(page["text"])
            for page in pages
        ),
        "total_chunks": len(chunks),
        "status": "indexed",
    }

@app.post("/papers/search")
def search_paper(request: SearchRequest):

    # Turn the user's question into an embedding
    query_embedding = create_embedding(request.question)

    # Find the most relevant chunks
    results = search_chunks(
        paper_id=request.paper_id,
        query_embedding=query_embedding,
        limit=5,
    )

    return {
        "question": request.question,
        "results": results,
    }

@app.post("/papers/ask")
def ask_paper(request: SearchRequest):

    return answer_question(request.paper_id, request.question)

@app.delete("/papers/{paper_id}")
def remove_paper(paper_id: int):
    deleted = delete_paper(paper_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Paper not found",
        )

    return {
        "paper_id": paper_id,
        "status": "deleted",
    }

@app.get("/papers/{paper_id}/overview", response_model=OverviewResponse)
def read_paper_overview(paper_id: int):
    try:
        return get_overview(paper_id)
    except PaperNotFound:
        raise HTTPException(status_code=404, detail="Paper not found")


@app.post("/papers/{paper_id}/overview", response_model=OverviewResponse)
def generate_paper_overview(paper_id: int):
    try:
        return create_overview(paper_id)
    except PaperNotFound:
        raise HTTPException(status_code=404, detail="Paper not found")
    except OverviewBusy:
        raise HTTPException(
            status_code=409,
            detail="An overview is already being generated. Wait a moment, then check again.",
        )
    except PaperHasNoText:
        raise HTTPException(status_code=422, detail="This paper has no readable indexed text.")
    except (OpenAIError, OverviewGenerationError, ValidationError):
        logging.getLogger(__name__).exception("Overview generation failed for paper %s", paper_id)
        raise HTTPException(
            status_code=502,
            detail="Overview generation failed. No overview was saved. Please try again.",
        )


@app.get("/models")
def model_info():
    """Current generation configuration, not provenance for previously cached answers."""
    return {"provider": "OpenAI", "ask_paper": CHAT_MODEL, "overview": overview_model()}
