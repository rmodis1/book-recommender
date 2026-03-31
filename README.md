# Shelf 📚

A ChatGPT-style book recommendation chatbot. Describe your reading tastes and get personalized recommendations powered by a seeded vector database and three live book APIs.

## Architecture

```
Next.js (Vercel)  ──SSE──►  FastAPI + LangGraph (Railway)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
             Supabase pgvector  Google Books    Open Library
             (semantic search)      API             API
                                                    │
                                              NYT Books API
```

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- A [Supabase](https://supabase.com) project with pgvector enabled
- API keys for [Google AI Studio](https://aistudio.google.com/app/apikey), [Google Books](https://console.cloud.google.com/apis/library/books.googleapis.com), and [NYT Books](https://developer.nytimes.com/apis)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn app.main:app --reload
```

API docs auto-generated at **http://localhost:8000/docs**

### Seed the vector database

```bash
cd backend
python -m ingestion.seed_books
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL
npm run dev
```

Open **http://localhost:3000**

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Google AI Studio key for Gemini |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `GOOGLE_BOOKS_API_KEY` | Google Books API key |
| `NYT_API_KEY` | NYT Books API key |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |

### Frontend (`frontend/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | FastAPI backend base URL |

## Usage Examples

```bash
# Chat (streaming SSE)
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I loved The Martian, what should I read next?", "session_id": "test-123"}'

# Health check
curl http://localhost:8000/health
```

## Deployment

- **Backend**: [Railway](https://railway.app) — set project root to `backend/`
- **Frontend**: [Vercel](https://vercel.com) — set project root to `frontend/`, set `NEXT_PUBLIC_API_URL` to Railway service URL

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
