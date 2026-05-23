"""
Redis Client for Hot Cache and Streams
"""
import redis
import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger
from mcp_server.schemas import QuoteData, StreamTick, DataSource

logger = get_logger(__name__)


class RedisClient:
    """Redis client for snapshot caching and stream ingestion."""

    SNAPSHOT_PREFIX = "snapshot:"
    STREAM_PREFIX = "stream:"
    
    def __init__(self):
        settings = get_settings()
        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            ssl=settings.redis_ssl,
            db=settings.redis_db,
            decode_responses=True,
        )
        self._connected = False
    
    def connect(self) -> bool:
        try:
            self._client.ping()
            self._connected = True
            logger.info("redis_connected", host=get_settings().redis_host)
            return True
        except redis.ConnectionError as e:
            logger.error("redis_connection_failed", error=str(e))
            self._connected = False
            return False
    
    def is_connected(self) -> bool:
        """Check if connected to Redis"""
        if not self._connected:
            return self.connect()
        try:
            self._client.ping()
            return True
        except redis.ConnectionError:
            self._connected = False
            return False
    
    def get_snapshot(self, symbol: str) -> Optional[QuoteData]:
        key = f"{self.SNAPSHOT_PREFIX}{symbol.upper()}"
        
        try:
            data = self._client.hgetall(key)
            
            if not data:
                logger.debug("snapshot_miss", symbol=symbol)
                return None
            
            quote = QuoteData(
                symbol=data.get("symbol", symbol),
                price=float(data.get("price", 0)),
                timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                data_source=DataSource(data.get("source", "redis_cache")),
                cache_hit=True,
                latency_ms=float(data.get("latency_ms", 0)),
                volume=float(data["volume"]) if data.get("volume") else None
            )
            
            logger.debug("snapshot_hit", symbol=symbol, age_sec=self._get_snapshot_age(symbol))
            return quote
            
        except Exception as e:
            logger.error("snapshot_get_error", symbol=symbol, error=str(e))
            return None
    
    def set_snapshot(self, quote: QuoteData) -> bool:
        key = f"{self.SNAPSHOT_PREFIX}{quote.symbol.upper()}"
        
        try:
            data = {
                "symbol": quote.symbol,
                "price": str(quote.price),
                "timestamp": quote.timestamp.isoformat(),
                "source": quote.data_source.value,
                "latency_ms": str(quote.latency_ms)
            }
            
            if quote.volume is not None:
                data["volume"] = str(quote.volume)
            
            self._client.hset(key, mapping=data)
            logger.info("snapshot_set", symbol=quote.symbol, price=quote.price)
            return True
            
        except Exception as e:
            logger.error("snapshot_set_error", symbol=quote.symbol, error=str(e))
            return False
    
    def get_snapshot_age(self, symbol: str) -> Optional[float]:
        """Get age of snapshot in seconds"""
        return self._get_snapshot_age(symbol)
    
    def _get_snapshot_age(self, symbol: str) -> Optional[float]:
        """Internal: Get age of snapshot in seconds"""
        key = f"{self.SNAPSHOT_PREFIX}{symbol.upper()}"
        
        try:
            timestamp_str = self._client.hget(key, "timestamp")
            if not timestamp_str:
                return None
            
            timestamp = datetime.fromisoformat(timestamp_str)
            age = (datetime.utcnow() - timestamp).total_seconds()
            return age
            
        except Exception as e:
            logger.error("snapshot_age_error", symbol=symbol, error=str(e))
            return None
    
    def is_snapshot_fresh(self, symbol: str, max_age_sec: int) -> bool:
        """Check if snapshot is fresh enough"""
        age = self._get_snapshot_age(symbol)
        if age is None:
            return False
        return age < max_age_sec
    
    def add_to_stream(self, tick: StreamTick) -> Optional[str]:
        """
        Add tick to Redis stream
        Returns stream entry ID or None on failure
        """
        key = f"{self.STREAM_PREFIX}{tick.symbol.upper()}"
        
        try:
            entry = {
                "symbol": tick.symbol,
                "price": str(tick.price),
                "volume": str(tick.volume),
                "ts": tick.timestamp.isoformat(),
                "source": tick.data_source.value
            }
            
            if tick.trade_id:
                entry["trade_id"] = tick.trade_id
            
            entry_id = self._client.xadd(key, entry, maxlen=10000)
            logger.debug("stream_add", symbol=tick.symbol, entry_id=entry_id)
            return entry_id
            
        except Exception as e:
            logger.error("stream_add_error", symbol=tick.symbol, error=str(e))
            return None
    
    def read_stream(self, symbol: str, count: int = 100, last_id: str = "0") -> List[StreamTick]:
        """Read entries from stream"""
        key = f"{self.STREAM_PREFIX}{symbol.upper()}"
        
        try:
            entries = self._client.xread({key: last_id}, count=count, block=0)
            
            ticks = []
            for stream_name, messages in entries:
                for msg_id, data in messages:
                    tick = StreamTick(
                        symbol=data.get("symbol", symbol),
                        price=float(data.get("price", 0)),
                        volume=float(data.get("volume", 0)),
                        timestamp=datetime.fromisoformat(data.get("ts", datetime.utcnow().isoformat())),
                        trade_id=data.get("trade_id"),
                        data_source=DataSource(data.get("source", "binance"))
                    )
                    ticks.append(tick)
            
            return ticks
            
        except Exception as e:
            logger.error("stream_read_error", symbol=symbol, error=str(e))
            return []
    
    def get_latest_from_stream(self, symbol: str) -> Optional[StreamTick]:
        """Get the most recent tick from stream"""
        key = f"{self.STREAM_PREFIX}{symbol.upper()}"
        
        try:
            entries = self._client.xrevrange(key, count=1)
            
            if not entries:
                return None
            
            msg_id, data = entries[0]
            
            return StreamTick(
                symbol=data.get("symbol", symbol),
                price=float(data.get("price", 0)),
                volume=float(data.get("volume", 0)),
                timestamp=datetime.fromisoformat(data.get("ts", datetime.utcnow().isoformat())),
                trade_id=data.get("trade_id"),
                data_source=DataSource(data.get("source", "binance"))
            )
            
        except Exception as e:
            logger.error("stream_latest_error", symbol=symbol, error=str(e))
            return None
    
    def get_stream_length(self, symbol: str) -> int:
        """Get number of entries in stream"""
        key = f"{self.STREAM_PREFIX}{symbol.upper()}"
        try:
            return self._client.xlen(key)
        except Exception:
            return 0
    
    def close(self):
        """Close Redis connection"""
        try:
            self._client.close()
            self._connected = False
            logger.info("redis_disconnected")
        except Exception as e:
            logger.error("redis_close_error", error=str(e))


# Singleton instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
