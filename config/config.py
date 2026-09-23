from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    SECRET_KEY: str = Field(..., description="Session signing secret — use a long random string")
    REMINDER_API_TOKEN: str = Field(..., description="Static token for the n8n reminder endpoint")
    DEBUG: bool = Field(False, description="Enable debug mode (disables HTTPS-only cookies)")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Some providers (Neon, Heroku, ...) hand out "postgres://", which
        # SQLAlchemy 2.x no longer recognizes as a dialect — needs "postgresql://".
        v = v.strip().strip("'\"")
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        return v

    @property
    def IS_DEMO_MODE(self) -> bool:
        # Matches the ephemeral-/tmp sqlite path app/db.py seeds on cold
        # start — true only for the throwaway Vercel demo, never for a real
        # self-hosted install, so the login page can safely surface the
        # sample credentials only there.
        return self.DATABASE_URL.startswith("sqlite:////tmp/")


settings = Settings()
