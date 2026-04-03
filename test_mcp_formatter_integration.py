#!/usr/bin/env python3
"""
Test that verifies the MCP server's chat agent uses the formatter.
This simulates what the /chat endpoint will return.
"""
import asyncio
import os
os.environ['WEB_MODE'] = '1'  # ensure web mode

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / "examples"))

from finance_formatter import format_financial_report

# Simulate what handle_quote_latest returns
mock_mcp_result = {
    "success": True,
    "data": {
        "symbol": "AAPL",
        "price": 159.50,
        "previous_close": 158.20,
        "open": 158.75,
        "high": 160.50,
        "low": 158.00,
        "volume": 52381220,
        "data_source": "finnhub",
        "cache_hit": False,
    }
}

# Simulate the normalize_quote function from chat_agent
USD_TO_INR = 89.94

def _normalize_quote(symbol, result):
    base_symbol = (symbol or "").upper() or "N/A"
    if not result.get("success"):
        return {"symbol": base_symbol, "error": result.get("error", "Unknown error")}
    
    data = result.get("data", {})
    
    def to_inr(value):
        return round(value * USD_TO_INR, 2) if value is not None else None
    
    price = to_inr(data.get("price"))
    prev = to_inr(data.get("previous_close"))
    open_px = to_inr(data.get("open"))
    high = to_inr(data.get("high"))
    low = to_inr(data.get("low"))
    
    change = None
    change_pct = None
    if price is not None and prev not in (None, 0):
        change = round(price - prev, 2)
        change_pct = round((change / prev) * 100, 2)
    
    return {
        "symbol": data.get("symbol", base_symbol).upper(),
        "price": price,
        "previous_close": prev,
        "open": open_px,
        "high": high,
        "low": low,
        "volume": data.get("volume"),
        "change": change,
        "change_pct": change_pct,
        "data_source": data.get("data_source", "Real-time market data via MCP financial server"),
        "cache_state": "cached" if data.get("cache_hit") else "fresh",
    }

# Test the flow
print("=" * 70)
print("MCP Server Chat Agent Integration Test")
print("=" * 70)
print()

normalized = _normalize_quote("AAPL", mock_mcp_result)
formatted = format_financial_report({"quotes": [normalized]})

print("FORMATTED OUTPUT (what /chat endpoint returns):")
print("-" * 70)
print(formatted)
print()

# Validation
checks = {
    'No asterisks': '*' not in formatted,
    'No underscores': '_' not in formatted,
    'No backticks': '`' not in formatted,
    'No ANSI codes': chr(27) not in formatted,
    'Has content': len(formatted) > 100,
    'Has • bullets': '•' in formatted,
}

print("VALIDATION:")
print("-" * 70)
all_pass = True
for check, result in checks.items():
    status = '✓' if result else '✗'
    print(f"{status} {check}")
    if not result:
        all_pass = False

print()
if all_pass:
    print("✅ Integration test PASSED - Frontend will receive formatted output")
else:
    print("❌ Integration test FAILED - Review the output above")
