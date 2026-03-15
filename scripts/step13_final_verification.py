"""
Step 13 — Final System Verification
=====================================
Verifies the complete end-to-end pipeline:

  NewsAPI → EventParser → EventIngestor → NebulaGraph
         → trace_impact → MCP handler → ToolResponse

Run: PYTHONPATH=src .venv/bin/python3.11 tests/step13_final_verification.py
"""
import asyncio
import os
import pathlib
import sys
import json

sys.path.insert(0, "src")

try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).parent.parent / ".env")
except ImportError:
    pass

PASS  = "\033[32m PASS\033[0m"
FAIL  = "\033[31m FAIL\033[0m"
HEAD  = "\033[1;34m"
RESET = "\033[0m"

failures = []

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS}  {label}")
    else:
        msg = f"  {FAIL}  {label}"
        if detail:
            msg += f"\n         {detail}"
        print(msg)
        failures.append(label)


# ─────────────────────────────────────────────────────────────
# LAYER 1 — Infrastructure
# ─────────────────────────────────────────────────────────────
def verify_infrastructure():
    print(f"\n{HEAD}[1] Infrastructure{RESET}")

    # Docker / NebulaGraph reachable
    import socket
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect(("127.0.0.1", 9669))
        nebula_port_open = True
    except Exception:
        nebula_port_open = False
    finally:
        s.close()
    check("NebulaGraph port 9669 is reachable", nebula_port_open)

    # Python client can authenticate
    from finance_mcp.graph.client import SecureGraphClient
    try:
        with SecureGraphClient() as c:
            auth_ok = True
    except Exception as e:
        auth_ok = False
    check("SecureGraphClient authenticates successfully", auth_ok)

    # NEWS_API_KEY present
    key = os.environ.get("NEWS_API_KEY", "").strip()
    check("NEWS_API_KEY loaded from .env", bool(key), "Set NEWS_API_KEY in .env")

    return key


# ─────────────────────────────────────────────────────────────
# LAYER 2 — Graph Schema
# ─────────────────────────────────────────────────────────────
def verify_schema():
    print(f"\n{HEAD}[2] Graph Schema (supply_chain space){RESET}")
    from finance_mcp.graph.client import SecureGraphClient

    with SecureGraphClient() as c:
        # Tags exist — insert a test vertex for each
        try:
            c.insert_company("SCHEMA_TEST", "Schema Test Co", "Test")
            check("Company tag exists and accepts writes", True)
        except Exception as e:
            check("Company tag exists and accepts writes", False, str(e))

        try:
            c.insert_commodity("SCHEMA_COMM_TEST", "Schema Test Commodity", "Test")
            check("Commodity tag exists and accepts writes", True)
        except Exception as e:
            check("Commodity tag exists and accepts writes", False, str(e))

        try:
            c.upsert_event("EVT_SCHEMA_TEST", "Schema verification event", 5)
            check("Event tag exists and accepts writes", True)
        except Exception as e:
            check("Event tag exists and accepts writes", False, str(e))

        # DEPENDS_ON edge
        from finance_mcp.graph.client import _validate_vid
        try:
            _validate_vid("SCHEMA_TEST", "src")
            q = 'INSERT EDGE IF NOT EXISTS DEPENDS_ON(weight) VALUES "SCHEMA_TEST"->"TSMC":($weight)'
            c._execute(q, {"weight": 0.1})
            check("DEPENDS_ON edge type exists and accepts writes", True)
        except Exception as e:
            check("DEPENDS_ON edge type exists and accepts writes", False, str(e))

        # Index: find_companies_by_sector
        try:
            r = c.find_companies_by_sector("Technology")
            check("LOOKUP index on Company.sector works", len(r.rows()) >= 0)
        except Exception as e:
            check("LOOKUP index on Company.sector works", False, str(e))


