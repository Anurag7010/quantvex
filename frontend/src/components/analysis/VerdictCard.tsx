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
  return (
    <section className="rounded-xl border border-[#8FABD433] bg-[#8FABD414] p-4">
      <h3 className="text-[16px] font-semibold text-white">⚖️ Final Verdict</h3>
      <ul className="mt-3 space-y-2 text-sm text-white/90">
        <li>
          <span className="font-semibold">Outlook:</span> {outlook}
        </li>
        <li className="text-[20px] font-semibold text-white">
          <span className="font-semibold">Confidence:</span> {confidence}
        </li>
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
