"""
Unit tests for Phase 1.2 — EDGAR auto-extraction module.

All network and OpenAI calls are mocked. No live EDGAR or Memgraph required.
"""
from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from finance_mcp.edgar.edgar_client import (
    _strip_html,
    _extract_sections,
    EdgarError,
)
from finance_mcp.edgar.supplier_extractor import (
    SupplierRelationship,
    _clamp,
)
from finance_mcp.edgar.graph_updater import UpdateResult
from mcp_server.schemas import ToolResponse


# ---------------------------------------------------------------------------
# edgar_client — pure helpers (no I/O)
# ---------------------------------------------------------------------------

class TestStripHtml:
    def test_removes_tags(self):
        assert "<b>" not in _strip_html("<b>hello</b>")

    def test_preserves_text(self):
        assert "hello world" in _strip_html("<p>hello world</p>")

    def test_decodes_amp_entity(self):
        assert "&" in _strip_html("AT&amp;T")

    def test_removes_nbsp(self):
        result = _strip_html("a&nbsp;b")
        assert "&nbsp;" not in result

    def test_collapses_whitespace(self):
        result = _strip_html("a   b\t\tc")
        assert "   " not in result

    def test_empty_string(self):
        assert _strip_html("") == ""


class TestExtractSections:
    _SAMPLE = (
        "Preamble text.\n"
        "ITEM 1. BUSINESS\n"
        "We source components from TSMC and Samsung.\n"
        "ITEM 1A. RISK FACTORS\n"
        "Our reliance on TSMC represents a concentration risk.\n"
        "ITEM 2. PROPERTIES\n"
        "We operate facilities in California.\n"
    )

    def test_item1_included(self):
        result = _extract_sections(self._SAMPLE)
        assert "ITEM 1. BUSINESS" in result or "source components from TSMC" in result

    def test_item1a_included(self):
        result = _extract_sections(self._SAMPLE)
        assert "concentration risk" in result

    def test_item2_not_included(self):
        result = _extract_sections(self._SAMPLE)
        assert "facilities in California" not in result

    def test_fallback_on_no_headers(self):
        plain = "Some random text without item headers."
        result = _extract_sections(plain)
        assert result == ""

    def test_returns_string(self):
        assert isinstance(_extract_sections(self._SAMPLE), str)


# ---------------------------------------------------------------------------
# edgar_client — get_cik (mocked httpx)
# ---------------------------------------------------------------------------

