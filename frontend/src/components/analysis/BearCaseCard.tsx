import React from "react";

interface BearCaseCardProps {
  keyRisks: string[];
  rationale: string;
}

const BearCaseCard: React.FC<BearCaseCardProps> = ({ keyRisks, rationale }) => {
  return (
    <section className="rounded-xl border-l-4 border-[#EF4444] bg-[rgba(239,68,68,0.08)] p-4">
      <h3 className="text-[16px] font-semibold text-white">Bear Case</h3>
      <p className="mt-3 text-sm font-semibold text-white">Key Risks:</p>
      <ul className="mt-2 space-y-2 text-sm text-white/90">
        {keyRisks.map((risk, idx) => (
          <li key={`${risk}-${idx}`} className="flex items-start gap-2">
            <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-[#EF4444]" />
            <span>{risk}</span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm">
        <span className="font-semibold text-white">Rationale:</span>{" "}
        <span className="text-white/85">{rationale}</span>
      </p>
    </section>
  );
};

export default BearCaseCard;
