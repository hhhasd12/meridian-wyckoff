async function checkResponse(r: Response) {
  if (!r.ok) throw new Error(`API ${r.url} → ${r.status} ${r.statusText}`);
  return r;
}

export async function fetchCandles(symbol: string, tf: string) {
  const r = await fetch(`/api/datasource/candles/${symbol}/${tf}`);
  await checkResponse(r);
  return r.arrayBuffer();
}

export function decodeCandlesFromBinary(raw: Float64Array) {
  const candles = [];
  for (let i = 0; i < raw.length; i += 6) {
    candles.push({
      timestamp: raw[i], open: raw[i+1], high: raw[i+2],
      low: raw[i+3], close: raw[i+4], volume: raw[i+5]
    });
  }
  return candles;
}

export async function fetchSymbols() {
  const r = await fetch('/api/datasource/symbols');
  await checkResponse(r);
  return r.json();
}

export async function fetchDrawings(s: string) {
  const r = await fetch(`/api/annotation/drawings/${s}`);
  await checkResponse(r);
  return r.json();
}

export async function saveDrawing(s: string, d: any) {
  const r = await fetch(`/api/annotation/drawings/${s}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(d)
  });
  await checkResponse(r);
  return r.json();
}

export async function updateDrawingApi(s: string, id: string, u: any) {
  const r = await fetch(`/api/annotation/drawings/${s}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(u)
  });
  await checkResponse(r);
  return r.json();
}

export async function deleteDrawingApi(s: string, id: string) {
  const r = await fetch(`/api/annotation/drawings/${s}/${id}`, { method: 'DELETE' });
  await checkResponse(r);
}

export async function fetchFeatures(s: string, id: string) {
  const r = await fetch(`/api/annotation/features/${s}/${id}`);
  await checkResponse(r);
  return r.json();
}

// ── Engine 端点（修复：需symbol/timeframe参数） ──

export async function fetchEngineState(symbol: string, timeframe: string) {
  const r = await fetch(`/api/engine/state/${symbol}/${timeframe}`);
  await checkResponse(r);
  return r.json();
}

export async function fetchEngineAllStates(symbol: string) {
  const r = await fetch(`/api/engine/state/${symbol}/all`);
  await checkResponse(r);
  return r.json();
}

export async function fetchEngineRanges(symbol: string) {
  const r = await fetch(`/api/engine/ranges/${symbol}`);
  await checkResponse(r);
  return r.json();
}

export async function fetchEngineEvents(symbol: string) {
  const r = await fetch(`/api/engine/events/${symbol}`);
  await checkResponse(r);
  return r.json();
}

// ── Backtester 端点 ──

export async function runBacktest(symbol: string, timeframe: string, params?: any) {
  const r = await fetch('/api/backtester/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, timeframe, params: params || null }),
  });
  await checkResponse(r);
  return r.json();
}

export async function fetchBacktestResult(runId: string) {
  const r = await fetch(`/api/backtester/result/${runId}`);
  await checkResponse(r);
  return r.json();
}

export async function fetchBacktestHistory() {
  const r = await fetch('/api/backtester/history');
  await checkResponse(r);
  return r.json();
}

// ── Evolution 端点 ──

export async function fetchEvolutionCases() {
  const r = await fetch('/api/evolution/cases');
  await checkResponse(r);
  return r.json();
}

export async function fetchEvolutionCaseStats() {
  const r = await fetch('/api/evolution/cases/stats');
  await checkResponse(r);
  return r.json();
}

export async function runEvolution(params?: Record<string, any>) {
  const r = await fetch('/api/evolution/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: params ? JSON.stringify(params) : undefined,
  });
  await checkResponse(r);
  return r.json();
}

export async function fetchEvolutionRuns() {
  const r = await fetch('/api/evolution/runs');
  await checkResponse(r);
  return r.json();
}

export async function fetchEvolutionRun(id: string) {
  const r = await fetch(`/api/evolution/runs/${id}`);
  await checkResponse(r);
  return r.json();
}

export async function fetchCurrentParams() {
  const r = await fetch('/api/evolution/params/current');
  await checkResponse(r);
  return r.json();
}

export async function fetchParamsHistory() {
  const r = await fetch('/api/evolution/params/history');
  await checkResponse(r);
  return r.json();
}

export async function rollbackParams(generation: number) {
  const r = await fetch('/api/evolution/params/rollback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ generation }),
  });
  await checkResponse(r);
  return r.json();
}

export async function setManualParams(params: Record<string, any>) {
  const r = await fetch('/api/evolution/params/manual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  await checkResponse(r);
  return r.json();
}