class TestGetCik:
    @pytest.mark.asyncio
    async def test_returns_cik_for_known_ticker(self):
        from finance_mcp.edgar.edgar_client import get_cik

        tickers_payload = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = tickers_payload

        with patch("httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            cik = await get_cik("AAPL")

        assert cik == "0000320193"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_ticker(self):
        from finance_mcp.edgar.edgar_client import get_cik

        tickers_payload = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = tickers_payload

        with patch("httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            cik = await get_cik("TSMC")

        assert cik is None

    @pytest.mark.asyncio
    async def test_cik_is_zero_padded(self):
        from finance_mcp.edgar.edgar_client import get_cik

        payload = {"0": {"cik_str": 1234, "ticker": "XYZ", "title": "XYZ Corp"}}
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = payload

        with patch("httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            cik = await get_cik("XYZ")

        assert cik == "0000001234"
        assert len(cik) == 10


# ---------------------------------------------------------------------------
# edgar_client — fetch_10k_filing (mocked)
# ---------------------------------------------------------------------------

class TestFetch10kFiling:
    @pytest.mark.asyncio
    async def test_raises_edgar_error_for_unknown_ticker(self):
        from finance_mcp.edgar.edgar_client import fetch_10k_filing

        with patch("finance_mcp.edgar.edgar_client.get_cik", new=AsyncMock(return_value=None)):
            with pytest.raises(EdgarError, match="not found in EDGAR"):
                await fetch_10k_filing("TSMC")

    @pytest.mark.asyncio
    async def test_raises_edgar_error_when_no_10k(self):
        from finance_mcp.edgar.edgar_client import fetch_10k_filing

        with patch("finance_mcp.edgar.edgar_client.get_cik", new=AsyncMock(return_value="0000320193")):
            submissions = {
                "filings": {
                    "recent": {
                        "form": ["8-K", "DEF 14A"],
                        "accessionNumber": ["0000320193-24-000001", "0000320193-24-000002"],
                        "filingDate": ["2024-01-15", "2024-02-01"],
                        "primaryDocument": ["doc1.htm", "doc2.htm"],
                    }
                }
            }
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = submissions

            with patch("httpx.AsyncClient") as MockClient:
                mock_ctx = AsyncMock()
                mock_ctx.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                with pytest.raises(EdgarError, match="No 10-K filing found"):
                    await fetch_10k_filing("AAPL")

    @pytest.mark.asyncio
    async def test_returns_text_and_date(self):
        from finance_mcp.edgar.edgar_client import fetch_10k_filing

        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "filingDate": ["2024-11-01"],
                    "primaryDocument": ["aapl-20240928.htm"],
                }
            }
        }

        html_content = (
            "<html><body>"
            "<p>ITEM 1. BUSINESS</p>"
            "<p>We depend on TSMC for chip manufacturing.</p>"
            "<p>ITEM 2. PROPERTIES</p>"
            "<p>Our headquarters is in Cupertino.</p>"
            "</body></html>"
        )

        submissions_resp = MagicMock()
        submissions_resp.raise_for_status = MagicMock()
        submissions_resp.json.return_value = submissions

        html_resp = MagicMock()
        html_resp.raise_for_status = MagicMock()
        html_resp.text = html_content

        with patch("finance_mcp.edgar.edgar_client.get_cik", new=AsyncMock(return_value="0000320193")):
            with patch("asyncio.sleep", new=AsyncMock()):
                with patch("httpx.AsyncClient") as MockClient:
                    mock_ctx = AsyncMock()
                    mock_ctx.get = AsyncMock(side_effect=[submissions_resp, html_resp])
                    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
                    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                    text, date = await fetch_10k_filing("AAPL")

        assert date == "2024-11-01"
        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_excludes_item2_from_text(self):
        from finance_mcp.edgar.edgar_client import fetch_10k_filing

        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "filingDate": ["2024-11-01"],
                    "primaryDocument": ["aapl.htm"],
                }
            }
        }
        html_content = (
            "ITEM 1. BUSINESS We source chips from TSMC. "
            "ITEM 2. PROPERTIES Our HQ is in Cupertino."
        )

        submissions_resp = MagicMock()
        submissions_resp.raise_for_status = MagicMock()
        submissions_resp.json.return_value = submissions

        html_resp = MagicMock()
        html_resp.raise_for_status = MagicMock()
        html_resp.text = html_content

        with patch("finance_mcp.edgar.edgar_client.get_cik", new=AsyncMock(return_value="0000320193")):
            with patch("asyncio.sleep", new=AsyncMock()):
                with patch("httpx.AsyncClient") as MockClient:
                    mock_ctx = AsyncMock()
                    mock_ctx.get = AsyncMock(side_effect=[submissions_resp, html_resp])
                    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
                    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                    text, _ = await fetch_10k_filing("AAPL")

        assert "Cupertino" not in text


# ---------------------------------------------------------------------------
# supplier_extractor — _clamp helper + extract_supplier_relationships
# ---------------------------------------------------------------------------

class TestClamp:
    def test_clamps_above_one(self):
        assert _clamp(1.5) == 1.0

    def test_clamps_below_zero(self):
        assert _clamp(-0.5) == 0.0

    def test_passes_midrange(self):
        assert _clamp(0.7) == 0.7

    def test_handles_non_numeric(self):
        assert _clamp("bad") == 0.5

    def test_handles_none(self):
        assert _clamp(None) == 0.5


