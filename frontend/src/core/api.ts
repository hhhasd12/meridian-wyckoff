/** REST API client — 3 endpoints matching src/api/app.py */

import type {
  AnalyzeResponse,
  BacktestDetailResponse,
  Candle,
  ChatMessage,
  DiagnosisResponse,
  EvolutionResultsResponse,
  MatchReport,
  SystemSnapshot,
  TradeRecord,
  V4WyckoffState,
  WyckoffAnnotation,
} from "../types/api";

const BASE_URL = "";

// Timeframe mapping: backend format → Binance interval
const TF_TO_BINANCE: Record<string, string> = {
  D1: "1d",
  H4: "4h",
  H1: "1h",
  M15: "15m",
  M5: "5m",
};

/** Fetch from Binance public klines API (no auth needed) */
async function fetchBinanceCandles(
  symbol: string,
  tf: string,
  limit: number,
): Promise<Candle[]> {
  // "BTC/USDT" → "BTCUSDT"
  const binanceSymbol = symbol.replace("/", "");
  const interval = TF_TO_BINANCE[tf] ?? tf.toLowerCase();
  const path = `/api/v3/klines?symbol=${binanceSymbol}&interval=${interval}&limit=${limit}`;

  // Try multiple Binance endpoints (api.binance.com is blocked in China)
  const hosts = [
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api.binance.com",
  ];

  let lastError: Error | null = null;
  for (const host of hosts) {
    try {
      const res = await fetch(`${host}${path}`, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) continue;
      const raw: (string | number)[][] = await res.json();
      return raw.map((k) => ({
        timestamp: new Date(k[0] as number).toISOString(),
        open: parseFloat(k[1] as string),
        high: parseFloat(k[2] as string),
        low: parseFloat(k[3] as string),
        close: parseFloat(k[4] as string),
        volume: parseFloat(k[5] as string),
      }));
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
    }
  }
  throw lastError ?? new Error("All Binance endpoints failed");
}

export async function fetchCandles(
  symbol: string,
  tf: string,
  limit = 500,
): Promise<Candle[]> {
  // 1. Try backend first
  try {
    const res = await fetch(
      `${BASE_URL}/api/candles/${symbol}/${tf}?limit=${limit}`,
    );
    if (res.ok) {
      const data: Candle[] = await res.json();
      if (data.length > 0) return data;
    }
  } catch {
    // backend unreachable — fall through to Binance
  }
  // 2. Fallback: Binance public API
  return fetchBinanceCandles(symbol, tf, limit);
}

export async function fetchSnapshot(): Promise<SystemSnapshot> {
  const res = await fetch(`${BASE_URL}/api/system/snapshot`);
  if (!res.ok) throw new Error(`fetchSnapshot failed: ${res.status}`);
  return res.json() as Promise<SystemSnapshot>;
}

export async function updateConfig(
  config: Record<string, unknown>,
): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/api/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  if (!res.ok) throw new Error(`updateConfig failed: ${res.status}`);
  return res.json() as Promise<{ status: string }>;
}

export async function fetchEvolutionResults(): Promise<EvolutionResultsResponse> {
  const res = await fetch(`${BASE_URL}/api/evolution/results`);
  if (!res.ok) throw new Error(`fetchEvolutionResults failed: ${res.status}`);
  return res.json() as Promise<EvolutionResultsResponse>;
}

export async function fetchTrades(): Promise<{ trades: TradeRecord[] }> {
  const res = await fetch(`${BASE_URL}/api/trades`);
  if (!res.ok) throw new Error(`fetchTrades failed: ${res.status}`);
  return res.json() as Promise<{ trades: TradeRecord[] }>;
}

export interface AdvisorLatestResponse {
  analysis: Record<string, unknown> | null;
  status: string;
}

export async function fetchAdvisorLatest(): Promise<AdvisorLatestResponse> {
  const res = await fetch(`${BASE_URL}/api/advisor/latest`);
  if (!res.ok) throw new Error(`fetchAdvisorLatest failed: ${res.status}`);
  return res.json() as Promise<AdvisorLatestResponse>;
}

// Evolution control

export async function startEvolution(
  maxCycles = 10,
): Promise<{ status: string; message?: string }> {
  const res = await fetch(`${BASE_URL}/api/evolution/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_cycles: maxCycles }),
  });
  if (!res.ok) throw new Error(`startEvolution failed: ${res.status}`);
  return res.json() as Promise<{ status: string; message?: string }>;
}

export async function stopEvolution(): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/api/evolution/stop`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`stopEvolution failed: ${res.status}`);
  return res.json() as Promise<{ status: string }>;
}

