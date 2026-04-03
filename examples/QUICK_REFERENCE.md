# Quick Reference: Frontend Output Format

## TL;DR

Your React component receives clean, structured plain text. Render it as-is in a monospace font with `whitespace-pre-wrap`.

```tsx
<p className="whitespace-pre-wrap font-mono">{response}</p>
```

## Output Guarantees

| Aspect           | Value                    |
| ---------------- | ------------------------ |
| Markdown Symbols | None ❌                  |
| ANSI Codes       | None ❌                  |
| Currency Format  | ₹ with commas            |
| Bullet Style     | • (U+2022)               |
| Line Breaks      | Preserved ✓              |
| Sections         | Separated by blank lines |

## Single Asset Example

```
MARKET SUMMARY

AAPL is trading above the previous close, reflecting positive intraday momentum.

...
```

**What the component receives**: A plain string with `\n` line breaks.

**What it renders**: Professional financial report with proper spacing.

## Multiple Assets Example

```
MARKET COMPARISON

Asset        Price (₹)      Change        Volume
----------------------------------------------------------------
AAPL               ₹14,325.20 ₹+115.05 (+0.81%)        52M
MSFT               ₹37,856.10 ₹-298.40 (-0.79%)        28M
```

**Key**: Text aligns using monospace font. Use `font-mono` in Tailwind.

## Environment Variables (Backend)

Set these on the MCP server / backend service:

```bash
export WEB_MODE=1                    # Always for web
export ENABLE_BOLD_FORMATTING=0      # No terminal codes
export PROFESSIONAL_OUTPUT=true      # Always use formatter
```

Default behavior: Web-safe output, no action needed.

## Validation

Run this test script to verify your backend is configured correctly:

```bash
python3 test_frontend_integration.py
```

Expected result:

```
✅ ALL TESTS PASSED - READY FOR FRONTEND
```

## If You See Problems

| Problem             | Cause                      | Fix                               |
| ------------------- | -------------------------- | --------------------------------- |
| Asterisks in output | Markdown escaping issue    | Check `WEB_MODE=1`                |
| ANSI codes visible  | Terminal codes in web mode | Set `ENABLE_BOLD_FORMATTING=0`    |
| Messy formatting    | Fallback text used         | Ensure `PROFESSIONAL_OUTPUT=true` |
| Table misaligned    | Not using monospace font   | Add `font-mono` to component      |

## React Component Template

```tsx
import { ChatMessage } from "@/types";

export function ChatBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="mb-4">
      <div
        className={`rounded-lg p-4 ${
          message.role === "user" ? "bg-blue-100 ml-auto" : "bg-gray-100"
        }`}
        style={{ maxWidth: "80%" }}
      >
        <p className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
          {message.content}
        </p>
      </div>
    </div>
  );
}
```

## API Response Format

MCP `/chat` endpoint returns:

```json
{
  "response": "MARKET SUMMARY\n\nAAPL is trading...",
  "status": "success"
}
```

The `response` field is plain text. Pass it directly to your component.

## Testing Locally

```bash
# Backend CLI (with terminal formatting)
export WEB_MODE=0 ENABLE_BOLD_FORMATTING=1
python3 examples/gemini_agent.py

# Run verification
python3 test_frontend_integration.py
```

Both should show clean, professional output.
