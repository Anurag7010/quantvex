import React, { useState, useRef, useEffect, useCallback } from "react";
import { AnimatedAIChat } from "../components/ui/animated-ai-chat";
import { Send, Bot, User, Zap } from "lucide-react";
import { mcpApi, ChatResponse, MultiAgentAnalysisData } from "../services/api";
import { useNavigate } from "react-router-dom";
import { StructuredAnalysisMessage } from "../components/analysis";
import StreamingAnalysis from "../components/StreamingAnalysis";
import TypewriterMessage from "../components/TypewriterMessage";
import { motion } from "framer-motion";

const ANALYSIS_RE =
  /\b(analyz[es]?|analyse[s]?)\s+([A-Z]{1,5})\b|\b([A-Z]{1,5})\s+(analysis|supply.?chain|risk|thesis)\b/i;
const COMMON_WORDS = new Set([
  "WHAT",
  "WILL",
  "THE",
  "AND",
  "WITH",
  "ON",
  "IS",
  "TO",
  "OF",
  "DUE",
  "FOR",
  "HOW",
  "CAN",
  "ARE",
]);

function detectAnalysisTrigger(
  text: string,
): { ticker: string; query: string } | null {
  const m = ANALYSIS_RE.exec(text);
  if (!m) return null;
  const ticker = (m[2] || m[3] || "").toUpperCase();
  if (!ticker || COMMON_WORDS.has(ticker)) return null;
  return { ticker, query: text.trim() };
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  streaming?: { ticker: string; query: string };
  typewrite?: boolean;
}

const SUGGESTED_PROMPTS = [
  "Analyze NVDA",
  "Which companies depend on TSMC?",
  "Impact of US chip export ban on semiconductors?",
  "Current price of AAPL?",
];

