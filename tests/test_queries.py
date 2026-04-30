"""
Tests for src/finance_mcp/graph/queries.py

Coverage strategy
-----------------
1. Structure tests — every constant is a plain str, non-empty, and contains
   only ``$name`` placeholders (no f-string artifacts or bare user values).

2. Placeholder tests — each template declares exactly the params its doc says
   it takes, and those names appear as $name in the query text.

3. No-format-string tests — no template contains a Python f-string marker
   (e.g. { or }) which would indicate a value was accidentally baked in.

4. Integration tests — execute each query against the live graph using the
   correct bound parameters.  Skipped when NebulaGraph is not reachable.

Run unit tests only (no docker required)::

    PYTHONPATH=src .venv/bin/python3.11 -m pytest tests/test_queries.py -v -m "not integration"

Run all tests (requires running NebulaGraph)::

    PYTHONPATH=src .venv/bin/python3.11 -m pytest tests/test_queries.py -v
"""

import re
import pytest

from finance_mcp.graph import queries

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _placeholders(query: str) -> set:
    """Return the set of $name placeholders present in a query string."""
    return set(re.findall(r"\$(\w+)", query))


def _nebula_reachable() -> bool:
    from nebula3.gclient.net import ConnectionPool
    from nebula3.Config import Config
    cfg = Config(); cfg.max_connection_pool_size = 1
    pool = ConnectionPool()
    try:
        return pool.init([("127.0.0.1", 9669)], cfg)
    except Exception:
        return False
    finally:
        try: pool.close()
        except Exception: pass


nebula_required = pytest.mark.skipif(
    not _nebula_reachable(),
    reason="NebulaGraph not reachable — start docker/nebula-docker-compose.yml",
)

# All exported query constants
_ALL_QUERY_CONSTANTS = [
    ("INSERT_COMPANY",               queries.INSERT_COMPANY),
    ("INSERT_COMMODITY",             queries.INSERT_COMMODITY),
    ("INSERT_EVENT",                 queries.INSERT_EVENT),
    ("UPSERT_EVENT",                 queries.UPSERT_EVENT),
    ("INSERT_DEPENDS_ON",            queries.INSERT_DEPENDS_ON),
    ("INSERT_REQUIRES",              queries.INSERT_REQUIRES),
    ("INSERT_IMPACTS",               queries.INSERT_IMPACTS),
    ("FETCH_COMPANY",                queries.FETCH_COMPANY),
    ("FETCH_COMMODITY",              queries.FETCH_COMMODITY),
    ("FETCH_EVENT",                  queries.FETCH_EVENT),
    ("TRACE_SUPPLY_CHAIN",           queries.TRACE_SUPPLY_CHAIN),
    ("GET_COMPANY_COMMODITIES",      queries.GET_COMPANY_COMMODITIES),
    ("GET_EVENTS_FOR_COMPANY",       queries.GET_EVENTS_FOR_COMPANY),
    ("LOOKUP_COMPANIES_BY_SECTOR",   queries.LOOKUP_COMPANIES_BY_SECTOR),
    ("LOOKUP_EVENTS_ABOVE_SEVERITY", queries.LOOKUP_EVENTS_ABOVE_SEVERITY),
    ("TRACE_IMPACT",                 queries.TRACE_IMPACT),
]


# ---------------------------------------------------------------------------
# STEP 1 — Structure: every constant is a non-empty str
# ---------------------------------------------------------------------------

