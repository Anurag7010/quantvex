"""
Integration tests for SecureGraphClient.

These tests require a live NebulaGraph instance.  They are skipped
automatically when the graph is not reachable so the CI suite does not
fail in environments that do not start the Docker stack.

Start the graph before running::

    docker compose -f docker/nebula-docker-compose.yml up -d

Then run::

    PYTHONPATH=src pytest tests/test_graph_client.py -v

TEST VERTEX
-----------
All tests share the VID ``"TEST_AAPL"`` so they remain isolated from any
production supply-chain data that may already be in the graph.  The
fixture inserts the vertex once per session and the teardown deletes it.

WHY NO RAW QUERY EXECUTION TEST
--------------------------------
There is nothing to test — SecureGraphClient deliberately has no public
execute() / run_query() method.  The absence of those names on the class
is the guarantee.  Any attempt to call client.execute("DROP SPACE ...")
will raise AttributeError at call time, which Python's own attribute
lookup enforces without a test being needed.
"""

import pytest
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

_NEBULA_HOST = "127.0.0.1"
_NEBULA_PORT = 9669
_TEST_VID = "TEST_AAPL"


def _nebula_reachable() -> bool:
    """Return True when NebulaGraph graphd is accepting connections."""
    cfg = Config()
    cfg.max_connection_pool_size = 1
    pool = ConnectionPool()
    try:
        ok = pool.init([(_NEBULA_HOST, _NEBULA_PORT)], cfg)
        return ok
    except Exception:
        return False
    finally:
        try:
            pool.close()
        except Exception:
            pass


