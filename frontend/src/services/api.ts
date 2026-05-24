import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const API_KEY = process.env.REACT_APP_API_KEY || '';

if (!API_KEY) {
  console.error('REACT_APP_API_KEY is not set. API calls will fail.');
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json',
  },
});

export interface QuoteData {
  symbol: string;
  price: number;
  inr_price?: number;
  usd_inr_rate?: number;
  timestamp: string;
  data_source: string;
  cache_hit: boolean;
  latency_ms: number;
  volume?: number;
  high?: number;
  inr_high?: number;
  low?: number;
  inr_low?: number;
  open?: number;
  inr_open?: number;
  previous_close?: number;
  inr_previous_close?: number;
}

export interface QuoteResponse {
  success: boolean;
  data: QuoteData | null;
  error: string | null;
  cache_hit: boolean;
  data_source: string | null;
  latency_ms: number;
}

export interface Capabilities {
  server: {
    name: string;
    version: string;
    description: string;
  };
  tools: Array<{
    name: string;
    description: string;
    inputSchema: Record<string, unknown>;
    outputSchema: Record<string, unknown>;
  }>;
  connectors: Array<{
    name: string;
    type: string;
    description: string;
    rate_limit: string;
  }>;
}

export interface HealthStatus {
  status: string;
  redis_connected: boolean;
  active_subscriptions: number;
}

export interface ChatResponse {
  response: string;
  success: boolean;
  error: string | null;
}

export interface MultiAgentAnalysisData {
  query: string;
  ticker?: string | null;
  final_verdict?: string;
  verdict?: string;
  conviction?: string;
  confidence?: number;
  composite_confidence?: number;
  summary?: string;
  key_drivers?: {
    bull_drivers?: string[];
    bear_drivers?: string[];
    dominant_side?: string;
  };
}

export type SSEStepName =
  | "init"
  | "quote_fetch"
  | "graph_trace"
  | "news_fetch"
  | "bull_thesis"
  | "bear_attack"
  | "rebuttal"
  | "judge"
  | "verdict"
  | "done";

export interface SSEStep {
  step: SSEStepName;
  message?: string;
  data?: Record<string, unknown>;
}

export interface MultiAgentAnalysisResponse {
  success: boolean;
  data: MultiAgentAnalysisData | null;
  error: string | null;
}

export interface SubscriptionResponse {
  success?: boolean;
  subscription_id?: string;
  status?: string;
  symbol?: string;
  channel?: string;
  message?: string;
  error?: string;
}

class MCPApi {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    api.defaults.baseURL = this.baseUrl;
  }

  async getHealth(): Promise<HealthStatus> {
    const response = await api.get<HealthStatus>('/health');
    return response.data;
  }

  async getCapabilities(): Promise<Capabilities> {
    const response = await api.get<Capabilities>('/capabilities');
    return response.data;
  }

  async getQuote(symbol: string, maxAgeSec: number = 60): Promise<QuoteResponse> {
    const response = await api.post<QuoteResponse>('/invoke', {
      tool_name: 'quote.latest',
      arguments: {
        symbol: symbol.toUpperCase(),
        maxAgeSec,
      },
      agent_id: 'react_frontend',
      query_text: `Get quote for ${symbol}`,
    });
    return response.data;
  }

  async subscribeStream(
    symbol: string,
    channel: 'trades' | 'quotes' = 'trades',
  ): Promise<SubscriptionResponse> {
    const response = await api.post<SubscriptionResponse>('/subscribe', {
      symbol: symbol.toUpperCase(),
      channel,
      agent_id: 'react_frontend',
    });
    return response.data;
  }

  async unsubscribe(subscriptionId: string): Promise<SubscriptionResponse> {
    const response = await api.post<SubscriptionResponse>('/unsubscribe', {
      subscription_id: subscriptionId,
    });
    return response.data;
  }

  async chat(message: string): Promise<ChatResponse> {
    const response = await api.post<ChatResponse>('/chat', {
      message,
    });
    return response.data;
  }

  async runMultiAgentAnalysis(
    query: string,
    ticker?: string,
  ): Promise<MultiAgentAnalysisResponse> {
    const response = await api.post<MultiAgentAnalysisResponse>('/invoke', {
      tool_name: 'multi_agent_analysis',
      arguments: {
        query,
        ticker,
      },
      agent_id: 'react_frontend',
      query_text: query,
    });
    return response.data;
  }

  streamAnalysis(ticker: string, query: string, onStep: (step: SSEStep) => void): EventSource {
    const params = new URLSearchParams({
      ticker: ticker.toUpperCase(),
      query,
      api_key: API_KEY,
    });
    const url = `${this.baseUrl}/stream/analysis?${params.toString()}`;
    const es = new EventSource(url);
    es.onmessage = (event) => {
      try {
        const step: SSEStep = JSON.parse(event.data);
        onStep(step);
      } catch {
        // malformed SSE line — ignore
      }
    };
    return es;
  }

  async getMarketIndices(): Promise<{
    nifty?: { price: number; change_pct: number };
    sensex?: { price: number; change_pct: number };
    usd_inr?: number;
    timestamp?: string;
  }> {
    const response = await api.get('/market/indices');
    return response.data;
  }

  async getCryptoQuote(symbol: string): Promise<{
    symbol: string;
    price_usd: number;
    inr_price: number;
    change_pct: number;
    volume: number;
    high_24h: number;
    low_24h: number;
    source: string;
    timestamp: string;
  }> {
    const response = await api.get(`/market/crypto/${symbol}`);
    return response.data;
  }
}

export const mcpApi = new MCPApi();
