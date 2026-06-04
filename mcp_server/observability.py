"""
mcp_server/observability.py

In-memory metrics collector for QuantVex.  All counters are module-level and
survive for the lifetime of the process.  Thread-safe via a single RLock.

Usage
-----
    from mcp_server.observability import metrics

    # Record a tool invocation
    metrics.record_tool_call("quote.latest", latency_ms=142.3, cache_hit=True, error=None)

    # Record an agent turn
    metrics.record_agent_turn(
        model="llama-3.3-70b-versatile",
        prompt_tokens=1200,
        completion_tokens=350,
        latency_ms=890.0,
    )

    # Record a graph query
    metrics.record_graph_query(query_type="trace_impact", nodes_returned=7, latency_ms=44.1)

    # Read current snapshot
    snapshot = metrics.snapshot()
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Optional

from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

_lock = threading.RLock()

_START_TIME: float = time.time()

_total_requests: int = 0
_tool_invocations: dict[str, int] = defaultdict(int)
_cache_hits: dict[str, int] = {"redis_hits": 0, "redis_misses": 0, "qdrant_hits": 0}
_latency_buckets: dict[str, list[float]] = defaultdict(list)
_errors_total: int = 0
_errors_by_tool: dict[str, int] = defaultdict(int)
_agent_prompt_tokens: int = 0
_agent_completion_tokens: int = 0
_graph_queries: dict[str, int] = defaultdict(int)


def record_tool_call(
    tool: str,
    latency_ms: float,
    cache_hit: bool = False,
    error: Optional[str] = None,
    cache_type: Optional[str] = None,
) -> None:
    """Record one completed tool invocation with latency and cache outcome."""
    global _total_requests, _errors_total

    with _lock:
        _total_requests += 1
        _tool_invocations[tool] += 1
        _latency_buckets[tool].append(latency_ms)

        if cache_hit:
            key = f"{cache_type}_hits" if cache_type in ("redis", "qdrant") else "redis_hits"
            _cache_hits[key] = _cache_hits.get(key, 0) + 1
        elif cache_type in ("redis", "qdrant"):
            miss_key = f"{cache_type}_misses"
            _cache_hits[miss_key] = _cache_hits.get(miss_key, 0) + 1

        if error:
            _errors_total += 1
            _errors_by_tool[tool] += 1

    logger.info(
        "tool_invocation",
        tool=tool,
        latency_ms=round(latency_ms, 2),
        cache_hit=cache_hit,
        error=error,
    )


def record_agent_turn(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
) -> None:
    """Record one LLM agent turn (token counts + latency)."""
    global _agent_prompt_tokens, _agent_completion_tokens

    with _lock:
        _agent_prompt_tokens += prompt_tokens
        _agent_completion_tokens += completion_tokens

    logger.info(
        "agent_turn",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=round(latency_ms, 2),
    )


def record_graph_query(
    query_type: str,
    nodes_returned: int,
    latency_ms: float,
) -> None:
    """Record one Memgraph query execution."""
    with _lock:
        _graph_queries[query_type] += 1

    logger.info(
        "graph_query",
        query_type=query_type,
        nodes_returned=nodes_returned,
        latency_ms=round(latency_ms, 2),
    )


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def snapshot() -> dict:
    """Return a point-in-time snapshot of all metrics."""
    with _lock:
        return {
            "uptime_seconds": round(time.time() - _START_TIME, 1),
            "total_requests": _total_requests,
            "tool_invocations": dict(_tool_invocations),
            "cache": dict(_cache_hits),
            "avg_latency_ms": {
                tool: _avg(lats) for tool, lats in _latency_buckets.items()
            },
            "errors": {
                "total": _errors_total,
                "by_tool": dict(_errors_by_tool),
            },
            "agent_tokens": {
                "total_prompt": _agent_prompt_tokens,
                "total_completion": _agent_completion_tokens,
            },
            "graph_queries": dict(_graph_queries),
        }


# Singleton-style module object for import convenience
class _Metrics:
    record_tool_call = staticmethod(record_tool_call)
    record_agent_turn = staticmethod(record_agent_turn)
    record_graph_query = staticmethod(record_graph_query)
    snapshot = staticmethod(snapshot)


metrics = _Metrics()
