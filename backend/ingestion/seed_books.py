"""
Book ingestion script.

Fetches ~500 books across 10 genres from Open Library, enriches them with
Google Books metadata, flags NYT bestsellers, then embeds and upserts into
Supabase pgvector.

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
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from supabase import create_client
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GENRES = [
    "science fiction",
    "fantasy",
    "mystery",
    "thriller",
    "romance",
    "historical fiction",
    "biography",
    "self help",
    "horror",
    "young adult",
]

BOOKS_PER_GENRE = 50
_OL_BASE = "https://openlibrary.org"
_GB_BASE = "https://www.googleapis.com/books/v1/volumes"
_COVERS_URL = "https://covers.openlibrary.org/b/id"


# ---------------------------------------------------------------------------
# Open Library fetch
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
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
        )
        resp.raise_for_status()
        return resp.json().get("docs", [])


# ---------------------------------------------------------------------------
# Google Books enrichment
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
)
def _fetch_gb_volume(title: str, author: str) -> dict[str, Any] | None:
    params: dict[str, Any] = {
        "q": f"intitle:{title} inauthor:{author}",
        "maxResults": 1,
        "printType": "books",
    }
    if settings.google_books_api_key:
        params["key"] = settings.google_books_api_key
    with httpx.Client(timeout=10) as client:
        resp = client.get(_GB_BASE, params=params)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0].get("volumeInfo", {}) if items else None


# ---------------------------------------------------------------------------
# Build unified book record
# ---------------------------------------------------------------------------

def _book_id(title: str, author: str) -> str:
    key = f"{title.lower()}::{author.lower()}"
    return hashlib.md5(key.encode()).hexdigest()  # noqa: S324 — used as a stable ID, not security


def _merge_book(ol_doc: dict[str, Any], gb_info: dict[str, Any] | None) -> dict[str, Any] | None:
    title = ol_doc.get("title", "").strip()
    authors = ol_doc.get("author_name", [])
    author = ", ".join(authors) if authors else "Unknown Author"

    if not title or not authors:
        return None

    # Description: prefer Google Books, fall back to OL first sentence
    description: str | None = None
    if gb_info:
        description = gb_info.get("description")
        if description and len(description) > 600:
            description = description[:600] + "…"
    if not description:
        fs = ol_doc.get("first_sentence")
        if isinstance(fs, dict):
            description = fs.get("value")
        elif isinstance(fs, str):
            description = fs

    # Cover: prefer Google Books thumbnail, fall back to OL
    cover_url: str | None = None
    if gb_info:
        images = gb_info.get("imageLinks", {})
        cover_url = images.get("thumbnail") or images.get("smallThumbnail")
        if cover_url:
            cover_url = cover_url.replace("http://", "https://", 1)
    if not cover_url:
        cover_id = ol_doc.get("cover_i")
        if cover_id:
            cover_url = f"{_COVERS_URL}/{cover_id}-M.jpg"

    # Genres: merge OL subjects + GB categories, cap at 8
    genres: list[str] = list(ol_doc.get("subject", []))[:5]
    if gb_info:
        genres += gb_info.get("categories", [])
    genres = list(dict.fromkeys(genres))[:8]  # deduplicate, preserve order

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

def ingest() -> None:
    logger.info("Connecting to Supabase…")
    client = create_client(settings.supabase_url_str, settings.supabase_service_key)
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )

    seen_ids: set[str] = set()
    documents: list[Document] = []

    for genre in GENRES:
        logger.info("Fetching Open Library — genre: %s", genre)
        try:
            ol_docs = _fetch_ol_subject(genre, BOOKS_PER_GENRE)
        except Exception as exc:
            logger.warning("Skipping genre %s: %s", genre, exc)
            continue

        for ol_doc in ol_docs:
            title = ol_doc.get("title", "").strip()
            authors = ol_doc.get("author_name", [])
            author = ", ".join(authors) if authors else ""

            if not title or not author:
                continue

            book_id = _book_id(title, author)
            if book_id in seen_ids:
                continue
            seen_ids.add(book_id)

            # Enrich with Google Books (rate-limit friendly: 1 req/sec)
            gb_info: dict[str, Any] | None = None
            try:
                gb_info = _fetch_gb_volume(title, author)
                time.sleep(0.5)
            except Exception as exc:
                logger.debug("Google Books enrichment failed for %r: %s", title, exc)

            book = _merge_book(ol_doc, gb_info)
            if not book:
                continue

            # Use description as the document content for embedding
            page_content = book["description"] or f"{book['title']} by {book['author']}"
            metadata = {k: v for k, v in book.items() if k != "description"}
            documents.append(Document(page_content=page_content, metadata=metadata))

        logger.info("Collected %d unique books so far", len(documents))

    if not documents:
        logger.error("No books collected — aborting")
        return

    logger.info("Upserting %d books into Supabase pgvector…", len(documents))
    SupabaseVectorStore.from_documents(
        documents=documents,
        embedding=embeddings,
        client=client,
        table_name="books",
        query_name="match_books",
    )
    logger.info("Ingestion complete — %d books embedded and stored", len(documents))


if __name__ == "__main__":
    ingest()
