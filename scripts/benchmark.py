"""
scripts/benchmark.py

Latency benchmark for the QuantVex MCP server.

Fires 100 requests to /invoke with quote.latest (10 unique tickers × 10 each)
and 20 requests to /invoke with trace_impact, then reports p50 / p95 / p99
latency and cache hit rate.

Usage
-----
    # Default (localhost:8000, test API key)
    PYTHONPATH=.:src python scripts/benchmark.py

    # Against a remote server
    python scripts/benchmark.py --url https://quantvex-api-zpai.onrender.com \
                                 --api-key your-key

    # Fewer requests for a quick check
    python scripts/benchmark.py --quote-requests 20 --trace-requests 5

Prerequisites
-------------
The MCP server must be running before executing this script.
Start it with:
    PYTHONPATH=src uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

QUOTE_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "V", "JPM", "BRK-B"]
TRACE_TICKERS = ["TSMC", "NVDA", "AAPL", "MSFT", "INTC"]


def percentile(data: list[float], pct: float) -> float:
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


async def fire_quote_request(
    client: httpx.AsyncClient,
    url: str,
    api_key: str,
    ticker: str,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            f"{url}/invoke",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json={"tool_name": "quote.latest", "arguments": {"symbol": ticker}},
            timeout=30.0,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        data = resp.json()
        cache_hit = data.get("data", {}).get("cache_hit", False) or data.get("cache_hit", False)
        return {
            "ticker": ticker,
            "status": resp.status_code,
            "latency_ms": elapsed_ms,
            "cache_hit": bool(cache_hit),
            "success": resp.status_code == 200,
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "ticker": ticker,
            "status": -1,
            "latency_ms": elapsed_ms,
            "cache_hit": False,
            "success": False,
            "error": str(exc),
        }


async def fire_trace_request(
    client: httpx.AsyncClient,
    url: str,
    api_key: str,
    ticker: str,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            f"{url}/invoke",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json={"tool_name": "trace_impact", "arguments": {"ticker": ticker, "max_hops": 2}},
            timeout=30.0,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "ticker": ticker,
            "status": resp.status_code,
            "latency_ms": elapsed_ms,
            "success": resp.status_code == 200,
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "ticker": ticker,
            "status": -1,
            "latency_ms": elapsed_ms,
            "success": False,
            "error": str(exc),
        }


def print_benchmark_table(
    quote_results: list[dict],
    trace_results: list[dict],
) -> None:
    print("\n" + "=" * 60)
    print("  QUANTVEX LATENCY BENCHMARK")
    print("=" * 60)

    def _section(name: str, results: list[dict]) -> None:
        latencies = [r["latency_ms"] for r in results]
        hits = sum(1 for r in results if r.get("cache_hit"))
        success = sum(1 for r in results if r["success"])
        total = len(results)

        p50 = percentile(latencies, 50)
        p95 = percentile(latencies, 95)
        p99 = percentile(latencies, 99)
        cache_rate = hits / total * 100 if total else 0

        print(f"\n  {name}")
        print(f"  {'Requests':<18} {total} total, {success} succeeded")
        print(f"  {'p50 latency':<18} {p50:.0f}ms")
        print(f"  {'p95 latency':<18} {p95:.0f}ms")
        print(f"  {'p99 latency':<18} {p99:.0f}ms")
        print(f"  {'min / max':<18} {min(latencies):.0f}ms / {max(latencies):.0f}ms")
        if name.lower().startswith("quote"):
            print(f"  {'Cache hit rate':<18} {cache_rate:.1f}%  ({hits}/{total} requests)")

    _section("quote.latest", quote_results)
    _section("trace_impact", trace_results)
    print("\n" + "=" * 60)


async def _throttled(sem: asyncio.Semaphore, coro, delay_s: float = 0.7):
    """Run coro with a semaphore and a brief post-release sleep to respect rate limits."""
    async with sem:
        result = await coro
        await asyncio.sleep(delay_s)
        return result


async def run_benchmark(
    url: str,
    api_key: str,
    quote_requests: int,
    trace_requests: int,
) -> dict:
    print(f"\nRunning benchmark against {url}")
    print(f"  quote.latest: {quote_requests} requests  (throttled to ~50 req/min)")
    print(f"  trace_impact:  {trace_requests} requests")

    # Concurrency cap: 5 in-flight at once with 0.7s sleep → ~7 req/s < 60/min limit
    sem = asyncio.Semaphore(5)

    async with httpx.AsyncClient() as client:
        # --- quote.latest: 10 tickers × repeats ---
        reps_per_ticker = max(1, quote_requests // len(QUOTE_TICKERS))
        quote_tasks = []
        for _rep in range(reps_per_ticker):
            for ticker in QUOTE_TICKERS[: min(len(QUOTE_TICKERS), quote_requests)]:
                coro = fire_quote_request(client, url, api_key, ticker)
                quote_tasks.append(_throttled(sem, coro))

        print("\nFiring quote.latest requests...")
        quote_results = await asyncio.gather(*quote_tasks)

        # Wait for rate-limit window to partially reset before trace burst
        print("Waiting 5s before trace_impact run...")
        await asyncio.sleep(5)

        # --- trace_impact ---
        trace_tasks = []
        for i in range(trace_requests):
            ticker = TRACE_TICKERS[i % len(TRACE_TICKERS)]
            coro = fire_trace_request(client, url, api_key, ticker)
            trace_tasks.append(_throttled(sem, coro, delay_s=0.5))

        print("Firing trace_impact requests...")
        trace_results = await asyncio.gather(*trace_tasks)

    print_benchmark_table(list(quote_results), list(trace_results))

    def _stats(results: list[dict]) -> dict:
        lats = [r["latency_ms"] for r in results]
        hits = sum(1 for r in results if r.get("cache_hit"))
        return {
            "total": len(results),
            "success": sum(1 for r in results if r["success"]),
            "p50_ms": round(percentile(lats, 50), 1),
            "p95_ms": round(percentile(lats, 95), 1),
            "p99_ms": round(percentile(lats, 99), 1),
            "min_ms": round(min(lats), 1),
            "max_ms": round(max(lats), 1),
            "avg_ms": round(statistics.mean(lats), 1),
            "cache_hits": hits,
            "cache_hit_rate_pct": round(hits / len(results) * 100, 1) if results else 0,
        }

    summary = {
        "run_at": datetime.utcnow().isoformat(),
        "server_url": url,
        "quote_latest": _stats(list(quote_results)),
        "trace_impact": _stats(list(trace_results)),
    }

    out = Path(__file__).parent / "benchmark_results.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nResults saved → {out}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantVex latency benchmark")
    parser.add_argument("--url", default="http://localhost:8000", help="Server base URL")
    parser.add_argument(
        "--api-key",
        default="dev_key_change_in_production",
        help="X-API-Key header value",
    )
    parser.add_argument("--quote-requests", type=int, default=100)
    parser.add_argument("--trace-requests", type=int, default=20)
    args = parser.parse_args()

    asyncio.run(
        run_benchmark(
            url=args.url.rstrip("/"),
            api_key=args.api_key,
            quote_requests=args.quote_requests,
            trace_requests=args.trace_requests,
        )
    )


if __name__ == "__main__":
    main()
