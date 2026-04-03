export interface ParsedMultiAgentAnalysis {
  title: string;
  verdict: {
    outlook: string;
    confidence: string;
    summary: string[];
  };
  bullCase: {
    keyDrivers: string[];
    rationale: string;
  };
  bearCase: {
    keyRisks: string[];
    rationale: string;
  };
  marketData: {
    currentPrice: string;
    trendInsight: string;
  };
  insights: string[];
}
