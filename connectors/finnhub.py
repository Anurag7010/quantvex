"""
Finnhub REST Connector
Free tier - 60 API calls/minute
"""
import httpx
import asyncio
import inspect
import time
from typing import Optional
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger
from mcp_server.schemas import QuoteData, DataSource
from connectors.exceptions import RateLimitError

logger = get_logger(__name__)


async def _response_json(response: httpx.Response) -> dict:
    payload = response.json()
    if inspect.isawaitable(payload):
        payload = await payload
    return payload


class FinnhubConnector:
    """Finnhub REST API connector. Free tier: 60 calls/min."""

    BASE_URL = "https://finnhub.io/api/v1"
    
    def __init__(self):
        settings = get_settings()
        self._api_key = settings.finnhub_api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0))
        self._last_call_time = 0
        self._min_interval = 1.0  # 60 calls/minute max
    
    async def close(self):
        await self._client.aclose()

    async def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed
            logger.debug("rate_limit_wait", seconds=sleep_time)
            await asyncio.sleep(sleep_time)
        self._last_call_time = time.time()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, RateLimitError))
    )
    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        await self._respect_rate_limit()
        start_time = time.time()
        
        try:
            headers = {"X-Finnhub-Token": self._api_key}
            params = {"symbol": symbol.upper()}
            
            logger.info("finnhub_request", symbol=symbol)
            
            response = await self._client.get(
                f"{self.BASE_URL}/quote",
                params=params,
                headers=headers
            )
            
            # Check for rate limit
            if response.status_code == 429:
                logger.warning("finnhub_rate_limit")
                raise RateLimitError("Rate limit exceeded")
            
            response.raise_for_status()
            data = await _response_json(response)
            
            # Check for empty response
            if not data or data.get("c") == 0:
                logger.warning("finnhub_empty_response", symbol=symbol)
                return None
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Normalize to unified schema
            # Finnhub response: c=current, h=high, l=low, o=open, pc=previous close, t=timestamp
            quote = QuoteData(
                symbol=symbol.upper(),
                price=float(data.get("c", 0)),
                timestamp=datetime.utcnow(),
                data_source=DataSource.FINNHUB,
                cache_hit=False,
                latency_ms=latency_ms,
                high=float(data.get("h", 0)) if data.get("h") else None,
                low=float(data.get("l", 0)) if data.get("l") else None,
                open=float(data.get("o", 0)) if data.get("o") else None,
                previous_close=float(data.get("pc", 0)) if data.get("pc") else None
            )
            
            logger.info(
                "finnhub_quote_fetched",
                symbol=symbol,
                price=quote.price,
                latency_ms=latency_ms
            )
            
            return quote
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            logger.error("finnhub_http_error", status=e.response.status_code)
            raise
        except Exception as e:
            logger.error("finnhub_error", error=str(e))
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, RateLimitError))
    )
    async def get_company_profile(self, symbol: str) -> Optional[dict]:
        """
        Fetch company profile data
        """
        await self._respect_rate_limit()
        
        try:
            headers = {"X-Finnhub-Token": self._api_key}
            params = {"symbol": symbol.upper()}
            
            response = await self._client.get(
                f"{self.BASE_URL}/stock/profile2",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            return await _response_json(response)
            
        except Exception as e:
            logger.error("finnhub_profile_error", error=str(e))
            raise
    
    async def search_symbol(self, query: str) -> list:
        """
        Search for symbols matching query
        """
        await self._respect_rate_limit()
        
        try:
            headers = {"X-Finnhub-Token": self._api_key}
            params = {"q": query}
            
            response = await self._client.get(
                f"{self.BASE_URL}/search",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            data = await _response_json(response)
            return data.get("result", [])
            
        except Exception as e:
            logger.error("finnhub_search_error", error=str(e))
            return []


# Singleton instance
_connector: Optional[FinnhubConnector] = None


def get_finnhub_connector() -> FinnhubConnector:
    global _connector
    if _connector is None:
        _connector = FinnhubConnector()
    return _connector