const ThinkingIndicator: React.FC = () => (
  <div className="flex gap-4 animate-[fadeUp_0.25s_ease_forwards]">
    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border border-[#4A70A9]/40 bg-[#4A70A9]/10">
      <Bot className="h-5 w-5 text-[#8FABD4]" />
    </div>
    <div className="inline-flex items-center gap-1.5 rounded-2xl border border-white/8 bg-white/4 px-5 py-4 backdrop-blur-lg">
      <span className="thinking-dot" />
      <span className="thinking-dot" style={{ animationDelay: "0.18s" }} />
      <span className="thinking-dot" style={{ animationDelay: "0.36s" }} />
    </div>
  </div>
);

const ChatPage: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [showChat, setShowChat] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content:
            "Hello, I'm the QuantVex intelligence agent.\n\nI can help analyze financial markets, track supply-chain risks, and interpret global events using real-time market data.\n\nAsk questions like:\n• What companies depend on TSMC?\n• Which stocks are exposed to oil supply disruptions?\n• How could semiconductor shortages affect tech companies?\n• What is the current price of Tesla?",
          timestamp: new Date(),
        },
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || loading) return;

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: content.trim(),
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setLoading(true);
      setShowChat(true);
      setInputValue("");

      const analysisTrigger = detectAnalysisTrigger(content.trim());

      if (analysisTrigger) {
        const streamingId = `streaming-${Date.now()}`;
        setMessages((prev) => [
          ...prev,
          {
            id: streamingId,
            role: "assistant",
            content: "",
            timestamp: new Date(),
            streaming: analysisTrigger,
          },
        ]);
        setLoading(false);
        return;
      }

      try {
        const response: ChatResponse = await mcpApi.chat(userMessage.content);

        if (response.success) {
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            content: response.response,
            timestamp: new Date(),
            typewrite: true,
          };
          setMessages((prev) => [...prev, assistantMessage]);
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: "assistant",
              content: `Error: ${response.error || "Failed to get response"}`,
              timestamp: new Date(),
            },
          ]);
        }
      } catch (error: unknown) {
        const msg =
          error instanceof Error ? error.message : "Network error occurred";
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: `Error: ${msg}`,
            timestamp: new Date(),
          },
        ]);
      } finally {
        setLoading(false);
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    },
    [loading],
  );

  const handleStreamDone = (id: string, result: MultiAgentAnalysisData) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id
          ? { ...m, streaming: undefined, content: JSON.stringify(result) }
          : m,
      ),
    );
  };

  const handleStreamError = (id: string, msg: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id
          ? { ...m, streaming: undefined, content: `Error: ${msg}` }
          : m,
      ),
    );
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) handleSendMessage(inputValue);
  };

  if (!showChat) {
    return (
      <div className="relative min-h-screen overflow-hidden bg-[linear-gradient(180deg,#000000_0%,#04070f_56%,#0A0F1C_100%)]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(74,112,169,0.1),transparent)]" />
        <div className="absolute top-5 left-5 z-20">
          <button
            onClick={() => navigate("/")}
            className="rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-sm text-white/90 backdrop-blur-xl transition hover:scale-[1.02] hover:bg-white/15"
          >
            Back to Home
          </button>
        </div>
        <div className="relative z-10">
          <AnimatedAIChat
            onSendMessage={handleSendMessage}
            isTyping={loading}
          />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      className="min-h-screen text-white bg-[linear-gradient(180deg,#000000_0%,#04070f_56%,#0A0F1C_100%)]"
    >
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(74,112,169,0.08),transparent)]" />

      {/* ── Header ── */}
      <header className="sticky top-0 z-40 border-b border-white/5 bg-[#040408]/90 backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-full max-w-4xl items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#4A70A9]/40 bg-[#4A70A9]/15">
              <Zap className="h-4 w-4 text-[#8FABD4]" />
            </div>
            <div>
              <h1 className="text-sm font-semibold tracking-tight text-white">
                QuantVex Intelligence
              </h1>
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <p className="text-[11px] text-neutral-500">
                  Live · Real-time market analysis
                </p>
              </div>
            </div>
          </div>
          <button
            onClick={() => navigate("/")}
            className="rounded-lg border border-white/10 bg-white/4 px-4 py-1.5 text-xs font-medium text-neutral-400 transition hover:border-white/20 hover:bg-white/8 hover:text-white duration-200"
          >
            ← Home
          </button>
        </div>
      </header>

      {/* ── Messages ── */}
      <main className="relative z-10 mx-auto flex max-w-4xl flex-col px-6 py-10">
        <div className="space-y-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-4 opacity-0 animate-[fadeUp_0.32s_ease_forwards] ${
                message.role === "user" ? "flex-row-reverse" : "flex-row"
              }`}
            >
              {message.id !== "welcome" && (
                <div
                  className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full ${
                    message.role === "user"
                      ? "border border-[#4A70A9]/40 bg-[#4A70A9]/20"
                      : "border border-white/10 bg-white/5"
                  }`}
                >
                  {message.role === "user" ? (
                    <User className="h-4 w-4 text-[#8FABD4]" />
                  ) : (
                    <Bot className="h-4 w-4 text-[#8FABD4]" />
                  )}
                </div>
              )}

              <div
                className={`flex-1 ${
                  message.role === "user" ? "text-right" : "text-left"
                }`}
              >
                {/* ── Welcome card ── */}
                {message.id === "welcome" ? (
                  <div className="w-full rounded-2xl border border-white/8 bg-white/3 p-6 backdrop-blur-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="flex h-7 w-7 items-center justify-center rounded-md border border-[#4A70A9]/40 bg-[#4A70A9]/15">
                        <Zap className="h-3.5 w-3.5 text-[#8FABD4]" />
                      </div>
                      <h2 className="text-base font-semibold tracking-tight text-white">
                        QuantVex Intelligence
                      </h2>
                    </div>
                    <p className="text-sm leading-relaxed text-neutral-400">
                      Analyze markets using real-time data and supply chain
                      reasoning.
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {SUGGESTED_PROMPTS.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => handleSendMessage(prompt)}
                          className="rounded-full border border-white/10 bg-white/4 px-4 py-1.5 text-xs text-neutral-400 transition hover:border-white/20 hover:bg-white/8 hover:text-white duration-200"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <>
                    {/* ── Streaming analysis (SSE) ── */}
                    {message.streaming ? (
                      <StreamingAnalysis
                        ticker={message.streaming.ticker}
                        query={message.streaming.query}
                        onDone={(result) =>
                          handleStreamDone(message.id, result)
                        }
                        onError={(err) => handleStreamError(message.id, err)}
                      />
                    ) : (
                      <div
                        className={`inline-block max-w-[88%] rounded-2xl p-5 text-sm leading-7 ${
                          message.role === "user"
                            ? "border border-[#4A70A9]/25 bg-[#4A70A9]/15 text-white"
                            : message.content.startsWith("Error:")
                              ? "border border-red-500/20 bg-red-900/10 text-red-200"
                              : "border border-white/8 bg-white/3 text-neutral-200 backdrop-blur-lg"
                        }`}
                      >
                        {message.role === "user" ? (
                          <p className="whitespace-pre-wrap">
                            {message.content}
                          </p>
                        ) : message.content.startsWith("Error:") ? (
                          <p className="whitespace-pre-wrap">
                            Something went wrong. Please try again.
                          </p>
                        ) : message.typewrite ? (
                          <TypewriterMessage content={message.content} />
                        ) : (
                          <StructuredAnalysisMessage
                            content={message.content}
                          />
                        )}
                      </div>
                    )}

                    {!message.streaming && (
                      <p className="mt-2 text-[11px] text-neutral-600">
                        {message.timestamp.toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {/* ── Thinking indicator ── */}
          {loading && <ThinkingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        {/* ── Input ── */}
        <div className="mt-10">
          <form
            onSubmit={handleFormSubmit}
            className="group flex flex-col gap-3 rounded-2xl border border-white/8 bg-white/3 p-4 backdrop-blur-xl transition-all duration-200 focus-within:border-[#8FABD4]/40 focus-within:shadow-[0_0_0_1px_rgba(143,171,212,0.2),0_0_32px_rgba(74,112,169,0.15)]"
          >
            <input
              ref={inputRef}
              type="text"
              name="message"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask about markets, companies, or global events…"
              disabled={loading}
              autoComplete="off"
              className="w-full bg-transparent px-2 py-1 text-sm text-white placeholder:text-neutral-600 focus:outline-none disabled:opacity-40"
            />
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-neutral-700">
                Press{" "}
                <kbd className="rounded border border-white/10 bg-white/5 px-1 py-0.5 font-mono text-[10px] text-neutral-500">
                  Enter
                </kbd>{" "}
                to send
              </p>
              <button
                type="submit"
                disabled={loading || !inputValue.trim()}
                className="flex items-center gap-2 rounded-xl bg-[linear-gradient(135deg,#4A70A9,#6A9AC9)] px-5 py-2 text-xs font-semibold text-white shadow-[0_4px_16px_rgba(74,112,169,0.35)] transition hover:scale-[1.02] hover:shadow-[0_4px_20px_rgba(74,112,169,0.5)] disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
              >
                <Send className="h-3.5 w-3.5" />
                Send
              </button>
            </div>
          </form>
        </div>
      </main>
    </motion.div>
  );
};

export default ChatPage;
