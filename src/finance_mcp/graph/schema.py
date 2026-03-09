"""
Phase 2 — NebulaGraph Schema Initialisation and RBAC Bootstrap

Responsibilities:
• Create the supply_chain graph space
• Define node tags (Company, Commodity, Event)
• Define edge types (DEPENDS_ON, REQUIRES, IMPACTS)
• Create property indexes for performance
• Create the restricted runtime user (mcp_agent)

SECURITY MODEL
--------------
The root account is used ONLY here during bootstrap.
The MCP server must NEVER call these functions at request time;
they are one-shot setup utilities.
After first run the application uses mcp_agent exclusively:
  - mcp_agent has USER-level access on supply_chain
  - mcp_agent cannot DROP spaces or ALTER schema
  - root credentials are never available to LLM code paths
"""

import time
import logging
from typing import Optional

from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection defaults — override via environment / explicit args as needed
# ---------------------------------------------------------------------------
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9669
ROOT_USER = "root"
ROOT_PASSWORD = "nebula"
AGENT_USER = "mcp_agent"
AGENT_PASSWORD = "mcp_agent_secret"
GRAPH_SPACE = "supply_chain"


def _create_pool(host: str, port: int, user: str, password: str) -> ConnectionPool:
    """Create and authenticate a NebulaGraph connection pool."""
    cfg = Config()
    cfg.max_connection_pool_size = 2
    pool = ConnectionPool()
    ok = pool.init([(host, port)], cfg)
    if not ok:
        raise RuntimeError(f"NebulaGraph connection pool init failed ({host}:{port})")
    return pool


def _execute(session, statement: str, description: str = "") -> None:
    """Execute a nGQL statement and raise on error."""
    result = session.execute(statement)
    if not result.is_succeeded():
        error_msg = result.error_msg()
        # "Existed" is not a real error for idempotent CREATE statements
        if "Existed" in error_msg or "existed" in error_msg:
            logger.info("already_exists: %s — %s", description, error_msg)
        else:
            raise RuntimeError(
                f"Schema statement failed [{description}]: {error_msg}\n"
                f"Statement: {statement}"
            )
    else:
        logger.info("ok: %s", description or statement[:80])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_STORAGE_HOST = "finance-mcp-nebula-storaged"
DEFAULT_STORAGE_PORT = 9779


def _ensure_storaged_online(
    session,
    storage_host: str = DEFAULT_STORAGE_HOST,
    storage_port: int = DEFAULT_STORAGE_PORT,
    timeout_sec: int = 60,
) -> None:
    """Register storage node if missing and poll until it is ONLINE."""
    # Register (idempotent — existing entries return OK)
    reg = session.execute(f'ADD HOSTS "{storage_host}":{storage_port}')
    if not reg.is_succeeded():
        msg = reg.error_msg()
        if "Existed" not in msg:
            raise RuntimeError(f"ADD HOSTS failed: {msg}")

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        result = session.execute("SHOW HOSTS")
        if result.is_succeeded():
            rows = result.rows()
            if rows:
                status = rows[0].values[2].get_sVal().decode()
                if status == "ONLINE":
                    logger.info("storaged is ONLINE")
                    return
        logger.info("Waiting for storaged to come ONLINE…")
        time.sleep(5)

    raise RuntimeError("Timed out waiting for storaged to become ONLINE")


# ---------------------------------------------------------------------------
# STEP 3 — Schema initialisation
# ---------------------------------------------------------------------------

