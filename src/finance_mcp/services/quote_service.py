from __future__ import annotations

from typing import Any

from connectors.alpha_vantage import get_alpha_vantage_connector
from connectors.finnhub import get_finnhub_connector


async def get_quote(symbol: str) -> dict[str, Any]:
    """Fetch a latest quote without depending on MCP invoke handlers."""
    normalized = symbol.strip().upper()
    try:
        finnhub = get_finnhub_connector()
        quote = await finnhub.get_quote(normalized)
        if quote and quote.price > 0:
            return {"success": True, "data": quote.model_dump()}
    except Exception as exc:  # noqa: BLE001
        finnhub_error = str(exc)
    else:
        finnhub_error = ""

    try:
        alpha_vantage = get_alpha_vantage_connector()
        quote = await alpha_vantage.get_quote(normalized)
        if quote and quote.price > 0:
            return {"success": True, "data": quote.model_dump()}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"{finnhub_error}; {exc}".strip("; ")}

    return {"success": False, "error": f"No quote available for {normalized}"}
