import React from "react";

interface BullCaseCardProps {
  keyDrivers: string[];
  rationale: string;
}

const BullCaseCard: React.FC<BullCaseCardProps> = ({
  keyDrivers,
  rationale,
}) => {
  return (
    <section className="rounded-xl border-l-4 border-[#22C55E] bg-[rgba(34,197,94,0.08)] p-4">
      <h3 className="text-[16px] font-semibold text-white">Bull Case</h3>
      <p className="mt-3 text-sm font-semibold text-white">Key Drivers:</p>
      <ul className="mt-2 space-y-2 text-sm text-white/90">
        {keyDrivers.map((driver, idx) => (
          <li key={`${driver}-${idx}`} className="flex items-start gap-2">
            <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-[#22C55E]" />
            <span>{driver}</span>
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

export default BullCaseCard;
