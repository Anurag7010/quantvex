"""
Alpha Vantage REST Connector
Free tier - rate limited to 5 calls/minute
"""
import httpx
import time
from typing import Optional
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger
from mcp_server.schemas import QuoteData, DataSource
from connectors.exceptions import RateLimitError

logger = get_logger(__name__)


class AlphaVantageConnector:
    """Alpha Vantage REST API connector. Free tier: 5 calls/min, 500/day."""

    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self):
        settings = get_settings()
        self._api_key = settings.alpha_vantage_api_key
        self._client = httpx.AsyncClient(timeout=30.0)
        self._last_call_time = 0
        self._min_interval = 12.0  # Enforce 5 calls/minute max
    
    async def close(self):
        await self._client.aclose()

    def _respect_rate_limit(self):
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed
            logger.debug("rate_limit_wait", seconds=sleep_time)
            time.sleep(sleep_time)
        self._last_call_time = time.time()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((httpx.HTTPError, RateLimitError))
    )
    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        self._respect_rate_limit()
        start_time = time.time()
        
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol.upper(),
                "apikey": self._api_key
            }
            
            logger.info("alpha_vantage_request", symbol=symbol)
            
            response = await self._client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for rate limit or error messages
            if "Note" in data:
                logger.warning("alpha_vantage_rate_limit", message=data["Note"])
                raise RateLimitError(data["Note"])
            
            if "Error Message" in data:
                logger.error("alpha_vantage_error", message=data["Error Message"])
                return None
            
            # Parse Global Quote response
            quote_data = data.get("Global Quote", {})
            
            if not quote_data:
                logger.warning("alpha_vantage_empty_response", symbol=symbol)
                return None
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Normalize to unified schema
            quote = QuoteData(
                symbol=quote_data.get("01. symbol", symbol).upper(),
                price=float(quote_data.get("05. price", 0)),
                timestamp=datetime.utcnow(),
                data_source=DataSource.ALPHA_VANTAGE,
                cache_hit=False,
                latency_ms=latency_ms,
                volume=float(quote_data.get("06. volume", 0)) if quote_data.get("06. volume") else None,
                high=float(quote_data.get("03. high", 0)) if quote_data.get("03. high") else None,
                low=float(quote_data.get("04. low", 0)) if quote_data.get("04. low") else None,
                open=float(quote_data.get("02. open", 0)) if quote_data.get("02. open") else None,
                previous_close=float(quote_data.get("08. previous close", 0)) if quote_data.get("08. previous close") else None
            )
            
            logger.info(
                "alpha_vantage_quote_fetched",
                symbol=symbol,
                price=quote.price,
                latency_ms=latency_ms
            )
            
            return quote
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            logger.error("alpha_vantage_http_error", status=e.response.status_code)
            raise
        except Exception as e:
            logger.error("alpha_vantage_error", error=str(e))
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((httpx.HTTPError, RateLimitError))
    )
    async def get_intraday(self, symbol: str, interval: str = "5min") -> Optional[dict]:
        """Fetch intraday time series (limited on free tier)."""
        self._respect_rate_limit()
        
        try:
            params = {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol.upper(),
                "interval": interval,
                "apikey": self._api_key,
                "outputsize": "compact"
            }
            
            response = await self._client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if "Note" in data:
                raise RateLimitError(data["Note"])
            
            return data
            
        except Exception as e:
            logger.error("alpha_vantage_intraday_error", error=str(e))
            raise


# Singleton instance
_connector: Optional[AlphaVantageConnector] = None


def get_alpha_vantage_connector() -> AlphaVantageConnector:
    global _connector
    if _connector is None:
        _connector = AlphaVantageConnector()
    return _connector
