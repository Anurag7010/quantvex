"""
Hash-based semantic cache backed by Redis.

Replaces the former Qdrant + sentence-transformers implementation.
Public interface is identical so all callers (server.py, quote_latest.py) require no changes.
"""
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

_CACHE_PREFIX = "sem:"


def _cache_key(symbol: str, query_text: str) -> str:
    digest = hashlib.sha256(query_text.encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}{symbol.upper()}:{digest}"


class SemanticCacheClient:
    """Redis-backed query cache using SHA-256 hash keys.

    Drop-in replacement for the former Qdrant + sentence-transformers client.
    Exact-match caching only (no fuzzy similarity); TTL enforces the recency window.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._recency_seconds = settings.semantic_cache_recency_minutes * 60
        self._redis: Optional[Any] = None

    def _get_redis(self) -> Any:
        if self._redis is None:
            import redis as redis_lib
            settings = get_settings()
            self._redis = redis_lib.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                ssl=settings.redis_ssl,
                db=settings.redis_db,
                decode_responses=True,
            )
        return self._redis

    def initialize(self) -> bool:
        try:
            self._get_redis().ping()
            logger.info("semantic_cache_initialized")
            return True
        except Exception as e:
            logger.warning("semantic_cache_init_failed", error=str(e))
            return False

    def health(self) -> bool:
        try:
            self._get_redis().ping()
            return True
        except Exception as e:
            logger.error("semantic_cache_health_error", error=str(e))
            return False

    def search_similar(
        self,
        query_text: str,
        symbol: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 1,
    ) -> Optional[Dict[str, Any]]:
        if not symbol:
            return None
        key = _cache_key(symbol, query_text)
        try:
            raw = self._get_redis().get(key)
            if raw is None:
                logger.debug("semantic_cache_miss", query=query_text[:50])
                return None
            payload = json.loads(raw)
            logger.info("semantic_cache_hit", symbol=symbol, query=query_text[:50])
            return payload
        except Exception as e:
            logger.error("semantic_search_error", error=str(e))
            return None

    def store_response(
        self,
        agent_id: str,
        symbol: str,
        query_text: str,
        response_text: str,
    ) -> bool:
        key = _cache_key(symbol, query_text)
        payload = json.dumps({
            "response_text": response_text,
            "symbol": symbol.upper(),
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().timestamp(),
            "score": 1.0,
        })
        try:
            self._get_redis().setex(key, self._recency_seconds, payload)
            logger.info("semantic_cache_stored", symbol=symbol, query=query_text[:50])
            return True
        except Exception as e:
            logger.error("semantic_store_error", error=str(e))
            return False

    def get_collection_stats(self) -> Dict[str, Any]:
        try:
            count = len(self._get_redis().keys(f"{_CACHE_PREFIX}*"))
            return {"cached_entries": count}
        except Exception as e:
            logger.error("collection_stats_error", error=str(e))
            return {}


_semantic_cache: Optional[SemanticCacheClient] = None


def get_semantic_cache() -> SemanticCacheClient:
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCacheClient()
    return _semantic_cache