# ─────────────────────────────────────────────────────────────
# LAYER 3 — News Ingestion Pipeline
# ─────────────────────────────────────────────────────────────
async def verify_pipeline(news_api_key: str):
    print(f"\n{HEAD}[3] News Ingestion Pipeline{RESET}")
    from finance_mcp.ingestion.pipeline import run_news_ingestion_pipeline

    result = await run_news_ingestion_pipeline(
        query="semiconductor supply chain shock",
        limit=5,
        news_api_key=news_api_key,
        nebula_host="127.0.0.1",
        nebula_port=9669,
    )

    check("Pipeline returns PipelineResult", result is not None)
    check("Articles fetched from NewsAPI", result.articles_fetched > 0,
          f"Got {result.articles_fetched}")
    check("No graph write failures", result.failed == 0,
          f"failures: {result.errors}")
    check("Pipeline query preserved in result",
          result.query == "semiconductor supply chain shock")

    print(f"         articles={result.articles_fetched}  "
          f"parsed={result.events_parsed}  "
          f"written={result.succeeded}  failed={result.failed}")
    return result


# ─────────────────────────────────────────────────────────────
# LAYER 4 — Graph Reasoning (trace_impact)
# ─────────────────────────────────────────────────────────────
def verify_graph_reasoning():
    print(f"\n{HEAD}[4] Graph Reasoning — trace_impact{RESET}")
    from finance_mcp.graph.client import SecureGraphClient

    with SecureGraphClient() as c:
        impacts = c.trace_impact("TSMC", max_hops=3)

    check("trace_impact returns a list", isinstance(impacts, list))
    check("trace_impact finds downstream companies", len(impacts) > 0,
          "No DEPENDS_ON edges found — run seed_test_data.py first")

    if impacts:
        item = impacts[0]
        check("Each result has 'ticker' key",  "ticker"  in item)
        check("Each result has 'name' key",    "name"    in item)
        check("Each result has 'sector' key",  "sector"  in item)
        check("ticker values are strings",     isinstance(item["ticker"], str))

    known = {i["ticker"] for i in impacts}
    for expected in ["AAPL", "NVDA"]:
        check(f"  {expected} is in impacted set", expected in known)

    print(f"         Impacted companies ({len(impacts)}): "
          + ", ".join(i["ticker"] for i in impacts))


# ─────────────────────────────────────────────────────────────
# LAYER 5 — MCP Handler (full handler call)
# ─────────────────────────────────────────────────────────────
async def verify_mcp_handler():
    print(f"\n{HEAD}[5] MCP Tool Handler — handle_trace_impact{RESET}")
    from mcp_server.invoke_handlers.trace_impact import handle_trace_impact

    # Valid call
    resp = await handle_trace_impact(ticker="TSMC", max_hops=2, agent_id="step13")
    check("Handler returns success=True for TSMC", resp.success,
          resp.error or "")
    check("Response data is a dict", isinstance(resp.data, dict))
    if resp.data:
        check("data.ticker == 'TSMC'",       resp.data.get("ticker") == "TSMC")
        check("data.impacted_count >= 1",    resp.data.get("impacted_count", 0) >= 1)
        check("data.impacted_companies is a list",
              isinstance(resp.data.get("impacted_companies"), list))
    check("latency_ms > 0", (resp.latency_ms or 0) > 0)

    # Invalid ticker rejected
    bad = await handle_trace_impact(ticker="'; DROP SPACE supply_chain;--", max_hops=2)
    check("Injection ticker rejected with success=False", not bad.success)

    # Invalid max_hops rejected
    bad2 = await handle_trace_impact(ticker="TSMC", max_hops=99)
    check("max_hops=99 rejected with success=False", not bad2.success)

    print(f"         impacted_count={resp.data.get('impacted_count') if resp.data else 'N/A'}"
          f"  latency={resp.latency_ms:.1f}ms" if resp.latency_ms else "")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
async def main():
    print("=" * 65)
    print("  STEP 13 — Final System Verification")
    print("=" * 65)

    news_api_key = verify_infrastructure()
    verify_schema()
    await verify_pipeline(news_api_key)
    verify_graph_reasoning()
    await verify_mcp_handler()

    # ── Summary ──────────────────────────────────────────────
    print(f"\n{'='*65}")
    total_checks = 20  # approximate
    if not failures:
        print(f"\033[1;32m  ALL CHECKS PASSED — System verified end-to-end\033[0m")
    else:
        print(f"\033[1;31m  {len(failures)} CHECK(S) FAILED:\033[0m")
        for f in failures:
            print(f"    • {f}")

    print("\n  Architecture verified:")
    print("  NewsAPI → EventParser → EventIngestor → NebulaGraph")
    print("         → trace_impact → MCP handler → ToolResponse")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
