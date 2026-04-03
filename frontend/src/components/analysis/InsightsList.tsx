import React from "react";

interface InsightsListProps {
  insights: string[];
}

const InsightsList: React.FC<InsightsListProps> = ({ insights }) => {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <h3 className="text-[16px] font-semibold text-white">🔍 Key Insights</h3>
      <ul className="mt-3 space-y-2 text-sm leading-relaxed text-white/90">
        {insights.map((insight, idx) => (
          <li key={`${insight}-${idx}`} className="flex items-start gap-2">
            <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-[#8FABD4]" />
            <span>{insight}</span>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default InsightsList;
