"""
Open Library API tool.

Searches books by subject, title, or author. Returns structured book data
with graceful fallback when description or cover is missing.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

_BASE_URL = "https://openlibrary.org"
_COVERS_URL = "https://covers.openlibrary.org/b/id"


def _cover_url(cover_id: int | None) -> str | None:
    if not cover_id:
        return None
    return f"{_COVERS_URL}/{cover_id}-M.jpg"


def _parse_doc(doc: dict[str, Any]) -> dict[str, Any]:
    cover_id = doc.get("cover_i") or (doc.get("cover_edition_key") and None)
    return {
        "title": doc.get("title", "Unknown Title"),
        "author": ", ".join(doc.get("author_name", ["Unknown Author"])),
        "description": doc.get("first_sentence", {}).get("value")
        if isinstance(doc.get("first_sentence"), dict)
        else doc.get("first_sentence") or None,
        "cover_url": _cover_url(doc.get("cover_i")),
        "genres": doc.get("subject", [])[:5],
        "source": "open_library",
    }


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
)
def _search(params: dict[str, Any]) -> list[dict[str, Any]]:
    with httpx.Client(timeout=10) as client:
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
    try:
        return _search({"q": query, "fields": "title,author_name,cover_i,subject,first_sentence", "limit": 10})
    except Exception as exc:
        logger.warning("Open Library search failed for query %r: %s", query, exc)
        return []
