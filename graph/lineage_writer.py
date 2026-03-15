"""
Lineage Writer for Neo4j
Records all data lineage and relationships during MCP operations
"""
import uuid
from typing import Optional
from datetime import datetime
from graph.neo4j_client import get_neo4j_client
from mcp_server.utils.logging import get_logger
from mcp_server.schemas import QuoteData, StreamTick, DataSource

logger = get_logger(__name__)


class LineageWriter:
    """Writes data lineage events to Neo4j."""

    def __init__(self):
        self._client = get_neo4j_client()
        self._initialized = False
    
    def initialize(self) -> bool:
        try:
            if not self._client.connect():
                return False
            
            # Create base API nodes for connectors
            self._client.create_api_node(
                name="alpha_vantage",
                api_type="rest",
                base_url="https://www.alphavantage.co"
            )
            self._client.create_api_node(
                name="finnhub",
                api_type="rest",
                base_url="https://finnhub.io"
            )
            self._client.create_api_node(
                name="binance",
                api_type="websocket",
                base_url="wss://stream.binance.com:9443"
            )
            self._client.create_api_node(
                name="mcp_server",
                api_type="mcp",
                base_url="http://localhost:8000"
            )
            
            # Create base endpoints
            self._client.create_endpoint_node(
                endpoint_id="av_quote",
                path="/query?function=GLOBAL_QUOTE",
                method="GET",
                api_name="alpha_vantage"
            )
            self._client.create_endpoint_node(
                endpoint_id="fh_quote",
                path="/api/v1/quote",
                method="GET",
                api_name="finnhub"
            )
            self._client.create_endpoint_node(
                endpoint_id="bn_trade_stream",
                path="/ws/{symbol}@trade",
                method="WS",
                api_name="binance"
            )
            self._client.create_endpoint_node(
                endpoint_id="mcp_quote_latest",
                path="/invoke",
                method="POST",
                api_name="mcp_server"
            )
            self._client.create_endpoint_node(
                endpoint_id="mcp_quote_stream",
                path="/subscribe",
                method="POST",
                api_name="mcp_server"
            )
            
            self._initialized = True
            logger.info("lineage_writer_initialized")
            return True
            
        except Exception as e:
            logger.error("lineage_init_error", error=str(e))
            return False
    
    def record_agent_call(
        self,
        agent_id: str,
        api_name: str,
        latency_ms: float,
        response_code: int,
        symbol: str,
        tool_name: str,
        query_text: Optional[str] = None
    ) -> bool:
        """Record an agent's call to an API"""
        try:
            # Ensure agent exists
            self._client.create_agent_node(agent_id=agent_id)
            
            # Ensure instrument exists
            self._client.create_instrument_node(symbol=symbol)
            
            # Create query node if query text provided
            if query_text:
                query_id = f"q_{uuid.uuid4().hex[:8]}"
                self._client.create_query_node(
                    query_id=query_id,
                    query_text=query_text,
                    tool_name=tool_name
                )
            
            # Create CALLS edge
            self._client.create_calls_edge(
                agent_id=agent_id,
                api_name=api_name,
                latency_ms=latency_ms,
                response_code=response_code
            )
            
            logger.info(
                "lineage_call_recorded",
                agent=agent_id,
                api=api_name,
                symbol=symbol
            )
            return True
            
        except Exception as e:
            logger.error("record_call_error", error=str(e))
            return False
    
    def record_tick_event(
        self,
        tick: StreamTick,
        endpoint_id: str = "bn_trade_stream"
    ) -> bool:
        """Record a tick event from a stream"""
        try:
            # Ensure instrument exists
            self._client.create_instrument_node(symbol=tick.symbol)
            
            # Create event node
            event_id = f"ev_{tick.trade_id or uuid.uuid4().hex[:8]}"
            self._client.create_event_node(
                event_id=event_id,
                event_type="trade",
                symbol=tick.symbol,
                price=tick.price,
                timestamp=tick.timestamp
            )
            
            # Link endpoint to event
            self._client.create_emits_edge(
                endpoint_id=endpoint_id,
                event_id=event_id
            )
            
            logger.debug("tick_event_recorded", symbol=tick.symbol, event_id=event_id)
            return True
            
        except Exception as e:
            logger.error("record_tick_error", error=str(e))
            return False
    
    def record_quote_fetch(
        self,
        quote: QuoteData,
        agent_id: Optional[str] = None
    ) -> bool:
        """Record a quote fetch event"""
        try:
            # Ensure instrument exists
            instrument_type = "crypto" if "USDT" in quote.symbol else "stock"
            self._client.create_instrument_node(
                symbol=quote.symbol,
                instrument_type=instrument_type
            )
            
            # Create event for the quote
            event_id = f"quote_{uuid.uuid4().hex[:8]}"
            self._client.create_event_node(
                event_id=event_id,
                event_type="quote",
                symbol=quote.symbol,
                price=quote.price,
                timestamp=quote.timestamp
            )
            
            # Determine endpoint based on source
            endpoint_map = {
                DataSource.ALPHA_VANTAGE: "av_quote",
                DataSource.FINNHUB: "fh_quote",
                DataSource.BINANCE: "bn_trade_stream",
                DataSource.REDIS_CACHE: "mcp_quote_latest",
                DataSource.SEMANTIC_CACHE: "mcp_quote_latest"
            }
            endpoint_id = endpoint_map.get(quote.data_source, "mcp_quote_latest")
            
            self._client.create_emits_edge(
                endpoint_id=endpoint_id,
                event_id=event_id
            )
            
            # If agent provided, record the call
            if agent_id:
                api_name = quote.data_source.value if quote.data_source in [
                    DataSource.ALPHA_VANTAGE, DataSource.FINNHUB, DataSource.BINANCE
                ] else "mcp_server"
                
                self._client.create_calls_edge(
                    agent_id=agent_id,
                    api_name=api_name,
                    latency_ms=quote.latency_ms,
                    response_code=200
                )
            
            logger.debug("quote_fetch_recorded", symbol=quote.symbol, source=quote.data_source.value)
            return True
            
        except Exception as e:
            logger.error("record_quote_error", error=str(e))
            return False


# Singleton instance
_lineage_writer: Optional[LineageWriter] = None


def get_lineage_writer() -> LineageWriter:
    global _lineage_writer
    if _lineage_writer is None:
        _lineage_writer = LineageWriter()
    return _lineage_writer
