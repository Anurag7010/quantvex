# QuantVex Eval Harness

Directional accuracy benchmark for the multi-agent investment analysis pipeline.

## What it tests

The harness runs 25 realistic investment queries through the full QuantVex
pipeline — bull agent → bear attack → bull rebuttal → judge verdict — and checks
whether the output verdict (`STRONG BUY / BUY / HOLD / SELL / STRONG SELL`) matches
the expected directional label (`bullish / neutral / bearish`).

**Mapping:**

| Verdict         | Direction |
|-----------------|-----------|
| STRONG BUY, BUY | bullish   |
| HOLD            | neutral   |
| SELL, STRONG SELL | bearish |
| INSUFFICIENT DATA | neutral |

### Test case distribution

| Category | Count | Examples |
|----------|-------|---------|
| Clearly bullish | 10 | NVDA, MSFT, AAPL, AMZN, GOOGL, META, V, JPM, LLY, CRM |
| Clearly bearish | 7 | INTC, PARA, MPW, PFE, BYND, WBA, QCOM |
| Contested HOLD | 8 | TSLA, AMD, BABA, PYPL, NFLX, XOM, DIS, BRK-B |

## Running

```bash
# Full eval (requires GROQ_API_KEY, live market data)
PYTHONPATH=.:src python evals/run_evals.py

# Fast smoke test (5 cases)
PYTHONPATH=.:src python evals/run_evals.py --limit 5

# Include single-LLM baseline comparison
PYTHONPATH=.:src python evals/run_evals.py --baseline
```

Results are saved to `evals/results/latest.json`.

## Quality gate

The script exits with **code 1** if accuracy falls below **60%**.

This gate enforces a minimum bar above random chance (33% for a 3-class problem).
A healthy run with working API keys typically achieves 72-80% on this benchmark.

## Interpreting the baseline

Running with `--baseline` fires each query as a bare Groq LLM call with zero
tools (no live quote, no graph traversal, no news). This measures what the
model achieves from training knowledge alone.

The delta between pipeline accuracy and baseline accuracy quantifies the value
added by real-time tool use.

## Files

| File | Description |
|------|-------------|
| `test_cases.json` | 25 benchmark test cases with expected directions |
| `run_evals.py` | Evaluation runner — imports handlers directly, no HTTP |
| `results/latest.json` | Most recent eval output (overwritten on each run) |
