from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import book_detail, chat
from app.core.config import settings
from app.core.limiter import limiter

_is_production = settings.environment == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Open the Tavily MCP connection once at startup; close it on shutdown."""
    if settings.tavily_api_key:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: PLC0415

            from app.agents.book_agent import init_web_curator  # noqa: PLC0415

            client = MultiServerMCPClient(
                {
                    "tavily": {
                        "transport": "streamable_http",
                        "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={settings.tavily_api_key}",
                    }
                }
            )
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
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(book_detail.router, prefix="/api")


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
