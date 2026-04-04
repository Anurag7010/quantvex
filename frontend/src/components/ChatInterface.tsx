import React, { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { mcpApi } from "../services/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

const formatInline = (text: string) => {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
};

const formatText = (text: string) => {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let idx = 0;
  let paragraphBuffer: string[] = [];
  let listBuffer: Array<{ content: string; level: number }> = [];

  const flushParagraph = () => {
    if (!paragraphBuffer.length) return;
    const content = paragraphBuffer.join(" ").trim();
    paragraphBuffer = [];
    if (!content) return;
    blocks.push(
      <p
        key={`p-${idx++}`}
        className="mb-3 text-sm leading-relaxed text-slate-100"
      >
        {formatInline(content)}
      </p>,
    );
  };

  const flushList = () => {
    if (!listBuffer.length) return;
    const items = listBuffer;
    listBuffer = [];
    blocks.push(
      <ul key={`ul-${idx++}`} className="mb-3 space-y-2">
        {items.map((item, i) => (
          <li
            key={`li-${idx}-${i}`}
            className="text-sm leading-relaxed text-slate-100"
            style={{ marginLeft: `${Math.min(item.level, 3) * 14}px` }}
          >
            <span className="mr-2 text-slate-300">•</span>
            {formatInline(item.content)}
          </li>
        ))}
      </ul>,
    );
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const headingMatch = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
    const bulletMatch = line.match(/^(\s*)[*-]\s+(.+)$/);

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      const headingText = headingMatch[2].trim();
      const classMap: Record<number, string> = {
        1: "text-2xl font-bold mt-4 mb-3 text-white",
        2: "text-xl font-bold mt-4 mb-3 text-white",
        3: "text-lg font-semibold mt-3 mb-2 text-white",
        4: "text-base font-semibold mt-3 mb-2 text-white",
        5: "text-sm font-semibold mt-2 mb-1 text-white",
        6: "text-sm font-semibold mt-2 mb-1 text-white",
      };
      const Tag = `h${Math.min(level, 6)}` as React.ElementType;
      blocks.push(
        <Tag key={`h-${idx++}`} className={classMap[Math.min(level, 6)]}>
          {formatInline(headingText)}
        </Tag>,
      );
      continue;
    }

    if (bulletMatch) {
      flushParagraph();
      const indentSpaces = bulletMatch[1].length;
      const level = Math.floor(indentSpaces / 2);
      listBuffer.push({ content: bulletMatch[2].trim(), level });
      continue;
    }

    flushList();
    paragraphBuffer.push(line.trim());
  }

  flushParagraph();
  flushList();

  return blocks;
};

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content:
            "Hello! I'm your financial AI assistant. I can help you with real-time stock prices, cryptocurrency data, and market analysis. Just ask me anything about financial markets.",
          timestamp: new Date(),
        },
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await mcpApi.chat(userMessage.content);

      if (response.success) {
        const assistantMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: response.response,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } else {
        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `Error: ${response.error || "Failed to get response"}`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    } catch (error: any) {
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: `Network error: ${error.message}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const suggestedQueries = [
    "What's the current price of Apple stock?",
    "How is Bitcoin performing today?",
    "Compare Microsoft and Google stock prices",
    "Show me Tesla's latest price",
  ];

  const handleSuggestionClick = (query: string) => {
    setInput(query);
    inputRef.current?.focus();
  };

  return (
    <div className="bg-slate-800 rounded-xl shadow-2xl border border-slate-700 flex flex-col h-[600px]">
      {/* Chat Header */}
      <div className="p-6 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary-600 rounded-lg">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">AI Assistant</h2>
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex gap-3 ${
              message.role === "user" ? "flex-row-reverse" : "flex-row"
            }`}
          >
            {/* Avatar */}
            <div
              className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                message.role === "user" ? "bg-primary-600" : "bg-slate-700"
              }`}
            >
              {message.role === "user" ? (
                <User className="w-4 h-4 text-white" />
              ) : (
                <Bot className="w-4 h-4 text-white" />
              )}
            </div>

            {/* Message Bubble */}
            <div
              className={`flex-1 max-w-[80%] ${
                message.role === "user" ? "text-right" : "text-left"
              }`}
            >
              <div
                className={`inline-block p-4 rounded-2xl ${
                  message.role === "user"
                    ? "bg-primary-600 text-white"
                    : "bg-slate-700 text-slate-100"
                }`}
              >
                {message.role === "user" ? (
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">
                    {message.content}
                  </p>
                ) : (
                  <div className="text-sm">{formatText(message.content)}</div>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1 px-2">
                {message.timestamp.toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="flex gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <div className="bg-slate-700 p-4 rounded-2xl">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Queries (show only when no messages) */}
      {messages.length === 1 && !loading && (
        <div className="px-6 pb-4">
          <p className="text-xs text-slate-400 mb-2">Try asking:</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {suggestedQueries.map((query, index) => (
              <button
                key={index}
                onClick={() => handleSuggestionClick(query)}
                className="text-left p-3 bg-slate-700/50 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition-colors duration-200"
              >
                {query}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-6 border-t border-slate-700">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about stocks, crypto, or market data..."
            disabled={loading}
            className="flex-1 px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors duration-200 flex items-center gap-2"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatInterface;
