# Frontend Integration Guide

## Overview

The Finance MCP agent now produces clean, structured financial reports optimized for web rendering. All responses are formatted for display in React chat components using `whitespace-pre-wrap`.

## Features

✓ **No Markdown Symbols** – Clean plain text output (no `*`, `_`, `###`, `---`)
✓ **Professional Formatting** – Sections with proper spacing and alignment
✓ **ANSI-Free Web Output** – Formatted for web frontends (no terminal escape codes)
✓ **Bullet Points** – Uses `•` character for insights and analysis
✓ **Proper Currency** – All prices shown in INR (₹) with proper formatting
✓ **Tables** – Multi-asset comparisons render cleanly in monospace

## Environment Setup

### For Web Backend

Set these environment variables before starting the MCP server or backend service:

```bash
export WEB_MODE=1                    # Disable ANSI codes (default for web)
export ENABLE_BOLD_FORMATTING=0      # No bold escape sequences
export PROFESSIONAL_OUTPUT=true      # Always use formatter
```

### For CLI (Local Testing)

Set these to see professional formatting with bold text:

```bash
export WEB_MODE=0                    # Enable ANSI codes for terminal
export ENABLE_BOLD_FORMATTING=1      # Use bold formatting
export PROFESSIONAL_OUTPUT=true      # Always use formatter
```

## Example Outputs

### Single Asset Report

```
MARKET SUMMARY

Apple Inc. is trading above the previous close, reflecting positive intraday momentum.


PRICE INFORMATION

Symbol: AAPL
Current Price: ₹14,325.20
Previous Close: ₹14,210.15
Change: ₹+115.05 (+0.81%)


TRADING RANGE

Open: ₹14,240.00
Day High: ₹14,450.30
Day Low: ₹14,180.10


MARKET ACTIVITY

Volume: 52,381,220


AI ANALYSIS

• The stock is trading above the previous close.
• Price is mid-range within today's trading band.
• Intraday volatility remains moderate.


DATA SOURCE

finnhub (fresh)
```

### Multi-Asset Comparison

```
MARKET COMPARISON

Asset        Price (₹)      Change        Volume
----------------------------------------------------------------
AAL               ₹1,150.42  ₹+25.42 (+2.26%)        30M
DAL               ₹4,280.10  ₹-19.90 (-0.46%)        20M
LUV               ₹2,850.75  ₹-29.25 (-1.02%)        12M


AI INSIGHTS

• AAL shows the strongest move at ₹+25.42 (+2.26%).
• LUV is lagging peers at ₹-29.25 (-1.02%).
• Data sourced from MCP financial server.


DATA SOURCE

Real-time market data via MCP financial server.
```

## React Component Integration

The formatter output is optimized for this React component pattern:

```tsx
<div className="prose prose-sm dark:prose-invert">
  <p className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
    {message.content}
  </p>
</div>
```

The output will render cleanly with:

- Proper line breaks preserved
- Monospace font for alignment
- Natural readability in chat bubbles
- Professional financial report appearance

## Usage via MCP `/chat` Endpoint

When calling the MCP backend `/chat` endpoint:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{
    "query": "Compare Tesla and NVIDIA prices today",
    "agent_id": "web_agent"
  }'
```

**Response** (plain text, web-safe):

```
MARKET COMPARISON

Asset        Price (₹)      Change        Volume
...
```

## Running the CLI Agent

For local testing with bold formatting:

```bash
export WEB_MODE=0 ENABLE_BOLD_FORMATTING=1 PROFESSIONAL_OUTPUT=true
python3 examples/gemini_agent.py
```

Type queries like:

- "What's the price of Apple?"
- "Compare Google and Microsoft"
- "Trade volume for Bitcoin"

## Key Formatting Rules

1. **Headers** – Plain text with blank lines (no markdown)
2. **Sections** – Separated by double blank lines
3. **Currency** – Always in ₹ with 2 decimal places
4. **Numbers** – Formatted with commas (e.g., `52,381,220`)
5. **Signs** – Plus/minus for changes (e.g., `₹+115.05`)
6. **Percentages** – Always with 2 decimals (e.g., `+0.81%`)
7. **Volumes** – Abbreviated when > 1M (e.g., `30M` instead of `30,211,200`)

## No Markdown Support

To ensure clean web rendering, the formatter explicitly avoids:

- ~~strikethrough~~
- `inline code`
- _emphasis_
- **bold** (use section headers instead)
- # headings (use section headers)
- --- separators (use spacing)
- > blockquotes
- [ ] checkboxes

## Verification

To verify the formatter is working correctly:

```bash
export WEB_MODE=1

python3 -c "
from examples.finance_formatter import format_financial_report
output = format_financial_report({'quotes': [{'symbol': 'TEST', 'price': 100}]})
print('ANSI codes present:', chr(27) in output)
print('Asterisks present:', '*' in output)
print('Underscores present:', '_' in output)
"
```

Expected output:

```
ANSI codes present: False
Asterisks present: False
Underscores present: False
```

## Support

For issues or questions about output formatting, check:

- `examples/finance_formatter.py` – Core formatting logic
- `examples/gemini_agent.py` – Integration with Gemini agent
- `FRONTEND_INTEGRATION.md` – This file