// Decision history

export interface DecisionRecord {
  id: string;
  signal: string;
  confidence: number;
  reasoning: string[];
  timestamp?: string;
}

export async function fetchDecisions(): Promise<{
  decisions: DecisionRecord[];
  total: number;
}> {
  const res = await fetch(`${BASE_URL}/api/decisions`);
  if (!res.ok) throw new Error(`fetchDecisions failed: ${res.status}`);
  return res.json() as Promise<{ decisions: DecisionRecord[]; total: number }>;
}

// Evolution config

export async function fetchEvolutionConfig(): Promise<{
  config: Record<string, unknown>;
}> {
  const res = await fetch(`${BASE_URL}/api/evolution/config`);
  if (!res.ok) throw new Error(`fetchEvolutionConfig failed: ${res.status}`);
  return res.json() as Promise<{ config: Record<string, unknown> }>;
}

// Backtest detail

export async function fetchBacktestDetail(
  cycleIndex: number,
): Promise<BacktestDetailResponse> {
  const res = await fetch(`${BASE_URL}/api/backtest/${cycleIndex}/detail`);
  if (!res.ok) throw new Error(`fetchBacktestDetail failed: ${res.status}`);
  return res.json() as Promise<BacktestDetailResponse>;
}

// State machine analysis

export async function fetchAnalysis(
  symbol = "ETHUSDT",
  bars = 2000,
  timeframe = "H4",
): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, bars, timeframe }),
  });
  if (!res.ok) throw new Error(`fetchAnalysis failed: ${res.status}`);
  return res.json() as Promise<AnalyzeResponse>;
}

// V4 State Machine

export async function fetchV4State(): Promise<V4WyckoffState> {
  const res = await fetch(`${BASE_URL}/api/wyckoff/state`);
  if (!res.ok) throw new Error(`fetchV4State failed: ${res.status}`);
  return res.json() as Promise<V4WyckoffState>;
}

// Annotations CRUD

export async function fetchAnnotations(
  symbol: string,
  timeframe: string,
): Promise<{ annotations: WyckoffAnnotation[] }> {
  const res = await fetch(
    `${BASE_URL}/api/annotations?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
  );
  if (!res.ok) throw new Error(`fetchAnnotations failed: ${res.status}`);
  return res.json() as Promise<{ annotations: WyckoffAnnotation[] }>;
}

export async function createAnnotation(
  data: Partial<WyckoffAnnotation>,
): Promise<{ success: boolean; annotation: WyckoffAnnotation }> {
  const res = await fetch(`${BASE_URL}/api/annotations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`createAnnotation failed: ${res.status}`);
  return res.json() as Promise<{ success: boolean; annotation: WyckoffAnnotation }>;
}

export async function deleteAnnotation(
  id: string,
  symbol: string,
  timeframe: string,
): Promise<{ success: boolean }> {
  const res = await fetch(
    `${BASE_URL}/api/annotations/${id}?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(`deleteAnnotation failed: ${res.status}`);
  return res.json() as Promise<{ success: boolean }>;
}

// Annotation compare

export async function fetchAnnotationCompare(
  symbol: string,
  timeframe: string,
): Promise<MatchReport> {
  const res = await fetch(
    `${BASE_URL}/api/annotations/compare?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
  );
  if (!res.ok) throw new Error(`fetchAnnotationCompare failed: ${res.status}`);
  return res.json() as Promise<MatchReport>;
}

// Diagnosis chat

export async function sendDiagnosisChat(
  message: string,
  context: Record<string, unknown> = {},
): Promise<{ success: boolean; response: DiagnosisResponse }> {
  const res = await fetch(`${BASE_URL}/api/annotations/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context }),
  });
  if (!res.ok) throw new Error(`sendDiagnosisChat failed: ${res.status}`);
  return res.json() as Promise<{ success: boolean; response: DiagnosisResponse }>;
}

// Chat history persistence

export async function fetchChatHistory(): Promise<{
  messages: ChatMessage[];
}> {
  const res = await fetch(`${BASE_URL}/api/annotations/chat/history`);
  if (!res.ok) throw new Error(`fetchChatHistory failed: ${res.status}`);
  return res.json() as Promise<{ messages: ChatMessage[] }>;
}

export async function clearChatHistory(): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE_URL}/api/annotations/chat/history`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`clearChatHistory failed: ${res.status}`);
  return res.json() as Promise<{ success: boolean }>;
}
