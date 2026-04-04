import React from "react";

interface MarketDataCardProps {
  currentPrice: string;
  trendInsight: string;
}

const MarketDataCard: React.FC<MarketDataCardProps> = ({
  currentPrice,
  trendInsight,
}) => {
  return (
    <section className="rounded-xl border border-[rgba(143,171,212,0.2)] bg-[rgba(143,171,212,0.08)] p-4">
      <h3 className="text-[16px] font-semibold text-white">Market Data</h3>
      <ul className="mt-3 space-y-2 text-sm text-white/90">
        <li>
          <span className="font-semibold">Current Price:</span> {currentPrice}
        </li>
        <li>
          <span className="font-semibold">Trend Insight:</span> {trendInsight}
        </li>
      </ul>
    </section>
  );
};

export default MarketDataCard;
