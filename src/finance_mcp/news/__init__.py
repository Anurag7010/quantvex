"""
finance_mcp.news

News ingestion layer (Phase 3).

Modules
-------
news_client   — NewsClient: fetch articles from NewsAPI.org
event_parser  — EventParser: convert headlines to ParsedEvent objects
"""
from finance_mcp.news.event_parser import EventParser, ImpactedEntity, ParsedEvent
from finance_mcp.news.news_client import NewsArticle, NewsClient

__all__ = ["NewsClient", "NewsArticle", "EventParser", "ParsedEvent", "ImpactedEntity"]
