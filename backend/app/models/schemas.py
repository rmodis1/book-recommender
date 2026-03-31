from pydantic import BaseModel, Field
from typing import List, Optional
import uuid


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Book(BaseModel):
    title: str
    author: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    genres: List[str] = []
    nyt_bestseller: bool = False
    nyt_list: Optional[str] = None
    source: str  # "vector_db" | "google_books" | "open_library"


class SSEEvent(BaseModel):
    event: str  # "text_token" | "books" | "done" | "error"
    data: str
