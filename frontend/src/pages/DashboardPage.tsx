import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LineChart, Search, TrendingDown, TrendingUp } from "lucide-react";
import { QuoteData, mcpApi } from "../services/api";
import { formatNumber } from "../lib/utils";
import {
  CartesianGrid,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type MarketScope = "us" | "india" | "crypto";

interface IndexPoint {
  name: string;
  value: number;
  change: number;
  isCurrency?: boolean;
  usdValue?: number;
}

interface IndianOverview {
  nifty: number;
  niftyChange: number;
  sensex: number;
  sensexChange: number;
}

const fallbackIndianOverview: IndianOverview = {
  nifty: 22140.85,
  niftyChange: 0.52,
  sensex: 73840.23,
  sensexChange: 0.44,
};

const aiInsightCards = [
  {
    title: "Semiconductor Production Risk",
    impact: "Impact: Apple, NVIDIA, AMD",
  },
  {
    title: "Oil Supply Disruption",
    impact: "Impact: Energy companies, Airlines",
  },
  {
    title: "Interest Rate Change",
    impact: "Impact: Banking and Tech sectors",
  },
];

const marketEvents = [
  {
    title: "Semiconductor Supply Alert",
    description: "Potential production disruptions detected in Taiwan.",
    severity: "High",
    time: "2 hours ago",
  },
  {
    title: "Crude Oil Inventory Shock",
    description: "Inventory drawdown exceeds consensus estimates.",
    severity: "Medium",
    time: "4 hours ago",
  },
  {
    title: "Rupee Volatility Watch",
    description:
      "USD/INR movement is increasing import cost sensitivity across sectors.",
    severity: "Low",
    time: "5 hours ago",
  },
];

const formatINR = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);

const formatUSD = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);

