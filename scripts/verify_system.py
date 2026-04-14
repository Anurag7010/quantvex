"""
Finance MCP — System Verification Script
Phase 3 Final

Run inside Docker:
    docker exec finance-mcp-server python tests/verify_system.py

Run locally with all services up:
    PYTHONPATH=src NEBULA_HOST=localhost .venv/bin/python tests/verify_system.py

Exit code 0 → all components healthy
Exit code 1 → one or more checks failed
"""
import asyncio
import os
import sys
import time
import traceback
from typing import Callable, List, Tuple

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Colours for readability
# ---------------------------------------------------------------------------
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"

def _ok(msg: str) -> None:   print(f"  {_GREEN}✓{_RESET}  {msg}")
def _fail(msg: str) -> None: print(f"  {_RED}✗{_RESET}  {msg}")
def _warn(msg: str) -> None: print(f"  {_YELLOW}!{_RESET}  {msg}")
def _section(title: str) -> None:
    print(f"\n{_BOLD}{'─'*60}{_RESET}")
    print(f"{_BOLD}  {title}{_RESET}")
    print(f"{_BOLD}{'─'*60}{_RESET}")


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------
_FAILURES: List[str] = []

def check(label: str, fn: Callable) -> bool:
    """Run fn(); log pass/fail; return True on success."""
    try:
        fn()
        _ok(label)
        return True
    except Exception as exc:
        _fail(f"{label}\n       {_RED}{exc}{_RESET}")
        _FAILURES.append(label)
        return False


# ===========================================================================
# 1. NebulaGraph connection
# ===========================================================================
def check_nebula_connection():
    _section("1. NebulaGraph Connection")
    from mcp_server.config import get_settings
    from finance_mcp.graph.client import SecureGraphClient
    s = get_settings()

    def _connect():
        with SecureGraphClient(host=s.nebula_host, port=s.nebula_port) as c:
            rs = c._execute("SHOW SPACES")
            spaces = [rs.row_values(i)[0].as_string() for i in range(rs.row_size())]
            assert "supply_chain" in spaces, f"supply_chain space missing; got {spaces}"

    check("NebulaGraph connects and supply_chain space exists", _connect)


# ===========================================================================
# 2. Graph schema & data
# ===========================================================================
def check_graph_data():
    _section("2. Graph Schema & Seed Data")
    from mcp_server.config import get_settings
    from finance_mcp.graph.client import SecureGraphClient
    s = get_settings()

    with SecureGraphClient(host=s.nebula_host, port=s.nebula_port) as c:

        def _companies():
            rs = c._execute("USE supply_chain; MATCH (n:Company) RETURN count(n) AS cnt")
            cnt = rs.row_values(0)[0].as_int()
            assert cnt >= 10, f"Only {cnt} companies in graph — run seed_production_data.py"

        def _commodities():
            rs = c._execute("USE supply_chain; MATCH (n:Commodity) RETURN count(n) AS cnt")
            cnt = rs.row_values(0)[0].as_int()
            assert cnt >= 6, f"Only {cnt} commodities"

        def _depends_on():
            rs = c._execute("USE supply_chain; MATCH ()-[e:DEPENDS_ON]->() RETURN count(e) AS cnt")
            cnt = rs.row_values(0)[0].as_int()
            assert cnt >= 20, f"Only {cnt} DEPENDS_ON edges — run seed_production_data.py"

        def _requires():
            rs = c._execute("USE supply_chain; MATCH ()-[e:REQUIRES]->() RETURN count(e) AS cnt")
            cnt = rs.row_values(0)[0].as_int()
            assert cnt >= 10, f"Only {cnt} REQUIRES edges"

        def _tsmc_cascade():
            impacted = c.trace_impact("TSMC", 2)
            assert len(impacted) >= 5, (
                f"TSMC cascade returned only {len(impacted)} companies "
                "(expected ≥5: Apple, NVIDIA, AMD, Qualcomm, Intel). "
                "Run seed_production_data.py to fix."
            )

        def _xom_cascade():
            impacted = c.trace_impact("XOM", 2)
            assert len(impacted) >= 3, (
                f"XOM cascade returned only {len(impacted)} companies "
                "(expected ≥3: airlines, logistics). "
                "Run seed_production_data.py to add oil-consumer edges."
            )

        def _asml_cascade():
            impacted = c.trace_impact("ASML", 3)
            assert len(impacted) >= 5, (
                f"ASML cascade returned only {len(impacted)} companies. "
                "Expected: TSMC + all companies that depend on TSMC."
            )

        check("≥10 Company vertices in graph", _companies)
        check("≥6  Commodity vertices in graph", _commodities)
        check("≥20 DEPENDS_ON edges in graph", _depends_on)
        check("≥10 REQUIRES edges in graph", _requires)
        check("TSMC → cascade yields ≥5 companies", _tsmc_cascade)
        check("XOM  → cascade yields ≥3 companies (airlines)", _xom_cascade)
        check("ASML → cascade yields ≥5 companies (via TSMC)", _asml_cascade)


