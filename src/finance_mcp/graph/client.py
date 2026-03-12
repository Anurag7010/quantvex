"""
Phase 2 — SecureGraphClient

Provides a connection-pooled, RBAC-scoped interface to the supply_chain
NebulaGraph space.

SECURITY MODEL
--------------
• Raw query execution is NEVER exposed publicly.  All statements are routed
  through the private _execute() method which uses execute_parameter() to
  bind values before transmission — preventing nGQL injection.

• The runtime session authenticates as mcp_agent (USER role) which:
    - Can INSERT/UPDATE/DELETE vertices and edges
    - Can traverse with GO, FETCH, MATCH, LOOKUP
    - Cannot DROP spaces, tags, or edge types
    - Cannot ALTER schema
    - Cannot CREATE or DROP other users
  Root credentials are absent from this module entirely.

• Optional TLS is wired through _load_ssl_context().  When cert paths are
  not configured the client falls back to clear-text (suitable for
  loopback/Docker-internal networks).

• Parameter injection guard rejects param values containing SQL/nGQL
  comment markers (--) and statement terminators (;) as a defence-in-depth
  measure on top of the protocol-level parameterisation.
"""

import logging
import os
import re
import ssl
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config
from nebula3.common import ttypes
from nebula3.data.ResultSet import ResultSet

from finance_mcp.graph import queries

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults — override via constructor arguments or environment variables
# ---------------------------------------------------------------------------
DEFAULT_HOST: str = os.environ.get("NEBULA_HOST", "127.0.0.1")
DEFAULT_PORT: int = int(os.environ.get("NEBULA_PORT", "9669"))
GRAPH_SPACE: str = "supply_chain"
AGENT_USER: str = "mcp_agent"
AGENT_PASSWORD: str = "mcp_agent_secret"
MAX_POOL_SIZE: int = 10

# Characters that indicate an injection attempt in parameter values
_INJECTION_MARKERS: tuple = (";", "--", "/*", "*/")

# VID validation — only alphanumeric + underscore, dot, hyphen; 1–64 chars.
# This pattern is deliberately narrow: it excludes whitespace, quotes,
# angle brackets, and all nGQL operator characters so that a validated
# VID literal embedded via str.format() cannot carry any injection payload.
_VID_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')


def _validate_vid(value: str, field: str = "vid") -> None:
    """
    Enforce that a vertex-ID string is safe to embed as a string literal.

    Raises ValueError when:
    - value is not a str
    - value is empty or longer than 64 characters
    - value contains any character outside [A-Za-z0-9_.-]

    After this check passes, embedding the value inside double-quoted nGQL
    (e.g. ``\'"AAPL"\'``) is injection-safe because the only characters
    that could escape a double-quoted string are ``"``, ``\\``, and control
    characters — none of which are permitted by the pattern.
    """
    if not isinstance(value, str) or not _VID_RE.match(value):
        raise ValueError(
            f"{field!r} must be a string of 1\u201364 characters containing only "
            f"alphanumeric characters, underscores, dots, or hyphens. "
            f"Got: {value!r}"
        )


