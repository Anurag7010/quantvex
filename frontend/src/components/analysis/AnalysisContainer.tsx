import React from "react";

interface AnalysisContainerProps {
  title: string;
  children: React.ReactNode;
}

const AnalysisContainer: React.FC<AnalysisContainerProps> = ({
  title,
  children,
}) => {
  return (
    <div className="w-full rounded-2xl border border-white/10 bg-[#121f33] p-5 shadow-[0_20px_45px_rgba(0,0,0,0.35)]">
      <h2 className="text-[22px] font-bold leading-tight text-white">
        {title}
      </h2>
      <div className="mt-5 space-y-5">{children}</div>
    </div>
  );
};

export default AnalysisContainer;