class TestExtractSupplierRelationships:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self):
        from finance_mcp.edgar.supplier_extractor import extract_supplier_relationships

        with patch("finance_mcp.edgar.supplier_extractor.get_settings") as mock_settings:
            mock_settings.return_value.groq_api_key = ""
            result = await extract_supplier_relationships("some 10-K text", "AAPL")

        assert result == []

    @pytest.mark.asyncio
    async def test_parses_gpt_response(self):
        from finance_mcp.edgar.supplier_extractor import extract_supplier_relationships

        gpt_response = json.dumps({
            "relationships": [
                {
                    "supplier_ticker": "TSM",
                    "supplier_name": "Taiwan Semiconductor Manufacturing",
                    "relationship_type": "supplier",
                    "dependency_strength": 0.9,
                    "evidence_quote": "We rely on TSMC for chip manufacturing",
                }
            ]
        })

        mock_choice = MagicMock()
        mock_choice.message.content = gpt_response
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("finance_mcp.edgar.supplier_extractor.get_settings") as mock_settings:
            mock_settings.return_value.groq_api_key = "gsk-test"
            mock_settings.return_value.groq_base_url = "https://api.groq.com/openai/v1"
            mock_settings.return_value.groq_model = "llama-3.3-70b-versatile"
            with patch("finance_mcp.edgar.supplier_extractor.AsyncOpenAI", return_value=mock_client):
                result = await extract_supplier_relationships("filing text", "AAPL")

        assert len(result) == 1
        assert result[0].supplier_ticker == "TSM"
        assert result[0].relationship_type == "supplier"
        assert result[0].dependency_strength == 0.9

    @pytest.mark.asyncio
    async def test_skips_self_references(self):
        from finance_mcp.edgar.supplier_extractor import extract_supplier_relationships

        gpt_response = json.dumps({
            "relationships": [
                {
                    "supplier_ticker": "AAPL",  # self-reference
                    "supplier_name": "Apple Inc.",
                    "relationship_type": "supplier",
                    "dependency_strength": 0.5,
                    "evidence_quote": "...",
                }
            ]
        })

        mock_choice = MagicMock()
        mock_choice.message.content = gpt_response
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("finance_mcp.edgar.supplier_extractor.get_settings") as mock_settings:
            mock_settings.return_value.groq_api_key = "gsk-test"
            mock_settings.return_value.groq_base_url = "https://api.groq.com/openai/v1"
            mock_settings.return_value.groq_model = "llama-3.3-70b-versatile"
            with patch("finance_mcp.edgar.supplier_extractor.AsyncOpenAI", return_value=mock_client):
                result = await extract_supplier_relationships("filing text", "AAPL")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_json_decode_error(self):
        from finance_mcp.edgar.supplier_extractor import extract_supplier_relationships

        mock_choice = MagicMock()
        mock_choice.message.content = "not json at all"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("finance_mcp.edgar.supplier_extractor.get_settings") as mock_settings:
            mock_settings.return_value.groq_api_key = "gsk-test"
            mock_settings.return_value.groq_base_url = "https://api.groq.com/openai/v1"
            mock_settings.return_value.groq_model = "llama-3.3-70b-versatile"
            with patch("finance_mcp.edgar.supplier_extractor.AsyncOpenAI", return_value=mock_client):
                result = await extract_supplier_relationships("filing text", "AAPL")

        assert result == []

    @pytest.mark.asyncio
    async def test_skips_invalid_relationship_type(self):
        from finance_mcp.edgar.supplier_extractor import extract_supplier_relationships

        gpt_response = json.dumps({
            "relationships": [
                {
                    "supplier_ticker": "TSM",
                    "supplier_name": "TSMC",
                    "relationship_type": "competitor",  # invalid
                    "dependency_strength": 0.5,
                    "evidence_quote": "...",
                }
            ]
        })

        mock_choice = MagicMock()
        mock_choice.message.content = gpt_response
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("finance_mcp.edgar.supplier_extractor.get_settings") as mock_settings:
            mock_settings.return_value.groq_api_key = "gsk-test"
            mock_settings.return_value.groq_base_url = "https://api.groq.com/openai/v1"
            mock_settings.return_value.groq_model = "llama-3.3-70b-versatile"
            with patch("finance_mcp.edgar.supplier_extractor.AsyncOpenAI", return_value=mock_client):
                result = await extract_supplier_relationships("filing text", "AAPL")

        assert result == []

    @pytest.mark.asyncio
    async def test_handles_gpt_api_error(self):
        from finance_mcp.edgar.supplier_extractor import extract_supplier_relationships

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API error"))

        with patch("finance_mcp.edgar.supplier_extractor.get_settings") as mock_settings:
            mock_settings.return_value.groq_api_key = "gsk-test"
            mock_settings.return_value.groq_base_url = "https://api.groq.com/openai/v1"
            mock_settings.return_value.groq_model = "llama-3.3-70b-versatile"
            with patch("finance_mcp.edgar.supplier_extractor.AsyncOpenAI", return_value=mock_client):
                result = await extract_supplier_relationships("filing text", "AAPL")

        assert result == []


