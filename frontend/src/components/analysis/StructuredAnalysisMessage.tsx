import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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

const MarkdownFallback: React.FC<{ content: string }> = ({ content }) => {
  return (
    <div className="prose prose-invert max-w-none text-sm leading-relaxed text-neutral-300">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-xl font-semibold text-white">
              {children}
            </h2>
          ),
          h3: ({ children }) => {
            const text = String(children).toLowerCase();
            if (text.includes("bull case")) {
              return (
                <h3 className="mb-1 mt-3 border-l-4 border-green-500 pl-4 text-lg font-semibold text-white">
                  {children}
                </h3>
              );
            }
            if (text.includes("bear case")) {
              return (
                <h3 className="mb-1 mt-3 border-l-4 border-red-500 pl-4 text-lg font-semibold text-white">
                  {children}
                </h3>
              );
            }
            if (text.includes("final verdict")) {
              return (
                <h3 className="mb-1 mt-3 border-l-4 border-[#4A70A9] pl-4 text-lg font-semibold text-white">
                  {children}
                </h3>
              );
            }
            return (
              <h3 className="mb-1 mt-3 text-lg font-semibold text-white">
                {children}
              </h3>
            );
          },
          p: ({ children }) => (
            <p className="text-neutral-300 leading-relaxed">{children}</p>
          ),
          ul: ({ children }) => <ul className="space-y-1 pl-4">{children}</ul>,
          li: ({ children }) => (
            <li className="text-neutral-300">{children}</li>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-white">{children}</strong>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

const StructuredAnalysisMessage: React.FC<StructuredAnalysisMessageProps> = ({
  content,
}) => {
  if (!isMultiAgentAnalysisMarkdown(content)) {
    return <MarkdownFallback content={content} />;
  }

  const parsed = parseMultiAgentAnalysis(content);
  if (!parsed) {
    return <MarkdownFallback content={content} />;
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
