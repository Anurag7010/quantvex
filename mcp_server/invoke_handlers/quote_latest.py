"""
Quote Latest Tool Handler
MCP tool: quote.latest
"""
import time
import json
from typing import Optional
from datetime import datetime
from mcp_server.utils.logging import get_logger
from mcp_server.utils.validation import InputValidator
from mcp_server.schemas import QuoteData, ToolResponse, DataSource
from mcp_server.config import get_settings
from cache.redis_client import get_redis_client
from cache.qdrant_client import get_semantic_cache
from connectors.alpha_vantage import get_alpha_vantage_connector
from connectors.finnhub import get_finnhub_connector
from graph.lineage_writer import get_lineage_writer

logger = get_logger(__name__)


async def handle_quote_latest(
    symbol: str,
    exchange: Optional[str] = None,
    max_age_sec: Optional[int] = None,
    agent_id: Optional[str] = None,
    query_text: Optional[str] = None
) -> ToolResponse:
    """
    Handle quote.latest invocation.

    Cache waterfall: Qdrant semantic cache → Redis hot cache → live connectors.
    Falls back through Finnhub → Alpha Vantage → Binance (crypto only).
    """
    start_time = time.time()
    settings = get_settings()
    
    try:
        # Validate inputs
        symbol = InputValidator.validate_symbol(symbol)
        exchange = InputValidator.validate_exchange(exchange)
        max_age_sec = InputValidator.validate_max_age_sec(max_age_sec) or settings.default_max_age_sec
        
        logger.info(
            "quote_latest_request",
            symbol=symbol,
            exchange=exchange,
            max_age_sec=max_age_sec
        )
        
        redis_client = get_redis_client()
        semantic_cache = get_semantic_cache()
        lineage_writer = get_lineage_writer()

        if query_text:
            semantic_hit = semantic_cache.search_similar(
                query_text=query_text,
                symbol=symbol,
                agent_id=agent_id
            )
            
            if semantic_hit:
                logger.info("semantic_cache_hit", symbol=symbol)
                latency_ms = (time.time() - start_time) * 1000
                
                return ToolResponse(
                    success=True,
                    data={
                        "symbol": symbol,
                        "price": json.loads(semantic_hit["response_text"]).get("price"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "data_source": DataSource.SEMANTIC_CACHE.value,
                        "cache_hit": True,
                        "latency_ms": latency_ms
                    },
                    cache_hit=True,
                    data_source=DataSource.SEMANTIC_CACHE.value,
                    latency_ms=latency_ms
                )
        
        if redis_client.is_connected():
            if redis_client.is_snapshot_fresh(symbol, max_age_sec):
                quote = redis_client.get_snapshot(symbol)
                
                if quote:
                    latency_ms = (time.time() - start_time) * 1000
                    quote.cache_hit = True
                    quote.latency_ms = latency_ms
                    quote.data_source = DataSource.REDIS_CACHE
                    
                    logger.info("redis_cache_hit", symbol=symbol)
                    
                    return ToolResponse(
                        success=True,
                        data=_quote_to_dict(quote),
                        cache_hit=True,
                        data_source=DataSource.REDIS_CACHE.value,
                        latency_ms=latency_ms
                    )
        
        quote = await _fetch_with_fallback(symbol, exchange)
        
        if not quote:
            latency_ms = (time.time() - start_time) * 1000
            return ToolResponse(
                success=False,
                error=f"Failed to fetch quote for {symbol}",
                latency_ms=latency_ms
            )
        
        if redis_client.is_connected():
            redis_client.set_snapshot(quote)

        if query_text and agent_id:
            semantic_cache.store_response(
                agent_id=agent_id,
                symbol=symbol,
                query_text=query_text,
                response_text=json.dumps(_quote_to_dict(quote))
            )
        
        if agent_id:
            lineage_writer.record_quote_fetch(quote, agent_id)
        
        latency_ms = (time.time() - start_time) * 1000
        quote.latency_ms = latency_ms
        
        logger.info(
            "quote_latest_response",
            symbol=symbol,
            price=quote.price,
            source=quote.data_source.value,
            latency_ms=latency_ms
        )
        
        return ToolResponse(
            success=True,
            data=_quote_to_dict(quote),
            cache_hit=False,
            data_source=quote.data_source.value,
            latency_ms=latency_ms
        )
        
    except ValueError as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("quote_latest_validation_error", error=str(e))
        return ToolResponse(
            success=False,
            error=str(e),
            latency_ms=latency_ms
        )
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("quote_latest_error", error=str(e))
        return ToolResponse(
            success=False,
            error=f"Internal error: {str(e)}",
            latency_ms=latency_ms
        )


async def _fetch_with_fallback(symbol: str, exchange: Optional[str] = None) -> Optional[QuoteData]:
    """Cascade through Binance (crypto) → Finnhub → Alpha Vantage."""
    
    is_crypto = any(x in symbol.upper() for x in ["USDT", "BTC", "ETH", "BNB"])

    if is_crypto:
        try:
            from connectors.binance_ws import get_binance_connector
            binance = get_binance_connector()
            tick = await binance.get_latest_price(symbol)
            if tick:
                return QuoteData(
                    symbol=tick.symbol,
                    price=tick.price,
                    timestamp=tick.timestamp,
                    data_source=DataSource.BINANCE,
                    volume=tick.volume
                )
        except Exception as e:
            logger.warning("binance_fallback_failed", error=str(e))

    try:
        finnhub = get_finnhub_connector()
        quote = await finnhub.get_quote(symbol)
        if quote and quote.price > 0:
            return quote
    except Exception as e:
        logger.warning("finnhub_fallback_failed", error=str(e))

    try:
        av = get_alpha_vantage_connector()
        quote = await av.get_quote(symbol)
        if quote and quote.price > 0:
            return quote
    except Exception as e:
        logger.warning("alpha_vantage_fallback_failed", error=str(e))
    
    return None


def _quote_to_dict(quote: QuoteData) -> dict:
    """Convert QuoteData to dictionary for response"""
    return {
        "symbol": quote.symbol,
        "price": quote.price,
        "timestamp": quote.timestamp.isoformat(),
        "data_source": quote.data_source.value,
        "cache_hit": quote.cache_hit,
        "latency_ms": quote.latency_ms,
        "volume": quote.volume,
        "high": quote.high,
        "low": quote.low,
        "open": quote.open,
        "previous_close": quote.previous_close
    }
