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

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
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

Tool usage:
- For EVERY request, call BOTH search_books_by_topic AND search_google_books. \
  Do not skip Google Books even if the vector database returns good results — \
  the two sources complement each other and improve variety.
- When calling tools, use the user's EXACT phrasing and genre terms as the \
  query (e.g. if they ask for "romantic comedies", search "romantic comedies", \
  not just "romance"). Run 2–3 searches with varied phrasings to widen \
  coverage (e.g. "contemporary romance funny", "romantic comedy novel").
- Also call search_nyt_bestsellers when the request fits a NYT list category.
- Use search_open_library only if both other sources fail.

Recommendation quality:
- Before including any book in your response, verify it genuinely fits the \
  genre or mood the user requested. If a result does not fit — even if a tool \
  returned it — silently discard it and replace it with a better match from \
  the other tool. Never pad recommendations with loosely related books.
- If you cannot find at least 3 genuinely relevant recommendations after \
  searching all sources, say so honestly and ask the user to clarify rather \
  than recommending tangentially related books.
- Prefer lesser-known gems alongside well-known titles when possible.

Formatting:
- Present recommendations in warm, conversational prose. Aim for 3–6 \
  recommendations per response.
- Format each numbered recommendation on a single line: \
  **1. Title** by Author — brief description. Do not put the number on its \
  own line or split the title onto a separate line.
- NEVER include markdown image syntax (e.g. ![image](url)) in your responses.

Conversation memory:
- Honour every constraint the user has stated in this conversation. If they \
  said they do not want books by a certain author, from a certain era, or in a \
  certain sub-genre, exclude ALL such books — even if tools return them. Review \
  the full conversation history before finalising your list.
- Series deduplication: if you recommend a series as a whole, do NOT also list \
  individual installments. Pick one entry point (the series or the first book) \
  and present only that.
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

    # Filter to only books the LLM actually mentioned in its final response,
    # so the cards match what was recommended rather than all tool results.
    llm_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            llm_text = msg.content.lower() if isinstance(msg.content, str) else ""
            break
    if llm_text:
        mentioned = [b for b in unique if b.get("title", "").lower() in llm_text]
        if mentioned:
            unique = mentioned

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

    except Exception:
        logger.exception("Agent error for session %s", session_id)
        # Yield a generic message — never expose raw exception details to the client
        yield (
            "error",
            "I ran into a problem fetching recommendations. Please try again in a moment.",
        )
