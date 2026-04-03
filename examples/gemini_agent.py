#!/usr/bin/env python3
"""
Gemini + Finance MCP Server Integration

"""
import os
import httpx
import asyncio
import google.generativeai as genai
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from finance_formatter import format_financial_report, USD_TO_INR


# Load environment variables
load_dotenv()

# ============ CONFIGURATION ============
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8000")
MCP_API_KEY = os.getenv("MCP_API_KEY", "dev_key_change_in_production")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

PROFESSIONAL_OUTPUT = os.getenv("PROFESSIONAL_OUTPUT", "true").lower() not in ("false", "0", "no", "off")
DEBUG_MODE = os.getenv("FINANCE_AGENT_DEBUG", "0").lower() in ("1", "true", "yes", "on")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not set in .env")
    
    exit(1)

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)


# ============ MCP TOOL FUNCTIONS ============
async def call_mcp_quote(symbol: str, max_age_sec: int = 60) -> Dict[str, Any]:
    """Fetch quote from MCP"""
    headers = {"X-API-Key": MCP_API_KEY}
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "tool_name": "quote.latest",
            "arguments": {"symbol": symbol.upper(), "maxAgeSec": max_age_sec},
            "agent_id": "gemini_agent",
            "query_text": f"Get quote for {symbol}"
        }
        try:
            response = await client.post(f"{MCP_BASE_URL}/invoke", json=payload, headers=headers)
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}


async def call_mcp_subscribe(symbol: str, channel: str = "trades") -> Dict[str, Any]:
    """Subscribe to real-time stream"""
    headers = {"X-API-Key": MCP_API_KEY}
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "symbol": symbol.upper(),
            "channel": channel,
            "agent_id": "gemini_agent"
        }
        try:
            response = await client.post(f"{MCP_BASE_URL}/subscribe", json=payload, headers=headers)
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}


def _parse_symbols(symbol_arg: Any) -> List[str]:
    """Convert incoming symbol argument into a clean symbol list."""
    if symbol_arg is None:
        return []
    if isinstance(symbol_arg, list):
        candidates = symbol_arg
    else:
        normalized = str(symbol_arg).replace(" and ", ",")
        separators = ["|", "/", " ", ",", ";"]
        for sep in separators:
            normalized = normalized.replace(sep, ",")
        candidates = normalized.split(",")
    symbols = [c.strip().upper() for c in candidates if c and c.strip()]
    return list(dict.fromkeys(symbols))  # dedupe while preserving order


async def _gather_quotes(symbols: List[str], max_age_sec: int) -> Dict[str, Dict[str, Any]]:
    tasks = [call_mcp_quote(symbol, max_age_sec) for symbol in symbols]
    results = await asyncio.gather(*tasks)
    return {symbol: result for symbol, result in zip(symbols, results)}


