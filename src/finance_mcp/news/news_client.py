"""
Phase 3 — NewsAPI Client

Fetches financial news articles from the NewsAPI.org ``/v2/everything``
endpoint and returns them as ``NewsArticle`` dataclass instances.

Security notes
--------------
* The API key is read from settings/environment — never hard-coded.
* Query strings are passed directly to the NewsAPI ``q`` parameter as
  legitimate search terms; they are not interpolated into any SQL/nGQL
  statement.
* HTTP responses are parsed with a safe JSON decoder; no ``eval`` or
  ``exec`` is used.
* Timeouts and a maximum-result cap prevent resource exhaustion.

Usage
-----
    from finance_mcp.news.news_client import NewsClient

    client = NewsClient()
    articles = await client.fetch_market_news("semiconductor", limit=5)
    for a in articles:
        print(a.title, a.published_at)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"

# Hard ceiling on articles per request — prevents accidental large fetches.
_MAX_RESULTS_CAP = 100

# Default page size sent to NewsAPI when the caller does not specify a limit.
_DEFAULT_PAGE_SIZE = 10

# HTTP request timeout (connect + read)
_REQUEST_TIMEOUT_SEC = 15.0

# Language filter — restrict to English articles by default.
_DEFAULT_LANGUAGE = "en"

# Sort order sent to NewsAPI.
_SORT_BY = "publishedAt"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class NewsArticle:
    """
    Structured representation of a single NewsAPI article.

    Attributes
    ----------
    title        : str         — headline text
    description  : str         — article summary / lead paragraph
    url          : str         — full article URL
    published_at : datetime    — UTC publication timestamp
    source_name  : str         — publisher name (e.g. "Reuters")
    query        : str         — the search query that surfaced this article
    """
    title: str
    description: str
    url: str
    published_at: datetime
    source_name: str
    query: str = field(default="")

    def as_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "source_name": self.source_name,
            "query": self.query,
        }


# ---------------------------------------------------------------------------
# NewsClient
# ---------------------------------------------------------------------------

class NewsClient:
    """
    Thin async client for the NewsAPI ``/v2/everything`` endpoint.

    Parameters
    ----------
    api_key : str | None
        NewsAPI key.  When ``None`` the key is read from the MCP settings
        (``settings.news_api_key``).  Pass explicitly in tests.
    language : str
        ISO-639-1 language code to filter results.  Default ``"en"``.
    timeout : float
        HTTP request timeout in seconds.  Default 15 s.

    Examples
    --------
    Standalone (sync test)::

        import asyncio
        from finance_mcp.news.news_client import NewsClient

        async def main():
            client = NewsClient(api_key="YOUR_KEY")
            articles = await client.fetch_market_news("semiconductor", limit=5)
            for a in articles:
                print(a.title)

        asyncio.run(main())

    With settings from environment::

        client = NewsClient()          # reads NEWS_API_KEY env var
        articles = await client.fetch_market_news("lithium", limit=10)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        language: str = _DEFAULT_LANGUAGE,
        timeout: float = _REQUEST_TIMEOUT_SEC,
    ) -> None:
        if api_key is None:
            # Defer import so this module can be imported without FastAPI
            from mcp_server.config import get_settings
            api_key = get_settings().news_api_key

        if not api_key or api_key.strip() == "":
            raise ValueError(
                "NewsClient: API key is required. "
                "Set NEWS_API_KEY in your .env file or pass api_key= directly."
            )

        self._api_key = api_key
        self._language = language
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_market_news(
        self,
        query: str,
        limit: int = _DEFAULT_PAGE_SIZE,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[NewsArticle]:
        """
        Fetch news articles matching ``query`` from NewsAPI.

        Parameters
        ----------
        query : str
            Search terms sent to NewsAPI ``q`` parameter.
            Example: ``"semiconductor"`` or ``"lithium battery supply"``.
            Must be a non-empty string, 1–500 characters.
        limit : int
            Maximum number of articles to return.  Capped at
            ``_MAX_RESULTS_CAP`` (100).  Default 10.
        from_date : str | None
            Optional ISO-8601 date lower bound, e.g. ``"2026-01-01"``.
            Passed directly to NewsAPI ``from`` parameter.
        to_date : str | None
            Optional ISO-8601 date upper bound, e.g. ``"2026-03-09"``.
            Passed directly to NewsAPI ``to`` parameter.

        Returns
        -------
        List[NewsArticle]
            Articles sorted by ``publishedAt`` descending (NewsAPI default
            when ``sortBy=publishedAt``).  May be an empty list if no
            articles match or all articles have empty headlines.

        Raises
        ------
        ValueError
            When ``query`` is empty/invalid or ``limit`` is out of range.
        httpx.HTTPStatusError
            When NewsAPI returns a non-2xx status code.
        httpx.TimeoutException
            When the request exceeds the configured timeout.
        RuntimeError
            When NewsAPI returns a non-OK status in the response body
            (e.g. ``"apiKeyInvalid"``).
        """
        # ----------------------------------------------------------------
        # Input validation
        # ----------------------------------------------------------------
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        query = query.strip()
        if len(query) > 500:
            raise ValueError("query must not exceed 500 characters")

        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be a positive integer")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        page_size = min(limit, _MAX_RESULTS_CAP)

        # ----------------------------------------------------------------
        # Build request parameters
        # ----------------------------------------------------------------
        params: dict = {
            "q": query,
            "language": self._language,
            "sortBy": _SORT_BY,
            "pageSize": page_size,
            "apiKey": self._api_key,
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        logger.info(
            "newsapi_fetch query=%r limit=%d language=%s",
            query, page_size, self._language,
        )

        # ----------------------------------------------------------------
        # HTTP request
        # ----------------------------------------------------------------
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.get(NEWSAPI_EVERYTHING_URL, params=params)

        # ----------------------------------------------------------------
        # Error handling
        # ----------------------------------------------------------------
        response.raise_for_status()  # raises httpx.HTTPStatusError on 4xx/5xx

        payload = response.json()

        if payload.get("status") != "ok":
            code = payload.get("code", "unknown")
            message = payload.get("message", "No error message returned")
            raise RuntimeError(
                f"NewsAPI error [{code}]: {message}"
            )

        # ----------------------------------------------------------------
        # Parse articles
        # ----------------------------------------------------------------
        raw_articles = payload.get("articles", [])
        articles: List[NewsArticle] = []

        for raw in raw_articles:
            title = (raw.get("title") or "").strip()
            description = (raw.get("description") or "").strip()
            url = (raw.get("url") or "").strip()
            source_name = (raw.get("source") or {}).get("name") or "Unknown"
            published_raw = raw.get("publishedAt") or ""

            # Skip articles NewsAPI returns with placeholder titles
            if not title or title == "[Removed]":
                continue

            published_at = _parse_datetime(published_raw)

            articles.append(
                NewsArticle(
                    title=title,
                    description=description,
                    url=url,
                    published_at=published_at,
                    source_name=source_name,
                    query=query,
                )
            )

        logger.info(
            "newsapi_fetch_done query=%r total_api=%d returned=%d",
            query,
            payload.get("totalResults", 0),
            len(articles),
        )
        return articles

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    async def fetch_semiconductor_news(self, limit: int = 10) -> List[NewsArticle]:
        """Shortcut for semiconductor supply-chain news."""
        return await self.fetch_market_news(
            "semiconductor OR chip shortage OR foundry", limit=limit
        )

    async def fetch_lithium_news(self, limit: int = 10) -> List[NewsArticle]:
        """Shortcut for lithium / battery metals news."""
        return await self.fetch_market_news(
            "lithium OR battery metals OR EV supply chain", limit=limit
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_datetime(raw: str) -> datetime:
    """
    Parse an ISO-8601 datetime string from NewsAPI into a UTC datetime.

    NewsAPI publishes timestamps as ``"2026-03-09T12:00:00Z"``.
    Falls back to the current UTC time when the string is absent or
    unparseable — the article is still useful even without a precise
    timestamp.
    """
    if not raw:
        return datetime.now(tz=timezone.utc)
    try:
        # Python 3.11+ handles trailing Z natively; handle older too.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.warning("newsapi_unparseable_date raw=%r", raw)
        return datetime.now(tz=timezone.utc)
