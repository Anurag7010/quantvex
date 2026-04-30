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

CRYPTO_SYMBOLS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC"}


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
                cached_quote = json.loads(semantic_hit["response_text"])
                rate = settings.usd_inr_rate or 89.94
                
                return ToolResponse(
                    success=True,
                    data={
                        "symbol": symbol,
                        "price": cached_quote.get("price"),
                        "inr_price": round(cached_quote.get("price") * rate, 2)
                        if cached_quote.get("price") is not None
                        else None,
                        "usd_inr_rate": rate,
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

    # --- Crypto: route to Binance REST API before any stock connector ---
    clean_symbol = symbol.upper().replace("USDT", "").replace("-USD", "")
    if clean_symbol in CRYPTO_SYMBOLS:
        quote = await _fetch_crypto_quote_binance(clean_symbol)
        if quote:
            return quote
        # fall through to stock connectors only if Binance failed

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


async def _fetch_crypto_quote_binance(symbol: str) -> Optional[QuoteData]:
    """Fetch crypto price from Binance public REST API — no key required."""
    import httpx
    from datetime import datetime

    pair = f"{symbol}USDT"
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                price_usd = float(data["lastPrice"])
                volume = float(data.get("volume", 0))
                return QuoteData(
                    symbol=symbol,
                    price=price_usd,
                    timestamp=datetime.utcnow(),
                    data_source=DataSource.BINANCE,
                    volume=volume,
                )
    except Exception as e:
        logger.warning("binance_rest_failed", symbol=symbol, error=str(e))
    return None


def _quote_to_dict(quote: QuoteData) -> dict:
    """Convert QuoteData to dictionary for response"""
    rate = get_settings().usd_inr_rate or 89.94

    def to_inr(value: Optional[float]) -> Optional[float]:
        return round(value * rate, 2) if value is not None else None

    return {
        "symbol": quote.symbol,
        "price": quote.price,
        "inr_price": to_inr(quote.price),
        "usd_inr_rate": rate,
        "timestamp": quote.timestamp.isoformat(),
        "data_source": quote.data_source.value,
        "cache_hit": quote.cache_hit,
        "latency_ms": quote.latency_ms,
        "volume": quote.volume,
        "high": quote.high,
        "inr_high": to_inr(quote.high),
        "low": quote.low,
        "inr_low": to_inr(quote.low),
        "open": quote.open,
        "inr_open": to_inr(quote.open),
        "previous_close": quote.previous_close,
        "inr_previous_close": to_inr(quote.previous_close),
    }
