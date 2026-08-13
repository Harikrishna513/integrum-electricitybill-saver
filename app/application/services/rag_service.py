"""
Official-source retrieval service — Milestone 20.
"""

from __future__ import annotations

from typing import Any

from app.infrastructure.rag.corpus import OfficialDocsCorpus, get_official_docs_corpus


class OfficialSourceRetriever:
    def __init__(self, corpus: OfficialDocsCorpus | None = None) -> None:
        self._corpus = corpus or get_official_docs_corpus()

    def search(self, query: str, *, top_k: int = 5) -> dict[str, Any]:
        hits = self._corpus.search(query, top_k=top_k)
        return {
            "query": query,
            "hit_count": len(hits),
            "sources_indexed": self._corpus.list_sources(),
            "hits": [
                {
                    "chunk_id": h.chunk.chunk_id,
                    "source_name": h.chunk.source_name,
                    "page_or_section": h.chunk.page_or_section,
                    "score": h.score,
                    "text": h.chunk.text,
                }
                for h in hits
            ],
            "disclaimer": (
                "Retrieved from local official/digest documents under data/Docs. "
                "Confirm against the latest BESCOM/KERC PDF before acting. "
                "RAG does not calculate ₹ amounts."
            ),
        }
