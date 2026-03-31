"""
Auto-seed module.

Silently expands the vector DB with new books discovered during live chat
queries (Google Books and NYT tools). Runs in a daemon thread so SSE
streaming is never blocked.

Books are upserted with stable MD5 IDs derived from title+author, so
repeated calls for the same book are no-ops at the Supabase level.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import urllib.parse
from typing import Any

from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr
from supabase import create_client

from app.core.config import settings

logger = logging.getLogger(__name__)


def _book_id(title: str, author: str) -> str:
    key = f"{title.lower()}::{author.lower()}"
    return hashlib.md5(key.encode()).hexdigest()  # noqa: S324 — stable ID, not security


def _upsert(books: list[dict[str, Any]]) -> None:
    """Embed and upsert a list of books into Supabase pgvector."""
    if not books:
        return

    documents: list[Document] = []
    ids: list[str] = []

    for book in books:
        title = (book.get("title") or "").strip()
        author = (book.get("author") or "").strip()
        if not title or not author:
            continue

        # Build a Goodreads URL if the tool didn't provide one
        book_url = book.get("book_url")
        if not book_url:
            q = urllib.parse.quote_plus(f"{title} {author}")
            book_url = f"https://www.goodreads.com/search?q={q}"

        doc_id = _book_id(title, author)
        page_content = (book.get("description") or "").strip() or f"{title} by {author}"
        metadata: dict[str, Any] = {
            "id": doc_id,
            "title": title,
            "author": author,
            "cover_url": book.get("cover_url"),
            "book_url": book_url,
            "genres": book.get("genres") or [],
            "nyt_bestseller": book.get("nyt_bestseller", False),
        }
        documents.append(Document(page_content=page_content, metadata=metadata))
        ids.append(doc_id)

    if not documents:
        return

    try:
        client = create_client(settings.supabase_url_str, settings.supabase_service_key)
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=SecretStr(settings.openai_api_key),
        )
        SupabaseVectorStore.from_documents(
            documents=documents,
            embedding=embeddings,
            client=client,
            table_name="books",
            query_name="match_books",
            ids=ids,
        )
        logger.info("Auto-seeded %d books into vector DB", len(documents))
    except Exception as exc:
        logger.warning("Auto-seed upsert failed: %s", exc)


def auto_seed(books: list[dict[str, Any]]) -> None:
    """Fire-and-forget: upsert books in a daemon thread so SSE streaming is never blocked."""
    if not books:
        return
    thread = threading.Thread(target=_upsert, args=(books,), daemon=True)
    thread.start()
