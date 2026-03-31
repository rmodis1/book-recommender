"""
Set required environment variables before any app module is imported.
This allows tests to run without a real .env file.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-supabase-key")
os.environ.setdefault("GOOGLE_BOOKS_API_KEY", "test-books-key")
os.environ.setdefault("NYT_API_KEY", "test-nyt-key")
