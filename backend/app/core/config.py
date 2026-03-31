from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List


class Settings(BaseSettings):
    # Gemini
    google_api_key: str

    # Supabase
    supabase_url: AnyHttpUrl
    supabase_service_key: str

    # Google Books
    google_books_api_key: str

    # NYT Books
    nyt_api_key: str

    # CORS
    allowed_origins: List[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()  # type: ignore[call-arg]