# ===========================================================================
# 3. News pipeline
# ===========================================================================
def check_news_pipeline():
    _section("3. News Pipeline")
    from mcp_server.config import get_settings
    from finance_mcp.news.news_client import NewsClient

    s = get_settings()

    def _news_key_configured():
        assert s.news_api_key, "NEWS_API_KEY not configured in .env"

    def _news_fetch():
        if not s.news_api_key:
            raise AssertionError("NEWS_API_KEY missing — skip news fetch")
        client = NewsClient(api_key=s.news_api_key)
        articles = asyncio.get_event_loop().run_until_complete(
            client.fetch_market_news("semiconductor chip supply", limit=3)
        )
        assert isinstance(articles, list), "fetch_market_news should return a list"
        # Zero articles is OK (quota exhausted or no results) — just don't crash.

    def _event_parser():
        from finance_mcp.news.event_parser import EventParser
        from finance_mcp.news.news_client import NewsArticle
        from datetime import datetime, timezone
        parser = EventParser()
        dummy = NewsArticle(
            title="TSMC halts EUV production after factory fire",
            description="Taiwan Semiconductor Manufacturing halted production. The chip foundry will be offline for weeks.",
            url="https://example.com/test",
            published_at=datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc),
            source_name="TestSource",
            query="semiconductor supply disruption",
        )
        events = parser.parse_articles([dummy])
        # Parser may return 0 events for dummy data — just verify no crash

    check("NEWS_API_KEY is set", _news_key_configured)
    check("NewsClient.fetch_articles() runs without crash", _news_fetch)
    check("EventParser.parse_articles() runs without crash", _event_parser)


# ===========================================================================
# 4. MCP tool handlers
# ===========================================================================
def check_mcp_handlers():
    _section("4. MCP Tool Handlers")

    async def _run_handlers():
        from mcp_server.invoke_handlers.trace_impact import handle_trace_impact
        from mcp_server.invoke_handlers.news_analysis import handle_news_analysis

        # --- trace_impact ---
        result = await handle_trace_impact(ticker="TSMC", max_hops=2, agent_id="verify")
        assert result.success, f"trace_impact failed: {result.error}"
        count = result.data.get("impacted_count", 0)
        assert count >= 5, (
            f"trace_impact('TSMC') returned only {count} companies. "
            "Expected ≥5. Check graph seed data."
        )

        # --- trace_impact for XOM (should now return ≥3 after seed) ---
        result2 = await handle_trace_impact(ticker="XOM", max_hops=2, agent_id="verify")
        assert result2.success, f"trace_impact(XOM) failed: {result2.error}"
        xom_count = result2.data.get("impacted_count", 0)
        assert xom_count >= 3, (
            f"trace_impact('XOM') returned {xom_count} companies. "
            "Expected ≥3 (airlines, logistics). Run seed_production_data.py."
        )

        # --- analyze_news_impact with ticker anchor (news optional, graph mandatory) ---
        result3 = await handle_news_impact_check()
        assert result3.success, f"analyze_news_impact failed: {result3.error}"
        assert result3.data.get("total_cascade_companies", 0) >= 1, (
            "analyze_news_impact returned 0 cascade companies even with ticker='TSMC'"
        )

    async def handle_news_impact_check():
        from mcp_server.invoke_handlers.news_analysis import handle_news_analysis
        return await handle_news_analysis(
            query="Taiwan semiconductor supply disruption",
            ticker="TSMC",
            limit=3,
            max_hops=2,
            agent_id="verify",
        )

    def _run():
        asyncio.get_event_loop().run_until_complete(_run_handlers())

    check("handle_trace_impact('TSMC') returns ≥5 companies", lambda: asyncio.get_event_loop().run_until_complete(
        _assert_trace("TSMC", 5)
    ))
    check("handle_trace_impact('XOM')  returns ≥3 companies", lambda: asyncio.get_event_loop().run_until_complete(
        _assert_trace("XOM", 3)
    ))
    check("handle_news_analysis(ticker='TSMC') returns cascade", lambda: asyncio.get_event_loop().run_until_complete(
        _assert_news_analysis()
    ))


