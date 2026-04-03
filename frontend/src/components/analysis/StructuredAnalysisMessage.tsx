import React from "react";

import AnalysisContainer from "./AnalysisContainer";
import BearCaseCard from "./BearCaseCard";
import BullCaseCard from "./BullCaseCard";
import InsightsList from "./InsightsList";
import MarketDataCard from "./MarketDataCard";
import VerdictCard from "./VerdictCard";
import {
  isMultiAgentAnalysisMarkdown,
  parseMultiAgentAnalysis,
} from "./analysisParser";

interface StructuredAnalysisMessageProps {
  content: string;
}

const sectionClass = "analysis-section-fade";

const StructuredAnalysisMessage: React.FC<StructuredAnalysisMessageProps> = ({
  content,
}) => {
  if (!isMultiAgentAnalysisMarkdown(content)) {
    return <p className="whitespace-pre-wrap">{content}</p>;
  }

  const parsed = parseMultiAgentAnalysis(content);
  if (!parsed) {
    return <p className="whitespace-pre-wrap">{content}</p>;
  }

  return (
    <AnalysisContainer title={parsed.title}>
      <div className={sectionClass} style={{ animationDelay: "0ms" }}>
        <VerdictCard
          outlook={parsed.verdict.outlook}
          confidence={parsed.verdict.confidence}
          summary={parsed.verdict.summary}
        />
      </div>

      <div className={sectionClass} style={{ animationDelay: "120ms" }}>
        <BullCaseCard
          keyDrivers={parsed.bullCase.keyDrivers}
          rationale={parsed.bullCase.rationale}
        />
      </div>

      <div className={sectionClass} style={{ animationDelay: "240ms" }}>
        <BearCaseCard
          keyRisks={parsed.bearCase.keyRisks}
          rationale={parsed.bearCase.rationale}
        />
      </div>

      <div className={sectionClass} style={{ animationDelay: "360ms" }}>
        <MarketDataCard
          currentPrice={parsed.marketData.currentPrice}
          trendInsight={parsed.marketData.trendInsight}
        />
      </div>

      <div className={sectionClass} style={{ animationDelay: "480ms" }}>
        <InsightsList insights={parsed.insights} />
      </div>
    </AnalysisContainer>
  );
};

export default StructuredAnalysisMessage;
