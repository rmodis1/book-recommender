import json
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def _fake_stream(message: str, session_id: str):
    """Minimal stand-in for stream_response that never calls external APIs."""
    yield ("text_token", "Here are some great sci-fi picks.")
    yield ("books", [{"title": "Dune", "author": "Frank Herbert", "source": "vector_db"}])


@pytest.mark.asyncio
async def test_chat_sse_events():
    """POST /api/chat should emit text_token, books, and done SSE events."""
    with patch("app.api.routes.chat.stream_response", side_effect=_fake_stream):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/chat",
                json={"message": "I love sci-fi novels", "session_id": "test-session"},
            )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    # Parse the raw SSE body into (event, data) pairs
    events: dict[str, list] = {}
    for chunk in response.text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = {line.split(": ", 1)[0]: line.split(": ", 1)[1] for line in chunk.splitlines() if ": " in line}
        name = lines.get("event", "")
        raw = lines.get("data", "{}")
        events.setdefault(name, []).append(json.loads(raw))

    assert "text_token" in events, "Expected at least one text_token event"
    assert events["text_token"][0]["token"] == "Here are some great sci-fi picks."

    assert "books" in events, "Expected a books event"
    books = events["books"][0]
    assert isinstance(books, list)
    assert books[0]["title"] == "Dune"

    assert "done" in events, "Expected a done event to close the stream"


@pytest.mark.asyncio
async def test_chat_multi_turn_preserves_session():
    """Two requests with the same session_id must each produce a done event."""
    call_count = 0

    async def _counting_stream(message: str, session_id: str):
        nonlocal call_count
        call_count += 1
        yield ("text_token", f"Turn {call_count} response for session {session_id}")

    with patch("app.api.routes.chat.stream_response", side_effect=_counting_stream):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r1 = await client.post(
                "/api/chat",
                json={"message": "Recommend a fantasy book", "session_id": "s1"},
            )
            r2 = await client.post(
                "/api/chat",
                json={"message": "Give me something similar", "session_id": "s1"},
            )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert "done" in r1.text
    assert "done" in r2.text
    assert call_count == 2
