"""
NYT Books API tool.

Fetches current bestseller lists by category. Returns rank, list name,
and weeks on list as additive signals for the recommendation agent.
Fails gracefully — returns empty list if the API is unavailable.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.nytimes.com/svc/books/v3"

# Mapping of friendly genre names to NYT list names
_LIST_MAP: dict[str, str] = {
    "fiction": "combined-print-and-e-book-fiction",
    "nonfiction": "combined-print-and-e-book-nonfiction",
    "mystery": "mass-market-paperback",
    "young adult": "young-adult",
    "science fiction": "science-fiction",
    "romance": "romance",
    "business": "business-books",
    "children": "childrens-middle-grade",
}


def _parse_book(book: dict[str, Any], list_name: str) -> dict[str, Any]:
    return {
        "title": book.get("title", ""),
        "author": book.get("author", ""),
        "description": book.get("description") or None,
        "cover_url": book.get("book_image") or None,
        "nyt_bestseller": True,
        "nyt_list": list_name,
        "nyt_rank": book.get("rank"),
        "weeks_on_list": book.get("weeks_on_list", 0),
        "source": "nyt_books",
    }


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
)
def _fetch_list(list_name: str) -> list[dict[str, Any]]:
    if not settings.nyt_api_key:
        return []
    with httpx.Client(timeout=10) as client:
        response = client.get(
            f"{_BASE_URL}/lists/current/{list_name}.json",
            params={"api-key": settings.nyt_api_key},
        )
        response.raise_for_status()
        books = response.json().get("results", {}).get("books", [])
        return [_parse_book(b, list_name) for b in books[:10]]


@tool
def search_nyt_bestsellers(genre: str) -> list[dict[str, Any]]:
    """
    Look up current NYT bestsellers for a given genre.

    Valid genres: fiction, nonfiction, mystery, young adult, science fiction,
    romance, business, children.

    Returns up to 10 books with title, author, description, cover URL,
    NYT rank, and weeks on the list. Use this to surface trending/popular books.
    """
    list_name = _LIST_MAP.get(genre.lower().strip())
    if not list_name:
        # Fall back to fiction list if genre not found
        list_name = _LIST_MAP["fiction"]

    try:
        return _fetch_list(list_name)
    except Exception as exc:
        logger.warning("NYT Books fetch failed for genre %r: %s", genre, exc)
        return []
