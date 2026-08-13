"""
RAG API — Milestone 20 (official-source retrieval from data/Docs).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.application.services.rag_service import OfficialSourceRetriever
from app.infrastructure.rag.corpus import get_official_docs_corpus

router = APIRouter(prefix="/rag", tags=["rag"])


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


@router.get("/sources")
def list_sources() -> dict:
    corpus = get_official_docs_corpus()
    return {
        "milestone": 20,
        "docs_dir": str(corpus.docs_dir),
        "chunk_count": len(corpus.chunks),
        "sources": corpus.list_sources(),
        "message": (
            "Place official BESCOM/KERC PDFs and digests under data/Docs. "
            "VNM/GNM digests are preferred for policy Q&A."
        ),
    }


@router.post("/search")
def search_docs(body: RagSearchRequest) -> dict:
    result = OfficialSourceRetriever().search(body.query, top_k=body.top_k)
    return {"milestone": 20, **result}
