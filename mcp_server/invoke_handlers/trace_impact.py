"""
Trace Impact Tool Handler
MCP tool: trace_impact

Exposes SecureGraphClient.trace_impact() — the Phase 2 causal reasoning
engine — as an MCP-callable tool.

Security model (inherited from Phase 2):
  • No raw nGQL is generated here.
  • All graph access is delegated to SecureGraphClient, which uses
    parameterised execute_parameter() calls and VID injection guards.
  • The handler authenticates as mcp_agent (USER role) — it cannot
    DROP spaces, ALTER schema, or create users.
"""
import re
import time
from typing import Optional

from mcp_server.utils.logging import get_logger
from mcp_server.schemas import ToolResponse
from mcp_server.config import get_settings
from finance_mcp.graph.client import SecureGraphClient

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# VID-compatible ticker pattern — mirrors _VID_RE in SecureGraphClient.
# Must be kept in sync with client.py if that pattern ever changes.
_TICKER_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')

_DEFAULT_MAX_HOPS: int = 2
_MAX_HOPS_LIMIT: int = 5


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

async def handle_trace_impact(
    ticker: str,
    max_hops: int = _DEFAULT_MAX_HOPS,
    agent_id: Optional[str] = None,
) -> ToolResponse:
    """
    Handle trace_impact tool invocation.

    Given a company ticker that has suffered an event (e.g. a supply
    disruption), traverse the supply-chain graph to find every company
    that depends on it within ``max_hops`` hops of DEPENDS_ON edges.

    Flow
    ----
    1. Validate ``ticker`` — must be non-empty, VID-safe characters only.
    2. Validate ``max_hops`` — must be an integer in [1, 5].
    3. Open a SecureGraphClient connection (reads host/port from settings).
    4. Call ``client.trace_impact(target_ticker, max_hops)``.
    5. Return a structured ToolResponse containing the impacted companies.

    Parameters
    ----------
    ticker : str
        Stock ticker / VID of the company that experienced the shock,
        e.g. ``"TSMC"``.  Converted to uppercase before use.
    max_hops : int
        Maximum traversal depth along DEPENDS_ON edges.
        Defaults to 2, capped at 5.
    agent_id : str | None
        Optional identifier of the calling agent (for logging only).

    Returns
    -------
    ToolResponse
        On success:
            success=True
            data={
                "ticker": str,
                "max_hops": int,
                "impacted_companies": [
                    {"ticker": str, "name": str, "sector": str},
                    ...
                ],
                "impacted_count": int
            }
        On failure:
            success=False
            error=<human-readable description>
    """
    start_time = time.time()
    settings = get_settings()

    # -----------------------------------------------------------------------
    # Step 1 — Validate ticker
    # -----------------------------------------------------------------------
    if not isinstance(ticker, str) or not ticker.strip():
        return ToolResponse(
            success=False,
            error="'ticker' must be a non-empty string.",
        )

    ticker = ticker.strip().upper()

    if not _TICKER_RE.match(ticker):
        return ToolResponse(
            success=False,
            error=(
                f"Invalid ticker format: {ticker!r}. "
                "Allowed characters: A–Z, 0–9, underscore, dot, hyphen. "
                "Length: 1–64 characters."
            ),
        )

    # -----------------------------------------------------------------------
    # Step 2 — Validate max_hops
    # -----------------------------------------------------------------------
    # Reject booleans explicitly (bool is a subclass of int in Python).
    if isinstance(max_hops, bool) or not isinstance(max_hops, int):
        return ToolResponse(
            success=False,
            error="'max_hops' must be an integer.",
        )

    if not (1 <= max_hops <= _MAX_HOPS_LIMIT):
        return ToolResponse(
            success=False,
            error=f"'max_hops' must be between 1 and {_MAX_HOPS_LIMIT}, got {max_hops}.",
        )

    logger.info(
        "trace_impact_request",
        ticker=ticker,
        max_hops=max_hops,
        agent_id=agent_id,
    )

    # -----------------------------------------------------------------------
    # Step 3 — Call graph reasoning engine
    # -----------------------------------------------------------------------
    try:
        with SecureGraphClient(
            host=settings.nebula_host,
            port=settings.nebula_port,
        ) as client:
            impacted = client.trace_impact(
                target_ticker=ticker,
                max_hops=max_hops,
            )

    except ValueError as exc:
        # Validation errors from SecureGraphClient (e.g. VID regex failure)
        logger.warning("trace_impact_validation_error", error=str(exc))
        return ToolResponse(success=False, error=str(exc))

    except RuntimeError as exc:
        # Graph engine execution errors (connection, query failure, etc.)
        logger.error("trace_impact_graph_error", error=str(exc))
        return ToolResponse(
            success=False,
            error=f"Graph query failed: {exc}",
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("trace_impact_unexpected_error", error=str(exc))
        return ToolResponse(
            success=False,
            error=f"Unexpected error: {exc}",
        )

    # -----------------------------------------------------------------------
    # Step 4 — Format and return response
    # -----------------------------------------------------------------------
    latency_ms = (time.time() - start_time) * 1000

    logger.info(
        "trace_impact_response",
        ticker=ticker,
        max_hops=max_hops,
        impacted_count=len(impacted),
        latency_ms=latency_ms,
    )

    return ToolResponse(
        success=True,
        data={
            "ticker": ticker,
            "max_hops": max_hops,
            "impacted_companies": impacted,
            "impacted_count": len(impacted),
        },
        latency_ms=latency_ms,
    )