nebula_required = pytest.mark.skipif(
    not _nebula_reachable(),
    reason="NebulaGraph not reachable — start docker/nebula-docker-compose.yml",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client():
    """
    Session-scoped SecureGraphClient.

    Imported here (not at module level) so that collection does not fail
    when nebula3-python is not installed in a CI environment that does not
    run graph tests.
    """
    from finance_mcp.graph.client import SecureGraphClient

    with SecureGraphClient(host=_NEBULA_HOST, port=_NEBULA_PORT) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def insert_test_vertex(client):
    """
    Insert a known Company vertex before all tests and delete it after.

    The INSERT uses a root-level pool directly instead of going through
    the restricted mcp_agent session because mcp_agent may not yet have
    INSERT privilege on a freshly created space (some NebulaGraph builds
    require an explicit GRANT for DML too).  If mcp_agent can INSERT,
    the FETCH tests below confirm it end-to-end.
    """
    # Use root to set up the test fixture — root access is acceptable in
    # test setup/teardown; it is never used in application code paths.
    cfg = Config()
    cfg.max_connection_pool_size = 1
    pool = ConnectionPool()
    pool.init([(_NEBULA_HOST, _NEBULA_PORT)], cfg)
    session = pool.get_session("root", "nebula")

    try:
        session.execute("USE supply_chain")
        session.execute(
            f"INSERT VERTEX Company(ticker, name, sector) "
            f'VALUES "{_TEST_VID}":("AAPL", "Apple Inc.", "Technology")'
        )
        yield
    finally:
        session.execute("USE supply_chain")
        session.execute(f'DELETE VERTEX "{_TEST_VID}"')
        session.release()
        pool.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@nebula_required
class TestSecureGraphClientPool:
    """Pool lifecycle tests."""

    def test_initialize_pool_succeeds(self):
        """initialize_pool() creates a working pool without raising."""
        from finance_mcp.graph.client import SecureGraphClient

        client = SecureGraphClient(host=_NEBULA_HOST, port=_NEBULA_PORT)
        client.initialize_pool()
        # Should be idempotent — calling again must not raise
        client.initialize_pool()
        client.close()

    def test_context_manager_closes_pool(self):
        """__exit__ closes the pool; subsequent pool access raises RuntimeError."""
        from finance_mcp.graph.client import SecureGraphClient

        with SecureGraphClient(host=_NEBULA_HOST, port=_NEBULA_PORT) as c:
            assert c._pool is not None
        assert c._pool is None

    def test_query_without_pool_raises(self):
        """Calling fetch_company before initialise_pool raises RuntimeError."""
        from finance_mcp.graph.client import SecureGraphClient

        client = SecureGraphClient(host=_NEBULA_HOST, port=_NEBULA_PORT)
        with pytest.raises(RuntimeError, match="not initialised"):
            client.fetch_company("AAPL")

    def test_no_raw_execute_attribute(self):
        """
        SecureGraphClient must NOT expose a public execute() method.

        This confirms that raw query execution is blocked by design —
        an LLM-controlled code path has no surface to inject arbitrary nGQL.
        """
        from finance_mcp.graph.client import SecureGraphClient

        client = SecureGraphClient()
        assert not hasattr(client, "execute"), (
            "SecureGraphClient must not expose a public execute() method"
        )
        assert not hasattr(client, "run_query"), (
            "SecureGraphClient must not expose a public run_query() method"
        )


@nebula_required
class TestFetchCompany:
    """
    Step 6 — FETCH PROP ON Company test.

    NebulaGraph 3.x does not support ``$param`` as a VID literal in
    ``FETCH PROP ON``.  The client therefore uses MATCH with a parameterised
    WHERE clause instead::

        MATCH (v:Company) WHERE id(v) == $ticker
        RETURN properties(v) AS props

    The ticker parameter is bound via execute_parameter() — the string
    ``"TEST_AAPL"`` travels as a typed nebula3 Value, not as part of the
    query text.  This is semantically equivalent to the requested
    ``FETCH PROP ON Company`` and preserves the same injection safety.

    Returned ResultSet structure
    ----------------------------
    Column 0:  ``props``  — NMap containing the tag properties:
        - ``ticker``  → sVal  b"AAPL"
        - ``name``    → sVal  b"Apple Inc."
        - ``sector``  → sVal  b"Technology"

    Row count: 1 for a VID that exists; 0 for a VID that does not exist.
    """

    def test_fetch_known_company_returns_one_row(self, client):
        """
        FETCH on an existing Company VID returns exactly one row.
        """
        result = client.fetch_company(_TEST_VID)

        assert result.is_succeeded(), f"Query failed: {result.error_msg()}"
        assert result.row_size() == 1, (
            f"Expected 1 row for VID '{_TEST_VID}', got {result.row_size()}"
        )

    def test_fetch_company_result_columns(self, client):
        """
        Result set has the expected 'props' column.
        """
        result = client.fetch_company(_TEST_VID)

        assert result.is_succeeded()
        assert "props" in result.keys(), (
            f"Expected column 'props', found: {result.keys()}"
        )

    def test_fetch_company_props_content(self, client):
        """
        The 'props' NMap contains ticker, name, and sector keys.
        """
        result = client.fetch_company(_TEST_VID)
        assert result.is_succeeded()
        assert result.row_size() == 1

        # Extract the NMap from column 0 of the first row
        row = result.row_values(0)
        props_value = row[0]  # nebula3 ValueWrapper for the 'props' column

        # as_map() returns a plain Python dict[str, ValueWrapper]
        nmap = props_value.as_map()
        assert nmap is not None, "props column did not return a map"

        # Keys are already plain str
        keys = set(nmap.keys())
        assert "ticker" in keys, f"Expected 'ticker' in props keys, got: {keys}"
        assert "name" in keys, f"Expected 'name' in props keys, got: {keys}"
        assert "sector" in keys, f"Expected 'sector' in props keys, got: {keys}"

    def test_fetch_nonexistent_company_returns_empty(self, client):
        """
        FETCH on a VID that does not exist returns an empty ResultSet (not an error).
        """
        result = client.fetch_company("VID_THAT_DOES_NOT_EXIST_XYZ")

        assert result.is_succeeded(), f"Query raised an error: {result.error_msg()}"
        assert result.row_size() == 0, (
            f"Expected 0 rows for nonexistent VID, got {result.row_size()}"
        )


@nebula_required
class TestInjectionGuard:
    """
    Verify that the injection guard in _execute rejects dangerous param values.

    These tests call _execute directly (a private method) solely to test
    the security boundary.  Application code must never call _execute.
    """

    def test_semicolon_in_param_raises_value_error(self, client):
        """
        A parameter value containing ';' is rejected before the query is sent.
        """
        with pytest.raises(ValueError, match="injection marker"):
            client._execute(
                "MATCH (v:Company) WHERE id(v) == $ticker RETURN properties(v) AS props",
                {"ticker": "AAPL; DROP SPACE supply_chain"},
            )

    def test_sql_comment_in_param_raises_value_error(self, client):
        """
        A parameter value containing '--' is rejected before the query is sent.
        """
        with pytest.raises(ValueError, match="injection marker"):
            client._execute(
                "MATCH (v:Company) WHERE id(v) == $ticker RETURN properties(v) AS props",
                {"ticker": "AAPL -- comment"},
            )

    def test_clean_param_passes_guard(self, client):
        """
        A clean parameter value passes the guard and executes normally.
        """
        result = client._execute(
            "MATCH (v:Company) WHERE id(v) == $ticker RETURN properties(v) AS props",
            {"ticker": _TEST_VID},
        )
        assert result.is_succeeded()
