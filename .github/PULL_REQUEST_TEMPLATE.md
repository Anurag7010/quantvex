## What does this PR do?

<!-- Describe the change and the motivation. -->

## How was it tested?

<!-- Describe the test strategy: unit tests, integration tests, manual verification, etc. -->

## Checklist

- [ ] Tests pass (`pytest tests/ -v -m "not integration and not live"`)
- [ ] Lint passes (`ruff check .`)
- [ ] Coverage maintained (`pytest --cov-fail-under=40`)
- [ ] No breaking changes to `/invoke`, `/chat`, or `/health` endpoints
- [ ] No new `print()` statements — use `logger` from `mcp_server/utils/logging.py`
