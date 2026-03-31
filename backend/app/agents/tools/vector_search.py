"""
Supabase pgvector semantic search tool.

Wraps LangChain's SupabaseVectorStore to expose a @tool for the agent.
Falls back to Open Library direct search if Supabase is unreachable.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase import create_client

from app.core.config import settings
from app.agents.tools.open_library import search_open_library

logger = logging.getLogger(__name__)


def _get_vector_store() -> SupabaseVectorStore:
    client = create_client(settings.supabase_url_str, settings.supabase_service_key)
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )
    return SupabaseVectorStore(
        client=client,
        embedding=embeddings,
        table_name="books",
        query_name="match_books",
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
        store = _get_vector_store()
        docs = store.similarity_search(query, k=8)
        return [
            {
                **doc.metadata,
                "description": doc.page_content,
                "source": "vector_db",
            }
            for doc in docs
        ]
    except Exception as exc:
        logger.warning("Vector search failed, falling back to Open Library: %s", exc)
        return search_open_library.invoke(query)  # type: ignore[arg-type]
