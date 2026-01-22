import React, { useState, useEffect, useRef } from "react";
import { Search, TrendingUp, TrendingDown, Play, Pause } from "lucide-react";
import { mcpApi, QuoteData } from "../services/api";

interface QuoteCardProps {
  onQuoteUpdate?: (quote: QuoteData) => void;
}

// Exchange rate: 1 USD = 89.94 INR
const USD_TO_INR = 89.94;

const QuoteCard: React.FC<QuoteCardProps> = ({ onQuoteUpdate }) => {
  const [symbol, setSymbol] = useState("");
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveMode, setLiveMode] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const popularSymbols = [
    { symbol: "AAPL", name: "Apple" },
    { symbol: "MSFT", name: "Microsoft" },
    { symbol: "GOOGL", name: "Google" },
    { symbol: "TSLA", name: "Tesla" },
    { symbol: "BTCUSDT", name: "Bitcoin" },
    { symbol: "ETHUSDT", name: "Ethereum" },
  ];

  const fetchQuote = async (sym: string) => {
    if (!sym.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await mcpApi.getQuote(sym);

      if (response.success && response.data) {
        setQuote(response.data);
        if (onQuoteUpdate) {
          onQuoteUpdate(response.data);
        }
      } else {
        setError(response.error || "Failed to fetch quote");
        setQuote(null);
      }
    } catch (err: any) {
      setError(err.message || "Network error");
      setQuote(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchQuote(symbol);
  };

  const handleQuickSearch = (sym: string) => {
    setSymbol(sym);
    fetchQuote(sym);
  };

  const getPriceChange = () => {
    if (!quote || !quote.previous_close) return null;
    const change = quote.price - quote.previous_close;
    const changePercent = (change / quote.previous_close) * 100;
    return { change, changePercent };
  };

  const priceChange = getPriceChange();

  // Live Mode: Auto-refresh every 5 seconds
  useEffect(() => {
    if (liveMode && symbol) {
      intervalRef.current = setInterval(() => {
        fetchQuote(symbol);
      }, 5000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [liveMode, symbol]);

  const toggleLiveMode = () => {
    setLiveMode(!liveMode);
  };

  // Calculate day range position (0-100%)
  const getDayRangePosition = () => {
    if (!quote || !quote.high || !quote.low) return null;
    const range = quote.high - quote.low;
    if (range === 0) return 50; // If no range, show in middle
    const position = ((quote.price - quote.low) / range) * 100;
    return Math.max(0, Math.min(100, position));
  };

  const rangePosition = getDayRangePosition();

  return (
    <div className="bg-slate-800 rounded-xl shadow-2xl p-8 border border-slate-700">
      {/* Search Form */}
      <form onSubmit={handleSubmit} className="mb-6">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 w-5 h-5" />
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="Enter stock or crypto symbol"
              className="w-full pl-10 pr-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-slate-600 text-white rounded-lg font-medium transition-colors duration-200 flex items-center gap-2"
          >
            {loading ? (
              <>
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Loading...
              </>
            ) : (
              <>
                <Search className="w-5 h-5" />
                Get Quote
              </>
            )}
          </button>
          {quote && (
            <button
              type="button"
              onClick={toggleLiveMode}
              className={`px-6 py-3 rounded-lg font-medium transition-colors duration-200 flex items-center gap-2 ${
                liveMode
                  ? "bg-green-600 hover:bg-green-700 text-white"
                  : "bg-slate-700 hover:bg-slate-600 text-slate-200"
              }`}
            >
              {liveMode ? (
                <>
                  <Pause className="w-5 h-5" />
                  Live
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  Start Live
                </>
              )}
            </button>
          )}
        </div>
      </form>

      {/* Popular Symbols */}
      <div className="mb-6">
        <p className="text-slate-400 text-sm mb-3">Popular:</p>
        <div className="flex flex-wrap gap-2">
          {popularSymbols.map((item) => (
            <button
              key={item.symbol}
              onClick={() => handleQuickSearch(item.symbol)}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-sm transition-colors duration-200"
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-900/30 border border-red-700 rounded-lg">
          <p className="text-red-300 text-sm"> {error}</p>
        </div>
      )}

      {/* Quote Display */}
      {quote && (
        <div className="space-y-4">
          {/* Main Price */}
          <div className="bg-slate-900/50 rounded-lg p-6 border border-slate-700">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h2 className="text-3xl font-bold text-white mb-1">
                  {quote.symbol}
                </h2>
                <p className="text-slate-400 text-sm">
                  {quote.data_source} • {quote.cache_hit ? " Cached" : " Fresh"}
                </p>
              </div>
              <div className="text-right">
                <p className="text-4xl font-bold text-white">
                  ₹
                  {(quote.price * USD_TO_INR).toLocaleString("en-IN", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </p>
                {priceChange && (
                  <div
                    className={`flex items-center gap-1 mt-1 ${
                      priceChange.change >= 0
                        ? "text-green-400"
                        : "text-red-400"
                    }`}
                  >
                    {priceChange.change >= 0 ? (
                      <TrendingUp className="w-5 h-5" />
                    ) : (
                      <TrendingDown className="w-5 h-5" />
                    )}
                    <span className="text-lg font-semibold">
                      {priceChange.change >= 0 ? "+" : ""}
                      {(priceChange.change * USD_TO_INR).toFixed(2)} (
                      {priceChange.changePercent >= 0 ? "+" : ""}
                      {priceChange.changePercent.toFixed(2)}%)
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Day Range Visualizer */}
          {quote.high && quote.low && rangePosition !== null && (
            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700 mt-4">
              <p className="text-slate-400 text-xs mb-3">Day Range</p>
              <div className="relative">
                {/* Progress bar background */}
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  {/* Filled portion */}
                  <div
                    className="h-full bg-gradient-to-r from-red-500 via-yellow-500 to-green-500 transition-all duration-500"
                    style={{ width: `${rangePosition}%` }}
                  />
                </div>
                {/* Current price indicator */}
                <div
                  className="absolute top-1/2 transform -translate-y-1/2 -translate-x-1/2 transition-all duration-500"
                  style={{ left: `${rangePosition}%` }}
                >
                  <div className="w-4 h-4 bg-white rounded-full border-2 border-slate-800 shadow-lg" />
                </div>
              </div>
              <div className="flex items-center justify-between mt-2 text-xs">
                <span className="text-red-400">
                  Low: ₹{(quote.low * USD_TO_INR).toFixed(2)}
                </span>
                <span className="text-slate-400">
                  Current: ₹{(quote.price * USD_TO_INR).toFixed(2)}
                </span>
                <span className="text-green-400">
                  High: ₹{(quote.high * USD_TO_INR).toFixed(2)}
                </span>
              </div>
            </div>
          )}

          {/* Stats Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {quote.open && (
              <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-xs mb-1">Open</p>
                <p className="text-white text-lg font-semibold">
                  ₹{(quote.open * USD_TO_INR).toFixed(2)}
                </p>
              </div>
            )}
            {quote.high && (
              <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-xs mb-1">High</p>
                <p className="text-green-400 text-lg font-semibold">
                  ₹{(quote.high * USD_TO_INR).toFixed(2)}
                </p>
              </div>
            )}
            {quote.low && (
              <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-xs mb-1">Low</p>
                <p className="text-red-400 text-lg font-semibold">
                  ₹{(quote.low * USD_TO_INR).toFixed(2)}
                </p>
              </div>
            )}
            {quote.volume && (
              <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
                <p className="text-slate-400 text-xs mb-1">Volume</p>
                <p className="text-white text-lg font-semibold">
                  {quote.volume.toLocaleString()}
                </p>
              </div>
            )}
          </div>

          {/* Metadata */}
          <div className="flex items-center justify-between text-sm font-bold text-white mt-4">
            <span>Latency: {quote.latency_ms.toFixed(2)}ms</span>
            <span>
              Updated: {new Date(quote.timestamp).toLocaleTimeString()}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuoteCard;
