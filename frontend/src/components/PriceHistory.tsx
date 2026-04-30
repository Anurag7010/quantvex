import React, { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { QuoteData } from "../services/api";

interface PriceHistoryProps {
  quotes: QuoteData[];
}

const PriceHistory: React.FC<PriceHistoryProps> = ({ quotes }) => {
  const [chartData, setChartData] = useState<
    Array<{ time: string; price: number; symbol: string }>
  >([]);
  const [currentSymbol, setCurrentSymbol] = useState<string>("");

  useEffect(() => {
    if (quotes.length > 0) {
      // Get the most recent symbol
      const latestSymbol = quotes[quotes.length - 1].symbol;
      setCurrentSymbol(latestSymbol);

      // Filter quotes to only show the current symbol
      const filteredQuotes = quotes.filter((q) => q.symbol === latestSymbol);

      const data = filteredQuotes.map((quote) => ({
        time: new Date(quote.timestamp).toLocaleTimeString(),
        price: quote.inr_price ?? 0,
        symbol: quote.symbol,
      }));
      setChartData(data);
    }
  }, [quotes]);

  if (quotes.length === 0) {
    return (
      <div className="bg-slate-800 rounded-xl shadow-2xl p-8 border border-slate-700">
        <h3 className="text-xl font-bold text-white mb-4">Price History</h3>
        <div className="text-center py-12">
          <p className="text-slate-400">
            Search for a symbol to see price history
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl shadow-2xl p-8 border border-slate-700">
      <h3 className="text-xl font-bold text-white mb-6">
        Price History {currentSymbol && `- ${currentSymbol}`}
      </h3>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="time"
              stroke="#94a3b8"
              style={{ fontSize: "12px" }}
            />
            <YAxis
              stroke="#94a3b8"
              style={{ fontSize: "12px" }}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#1e293b",
                border: "1px solid #475569",
                borderRadius: "8px",
                color: "#fff",
              }}
              formatter={(value: string | number | readonly (string | number)[] | undefined) => [
                `₹${Number(value).toFixed(2)}`,
                "Price",
              ]}
            />
            <Line
              type="monotone"
              dataKey="price"
              stroke="#0ea5e9"
              strokeWidth={2}
              dot={{ fill: "#0ea5e9", r: 4 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs mb-1">Total Queries</p>
          <p className="text-white text-lg font-semibold">{chartData.length}</p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs mb-1">Current Symbol</p>
          <p className="text-white text-lg font-semibold">
            {currentSymbol || "N/A"}
          </p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs mb-1">Cache Hits</p>
          <p className="text-green-400 text-lg font-semibold">
            {
              quotes.filter((q) => q.symbol === currentSymbol && q.cache_hit)
                .length
            }
          </p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-700">
          <p className="text-slate-400 text-xs mb-1">Avg Latency</p>
          <p className="text-blue-400 text-lg font-semibold">
            {chartData.length > 0
              ? (
                  quotes
                    .filter((q) => q.symbol === currentSymbol)
                    .reduce((sum, q) => sum + q.latency_ms, 0) /
                  chartData.length
                ).toFixed(0)
              : 0}
            ms
          </p>
        </div>
      </div>
    </div>
  );
};

export default PriceHistory;