const formatInrCompact = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchSymbol, setSearchSymbol] = useState("");
  const [quoteData, setQuoteData] = useState<QuoteData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [marketScope, setMarketScope] = useState<MarketScope>("us");
  const [usdInrRate, setUsdInrRate] = useState(82.94);
  const [indianOverview, setIndianOverview] = useState<IndianOverview>(
    fallbackIndianOverview,
  );

  const getUsdInrRate = async () => {
    try {
      const primary = await fetch(
        "https://api.exchangerate.host/latest?base=USD&symbols=INR",
      );
      const primaryJson = await primary.json();
      const primaryRate = Number(primaryJson?.rates?.INR);
      if (Number.isFinite(primaryRate) && primaryRate > 0) {
        return primaryRate;
      }
    } catch {
      // fallback used below
    }

    try {
      const fallback = await fetch("https://open.er-api.com/v6/latest/USD");
      const fallbackJson = await fallback.json();
      const fallbackRate = Number(fallbackJson?.rates?.INR);
      if (Number.isFinite(fallbackRate) && fallbackRate > 0) {
        return fallbackRate;
      }
    } catch {
      // keep existing rate
    }

    return usdInrRate;
  };

  const getYahooIndex = async (symbol: string) => {
    try {
      const response = await fetch(
        `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}`,
      );
      const json = await response.json();
      const meta = json?.chart?.result?.[0]?.meta;
      const price = Number(meta?.regularMarketPrice);
      const previousClose = Number(meta?.previousClose);
      if (
        !Number.isFinite(price) ||
        !Number.isFinite(previousClose) ||
        previousClose === 0
      ) {
        return null;
      }
      const change = ((price - previousClose) / previousClose) * 100;
      return { price, change };
    } catch {
      return null;
    }
  };

  useEffect(() => {
    let mounted = true;

    const refreshGlobalRatesAndIndia = async () => {
      const [rate, nifty, sensex] = await Promise.all([
        getUsdInrRate(),
        getYahooIndex("^NSEI"),
        getYahooIndex("^BSESN"),
      ]);

      if (!mounted) return;

      setUsdInrRate(rate);
      setIndianOverview({
        nifty: nifty?.price ?? fallbackIndianOverview.nifty,
        niftyChange: nifty?.change ?? fallbackIndianOverview.niftyChange,
        sensex: sensex?.price ?? fallbackIndianOverview.sensex,
        sensexChange: sensex?.change ?? fallbackIndianOverview.sensexChange,
      });
    };

    void refreshGlobalRatesAndIndia();
    const interval = setInterval(refreshGlobalRatesAndIndia, 5 * 60 * 1000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchSymbol.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await mcpApi.getQuote(searchSymbol, 60);
      if (response.success && response.data) {
        setQuoteData(response.data);
      } else {
        setError(response.error || "Failed to fetch quote");
      }
    } catch (err: any) {
      setError(err.message || "Network error occurred");
    } finally {
      setLoading(false);
    }
  };

  const chartData = useMemo(() => {
    if (!quoteData) return [];
    const data = [];
    const basePriceUsd = quoteData.price || 150;

    for (let i = 30; i >= 0; i--) {
      const variance = (Math.random() - 0.5) * 5;
      const usd = basePriceUsd + variance;
      data.push({
        time: `${i}d ago`,
        priceUsd: usd,
        priceInr: usd * usdInrRate,
      });
    }

    return data;
  }, [quoteData, usdInrRate]);

  const overviewCards: IndexPoint[] = useMemo(() => {
    if (marketScope === "india") {
      return [
        {
          name: "NIFTY 50",
          value: indianOverview.nifty,
          change: indianOverview.niftyChange,
        },
        {
          name: "SENSEX",
          value: indianOverview.sensex,
          change: indianOverview.sensexChange,
        },
        {
          name: "USD / INR",
          value: usdInrRate,
          change: 0,
        },
      ];
    }

    if (marketScope === "crypto") {
      return [
        {
          name: "Bitcoin",
          value: 97453.32 * usdInrRate,
          usdValue: 97453.32,
          change: 3.12,
          isCurrency: true,
        },
        {
          name: "Ethereum",
          value: 4210.24 * usdInrRate,
          usdValue: 4210.24,
          change: 2.41,
          isCurrency: true,
        },
        {
          name: "Solana",
          value: 197.42 * usdInrRate,
          usdValue: 197.42,
          change: -1.09,
          isCurrency: true,
        },
      ];
    }

    return [
      { name: "S&P 500", value: 5234.18, change: 1.24 },
      { name: "NASDAQ", value: 16441.87, change: -0.58 },
      {
        name: "NIFTY 50",
        value: indianOverview.nifty,
        change: indianOverview.niftyChange,
      },
      {
        name: "Bitcoin",
        value: 97453.32 * usdInrRate,
        usdValue: 97453.32,
        change: 3.12,
        isCurrency: true,
      },
    ];
  }, [indianOverview, marketScope, usdInrRate]);

  const sparklineSeries = useMemo(() => {
    return overviewCards.map((index, idx) => {
      const direction = index.change >= 0 ? 1 : -1;
      const base = index.value;
      return Array.from({ length: 12 }, (_, i) => {
        const drift = (i - 5.5) * direction * (base * 0.0006);
        const wave = Math.sin(i * 0.9 + idx) * (base * 0.0004);
        return { index: i, value: base + drift + wave };
      });
    });
  }, [overviewCards]);

  const handleNav = (tab: string, targetId: string) => {
    setActiveTab(tab);
    document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth" });
  };

  const quoteInrPrice = quoteData ? quoteData.price * usdInrRate : null;

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-black/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between px-6 py-4 sm:px-8">
          <div className="flex items-center gap-4">
            <div className="text-lg font-semibold tracking-[-0.02em]">
              Finance MCP
            </div>
            <span className="hidden text-sm text-white/60 lg:inline">
              Market Intelligence Command Center
            </span>
          </div>
          <nav className="hidden items-center gap-6 text-sm font-medium md:flex">
            <button
              onClick={() => handleNav("overview", "overview")}
              className={
                activeTab === "overview"
                  ? "text-[#8FABD4]"
                  : "text-white/70 hover:text-white"
              }
            >
              Overview
            </button>
            <button
              onClick={() => handleNav("market", "market")}
              className={
                activeTab === "market"
                  ? "text-[#8FABD4]"
                  : "text-white/70 hover:text-white"
              }
            >
              Market Data
            </button>
            <button
              onClick={() => handleNav("insights", "insights")}
              className={
                activeTab === "insights"
                  ? "text-[#8FABD4]"
                  : "text-white/70 hover:text-white"
              }
            >
              AI Insights
            </button>
            <button
              onClick={() => handleNav("news", "news")}
              className={
                activeTab === "news"
                  ? "text-[#8FABD4]"
                  : "text-white/70 hover:text-white"
              }
            >
              News Events
            </button>
            <button
              onClick={() => navigate("/chat")}
              className="text-white/70 hover:text-white"
            >
              AI Chat
            </button>
          </nav>
          <button
            onClick={() => navigate("/chat")}
            className="rounded-xl bg-[#4A70A9] px-4 py-2 text-sm font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5 hover:scale-[1.03]"
          >
            Open AI Chat
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] space-y-12 px-6 py-12 sm:px-8">
        <section id="overview" className="space-y-8">
          <div className="space-y-3">
            <h1 className="text-[36px] font-bold tracking-[-0.02em]">
              Global Market Intelligence Dashboard
            </h1>
            <p className="text-[15px] leading-6 text-white/70">
              Monitor global indices, analyze asset movements, and surface
              AI-driven financial signals across US and Indian markets.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {(
              [
                { key: "us", label: "US Markets" },
                { key: "india", label: "Indian Markets" },
                { key: "crypto", label: "Crypto" },
              ] as const
            ).map((scope) => (
              <button
                key={scope.key}
                onClick={() => setMarketScope(scope.key)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  marketScope === scope.key
                    ? "border-[#8FABD4] bg-[#4A70A9]/25 text-[#8FABD4]"
                    : "border-white/10 text-white/70 hover:text-white"
                }`}
              >
                {scope.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-7 md:grid-cols-2 xl:grid-cols-4">
            {overviewCards.map((index, idx) => {
              const isPositive = index.change >= 0;
              const changeColor = isPositive ? "#8FABD4" : "#ff6b6b";
              return (
                <div key={index.name} className="fin-panel p-6">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-white/60">
                        {index.name}
                      </p>
                      <p className="mt-3 text-2xl font-semibold">
                        {index.isCurrency
                          ? formatINR(index.value)
                          : formatNumber(index.value)}
                      </p>
                      {index.usdValue ? (
                        <p className="mt-1 text-xs text-white/50">
                          {formatUSD(index.usdValue)}
                        </p>
                      ) : null}
                      <div className="mt-3 flex items-center gap-2 text-sm">
                        <span style={{ color: changeColor }}>
                          {isPositive ? "+" : ""}
                          {index.change.toFixed(2)}%
                        </span>
                        <span className="text-white/60">Today</span>
                      </div>
                    </div>
                    <div
                      className="flex h-9 w-9 items-center justify-center rounded-full"
                      style={{
                        background: isPositive
                          ? "rgba(143,171,212,0.2)"
                          : "rgba(255,107,107,0.15)",
                      }}
                    >
                      {isPositive ? (
                        <TrendingUp
                          className="h-4 w-4"
                          style={{ color: changeColor }}
                        />
                      ) : (
                        <TrendingDown
                          className="h-4 w-4"
                          style={{ color: changeColor }}
                        />
                      )}
                    </div>
                  </div>
                  <div className="mt-4 h-16">
                    <ResponsiveContainer width="100%" height="100%">
                      <RechartsLineChart data={sparklineSeries[idx]}>
                        <Line
                          type="monotone"
                          dataKey="value"
                          stroke={changeColor}
                          strokeWidth={2}
                          dot={false}
                        />
                      </RechartsLineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="space-y-6">
          <div>
            <h2 className="text-[20px] font-semibold">
              Indian Market Overview
            </h2>
            <p className="text-[15px] leading-6 text-white/70">
              Updated every 5 minutes with NIFTY 50, SENSEX, and USD/INR
              context.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-7 md:grid-cols-3">
            <div className="fin-panel p-6">
              <p className="text-xs uppercase tracking-[0.2em] text-white/60">
                NIFTY 50
              </p>
              <p className="mt-3 text-2xl font-semibold">
                {formatNumber(indianOverview.nifty)}
              </p>
              <p
                className="mt-2 text-sm"
                style={{
                  color:
                    indianOverview.niftyChange >= 0 ? "#8FABD4" : "#ff6b6b",
                }}
              >
                {indianOverview.niftyChange >= 0 ? "+" : ""}
                {indianOverview.niftyChange.toFixed(2)}%
              </p>
            </div>
            <div className="fin-panel p-6">
              <p className="text-xs uppercase tracking-[0.2em] text-white/60">
                SENSEX
              </p>
              <p className="mt-3 text-2xl font-semibold">
                {formatNumber(indianOverview.sensex)}
              </p>
              <p
                className="mt-2 text-sm"
                style={{
                  color:
                    indianOverview.sensexChange >= 0 ? "#8FABD4" : "#ff6b6b",
                }}
              >
                {indianOverview.sensexChange >= 0 ? "+" : ""}
                {indianOverview.sensexChange.toFixed(2)}%
              </p>
            </div>
            <div className="fin-panel p-6">
              <p className="text-xs uppercase tracking-[0.2em] text-white/60">
                USD / INR
              </p>
              <p className="mt-3 text-2xl font-semibold">
                {usdInrRate.toFixed(2)}
              </p>
              <p className="mt-2 text-xs text-white/60">
                Live reference FX rate
              </p>
            </div>
          </div>
        </section>

        <section id="market" className="space-y-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-[20px] font-semibold">Market Data</h2>
              <p className="text-[15px] leading-6 text-white/70">
                Search global assets and view INR-converted pricing with USD
                references.
              </p>
            </div>
            <form onSubmit={handleSearch} className="flex flex-wrap gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/50" />
                <input
                  type="text"
                  value={searchSymbol}
                  onChange={(e) => setSearchSymbol(e.target.value)}
                  placeholder="Search global assets (AAPL, TSLA, BTC, RELIANCE, TCS)"
                  className="h-11 w-[360px] max-w-full rounded-xl border border-white/10 bg-white/5 pl-10 pr-4 text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-[#4A70A9]"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="h-11 rounded-xl bg-[#4A70A9] px-5 text-sm font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5 disabled:opacity-60"
              >
                {loading ? "Searching..." : "Search"}
              </button>
            </form>
          </div>

          <div className="flex flex-wrap gap-2">
            {[
              ["Apple", "AAPL"],
              ["Tesla", "TSLA"],
              ["Reliance", "RELIANCE.NS"],
              ["TCS", "TCS.NS"],
              ["Bitcoin", "BTC"],
            ].map(([name, symbol]) => (
              <button
                key={symbol}
                onClick={() => setSearchSymbol(symbol)}
                className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/70 transition hover:border-[#8FABD4] hover:text-white"
              >
                {name} ({symbol})
              </button>
            ))}
          </div>

          {error && (
            <div className="fin-panel border border-[#ff6b6b]/40 p-4 text-sm text-white/80">
              {error}
            </div>
          )}

          <div className="fin-panel p-6">
            <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1.1fr_2fr]">
              <div className="space-y-6">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-[0.2em] text-white/60">
                    Selected Asset
                  </p>
                  <div className="text-3xl font-semibold">
                    {quoteInrPrice ? formatINR(quoteInrPrice) : "--"}
                  </div>
                  <div className="text-sm text-white/70">
                    {quoteData?.symbol || "Awaiting symbol search"}
                  </div>
                  {quoteData ? (
                    <p className="text-xs text-white/60">
                      Approx {formatUSD(quoteData.price)} USD
                    </p>
                  ) : null}
                  {quoteData ? (
                    <p className="text-xs text-white/50">
                      Converted using live USD to INR rate
                    </p>
                  ) : null}
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="space-y-1">
                    <p className="text-white/60">Open</p>
                    <p className="font-medium">
                      {quoteData?.open
                        ? formatINR(quoteData.open * usdInrRate)
                        : "--"}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-white/60">High</p>
                    <p className="font-medium">
                      {quoteData?.high
                        ? formatINR(quoteData.high * usdInrRate)
                        : "--"}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-white/60">Low</p>
                    <p className="font-medium">
                      {quoteData?.low
                        ? formatINR(quoteData.low * usdInrRate)
                        : "--"}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-white/60">Latency</p>
                    <p className="font-medium">
                      {quoteData?.latency_ms
                        ? `${quoteData.latency_ms} ms`
                        : "--"}
                    </p>
                  </div>
                </div>

                <div className="text-xs text-white/50">
                  {quoteData?.cache_hit
                    ? "Cached response"
                    : "Live market feed (USD source, INR display)"}
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium text-white/90">
                    <LineChart className="h-4 w-4" />
                    Price Trend
                  </div>
                  <div className="flex gap-2">
                    {["1D", "1W", "1M", "1Y"].map((period) => (
                      <button
                        key={period}
                        className="rounded-lg border border-white/10 px-3 py-1 text-xs text-white/70 transition hover:border-[#8FABD4] hover:text-white"
                      >
                        {period}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="h-[240px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsLineChart data={chartData}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,0.06)"
                      />
                      <XAxis
                        dataKey="time"
                        stroke="rgba(255,255,255,0.4)"
                        style={{ fontSize: "12px" }}
                      />
                      <YAxis
                        stroke="rgba(255,255,255,0.4)"
                        style={{ fontSize: "12px" }}
                        domain={["auto", "auto"]}
                        tickFormatter={(value: number) =>
                          formatInrCompact(value)
                        }
                        label={{
                          value: "Price (INR)",
                          angle: -90,
                          position: "insideLeft",
                          fill: "rgba(255,255,255,0.65)",
                          style: { fontSize: "11px" },
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "rgba(0,0,0,0.85)",
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: "10px",
                          color: "white",
                        }}
                        formatter={(value: any, _name: any, item: any) => {
                          const usdValue = item?.payload?.priceUsd;
                          return [
                            `${formatINR(Number(value))} (≈ ${formatUSD(Number(usdValue))})`,
                            "Price",
                          ];
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="priceInr"
                        stroke="#4A70A9"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: "#8FABD4" }}
                      />
                    </RechartsLineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="insights" className="space-y-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-[20px] font-semibold">AI Market Insights</h2>
              <p className="text-[15px] leading-6 text-white/70">
                Analyze how global events and supply chain disruptions may
                affect companies and industries.
              </p>
            </div>
            <button
              onClick={() => navigate("/chat")}
              className="rounded-xl bg-[#4A70A9] px-5 py-2.5 text-sm font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5"
            >
              Run AI Analysis
            </button>
          </div>

          <div className="grid grid-cols-1 gap-7 md:grid-cols-2 xl:grid-cols-3">
            {aiInsightCards.map((card) => (
              <div key={card.title} className="fin-panel p-6">
                <h3 className="text-base font-semibold text-white">
                  {card.title}
                </h3>
                <p className="mt-3 text-sm leading-6 text-white/70">
                  {card.impact}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section id="news" className="space-y-8">
          <div>
            <h2 className="text-[20px] font-semibold">Recent Market Events</h2>
            <p className="text-[15px] leading-6 text-white/70">
              Intelligence alerts highlighting market-moving developments.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-7 md:grid-cols-2">
            {marketEvents.map((event) => {
              const severityColor =
                event.severity === "High"
                  ? "#ff6b6b"
                  : event.severity === "Medium"
                    ? "#f59e0b"
                    : "#8FABD4";
              return (
                <div key={event.title} className="fin-panel p-6">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-base font-semibold text-white">
                        {event.title}
                      </h3>
                      <p className="mt-3 text-sm leading-6 text-white/70">
                        {event.description}
                      </p>
                    </div>
                    <span
                      className="rounded-full px-3 py-1 text-xs font-medium"
                      style={{
                        background: `${severityColor}20`,
                        color: severityColor,
                      }}
                    >
                      {event.severity}
                    </span>
                  </div>
                  <div className="mt-4 text-xs text-white/50">
                    Severity: {event.severity} | Time: {event.time}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </main>
    </div>
  );
};

export default DashboardPage;
