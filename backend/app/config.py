from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file.

    The QueueStorm Investigator is self-contained: no database and no outbound
    network call on the analysis path. The only runtime setting is CORS.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # CORS: comma-separated list of allowed origins. "*" allows all.
    cors_origins: str = "*"

    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def cors_allow_credentials(self) -> bool:
        """Credentials cannot be combined with a wildcard origin.

        Browsers reject ``Access-Control-Allow-Origin: *`` together with
        ``Allow-Credentials: true``; enabling it is also a security smell. We
        only allow credentials when a concrete origin allowlist is configured.
        """
        return self.cors_origins.strip() != "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
