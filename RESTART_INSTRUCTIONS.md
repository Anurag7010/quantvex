# How to Restart and Test

## 1. Stop and Restart the MCP Server

```bash
# Stop the existing Docker containers
docker-compose -f infra/docker-compose.yml down

# Restart with the updated code
docker-compose -f infra/docker-compose.yml up -d --build
```

This will rebuild the MCP server image with the new formatter integration.

## 2. Verify the Server Started

```bash
# Check health
curl -s http://localhost:8000/health | jq .

# Should show: {"status": "healthy"}
```

## 3. Test the Chat Endpoint

```bash
# Test a financial quote query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev_key_change_in_production" \
  -d '{"message": "What is the current price of Apple stock?"}'
```

**Expected response**: Clean, formatted financial report (no markdown, no asterisks)

## 4. Test in the Frontend

1. Open http://localhost:3000 in your browser
2. Switch to the "Agent" tab
3. Ask a market question:
   - "What's the price of Tesla?"
   - "Compare AAPL and MSFT today"
   - "How much is Bitcoin worth?"

**Expected**: Professional financial report renders in the chat bubble

## 5. Integration Verification

Run the test script:

```bash
python3 test_mcp_formatter_integration.py
```

Should show: `✅ Integration test PASSED`

## What Changed?

- ✅ Updated `mcp_server/chat_agent.py` to import the formatter
- ✅ Added `_normalize_quote()` helper function
- ✅ Modified `_execute_tool()` for `get_stock_quote` to use the formatter
- ✅ All financial responses now go through `format_financial_report()`

## Result

When a user asks for market data in the frontend chat:

1. Request → MCP Server `/chat` endpoint
2. Gemini calls `get_stock_quote` tool
3. Tool returns raw MCP data
4. `_normalize_quote()` converts to formatter structure
5. `format_financial_report()` produces clean output
6. Frontend receives structured text (no markdown)
7. Renders perfectly in chat bubble with `whitespace-pre-wrap`

---

**Note**: Both the CLI (`examples/gemini_agent.py`) and the frontend (via MCP server) now use the same professional formatter. You're all set!
