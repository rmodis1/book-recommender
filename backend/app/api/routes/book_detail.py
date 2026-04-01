from fastapi import APIRouter
from pydantic import BaseModel
from langchain_openai import ChatOpenAI

from app.core.config import settings

router = APIRouter()


class DetailRequest(BaseModel):
    subject: str


class DetailResponse(BaseModel):
    detail: str


_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    openai_api_key=settings.openai_api_key,
)

_DETAIL_PROMPT = """You are a knowledgeable and enthusiastic book expert. \
Given the book reference "{subject}", write a concise, engaging overview (2–3 short paragraphs) covering:
- What the book is about (plot or subject, without major spoilers)
- What makes it special or noteworthy
- Who would enjoy it most

Be warm, specific, and enthusiastic. Write in flowing prose — no bullet points or headers."""


@router.post("/book-detail", response_model=DetailResponse)
async def get_book_detail(req: DetailRequest) -> DetailResponse:
    prompt = _DETAIL_PROMPT.format(subject=req.subject)
    response = await _llm.ainvoke(prompt)
    return DetailResponse(detail=str(response.content))
