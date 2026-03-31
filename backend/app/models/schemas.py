import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Book(BaseModel):
    title: str
    author: str
    description: str | None = None
    cover_url: str | None = None
    book_url: str | None = None
    genres: list[str] = []
    nyt_bestseller: bool = False
    nyt_list: str | None = None
    source: str  # "vector_db" | "google_books" | "open_library"


class SSEEvent(BaseModel):
    event: str  # "text_token" | "books" | "done" | "error"
    data: str
