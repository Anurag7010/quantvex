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

interface VerdictJson {
  verdict?: string;
  final_verdict?: string;
  conviction?: string;
  composite_confidence?: number;
  confidence?: number;
  summary?: string;
  time_horizon?: string;
  ticker?: string;
  bull_rebuttal?: string;
  key_drivers?: {
    bull_drivers?: string[];
    bear_drivers?: string[];
    dominant_side?: string;
  };
  bull_case?: {
    reasoning?: string;
    signals?: string[];
    confidence?: number;
  };
  bear_case?: {
    reasoning?: string;
    signals?: string[];
    confidence?: number;
  };
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

const renderVerdictUI = (
  verdict: string,
  conviction: string,
  compositeConfidence: number,
  bullConfidence: number,
  bearConfidence: number,
  bullReasoning: string,
  bearReasoning: string,
  bullDrivers: string[],
  bearDrivers: string[],
  summary: string,
  timeHorizon: string,
  ticker: string,
  conclusion: string,
) => {
  const verdictColor = getVerdictColor(verdict);
  return (
    <div className="structured-analysis-wrapper">
      <div className="verdict-strip" style={{ borderColor: verdictColor }}>
        <div className="verdict-left">
          <span className="verdict-badge" style={{ background: verdictColor }}>{verdict}</span>
          <span className="conviction-label">Conviction: {conviction}</span>
          <span className="horizon-label">⏱ {timeHorizon}</span>
        </div>
        <div className="confidence-meter">
          <span className="confidence-label">Composite Confidence</span>
          <div className="confidence-bar-track">
            <div className="confidence-bar-fill" style={{ width: `${compositeConfidence}%`, background: verdictColor }} />
          </div>
          <span className="confidence-value">{compositeConfidence}%</span>
        </div>
      </div>

      <div className="analysis-summary"><p>{summary}</p></div>

      <div className="thesis-grid">
        <div className="thesis-card bull">
          <div className="thesis-header">
            <span className="thesis-icon">▲</span>
            <h4>Bull Case{ticker ? ` — ${ticker}` : ""}</h4>
            <span className="thesis-confidence">{bullConfidence}%</span>
          </div>
          <div className="confidence-mini-bar">
            <div style={{ width: `${bullConfidence}%`, background: "#24a148" }} />
          </div>
          <p className="thesis-reasoning">{bullReasoning || "Positive catalysts identified."}</p>
          <ul className="driver-list bull-drivers">
            {bullDrivers.map((d, i) => <li key={i}><span>▲</span>{d}</li>)}
          </ul>
        </div>

        <div className="thesis-card bear">
          <div className="thesis-header">
            <span className="thesis-icon">▼</span>
            <h4>Bear Case{ticker ? ` — ${ticker}` : ""}</h4>
            <span className="thesis-confidence">{bearConfidence}%</span>
          </div>
          <div className="confidence-mini-bar">
            <div style={{ width: `${bearConfidence}%`, background: "#da1e28" }} />
          </div>
          <p className="thesis-reasoning">{bearReasoning || "Key risks identified."}</p>
          <ul className="driver-list bear-drivers">
            {bearDrivers.map((d, i) => <li key={i}><span>▼</span>{d}</li>)}
          </ul>
        </div>
      </div>

      {conclusion && (
        <div className="analysis-conclusion">
          <h4>Conclusion</h4>
          <p>{conclusion}</p>
        </div>
      )}
    </div>
  );
};

const StructuredAnalysisMessage: React.FC<StructuredAnalysisMessageProps> = ({
  content,
}) => {
  // JSON path — handles persisted streaming results and direct /invoke responses
  try {
    const j: VerdictJson = JSON.parse(content);
    if (j && (j.verdict || j.final_verdict)) {
      const verdict = (j.verdict || j.final_verdict || "HOLD").toUpperCase();
      const conviction = j.conviction ?? "MODERATE";
      const compositeConfidence = Math.round(
        j.composite_confidence ?? (j.confidence ?? 0.5) * 100
      );
      const bullConf = Math.round((j.bull_case?.confidence ?? 0.5) * 100);
      const bearConf = Math.round((j.bear_case?.confidence ?? 0.5) * 100);
      const bullDrivers = j.key_drivers?.bull_drivers ?? j.bull_case?.signals ?? [];
      const bearDrivers = j.key_drivers?.bear_drivers ?? j.bear_case?.signals ?? [];
      const bullReasoning = j.bull_case?.reasoning ?? "";
      const bearReasoning = j.bear_case?.reasoning ?? "";
      const summary = j.summary ?? "";
      const timeHorizon = j.time_horizon ?? "3-6 months";
      const ticker = j.ticker ?? "";
      const conclusion = j.bull_rebuttal ?? "";

      return renderVerdictUI(
        verdict, conviction, compositeConfidence,
        bullConf, bearConf,
        bullReasoning, bearReasoning,
        bullDrivers, bearDrivers,
        summary, timeHorizon, ticker, conclusion,
      );
    }
  } catch {
    // not JSON — fall through to markdown path
  }

  // Markdown path — handles GPT-formatted responses
  if (!isMultiAgentAnalysisMarkdown(content)) {
    return <MarkdownFallback content={content} />;
  }

  const parsed = parseMultiAgentAnalysis(content);
  if (!parsed) {
    return <MarkdownFallback content={content} />;
  }

  const verdict = parsed.verdict.outlook;
  const compositeConfidence = parseConfidencePct(parsed.verdict.confidence);
  const conviction = parsed.verdict.confidence;
  const bullDrivers = parsed.bullCase.keyDrivers;
  const bullReasoning = parsed.bullCase.rationale;
  const bullConfidence = Math.min(100, compositeConfidence + 5);
  const bearDrivers = parsed.bearCase.keyRisks;
  const bearReasoning = parsed.bearCase.rationale;
  const bearConfidence = Math.max(0, 100 - compositeConfidence - 5);
  const summary = parsed.verdict.summary.join(" ") || parsed.marketData.trendInsight;
  const conclusion = parsed.insights.join(" ") || parsed.marketData.trendInsight;

  return renderVerdictUI(
    verdict, conviction, compositeConfidence,
    bullConfidence, bearConfidence,
    bullReasoning, bearReasoning,
    bullDrivers, bearDrivers,
    summary, "Medium-Term", "", conclusion,
  );
};

export default StructuredAnalysisMessage;
