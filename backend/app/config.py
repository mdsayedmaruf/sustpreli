from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database (optional). A Postgres URL, e.g. Neon. If empty, chat history
    # is not persisted and the app runs without a database.
    database_url: str = ""

    # OpenRouter (optional — the service scores fully without it; see plan.md #3)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"

    # Enable optional LLM polishing of prose fields. OFF by default: the
    # deterministic engine is the reliable, enum-exact path and needs no key.
    use_llm: bool = False

    # Outbound LLM call timeout. Must stay well under the 30s per-request budget
    # the judge harness enforces (problem.md §9). Was a hardcoded 120s.
    llm_timeout_seconds: float = 10.0

    # Sent to OpenRouter for ranking/attribution (optional but recommended)
    app_url: str = "http://localhost:5173"
    app_title: str = "Hackathon Chatbot"

    # System prompt prepended to every conversation
    system_prompt: str = (
        "You are a helpful, friendly assistant. Answer clearly and concisely."
    )

    # CORS: comma-separated list of allowed origins. "*" allows all.
    cors_origins: str = "*"

    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