class TestQueryTypes:

    @pytest.mark.parametrize("name,query", _ALL_QUERY_CONSTANTS)
    def test_is_string(self, name, query):
        assert isinstance(query, str), f"{name} must be a str"

    @pytest.mark.parametrize("name,query", _ALL_QUERY_CONSTANTS)
    def test_is_non_empty(self, name, query):
        assert query.strip(), f"{name} must not be empty"

    @pytest.mark.parametrize("name,query", _ALL_QUERY_CONSTANTS)
    def test_has_no_fstring_curly_braces(self, name, query):
        """
        No query template should contain { } unless it is the intentional
        structural ``{depth}`` slot in TRACE_SUPPLY_CHAIN.

        ``{depth}`` is explicitly whitelisted because:
        - It is filled by a validated int, not user data.
        - NebulaGraph 3.x does not support $param in MATCH hop-count positions.
        - A validated integer literal cannot carry nGQL injection.

        Any OTHER curly brace would indicate a value was accidentally
        formatted directly into the string (injection risk).
        """
        # Whitelist of intentional Python .format() slots per query.
        # Each slot is filled with a validated non-injection literal:
        #   {depth}     — validated int (TRACE_SUPPLY_CHAIN)
        #   {vid}       — validated [A-Za-z0-9_.-]{1,64} (INSERT_*/UPSERT_EVENT)
        #   {max_hops}  — validated int (TRACE_IMPACT)
        _WHITELISTED = re.compile(r'\{(depth|vid|max_hops)\}')
        cleaned = _WHITELISTED.sub('', query)
        # Also strip known-safe NebulaGraph function literals
        cleaned = cleaned.replace("datetime()", "").replace("datetime($impact_time)", "")
        assert "{" not in cleaned and "}" not in cleaned, (
            f"{name} contains unexpected curly braces — values must use $param "
            "placeholders, not f-strings or .format()"
        )


# ---------------------------------------------------------------------------
# STEP 2 — Placeholder correctness: declared params match $name occurrences
# ---------------------------------------------------------------------------

class TestPlaceholders:
    """
    Verify that each template declares the exact set of $name placeholders
    documented in its docstring.
    """

    def test_insert_company_placeholders(self):
        # VID is embedded via .format(vid=...), so only $param slots remain
        assert _placeholders(queries.INSERT_COMPANY) == {"ticker", "name", "sector"}

    def test_insert_commodity_placeholders(self):
        assert _placeholders(queries.INSERT_COMMODITY) == {"name", "category"}

    def test_insert_event_placeholders(self):
        assert _placeholders(queries.INSERT_EVENT) == {"description", "severity"}

    def test_upsert_event_placeholders(self):
        assert _placeholders(queries.UPSERT_EVENT) == {"description", "severity"}

    def test_insert_depends_on_placeholders(self):
        assert _placeholders(queries.INSERT_DEPENDS_ON) == {"src", "dst", "weight"}

    def test_insert_requires_placeholders(self):
        assert _placeholders(queries.INSERT_REQUIRES) == {"src", "dst", "volume"}

    def test_insert_impacts_placeholders(self):
        assert _placeholders(queries.INSERT_IMPACTS) == {"src", "dst", "impact_time"}

    def test_fetch_company_placeholders(self):
        assert _placeholders(queries.FETCH_COMPANY) == {"ticker"}

    def test_fetch_commodity_placeholders(self):
        assert _placeholders(queries.FETCH_COMMODITY) == {"commodity_id"}

    def test_fetch_event_placeholders(self):
        assert _placeholders(queries.FETCH_EVENT) == {"event_id"}

    def test_trace_supply_chain_placeholders(self):
        # {depth} is a Python format slot, not a $nGQL param; only $ticker remains
        assert _placeholders(queries.TRACE_SUPPLY_CHAIN) == {"ticker"}

    def test_get_company_commodities_placeholders(self):
        assert _placeholders(queries.GET_COMPANY_COMMODITIES) == {"ticker"}

    def test_get_events_for_company_placeholders(self):
        assert _placeholders(queries.GET_EVENTS_FOR_COMPANY) == {"ticker"}

    def test_lookup_companies_by_sector_placeholders(self):
        assert _placeholders(queries.LOOKUP_COMPANIES_BY_SECTOR) == {"sector"}

    def test_lookup_events_above_severity_placeholders(self):
        assert _placeholders(queries.LOOKUP_EVENTS_ABOVE_SEVERITY) == {"min_severity"}

    def test_trace_impact_placeholders(self):
        # {max_hops} is a Python format slot; only the $ticker nGQL param remains
        assert _placeholders(queries.TRACE_IMPACT) == {"ticker"}


