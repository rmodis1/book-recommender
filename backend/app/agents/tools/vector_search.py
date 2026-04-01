"""
Supabase pgvector semantic search tool.

Calls the match_books RPC function directly via supabase-py, bypassing
the langchain_community SupabaseVectorStore which has internal-API
compatibility issues with supabase>=2.21.
Falls back to Open Library if Supabase is unreachable.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, cast

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr
from supabase import create_client

from app.agents.tools.open_library import search_open_library
from app.core.config import settings

logger = logging.getLogger(__name__)

_embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=SecretStr(settings.openai_api_key),
)


@tool
def search_books_by_topic(query: str) -> list[dict[str, Any]]:
    """
    Semantically search the book vector database for books matching the query.

    This is the primary search tool — use it first for every recommendation request.
    Returns up to 8 books most semantically similar to the query, each with
    title, author, description, genres, and cover URL.

    Falls back to Open Library search if the vector database is unavailable.
    """
    try:
        vector = _embeddings.embed_query(query)
        client = create_client(settings.supabase_url_str, settings.supabase_service_key)
        # Fetch more candidates than needed so we can diversify by author
        response = client.rpc(
            "match_books",
            {"query_embedding": vector, "match_count": 20, "filter": {}},
        ).execute()
        rows = cast(list[dict[str, Any]], response.data or [])

        # Build full result objects, then deduplicate by author (≤2 per author)
        # so that popular authors don't crowd out every slot in every query.
        candidates = []
        for row in rows:
            metadata: dict[str, Any] = row.get("metadata") or {}
            title = metadata.get("title", "")
            author = metadata.get("author", "")
            q = urllib.parse.quote_plus(f"{title} {author}".strip())
            book_url = f"https://www.goodreads.com/search?q={q}"
            candidates.append(
                {
                    **metadata,
                    "description": row.get("content", ""),
                    "similarity": row.get("similarity", 0.0),
                    "book_url": book_url,
                    "source": "vector_db",
                }
            )

        # Author-diversity pass: keep at most 2 books per author, return top 8
        author_counts: dict[str, int] = {}
        diverse: list[dict[str, Any]] = []
        for book in candidates:
            author = (book.get("author") or "unknown").lower()
            if author_counts.get(author, 0) < 2:
                author_counts[author] = author_counts.get(author, 0) + 1
                diverse.append(book)
            if len(diverse) == 8:
                break

        return diverse
    except Exception as exc:
        logger.warning("Vector search failed, falling back to Open Library: %s", exc)
        return search_open_library.invoke(query)  # type: ignore[arg-type]
