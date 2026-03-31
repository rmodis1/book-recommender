"""
Book ingestion script.

Fetches up to ~5,600 books across 28 genres from Open Library, then embeds
and upserts into Supabase pgvector. Google Books is not used during seeding
to avoid exhausting the free-tier daily quota (~1,000 req/day); it is called
only during live chat queries via the search_google_books tool.

Usage:
    cd backend
    source .venv/bin/activate
    python -m ingestion.seed_books
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import httpx
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr
from supabase import create_client
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GENRES = [
    # Speculative fiction
    "science fiction",
    "hard science fiction",
    "space opera",
    "fantasy",
    "epic fantasy",
    "urban fantasy",
    "horror",
    # Mystery & thriller
    "mystery",
    "cozy mystery",
    "detective fiction",
    "thriller",
    "psychological thriller",
    "true crime",
    # Romance
    "contemporary romance",
    "romantic comedy",
    "historical romance",
    "paranormal romance",
    # Literary & general fiction
    "literary fiction",
    "historical fiction",
    "short stories",
    "young adult",
    "young adult fantasy",
    # Nonfiction
    "biography",
    "memoir",
    "self help",
    "popular science",
    "history",
    "travel writing",
]

BOOKS_PER_GENRE = 200
_OL_BASE = "https://openlibrary.org"
_COVERS_URL = "https://covers.openlibrary.org/b/id"


# ---------------------------------------------------------------------------
# Open Library fetch
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=2, min=4, max=120),
    stop=stop_after_attempt(5),
)
def _fetch_ol_subject(subject: str, limit: int = 50) -> list[dict[str, Any]]:
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_OL_BASE}/search.json",
            params={
                "subject": subject,
                "fields": "title,author_name,cover_i,subject,first_sentence,isbn",
                "limit": limit,
                "language": "eng",
            },
            headers={"User-Agent": "Shelf/1.0 (contact@example.com)"},
        )
        resp.raise_for_status()
        return resp.json().get("docs", [])


# ---------------------------------------------------------------------------
# Build book record from Open Library data
# ---------------------------------------------------------------------------


def _book_id(title: str, author: str) -> str:
    key = f"{title.lower()}::{author.lower()}"
    return hashlib.md5(key.encode()).hexdigest()  # noqa: S324 — used as a stable ID, not security


def _build_book(ol_doc: dict[str, Any]) -> dict[str, Any] | None:
    title = ol_doc.get("title", "").strip()
    authors = ol_doc.get("author_name", [])
    author = ", ".join(authors) if authors else "Unknown Author"

    if not title or not authors:
        return None

    # Description from OL first sentence
    description: str | None = None
    fs = ol_doc.get("first_sentence")
    if isinstance(fs, dict):
        description = fs.get("value")
    elif isinstance(fs, str):
        description = fs
    if description and len(description) > 600:
        description = description[:600] + "…"

    # Cover from OL
    cover_url: str | None = None
    cover_id = ol_doc.get("cover_i")
    if cover_id:
        cover_url = f"{_COVERS_URL}/{cover_id}-M.jpg"

    # Genres from OL subjects, deduplicated, cap at 8
    genres: list[str] = list(dict.fromkeys(ol_doc.get("subject", [])))[:8]

    return {
        "id": _book_id(title, author),
        "title": title,
        "author": author,
        "description": description or "",
        "cover_url": cover_url,
        "genres": genres,
        "nyt_bestseller": False,
    }


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------


def _upsert_batch(
    documents: list[Document],
    embeddings: OpenAIEmbeddings,
    client: Any,
) -> None:
    """Embed and upsert a list of documents into Supabase pgvector."""
    ids = [doc.metadata["id"] for doc in documents]
    SupabaseVectorStore.from_documents(
        documents=documents,
        embedding=embeddings,
        client=client,
        table_name="books",
        query_name="match_books",
        ids=ids,
    )


def ingest() -> None:
    logger.info("Connecting to Supabase…")
    client = create_client(settings.supabase_url_str, settings.supabase_service_key)
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=SecretStr(settings.openai_api_key),
    )

    seen_ids: set[str] = set()
    total_upserted = 0

    for genre in GENRES:
        logger.info("Fetching Open Library — genre: %s", genre)
        try:
            ol_docs = _fetch_ol_subject(genre, BOOKS_PER_GENRE)
        except Exception as exc:
            logger.warning("Skipping genre %s: %s", genre, exc)
            continue

        genre_docs: list[Document] = []
        for ol_doc in ol_docs:
            book = _build_book(ol_doc)
            if not book:
                continue

            book_id = book["id"]
            if book_id in seen_ids:
                continue
            seen_ids.add(book_id)

            page_content = book["description"] or f"{book['title']} by {book['author']}"
            metadata = {k: v for k, v in book.items() if k != "description"}
            genre_docs.append(Document(page_content=page_content, metadata=metadata))

        if genre_docs:
            logger.info("Upserting %d books for genre %r…", len(genre_docs), genre)
            try:
                _upsert_batch(genre_docs, embeddings, client)
                total_upserted += len(genre_docs)
                logger.info("Upserted — total so far: %d", total_upserted)
            except Exception as exc:
                logger.error("Upsert failed for genre %r: %s — skipping", genre, exc)

        time.sleep(0.35)  # ≈3 req/sec — stay within OL identified-request limit

    logger.info("Ingestion complete — %d books embedded and stored", total_upserted)


if __name__ == "__main__":
    ingest()