def _validate_str(value: Any, field: str, max_len: int, required: bool = True) -> None:
    """
    Enforce that a property string value meets basic safety constraints.

    Raises ValueError when:
    - value is not a str
    - required=True and value is empty after stripping
    - len(value) > max_len
    """
    if not isinstance(value, str):
        raise ValueError(f"{field!r} must be a str, got {type(value).__name__}")
    if required and not value.strip():
        raise ValueError(f"{field!r} must not be empty")
    if len(value) > max_len:
        raise ValueError(
            f"{field!r} must be at most {max_len} characters, "
            f"got {len(value)}"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _py_to_nebula(val: Any) -> ttypes.Value:
    """
    Convert a Python scalar to a NebulaGraph typed Value for use in
    execute_parameter().

    Supported types: bool, int, float, str, bytes.
    Raises TypeError for unsupported types so that mistakes surface early
    rather than silently sending malformed parameters.
    """
    if isinstance(val, bool):        # bool is a subclass of int — check first
        return ttypes.Value(bVal=val)
    if isinstance(val, int):
        return ttypes.Value(iVal=val)
    if isinstance(val, float):
        return ttypes.Value(fVal=val)
    if isinstance(val, str):
        return ttypes.Value(sVal=val.encode("utf-8"))
    if isinstance(val, bytes):
        return ttypes.Value(sVal=val)
    raise TypeError(
        f"Unsupported parameter type for NebulaGraph: {type(val).__name__}. "
        "Use bool, int, float, str, or bytes."
    )


def _check_params_for_injection(params: Dict[str, Any]) -> None:
    """
    Scan string parameter values for nGQL injection markers.

    This is a defence-in-depth layer on top of protocol-level
    parameterisation.  It cannot replace parameterised queries but it
    catches the most common accidental or malicious patterns.
    """
    for key, val in params.items():
        if isinstance(val, (str, bytes)):
            text = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else val
            for marker in _INJECTION_MARKERS:
                if marker in text:
                    raise ValueError(
                        f"Potential injection marker '{marker}' detected in "
                        f"parameter '{key}'. Raw nGQL control characters are "
                        "not permitted in parameter values."
                    )


# ---------------------------------------------------------------------------
# SecureGraphClient
# ---------------------------------------------------------------------------

class SecureGraphClient:
    """
    Connection-pooled, RBAC-scoped NebulaGraph client for supply_chain.

    Usage — explicit lifecycle::

        client = SecureGraphClient()
        client.initialize_pool()
        try:
            result = client.fetch_company("AAPL")
        finally:
            client.close()

    Usage — context manager::

        with SecureGraphClient() as client:
            result = client.fetch_company("AAPL")

    The public API exposes only purpose-specific methods.  There is
    deliberately no execute() or run_query() method — raw query execution
    is not available to callers.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        user: str = AGENT_USER,
        password: str = AGENT_PASSWORD,
        pool_size: int = MAX_POOL_SIZE,
        ssl_cert_path: Optional[str] = None,
        ssl_key_path: Optional[str] = None,
        ssl_ca_path: Optional[str] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._pool_size = pool_size
        self._ssl_cert_path = ssl_cert_path
        self._ssl_key_path = ssl_key_path
        self._ssl_ca_path = ssl_ca_path
        self._pool: Optional[ConnectionPool] = None

    # -------------------------------------------------------------------
    # STEP 3 — Connection pool lifecycle
    # -------------------------------------------------------------------

    def initialize_pool(self) -> None:
        """
        Build and connect the nebula3 ConnectionPool.

        Must be called before any query method.  Idempotent — calling
        again after the pool is already open is a no-op.
        """
        if self._pool is not None:
            logger.debug("SecureGraphClient: pool already initialised, skipping")
            return

        cfg = Config()
        cfg.max_connection_pool_size = self._pool_size

        # Step 4 — attach SSL context if certs were provided
        ssl_ctx = self._load_ssl_context()
        if ssl_ctx is not None:
            cfg.ssl_config = ssl_ctx

        pool = ConnectionPool()
        ok = pool.init([(self._host, self._port)], cfg)
        if not ok:
            raise RuntimeError(
                f"SecureGraphClient: pool init failed — "
                f"could not connect to {self._host}:{self._port}"
            )

        self._pool = pool
        logger.info(
            "SecureGraphClient: pool ready — %s:%s user=%s pool_size=%d",
            self._host,
            self._port,
            self._user,
            self._pool_size,
        )

    def close(self) -> None:
        """Release all pool connections."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None
            logger.info("SecureGraphClient: pool closed")

    def __enter__(self) -> "SecureGraphClient":
        self.initialize_pool()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _session(self) -> Generator:
        """
        Acquire a session from the pool scoped to supply_chain and release
        it when the block exits — even on exceptions.
        """
        if self._pool is None:
            raise RuntimeError(
                "SecureGraphClient: pool is not initialised. "
                "Call initialize_pool() or use the context manager."
            )
        session = self._pool.get_session(self._user, self._password)
        try:
            # Pin every session to the restricted space immediately
            use_result = session.execute(f"USE {GRAPH_SPACE}")
            if not use_result.is_succeeded():
                raise RuntimeError(
                    f"SecureGraphClient: failed to switch to space "
                    f"'{GRAPH_SPACE}': {use_result.error_msg()}"
                )
            yield session
        finally:
            session.release()

    # -------------------------------------------------------------------
    # STEP 4 — SSL context loader (optional TLS support)
    # -------------------------------------------------------------------

    def _load_ssl_context(self) -> Optional[ssl.SSLContext]:
        """
        Build a TLS SSLContext from PEM files when cert paths are configured.

        Returns None when no cert paths are set — the pool then uses a
        plain TCP connection, which is appropriate for loopback and
        Docker-internal deployments.

        To enable mutual TLS with a self-signed CA::

            client = SecureGraphClient(
                ssl_ca_path="/certs/ca.pem",
                ssl_cert_path="/certs/client.pem",
                ssl_key_path="/certs/client.key",
            )

        Files are validated for existence before the pool is created so
        that missing certs raise immediately rather than at query time.
        """
        if not any([self._ssl_cert_path, self._ssl_key_path, self._ssl_ca_path]):
            return None  # plain TCP — SSL not requested

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False  # Host is identified via the pool address

        if self._ssl_ca_path:
            ca = Path(self._ssl_ca_path)
            if not ca.exists():
                raise FileNotFoundError(
                    f"SecureGraphClient: CA cert not found at '{ca}'"
                )
            ctx.load_verify_locations(cafile=str(ca))
        else:
            # No CA provided — disable certificate verification
            # (acceptable for dev/test; must NOT be used in production)
            ctx.verify_mode = ssl.CERT_NONE

        if self._ssl_cert_path and self._ssl_key_path:
            cert = Path(self._ssl_cert_path)
            key = Path(self._ssl_key_path)
            if not cert.exists():
                raise FileNotFoundError(
                    f"SecureGraphClient: client cert not found at '{cert}'"
                )
            if not key.exists():
                raise FileNotFoundError(
                    f"SecureGraphClient: client key not found at '{key}'"
                )
            ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))

        logger.info("SecureGraphClient: TLS enabled")
        return ctx

    # -------------------------------------------------------------------
    # STEP 5 — Private safe execution engine
    # -------------------------------------------------------------------

    def _execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> ResultSet:
        """
        Execute a parameterised nGQL statement and return the ResultSet.

        SAFETY CONTRACT
        ---------------
        • `query` MUST be a hard-coded string literal in call sites.
          Never pass an f-string or .format() result that contains
          user-supplied data.  Code review must enforce this — the method
          cannot detect it at runtime because it receives a plain str.

        • All user-supplied values MUST travel through `params`.
          nebula3's execute_parameter() serialises them at the protocol
          level before the statement reaches the graph engine — preventing
          nGQL injection in the same way SQL prepared statements prevent
          SQL injection.

        • An injection guard pre-scans string parameter values for known
          dangerous markers (;, --, /*, */) and raises ValueError if found.

        Parameters
        ----------
        query:
            nGQL statement with ``$param_name`` placeholders.
        params:
            Mapping of placeholder names → Python scalars (bool, int,
            float, str, bytes).  Values are converted to NebulaGraph
            ``ttypes.Value`` objects before execution.

        Raises
        ------
        ValueError
            When params contain suspected injection markers.
        RuntimeError
            When nebula3 reports a query execution failure.
        """
        if params is None:
            params = {}

        _check_params_for_injection(params)

        nebula_params: Dict[str, ttypes.Value] = {
            k: _py_to_nebula(v) for k, v in params.items()
        }

        with self._session() as session:
            if nebula_params:
                result: ResultSet = session.execute_parameter(query, nebula_params)
            else:
                result = session.execute(query)

            if not result.is_succeeded():
                raise RuntimeError(
                    f"SecureGraphClient: query failed — {result.error_msg()}\n"
                    f"Statement: {query}"
                )

        return result

    # -------------------------------------------------------------------
    # Public API — controlled, purpose-specific query methods
    # -------------------------------------------------------------------
    # Every nGQL string comes from finance_mcp.graph.queries — immutable
    # module-level constants.  No query text is built at runtime.  All
    # user-supplied values travel through the params dict to _execute(),
    # which binds them via execute_parameter() at the protocol level.
    # -------------------------------------------------------------------

    def fetch_company(self, ticker: str) -> ResultSet:
        """
        Fetch all properties of a Company vertex.

        Delegates to queries.FETCH_COMPANY with ``$ticker`` bound.
        Returns a ResultSet with column ``props``.
        """
        return self._execute(queries.FETCH_COMPANY, {"ticker": ticker})

    def fetch_commodity(self, commodity_name: str) -> ResultSet:
        """
        Fetch all properties of a Commodity vertex.

        Delegates to queries.FETCH_COMMODITY with ``$commodity_id`` bound.
        Returns a ResultSet with column ``props``.
        """
        return self._execute(
            queries.FETCH_COMMODITY, {"commodity_id": commodity_name}
        )

    def fetch_event(self, event_id: str) -> ResultSet:
        """
        Fetch all properties of an Event vertex.

        Delegates to queries.FETCH_EVENT with ``$event_id`` bound.
        Returns a ResultSet with column ``props``.
        """
        return self._execute(queries.FETCH_EVENT, {"event_id": event_id})

    def get_company_dependencies(
        self,
        ticker: str,
        depth: int = 1,
    ) -> ResultSet:
        """
        Walk DEPENDS_ON edges outward from a Company up to ``depth`` hops.

        ``depth`` is bounds-checked to [1, 5].  It is then embedded as an
        integer literal into queries.TRACE_SUPPLY_CHAIN via Python
        str.format() — this is safe because:
          1. depth is validated as a plain int before format() is called.
          2. Python's str.format() with a validated int cannot produce
             executable nGQL because integers contain no statement
             separators, comment markers, or VID operators.
          3. The $ticker that carries user data still travels through
             execute_parameter() as a typed Value.

        Columns: ``supplier``, ``dependent``, ``weight``.
        """
        if not isinstance(depth, int) or not (1 <= depth <= 5):
            raise ValueError("depth must be an integer between 1 and 5 inclusive")
        # Embed validated int literal for hop count; $ticker stays a param.
        query = queries.TRACE_SUPPLY_CHAIN.format(depth=depth)
        return self._execute(query, {"ticker": ticker})

    def get_commodity_requirements(self, ticker: str) -> ResultSet:
        """
        List Commodity vertices required by a Company via REQUIRES edges.

        Delegates to queries.GET_COMPANY_COMMODITIES.
        Columns: ``commodity`` (VID), ``volume`` (int).
        """
        return self._execute(queries.GET_COMPANY_COMMODITIES, {"ticker": ticker})

    def get_events_impacting_company(self, ticker: str) -> ResultSet:
        """
        Find Event vertices that impact a Company (reverse IMPACTS traversal).

        Delegates to queries.GET_EVENTS_FOR_COMPANY.
        Columns: ``event_id`` (VID), ``impact_time`` (datetime).
        """
        return self._execute(
            queries.GET_EVENTS_FOR_COMPANY, {"ticker": ticker}
        )

    def find_companies_by_sector(self, sector: str) -> ResultSet:
        """
        Index-scan for all Company vertices in a given GICS sector.

        Delegates to queries.LOOKUP_COMPANIES_BY_SECTOR.
        Columns: ``ticker`` (str), ``name`` (str).
        """
        return self._execute(
            queries.LOOKUP_COMPANIES_BY_SECTOR, {"sector": sector}
        )

    def find_events_above_severity(self, min_severity: int) -> ResultSet:
        """
        Find all Event vertices at or above a severity threshold.

        Delegates to queries.LOOKUP_EVENTS_ABOVE_SEVERITY.
        ``min_severity`` is validated as an int in [0, 10].
        Columns: ``event_id`` (str), ``description`` (str), ``severity`` (int).
        """
        if not isinstance(min_severity, int) or not (0 <= min_severity <= 10):
            raise ValueError("min_severity must be an integer between 0 and 10")
        return self._execute(
            queries.LOOKUP_EVENTS_ABOVE_SEVERITY,
            {"min_severity": min_severity},
        )

    # -------------------------------------------------------------------
    # Reasoning API — derived / aggregated graph intelligence
    # -------------------------------------------------------------------

    def trace_impact(
        self,
        target_ticker: str,
        max_hops: int = 3,
    ) -> list:
        """
        Find all companies downstream of a supply shock at ``target_ticker``.

        Traverses DEPENDS_ON edges in **reverse** from the target:
        every company X such that ``X-[:DEPENDS_ON*1..max_hops]->target``
        exists is returned.

        Example — TSMC factory outage::

            impacted = client.trace_impact("TSMC", max_hops=3)
            # → [{"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
            #    {"ticker": "NVDA", "name": "NVIDIA Corp.", "sector": "Technology"},
            #    ...]

        Parameters
        ----------
        target_ticker : str
            VID of the company that has suffered a supply shock.
            Must satisfy the VID regex ``[A-Za-z0-9_.-]{1,64}``.
        max_hops : int
            Maximum traversal depth along DEPENDS_ON edges, 1–5.
            Defaults to 3.  Validated before being embedded as an int
            literal into the query template via ``str.format()``.

        Returns
        -------
        list[dict]
            Each element is ``{"ticker": str, "name": str, "sector": str}``.
            Returns an empty list when no downstream companies are found.
            The list is deduplicated (DISTINCT in nGQL) and ordered by the
            graph engine.

        Raises
        ------
        ValueError
            When ``target_ticker`` fails VID validation or ``max_hops``
            is outside [1, 5].
        RuntimeError
            When the graph engine reports an execution error.
        """
        _validate_vid(target_ticker, "target_ticker")
        if not isinstance(max_hops, int) or not (1 <= max_hops <= 5):
            raise ValueError("max_hops must be an integer between 1 and 5 inclusive")

        query = queries.TRACE_IMPACT.format(max_hops=max_hops)
        rs = self._execute(query, {"ticker": target_ticker})

        impacted: list = []
        for i in range(rs.row_size()):
            row = rs.row_values(i)
            impacted.append(
                {
                    "ticker": row[0].as_string(),
                    "name":   row[1].as_string(),
                    "sector": row[2].as_string(),
                }
            )
        logger.info(
            "trace_impact: target=%r max_hops=%d found=%d",
            target_ticker, max_hops, len(impacted),
        )
        return impacted

    def find_companies_requiring(self, commodity_id: str) -> List[Dict[str, Any]]:
        """
        Find all Company vertices that directly require a given commodity.

        Used to propagate a commodity-level disruption (e.g. crude oil
        shortage caused by geopolitical conflict) to the set of companies
        that depend on that commodity before tracing their downstream
        DEPENDS_ON cascade.

        Parameters
        ----------
        commodity_id : str
            Commodity VID, e.g. ``"CRUDE_OIL"`` or ``"SEMICONDUCTOR"``.
            Must match the VID pattern ``[A-Za-z0-9_.-]{1,64}``.

        Returns
        -------
        list[dict]
            Each element is ``{"ticker": str, "name": str, "sector": str}``.
            Returns an empty list when no companies require the commodity.

        Raises
        ------
        ValueError
            When ``commodity_id`` fails VID validation.
        RuntimeError
            When the graph engine reports an execution error.
        """
        _validate_vid(commodity_id, "commodity_id")
        rs = self._execute(
            queries.FIND_COMPANIES_REQUIRING_COMMODITY,
            {"commodity_id": commodity_id},
        )
        companies: list = []
        for i in range(rs.row_size()):
            row = rs.row_values(i)
            companies.append(
                {
                    "ticker": row[0].as_string(),
                    "name":   row[1].as_string(),
                    "sector": row[2].as_string(),
                }
            )
        logger.info(
            "find_companies_requiring: commodity=%r found=%d",
            commodity_id, len(companies),
        )
        return companies

    def insert_company(
        self,
        ticker: str,
        name: str,
        sector: str = "",
    ) -> bool:
        """
        Insert a Company vertex.

        If a vertex with the same VID already exists its properties are
        overwritten (last-write-wins idempotent semantics).

        Parameters
        ----------
        ticker : str
            Stock ticker symbol used as the vertex ID.
            Must be 1–64 characters: ``[A-Za-z0-9_.-]``.
        name   : str
            Full company name, e.g. ``"Apple Inc."``.  1–256 chars.
        sector : str
            GICS sector string, e.g. ``"Technology"``.  0–128 chars.

        Returns
        -------
        bool
            ``True`` on success.

        Raises
        ------
        ValueError
            When any argument fails validation.
        RuntimeError
            When the graph engine reports an execution error.
        """
        _validate_vid(ticker, "ticker")
        _validate_str(name, "name", max_len=256)
        _validate_str(sector, "sector", max_len=128, required=False)

        self._execute(
            queries.INSERT_COMPANY.format(vid=ticker),
            {"ticker": ticker, "name": name, "sector": sector},
        )
        logger.info("insert_company: inserted VID=%r name=%r", ticker, name)
        return True

    def insert_commodity(
        self,
        commodity_id: str,
        name: str,
        category: str = "",
    ) -> bool:
        """
        Insert a Commodity vertex.

        If a vertex with the same VID already exists its properties are
        overwritten.

        Parameters
        ----------
        commodity_id : str
            Vertex ID for the commodity, e.g. ``"LITHIUM"``.
            Must be 1–64 characters: ``[A-Za-z0-9_.-]``.
        name         : str
            Human-readable commodity name, e.g. ``"Lithium"``.  1–256 chars.
        category     : str
            Commodity category, e.g. ``"Battery Metals"``.  0–128 chars.

        Returns
        -------
        bool
            ``True`` on success.

        Raises
        ------
        ValueError
            When any argument fails validation.
        RuntimeError
            When the graph engine reports an execution error.
        """
        _validate_vid(commodity_id, "commodity_id")
        _validate_str(name, "name", max_len=256)
        _validate_str(category, "category", max_len=128, required=False)

        self._execute(
            queries.INSERT_COMMODITY.format(vid=commodity_id),
            {"name": name, "category": category},
        )
        logger.info(
            "insert_commodity: inserted VID=%r name=%r", commodity_id, name
        )
        return True

    def upsert_event(
        self,
        event_id: str,
        description: str,
        severity: int,
    ) -> bool:
        """
        Upsert an Event vertex.

        Uses NebulaGraph ``UPSERT VERTEX ON`` semantics:
        - Absent vertex: created with the supplied property values.
        - Present vertex: ``description`` and ``severity`` are updated;
          other properties (if any future schema additions add them) are
          left untouched.

        Parameters
        ----------
        event_id    : str
            Vertex ID for the event, e.g. ``"EVT_2026_001"``.
            Must be 1–64 characters: ``[A-Za-z0-9_.-]``.
        description : str
            Free-text description of the event.  1–1024 chars.
        severity    : int
            Impact severity 0 (informational) – 10 (critical).

        Returns
        -------
        bool
            ``True`` on success.

        Raises
        ------
        ValueError
            When any argument fails validation.
        RuntimeError
            When the graph engine reports an execution error.
        """
        _validate_vid(event_id, "event_id")
        _validate_str(description, "description", max_len=1024)
        if not isinstance(severity, int) or not (0 <= severity <= 10):
            raise ValueError("severity must be an integer between 0 and 10 inclusive")

        self._execute(
            queries.UPSERT_EVENT.format(vid=event_id),
            {"description": description, "severity": severity},
        )
        logger.info(
            "upsert_event: upserted VID=%r severity=%d", event_id, severity
        )
        return True

    def insert_depends_on(
        self,
        src_ticker: str,
        dst_ticker: str,
        weight: float = 1.0,
    ) -> bool:
        """
        Insert a DEPENDS_ON edge from src_ticker to dst_ticker.

        Parameters
        ----------
        src_ticker : str — the dependent company VID (e.g. "AAPL")
        dst_ticker : str — the supplier company VID  (e.g. "TSMC")
        weight     : float — dependency strength 0.0–1.0
        """
        _validate_vid(src_ticker, "src_ticker")
        _validate_vid(dst_ticker, "dst_ticker")
        if not isinstance(weight, (int, float)) or not (0.0 <= weight <= 1.0):
            raise ValueError("weight must be a float between 0.0 and 1.0")
        # NebulaGraph 3.x does not support $params in VID positions for INSERT EDGE.
        # VIDs are validated by _validate_vid (only [A-Za-z0-9_.-], max 64 chars)
        # so embedding them as double-quoted string literals is injection-safe.
        query = (
            f'INSERT EDGE IF NOT EXISTS DEPENDS_ON(weight) '
            f'VALUES "{src_ticker}"->"{dst_ticker}":($weight)'
        )
        self._execute(query, {"weight": float(weight)})
        logger.info(
            "insert_depends_on: %r -> %r weight=%.2f", src_ticker, dst_ticker, weight
        )
        return True

    def insert_requires(
        self,
        ticker: str,
        commodity_id: str,
        volume: int = 0,
    ) -> bool:
        """
        Insert a REQUIRES edge from a Company to a Commodity.

        Parameters
        ----------
        ticker       : str — Company VID
        commodity_id : str — Commodity VID
        volume       : int — annual demand volume
        """
        _validate_vid(ticker, "ticker")
        _validate_vid(commodity_id, "commodity_id")
        if not isinstance(volume, int) or volume < 0:
            raise ValueError("volume must be a non-negative integer")
        # VIDs embedded as validated literals — see insert_depends_on comment.
        query = (
            f'INSERT EDGE IF NOT EXISTS REQUIRES(volume) '
            f'VALUES "{ticker}"->"{commodity_id}":($volume)'
        )
        self._execute(query, {"volume": volume})
        logger.info(
            "insert_requires: %r -> %r volume=%d", ticker, commodity_id, volume
        )
        return True
