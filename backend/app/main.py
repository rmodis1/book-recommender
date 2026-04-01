from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import book_detail, chat
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Open the Tavily MCP connection once at startup; close it on shutdown."""
    if settings.tavily_api_key:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: PLC0415

            from app.agents.book_agent import init_web_curator  # noqa: PLC0415

            client = MultiServerMCPClient({
                "tavily": {
                    "transport": "streamable_http",
                    "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={settings.tavily_api_key}",
                }
            })
            tavily_tools = await client.get_tools()
            init_web_curator(tavily_tools)
            yield
        except Exception as exc:
            import logging  # noqa: PLC0415
            logging.getLogger(__name__).warning(
                "Tavily MCP unavailable — Web Curator disabled: %s", exc
            )
            yield
    else:
        yield

app = FastAPI(
    title="Shelf — Book Recommendation API",
    description="LangGraph-powered book recommendation chatbot API.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(book_detail.router, prefix="/api")


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
