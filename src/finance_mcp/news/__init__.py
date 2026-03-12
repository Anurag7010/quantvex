"""
finance_mcp.news

News ingestion layer (Phase 3).

Modules
-------
news_client   — NewsClient: fetch articles from NewsAPI.org
event_parser  — EventParser: convert headlines to ParsedEvent objects
"""
from finance_mcp.news.news_client import NewsClient, NewsArticle
from finance_mcp.news.event_parser import EventParser, ParsedEvent, ImpactedEntity

__all__ = ["NewsClient", "NewsArticle", "EventParser", "ParsedEvent", "ImpactedEntity"]
