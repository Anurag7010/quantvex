"""News client for financial headlines sourced from NewsData.io."""

from __future__ import annotations

import hashlib
import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
import certifi

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEWSDATA_NEWS_URL = "https://newsdata.io/api/1/latest"

# Hard ceiling on articles per request — prevents accidental large fetches.
_MAX_RESULTS_CAP = 100

# Default page size sent to NewsData.io when the caller does not specify a limit.
_DEFAULT_PAGE_SIZE = 10

# HTTP request timeout (connect + read)
_REQUEST_TIMEOUT_SEC = 15.0

# Language filter — restrict to English articles by default.
_DEFAULT_LANGUAGE = "en"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class NewsArticle:
    """
    Structured representation of a single news article.

    Attributes
    ----------
    title        : str         — headline text
    description  : str         — article summary / lead paragraph
    url          : str         — full article URL
    published_at : datetime    — UTC publication timestamp
    source_name  : str         — publisher name (e.g. "Reuters")
    query        : str         — the search query that surfaced this article
    article_id   : str         — stable short id derived from url + title
    """
    title: str
    description: str
    url: str
    published_at: datetime
    source_name: str
    query: str = field(default="")
    article_id: str = field(default="")

    def as_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "source_name": self.source_name,
            "query": self.query,
            "article_id": self.article_id,
        }


# ---------------------------------------------------------------------------
# NewsClient
# ---------------------------------------------------------------------------

class NewsClient:
    """
    Thin async client for the NewsData.io news endpoint.

    Parameters
    ----------
    api_key : str | None
        NewsData.io key. When ``None`` the key is read from the MCP settings
        (``settings.newsdata_api_key``). Pass explicitly in tests.
    language : str
        ISO-639-1 language code to filter results. Default ``"en"``.
    timeout : float
        HTTP request timeout in seconds. Default 15 s.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        language: str = _DEFAULT_LANGUAGE,
        timeout: float = _REQUEST_TIMEOUT_SEC,
    ) -> None:
        if api_key is None:
            from mcp_server.config import get_settings

            settings = get_settings()
            api_key = settings.newsdata_api_key or settings.news_api_key

        if not api_key or api_key.strip() == "":
            raise RuntimeError(
                "NEWSDATA_API_KEY is not set. Get a free key at https://newsdata.io "
                "and add it to your .env file."
            )

        self._api_key = api_key
        self._language = language
        self._timeout = timeout
        self.base_url = NEWSDATA_NEWS_URL

    async def fetch_market_news(
        self,
        query: str,
        limit: int = _DEFAULT_PAGE_SIZE,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[NewsArticle]:
        """Fetch news articles matching ``query`` from NewsData.io."""
        return await self.fetch_articles(
            query=query,
            max_results=limit,
            from_date=from_date,
            to_date=to_date,
        )

    async def fetch_articles(
        self,
        query: str,
        max_results: int = _DEFAULT_PAGE_SIZE,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[NewsArticle]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        query = query.strip()
        if len(query) > 500:
            raise ValueError("query must not exceed 500 characters")

        if not isinstance(max_results, int) or isinstance(max_results, bool):
            raise ValueError("max_results must be a positive integer")
        if max_results < 1:
            raise ValueError("max_results must be at least 1")

        page_size = min(max_results, _MAX_RESULTS_CAP)
        words = query.split()
        ladder = list(
            dict.fromkeys(
                [
                    " ".join(words[:3]),
                    " ".join(words[:2]),
                    words[0],
                ]
            )
        )

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        ) as session:
            for q in ladder:
                articles = await self._fetch_single(
                    session,
                    q,
                    page_size,
                    from_date=from_date,
                    to_date=to_date,
                )
                if articles:
                    return articles
        return []

    async def _fetch_single(
        self,
        session: aiohttp.ClientSession,
        query: str,
        size: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[NewsArticle]:
        params = {
            "apikey": self._api_key,
            "q": query,
            "language": self._language,
            "size": min(size, 10),
        }
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        try:
            async with session.get(self.base_url, params=params) as resp:
                if resp.status != 200:
                    logger.info(
                        "newsdata_fetch_status query=%r status=%s",
                        query,
                        resp.status,
                    )
                    return []
                payload = await resp.json()
        except Exception as exc:
            logger.warning("newsdata_fetch_failed query=%r error=%s", query, exc)
            return []

        status = str(payload.get("status", "")).lower()
        if status and status not in {"ok", "success"}:
            return []

        articles = self._parse_results(payload.get("results", []))
        for article in articles:
            article.query = query

        logger.info(
            "newsdata_fetch_done query=%r returned=%d",
            query,
            len(articles),
        )
        return articles

    def _parse_results(self, results: list) -> List[NewsArticle]:
        articles: List[NewsArticle] = []
        for item in results:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            url = (item.get("link") or item.get("url") or "").strip()
            article_id = hashlib.md5((url + title).encode("utf-8")).hexdigest()[:12]
            description = (item.get("description") or title).strip()
            source_name = item.get("source_id") or item.get("source_name") or "unknown"
            published_raw = item.get("pubDate") or item.get("publishedAt") or ""
            articles.append(
                NewsArticle(
                    title=title,
                    description=description,
                    url=url,
                    published_at=_parse_datetime(published_raw),
                    source_name=source_name,
                    article_id=article_id,
                )
            )
        return articles

    async def fetch_articles_fallback(self, query: str) -> List["NewsArticle"]:
        """Fallback: Google News RSS — no key required, server-side only."""
        rss_url = (
            f"https://news.google.com/rss/search"
            f"?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=10.0),
            ) as session:
                async with session.get(rss_url) as resp:
                    if resp.status == 200:
                        return self._parse_rss(await resp.text(), query)
        except Exception as exc:
            logger.warning("newsdata_rss_fallback_failed query=%r error=%s", query, exc)
        return []

    def _parse_rss(self, xml_content: str, query: str = "") -> List["NewsArticle"]:
        """Parse a Google News RSS feed into NewsArticle instances."""
        import xml.etree.ElementTree as ET

        articles: List[NewsArticle] = []
        try:
            root = ET.fromstring(xml_content)
            items = root.findall(".//item")[:10]
            for item in items:
                title = (item.findtext("title") or "").strip()
                url = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                if title and url:
                    articles.append(
                        NewsArticle(
                            title=title,
                            description=title,
                            url=url,
                            published_at=_parse_datetime(pub_date),
                            source_name="Google News RSS",
                            query=query,
                        )
                    )
        except Exception as exc:
            logger.warning("newsdata_rss_parse_failed error=%s", exc)
        return articles

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


def _parse_datetime(raw: str) -> datetime:
    """Parse a timestamp string into a UTC datetime."""
    if not raw:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.warning("newsdata_unparseable_date raw=%r", raw)
        return datetime.now(tz=timezone.utc)
