import React, { useState, useRef, useEffect } from "react";
import { AnimatedAIChat } from "../components/ui/animated-ai-chat";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { mcpApi, ChatResponse, MultiAgentAnalysisData } from "../services/api";
import { useNavigate } from "react-router-dom";
import { StructuredAnalysisMessage } from "../components/analysis";
import StreamingAnalysis from "../components/StreamingAnalysis";
import { motion } from "framer-motion";

// Match "analyze NVDA", "NVDA analysis", "analyse TSMC", "AAPL supply chain risk", etc.
const ANALYSIS_RE = /\b(analyz[es]?|analyse[s]?)\s+([A-Z]{1,5})\b|\b([A-Z]{1,5})\s+(analysis|supply.?chain|risk|thesis)\b/i;
const COMMON_WORDS = new Set(["WHAT", "WILL", "THE", "AND", "WITH", "ON", "IS", "TO", "OF", "DUE", "FOR", "HOW", "CAN", "ARE"]);

function detectAnalysisTrigger(text: string): { ticker: string; query: string } | null {
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
}

const SUGGESTED_PROMPTS = [
  "Which companies depend on TSMC?",
  "Impact of oil supply disruption?",
  "Show Tesla stock price",
];

const ChatPage: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Add welcome message on mount
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

  const handleSendMessage = async (content: string) => {
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

    const analysisTrigger = detectAnalysisTrigger(content.trim());

    if (analysisTrigger) {
      // Insert a placeholder streaming message; StreamingAnalysis will populate it
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
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Network error occurred";
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: `Error: ${message}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleStreamDone = (id: string, result: MultiAgentAnalysisData) => {
    // Convert the streaming placeholder to a normal assistant message so the
    // verdict persists after StreamingAnalysis unmounts.
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, streaming: undefined, content: JSON.stringify(result) } : m
      )
    );
  };

  const handleStreamError = (id: string, msg: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id
          ? { ...m, streaming: undefined, content: `Error: ${msg}` }
          : m
      )
    );
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
      transition={{ duration: 0.4 }}
      className="min-h-screen text-white bg-[linear-gradient(180deg,#000000_0%,#04070f_56%,#0A0F1C_100%)]"
    >
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(74,112,169,0.1),transparent)]" />

      <header className="sticky top-0 z-40 border-b border-white/5 bg-[#0a0a0f]/95 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-4xl items-center justify-between px-6">
          <div>
            <h1 className="text-base font-semibold tracking-tight">
              QuantVex Intelligence
            </h1>
            <p className="text-xs text-neutral-400">
              Real-time market and supply chain analysis.
            </p>
          </div>
          <button
            onClick={() => navigate("/")}
            className="rounded-xl border border-white/10 bg-[#0f62fe]/10 text-[#6ea6ff] px-4 py-2 text-sm font-medium transition hover:bg-[#0f62fe]/20 hover:text-white duration-200"
          >
            ← Home
          </button>
        </div>
      </header>

      <main className="relative z-10 mx-auto flex max-w-4xl flex-col px-6 py-12">
        <div className="space-y-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-4 opacity-0 animate-[fadeUp_0.35s_ease_forwards] ${
                message.role === "user" ? "flex-row-reverse" : "flex-row"
              }`}
            >
              {message.id !== "welcome" && (
                <div
                  className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full ${
                    message.role === "user"
                      ? "bg-[#4A70A9]/30 border border-[#4A70A9]/40"
                      : "border border-white/20 bg-white/10"
                  }`}
                >
                  {message.role === "user" ? (
                    <User className="h-5 w-5 text-white" />
                  ) : (
                    <Bot className="h-5 w-5 text-[#8FABD4]" />
                  )}
                </div>
              )}
              <div
                className={`flex-1 ${
                  message.role === "user" ? "text-right" : "text-left"
                }`}
              >
                {message.id === "welcome" ? (
                  <div className="inline-block w-full rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-lg text-left">
                    <h2 className="text-xl font-semibold tracking-tight text-white">
                      QuantVex Intelligence
                    </h2>
                    <p className="mt-2 text-base leading-relaxed text-neutral-300">
                      Analyze markets using real-time data and supply chain
                      reasoning.
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {SUGGESTED_PROMPTS.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => handleSendMessage(prompt)}
                          className="rounded-full bg-white/5 px-4 py-2 text-sm text-neutral-300 transition hover:bg-white/10"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <>
                    {message.streaming ? (
                      <StreamingAnalysis
                        ticker={message.streaming.ticker}
                        query={message.streaming.query}
                        onDone={(result) => handleStreamDone(message.id, result)}
                        onError={(err) => handleStreamError(message.id, err)}
                      />
                    ) : (
                      <div
                        className={`inline-block max-w-[85%] rounded-2xl p-5 text-sm leading-7 ${
                          message.role === "user"
                            ? "border border-[#4A70A9]/30 bg-[#4A70A9]/20 text-white"
                            : message.content.startsWith("Error:")
                              ? "border border-red-500/20 bg-red-500/10 text-red-100"
                              : "border border-white/10 bg-white/5 text-neutral-200 backdrop-blur-lg"
                        }`}
                      >
                        {message.role === "assistant" &&
                        !message.content.startsWith("Error:") ? (
                          <StructuredAnalysisMessage content={message.content} />
                        ) : message.content.startsWith("Error:") ? (
                          <p className="whitespace-pre-wrap">
                            Something went wrong. Please try again.
                          </p>
                        ) : (
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        )}
                      </div>
                    )}
                    {!message.streaming && (
                      <p className="mt-2 text-xs text-neutral-500">
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex gap-4 opacity-0 animate-[fadeUp_0.35s_ease_forwards]">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5">
                <Bot className="h-5 w-5 text-[#8FABD4]" />
              </div>
              <div className="inline-flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-5 py-4 text-sm text-neutral-300 backdrop-blur-lg">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>AI is analyzing...</span>
                <span className="typing-dots" aria-hidden="true">
                  <span>.</span>
                  <span>.</span>
                  <span>.</span>
                </span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="mt-10">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.currentTarget);
              const message = formData.get("message") as string;
              if (message) {
                handleSendMessage(message);
                e.currentTarget.reset();
              }
            }}
            className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl focus-within:border-[#8FABD4]/50 focus-within:shadow-[0_0_0_1px_rgba(143,171,212,0.35),0_0_28px_rgba(74,112,169,0.25)]"
          >
            <input
              type="text"
              name="message"
              placeholder="Ask Finance MCP about markets, companies, or global events..."
              disabled={loading}
              className="w-full rounded-xl border border-transparent bg-transparent px-4 py-3 text-sm text-white placeholder:text-neutral-500 focus:outline-none disabled:opacity-50"
            />
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={loading}
                className="flex items-center gap-2 rounded-xl bg-[linear-gradient(90deg,#4A70A9,#8FABD4)] px-5 py-2.5 text-sm font-medium text-white transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    <span>Send</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </main>
    </motion.div>
  );
};

export default ChatPage;
