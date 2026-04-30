from __future__ import annotations

from typing import Any

from finance_mcp.graph.client import SecureGraphClient


async def trace_impact(target_vid: str, hops: int = 2) -> dict[str, Any]:
    """Trace downstream graph impact without depending on MCP invoke handlers."""
    normalized = target_vid.strip().upper()
    with SecureGraphClient() as client:
        impacted = client.trace_impact(normalized, hops)
    return {
        "success": True,
        "data": {
            "ticker": normalized,
            "max_hops": hops,
            "impacted_companies": impacted,
            "impacted_count": len(impacted),
        },
    }