def initialize_graph_schema(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    root_password: str = ROOT_PASSWORD,
    storage_host: str = DEFAULT_STORAGE_HOST,
    storage_port: int = DEFAULT_STORAGE_PORT,
) -> None:
    """
    Connect as root, create the supply_chain space, define all tags,
    edge types, and indexes.

    Safe to call multiple times — all statements are idempotent.
    """
    pool = _create_pool(host, port, ROOT_USER, root_password)
    session = pool.get_session(ROOT_USER, root_password)

    try:
        # ----------------------------------------------------------------
        # 0. Register storaged if not already present and wait until ONLINE
        # ----------------------------------------------------------------
        _ensure_storaged_online(session, storage_host, storage_port)

        # ----------------------------------------------------------------
        # 1. Create graph space
        # ----------------------------------------------------------------
        _execute(
            session,
            "CREATE SPACE IF NOT EXISTS supply_chain (vid_type = FIXED_STRING(64))",
            "CREATE SPACE supply_chain",
        )

        # NebulaGraph requires a short pause after space creation before
        # DDL statements inside that space are valid.
        logger.info("Waiting for space to become active…")
        time.sleep(10)

        _execute(session, f"USE {GRAPH_SPACE}", "USE supply_chain")

        # ----------------------------------------------------------------
        # 2. Node tags
        # ----------------------------------------------------------------
        _execute(
            session,
            "CREATE TAG IF NOT EXISTS Company("
            "  ticker string NOT NULL,"
            "  name   string NOT NULL,"
            "  sector string DEFAULT ''"
            ")",
            "CREATE TAG Company",
        )

        _execute(
            session,
            "CREATE TAG IF NOT EXISTS Commodity("
            "  name     string NOT NULL,"
            "  category string DEFAULT ''"
            ")",
            "CREATE TAG Commodity",
        )

        _execute(
            session,
            "CREATE TAG IF NOT EXISTS Event("
            "  description string NOT NULL,"
            "  severity    int    DEFAULT 0"
            ")",
            "CREATE TAG Event",
        )

        # ----------------------------------------------------------------
        # 3. Edge types
        # ----------------------------------------------------------------
        _execute(
            session,
            "CREATE EDGE IF NOT EXISTS DEPENDS_ON(weight double DEFAULT 1.0)",
            "CREATE EDGE DEPENDS_ON",
        )

        _execute(
            session,
            "CREATE EDGE IF NOT EXISTS REQUIRES(volume int DEFAULT 0)",
            "CREATE EDGE REQUIRES",
        )

        _execute(
            session,
            "CREATE EDGE IF NOT EXISTS IMPACTS(impact_time datetime DEFAULT datetime())",
            "CREATE EDGE IMPACTS",
        )

        # ----------------------------------------------------------------
        # 4. Indexes (enable LOOKUP and filter-pushdown)
        # ----------------------------------------------------------------
        # Brief pause — tags/edges must be committed before index creation
        time.sleep(3)

        _execute(
            session,
            "CREATE TAG INDEX IF NOT EXISTS idx_company_ticker ON Company(ticker(64))",
            "CREATE INDEX idx_company_ticker",
        )

        _execute(
            session,
            "CREATE TAG INDEX IF NOT EXISTS idx_commodity_name ON Commodity(name(64))",
            "CREATE INDEX idx_commodity_name",
        )

        _execute(
            session,
            "CREATE EDGE INDEX IF NOT EXISTS idx_impacts_time ON IMPACTS(impact_time)",
            "CREATE INDEX idx_impacts_time",
        )

        _execute(
            session,
            "CREATE TAG INDEX IF NOT EXISTS idx_company_sector ON Company(sector(64))",
            "CREATE INDEX idx_company_sector",
        )

        _execute(
            session,
            "CREATE TAG INDEX IF NOT EXISTS idx_event_severity ON Event(severity)",
            "CREATE INDEX idx_event_severity",
        )

        logger.info("Graph schema initialisation complete.")

    finally:
        session.release()
        pool.close()


# ---------------------------------------------------------------------------
# STEP 4 — RBAC: create restricted runtime user
# ---------------------------------------------------------------------------

def create_agent_user(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    root_password: str = ROOT_PASSWORD,
    agent_password: str = AGENT_PASSWORD,
) -> None:
    """
    Create the mcp_agent user and grant it USER-level access on supply_chain.

    WHY root must never be used by the MCP server
    ---------------------------------------------
    root has unrestricted DDL power:
      - DROP SPACE supply_chain  — destroys all data instantly
      - DROP USER / CREATE USER  — can lock out the system
      - ALTER TAG / EDGE         — corrupts schema silently
    If an LLM ever manipulates a prompt into the query path and root is
    the session user, the entire graph can be wiped in a single statement.

    mcp_agent is scoped to USER-level ONLY:
      - Can INSERT / UPDATE / DELETE vertices and edges
      - Can execute traversal queries (GO, FETCH, MATCH, LOOKUP)
      - Cannot DROP spaces, tags, or edge types
      - Cannot ALTER schema
      - Cannot CREATE or DROP other users

    This limits the blast radius of a prompt-injection attack to data
    mutations only — NOT structural destruction.
    """
    pool = _create_pool(host, port, ROOT_USER, root_password)
    session = pool.get_session(ROOT_USER, root_password)

    try:
        _execute(
            session,
            f"CREATE USER IF NOT EXISTS {AGENT_USER} WITH PASSWORD '{agent_password}'",
            f"CREATE USER {AGENT_USER}",
        )

        _execute(
            session,
            f"GRANT ROLE USER ON {GRAPH_SPACE} TO {AGENT_USER}",
            f"GRANT USER on {GRAPH_SPACE} to {AGENT_USER}",
        )

        logger.info(
            "RBAC bootstrap complete: user '%s' granted USER role on '%s'.",
            AGENT_USER,
            GRAPH_SPACE,
        )

    finally:
        session.release()
        pool.close()


# ---------------------------------------------------------------------------
# Convenience: run both in sequence
# ---------------------------------------------------------------------------

def bootstrap(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    root_password: str = ROOT_PASSWORD,
    agent_password: str = AGENT_PASSWORD,
    storage_host: str = DEFAULT_STORAGE_HOST,
    storage_port: int = DEFAULT_STORAGE_PORT,
) -> None:
    """Run full Phase 2 bootstrap: schema + RBAC."""
    logger.info("Starting Phase 2 graph bootstrap…")
    initialize_graph_schema(
        host=host,
        port=port,
        root_password=root_password,
        storage_host=storage_host,
        storage_port=storage_port,
    )
    create_agent_user(
        host=host,
        port=port,
        root_password=root_password,
        agent_password=agent_password,
    )
    logger.info("Phase 2 bootstrap finished.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    bootstrap()
