"""
Analyze News Impact Tool Handler
MCP tool: analyze_news_impact

Real-time pipeline:
  1. Fetch live news from NewsAPI using the caller's query
  2. Parse each article for disruption signals and affected entities
     (companies named in headlines AND commodities like crude oil, semiconductors)
  3. Write parsed events to Memgraph (IMPACTS edges)
  4. For every company entity found → trace downstream DEPENDS_ON cascade
  5. For every commodity entity found → look up which companies REQUIRE it,
     then trace downstream cascade from those companies
  6. Return a structured result: news headlines + directly affected entities
     + full downstream cascade map

Security
--------
* All graph writes and reads go through GraphClient which enforces
  parameterised Cypher and VID validation — no injection surface.
* The news query string is passed only to the NewsAPI ``q`` param (never
  interpolated into nGQL).
* Results are validated before being returned to the LLM.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from mcp_server.config import get_settings
from mcp_server.schemas import ToolResponse
from mcp_server.utils.logging import get_logger
from finance_mcp.graph.client import GraphClient
from finance_mcp.ingestion.pipeline import run_news_ingestion_pipeline

logger = get_logger(__name__)

_DEFAULT_LIMIT: int = 10
_MAX_LIMIT: int = 20
_DEFAULT_MAX_HOPS: int = 2
_MAX_HOPS_LIMIT: int = 5


async def handle_news_analysis(
    query: str,
    limit: int = _DEFAULT_LIMIT,
    max_hops: int = _DEFAULT_MAX_HOPS,
    ticker: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> ToolResponse:
    """
    Fetch live news, parse disruption events, ingest them into the graph,
    and return a full supply-chain impact cascade.

    Parameters
    ----------
    query    : str        — NewsAPI search query, e.g. "Iran USA war oil sanctions"
    limit    : int        — number of articles to fetch (1–20, default 10)
    max_hops : int        — supply-chain traversal depth (1–5, default 2)
    ticker   : str | None — known company/commodity VID to ALWAYS trace in the
                            graph regardless of what the news pipeline finds.
                            Use this as a fallback anchor so graph traversal
                            runs even when no articles are returned or news
                            parsing does not recognize the entity.
    agent_id : str        — optional caller identifier for logging

    Returns
    -------
    ToolResponse
        success=True :
            data = {
                "query": str,
                "articles_fetched": int,
                "events_found": int,
                "events_ingested": int,
                "news_events": [
                    {"headline", "severity", "event_type", "published_at", "source_url"}
                ],
                "directly_affected": [
                    {"ticker", "name", "type": "company"|"commodity"}
                ],
                "downstream_cascade": {
                    ticker: [{"ticker", "name", "sector"}, ...]
                },
                "total_cascade_companies": int,
            }
        success=False : error message
    """
    start_time = time.time()
    settings = get_settings()

    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------
    if not isinstance(query, str) or not query.strip():
        return ToolResponse(success=False, error="'query' must be a non-empty string.")
    query = query.strip()
    if len(query) > 500:
        return ToolResponse(success=False, error="'query' must not exceed 500 characters.")

    if isinstance(limit, bool) or not isinstance(limit, int):
        limit = _DEFAULT_LIMIT
    limit = max(1, min(limit, _MAX_LIMIT))

    if isinstance(max_hops, bool) or not isinstance(max_hops, int):
        max_hops = _DEFAULT_MAX_HOPS
    max_hops = max(1, min(max_hops, _MAX_HOPS_LIMIT))

    logger.info(
        "news_analysis_request",
        query=query,
        limit=limit,
        max_hops=max_hops,
        agent_id=agent_id,
    )

    # ------------------------------------------------------------------
    # Stage 1+2+3: fetch news → parse events → ingest to graph
    # Errors here are soft-failures: we fall through with empty collections
    # so that the ticker-anchor fallback can still trigger a graph trace.
    # ------------------------------------------------------------------
    pipeline_result = None
    pipeline_error: Optional[str] = None
    try:
        pipeline_result = await run_news_ingestion_pipeline(
            query=query,
            limit=limit,
            memgraph_host=settings.memgraph_host,
            memgraph_port=settings.memgraph_port,
        )
    except RuntimeError as exc:
        # Surface real errors (bad API key, rate limit, etc.) with agent_note
        pipeline_error = str(exc).strip() or repr(exc) or type(exc).__name__
        logger.error("news_analysis_pipeline_error", error=pipeline_error)
        if not ticker:
            return ToolResponse(
                success=True,
                data={
                    "query": query,
                    "articles_found": 0,
                    "articles_fetched": 0,
                    "events_found": 0,
                    "events_ingested": 0,
                    "direct_entities": [],
                    "directly_affected": [],
                    "cascade": [],
                    "downstream_cascade": {},
                    "total_cascade_companies": 0,
                    "news_events": [],
                    "error": pipeline_error,
                    "pipeline_error": pipeline_error,
                    "news_available": False,
                    "agent_note": (
                        f"News fetch failed: {pipeline_error}. "
                        "Tell the user you attempted to fetch live news but encountered an error. "
                        "Provide relevant context from your training data with a clear disclaimer "
                        "that it may not reflect the latest developments."
                    ),
                },
            )
        # ticker anchor present — fall through so graph trace can still run
    except Exception as exc:
        pipeline_error = str(exc).strip() or repr(exc) or type(exc).__name__
        logger.error("news_analysis_pipeline_error", error=pipeline_error)
        if not ticker:
            return ToolResponse(
                success=True,
                data={
                    "query": query,
                    "articles_found": 0,
                    "articles_fetched": 0,
                    "events_found": 0,
                    "events_ingested": 0,
                    "news_events": [],
                    "directly_affected": [],
                    "downstream_cascade": {},
                    "total_cascade_companies": 0,
                    "error": f"Unexpected error: {pipeline_error}",
                    "pipeline_error": pipeline_error,
                    "news_available": False,
                    "agent_note": "Tool failed unexpectedly. Acknowledge this to the user.",
                },
            )
        # Do NOT return yet — ticker-anchor fallback may still yield graph data.

    # ------------------------------------------------------------------
    # Collect unique entities from parsed events (skip when pipeline failed)
    # ------------------------------------------------------------------
    company_entities: Dict[str, str] = {}   # ticker -> name
    commodity_entities: Dict[str, str] = {} # commodity_id -> name
    news_events: List[dict] = []

    if pipeline_result is not None:
        for event in pipeline_result.parsed_events:
            news_events.append(
                {
                    "headline": event.description,
                    "severity": event.severity,
                    "event_type": event.event_type,
                    "published_at": event.published_at.isoformat(),
                    "source_url": event.source_url,
                }
            )
            for entity in event.impacted_entities:
                if entity.entity_type == "company":
                    company_entities[entity.entity_id] = entity.name
                else:
                    commodity_entities[entity.entity_id] = entity.name

    # ------------------------------------------------------------------
    # Ticker anchor: when the caller knows which company or commodity is at
    # the centre of the disruption, always include it — even if the news NER
    # missed it or the pipeline failed entirely.
    # Commodity VIDs go into commodity_entities and are traced directly;
    # GraphClient.trace_impact handles Commodity -> REQUIRES cascades.
    # ------------------------------------------------------------------
    _KNOWN_COMMODITY_VIDS = frozenset({
        "CRUDE_OIL", "NATURAL_GAS", "COAL", "SEMICONDUCTOR_WAFER",
        "LITHIUM", "COBALT", "COPPER", "RARE_EARTH", "ALUMINUM", "STEEL",
        "CORN", "WHEAT", "SOYBEANS", "COFFEE", "SUGAR", "PALM_OIL",
        "SHIPPING_CONTAINERS", "SEMICONDUCTOR_CHIPS", "SILICON", "NEON_GAS",
    })
    if ticker:
        ticker = ticker.strip().upper()
        if ticker:
            if ticker in _KNOWN_COMMODITY_VIDS:
                if ticker not in commodity_entities:
                    commodity_entities[ticker] = ticker
            elif ticker not in company_entities:
                # Name is unknown at this point; the graph client will supply it
                # during the trace — we just need the VID in the set.
                company_entities[ticker] = ticker

    # ------------------------------------------------------------------
    # Graceful no-content response — nothing to trace in the graph
    # ------------------------------------------------------------------
    if not company_entities and not commodity_entities:
        if pipeline_error:
            note = (
                f"The news pipeline encountered an error ({pipeline_error}) and "
                "no company or commodity entities could be extracted. "
                "You can use trace_supply_chain_impact directly with a known ticker."
            )
        else:
            note = (
                "No supply-chain disruption signals were detected in the retrieved "
                "articles. The event may not have matched any tracked company or "
                "commodity. Try a more specific query, or use "
                "trace_supply_chain_impact with a known ticker."
            )
        return ToolResponse(
            success=True,
            data={
                "query": query,
                "articles_fetched": 0 if pipeline_result is None else pipeline_result.articles_fetched,
                "events_found": 0,
                "events_ingested": 0,
                "news_events": [],
                "directly_affected": [],
                "downstream_cascade": {},
                "total_cascade_companies": 0,
                "message": note,
                "pipeline_error": pipeline_error,
                "news_available": False,
            },
        )

    # ------------------------------------------------------------------
    # Stage 4+5: trace supply-chain cascade from each affected entity
    # ------------------------------------------------------------------
    downstream_cascade: Dict[str, List[dict]] = {}

    if company_entities or commodity_entities:
        try:
            with GraphClient(
                host=settings.memgraph_host,
                port=settings.memgraph_port,
            ) as client:
                # Directly named companies → trace downstream dependents
                for ticker in company_entities:
                    try:
                        impacted = client.trace_impact(ticker, max_hops)
                        if impacted:
                            downstream_cascade[ticker] = impacted
                    except Exception as exc:
                        logger.warning(
                            "news_analysis_trace_error ticker=%s error=%s",
                            ticker, exc,
                        )

                # Commodity entities -> trace commodity anchors directly.
                for commodity_id, commodity_name in commodity_entities.items():
                    try:
                        impacted = client.trace_impact(commodity_id, max_hops)
                        if impacted:
                            downstream_cascade[commodity_id] = impacted
                            for co in impacted:
                                company_entities.setdefault(co["ticker"], co["name"])
                    except Exception as exc:
                        logger.warning(
                            "news_analysis_commodity_error commodity=%s error=%s",
                            commodity_id, exc,
                        )
        except Exception as exc:
            err = str(exc).strip() or repr(exc) or type(exc).__name__
            logger.error("news_analysis_graph_error", error=err)
            # Return partial results rather than failing entirely
            return ToolResponse(
                success=False,
                error=f"Graph query failed: {err}",
            )

    # ------------------------------------------------------------------
    # Build response
    # ------------------------------------------------------------------
    directly_affected = [
        {"ticker": t, "name": n, "type": "company"}
        for t, n in company_entities.items()
    ] + [
        {"ticker": c, "name": n, "type": "commodity"}
        for c, n in commodity_entities.items()
    ]

    # Count unique downstream companies across all cascade entries
    cascade_tickers: set = set()
    for companies in downstream_cascade.values():
        for c in companies:
            cascade_tickers.add(c["ticker"])

    latency_ms = (time.time() - start_time) * 1000

    articles_fetched = 0 if pipeline_result is None else pipeline_result.articles_fetched
    events_parsed   = 0 if pipeline_result is None else pipeline_result.events_parsed
    events_ingested = 0 if pipeline_result is None else pipeline_result.succeeded

    logger.info(
        "news_analysis_response articles=%d events=%d direct=%d cascade=%d latency=%.0fms",
        articles_fetched,
        events_parsed,
        len(directly_affected),
        len(cascade_tickers),
        latency_ms,
    )

    return ToolResponse(
        success=True,
        data={
            "query": query,
            "articles_fetched": articles_fetched,
            "events_found": events_parsed,
            "events_ingested": events_ingested,
            "news_events": news_events,
            "directly_affected": directly_affected,
            "downstream_cascade": downstream_cascade,
            "total_cascade_companies": len(cascade_tickers),
            "news_available": articles_fetched > 0,
            "pipeline_error": pipeline_error,
        },
        latency_ms=latency_ms,
    )
