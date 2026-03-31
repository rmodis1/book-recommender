from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest

router = APIRouter()


@router.post("/chat", tags=["chat"])
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Stream book recommendations as Server-Sent Events.

    Events emitted (in order):
    - `text_token` — incremental prose token from the LLM
    - `books`      — JSON array of Book objects
    - `done`       — stream complete
    - `error`      — something went wrong
    """
    # Agent wired in Phase 3; stub returns a single done event for now.
    async def _stream():
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
