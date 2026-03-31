"""
Google Books API tool.

Enriches results with cover thumbnails, descriptions, and categories.
Falls back gracefully if the API is unavailable or the key is missing.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.googleapis.com/books/v1/volumes"


def _parse_volume(item: dict[str, Any]) -> dict[str, Any]:
    info = item.get("volumeInfo", {})
    image_links = info.get("imageLinks", {})
    cover_url = (
        image_links.get("thumbnail")
        or image_links.get("smallThumbnail")
    )
    # Enforce HTTPS on cover URLs
    if cover_url and cover_url.startswith("http://"):
        cover_url = cover_url.replace("http://", "https://", 1)

    description = info.get("description")
    if description and len(description) > 500:
        description = description[:500] + "…"

    return {
        "title": info.get("title", "Unknown Title"),
        "author": ", ".join(info.get("authors", ["Unknown Author"])),
        "description": description,
        "cover_url": cover_url,
        "genres": info.get("categories", [])[:5],
        "source": "google_books",
    }


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
)
def _search(query: str) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"q": query, "maxResults": 10, "printType": "books"}
    if settings.google_books_api_key:
        params["key"] = settings.google_books_api_key
    with httpx.Client(timeout=10) as client:
        response = client.get(_BASE_URL, params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
        return [_parse_volume(i) for i in items]


@tool
def search_google_books(query: str) -> list[dict[str, Any]]:
    """
    Search Google Books for volumes matching the query.

    Returns up to 10 books with title, author, description, cover thumbnail URL,
    and genre categories. Prefer this tool for cover images and rich descriptions.
    """
    try:
        return _search(query)
    except Exception as exc:
        logger.warning("Google Books search failed for query %r: %s", query, exc)
        return []
