-- Run this in the Supabase SQL Editor before running seed_books.py
-- Dashboard → SQL Editor → New query → paste → Run

-- 1. Enable pgvector extension
create extension if not exists vector;

-- 2. Create the books table
create table if not exists books (
  id          text primary key,
  content     text,                        -- page_content used for embedding
  metadata    jsonb,                       -- title, author, cover_url, genres, etc.
  embedding   vector(1536)                 -- text-embedding-3-small dimensions
);

-- 3. Create the match_books function used by SupabaseVectorStore
create or replace function match_books(
  query_embedding vector(1536),
  match_count     int default 8,
  filter          jsonb default '{}'
)
returns table (
  id         text,
  content    text,
  metadata   jsonb,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    books.id,
    books.content,
    books.metadata,
    1 - (books.embedding <=> query_embedding) as similarity
  from books
  where books.metadata @> filter
  order by books.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- 4. Optional: HNSW index for faster search on larger datasets (run after ingestion)
-- create index on books using hnsw (embedding vector_cosine_ops)
-- with (m = 16, ef_construction = 64);
