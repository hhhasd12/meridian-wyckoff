/** REST API client — 3 endpoints matching src/api/app.py */

import type { Candle, SystemSnapshot } from "../types/api";

const BASE_URL = "";

export async function fetchCandles(
  symbol: string,
  tf: string,
  limit = 500,
): Promise<Candle[]> {
  const encoded = encodeURIComponent(symbol);
  const res = await fetch(
    `${BASE_URL}/api/candles/${encoded}/${tf}?limit=${limit}`,
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