# ---------------------------------------------------------------------------
# graph_updater
# ---------------------------------------------------------------------------

class TestUpdateGraphFromFiling:
    def _make_rel(
        self,
        ticker="TSM",
        name="TSMC",
        rel_type="supplier",
        strength=0.9,
        evidence="critical supplier",
    ) -> SupplierRelationship:
        return SupplierRelationship(
            supplier_ticker=ticker,
            supplier_name=name,
            relationship_type=rel_type,
            dependency_strength=strength,
            evidence_quote=evidence,
        )

    @pytest.mark.asyncio
    async def test_empty_relationships_returns_zeros(self):
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        result = await update_graph_from_filing("AAPL", [], filing_date="2024-11-01")
        assert result.new_edges_added == 0
        assert result.updated_edges == 0
        assert result.companies_discovered == 0

    @pytest.mark.asyncio
    async def test_supplier_edge_direction(self):
        """Supplier rel → (ticker)-[:DEPENDS_ON]->(supplier)"""
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        runs: list[dict] = []

        def mock_run(query, **params):
            runs.append({"query": query, "params": params})
            if "MATCH (a:Company" in query and "RETURN r.source" in query:
                return []  # new edge
            return []

        with patch("finance_mcp.edgar.graph_updater.GraphClient") as MockGC:
            mock_client = MagicMock()
            mock_client._run.side_effect = mock_run
            MockGC.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockGC.return_value.__exit__ = MagicMock(return_value=False)

            rel = self._make_rel(rel_type="supplier")
            result = await update_graph_from_filing("AAPL", [rel])

        # Find the MERGE edge call
        merge_calls = [r for r in runs if "MERGE (a)-[r:DEPENDS_ON]->(b)" in r["query"]]
        assert len(merge_calls) == 1
        assert merge_calls[0]["params"]["src"] == "AAPL"
        assert merge_calls[0]["params"]["dst"] == "TSM"

    @pytest.mark.asyncio
    async def test_customer_edge_direction(self):
        """Customer rel → (customer)-[:DEPENDS_ON]->(ticker)"""
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        runs: list[dict] = []

        def mock_run(query, **params):
            runs.append({"query": query, "params": params})
            return []

        with patch("finance_mcp.edgar.graph_updater.GraphClient") as MockGC:
            mock_client = MagicMock()
            mock_client._run.side_effect = mock_run
            MockGC.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockGC.return_value.__exit__ = MagicMock(return_value=False)

            rel = self._make_rel(ticker="NVDA", name="NVIDIA", rel_type="customer")
            await update_graph_from_filing("AAPL", [rel])

        merge_calls = [r for r in runs if "MERGE (a)-[r:DEPENDS_ON]->(b)" in r["query"]]
        assert merge_calls[0]["params"]["src"] == "NVDA"
        assert merge_calls[0]["params"]["dst"] == "AAPL"

    @pytest.mark.asyncio
    async def test_new_edge_increments_new_edges_added(self):
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        def mock_run(query, **params):
            if "RETURN r.source" in query:
                return []  # edge does not exist yet
            return []

        with patch("finance_mcp.edgar.graph_updater.GraphClient") as MockGC:
            mock_client = MagicMock()
            mock_client._run.side_effect = mock_run
            MockGC.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockGC.return_value.__exit__ = MagicMock(return_value=False)

            result = await update_graph_from_filing("AAPL", [self._make_rel()])

        assert result.new_edges_added == 1
        assert result.updated_edges == 0

    @pytest.mark.asyncio
    async def test_existing_edge_increments_updated_edges(self):
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        def mock_run(query, **params):
            if "RETURN r.source" in query:
                return [{"source": "EDGAR"}]  # edge already exists
            return []

        with patch("finance_mcp.edgar.graph_updater.GraphClient") as MockGC:
            mock_client = MagicMock()
            mock_client._run.side_effect = mock_run
            MockGC.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockGC.return_value.__exit__ = MagicMock(return_value=False)

            result = await update_graph_from_filing("AAPL", [self._make_rel()])

        assert result.updated_edges == 1
        assert result.new_edges_added == 0

    @pytest.mark.asyncio
    async def test_graph_error_captured_in_errors_list(self):
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        def mock_run(query, **params):
            if "MERGE (c:Company" in query:
                raise RuntimeError("connection refused")
            return []

        with patch("finance_mcp.edgar.graph_updater.GraphClient") as MockGC:
            mock_client = MagicMock()
            mock_client._run.side_effect = mock_run
            MockGC.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockGC.return_value.__exit__ = MagicMock(return_value=False)

            result = await update_graph_from_filing("AAPL", [self._make_rel()])

        assert len(result.errors) == 1
        assert "TSM" in result.errors[0]

    @pytest.mark.asyncio
    async def test_filing_date_in_result(self):
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        with patch("finance_mcp.edgar.graph_updater.GraphClient") as MockGC:
            mock_client = MagicMock()
            mock_client._run.return_value = []
            MockGC.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockGC.return_value.__exit__ = MagicMock(return_value=False)

            result = await update_graph_from_filing(
                "AAPL", [self._make_rel()], filing_date="2024-11-01"
            )

        assert result.filing_date == "2024-11-01"

    @pytest.mark.asyncio
    async def test_update_result_as_dict_keys(self):
        from finance_mcp.edgar.graph_updater import update_graph_from_filing

        result = await update_graph_from_filing("AAPL", [], filing_date="2024-11-01")
        d = result.as_dict()
        assert set(d.keys()) == {
            "ticker", "new_edges_added", "updated_edges",
            "companies_discovered", "filing_date", "errors",
        }


