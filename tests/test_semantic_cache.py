"""Unit tests for the hash-based semantic cache (cache/qdrant_client.py)."""
import json
from unittest.mock import MagicMock
import pytest


def _make_client(mock_redis):
    from cache.qdrant_client import SemanticCacheClient
    client = SemanticCacheClient()
    client._redis = mock_redis
    return client


def test_cache_key_is_deterministic():
    from cache.qdrant_client import _cache_key
    k1 = _cache_key("AAPL", "what is the price of apple?")
    k2 = _cache_key("AAPL", "what is the price of apple?")
    assert k1 == k2
    assert k1.startswith("sem:AAPL:")


def test_cache_key_differs_by_symbol():
    from cache.qdrant_client import _cache_key
    k1 = _cache_key("AAPL", "price query")
    k2 = _cache_key("MSFT", "price query")
    assert k1 != k2


def test_search_similar_miss():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    client = _make_client(mock_redis)
    result = client.search_similar("what is aapl price", symbol="AAPL")
    assert result is None


def test_search_similar_hit():
    payload = {
        "response_text": '{"price": 195.0}',
        "symbol": "AAPL",
        "agent_id": "test",
        "timestamp": 0.0,
        "score": 1.0,
    }
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(payload)
    client = _make_client(mock_redis)
    result = client.search_similar("aapl price", symbol="AAPL")
    assert result is not None
    assert result["symbol"] == "AAPL"
    assert result["score"] == 1.0


def test_store_response_sets_correct_key_and_ttl():
    mock_redis = MagicMock()
    client = _make_client(mock_redis)
    ok = client.store_response(
        agent_id="agent1",
        symbol="AAPL",
        query_text="what is aapl price",
        response_text='{"price": 195.0}',
    )
    assert ok is True
    mock_redis.setex.assert_called_once()
    key, ttl, raw = mock_redis.setex.call_args[0]
    assert key.startswith("sem:AAPL:")
    assert ttl > 0
    stored = json.loads(raw)
    assert stored["symbol"] == "AAPL"
    assert stored["response_text"] == '{"price": 195.0}'


def test_search_similar_no_symbol_returns_none():
    mock_redis = MagicMock()
    client = _make_client(mock_redis)
    result = client.search_similar("some query", symbol=None)
    assert result is None
    mock_redis.get.assert_not_called()


def test_initialize_success():
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    client = _make_client(mock_redis)
    assert client.initialize() is True


def test_initialize_failure():
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("connection refused")
    client = _make_client(mock_redis)
    assert client.initialize() is False


def test_health_failure():
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("connection refused")
    client = _make_client(mock_redis)
    assert client.health() is False


def test_get_semantic_cache_is_singleton():
    from cache import qdrant_client as qc
    qc._semantic_cache = None
    c1 = qc.get_semantic_cache()
    c2 = qc.get_semantic_cache()
    assert c1 is c2
    qc._semantic_cache = None
