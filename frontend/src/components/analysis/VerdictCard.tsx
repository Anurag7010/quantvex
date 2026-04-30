import React from "react";

interface VerdictCardProps {
  outlook: string;
  confidence: string;
  summary: string[];
}

const VerdictCard: React.FC<VerdictCardProps> = ({
  outlook,
  confidence,
  summary,
}) => {
  const verdictColor =
    {
      "STRONG BUY": "#24a148",
      BUY: "#42be65",
      HOLD: "#f1c21b",
      SELL: "#ff832b",
      "STRONG SELL": "#da1e28",
      "INSUFFICIENT DATA": "#6f6f6f",
      Bullish: "#24a148",
      Bearish: "#da1e28",
      Mixed: "#f1c21b",
    }[outlook] ?? "#6f6f6f";
  const confidenceValue = Number(confidence.replace("%", ""));

  return (
    <section className="rounded-xl border border-[#8FABD433] bg-[#8FABD414] p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[16px] font-semibold text-white">Final Verdict</h3>
        <span
          className="rounded-full px-3 py-1 text-xs font-semibold text-black"
          style={{ backgroundColor: verdictColor }}
        >
          {outlook}
        </span>
      </div>
      <ul className="mt-3 space-y-2 text-sm text-white/90">
        <li className="text-[20px] font-semibold text-white">
          <span className="font-semibold">Confidence:</span> {confidence}
        </li>
        {Number.isFinite(confidenceValue) ? (
          <li>
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(0, Math.min(confidenceValue, 100))}%`,
                  backgroundColor: verdictColor,
                }}
              />
            </div>
          </li>
        ) : null}
        <li>
          <span className="font-semibold">Summary:</span>
          <div className="mt-1 space-y-1">
            {summary.map((line, idx) => (
              <p
                key={`${line}-${idx}`}
                className="text-sm leading-relaxed text-white/85"
              >
                {line}
              </p>
            ))}
          </div>
        </li>
      </ul>
    </section>
  );
};

export default VerdictCard;
