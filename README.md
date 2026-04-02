# Shelf 📚

A ChatGPT-style book recommendation chatbot. Describe your reading tastes and Shelf's multi-agent pipeline queries a seeded vector database, live book APIs, and the web in parallel to find personalized recommendations — streamed back token by token.

**[Try it live →](https://book-recommender-ten.vercel.app)**

<img width="1373" height="745" alt="Screenshot 2026-04-02 at 7 20 34 PM" src="https://github.com/user-attachments/assets/d05fc24a-d66a-42f7-bf25-090257f27e4c" />

## How It Works

Each chat message is processed by a 5-stage LangGraph pipeline:

```
normalize_query
      │
      ▼
┌─────────────────────────────────────────┐
│          parallel_personas              │
│                                         │
│  The Librarian   The Trend Watcher  The Web Curator  │
│  (vector DB +    (Google Books +    (Tavily web      │
│   Open Library)   NYT Bestsellers)   search)         │
└─────────────────────────────────────────┘
      │
      ▼
synthesizer  (LLM ranks & writes prose)
      │
      ▼
filter_books (extracts final book list)
```

1. **normalize_query** — an LLM parses the user's request and generates optimized search queries for each source
2. **parallel_personas** — three specialist agents run concurrently, each querying different data sources
3. **synthesizer** — an LLM picks the 3–6 best matches, writes recommendation prose, and streams it back token-by-token via SSE
4. **filter_books** — the final book list is extracted from the LLM output and sent to the frontend as a structured JSON event

Conversation state (session ID, search angles, previously shown books) is preserved across turns using LangGraph's `MemorySaver`, enabling follow-ups like *"give me 3 more"*.

## Architecture

```
Next.js (Vercel) ──SSE──► FastAPI + LangGraph (Railway)
                                   │
               ┌───────────────────┼──────────────────────┐
               ▼                   ▼                      ▼
        Supabase pgvector     Google Books API      Tavily MCP
        (semantic search)   + NYT Bestsellers API   (web search)
               │
        Open Library API
```

## Quick Start

### Prerequisites
- Python 3.13+
- Node.js 20+
- A [Supabase](https://supabase.com) project with the **pgvector extension** enabled and the `match_books` RPC function created (see `backend/ingestion/`)
- API keys for [OpenAI](https://platform.openai.com/api-keys), [Google Books](https://console.cloud.google.com/apis/library/books.googleapis.com), and [NYT Books](https://developer.nytimes.com/apis)
- Optionally: a [Tavily](https://app.tavily.com) API key (enables the Web Curator persona)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn app.main:app --reload
```

API docs available at **http://localhost:8000/docs** (development only; disabled in production).

### Seed the vector database

```bash
cd backend
python -m ingestion.seed_books
```

This fetches ~5,600 books across 28 genres from Open Library, embeds them via OpenAI `text-embedding-3-small`, and upserts them into Supabase pgvector. Expect 10–20 minutes depending on network and API quota.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open **http://localhost:3000**

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API key (LLM chat + embeddings) |
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | ✅ | Supabase service role key |
| `GOOGLE_BOOKS_API_KEY` | ✅ | Google Books API key |
| `NYT_API_KEY` | ✅ | NYT Books API key |
| `TAVILY_API_KEY` | ❌ | Tavily web search key (Web Curator disabled if blank) |
| `ALLOWED_ORIGINS` | ✅ | Comma-separated CORS origins (e.g. `https://yourapp.vercel.app`) |
| `ENVIRONMENT` | ✅ | `development` or `production` (disables `/docs` in production) |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | ✅ | FastAPI backend base URL |

## Usage Examples

```bash
# Chat (returns a Server-Sent Events stream)
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I loved The Martian, what should I read next?", "session_id": "test-123"}'

# Health check
curl http://localhost:8000/health
```

## Deployment

### Backend — Railway

1. Create a new project at [railway.app](https://railway.app) → **Deploy from GitHub repo**
2. In the service **Settings → Source**, set **Root Directory** to `backend/`
3. Railway auto-detects the `Dockerfile`
4. In the **Variables** tab, add all 8 environment variables listed above
5. After deploy, verify: `curl https://your-railway-url/health` → `{"status":"ok"}`

### Frontend — Vercel

1. Create a new project at [vercel.com](https://vercel.com) → **Import from GitHub**
2. Set **Root Directory** to `frontend/`
3. Add environment variable: `NEXT_PUBLIC_API_URL` = your Railway URL (with `https://`)
4. Deploy → copy the Vercel URL
5. Go back to Railway → update `ALLOWED_ORIGINS` to your Vercel URL → Railway auto-redeploys

> **Note**: `NEXT_PUBLIC_` variables are baked in at build time. Changing them in Vercel requires a redeploy.

## CI/CD

GitHub Actions runs automatically on pushes to `main` and `develop`:

| Workflow | Scope | Checks |
|---|---|---|
| `backend-ci` | `backend/**` | ruff, mypy, bandit, pytest |
| `frontend-ci` | `frontend/**` | eslint, tsc, next build |
| `codeql` | All PRs + weekly | Security scanning (Python + JS/TS) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