async def _assert_trace(ticker: str, min_count: int):
    from mcp_server.invoke_handlers.trace_impact import handle_trace_impact
    r = await handle_trace_impact(ticker=ticker, max_hops=2, agent_id="verify")
    assert r.success, f"failed: {r.error}"
    cnt = r.data.get("impacted_count", 0)
    assert cnt >= min_count, f"{ticker} cascade = {cnt}, expected ≥{min_count}"


async def _assert_news_analysis():
    from mcp_server.invoke_handlers.news_analysis import handle_news_analysis
    r = await handle_news_analysis(
        query="Taiwan semiconductor supply disruption",
        ticker="TSMC",
        limit=3,
        max_hops=2,
        agent_id="verify",
    )
    assert r.success, f"failed: {r.error}"
    assert r.data.get("total_cascade_companies", 0) >= 1, "0 cascade companies despite ticker anchor"


# ===========================================================================
# 5. GPT tool registration
# ===========================================================================
def check_gpt_agent():
    _section("5. GPT Chat Agent Tool Registration")
    from mcp_server.config import get_settings
    s = get_settings()

    def _openai_key():
        assert s.openai_api_key, "OPENAI_API_KEY not configured in .env"

    def _tools_registered():
        if not s.openai_api_key:
            raise AssertionError("OPENAI_API_KEY missing — skip tool check")
        from mcp_server.chat_agent import GPTChatAgent
        agent = GPTChatAgent()
        names = {tool["function"]["name"] for tool in agent.tools}
        required = {
            "get_stock_quote",
            "trace_supply_chain_impact",
            "analyze_news_impact",
            "multi_agent_analysis",
        }
        missing = required - names
        assert not missing, f"Missing function declarations: {missing}"

    check("OPENAI_API_KEY is set", _openai_key)
    check("GPTChatAgent registers all 4 tools", _tools_registered)


# ===========================================================================
# 6. HTTP endpoint health-check  (only when running inside Docker)
# ===========================================================================
def check_http_endpoint():
    _section("6. Server Health Endpoint")
    import urllib.request, urllib.error

    def _health():
        try:
            req = urllib.request.urlopen("http://localhost:8000/health", timeout=5)
            assert req.status == 200, f"Health returned HTTP {req.status}"
        except urllib.error.URLError as e:
            raise AssertionError(f"Cannot reach http://localhost:8000/health — {e}")

    check("GET /health returns 200", _health)


# ===========================================================================
# Main
# ===========================================================================
def main():
    print(f"\n{_BOLD}{'='*60}{_RESET}")
    print(f"{_BOLD}  Finance MCP — Phase 3 System Verification{_RESET}")
    print(f"{_BOLD}{'='*60}{_RESET}")

    t0 = time.time()

    check_nebula_connection()
    check_graph_data()
    check_news_pipeline()
    check_mcp_handlers()
    check_gpt_agent()
    check_http_endpoint()

    elapsed = time.time() - t0

    print(f"\n{_BOLD}{'='*60}{_RESET}")
    if _FAILURES:
        print(f"\n{_RED}{_BOLD}  SYSTEM NOT READY — {len(_FAILURES)} check(s) failed:{_RESET}")
        for f in _FAILURES:
            print(f"    {_RED}✗  {f}{_RESET}")
        print()
        sys.exit(1)
    else:
        print(f"\n{_GREEN}{_BOLD}  SYSTEM READY — ALL COMPONENTS WORKING  ✓{_RESET}")
        print(f"  Completed in {elapsed:.1f}s")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
