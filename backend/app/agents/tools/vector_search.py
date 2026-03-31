"""
Supabase pgvector semantic search tool.

Calls the match_books RPC function directly via supabase-py, bypassing
the langchain_community SupabaseVectorStore which has internal-API
compatibility issues with supabase>=2.21.
Falls back to Open Library if Supabase is unreachable.
"""

from __future__ import annotations

import logging
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
        response = client.rpc(
            "match_books",
            {"query_embedding": vector, "match_count": 8, "filter": {}},
        ).execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        results = []
        for row in rows:
            metadata: dict[str, Any] = row.get("metadata") or {}
            results.append(
                {
                    **metadata,
                    "description": row.get("content", ""),
                    "similarity": row.get("similarity", 0.0),
                    "source": "vector_db",
                }
            )
        return results
    except Exception as exc:
        logger.warning("Vector search failed, falling back to Open Library: %s", exc)
        return search_open_library.invoke(query)  # type: ignore[arg-type]
