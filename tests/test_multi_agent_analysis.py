"""Tests for Phase 4 multi-agent reasoning integration."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from mcp_server.schemas import ToolResponse
from mcp_server.server import app
from mcp_server.invoke_handlers.multi_agent_analysis import handle_multi_agent_analysis

API_KEY = "dev_key_change_in_production"


@pytest.fixture
def client():
    return TestClient(app, headers={"X-API-Key": API_KEY})


@pytest.mark.asyncio
async def test_multi_agent_handler_rejects_empty_query():
    response = await handle_multi_agent_analysis(query="   ")
    assert response.success is False
    assert "query" in (response.error or "")


@pytest.mark.asyncio
async def test_multi_agent_handler_success_payload():
    payload = {
        "query": "What happens if TSMC shuts down?",
        "ticker": "TSMC",
        "bull_case": {"reasoning": "bull", "signals": ["s1"], "confidence": 0.6},
        "bear_case": {"reasoning": "bear", "signals": ["s2"], "confidence": 0.7},
        "final_verdict": "Leaning bearish",
        "confidence": 0.68,
        "summary": "Balanced result",
        "key_drivers": ["s1", "s2"],
    }

    with patch(
        "mcp_server.invoke_handlers.multi_agent_analysis.run_multi_agent_analysis",
        new=AsyncMock(return_value=payload),
    ):
        response = await handle_multi_agent_analysis(
            query="What happens if TSMC shuts down?",
            ticker="TSMC",
            agent_id="test",
        )

    assert response.success is True
    assert response.data is not None
    assert response.data.get("final_verdict") == "Leaning bearish"


def test_invoke_dispatches_multi_agent_tool(client: TestClient):
    fake = ToolResponse(
        success=True,
        data={
            "query": "Impact of oil supply disruption",
            "bull_case": {"reasoning": "bull", "signals": [], "confidence": 0.55},
            "bear_case": {"reasoning": "bear", "signals": [], "confidence": 0.73},
            "final_verdict": "Leaning bearish",
            "confidence": 0.73,
            "summary": "Risk dominates",
            "key_drivers": ["Energy inflation"],
        },
    )

    with patch("mcp_server.server.handle_multi_agent_analysis", new=AsyncMock(return_value=fake)):
        resp = client.post(
            "/invoke",
            json={
                "tool_name": "multi_agent_analysis",
                "arguments": {"query": "Impact of oil supply disruption", "ticker": "XOM"},
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["final_verdict"] == "Leaning bearish"


@pytest.mark.parametrize(
    "query,ticker",
    [
        ("What happens if oil supply is disrupted due to Middle East conflict?", "XOM"),
        ("Is NVIDIA bullish if semiconductor demand increases?", "NVDA"),
        ("Impact of interest rate hike on banking stocks", None),
        ("What happens if TSMC shuts down?", "TSMC"),
    ],
)
def test_required_phase4_queries_are_structured(client: TestClient, query: str, ticker: str | None):
    fake = ToolResponse(
        success=True,
        data={
            "query": query,
            "ticker": ticker,
            "bull_case": {"reasoning": "bull", "signals": ["upside"], "confidence": 0.62},
            "bear_case": {"reasoning": "bear", "signals": ["downside"], "confidence": 0.71},
            "final_verdict": "Leaning bearish",
            "confidence": 0.71,
            "summary": "Risk dominates",
            "key_drivers": ["upside", "downside"],
        },
    )

    with patch("mcp_server.server.handle_multi_agent_analysis", new=AsyncMock(return_value=fake)) as mock_handler:
        payload = {
            "tool_name": "multi_agent_analysis",
            "arguments": {"query": query},
        }
        if ticker:
            payload["arguments"]["ticker"] = ticker

        resp = client.post("/invoke", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "bull_case" in body["data"]
    assert "bear_case" in body["data"]
    assert "final_verdict" in body["data"]
    assert "confidence" in body["data"]
    assert mock_handler.await_count == 1
