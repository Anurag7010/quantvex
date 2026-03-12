import React, { useState, useRef, useEffect } from "react";
import { AnimatedAIChat } from "../components/ui/animated-ai-chat";
import { Send, Bot, User, Loader2, ArrowRight } from "lucide-react";
import { mcpApi, ChatResponse } from "../services/api";
import { useNavigate } from "react-router-dom";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

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
            "Hello, I'm the Finance MCP intelligence agent.\n\nI can help analyze financial markets, track supply-chain risks, and interpret global events using real-time market data.\n\nAsk questions like:\n• What companies depend on TSMC?\n• Which stocks are exposed to oil supply disruptions?\n• How could semiconductor shortages affect tech companies?\n• What is the current price of Tesla?",
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
    } catch (error: any) {
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: `Error: ${error.message || "Network error occurred"}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  if (!showChat) {
    return (
      <div className="min-h-screen relative overflow-hidden bg-[radial-gradient(circle_at_top,#263b5e_0%,#17253d_35%,#111b2f_100%)]">
        <div className="absolute top-5 left-5 z-20">
          <button
            onClick={() => navigate("/")}
            className="rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-sm text-white/90 backdrop-blur-xl transition hover:bg-white/15"
          >
            Back to Home
          </button>
        </div>
        <AnimatedAIChat onSendMessage={handleSendMessage} isTyping={loading} />
      </div>
    );
  }

  return (
    <div className="min-h-screen text-white bg-[linear-gradient(180deg,#22385b_0%,#172842_45%,#101c31_100%)]">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#1c2d48]/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1100px] items-center justify-between px-6 py-5">
          <div>
            <h1 className="text-[20px] font-semibold">
              Finance MCP Intelligence
            </h1>
            <p className="text-[13px] text-white/70">
              AI-powered market analysis using real-time financial data and
              supply-chain reasoning.
            </p>
          </div>
          <button
            onClick={() => navigate("/dashboard")}
            className="rounded-xl bg-[#4A70A9] px-4 py-2 text-sm font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5"
          >
            Open Dashboard
          </button>
        </div>
      </header>

      <main className="mx-auto flex max-w-[1100px] flex-col px-6 py-10">
        <div className="space-y-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`fade-up flex gap-4 ${
                message.role === "user" ? "flex-row-reverse" : "flex-row"
              }`}
            >
              <div
                className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full ${
                  message.role === "user"
                    ? "bg-[#4A70A9]"
                    : "border border-white/20 bg-white/10"
                }`}
              >
                {message.role === "user" ? (
                  <User className="h-5 w-5 text-white" />
                ) : (
                  <Bot className="h-5 w-5 text-[#8FABD4]" />
                )}
              </div>
              <div
                className={`flex-1 ${
                  message.role === "user" ? "text-right" : "text-left"
                }`}
              >
                <div
                  className={`inline-block max-w-[720px] rounded-2xl px-5 py-4 text-sm leading-6 ${
                    message.role === "user"
                      ? "bg-[#4A70A9] text-white"
                      : "fin-panel text-white/90"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>
                <p className="mt-2 text-xs text-white/50">
                  {message.timestamp.toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))}

          {loading && (
            <div className="fade-up flex gap-4">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5">
                <Bot className="h-5 w-5 text-[#8FABD4]" />
              </div>
              <div className="fin-panel inline-flex items-center gap-3 px-4 py-3 text-sm text-white/80">
                <Loader2 className="h-4 w-4 animate-spin" />
                Finance MCP is analyzing market data
                <span className="flex gap-1">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/60" />
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/60 [animation-delay:0.2s]" />
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/60 [animation-delay:0.4s]" />
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
            className="fin-panel flex flex-col gap-3 p-4"
          >
            <input
              type="text"
              name="message"
              placeholder="Ask Finance MCP about markets, companies, or global events..."
              disabled={loading}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-[#4A70A9] disabled:opacity-50"
            />
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={loading}
                className="flex items-center gap-2 rounded-xl bg-[#4A70A9] px-5 py-2.5 text-sm font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    <span>Send</span>
                  </>
                )}
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
};

export default ChatPage;
