"""
Neo4j Client for Graph Database Operations
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from neo4j import GraphDatabase, Session
from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)


class Neo4jClient:
    """Neo4j client for lineage and relationship graph operations."""

    def __init__(self):
        settings = get_settings()
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password)
        )
        self._initialized = False
    
    def connect(self) -> bool:
        """Test connection and initialize schema"""
        try:
            with self._driver.session() as session:
                result = session.run("RETURN 1 AS num")
                result.single()
            
            self._initialize_schema()
            self._initialized = True
            logger.info("neo4j_connected")
            return True
            
        except Exception as e:
            logger.error("neo4j_connection_error", error=str(e))
            return False

    def ping(self) -> bool:
        """Run a lightweight Neo4j query to verify connectivity."""
        try:
            with self._driver.session() as session:
                result = session.run("RETURN 1 AS num")
                result.single()
            return True
        except Exception as e:
            logger.error("neo4j_ping_error", error=str(e))
            return False
    
    def _initialize_schema(self):
        """Initialize constraints and indexes"""
        constraints = [
            "CREATE CONSTRAINT api_name IF NOT EXISTS FOR (a:API) REQUIRE a.name IS UNIQUE",
            "CREATE CONSTRAINT endpoint_id IF NOT EXISTS FOR (e:Endpoint) REQUIRE e.endpoint_id IS UNIQUE",
            "CREATE CONSTRAINT instrument_symbol IF NOT EXISTS FOR (i:Instrument) REQUIRE i.symbol IS UNIQUE",
            "CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (ag:Agent) REQUIRE ag.agent_id IS UNIQUE",
            "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (ev:Event) REQUIRE ev.event_id IS UNIQUE",
            "CREATE CONSTRAINT query_id IF NOT EXISTS FOR (q:Query) REQUIRE q.query_id IS UNIQUE"
        ]
        
        with self._driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception:
                    pass  # Constraint may already exist
        
        logger.info("neo4j_schema_initialized")
    
    def close(self):
        """Close the driver connection"""
        if self._driver:
            self._driver.close()
            logger.info("neo4j_disconnected")
    
    def create_api_node(self, name: str, api_type: str, base_url: str) -> bool:
        """Create an API node"""
        query = """
        MERGE (a:API {name: $name})
        SET a.type = $api_type, a.base_url = $base_url, a.updated_at = datetime()
        RETURN a
        """
        try:
            with self._driver.session() as session:
                session.run(query, name=name, api_type=api_type, base_url=base_url)
            return True
        except Exception as e:
            logger.error("create_api_error", error=str(e))
            return False
    
    def create_endpoint_node(self, endpoint_id: str, path: str, method: str, api_name: str) -> bool:
        """Create an Endpoint node and link to API"""
        query = """
        MERGE (e:Endpoint {endpoint_id: $endpoint_id})
        SET e.path = $path, e.method = $method, e.updated_at = datetime()
        WITH e
        MATCH (a:API {name: $api_name})
        MERGE (a)-[:PROVIDES]->(e)
        RETURN e
        """
        try:
            with self._driver.session() as session:
                session.run(query, endpoint_id=endpoint_id, path=path, method=method, api_name=api_name)
            return True
        except Exception as e:
            logger.error("create_endpoint_error", error=str(e))
            return False
    
    def create_instrument_node(self, symbol: str, instrument_type: str = "stock", exchange: Optional[str] = None) -> bool:
        """Create an Instrument node"""
        query = """
        MERGE (i:Instrument {symbol: $symbol})
        SET i.type = $instrument_type, i.exchange = $exchange, i.updated_at = datetime()
        RETURN i
        """
        try:
            with self._driver.session() as session:
                session.run(query, symbol=symbol.upper(), instrument_type=instrument_type, exchange=exchange)
            return True
        except Exception as e:
            logger.error("create_instrument_error", error=str(e))
            return False
    
    def create_agent_node(self, agent_id: str, agent_type: str = "langchain") -> bool:
        """Create an Agent node"""
        query = """
        MERGE (ag:Agent {agent_id: $agent_id})
        SET ag.type = $agent_type, ag.created_at = datetime()
        RETURN ag
        """
        try:
            with self._driver.session() as session:
                session.run(query, agent_id=agent_id, agent_type=agent_type)
            return True
        except Exception as e:
            logger.error("create_agent_error", error=str(e))
            return False
    
    def create_event_node(
        self,
        event_id: str,
        event_type: str,
        symbol: str,
        price: float,
        timestamp: datetime
    ) -> bool:
        """Create an Event node and link to Instrument"""
        query = """
        MERGE (ev:Event {event_id: $event_id})
        SET ev.type = $event_type, ev.price = $price, ev.timestamp = datetime($timestamp)
        WITH ev
        MATCH (i:Instrument {symbol: $symbol})
        MERGE (ev)-[:ABOUT]->(i)
        RETURN ev
        """
        try:
            with self._driver.session() as session:
                session.run(
                    query,
                    event_id=event_id,
                    event_type=event_type,
                    symbol=symbol.upper(),
                    price=price,
                    timestamp=timestamp.isoformat()
                )
            return True
        except Exception as e:
            logger.error("create_event_error", error=str(e))
            return False
    
    def create_query_node(self, query_id: str, query_text: str, tool_name: str) -> bool:
        """Create a Query node"""
        query = """
        MERGE (q:Query {query_id: $query_id})
        SET q.text = $query_text, q.tool = $tool_name, q.created_at = datetime()
        RETURN q
        """
        try:
            with self._driver.session() as session:
                session.run(query, query_id=query_id, query_text=query_text, tool_name=tool_name)
            return True
        except Exception as e:
            logger.error("create_query_error", error=str(e))
            return False
    
    # ==================== EDGE OPERATIONS ====================
    
    def create_calls_edge(
        self,
        agent_id: str,
        api_name: str,
        latency_ms: float,
        response_code: int,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """Create a CALLS edge between Agent and API"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        query = """
        MATCH (ag:Agent {agent_id: $agent_id})
        MATCH (a:API {name: $api_name})
        CREATE (ag)-[r:CALLS {
            latency_ms: $latency_ms,
            response_code: $response_code,
            timestamp: datetime($timestamp)
        }]->(a)
        RETURN r
        """
        try:
            with self._driver.session() as session:
                session.run(
                    query,
                    agent_id=agent_id,
                    api_name=api_name,
                    latency_ms=latency_ms,
                    response_code=response_code,
                    timestamp=timestamp.isoformat()
                )
            logger.debug("calls_edge_created", agent=agent_id, api=api_name)
            return True
        except Exception as e:
            logger.error("create_calls_edge_error", error=str(e))
            return False
    
    def create_emits_edge(self, endpoint_id: str, event_id: str) -> bool:
        """Create an EMITS edge between Endpoint and Event"""
        query = """
        MATCH (e:Endpoint {endpoint_id: $endpoint_id})
        MATCH (ev:Event {event_id: $event_id})
        MERGE (e)-[:EMITS]->(ev)
        RETURN e, ev
        """
        try:
            with self._driver.session() as session:
                session.run(query, endpoint_id=endpoint_id, event_id=event_id)
            return True
        except Exception as e:
            logger.error("create_emits_edge_error", error=str(e))
            return False
    
    def create_depends_on_edge(self, indicator_symbol: str, instrument_symbol: str) -> bool:
        """Create a DEPENDS_ON edge between Indicator and Instrument"""
        query = """
        MATCH (ind:Instrument {symbol: $indicator_symbol})
        MATCH (inst:Instrument {symbol: $instrument_symbol})
        MERGE (ind)-[:DEPENDS_ON]->(inst)
        RETURN ind, inst
        """
        try:
            with self._driver.session() as session:
                session.run(
                    query,
                    indicator_symbol=indicator_symbol.upper(),
                    instrument_symbol=instrument_symbol.upper()
                )
            return True
        except Exception as e:
            logger.error("create_depends_on_edge_error", error=str(e))
            return False
    
    # ==================== QUERY OPERATIONS ====================
    
    def get_agent_call_history(self, agent_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get call history for an agent"""
        query = """
        MATCH (ag:Agent {agent_id: $agent_id})-[r:CALLS]->(a:API)
        RETURN a.name AS api_name, r.latency_ms AS latency_ms, 
               r.response_code AS response_code, r.timestamp AS timestamp
        ORDER BY r.timestamp DESC
        LIMIT $limit
        """
        try:
            with self._driver.session() as session:
                result = session.run(query, agent_id=agent_id, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error("get_call_history_error", error=str(e))
            return []
    
    def get_instrument_events(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events for an instrument"""
        query = """
        MATCH (ev:Event)-[:ABOUT]->(i:Instrument {symbol: $symbol})
        RETURN ev.event_id AS event_id, ev.type AS event_type, 
               ev.price AS price, ev.timestamp AS timestamp
        ORDER BY ev.timestamp DESC
        LIMIT $limit
        """
        try:
            with self._driver.session() as session:
                result = session.run(query, symbol=symbol.upper(), limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error("get_instrument_events_error", error=str(e))
            return []
    
    def get_api_endpoints(self, api_name: str) -> List[Dict[str, Any]]:
        """Get all endpoints for an API"""
        query = """
        MATCH (a:API {name: $api_name})-[:PROVIDES]->(e:Endpoint)
        RETURN e.endpoint_id AS endpoint_id, e.path AS path, e.method AS method
        """
        try:
            with self._driver.session() as session:
                result = session.run(query, api_name=api_name)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error("get_api_endpoints_error", error=str(e))
            return []


# Singleton instance
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client
