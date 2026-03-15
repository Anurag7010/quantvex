"""
Phase 3 — news client static verification.
Run: PYTHONPATH=src .venv/bin/python3.11 tests/check_news_client.py
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent


def check(label, ok, detail=""):
    if ok:
        print(f"  OK  {label}")
    else:
        print(f"FAIL  {label}  {detail}")
        sys.exit(1)


print("=== Phase 3 — news client static verification ===\n")

# 1. Syntax
for rel in [
    "src/finance_mcp/news/__init__.py",
    "src/finance_mcp/news/news_client.py",
]:
    path = ROOT / rel
    check(f"{rel} exists", path.exists())
    try:
        ast.parse(path.read_text())
        check(f"{rel} syntax OK", True)
    except SyntaxError as e:
        check(f"{rel} syntax OK", False, str(e))

# 2. Key symbols in news_client.py
src = (ROOT / "src/finance_mcp/news/news_client.py").read_text()
check("NewsArticle dataclass defined", "class NewsArticle:" in src)
check("NewsClient class defined", "class NewsClient:" in src)
check("fetch_market_news method defined", "async def fetch_market_news(" in src)
check("fetch_semiconductor_news shortcut", "async def fetch_semiconductor_news(" in src)
check("fetch_lithium_news shortcut", "async def fetch_lithium_news(" in src)
check("NEWSAPI_EVERYTHING_URL constant", "NEWSAPI_EVERYTHING_URL" in src)
check("httpx used for HTTP", "import httpx" in src)
check("api_key reads from settings", "get_settings().news_api_key" in src)
check("no duplicate http.get calls", src.count("await http.get(") == 1)
check("response.raise_for_status() present", "raise_for_status()" in src)
check("NewsAPI status check present", 'payload.get("status") != "ok"' in src)
check("_parse_datetime helper defined", "def _parse_datetime(" in src)
check("as_dict method on NewsArticle", "def as_dict(" in src)

# 3. __init__.py re-exports
init_src = (ROOT / "src/finance_mcp/news/__init__.py").read_text()
check("__init__.py exports NewsClient", "NewsClient" in init_src)
check("__init__.py exports NewsArticle", "NewsArticle" in init_src)

# 4. config.py has news_api_key
cfg = (ROOT / "mcp_server/config.py").read_text()
check("config.py has news_api_key", "news_api_key" in cfg)

print("\nAll checks passed.")
