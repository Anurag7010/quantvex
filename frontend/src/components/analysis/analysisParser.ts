import { ParsedMultiAgentAnalysis } from "./types";

const stripMarkdown = (value: string): string =>
  value
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .trim();

const parseBulletValue = (line: string, label: string): string => {
  const re = new RegExp(`^-\\s*\\*\\*${label}:\\*\\*\\s*(.+)$`, "i");
  const match = line.match(re);
  return match ? stripMarkdown(match[1]) : "";
};

export const isMultiAgentAnalysisMarkdown = (content: string): boolean => {
  return /^##\s+.*Multi-Agent Market Analysis/mi.test(content);
};

export const parseMultiAgentAnalysis = (
  content: string,
): ParsedMultiAgentAnalysis | null => {
  if (!isMultiAgentAnalysisMarkdown(content)) {
    return null;
  }

  const lines = content.replace(/\r\n/g, "\n").split("\n");

  const parsed: ParsedMultiAgentAnalysis = {
    title: "Multi-Agent Market Analysis",
    verdict: {
      outlook: "Mixed",
      confidence: "N/A",
      summary: [],
    },
    bullCase: {
      keyDrivers: [],
      rationale: "",
    },
    bearCase: {
      keyRisks: [],
      rationale: "",
    },
    marketData: {
      currentPrice: "N/A",
      trendInsight: "No trend insight available.",
    },
    insights: [],
  };

  type Section = "none" | "verdict" | "bull" | "bear" | "market" | "insights";
  let section: Section = "none";
  let subMode: "none" | "summary" | "bull-drivers" | "bull-rationale" | "bear-risks" | "bear-rationale" = "none";

  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line === "---") continue;

    if (line.startsWith("## ")) {
      parsed.title = stripMarkdown(line.replace(/^##\s+/, ""));
      continue;
    }

    if (line.startsWith("### ")) {
      subMode = "none";
      if (line.includes("Final Verdict")) section = "verdict";
      else if (line.includes("Bull Case")) section = "bull";
      else if (line.includes("Bear Case")) section = "bear";
      else if (line.includes("Market Data")) section = "market";
      else if (line.includes("Key Insights")) section = "insights";
      else section = "none";
      continue;
    }

    if (section === "verdict") {
      const outlook = parseBulletValue(line, "Outlook");
      const confidence = parseBulletValue(line, "Confidence");
      if (outlook) {
        parsed.verdict.outlook = outlook;
        continue;
      }
      if (confidence) {
        parsed.verdict.confidence = confidence;
        continue;
      }
      if (/^-\s*\*\*Summary:\*\*/i.test(line)) {
        const inLine = stripMarkdown(line.replace(/^-\s*\*\*Summary:\*\*/i, ""));
        subMode = "summary";
        if (inLine) parsed.verdict.summary.push(inLine);
        continue;
      }
      if (subMode === "summary") {
        parsed.verdict.summary.push(stripMarkdown(line));
      }
      continue;
    }

    if (section === "bull") {
      if (/^\*\*Key Drivers:\*\*/i.test(line)) {
        subMode = "bull-drivers";
        continue;
      }
      if (/^\*\*Rationale:\*\*/i.test(line)) {
        subMode = "bull-rationale";
        const inline = stripMarkdown(line.replace(/^\*\*Rationale:\*\*/i, ""));
        if (inline) parsed.bullCase.rationale = inline;
        continue;
      }
      if (/^-\s+/.test(line) && subMode === "bull-drivers") {
        parsed.bullCase.keyDrivers.push(stripMarkdown(line.replace(/^-\s+/, "")));
        continue;
      }
      if (subMode === "bull-rationale") {
        parsed.bullCase.rationale = [parsed.bullCase.rationale, stripMarkdown(line)]
          .filter(Boolean)
          .join(" ")
          .trim();
      }
      continue;
    }

    if (section === "bear") {
      if (/^\*\*Key Risks:\*\*/i.test(line)) {
        subMode = "bear-risks";
        continue;
      }
      if (/^\*\*Rationale:\*\*/i.test(line)) {
        subMode = "bear-rationale";
        const inline = stripMarkdown(line.replace(/^\*\*Rationale:\*\*/i, ""));
        if (inline) parsed.bearCase.rationale = inline;
        continue;
      }
      if (/^-\s+/.test(line) && subMode === "bear-risks") {
        parsed.bearCase.keyRisks.push(stripMarkdown(line.replace(/^-\s+/, "")));
        continue;
      }
      if (subMode === "bear-rationale") {
        parsed.bearCase.rationale = [parsed.bearCase.rationale, stripMarkdown(line)]
          .filter(Boolean)
          .join(" ")
          .trim();
      }
      continue;
    }

    if (section === "market") {
      const currentPrice = parseBulletValue(line, "Current Price");
      const trendInsight = parseBulletValue(line, "Trend Insight");
      if (currentPrice) parsed.marketData.currentPrice = currentPrice;
      if (trendInsight) parsed.marketData.trendInsight = trendInsight;
      continue;
    }

    if (section === "insights" && /^-\s+/.test(line)) {
      parsed.insights.push(stripMarkdown(line.replace(/^-\s+/, "")));
    }
  }

  if (!parsed.verdict.summary.length) {
    parsed.verdict.summary = ["Signals are mixed across upside catalysts and downside risk transmission."];
  }

  if (!parsed.bullCase.keyDrivers.length) {
    parsed.bullCase.keyDrivers = ["No explicit bullish drivers provided."];
  }

  if (!parsed.bearCase.keyRisks.length) {
    parsed.bearCase.keyRisks = ["No explicit bearish risks provided."];
  }

  if (!parsed.insights.length) {
    parsed.insights = ["No additional key insights provided."];
  }

  return parsed;
};
