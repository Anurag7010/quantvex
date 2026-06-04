"""
evals/run_evals.py

Evaluation runner for the QuantVex multi-agent analysis pipeline.

Loads 25 benchmark test cases from test_cases.json, invokes the
handle_multi_agent_analysis handler directly (no HTTP), and measures
directional accuracy against expected verdicts.

Quality gate: exits with code 1 if accuracy < 60%.

Usage
-----
    PYTHONPATH=.:src python evals/run_evals.py

    # Run baseline comparison (single LLM, no tools)
    PYTHONPATH=.:src python evals/run_evals.py --baseline

    # Cap to first N cases (fast smoke test)
    PYTHONPATH=.:src python evals/run_evals.py --limit 5

Environment
-----------
GROQ_API_KEY must be set. Without it, every verdict will be INSUFFICIENT DATA.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------------
# Path bootstrap so we can import from repo root without installation
# ------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "src"))

CASES_FILE = Path(__file__).parent / "test_cases.json"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------------
# Verdict → direction mapping
# ------------------------------------------------------------------
_BULLISH_VERDICTS = {"STRONG BUY", "BUY"}
_BEARISH_VERDICTS = {"SELL", "STRONG SELL"}
_NEUTRAL_VERDICTS = {"HOLD", "INSUFFICIENT DATA"}


def _map_verdict(verdict: Optional[str]) -> str:
    if not verdict:
        return "neutral"
    v = verdict.upper().strip()
    if v in _BULLISH_VERDICTS:
        return "bullish"
    if v in _BEARISH_VERDICTS:
        return "bearish"
    return "neutral"


# ------------------------------------------------------------------
# Multi-agent pipeline runner
# ------------------------------------------------------------------
async def _run_multi_agent(query: str, ticker: Optional[str]) -> dict:
    from mcp_server.invoke_handlers.multi_agent_analysis import handle_multi_agent_analysis

    response = await handle_multi_agent_analysis(query=query, ticker=ticker)
    if response.success and response.data:
        return response.data
    return {"verdict": "INSUFFICIENT DATA", "error": response.error}


# ------------------------------------------------------------------
# Baseline: single LLM call with no tools
# ------------------------------------------------------------------
async def _run_baseline(query: str, ticker: Optional[str]) -> str:
    """Ask a plain Groq LLM (no tools) for a buy/hold/sell verdict."""
    try:
        from openai import AsyncOpenAI

        from mcp_server.config import get_settings

        settings = get_settings()
        if not settings.groq_api_key:
            return "neutral"

        client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
        ticker_hint = f" (ticker: {ticker})" if ticker else ""
        prompt = (
            f"You are a financial analyst. Given the query: '{query}'{ticker_hint}\n"
            "Respond with EXACTLY one word: BUY, SELL, or HOLD. Nothing else."
        )
        resp = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip().upper()
        return _map_verdict(raw)
    except Exception:
        return "neutral"


# ------------------------------------------------------------------
# Table printer
# ------------------------------------------------------------------
def _print_table(results: list[dict]) -> None:
    w_id, w_ticker, w_exp, w_got, w_match, w_ms = 8, 8, 10, 15, 7, 10
    header = (
        f"{'ID':<{w_id}} {'Ticker':<{w_ticker}} {'Expected':<{w_exp}} "
        f"{'Got':<{w_match}} {'Verdict':<{w_got}} {'Latency':>{w_ms}}"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for r in results:
        match_sym = "PASS" if r["pass"] else "FAIL"
        print(
            f"{r['id']:<{w_id}} {str(r['ticker']):<{w_ticker}} "
            f"{r['expected']:<{w_exp}} {match_sym:<{w_match}} "
            f"{str(r['verdict']):<{w_got}} {r['latency_ms']:>{w_ms}.0f}ms"
        )
    print(sep)


# ------------------------------------------------------------------
# Main eval loop
# ------------------------------------------------------------------
async def run_evals(
    limit: Optional[int] = None,
    run_baseline: bool = False,
) -> dict:
    cases = json.loads(CASES_FILE.read_text())
    if limit:
        cases = cases[:limit]

    results = []
    baseline_results = []
    total = len(cases)

    print(f"\nQuantVex Multi-Agent Eval — {total} test cases")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")

    for i, case in enumerate(cases, 1):
        print(f"  [{i:02d}/{total}] {case['id']} {case['ticker']:>6}  {case['query'][:55]}...")

        # --- multi-agent pipeline ---
        t0 = time.time()
        try:
            data = await _run_multi_agent(case["query"], case.get("ticker"))
            verdict = data.get("verdict", "INSUFFICIENT DATA")
        except Exception as exc:
            verdict = "INSUFFICIENT DATA"
            data = {"error": str(exc)}
        latency_ms = (time.time() - t0) * 1000

        got_dir = _map_verdict(verdict)
        exp_dir = case["expected_direction"]
        passed = got_dir == exp_dir

        row = {
            "id": case["id"],
            "ticker": case.get("ticker", ""),
            "query": case["query"],
            "expected": exp_dir,
            "verdict": verdict,
            "got_direction": got_dir,
            "pass": passed,
            "latency_ms": round(latency_ms, 1),
            "raw": data,
        }
        results.append(row)
        status = "✓" if passed else "✗"
        print(f"         {status}  verdict={verdict}  direction={got_dir}  ({latency_ms:.0f}ms)")

        # --- baseline (optional) ---
        if run_baseline:
            b_dir = await _run_baseline(case["query"], case.get("ticker"))
            baseline_results.append({
                "id": case["id"],
                "expected": exp_dir,
                "got_direction": b_dir,
                "pass": b_dir == exp_dir,
            })

    # --- Summary ---
    passed_count = sum(1 for r in results if r["pass"])
    accuracy = passed_count / total * 100
    avg_latency = sum(r["latency_ms"] for r in results) / total

    baseline_acc: Optional[float] = None
    if run_baseline and baseline_results:
        b_passed = sum(1 for r in baseline_results if r["pass"])
        baseline_acc = b_passed / len(baseline_results) * 100

    print()
    _print_table(results)
    print(f"\nResults:  {passed_count}/{total} passed")
    print(f"Accuracy: {accuracy:.1f}%")
    print(f"Avg latency: {avg_latency:.0f}ms")
    if baseline_acc is not None:
        print(f"Baseline (no tools): {baseline_acc:.1f}%")
        improvement = accuracy - baseline_acc
        sign = "+" if improvement >= 0 else ""
        print(f"Pipeline improvement: {sign}{improvement:.1f} pp over baseline")

    summary = {
        "run_at": datetime.utcnow().isoformat(),
        "total": total,
        "passed": passed_count,
        "accuracy_pct": round(accuracy, 1),
        "avg_latency_ms": round(avg_latency, 1),
        "baseline_accuracy_pct": round(baseline_acc, 1) if baseline_acc is not None else None,
        "quality_gate": "PASS" if accuracy >= 60 else "FAIL",
        "results": results,
    }

    results_path = RESULTS_DIR / "latest.json"
    results_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nResults saved → {results_path}")
    print(f"Quality gate (≥60%): {summary['quality_gate']}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QuantVex multi-agent eval harness")
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N cases")
    parser.add_argument("--baseline", action="store_true", help="Also run single-LLM baseline")
    args = parser.parse_args()

    summary = asyncio.run(run_evals(limit=args.limit, run_baseline=args.baseline))

    if summary["quality_gate"] == "FAIL":
        print(f"\nQuality gate FAILED: {summary['accuracy_pct']}% < 60% threshold")
        sys.exit(1)


if __name__ == "__main__":
    main()
