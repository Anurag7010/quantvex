"""Formatting helpers for Finance MCP GPT agent.

Transforms raw quote payloads into professional, structured financial reports.
"""
import os
from typing import Any, Dict, List, Optional

INR_SYMBOL = "₹"

WEB_MODE = os.getenv("WEB_MODE", "1").lower() in ("1", "true", "yes", "on")
USE_BOLD = os.getenv("ENABLE_BOLD_FORMATTING", "0" if WEB_MODE else "1").lower() not in ("0", "false", "no", "off")
BOLD = "\033[1m"
RESET = "\033[0m"


def _bold(text: str) -> str:
    if not USE_BOLD:
        return text
    return f"{BOLD}{text}{RESET}"


def _format_currency(value: Optional[float]) -> str:
    """Format a numeric value as INR currency."""
    if value is None:
        return "N/A"
    return f"{INR_SYMBOL}{value:,.2f}"


def _format_signed_currency(value: Optional[float]) -> str:
    """Format currency with an explicit sign for deltas."""
    if value is None:
        return "N/A"
    return f"{INR_SYMBOL}{value:+,.2f}"


def _format_change(change: Optional[float], pct: Optional[float]) -> str:
    if change is None:
        return "N/A"
    pct_str = f"{pct:+.2f}%" if pct is not None else "N/A"
    return f"{_format_signed_currency(change)} ({pct_str})"


def _format_volume(volume: Optional[float]) -> str:
    if volume is None:
        return "N/A"
    return f"{volume:,.0f}"


def _market_summary(symbol: str, change: Optional[float], pct: Optional[float], direction_hint: str) -> str:
    if change is None or pct is None:
        return f"{symbol} pricing updated with latest available market data."
    if change > 0:
        return f"{symbol} is trading above the previous close, reflecting positive intraday momentum."
    if change < 0:
        return f"{symbol} is trading below the previous close, reflecting soft intraday sentiment."
    return direction_hint or f"{symbol} is holding near the previous close."


def _analysis_points(quote: Dict[str, Any]) -> List[str]:
    price = quote.get("price")
    prev = quote.get("previous_close")
    high = quote.get("high")
    low = quote.get("low")
    volume = quote.get("volume")
    change = quote.get("change")
    pct = quote.get("change_pct")

    points: List[str] = []

    if change is not None and pct is not None:
        if change > 0:
            points.append("Price is trading above the previous close.")
        elif change < 0:
            points.append("Price is trading below the previous close.")
        else:
            points.append("Price is flat versus the previous close.")
    elif price is not None:
        points.append("Latest price captured; prior close unavailable.")

    if high is not None and low is not None and price is not None:
        range_span = high - low
        if range_span:
            distance_from_low = price - low
            percentile = distance_from_low / range_span
            if percentile >= 0.8:
                points.append("Price is trading near the intraday high.")
            elif percentile <= 0.2:
                points.append("Price is trading near the intraday low.")
            else:
                points.append("Price is mid-range within today's trading band.")
    elif high is not None or low is not None:
        points.append("Partial intraday range available; awaiting full range data.")

    if volume is not None:
        points.append("Reported volume updated." if volume else "Volume reported as zero; verify market status.")
    else:
        points.append("Volume data not provided.")

    return points[:3]


def _single_asset_report(quote: Dict[str, Any], errors: List[str]) -> str:
    symbol = quote.get("symbol", "N/A")
    change = quote.get("change")
    pct = quote.get("change_pct")
    data_source = quote.get("data_source", "Real-time market data via MCP financial server")
    cache_state = quote.get("cache_state", "fresh")

    lines: List[str] = []
    lines.append("### MARKET SUMMARY\n")
    lines.append(_market_summary(symbol, change, pct, quote.get("summary_hint", "")) + "\n")

    lines.append("### PRICE INFORMATION\n")
    lines.append(f"- **Symbol:** {symbol}")
    lines.append(f"- **Current Price:** {_format_currency(quote.get('inr_price'))}")
    lines.append(f"- **Previous Close:** {_format_currency(quote.get('inr_previous_close'))}")
    lines.append(f"- **Change:** {_format_change(change, pct)}\n")

    lines.append("### TRADING RANGE\n")
    lines.append(f"- **Open:** {_format_currency(quote.get('inr_open'))}")
    lines.append(f"- **Day High:** {_format_currency(quote.get('inr_high'))}")
    lines.append(f"- **Day Low:** {_format_currency(quote.get('inr_low'))}\n")

    lines.append("### MARKET ACTIVITY\n")
    lines.append(f"- **Volume:** {_format_volume(quote.get('volume'))}\n")

    lines.append("### AI ANALYSIS\n")
    for point in _analysis_points(quote):
        lines.append(f"- {point}")
    lines.append("\n")

    lines.append("### DATA SOURCE\n")
    lines.append(f"_{data_source}_ ({cache_state})")

    if errors:
        lines.append("### DATA GAPS\n")
        for err in errors:
            lines.append(f"- {err}")

    return "\n".join(lines).strip()


def _comparison_report(quotes: List[Dict[str, Any]], errors: List[str]) -> str:
    lines: List[str] = []
    lines.append("### MARKET COMPARISON\n")
    lines.append("| Asset | Price | Change | Volume |")
    lines.append("|---|---|---|---|")

    for quote in quotes:
        symbol = quote.get("symbol", "N/A")
        price = _format_currency(quote.get("inr_price"))
        change_str = _format_change(quote.get("change"), quote.get("change_pct"))
        volume = quote.get("volume")
        volume_str = f"{volume / 1e6:.0f}M" if volume and volume >= 1e6 else _format_volume(volume)
        lines.append(f"| **{symbol}** | {price} | {change_str} | {volume_str} |")

    lines.append("\n### AI INSIGHTS\n")

    sorted_quotes = [q for q in quotes if q.get("change_pct") is not None]
    sorted_quotes.sort(key=lambda q: q.get("change_pct", 0), reverse=True)

    if sorted_quotes:
        leader = sorted_quotes[0]
        lines.append(
            f"- **{leader.get('symbol', 'Asset')}** shows the strongest move at **{_format_change(leader.get('change'), leader.get('change_pct'))}**."
        )
        if len(sorted_quotes) > 1:
            laggard = sorted_quotes[-1]
            lines.append(
                f"- **{laggard.get('symbol', 'Asset')}** is lagging peers at **{_format_change(laggard.get('change'), laggard.get('change_pct'))}**."
            )
    else:
        lines.append("- Change metrics are not available for comparison.")

    lines.append("- Data sourced from MCP financial server.")

    if errors:
        lines.append("\n### ERRORS\n")
        for err in errors:
            lines.append(f"- {err}")

    return "\n".join(lines).strip()


def format_financial_report(data: Dict[str, Any]) -> str:
    """Transform normalized quote data into a professional report string."""
    quotes: List[Dict[str, Any]] = data.get("quotes", []) if isinstance(data, dict) else []
    if not quotes:
        return "DATA UNAVAILABLE\nNo market data was returned."

    success_quotes = [q for q in quotes if not q.get("error")]
    errors = [f"{q.get('symbol', 'Unknown')}: {q.get('error')}" for q in quotes if q.get("error")]

    if not success_quotes:
        return "DATA UNAVAILABLE\n" + "\n".join(errors)

    if len(success_quotes) == 1:
        return _single_asset_report(success_quotes[0], errors)

    return _comparison_report(success_quotes, errors)
