"""
Phase 3 static verification script.
Run with:  PYTHONPATH=src .venv/bin/python3.11 tests/check_phase3.py
"""
import json
import pathlib
import ast
import sys

ROOT = pathlib.Path(__file__).parent.parent

def check(label, ok, detail=""):
    if ok:
        print(f"  OK  {label}")
    else:
        print(f"FAIL  {label}  {detail}")
        sys.exit(1)

print("=== Phase 3 static verification ===\n")

# 1. trace_impact.py syntax
src = (ROOT / "mcp_server/invoke_handlers/trace_impact.py").read_text()
try:
    ast.parse(src)
    check("trace_impact.py parses without syntax errors", True)
except SyntaxError as e:
    check("trace_impact.py parses without syntax errors", False, str(e))

# 2. Required symbols present in trace_impact.py
check("handle_trace_impact function defined", "async def handle_trace_impact" in src)
check("SecureGraphClient imported", "SecureGraphClient" in src)
check("ToolResponse imported", "ToolResponse" in src)
check("ticker validation present", "_TICKER_RE" in src)
check("max_hops validation present", "_MAX_HOPS_LIMIT" in src)
check("trace_impact() called", "client.trace_impact(" in src)

# 3. __init__.py exports
init_src = (ROOT / "mcp_server/invoke_handlers/__init__.py").read_text()
check("__init__.py exports handle_trace_impact", "handle_trace_impact" in init_src)

# 4. server.py dispatch
srv = (ROOT / "mcp_server/server.py").read_text()
check("server.py imports handle_trace_impact", "handle_trace_impact" in srv)
check("server.py dispatches trace_impact", '"trace_impact"' in srv)

# 5. config.py nebula settings
cfg = (ROOT / "mcp_server/config.py").read_text()
check("config.py has nebula_host", "nebula_host" in cfg)
check("config.py has nebula_port", "nebula_port" in cfg)

# 6. capabilities.json
caps = json.loads((ROOT / "mcp_server/capabilities.json").read_text())
tool_names = [t["name"] for t in caps["tools"]]
check(f"capabilities.json tools: {tool_names}", "trace_impact" in tool_names)

ti_tool = next(t for t in caps["tools"] if t["name"] == "trace_impact")
check("trace_impact has description", bool(ti_tool.get("description")))
check("trace_impact inputSchema has ticker", "ticker" in ti_tool["inputSchema"]["properties"])
check("trace_impact inputSchema has max_hops", "max_hops" in ti_tool["inputSchema"]["properties"])
check("trace_impact required includes ticker", "ticker" in ti_tool["inputSchema"]["required"])

print("\nAll checks passed.")
