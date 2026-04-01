"""
LangGraph multi-agent pipeline for book recommendations.

Graph shape:
  START → normalize_query → parallel_personas → synthesizer → filter_books → END

Personas (run in parallel via asyncio.gather):
  The Librarian      — vector_db + open_library  — catalog specialist
  The Trend Watcher  — google_books + nyt         — popularity specialist
  The Web Curator    — Tavily MCP                 — community specialist (optional)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, SecretStr
from typing_extensions import TypedDict

from app.agents.tools.google_books import search_google_books
from app.agents.tools.nyt_books import search_nyt_bestsellers
from app.agents.tools.open_library import search_open_library
from app.agents.tools.vector_search import search_books_by_topic
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persona system prompts
# ---------------------------------------------------------------------------
_LIBRARIAN_PROMPT = """You are The Librarian — a genre expert and literary catalog specialist.
Your job: search the book catalog and find the best matches for the user's request.

Instructions:
- Call search_books_by_topic with the vector DB query given in the message.
- Also call search_open_library with the Open Library query given in the message.
- Evaluate results: trust genre tags and overall fit, not just exact keyword matches.
  A "romantic comedy" might use words like "witty" or "charming" — that is on-genre.
- Only reject a result if it is clearly off-genre (e.g. a war memoir tagged "romance").
- Respond with a brief summary of which books you found and why they fit."""

_TRENDS_PROMPT = """You are The Trend Watcher — an expert on bestselling and trending books.
Your job: surface popular, acclaimed, and widely-read books that match the user's request.

Instructions:
- Call search_google_books with the Google Books query given in the message.
- Call search_nyt_bestsellers with the NYT genre/list given in the message.
- Evaluate whether each result genuinely fits the user's genre and mood request.
- Respond with a brief summary of the best-matching popular books you found."""

_WEB_CURATOR_PROMPT = """You are The Web Curator — you find what real readers are recommending online.
Your job: search the web for genuine reader recommendations that match the user's request.

Instructions:
- Use your search tool to find what readers online recommend for the given request.
- Look for specific book titles and authors mentioned in reviews and discussions.
- Evaluate whether recommended books genuinely match the user's genre and mood.
- Output ONLY a valid JSON array of the books you found, exactly like this:
  [{"title": "Book Title", "author": "Author Name", \
  "description": "why readers love it", "source": "web"}]
  If no clear matches, output: []
- Do NOT include any prose outside the JSON array."""

_SYNTHESIZER_PROMPT = """You are Shelf, a knowledgeable and friendly librarian.
Your job is to recommend books to users based on their interests, mood, or any \
other criteria they share.

You have received candidate books from three specialist agents: The Librarian \
(catalog), The Trend Watcher (bestsellers), and The Web Curator (reader \
communities). Review all candidates carefully and pick the best 3–6 for the \
user's request.

Recommendation quality:
- SOURCE PRIORITY: Strongly prefer books from the Librarian [vector_db] and \
  Trend Watcher [google_books] / [nyt] sources. These are verified titles from \
  trusted databases. Catalog entries include a relevance score (score=0.00–1.00): \
  higher scores mean stronger semantic match — prefer high-scoring candidates.
- AVOID OVER-RECOMMENDING POPULAR DEFAULTS: Some books (e.g. Project Hail Mary, \
  The Martian, A Little Life) appear frequently in search results regardless of \
  the request. Only include such a book if it genuinely fits the user's specific \
  genre, mood, and tone — not just because it appeared in the candidates list. \
  When in doubt, favour a less ubiquitous title that fits better.
- RECENCY PREFERENCE: Among candidates of similar relevance, slightly prefer recently \
  published books (last 5 years) and current NYT bestsellers over older titles, \
  unless an older title is clearly the definitive recommendation for that genre.
- WEB SOURCE SKEPTICISM: Books marked [web] are unverified. Only include a \
  web-sourced book if it is a genuinely well-known, widely-read title you \
  recognise as real and relevant. Discard obscure self-published or indie titles.
