"""
Official-document RAG corpus — Milestone 20.

Indexes files under data/Docs (PDF, MD, TXT) into searchable chunks.
Retrieval is keyword/TF-IDF style (no external vector DB required for v1).

IMPORTANT
  RAG retrieves official text for explanation / policy Q&A.
  It must NOT invent tariff ₹ or eligibility approvals — engines still own money.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[3] / "data" / "Docs"


@dataclass(frozen=True)
class DocChunk:
    chunk_id: str
    source_path: str
    source_name: str
    page_or_section: str
    text: str


@dataclass
class RetrievalHit:
    chunk: DocChunk
    score: float


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9\u0C80-\u0CFF]+", text.lower())


class OfficialDocsCorpus:
    def __init__(self, docs_dir: Path | None = None) -> None:
        self.docs_dir = docs_dir or DEFAULT_DOCS_DIR
        self.chunks: list[DocChunk] = []
        self._df: dict[str, int] = {}
        self._chunk_tf: list[dict[str, float]] = []
        self._load()

    def _load(self) -> None:
        if not self.docs_dir.exists():
            return
        for path in sorted(self.docs_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("_extracted"):
                # Prefer original PDF; skip raw dump if digest/MD exist
                continue
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                self._ingest_pdf(path)
            elif suffix in {".md", ".txt"}:
                self._ingest_text(path)
        self._build_index()

    def _ingest_pdf(self, path: Path) -> None:
        try:
            reader = PdfReader(str(path))
        except Exception:  # noqa: BLE001
            return
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len(text) < 40:
                continue
            for j, piece in enumerate(self._split(text), start=1):
                self.chunks.append(
                    DocChunk(
                        chunk_id=f"{path.stem}-p{i}-{j}",
                        source_path=str(path),
                        source_name=path.name,
                        page_or_section=f"page {i}",
                        text=piece,
                    )
                )

    def _ingest_text(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        for j, piece in enumerate(self._split(text), start=1):
            self.chunks.append(
                DocChunk(
                    chunk_id=f"{path.stem}-s{j}",
                    source_path=str(path),
                    source_name=path.name,
                    page_or_section=f"section {j}",
                    text=piece,
                )
            )

    def _split(self, text: str, *, max_chars: int = 900) -> list[str]:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        chunks: list[str] = []
        buf = ""
        for p in paras:
            if len(buf) + len(p) + 1 <= max_chars:
                buf = f"{buf}\n{p}".strip()
            else:
                if buf:
                    chunks.append(buf)
                if len(p) <= max_chars:
                    buf = p
                else:
                    for i in range(0, len(p), max_chars):
                        chunks.append(p[i : i + max_chars])
                    buf = ""
        if buf:
            chunks.append(buf)
        return chunks

    def _build_index(self) -> None:
        self._df = {}
        self._chunk_tf = []
        for chunk in self.chunks:
            tokens = _tokenize(chunk.text)
            tf: dict[str, float] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0.0) + 1.0
            # normalize term frequency
            if tokens:
                n = float(len(tokens))
                tf = {k: v / n for k, v in tf.items()}
            self._chunk_tf.append(tf)
            for term in tf:
                self._df[term] = self._df.get(term, 0) + 1

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalHit]:
        if not self.chunks:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        n_docs = len(self.chunks)
        scores: list[tuple[int, float]] = []
        for idx, tf in enumerate(self._chunk_tf):
            score = 0.0
            for term in q_tokens:
                if term not in tf:
                    continue
                idf = math.log((1 + n_docs) / (1 + self._df.get(term, 0))) + 1.0
                score += tf[term] * idf
            # boost exact phrase / key policy terms
            lower = self.chunks[idx].text.lower()
            for boost_term in ("vnm", "gnm", "net metering", "virtual", "group net"):
                if boost_term in query.lower() and boost_term in lower:
                    score += 0.15
            if score > 0:
                scores.append((idx, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [
            RetrievalHit(chunk=self.chunks[i], score=round(s, 4))
            for i, s in scores[:top_k]
        ]

    def list_sources(self) -> list[dict]:
        seen: dict[str, int] = {}
        for c in self.chunks:
            seen[c.source_name] = seen.get(c.source_name, 0) + 1
        return [
            {"source_name": name, "chunk_count": count}
            for name, count in sorted(seen.items())
        ]


@lru_cache
def get_official_docs_corpus() -> OfficialDocsCorpus:
    return OfficialDocsCorpus()
