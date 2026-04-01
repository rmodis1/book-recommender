"""
Open Library API tool.

Searches books by subject, title, or author. Returns structured book data
with graceful fallback when description or cover is missing.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_BASE_URL = "https://openlibrary.org"
_COVERS_URL = "https://covers.openlibrary.org/b/id"


def _cover_url(cover_id: int | None) -> str | None:
    if not cover_id:
        return None
    return f"{_COVERS_URL}/{cover_id}-M.jpg"


def _parse_doc(doc: dict[str, Any]) -> dict[str, Any]:
    title = doc.get("title", "Unknown Title")
    author = ", ".join(doc.get("author_name", ["Unknown Author"]))
    q = urllib.parse.quote_plus(f"{title} {author}".strip())
    return {
        "title": title,
        "author": author,
        "description": doc.get("first_sentence", {}).get("value")
        if isinstance(doc.get("first_sentence"), dict)
        else doc.get("first_sentence") or None,
        "cover_url": _cover_url(doc.get("cover_i")),
        "book_url": f"https://www.goodreads.com/search?q={q}" if q else None,
        "genres": doc.get("subject", [])[:5],
        "source": "open_library",
    }


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(1),
)
def _search(params: dict[str, Any]) -> list[dict[str, Any]]:
    with httpx.Client(timeout=6) as client:
        response = client.get(f"{_BASE_URL}/search.json", params=params)
        response.raise_for_status()
        docs = response.json().get("docs", [])
        return [_parse_doc(d) for d in docs[:10]]


@tool
def search_open_library(query: str) -> list[dict[str, Any]]:
    """
    Search Open Library for books matching the query.

    Returns up to 10 books with title, author, description, genres, and cover URL.
    Use this to find books by topic, title, or author name.
    """
    fields = "key,title,author_name,cover_i,subject,first_sentence"
    try:
        # Use subject: prefix for more targeted, faster results
        subject_query = f"subject:{query}"
        return _search({
            "q": subject_query,
            "fields": fields,
            "limit": 10,
            "language": "eng",
            "sort": "rating",
        })
    except Exception as exc:
        logger.warning("Open Library search failed for query %r: %s", query, exc)
        return []
