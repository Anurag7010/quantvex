from functools import lru_cache
from typing import Any, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "AgentResponse"

    alpha_vantage_api_key: str = "demo"
    finnhub_api_key: str = "demo"
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"

    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8000
    mcp_server_name: str = "finance-mcp"
    mcp_server_version: str = "2.0.0"

    default_max_age_sec: int = 60
    semantic_cache_threshold: float = 0.86
    semantic_cache_recency_minutes: int = 5

    log_level: str = "INFO"

    memgraph_host: str = Field(default="localhost", env="MEMGRAPH_HOST")
    memgraph_port: int = Field(default=7687, env="MEMGRAPH_PORT")
    memgraph_user: str = Field(default="", env="MEMGRAPH_USER")
    memgraph_password: str = Field(default="", env="MEMGRAPH_PASSWORD")

    verdict_db_path: str = Field(default="verdicts.db", env="VERDICT_DB_PATH")

    newsdata_api_key: str = Field(default="", env="NEWSDATA_API_KEY")
    news_api_key: str = Field(default="", env="NEWS_API_KEY")
    mcp_api_key: str = "dev_key_change_in_production"
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = "gpt-4o"
    groq_api_key: str = Field(default="", env="GROQ_API_KEY")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", env="GROQ_BASE_URL")
    groq_model: str = Field(default="llama-3.3-70b-versatile", env="GROQ_MODEL")
    usd_inr_rate: Optional[float] = Field(default=89.94, env="USD_INR_RATE")
    allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        env="ALLOWED_ORIGINS",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