def _normalize_quote(symbol: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize MCP quote payload into INR fields."""
    base_symbol = (symbol or "").upper() or "N/A"

    if not result.get("success"):
        return {"symbol": base_symbol, "error": result.get("error", "Unknown error")}

    data = result.get("data", {})

    def to_inr(value: Optional[float]) -> Optional[float]:
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


def _sanitize_output(text: str) -> str:
    """Remove markdown emphasis markers for clean CLI output."""
    if not text:
        return ""
    cleaned = text.replace("*", "")
    cleaned = cleaned.replace("_", "")
    cleaned = cleaned.replace("`", "")
    return " ".join(cleaned.split()) if "\n" not in cleaned else "\n".join(line.strip() for line in cleaned.split("\n"))


# ============ TOOL EXECUTION ============
def execute_tool(function_name: str, function_args: Dict[str, Any]) -> str:
    """Execute a tool call and return formatted result"""

    if function_name == "get_stock_quote":
        symbol_arg = function_args.get("symbols") or function_args.get("symbol") or "AAPL"
        symbols = _parse_symbols(symbol_arg)
        if not symbols:
            symbols = ["AAPL"]

        max_age = int(function_args.get("max_age_sec", 60))

        raw_results = asyncio.run(_gather_quotes(symbols, max_age))
        normalized_quotes = [_normalize_quote(sym, raw_results.get(sym, {})) for sym in symbols]

        return format_financial_report({"quotes": normalized_quotes})

    elif function_name == "subscribe_realtime":
        symbol = function_args.get("symbol", "BTCUSDT")
        channel = function_args.get("channel", "trades")

        result = asyncio.run(call_mcp_subscribe(symbol, channel))

        if result.get("subscription_id"):
            return (
                "MARKET STREAM\n"
                f"Symbol: {symbol.upper()}\n"
                f"Channel: {channel}\n"
                f"Subscription ID: {result['subscription_id']}\n"
                "Status: Subscribed"
            )
        else:
            return f"Subscription error: {result.get('error', 'Unknown error')}"

    else:
        return f"Unknown function: {function_name}"


# ============ GEMINI TOOL DEFINITIONS ============
tools = [
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="get_stock_quote",
                description="Get the latest stock or cryptocurrency price quote. Use this for any questions about current prices, stock values, market data, or financial instrument values.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "symbol": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL, TSLA) or crypto pair (e.g., BTCUSDT, ETHUSDT, SOLUSDT)"
                        ),
                        "symbols": genai.protos.Schema(
                            type=genai.protos.Type.ARRAY,
                            items=genai.protos.Schema(type=genai.protos.Type.STRING),
                            description="Multiple symbols for side-by-side comparison."
                        ),
                        "max_age_sec": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Maximum age of cached data in seconds. Default is 60."
                        )
                    },
                    required=[]
                )
            ),
            genai.protos.FunctionDeclaration(
                name="subscribe_realtime",
                description="Subscribe to real-time price updates for a cryptocurrency. Use when user wants live streaming data.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "symbol": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Crypto pair symbol (e.g., BTCUSDT, ETHUSDT)"
                        ),
                        "channel": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Stream channel type: 'trades' or 'quotes'"
                        )
                    },
                    required=["symbol"]
                )
            )
        ]
    )
]


# ============ CHAT WITH GEMINI ============
def chat_with_gemini(user_message: str, chat_history: Optional[list] = None) -> str:
    """
    Send message to Gemini with MCP tool access
    and return the response text.
    """
    # Initialize model with tools
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",  # Free tier, latest model
        tools=tools,
        system_instruction="""You are FinSight AI — a professional financial intelligence assistant.

    Your responses must follow strict financial reporting standards similar to investment research summaries.

    RESPONSE STYLE RULES

    1. Never use markdown emphasis such as: *text* or _text_
    2. Always use clear structured sections.
    3. Use professional financial tone similar to Bloomberg Terminal reports.
    4. Always format currency in Indian Rupees (₹).
    5. Prioritize clarity and readability.
    6. Avoid casual conversational language.
    7. When numerical data is present, organize it clearly.
    8. Always highlight key metrics.

    STANDARD RESPONSE STRUCTURE

    MARKET SUMMARY
    Short explanation of the asset and its current performance.

    PRICE INFORMATION
    Symbol: <symbol>
    Current Price: ₹X
    Previous Close: ₹X
    Change: ₹X (X%)

    TRADING RANGE
    Open: ₹X
    Day High: ₹X
    Day Low: ₹X

    MARKET ACTIVITY
    Volume: X

    ANALYSIS
    Provide 2–3 concise insights about the price movement.

    DATA SOURCE
    Real-time market data via MCP financial server.

    MULTI-ASSET COMPARISON FORMAT

    When multiple assets are requested, produce a comparison table.

    Example format:

    MARKET COMPARISON

    Asset | Price (₹) | Change | Volume
    Apple (AAPL) | ₹XXX | +X% | XXX
    Tesla (TSLA) | ₹XXX | -X% | XXX

    INSIGHTS
    Provide a short explanation comparing the assets.

    TOOL USAGE POLICY

    Always call the financial tools for real-time price data.

    Never fabricate market data.

    SYMBOL MAPPINGS

    Apple = AAPL
    Microsoft = MSFT
    Google = GOOGL
    Amazon = AMZN
    Tesla = TSLA
    NVIDIA = NVDA
    Bitcoin = BTCUSDT
    Ethereum = ETHUSDT
    Solana = SOLUSDT

    FINAL QUALITY CHECK

    Before returning a response, ensure the output looks like a professional financial report.

    If the response is messy or poorly structured, rewrite it before returning it."""
    )
    
    # Start or continue chat
    chat = model.start_chat(history=chat_history or [])
    
    # Send user message
    response = chat.send_message(user_message)
    latest_tool_output: Optional[str] = None

    # Handle function calls
    while response.candidates[0].content.parts:
        function_calls = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                function_calls.append(part.function_call)

        if not function_calls:
            break

        quote_calls = [call for call in function_calls if call.name == "get_stock_quote"]
        aggregated_quote_result: Optional[str] = None

        if len(quote_calls) > 1:
            aggregate_symbols: List[str] = []
            max_ages: List[int] = []
            for call in quote_calls:
                args = dict(call.args) if call.args else {}
                aggregate_symbols.extend(_parse_symbols(args.get("symbols") or args.get("symbol")))
                if "max_age_sec" in args:
                    try:
                        max_ages.append(int(args.get("max_age_sec")))
                    except Exception:
                        pass
            aggregate_symbols = list(dict.fromkeys(aggregate_symbols))
            aggregated_quote_result = execute_tool(
                "get_stock_quote",
                {
                    "symbols": aggregate_symbols,
                    "max_age_sec": min(max_ages) if max_ages else 60,
                },
            )

        function_responses = []
        for function_call in function_calls:
            func_name = function_call.name
            func_args = dict(function_call.args) if function_call.args else {}

            if DEBUG_MODE:
                print(f"\n Gemini calling: {func_name}")
                print(f"   Arguments: {func_args}")

            if aggregated_quote_result and func_name == "get_stock_quote":
                result = aggregated_quote_result
            else:
                result = execute_tool(func_name, func_args)

            latest_tool_output = result

            if DEBUG_MODE:
                print(f" Result:\n{result}\n")

            function_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=func_name,
                        response={"result": result}
                    )
                )
            )

        response = chat.send_message(genai.protos.Content(parts=function_responses))

    final_text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text"):
            final_text += part.text

    final_output = final_text.strip() if final_text else ""
    if PROFESSIONAL_OUTPUT and latest_tool_output:
        final_output = latest_tool_output
    else:
        final_output = _sanitize_output(final_output)

    return final_output


# ============ INTERACTIVE CLI ============
def interactive_mode():
    """Interactive chat"""
    print("=" * 60)
    print("  Gemini + Finance MCP Agent")
    
    print("\nExamples:")
    print("  • What's the price of Apple stock?")
    print("  • How much is Bitcoin worth?")
    print("  • Compare Tesla and NVIDIA prices")
    print("\n'exit' to stop.\n")
    print("-" * 60)
    
    chat_history = []
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break

            response = chat_with_gemini(user_input, chat_history)
            print(f"\n{response}\n")
            
            # Update history for context
            chat_history.append({"role": "user", "parts": [user_input]})
            chat_history.append({"role": "model", "parts": [response]})
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")


# ============ DEMO MODE ============
def demo_mode():
    
    print("=" * 60)
    print("  Gemini + Finance MCP Demo")
    print("=" * 60)
    
    demo_queries = [
        "What's the current price of Apple stock?",
        "How much is Bitcoin trading at right now?",
        "Can you compare Microsoft and Google stock prices?",
        "What's Ethereum worth today?"
    ]
    
    for query in demo_queries:
        print(f"\n{'='*60}")
        print(f"User: {query}")
        print("-" * 60)
        
        try:
            response = chat_with_gemini(query)
            print(f"\n{response}\n")
        except Exception as e:
            print(f"\nError: {e}")
        
        print()


# ============ MAIN ============
if __name__ == "__main__":
    import sys
    
    # Check MCP server health first
    async def check_mcp():
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{MCP_BASE_URL}/health")
                return response.json().get("status") == "healthy"
            except:
                return False
    
    print("Checking MCP server...")
    if not asyncio.run(check_mcp()):
        print("MCP server not running")
        print("   Start with: cd infra && docker-compose up -d")
        exit(1)
    print("MCP server is healthy\n")
    
    # Run mode based on argument
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo_mode()
    else:
        interactive_mode()
