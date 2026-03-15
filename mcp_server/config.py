from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "AgentResponse"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    alpha_vantage_api_key: str = "demo"
    finnhub_api_key: str = "demo"
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"

    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8000
    mcp_server_name: str = "finance-mcp"
    mcp_server_version: str = "1.0.0"

    default_max_age_sec: int = 60
    semantic_cache_threshold: float = 0.86
    semantic_cache_recency_minutes: int = 5

    log_level: str = "INFO"

    nebula_host: str = "finance-mcp-nebula-graphd"
    nebula_port: int = 9669

    news_api_key: str = ""
    mcp_api_key: str = "dev_key_change_in_production"
    gemini_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
