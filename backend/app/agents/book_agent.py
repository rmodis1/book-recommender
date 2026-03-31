"""
LangGraph ReAct agent for book recommendations.

Graph shape:
  START → agent → (tools | END)
             ↑__________|

State carries messages, session_id, and the books list accumulated
from tool calls so we can emit a `books` SSE event at the end.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app.agents.tools.google_books import search_google_books
from app.agents.tools.nyt_books import search_nyt_bestsellers
from app.agents.tools.open_library import search_open_library
from app.agents.tools.vector_search import search_books_by_topic
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are Shelf, a knowledgeable and friendly librarian.
Your job is to recommend books to users based on their interests, mood, or any \
other criteria they share.

Guidelines:
- Always search the vector database first using search_books_by_topic.
- Enrich results with Google Books details when descriptions are thin.
- Check NYT bestsellers lists to surface popular titles in the relevant genre.
- If sources conflict on author or title, prefer Google Books data.
- Mention bestseller status naturally in your prose when applicable.
- When the vector database is unavailable, fall back to Open Library.
- Present recommendations in warm, conversational prose, then summarise each \
  book in 1–2 sentences. Aim for 3–8 recommendations per response.
- Keep responses focused on books — politely redirect off-topic questions."""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: str
    books_found: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# LLM + tools
# ---------------------------------------------------------------------------
_TOOLS = [
    search_books_by_topic,
    search_google_books,
    search_open_library,
    search_nyt_bestsellers,
]


def _make_llm():
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        streaming=True,
        temperature=0.7,
    ).bind_tools(_TOOLS)


# ---------------------------------------------------------------------------
# Node helpers
# ---------------------------------------------------------------------------
def _agent_node(state: AgentState) -> dict:
    messages = state["messages"]
    # Prepend system message if this is the first turn
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages

    llm = _make_llm()
    response = llm.invoke(messages)
    return {"messages": [response]}


def _should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def _collect_books(state: AgentState) -> dict:
    """After tool calls complete, gather any book lists from tool results."""
    books: list[dict[str, Any]] = []
    for msg in reversed(state["messages"]):
        # ToolMessage content is a JSON string produced by our @tool functions
        if hasattr(msg, "content") and hasattr(msg, "tool_call_id"):
            try:
                result = json.loads(msg.content)
                if isinstance(result, list) and result and isinstance(result[0], dict):
                    books.extend(result)
            except (json.JSONDecodeError, TypeError):
                pass
    # De-duplicate by id if present, else by title+author
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for b in books:
        key = b.get("id") or f"{b.get('title', '')}::{b.get('author', '')}"
        if key not in seen:
            seen.add(key)
            unique.append(b)
    return {"books_found": unique}


# ---------------------------------------------------------------------------
# Build graph (compiled once at import time)
# ---------------------------------------------------------------------------
def _build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("agent", _agent_node)
    builder.add_node("tools", ToolNode(_TOOLS))
    builder.add_node("collect_books", _collect_books)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", _should_continue, {"tools": "tools", END: "collect_books"}
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("collect_books", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public streaming interface
# ---------------------------------------------------------------------------
async def stream_response(
    message: str,
    session_id: str,
) -> AsyncIterator[tuple[str, Any]]:
    """
    Async generator that yields (event_type, data) tuples:
      ("text_token", str)          — incremental LLM prose token
      ("books",      list[dict])   — accumulated book objects
      ("error",      str)          — error message
    """
    config = {"configurable": {"thread_id": session_id}}
    inputs: AgentState = {
        "messages": [HumanMessage(content=message)],
        "session_id": session_id,
        "books_found": [],
    }

    try:
        async for event in _graph.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]

            # Stream LLM text tokens
            if kind == "on_chat_model_stream":
                chunk: AIMessageChunk = event["data"]["chunk"]
                if chunk.content and not getattr(chunk, "tool_calls", None):
                    yield ("text_token", chunk.content)

            # Emit books after collect_books node runs
            elif kind == "on_chain_end" and event.get("name") == "collect_books":
                books = event["data"]["output"].get("books_found", [])
                if books:
                    yield ("books", books)

    except Exception as exc:
        logger.exception("Agent error for session %s", session_id)
        yield ("error", str(exc))
