from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    SECRET_KEY: str = Field(..., description="Session signing secret — use a long random string")
    REMINDER_API_TOKEN: str = Field(..., description="Static token for the n8n reminder endpoint")
    DEBUG: bool = Field(False, description="Enable debug mode (disables HTTPS-only cookies)")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
