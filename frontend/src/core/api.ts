/** REST API client — 3 endpoints matching src/api/app.py */

import type {
  AnalyzeResponse,
  BacktestDetailResponse,
  Candle,
  EvolutionResultsResponse,
  SystemSnapshot,
  TradeRecord,
  V4WyckoffState,
} from "../types/api";

const BASE_URL = "";

export async function fetchCandles(
  symbol: string,
  tf: string,
  limit = 500,
): Promise<Candle[]> {
  // symbol 含 "/" (如 "BTC/USDT")，后端路由用 {symbol:path} 匹配，
  // 不能 encodeURIComponent 否则 "/" 被转义为 %2F 导致 404
  const res = await fetch(
    `${BASE_URL}/api/candles/${symbol}/${tf}?limit=${limit}`,
  );
  if (!res.ok) throw new Error(`fetchCandles failed: ${res.status}`);
  return res.json() as Promise<Candle[]>;
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
): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, bars }),
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
