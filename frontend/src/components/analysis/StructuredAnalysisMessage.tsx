import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  isMultiAgentAnalysisMarkdown,
  parseMultiAgentAnalysis,
} from "./analysisParser";

interface StructuredAnalysisMessageProps {
  content: string;
}

const VERDICT_COLORS: Record<string, string> = {
  "STRONG BUY": "#24a148",
  "BUY": "#42be65",
  "HOLD": "#f1c21b",
  "SELL": "#ff832b",
  "STRONG SELL": "#da1e28",
  "INSUFFICIENT DATA": "#6f6f6f",
};

const getVerdictColor = (outlook: string): string => {
  const upper = outlook.toUpperCase();
  for (const key of Object.keys(VERDICT_COLORS)) {
    if (upper.includes(key)) return VERDICT_COLORS[key];
  }
  return "#6f6f6f";
};

const parseConfidencePct = (raw: string): number => {
  const match = raw.match(/(\d+)/);
  return match ? Math.min(100, Math.max(0, parseInt(match[1], 10))) : 65;
};

const MarkdownFallback: React.FC<{ content: string }> = ({ content }) => {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-xl font-semibold" style={{ color: "#f4f4f4" }}>
              {children}
            </h2>
          ),
          h3: ({ children }) => {
            const text = String(children).toLowerCase();
            if (text.includes("bull case")) {
              return (
                <h3 className="mb-1 mt-3 pl-4 text-lg font-semibold" style={{ borderLeft: "4px solid #24a148", color: "#f4f4f4" }}>
                  {children}
                </h3>
              );
            }
            if (text.includes("bear case")) {
              return (
                <h3 className="mb-1 mt-3 pl-4 text-lg font-semibold" style={{ borderLeft: "4px solid #da1e28", color: "#f4f4f4" }}>
                  {children}
                </h3>
              );
            }
            return (
              <h3 className="mb-1 mt-3 text-lg font-semibold" style={{ color: "#f4f4f4" }}>
                {children}
              </h3>
            );
          },
          p: ({ children }) => (
            <p style={{ color: "#c8c8d0", lineHeight: 1.7, fontSize: 15 }}>{children}</p>
          ),
          ul: ({ children }) => <ul style={{ paddingLeft: 20 }}>{children}</ul>,
          li: ({ children }) => (
            <li style={{ color: "#c8c8d0", fontSize: 14, padding: "3px 0" }}>{children}</li>
          ),
          strong: ({ children }) => (
            <strong style={{ color: "#f4f4f4", fontWeight: 600 }}>{children}</strong>
          ),
          code: ({ children }) => (
            <code style={{ background: "#1e1e2a", borderRadius: 4, padding: "2px 6px", fontFamily: "monospace", fontSize: 13, color: "#c8c8d0" }}>
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre style={{ background: "#1e1e2a", borderRadius: 8, padding: 16, overflow: "auto", fontSize: 13 }}>
              {children}
            </pre>
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

  const verdict = parsed.verdict.outlook;
  const verdictColor = getVerdictColor(verdict);
  const compositeConfidence = parseConfidencePct(parsed.verdict.confidence);
  const conviction = parsed.verdict.confidence;
  const timeHorizon = "Medium-Term";

  // Bull / bear
  const bullDrivers = parsed.bullCase.keyDrivers;
  const bullReasoning = parsed.bullCase.rationale;
  const bullConfidence = Math.min(100, compositeConfidence + 5);

  const bearDrivers = parsed.bearCase.keyRisks;
  const bearReasoning = parsed.bearCase.rationale;
  const bearConfidence = Math.max(0, 100 - compositeConfidence - 5);

  const summary = parsed.verdict.summary.join(" ");
  const conclusion = parsed.insights.join(" ") || parsed.marketData.trendInsight;

  return (
    <div className="structured-analysis-wrapper">
      {/* Verdict header strip */}
      <div className="verdict-strip" style={{ borderColor: verdictColor }}>
        <div className="verdict-left">
          <span className="verdict-badge" style={{ background: verdictColor }}>
            {verdict}
          </span>
          <span className="conviction-label">Conviction: {conviction}</span>
          <span className="horizon-label">⏱ {timeHorizon}</span>
        </div>
        <div className="confidence-meter">
          <span className="confidence-label">Composite Confidence</span>
          <div className="confidence-bar-track">
            <div
              className="confidence-bar-fill"
              style={{ width: `${compositeConfidence}%`, background: verdictColor }}
            />
          </div>
          <span className="confidence-value">{compositeConfidence}%</span>
        </div>
      </div>

      {/* Summary */}
      <div className="analysis-summary">
        <p>{summary || parsed.marketData.trendInsight}</p>
      </div>

      {/* Bull / Bear grid */}
      <div className="thesis-grid">
        <div className="thesis-card bull">
          <div className="thesis-header">
            <span className="thesis-icon">▲</span>
            <h4>Bull Case</h4>
            <span className="thesis-confidence">{bullConfidence}%</span>
          </div>
          <div className="confidence-mini-bar">
            <div style={{ width: `${bullConfidence}%`, background: "#24a148" }} />
          </div>
          <p className="thesis-reasoning">{bullReasoning || "Positive catalysts identified."}</p>
          <ul className="driver-list bull-drivers">
            {bullDrivers.map((d, i) => (
              <li key={i}><span>▲</span>{d}</li>
            ))}
          </ul>
        </div>

        <div className="thesis-card bear">
          <div className="thesis-header">
            <span className="thesis-icon">▼</span>
            <h4>Bear Case</h4>
            <span className="thesis-confidence">{bearConfidence}%</span>
          </div>
          <div className="confidence-mini-bar">
            <div style={{ width: `${bearConfidence}%`, background: "#da1e28" }} />
          </div>
          <p className="thesis-reasoning">{bearReasoning || "Key risks identified."}</p>
          <ul className="driver-list bear-drivers">
            {bearDrivers.map((d, i) => (
              <li key={i}><span>▼</span>{d}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Conclusion */}
      <div className="analysis-conclusion">
        <h4>Conclusion</h4>
        <p>{conclusion}</p>
      </div>
    </div>
  );
};

export default StructuredAnalysisMessage;