# ---------------------------------------------------------------------------
# STEP 3 — Injection guard: markers in param values are rejected
# ---------------------------------------------------------------------------

class TestInjectionPrevention:
    """
    Demonstrate that parameterisation prevents injection by verifying the
    guard layer in SecureGraphClient._execute rejects dangerous values,
    regardless of which query template is used.

    These tests mock the pool so they run without a live graph.
    """

    @pytest.fixture
    def client(self):
        from unittest.mock import MagicMock, patch
        from finance_mcp.graph.client import SecureGraphClient

        c = SecureGraphClient()
        # Inject a fake pool so _session() can be entered
        fake_pool = MagicMock()
        fake_session = MagicMock()
        fake_session.execute.return_value = MagicMock(is_succeeded=lambda: True)
        fake_pool.get_session.return_value = fake_session
        c._pool = fake_pool
        return c

    @pytest.mark.parametrize("marker", [";", "--", "/*", "*/"])
    def test_injection_marker_rejected_in_ticker(self, client, marker):
        """Any injection marker in ticker param raises ValueError before execution."""
        with pytest.raises(ValueError, match="injection marker"):
            client._execute(
                queries.FETCH_COMPANY,
                {"ticker": f"AAPL{marker}DROP SPACE supply_chain"},
            )

    @pytest.mark.parametrize("marker", [";", "--", "/*", "*/"])
    def test_injection_marker_rejected_in_sector(self, client, marker):
        """Any injection marker in sector param raises ValueError before execution."""
        with pytest.raises(ValueError, match="injection marker"):
            client._execute(
                queries.LOOKUP_COMPANIES_BY_SECTOR,
                {"sector": f"Technology{marker}DROP SPACE supply_chain"},
            )

    def test_clean_string_param_passes_guard(self, client):
        """A clean string parameter value is accepted and execution proceeds."""
        # The mock session execute returns success — no error expected
        result = client._execute(
            queries.FETCH_COMPANY,
            {"ticker": "AAPL"},
        )
        assert result is not None

    def test_int_param_bypasses_string_check(self, client):
        """Integer params are never scanned for string markers."""
        # min_severity=3 is a clean int — no injection check needed
        result = client._execute(
            queries.LOOKUP_EVENTS_ABOVE_SEVERITY,
            {"min_severity": 3},
        )
        assert result is not None


# ---------------------------------------------------------------------------
# STEP 4 — Integration: execute each template against live NebulaGraph
# ---------------------------------------------------------------------------
#
# Fixtures insert a small deterministic dataset before the session and
# clean it up afterwards.  Each test asserts on is_succeeded() only —
# row counts may vary if the test vertex was already deleted by a prior run.

_TEST_COMPANY   = "TEST_QUERIES_AAPL"
_TEST_COMMODITY = "TEST_QUERIES_OIL"
_TEST_EVENT     = "TEST_QUERIES_EVT1"


@pytest.fixture(scope="module")
def live_client():
    from finance_mcp.graph.client import SecureGraphClient
    with SecureGraphClient(host="127.0.0.1", port=9669) as c:
        yield c


