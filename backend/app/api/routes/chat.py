import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agents.book_agent import stream_response
from app.core.limiter import limiter
from app.models.schemas import ChatRequest

router = APIRouter()


@router.post("/chat", tags=["chat"])
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """
    Stream book recommendations as Server-Sent Events.

    Events emitted (in order):
    - `text_token` — incremental prose token from the LLM
    - `books`      — JSON array of Book objects
    - `done`       — stream complete
    - `error`      — something went wrong
    """

    async def _stream():
        try:
            async for event_type, data in stream_response(body.message, body.session_id):
                if event_type == "text_token":
                    payload = json.dumps({"token": data})
                elif event_type == "books":
                    payload = json.dumps(data)
                else:  # "error"
                    payload = json.dumps({"message": data})
                yield f"event: {event_type}\ndata: {payload}\n\n"
        finally:
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
