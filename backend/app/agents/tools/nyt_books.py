"""
NYT Books API tool.

Uses /lists/overview.json to get all current bestseller lists in one call,
then filters to the lists most relevant to the requested genre.

The /lists/names.json endpoint was removed by NYT on May 15, 2025.
The overview endpoint is the correct replacement and returns real list names
dynamically, so this tool never has to maintain a hardcoded name mapping.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings
from ingestion.auto_seed import auto_seed

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.nytimes.com/svc/books/v3"

# Keywords used to match a genre string against NYT list display names / encoded names.
# Each entry is (genre_keyword, [list_name_encoded substrings to prefer]).
# If nothing matches, we fall back to hardcover-fiction.
_GENRE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("young adult", ["young-adult"]),
    ("children", ["childrens", "middle-grade", "picture-book"]),
    ("nonfiction", ["nonfiction", "non-fiction"]),
    ("business", ["business"]),
    ("biography", ["biography", "memoir"]),
    ("self help", ["advice", "self-help", "how-to"]),
    ("graphic", ["graphic"]),
    ("audio", ["audio"]),
    ("fiction", ["fiction"]),  # broad fallback inside fiction
]


def _parse_book(book: dict[str, Any], list_name_encoded: str) -> dict[str, Any]:
    return {
        "title": book.get("title", ""),
        "author": book.get("author", ""),
        "description": book.get("description") or None,
        "cover_url": book.get("book_image") or None,
        "nyt_bestseller": True,
        "nyt_list": list_name_encoded,
        "nyt_rank": book.get("rank"),
        "weeks_on_list": book.get("weeks_on_list", 0),
        "source": "nyt_books",
    }


def _is_transient(exc: BaseException) -> bool:
    """Retry on network errors, 5xx server errors, and 429 rate-limit responses."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.HTTPError)


@retry(
    retry=retry_if_exception(_is_transient),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
)
def _fetch_overview() -> list[dict[str, Any]]:
    """Fetch all current bestseller lists in one call via the overview endpoint."""
    with httpx.Client(timeout=15) as client:
        response = client.get(
            f"{_BASE_URL}/lists/overview.json",
            params={"api-key": settings.nyt_api_key},
        )
        response.raise_for_status()
        return response.json().get("results", {}).get("lists", [])


def _match_lists(genre: str, all_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the subset of NYT lists most relevant to the genre."""
    genre_lower = genre.lower().strip()

    # Find matching keywords for this genre
    preferred_substrings: list[str] = []
    for keyword, substrings in _GENRE_KEYWORDS:
        if keyword in genre_lower or genre_lower in keyword:
            preferred_substrings = substrings
            break

    if not preferred_substrings:
        # Unknown genre — prefer general fiction lists
        preferred_substrings = ["fiction"]

    matched = [
        lst
        for lst in all_lists
        if any(sub in lst.get("list_name_encoded", "") for sub in preferred_substrings)
    ]

    # If no specific match, fall back to hardcover-fiction
    if not matched:
        matched = [lst for lst in all_lists if lst.get("list_name_encoded") == "hardcover-fiction"]

    return matched


@tool
def search_nyt_bestsellers(genre: str) -> list[dict[str, Any]]:
    """
    Look up current NYT bestsellers for a given genre using the overview endpoint.

    Accepts any genre string (e.g. 'science fiction', 'young adult', 'nonfiction').
    Dynamically matches against whatever lists NYT currently publishes — no
    hardcoded list names required.

    Returns up to 15 books with title, author, description, cover URL,
    NYT rank, and weeks on the list. Use this to surface trending/popular books.
    """
    if not settings.nyt_api_key:
        return []

    try:
        all_lists = _fetch_overview()
        matched_lists = _match_lists(genre, all_lists)

        books: list[dict[str, Any]] = []
        seen: set[str] = set()
        for lst in matched_lists:
            list_name_encoded = lst.get("list_name_encoded", "")
            for book in lst.get("books", []):
                key = f"{book.get('title', '')}::{book.get('author', '')}"
                if key not in seen:
                    seen.add(key)
                    books.append(_parse_book(book, list_name_encoded))

        logger.info("NYT overview returned %d books for genre %r", len(books), genre)
        auto_seed(books)
        return books[:15]

    except Exception as exc:
        logger.warning("NYT Books fetch failed for genre %r: %s", genre, exc)
        return []
