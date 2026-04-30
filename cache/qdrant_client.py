"""
Qdrant Client for Semantic Cache
"""
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from qdrant_client import QdrantClient as QdrantClientLib
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, Range
from sentence_transformers import SentenceTransformer
from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)


class SemanticCacheClient:
    """Qdrant-based semantic cache for agent responses"""
    
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    VECTOR_SIZE = 384
    
    def __init__(self):
        settings = get_settings()
        self._client = QdrantClientLib(
            host=settings.qdrant_host,
            port=settings.qdrant_port
        )
        self._collection_name = settings.qdrant_collection
        self._model: Optional[SentenceTransformer] = None
        self._threshold = settings.semantic_cache_threshold
        self._recency_minutes = settings.semantic_cache_recency_minutes
        self._initialized = False
    
    def _get_model(self) -> SentenceTransformer:
        """Lazy load the sentence transformer model"""
        if self._model is None:
            logger.info("loading_embedding_model", model=self.EMBEDDING_MODEL)
            self._model = SentenceTransformer(self.EMBEDDING_MODEL)
            logger.info("embedding_model_loaded")
        return self._model
    
    def initialize(self) -> bool:
        """Initialize the collection if it doesn't exist"""
        try:
            collections = self._client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self._collection_name not in collection_names:
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                logger.info("collection_created", name=self._collection_name)
            else:
                logger.info("collection_exists", name=self._collection_name)
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error("qdrant_init_error", error=str(e))
            return False

    def health(self) -> bool:
        """Run a lightweight Qdrant health check without loading embeddings."""
        try:
            self._client.get_collections()
            return True
        except Exception as e:
            logger.error("qdrant_health_error", error=str(e))
            return False
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for text"""
        model = self._get_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def search_similar(
        self,
        query_text: str,
        symbol: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Search for semantically similar cached responses
        Returns the best match if similarity >= threshold and within recency window
        """
        if not self._initialized:
            self.initialize()
        
        try:
            # Generate query embedding
            query_vector = self.embed_text(query_text)
            
            # Build filter conditions
            must_conditions = []
            
            # Recency filter: only consider responses from last N minutes
            cutoff_time = (datetime.utcnow() - timedelta(minutes=self._recency_minutes)).timestamp()
            must_conditions.append(
                FieldCondition(
                    key="timestamp",
                    range=Range(gte=cutoff_time)
                )
            )
            
            # Optional symbol filter
            if symbol:
                must_conditions.append(
                    FieldCondition(
                        key="symbol",
                        match=models.MatchValue(value=symbol.upper())
                    )
                )
            
            # Search with filter
            results = self._client.search(
                collection_name=self._collection_name,
                query_vector=query_vector,
                query_filter=Filter(must=must_conditions) if must_conditions else None,
                limit=limit,
                score_threshold=self._threshold
            )
            
            if not results:
                logger.debug("semantic_cache_miss", query=query_text[:50])
                return None
            
            best_match = results[0]
            
            logger.info(
                "semantic_cache_hit",
                query=query_text[:50],
                score=best_match.score,
                symbol=best_match.payload.get("symbol")
            )
            
            return {
                "response_text": best_match.payload.get("response_text"),
                "symbol": best_match.payload.get("symbol"),
                "agent_id": best_match.payload.get("agent_id"),
                "timestamp": best_match.payload.get("timestamp"),
                "score": best_match.score
            }
            
        except Exception as e:
            logger.error("semantic_search_error", error=str(e))
            return None
    
    def store_response(
        self,
        agent_id: str,
        symbol: str,
        query_text: str,
        response_text: str
    ) -> bool:
        """Store a new response in the semantic cache"""
        if not self._initialized:
            self.initialize()
        
        try:
            # Generate embedding
            vector = self.embed_text(query_text)
            
            # Create point
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "agent_id": agent_id,
                    "symbol": symbol.upper(),
                    "query_text": query_text,
                    "response_text": response_text,
                    "timestamp": datetime.utcnow().timestamp()
                }
            )
            
            # Upsert point
            self._client.upsert(
                collection_name=self._collection_name,
                points=[point]
            )
            
            logger.info(
                "semantic_cache_stored",
                symbol=symbol,
                query=query_text[:50]
            )
            return True
            
        except Exception as e:
            logger.error("semantic_store_error", error=str(e))
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        try:
            info = self._client.get_collection(self._collection_name)
            return {
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "points_count": info.points_count
            }
        except Exception as e:
            logger.error("collection_stats_error", error=str(e))
            return {}


# Singleton instance
_semantic_cache: Optional[SemanticCacheClient] = None


def get_semantic_cache() -> SemanticCacheClient:
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCacheClient()
    return _semantic_cache