- KNOWLEDGE FALLBACK: If the catalog/NYT candidates are fewer than 3 strong \
  matches, fill remaining slots with well-known acclaimed books from your own \
  knowledge. For popular genres there are always classic or highly-rated titles \
  you can confidently recommend — but apply the same "does it genuinely fit?" \
  standard as for candidates.
- Prefer a mix of eras, styles, and authors. Do not recommend two books by the \
  same author unless the user specifically asks for more from that author.

Formatting:
- Present recommendations in warm, conversational prose. Aim for 3–6 \
  recommendations per response.
- Format EVERY numbered recommendation exactly like this — number, title, \
  author, and description all on ONE line:
    CORRECT: **1. The Martian** by Andy Weir — a gripping survival story.
    WRONG:   1.\n  **The Martian** by Andy Weir — ...
    WRONG:   **1.**\n  **The Martian** by Andy Weir — ...
  The number and title must be inside the same pair of ** markers: **1. Title**
- TITLE CASING: Write book titles in standard Title Case (e.g. "The Great Gatsby", \
  "A Court of Thorns and Roses"). NEVER write titles in ALL CAPS \
  (e.g. "THE GREAT GATSBY" is wrong). If a source provides an all-caps title, \
  convert it to Title Case.
- NEVER include markdown image syntax (e.g. ![image](url)) in your responses.
- After the description of each recommendation, add a "Tell me more" link \
  using angle-bracket URL syntax to handle spaces: \
  [Tell me more](<#ask:TITLE by AUTHOR>) — \
  replace TITLE and AUTHOR with the actual values after "#ask:". \
  The display text must be exactly "Tell me more" (nothing else). \
  Example: [Tell me more](<#ask:The Martian by Andy Weir>)

Conversation memory:
- Honour every constraint the user has stated in this conversation. If they \
  said they do not want books by a certain author, from a certain era, or in a \
  certain sub-genre, exclude ALL such books even if candidates include them.
- Never recommend a book the user has already read.
- Series deduplication: pick one entry point (the series or the first book), not both.
- Keep responses focused on books — politely redirect off-topic questions."""


# ---------------------------------------------------------------------------
# Structured output schemas
# ---------------------------------------------------------------------------
class _QueryAngles(BaseModel):
    search_angles: list[str]
    excluded_terms: list[str]
    is_followup: bool
    genre_categories: dict[str, str]
    # Expected keys:
    #   "vector_db"    — semantic phrase for pgvector
    #   "google_books" — keyword/subject query for Google Books API
    #   "nyt"          — NYT list_name_encoded (e.g. "hardcover-fiction")
    #   "open_library" — subject phrase for Open Library
    #   "web"          — natural-language query for web/Tavily search


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: str
    books_found: list[dict[str, Any]]
    search_angles: list[str]
    excluded_terms: list[str]
    genre_categories: dict[str, str]


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------
def _make_llm(streaming: bool = True) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=SecretStr(settings.openai_api_key),
        streaming=streaming,
        temperature=0.7,
    )


# ---------------------------------------------------------------------------
# Persona agents
# Librarian + Trend Watcher: created at module level (tools are sync + stable)
# Web Curator: created lazily via init_web_curator() during app lifespan startup
# ---------------------------------------------------------------------------
_librarian_agent = create_react_agent(
    _make_llm(streaming=False),
    tools=[search_books_by_topic, search_open_library],
)

_trends_agent = create_react_agent(
    _make_llm(streaming=False),
    tools=[search_google_books, search_nyt_bestsellers],
)

_web_curator_agent = None  # set by init_web_curator() when Tavily key is present


def init_web_curator(tavily_tools: list) -> None:
    """Called from app lifespan after Tavily MCP tools are loaded."""
    global _web_curator_agent
    _web_curator_agent = create_react_agent(
        _make_llm(streaming=False),
        tools=tavily_tools,
    )
    logger.info("Web Curator agent initialized with %d Tavily tools", len(tavily_tools))


# ---------------------------------------------------------------------------
# Node: normalize_query
# ---------------------------------------------------------------------------
_NORMALIZE_PROMPT = """\
You help a book recommendation system translate a user's request into specific \
search queries optimised for multiple sources.

Given the conversation so far, produce:

1. search_angles — 3-4 concrete, API-friendly search strings covering the \
   request from different angles. Each should be a phrase likely to match real \
   book metadata (genre terms, mood terms, comparable authors).
   Example for "cozy mysteries with cats":
     ["cozy mystery cat amateur sleuth", "feline detective cozy fiction", \
      "cat mystery novel series", "cozy crime domestic animals"]

2. excluded_terms — words/phrases the user wants avoided. Empty list if none.

3. is_followup — true ONLY if the user wants more of the exact same thing \
   (e.g. "give me 3 more", "any others?", "more like the last one"). \
   FALSE whenever the user introduces a different genre, topic, mood, author, \
   or time period. When in doubt, set is_followup=false.

4. genre_categories — per-source optimised queries with these exact keys:
   - "vector_db"    : semantic phrase for a vector database search
   - "google_books" : subject/keyword query for the Google Books API
   - "nyt"          : EXACTLY ONE NYT list_name_encoded value. Choose from:
       "hardcover-fiction"             (novels, genre fiction, literary fiction)
       "hardcover-nonfiction"          (general nonfiction)
       "trade-fiction-paperback"       (literary / indie fiction paperbacks)
       "young-adult-hardcover"         (YA fiction and nonfiction)
       "advice-how-to-and-miscellaneous" (self-help, how-to guides)
       "business-books"                (business, economics)
       "graphic-books-and-manga"       (graphic novels, comics, manga)
       "health-wellness"               (health, diet, wellness)
       Most fiction genres → "hardcover-fiction".
       Nonfiction → "hardcover-nonfiction".
   - "open_library" : subject query for Open Library
   - "web"          : natural-language query for a web search (include year and
                      community terms, e.g. "best cozy mystery 2023 readers recommend")

If is_followup is true, return empty search_angles, excluded_terms, and \
genre_categories — the previous turn's values will be reused."""


def _normalize_query_node(state: AgentState) -> dict:
    # Find the latest human message
    user_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_text = msg.content if isinstance(msg.content, str) else ""
            break

    llm = _make_llm(streaming=False).with_structured_output(_QueryAngles, method="function_calling")
    result: _QueryAngles = llm.invoke(
        [  # type: ignore[assignment]
            SystemMessage(content=_NORMALIZE_PROMPT),
            HumanMessage(content=user_text),
        ]
    )

    # If it's a follow-up and we already have angles, keep them
    if result.is_followup and state.get("search_angles"):
        return {}  # no-op — preserve existing state

    return {
        "search_angles": result.search_angles,
        "excluded_terms": result.excluded_terms,
        "genre_categories": result.genre_categories,
    }


# ---------------------------------------------------------------------------
# Parallel personas helpers
# ---------------------------------------------------------------------------
def _extract_books_from_messages(messages: list) -> list[dict[str, Any]]:
    """Extract book dicts from ToolMessage results in an agent's message history."""
    books: list[dict[str, Any]] = []
    for msg in messages:
        if hasattr(msg, "tool_call_id"):  # ToolMessage
            try:
                raw = msg.content if isinstance(msg.content, str) else "[]"
                data = json.loads(raw)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("title"):
                            books.append(item)
            except (json.JSONDecodeError, TypeError):
                pass
    return books


def _extract_books_from_final_message(messages: list) -> list[dict[str, Any]]:
    """Fallback: try to parse a JSON array from the final AIMessage (Web Curator)."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = msg.content if isinstance(msg.content, str) else ""
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    if isinstance(data, list):
                        return [
                            item for item in data if isinstance(item, dict) and item.get("title")
                        ]
                except (json.JSONDecodeError, ValueError):
                    pass
    return []


async def _run_librarian(cats: dict[str, str]) -> list[dict[str, Any]]:
    try:
        vdb_q = cats.get("vector_db", "")
        ol_q = cats.get("open_library", vdb_q)
        result = await _librarian_agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=_LIBRARIAN_PROMPT),
                    HumanMessage(
                        content=(
                            f'Call search_books_by_topic with this query: "{vdb_q}"\n'
                            f'Also call search_open_library with this query: "{ol_q}"'
                        )
                    ),
                ]
            }
        )
        return _extract_books_from_messages(result["messages"])
    except Exception as exc:
        logger.warning("Librarian agent failed: %s", exc)
        return []


async def _run_trends(cats: dict[str, str]) -> list[dict[str, Any]]:
    try:
        gb_q = cats.get("google_books", "")
        nyt_g = cats.get("nyt", "hardcover-fiction")
        result = await _trends_agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=_TRENDS_PROMPT),
                    HumanMessage(
                        content=(
                            f'Call search_google_books with this query: "{gb_q}"\n'
                            f'Call search_nyt_bestsellers with genre: "{nyt_g}"'
                        )
                    ),
                ]
            }
        )
        return _extract_books_from_messages(result["messages"])
    except Exception as exc:
        logger.warning("Trend Watcher agent failed: %s", exc)
        return []


async def _run_web_curator(cats: dict[str, str]) -> list[dict[str, Any]]:
    if _web_curator_agent is None:
        return []
    try:
        web_q = cats.get("web", "")
        result = await _web_curator_agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=_WEB_CURATOR_PROMPT),
                    HumanMessage(content=f"Search for book recommendations: {web_q}"),
                ]
            }
        )
        books = _extract_books_from_messages(result["messages"])
        if not books:
            books = _extract_books_from_final_message(result["messages"])
        return books
    except Exception as exc:
        logger.warning("Web Curator agent failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Node: parallel_personas
# ---------------------------------------------------------------------------
async def _parallel_personas_node(state: AgentState) -> dict:
    """Run all specialist persona agents in parallel and collect candidate books."""
    cats = state.get("genre_categories") or {}

    tasks: list = [_run_librarian(cats), _run_trends(cats)]
    if _web_curator_agent is not None:
        tasks.append(_run_web_curator(cats))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_books: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, list):
            all_books.extend(r)

    # Deduplicate by title + author
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for b in all_books:
        key = f"{b.get('title', '').lower()}::{b.get('author', '').lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(b)

    return {"books_found": unique}


# ---------------------------------------------------------------------------
# Node: synthesizer
# ---------------------------------------------------------------------------
def _synthesizer_node(state: AgentState) -> dict:
    """Write the final prose recommendation from pre-vetted candidate books."""
    messages = list(state["messages"])
    books = state.get("books_found") or []
    exclusions = state.get("excluded_terms") or []

    # Build candidate context (up to 25 books), sorted: catalog first, then others
    # Include similarity score where available so the synthesizer can weigh relevance
    catalog_books = [b for b in books if b.get("source") == "vector_db"]
    other_books = [b for b in books if b.get("source") != "vector_db"]
    ordered_books = catalog_books + other_books

    candidate_lines: list[str] = []
    for b in ordered_books[:25]:
        genres = ", ".join((b.get("genres") or [])[:3])
        raw_desc = b.get("description") or ""
        desc = (raw_desc if isinstance(raw_desc, str) else " ".join(raw_desc))[:150].rstrip()
        source = b.get("source", "catalog")
        similarity = b.get("similarity")
        score_str = f" score={similarity:.2f}" if isinstance(similarity, float) else ""
        line = f"- {b['title']} by {b.get('author', 'Unknown')} [{source}{score_str}]"
        if genres:
            line += f" | genres: {genres}"
        if desc:
            line += f" | {desc}"
        candidate_lines.append(line)

    addendum = ""
    if candidate_lines:
        addendum += "\n\nCANDIDATE BOOKS FROM SPECIALIST AGENTS (choose the best 3–6):\n"
        addendum += "\n".join(candidate_lines)
    if exclusions:
        addendum += f"\n\nEXCLUDED TERMS (never recommend): {', '.join(exclusions)}"

    system_content = _SYNTHESIZER_PROMPT + addendum

    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=system_content)] + messages
    else:
        messages = [
            SystemMessage(content=system_content) if isinstance(m, SystemMessage) else m
            for m in messages
        ]

    llm = _make_llm(streaming=True)  # no tools — pure prose generation
    response = llm.invoke(messages)
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Node: filter_books
# ---------------------------------------------------------------------------
def _main_title(title: str) -> str:
    """Normalize a title by stripping subtitles/series suffixes before comparing."""
    return re.split(r"[:(—–]", title)[0].strip().lower()


def _filter_books_node(state: AgentState) -> dict:
    """Match catalog books to the synthesizer's recommendations.

    For any recommended title not found in the catalog results, do a targeted
    Google Books lookup so book cards always appear for at least the top picks.
    """
    books = state.get("books_found") or []

    # Find the final prose response from the synthesizer
    llm_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            llm_text = msg.content if isinstance(msg.content, str) else ""
            break

    if not llm_text:
        return {"books_found": []}

    # Extract (title, author) pairs from **N. Title** by Author lines
    pairs: list[tuple[str, str]] = re.findall(r"\*\*\d+\.\s+(.+?)\*\*\s+by\s+([^—\n\[]+)", llm_text)
    if not pairs:
        # Plain-text fallback: "1. Title by Author"
        plain = re.findall(r"^\d+\.\s+(.+?)\s+by\s+([^—\n\[]+)", llm_text, re.MULTILINE)
        pairs = plain

    if not pairs:
        return {"books_found": books or []}

    # Index catalog books by normalised title
    books_by_title: dict[str, dict[str, Any]] = {_main_title(b.get("title", "")): b for b in books}

    result: list[dict[str, Any]] = []
    missing: list[tuple[str, str]] = []

    for raw_title, raw_author in pairs:
        title = raw_title.strip()
        author = raw_author.strip()
        key = _main_title(title)
        if key in books_by_title:
            result.append(books_by_title[key])
        else:
            missing.append((title, author))

    # Fallback: look up missing titles via Google Books so cards always appear
    for title, author in missing:
        try:
            hits: list[dict[str, Any]] = search_google_books.invoke({"query": f"{title} {author}"})
            if hits:
                result.append(hits[0])
        except Exception as exc:
            logger.debug("Fallback lookup failed for %r: %s", title, exc)

    return {"books_found": result}


# ---------------------------------------------------------------------------
# Build graph (compiled once at import time)
# ---------------------------------------------------------------------------
def _build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("normalize_query", _normalize_query_node)
    builder.add_node("parallel_personas", _parallel_personas_node)
    builder.add_node("synthesizer", _synthesizer_node)
    builder.add_node("filter_books", _filter_books_node)

    builder.add_edge(START, "normalize_query")
    builder.add_edge("normalize_query", "parallel_personas")
    builder.add_edge("parallel_personas", "synthesizer")
    builder.add_edge("synthesizer", "filter_books")
    builder.add_edge("filter_books", END)

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
    # Only reset books_found each turn — search_angles and excluded_terms are
    # preserved by the checkpoint and managed by _normalize_query_node.
    inputs: AgentState = {
        "messages": [HumanMessage(content=message)],
        "session_id": session_id,
        "books_found": [],
        "search_angles": [],
        "excluded_terms": [],
        "genre_categories": {},
    }

    try:
        async for event in _graph.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]

            # Stream LLM text tokens (only from the agent node, not normalize/filter)
            if kind == "on_chat_model_stream":
                metadata = event.get("metadata", {})
                if metadata.get("langgraph_node") == "synthesizer":
                    chunk: AIMessageChunk = event["data"]["chunk"]
                    if chunk.content and not getattr(chunk, "tool_calls", None):
                        yield ("text_token", chunk.content)

            # Emit books after filter_books node runs
            elif kind == "on_chain_end" and event.get("name") == "filter_books":
                books = event["data"]["output"].get("books_found", [])
                if books:
                    yield ("books", books)

    except Exception:
        logger.exception("Agent error for session %s", session_id)
        yield (
            "error",
            "I ran into a problem fetching recommendations. Please try again in a moment.",
        )