# ---------------------------------------------------------------------------
# handle_edgar_refresh — end-to-end with all dependencies mocked
# ---------------------------------------------------------------------------

class TestHandleEdgarRefresh:
    @pytest.mark.asyncio
    async def test_empty_ticker_returns_failure(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh

        result = await handle_edgar_refresh("")
        assert result.success is False
        assert "non-empty" in (result.error or "")

    @pytest.mark.asyncio
    async def test_invalid_ticker_returns_failure(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh

        result = await handle_edgar_refresh("INVALID TICKER!")
        assert result.success is False
        assert "Invalid ticker format" in (result.error or "")

    @pytest.mark.asyncio
    async def test_edgar_error_returns_failure(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh

        with patch(
            "mcp_server.invoke_handlers.edgar_refresh.fetch_10k_filing",
            new=AsyncMock(side_effect=EdgarError("not found in EDGAR")),
        ):
            result = await handle_edgar_refresh("TSMC")

        assert result.success is False
        assert "not found in EDGAR" in (result.error or "")

    @pytest.mark.asyncio
    async def test_no_relationships_returns_success_with_note(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh

        with patch(
            "mcp_server.invoke_handlers.edgar_refresh.fetch_10k_filing",
            new=AsyncMock(return_value=("some filing text", "2024-11-01")),
        ):
            with patch(
                "mcp_server.invoke_handlers.edgar_refresh.extract_supplier_relationships",
                new=AsyncMock(return_value=[]),
            ):
                result = await handle_edgar_refresh("AAPL")

        assert result.success is True
        assert result.data["relationships_found"] == 0
        assert "note" in result.data

    @pytest.mark.asyncio
    async def test_successful_refresh_returns_correct_fields(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh
        from finance_mcp.edgar.graph_updater import UpdateResult

        update = UpdateResult(
            ticker="AAPL",
            new_edges_added=3,
            updated_edges=1,
            companies_discovered=4,
            filing_date="2024-11-01",
        )
        rels = [
            SupplierRelationship("TSM", "TSMC", "supplier", 0.9, "key fab"),
            SupplierRelationship("ARMH", "ARM Holdings", "supplier", 0.7, "IP"),
            SupplierRelationship("SAMSUNG", "Samsung", "supplier", 0.6, "NAND"),
            SupplierRelationship("NVDA", "NVIDIA", "customer", 0.4, "buys chips"),
        ]

        with patch(
            "mcp_server.invoke_handlers.edgar_refresh.fetch_10k_filing",
            new=AsyncMock(return_value=("filing text content", "2024-11-01")),
        ):
            with patch(
                "mcp_server.invoke_handlers.edgar_refresh.extract_supplier_relationships",
                new=AsyncMock(return_value=rels),
            ):
                with patch(
                    "mcp_server.invoke_handlers.edgar_refresh.update_graph_from_filing",
                    new=AsyncMock(return_value=update),
                ):
                    result = await handle_edgar_refresh("AAPL")

        assert result.success is True
        data = result.data
        assert data["ticker"] == "AAPL"
        assert data["filing_date"] == "2024-11-01"
        assert data["relationships_found"] == 4
        assert data["new_edges_added"] == 3
        assert data["updated_edges"] == 1
        assert data["companies_discovered"] == 4

    @pytest.mark.asyncio
    async def test_ticker_uppercased(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh

        received: list[str] = []

        async def mock_fetch(ticker):
            received.append(ticker)
            raise EdgarError("stop here")

        with patch("mcp_server.invoke_handlers.edgar_refresh.fetch_10k_filing", new=mock_fetch):
            await handle_edgar_refresh("aapl")

        assert received[0] == "AAPL"

    @pytest.mark.asyncio
    async def test_graph_error_returns_failure(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh

        rels = [SupplierRelationship("TSM", "TSMC", "supplier", 0.9, "fab")]

        with patch(
            "mcp_server.invoke_handlers.edgar_refresh.fetch_10k_filing",
            new=AsyncMock(return_value=("text", "2024-11-01")),
        ):
            with patch(
                "mcp_server.invoke_handlers.edgar_refresh.extract_supplier_relationships",
                new=AsyncMock(return_value=rels),
            ):
                with patch(
                    "mcp_server.invoke_handlers.edgar_refresh.update_graph_from_filing",
                    new=AsyncMock(side_effect=RuntimeError("graph down")),
                ):
                    result = await handle_edgar_refresh("AAPL")

        assert result.success is False
        assert "Graph update failed" in (result.error or "")

    @pytest.mark.asyncio
    async def test_returns_tool_response_instance(self):
        from mcp_server.invoke_handlers.edgar_refresh import handle_edgar_refresh

        with patch(
            "mcp_server.invoke_handlers.edgar_refresh.fetch_10k_filing",
            new=AsyncMock(side_effect=EdgarError("not found")),
        ):
            result = await handle_edgar_refresh("AAPL")

        assert isinstance(result, ToolResponse)