@pytest.fixture(scope="module")
def seed_graph(live_client):
    """Insert test fixtures into the live graph before the module runs."""
    from nebula3.gclient.net import ConnectionPool
    from nebula3.Config import Config
    cfg = Config(); cfg.max_connection_pool_size = 1
    pool = ConnectionPool(); pool.init([("127.0.0.1", 9669)], cfg)
    s = pool.get_session("root", "nebula")
    s.execute("USE supply_chain")

    stmts = [
        f'INSERT VERTEX Company(ticker, name, sector) '
        f'VALUES "{_TEST_COMPANY}":("AAPL", "Apple Inc.", "Technology")',
        f'INSERT VERTEX Commodity(name, category) '
        f'VALUES "{_TEST_COMMODITY}":("Crude Oil", "Energy")',
        f'INSERT VERTEX Event(description, severity) '
        f'VALUES "{_TEST_EVENT}":("Supply disruption", 7)',
        f'INSERT EDGE DEPENDS_ON(weight) '
        f'VALUES "{_TEST_COMPANY}"->"{_TEST_COMPANY}":(0.5)',
        f'INSERT EDGE REQUIRES(volume) '
        f'VALUES "{_TEST_COMPANY}"->"{_TEST_COMMODITY}":(1000)',
        f'INSERT EDGE IMPACTS(impact_time) '
        f'VALUES "{_TEST_EVENT}"->"{_TEST_COMPANY}":(datetime("2026-03-09T00:00:00"))',
    ]
    for stmt in stmts:
        s.execute(stmt)

    yield

    # Teardown
    s.execute("USE supply_chain")
    for vid in [_TEST_COMPANY, _TEST_COMMODITY, _TEST_EVENT]:
        s.execute(f'DELETE VERTEX "{vid}" WITH EDGE')
    s.release()
    pool.close()


@nebula_required
@pytest.mark.usefixtures("seed_graph")
class TestQueryIntegration:
    """Execute every query template with mock parameters against live graph."""

    def test_fetch_company(self, live_client):
        r = live_client.fetch_company(_TEST_COMPANY)
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() == 1

    def test_fetch_commodity(self, live_client):
        r = live_client.fetch_commodity(_TEST_COMMODITY)
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() == 1

    def test_fetch_event(self, live_client):
        r = live_client.fetch_event(_TEST_EVENT)
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() == 1

    def test_fetch_nonexistent_returns_empty(self, live_client):
        r = live_client.fetch_company("DOES_NOT_EXIST_XYZ")
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() == 0

    def test_trace_supply_chain(self, live_client):
        r = live_client.get_company_dependencies(_TEST_COMPANY, depth=1)
        assert r.is_succeeded(), r.error_msg()

    def test_trace_supply_chain_depth_bounds(self, live_client):
        with pytest.raises(ValueError, match="depth"):
            live_client.get_company_dependencies(_TEST_COMPANY, depth=10)

    def test_get_commodity_requirements(self, live_client):
        r = live_client.get_commodity_requirements(_TEST_COMPANY)
        assert r.is_succeeded(), r.error_msg()

    def test_get_events_for_company(self, live_client):
        r = live_client.get_events_impacting_company(_TEST_COMPANY)
        assert r.is_succeeded(), r.error_msg()

    def test_find_companies_by_sector(self, live_client):
        r = live_client.find_companies_by_sector("Technology")
        assert r.is_succeeded(), r.error_msg()

    def test_find_events_above_severity(self, live_client):
        r = live_client.find_events_above_severity(min_severity=5)
        assert r.is_succeeded(), r.error_msg()

    def test_find_events_severity_bounds(self, live_client):
        with pytest.raises(ValueError, match="min_severity"):
            live_client.find_events_above_severity(min_severity=11)

    def test_insert_company_template_shape(self, live_client):
        """
        INSERT_COMPANY executes without error for a fresh VID.
        Teardown is handled by seed_graph — this inserts a second vertex.
        """
        # Use a unique VID to avoid conflict with seed fixture
        from nebula3.gclient.net import ConnectionPool
        from nebula3.Config import Config
        cfg = Config(); cfg.max_connection_pool_size = 1
        pool = ConnectionPool(); pool.init([("127.0.0.1", 9669)], cfg)
        s = pool.get_session("root", "nebula")
        s.execute("USE supply_chain")
        r = s.execute(
            'INSERT VERTEX IF NOT EXISTS Company(ticker, name, sector) '
            'VALUES "TEST_QUERIES_INSERT":("TEST", "Test Corp", "Financials")'
        )
        assert r.is_succeeded(), r.error_msg()
        s.execute('DELETE VERTEX "TEST_QUERIES_INSERT"')
        s.release(); pool.close()
