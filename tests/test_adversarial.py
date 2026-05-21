"""
Phase 1.4 — Adversarial Debate Architecture + SQLite Verdict History
Tests cover:
  - Sequential debate flow (bull → bear attack → bull rebuttal → judge)
  - weakest_claim propagation through AgentOutput.metadata
  - Bear agent targeted attack on bull's weakest claim
  - Judge receiving full transcript
  - SQLite verdict recording (db.py, tracker.py)
  - Accuracy statistics (accuracy.py)
  - /verdicts/accuracy and /verdicts/history endpoints
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from finance_mcp.reasoning.schemas import AgentInput, AgentOutput, JudgeVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bull_output(
    confidence: float = 0.65,
    signals: list[str] | None = None,
    weakest_claim: str = "test claim",
) -> AgentOutput:
    return AgentOutput(
        stance="bull",
        reasoning="Bull thesis: " + " ".join(signals or ["sig1"]),
        signals=signals or ["sig1"],
        confidence=confidence,
        metadata={"weakest_claim": weakest_claim},
    )


def _make_bear_output(
    confidence: float = 0.55,
    attack_target: str | None = "test claim",
) -> AgentOutput:
    return AgentOutput(
        stance="bear",
        reasoning="Bear thesis.",
        signals=["bear sig"],
        confidence=confidence,
        metadata={"attack_target": attack_target},
    )


# ---------------------------------------------------------------------------
# TestAgentOutputMetadata
# ---------------------------------------------------------------------------

class TestAgentOutputMetadata:
    def test_metadata_field_exists(self):
        out = AgentOutput(stance="bull", reasoning="r", confidence=0.5)
        assert isinstance(out.metadata, dict)

    def test_metadata_defaults_empty(self):
        out = AgentOutput(stance="bull", reasoning="r", confidence=0.5)
        assert out.metadata == {}

    def test_metadata_stores_weakest_claim(self):
        out = AgentOutput(
            stance="bull", reasoning="r", confidence=0.5,
            metadata={"weakest_claim": "claim here"},
        )
        assert out.metadata["weakest_claim"] == "claim here"

    def test_metadata_stores_attack_target(self):
        out = AgentOutput(
            stance="bear", reasoning="r", confidence=0.5,
            metadata={"attack_target": "some claim"},
        )
        assert out.metadata["attack_target"] == "some claim"


# ---------------------------------------------------------------------------
# TestBullAgentWeakestClaim
# ---------------------------------------------------------------------------

class TestBullAgentWeakestClaim:
    """Unit tests for _identify_weakest_claim logic."""

    def test_no_signals_returns_generic_claim(self):
        from finance_mcp.reasoning.bull_agent import _identify_weakest_claim
        result = _identify_weakest_claim([], 0.35)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_low_confidence_returns_weak_support_claim(self):
        from finance_mcp.reasoning.bull_agent import _identify_weakest_claim
        result = _identify_weakest_claim(["sig"], 0.4)
        assert isinstance(result, str)

    def test_moderate_confidence_returns_last_signal(self):
        from finance_mcp.reasoning.bull_agent import _identify_weakest_claim
        signals = ["strong sig", "weak sig"]
        result = _identify_weakest_claim(signals, 0.6)
        assert result == "weak sig"

    def test_selective_signal_flagged_at_high_confidence(self):
        from finance_mcp.reasoning.bull_agent import _identify_weakest_claim
        signals = ["Firm revenue signal.", "Cascade creates selective upside for advantaged firms."]
        result = _identify_weakest_claim(signals, 0.8)
        assert "selective" in result.lower() or "advantaged" in result.lower()

    @pytest.mark.asyncio
    async def test_run_bull_agent_sets_weakest_claim_in_metadata(self):
        from finance_mcp.reasoning.bull_agent import run_bull_agent
        agent_input = AgentInput(query="NVDA supply chain risk", ticker="NVDA")
        with (
            patch("finance_mcp.reasoning.bull_agent.get_quote", new_callable=AsyncMock) as mock_q,
            patch("finance_mcp.reasoning.bull_agent.trace_impact", new_callable=AsyncMock) as mock_ti,
        ):
            mock_q.return_value = {"success": False}
            mock_ti.return_value = {"success": False}
            result = await run_bull_agent(agent_input)
        assert "weakest_claim" in result.metadata
        assert isinstance(result.metadata["weakest_claim"], str)
        assert len(result.metadata["weakest_claim"]) > 0


# ---------------------------------------------------------------------------
# TestBearAgentTargetedAttack
# ---------------------------------------------------------------------------

class TestBearAgentTargetedAttack:
    @pytest.mark.asyncio
    async def test_attack_target_in_metadata_when_bull_thesis_provided(self):
        from finance_mcp.reasoning.bear_agent import run_bear_agent
        bull = _make_bull_output(weakest_claim="Strategic supply importance is overstated.")
        agent_input = AgentInput(query="NVDA risk", ticker="NVDA")
        with (
            patch("finance_mcp.reasoning.bear_agent.get_quote", new_callable=AsyncMock) as mock_q,
            patch("finance_mcp.reasoning.bear_agent.trace_impact", new_callable=AsyncMock) as mock_ti,
        ):
            mock_q.return_value = {"success": False}
            mock_ti.return_value = {"success": False}
            result = await run_bear_agent(agent_input, bull_thesis=bull)
        assert result.metadata.get("attack_target") == "Strategic supply importance is overstated."

    @pytest.mark.asyncio
    async def test_no_attack_target_without_bull_thesis(self):
        from finance_mcp.reasoning.bear_agent import run_bear_agent
        agent_input = AgentInput(query="market risk", ticker=None)
        with (
            patch("finance_mcp.reasoning.bear_agent.get_quote", new_callable=AsyncMock) as mock_q,
            patch("finance_mcp.reasoning.bear_agent.trace_impact", new_callable=AsyncMock) as mock_ti,
        ):
            mock_q.return_value = {"success": False}
            mock_ti.return_value = {"success": False}
            result = await run_bear_agent(agent_input, bull_thesis=None)
        assert result.metadata.get("attack_target") is None

    @pytest.mark.asyncio
    async def test_targeted_attack_signal_added_to_signals(self):
        from finance_mcp.reasoning.bear_agent import run_bear_agent
        claim = "Graph shows 5 downstream dependents."
        bull = _make_bull_output(weakest_claim=claim)
        agent_input = AgentInput(query="TSMC risk", ticker="TSMC")
        with (
            patch("finance_mcp.reasoning.bear_agent.get_quote", new_callable=AsyncMock) as mock_q,
            patch("finance_mcp.reasoning.bear_agent.trace_impact", new_callable=AsyncMock) as mock_ti,
        ):
            mock_q.return_value = {"success": False}
            mock_ti.return_value = {"success": False}
            result = await run_bear_agent(agent_input, bull_thesis=bull)
        assert any(claim in sig for sig in result.signals)

    @pytest.mark.asyncio
    async def test_confidence_boosted_when_targeting(self):
        from finance_mcp.reasoning.bear_agent import run_bear_agent
        bull = _make_bull_output(weakest_claim="some weak claim")
        agent_input = AgentInput(query="AAPL risk", ticker="AAPL")
        with (
            patch("finance_mcp.reasoning.bear_agent.get_quote", new_callable=AsyncMock) as mock_q,
            patch("finance_mcp.reasoning.bear_agent.trace_impact", new_callable=AsyncMock) as mock_ti,
        ):
            mock_q.return_value = mock_ti.return_value = {"success": False}
            result_with = await run_bear_agent(agent_input, bull_thesis=bull)
            result_without = await run_bear_agent(agent_input, bull_thesis=None)
        assert result_with.confidence > result_without.confidence


# ---------------------------------------------------------------------------
# TestJudgeAgentWithRebuttal
# ---------------------------------------------------------------------------

class TestJudgeAgentWithRebuttal:
    def test_judge_accepts_rebuttal_parameter(self):
        from finance_mcp.reasoning.judge_agent import run_judge_agent
        bull = _make_bull_output()
        bear = _make_bear_output()
        verdict = run_judge_agent(bull, bear, bull_rebuttal="Bull maintains position.")
        assert isinstance(verdict, JudgeVerdict)

    def test_rebuttal_appears_in_summary(self):
        from finance_mcp.reasoning.judge_agent import run_judge_agent
        bull = _make_bull_output(confidence=0.8)
        bear = _make_bear_output(confidence=0.4, attack_target="weak claim")
        verdict = run_judge_agent(bull, bear, bull_rebuttal="Bull maintains: claim is valid.")
        assert "maintains" in verdict.summary or "claim" in verdict.summary

    def test_attack_target_appears_in_summary(self):
        from finance_mcp.reasoning.judge_agent import run_judge_agent
        bull = _make_bull_output(confidence=0.7)
        bear = _make_bear_output(confidence=0.5, attack_target="specific contested claim")
        verdict = run_judge_agent(bull, bear)
        assert "specific contested claim" in verdict.summary

    def test_no_rebuttal_still_returns_valid_verdict(self):
        from finance_mcp.reasoning.judge_agent import run_judge_agent
        bull = _make_bull_output()
        bear = _make_bear_output(attack_target=None)
        verdict = run_judge_agent(bull, bear)
        assert verdict.verdict in {
            "STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL", "INSUFFICIENT DATA"
        }


# ---------------------------------------------------------------------------
# TestAdversarialOrchestrator
# ---------------------------------------------------------------------------

class TestAdversarialOrchestrator:
    @pytest.mark.asyncio
    async def test_result_contains_weakest_claim(self):
        from finance_mcp.reasoning.orchestrator import run_multi_agent_analysis
        with (
            patch("finance_mcp.reasoning.bull_agent.get_quote", new_callable=AsyncMock) as q,
            patch("finance_mcp.reasoning.bull_agent.trace_impact", new_callable=AsyncMock) as ti,
            patch("finance_mcp.reasoning.bear_agent.get_quote", new_callable=AsyncMock) as q2,
            patch("finance_mcp.reasoning.bear_agent.trace_impact", new_callable=AsyncMock) as ti2,
        ):
            q.return_value = q2.return_value = {"success": False}
            ti.return_value = ti2.return_value = {"success": False}
            result = await run_multi_agent_analysis("NVDA supply risk", ticker="NVDA")
        assert "weakest_claim" in result["bull_case"]
        assert isinstance(result["bull_case"]["weakest_claim"], str)

    @pytest.mark.asyncio
    async def test_result_contains_attack_target(self):
        from finance_mcp.reasoning.orchestrator import run_multi_agent_analysis
        with (
            patch("finance_mcp.reasoning.bull_agent.get_quote", new_callable=AsyncMock) as q,
            patch("finance_mcp.reasoning.bull_agent.trace_impact", new_callable=AsyncMock) as ti,
            patch("finance_mcp.reasoning.bear_agent.get_quote", new_callable=AsyncMock) as q2,
            patch("finance_mcp.reasoning.bear_agent.trace_impact", new_callable=AsyncMock) as ti2,
        ):
            q.return_value = q2.return_value = {"success": False}
            ti.return_value = ti2.return_value = {"success": False}
            result = await run_multi_agent_analysis("NVDA supply risk", ticker="NVDA")
        assert "attack_target" in result["bear_case"]

    @pytest.mark.asyncio
    async def test_result_contains_bull_rebuttal(self):
        from finance_mcp.reasoning.orchestrator import run_multi_agent_analysis
        with (
            patch("finance_mcp.reasoning.bull_agent.get_quote", new_callable=AsyncMock) as q,
            patch("finance_mcp.reasoning.bull_agent.trace_impact", new_callable=AsyncMock) as ti,
            patch("finance_mcp.reasoning.bear_agent.get_quote", new_callable=AsyncMock) as q2,
            patch("finance_mcp.reasoning.bear_agent.trace_impact", new_callable=AsyncMock) as ti2,
        ):
            q.return_value = q2.return_value = {"success": False}
            ti.return_value = ti2.return_value = {"success": False}
            result = await run_multi_agent_analysis("AAPL risk", ticker="AAPL")
        assert "bull_rebuttal" in result
        assert isinstance(result["bull_rebuttal"], str)

    @pytest.mark.asyncio
    async def test_sequential_not_parallel(self):
        """Bear agent should receive the bull thesis (proving sequential execution)."""
        from finance_mcp.reasoning.orchestrator import run_multi_agent_analysis
        captured: list[Any] = []

        async def fake_bear(agent_input: AgentInput, bull_thesis=None):
            captured.append(bull_thesis)
            return AgentOutput(
                stance="bear", reasoning="bear", signals=[], confidence=0.4,
                metadata={"attack_target": None},
            )

        with (
            patch("finance_mcp.reasoning.orchestrator.run_bear_agent", side_effect=fake_bear),
            patch("finance_mcp.reasoning.bull_agent.get_quote", new_callable=AsyncMock) as q,
            patch("finance_mcp.reasoning.bull_agent.trace_impact", new_callable=AsyncMock) as ti,
        ):
            q.return_value = ti.return_value = {"success": False}
            await run_multi_agent_analysis("test", ticker="AAPL")

        assert len(captured) == 1
        assert captured[0] is not None  # bear received bull_thesis


# ---------------------------------------------------------------------------
# TestGenerateRebuttal
# ---------------------------------------------------------------------------

class TestGenerateRebuttal:
    def test_maintains_when_bull_confident(self):
        from finance_mcp.reasoning.orchestrator import _generate_rebuttal
        bull = _make_bull_output(confidence=0.75)
        bear = _make_bear_output(confidence=0.55, attack_target="claim X")
        rebuttal = _generate_rebuttal(bull, bear)
        assert "maintains" in rebuttal.lower() or "acknowledged" in rebuttal.lower()

    def test_concedes_when_bear_stronger(self):
        from finance_mcp.reasoning.orchestrator import _generate_rebuttal
        bull = _make_bull_output(confidence=0.40)
        bear = _make_bear_output(confidence=0.80, attack_target="claim Y")
        rebuttal = _generate_rebuttal(bull, bear)
        assert "concedes" in rebuttal.lower() or "less certain" in rebuttal.lower()

    def test_no_attack_target_returns_generic(self):
        from finance_mcp.reasoning.orchestrator import _generate_rebuttal
        bull = _make_bull_output(confidence=0.65)
        bear = _make_bear_output(attack_target=None)
        rebuttal = _generate_rebuttal(bull, bear)
        assert isinstance(rebuttal, str) and len(rebuttal) > 0


# ---------------------------------------------------------------------------
# TestVerdictDB
# ---------------------------------------------------------------------------

class TestVerdictDB:
    def test_initialize_db_creates_table(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db, get_connection
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        conn = get_connection(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='verdicts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_initialize_db_is_idempotent(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        initialize_db(db_path)  # Should not raise

    def test_get_connection_returns_row_factory(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db, get_connection
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        conn = get_connection(db_path)
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_table_has_expected_columns(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db, get_connection
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA table_info(verdicts)")
        cols = {row["name"] for row in cursor.fetchall()}
        expected = {
            "id", "ticker", "query", "verdict", "confidence",
            "created_at", "price_at_verdict", "price_5d", "price_30d",
            "correct_5d", "correct_30d",
        }
        assert expected == cols
        conn.close()


# ---------------------------------------------------------------------------
# TestVerdictTracker
# ---------------------------------------------------------------------------

class TestVerdictTracker:
    @pytest.mark.asyncio
    async def test_record_verdict_returns_uuid(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db
        from finance_mcp.verdict_history.tracker import record_verdict
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        with patch("finance_mcp.verdict_history.tracker.asyncio.create_task"):
            verdict_id = await record_verdict(
                {"ticker": "AAPL", "query": "test", "verdict": "BUY", "confidence": 0.7},
                db_path=db_path,
            )
        assert isinstance(verdict_id, str)
        uuid.UUID(verdict_id)  # Raises if not valid UUID

    @pytest.mark.asyncio
    async def test_record_verdict_stores_row(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db, get_connection
        from finance_mcp.verdict_history.tracker import record_verdict
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        with patch("finance_mcp.verdict_history.tracker.asyncio.create_task"):
            verdict_id = await record_verdict(
                {"ticker": "NVDA", "query": "q", "verdict": "STRONG BUY", "confidence": 0.88,
                 "price_at_verdict": 875.5},
                db_path=db_path,
            )
        conn = get_connection(db_path)
        row = conn.execute("SELECT * FROM verdicts WHERE id = ?", (verdict_id,)).fetchone()
        assert row is not None
        assert row["ticker"] == "NVDA"
        assert row["verdict"] == "STRONG BUY"
        assert row["price_at_verdict"] == pytest.approx(875.5)
        conn.close()

    @pytest.mark.asyncio
    async def test_record_verdict_normalises_ticker(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db, get_connection
        from finance_mcp.verdict_history.tracker import record_verdict
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        with patch("finance_mcp.verdict_history.tracker.asyncio.create_task"):
            verdict_id = await record_verdict(
                {"ticker": "aapl", "query": "q", "verdict": "BUY", "confidence": 0.6},
                db_path=db_path,
            )
        conn = get_connection(db_path)
        row = conn.execute("SELECT ticker FROM verdicts WHERE id = ?", (verdict_id,)).fetchone()
        assert row["ticker"] == "AAPL"
        conn.close()

    @pytest.mark.asyncio
    async def test_record_verdict_spawns_background_task(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db
        from finance_mcp.verdict_history.tracker import record_verdict
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        with patch("finance_mcp.verdict_history.tracker.asyncio.create_task") as mock_ct:
            await record_verdict(
                {"ticker": "TSMC", "query": "q", "verdict": "BUY", "confidence": 0.7,
                 "price_at_verdict": 100.0},
                db_path=db_path,
            )
        mock_ct.assert_called_once()

    def test_is_correct_bullish_up(self):
        from finance_mcp.verdict_history.tracker import _is_correct
        assert _is_correct("STRONG BUY", 100.0, 103.0) == 1

    def test_is_correct_bullish_down(self):
        from finance_mcp.verdict_history.tracker import _is_correct
        assert _is_correct("BUY", 100.0, 97.0) == 0

    def test_is_correct_bearish_down(self):
        from finance_mcp.verdict_history.tracker import _is_correct
        assert _is_correct("STRONG SELL", 100.0, 96.0) == 1

    def test_is_correct_bearish_up(self):
        from finance_mcp.verdict_history.tracker import _is_correct
        assert _is_correct("SELL", 100.0, 103.0) == 0


# ---------------------------------------------------------------------------
# TestVerdictAccuracy
# ---------------------------------------------------------------------------

class TestVerdictAccuracy:
    def _seed(self, db_path: str, rows: list[dict]) -> None:
        from finance_mcp.verdict_history.db import get_connection
        conn = get_connection(db_path)
        for row in rows:
            conn.execute(
                """INSERT INTO verdicts (id, ticker, query, verdict, confidence, created_at,
                   price_at_verdict, price_5d, price_30d, correct_5d, correct_30d)
                   VALUES (:id, :ticker, :query, :verdict, :confidence, :created_at,
                           :price_at_verdict, :price_5d, :price_30d, :correct_5d, :correct_30d)""",
                row,
            )
        conn.commit()
        conn.close()

    def test_empty_db_returns_empty_dict(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db
        from finance_mcp.verdict_history.accuracy import compute_accuracy_stats
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        stats = compute_accuracy_stats(db_path)
        assert stats == {}

    def test_single_verdict_appears_in_stats(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db
        from finance_mcp.verdict_history.accuracy import compute_accuracy_stats
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        self._seed(db_path, [{
            "id": str(uuid.uuid4()), "ticker": "AAPL", "query": "q",
            "verdict": "BUY", "confidence": 0.7, "created_at": "2026-01-01T00:00:00",
            "price_at_verdict": 100, "price_5d": None, "price_30d": None,
            "correct_5d": None, "correct_30d": None,
        }])
        stats = compute_accuracy_stats(db_path)
        assert "BUY" in stats
        assert stats["BUY"]["n"] == 1
        assert stats["BUY"]["5d"] is None  # pending

    def test_accuracy_computed_when_resolved(self, tmp_path):
        from finance_mcp.verdict_history.db import initialize_db
        from finance_mcp.verdict_history.accuracy import compute_accuracy_stats
        db_path = str(tmp_path / "test.db")
        initialize_db(db_path)
        self._seed(db_path, [
            {
                "id": str(uuid.uuid4()), "ticker": "NVDA", "query": "q",
                "verdict": "STRONG BUY", "confidence": 0.9, "created_at": "2026-01-01T00:00:00",
                "price_at_verdict": 100, "price_5d": 105.0, "price_30d": None,
                "correct_5d": 1, "correct_30d": None,
            },
            {
                "id": str(uuid.uuid4()), "ticker": "NVDA", "query": "q2",
                "verdict": "STRONG BUY", "confidence": 0.85, "created_at": "2026-01-02T00:00:00",
                "price_at_verdict": 100, "price_5d": 98.0, "price_30d": None,
                "correct_5d": 0, "correct_30d": None,
            },
        ])
        stats = compute_accuracy_stats(db_path)
        assert stats["STRONG BUY"]["5d"] == pytest.approx(50.0)
        assert stats["STRONG BUY"]["30d"] is None
        assert stats["STRONG BUY"]["n"] == 2


# ---------------------------------------------------------------------------
# TestVerdictEndpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db_settings(tmp_path, monkeypatch):
    """Point the server settings at a fresh temp DB."""
    db_path = str(tmp_path / "test_verdicts.db")
    from finance_mcp.verdict_history.db import initialize_db
    initialize_db(db_path)
    monkeypatch.setenv("VERDICT_DB_PATH", db_path)
    # Clear lru_cache so settings pick up the new env var
    from mcp_server.config import get_settings
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_verdicts_accuracy_endpoint_returns_200(tmp_db_settings):
    from mcp_server.server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/verdicts/accuracy",
            headers={"X-API-Key": "dev_key_change_in_production"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


@pytest.mark.asyncio
async def test_verdicts_history_endpoint_returns_list(tmp_db_settings):
    from mcp_server.server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/verdicts/history",
            headers={"X-API-Key": "dev_key_change_in_production"},
        )
    assert resp.status_code == 200
    assert "verdicts" in resp.json()
    assert isinstance(resp.json()["verdicts"], list)


@pytest.mark.asyncio
async def test_verdicts_accuracy_requires_api_key():
    from mcp_server.server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/verdicts/accuracy")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_verdicts_history_ticker_filter(tmp_db_settings):
    """History endpoint with ?ticker=AAPL should only return AAPL rows."""
    from finance_mcp.verdict_history.db import get_connection
    conn = get_connection(tmp_db_settings)
    conn.execute(
        """INSERT INTO verdicts (id, ticker, query, verdict, confidence, created_at,
           price_at_verdict, price_5d, price_30d, correct_5d, correct_30d)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), "AAPL", "q", "BUY", 0.7, "2026-01-01", None, None, None, None, None),
    )
    conn.execute(
        """INSERT INTO verdicts (id, ticker, query, verdict, confidence, created_at,
           price_at_verdict, price_5d, price_30d, correct_5d, correct_30d)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), "NVDA", "q", "SELL", 0.6, "2026-01-02", None, None, None, None, None),
    )
    conn.commit()
    conn.close()

    from mcp_server.server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/verdicts/history?ticker=AAPL",
            headers={"X-API-Key": "dev_key_change_in_production"},
        )
    assert resp.status_code == 200
    verdicts = resp.json()["verdicts"]
    assert all(v["ticker"] == "AAPL" for v in verdicts)
