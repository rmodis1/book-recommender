from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str

    # Supabase
    supabase_url: AnyHttpUrl
    supabase_service_key: str

    # Google Books
    google_books_api_key: str = ""

    # NYT Books
    nyt_api_key: str = ""

    # CORS — stored as comma-separated string to avoid pydantic-settings JSON parsing
    allowed_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()  # type: ignore[call-arg]
