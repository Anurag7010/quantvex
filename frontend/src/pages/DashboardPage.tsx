import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  LineChart,
  Menu,
  Search,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
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

const QuoteCardSkeleton: React.FC = () => (
  <div className="fin-panel p-6">
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1.1fr_2fr]">
      <div className="space-y-5">
        <div className="h-4 w-20 animate-pulse rounded bg-white/10" />
        <div className="h-9 w-40 animate-pulse rounded bg-white/10" />
        <div className="grid grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={index}
              className="h-14 animate-pulse rounded bg-white/10"
            />
          ))}
        </div>
      </div>
      <div className="h-[240px] animate-pulse rounded-xl bg-white/10" />
    </div>
  </div>
);

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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [marketScope, setMarketScope] = useState<MarketScope>("us");
  const [usdInrRate, setUsdInrRate] = useState(82.94);
  const [indianOverview, setIndianOverview] = useState<IndianOverview>(
    fallbackIndianOverview,
  );

  // ── Live Indian Market Overview (server-proxied, no CORS) ──────────────────
  const [indicesLoading, setIndicesLoading] = useState(true);

  const fetchIndices = useCallback(async () => {
    try {
      const data = await mcpApi.getMarketIndices();
      const niftyPrice = data.nifty?.price;
      const sensexPrice = data.sensex?.price;
      if (niftyPrice) {
        setIndianOverview({
          nifty: niftyPrice,
          niftyChange: data.nifty?.change_pct ?? 0,
          sensex: sensexPrice ?? fallbackIndianOverview.sensex,
          sensexChange: data.sensex?.change_pct ?? 0,
        });
      }
      if (data.usd_inr) setUsdInrRate(data.usd_inr);
    } catch {
      /* keep fallback values */
    } finally {
      setIndicesLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIndices();
    const id = setInterval(fetchIndices, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchIndices]);

  // ── Crypto symbol list ─────────────────────────────────────────────────────
  const CRYPTO_LIST = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"];

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchSymbol.trim()) return;

    const upper = searchSymbol.trim().toUpperCase();
    setLoading(true);
    setError(null);

    try {
      if (CRYPTO_LIST.includes(upper)) {
        // Route crypto through Binance proxy (no CORS, no auth needed)
        const data = await mcpApi.getCryptoQuote(upper);
        setQuoteData({
          symbol: data.symbol,
          price: data.price_usd,
          inr_price: data.inr_price,
          usd_inr_rate: usdInrRate,
          timestamp: data.timestamp,
          data_source: data.source,
          cache_hit: false,
          latency_ms: 0,
          high: data.high_24h,
          low: data.low_24h,
          volume: data.volume,
        });
      } else {
        const response = await mcpApi.getQuote(upper, 60);
        if (response.success && response.data) {
          setQuoteData(response.data);
          if (response.data.usd_inr_rate) {
            setUsdInrRate(response.data.usd_inr_rate);
          }
        } else {
          setError(response.error || "Failed to fetch quote");
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Network error occurred");
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
      const inrBase = quoteData.inr_price ?? quoteData.price;
      data.push({
        time: `${i}d ago`,
        priceUsd: usd,
        priceInr: inrBase + variance * (quoteData.usd_inr_rate ?? usdInrRate),
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
          value: 97453.32,
          change: 3.12,
        },
        {
          name: "Ethereum",
          value: 4210.24,
          change: 2.41,
        },
        {
          name: "Solana",
          value: 197.42,
          change: -1.09,
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
        value: 97453.32,
        change: 3.12,
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
    setMobileNavOpen(false);
    document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth" });
  };

  const quoteInrPrice = quoteData ? (quoteData.inr_price ?? null) : null;

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-black/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between px-6 py-4 sm:px-8">
          <div className="flex items-center gap-4">
            <div className="text-lg font-semibold tracking-[-0.02em]">
              QuantVex
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
            type="button"
            onClick={() => setMobileNavOpen((open) => !open)}
            className="rounded-lg border border-white/10 p-2 text-white md:hidden"
            aria-label="Toggle navigation"
          >
            {mobileNavOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>
          <button
            onClick={() => navigate("/")}
            className="rounded-xl bg-[#4A70A9] px-4 py-2 text-sm font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5 hover:scale-[1.03]"
          >
            Home
          </button>
        </div>
        {mobileNavOpen ? (
          <nav className="mx-auto flex max-w-[1280px] flex-col gap-2 px-6 pb-4 text-sm md:hidden">
            {[
              ["overview", "Overview"],
              ["market", "Market Data"],
              ["insights", "AI Insights"],
              ["news", "News Events"],
            ].map(([tab, label]) => (
              <button
                key={tab}
                onClick={() => handleNav(tab, tab)}
                className={`rounded-lg px-3 py-2 text-left ${
                  activeTab === tab ? "bg-white/10 text-white" : "text-white/70"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        ) : null}
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
              const changeColor = isPositive ? "#24a148" : "#da1e28";
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
                          ? "rgba(36,161,72,0.18)"
                          : "rgba(218,30,40,0.15)",
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
                    indianOverview.niftyChange >= 0 ? "#24a148" : "#da1e28",
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
                    indianOverview.sensexChange >= 0 ? "#24a148" : "#da1e28",
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
                Live rate via open.er-api.com
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
              ["Ethereum", "ETH-USD"],
              ["Bitcoin", "BTC-USD"],
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

          {loading ? (
            <QuoteCardSkeleton />
          ) : (
            <div className="fin-panel p-6">
              <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1.1fr_2fr]">
                <div className="space-y-6">
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.2em] text-white/60">
                      Price
                    </p>
                    <div className="text-3xl font-semibold">
                      {quoteInrPrice ? formatINR(quoteInrPrice) : "₹ N/A"}
                    </div>
                    <div className="text-sm text-white/70">
                      {quoteData?.symbol || "Awaiting symbol search"}
                    </div>
                    {quoteData ? (
                      <p className="text-sm text-white/60">
                        {formatUSD(quoteData.price)} USD
                      </p>
                    ) : null}
                    {quoteData ? (
                      <p className="text-xs text-white/50"></p>
                    ) : null}
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="space-y-1">
                      <p className="text-white/60">Open</p>
                      <p className="font-medium">
                        {quoteData?.open
                          ? quoteData.inr_open
                            ? formatINR(quoteData.inr_open)
                            : "₹ N/A"
                          : "--"}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-white/60">High</p>
                      <p className="font-medium">
                        {quoteData?.high
                          ? quoteData.inr_high
                            ? formatINR(quoteData.inr_high)
                            : "₹ N/A"
                          : "--"}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-white/60">Low</p>
                      <p className="font-medium">
                        {quoteData?.low
                          ? quoteData.inr_low
                            ? formatINR(quoteData.inr_low)
                            : "₹ N/A"
                          : "--"}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-white/60">Latency</p>
                      <p className="font-medium">
                        {quoteData?.latency_ms
                          ? `${Number(quoteData.latency_ms).toFixed(2)} ms`
                          : "--"}
                      </p>
                    </div>
                  </div>

                  <div className="text-xs text-white/50">
                    {quoteData?.cache_hit
                      ? "Cached response"
                      : "Live market feed (USD source, INR display)"}
                  </div>
                  {quoteData ? (
                    <div className="text-xs text-white/50">
                      Last updated:{" "}
                      {new Date(quoteData.timestamp).toLocaleString()}
                    </div>
                  ) : null}
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
                    {chartData.length === 0 ? (
                      <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-white/10 text-center text-white/50">
                        <LineChart className="mb-3 h-8 w-8" />
                        <p className="text-sm">
                          Search for a symbol above to view the chart
                        </p>
                      </div>
                    ) : (
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
                            formatter={(
                              value:
                                | string
                                | number
                                | readonly (string | number)[]
                                | undefined,
                              _name: string | number | undefined,
                              item: { payload?: { priceUsd?: number } },
                            ) => {
                              const usdValue = item.payload?.priceUsd;
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
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* Market Intelligence CTA — replaces AI Market Insights + Recent Market Events */}
        <div className="market-intelligence-cta">
          <div className="cta-content">
            <h3>AI Market Intelligence</h3>
            <p>
              Ask about supply chain risks, company analysis, live news impact,
              and multi-agent investment theses.
            </p>
          </div>
          <button className="btn-primary" onClick={() => navigate("/chat")}>
            Open AI Analyst →
          </button>
        </div>
      </main>
    </div>
  );
};

export default DashboardPage;
