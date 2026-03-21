/** Frontend types mirroring src/kernel/types.py */

// ============================================================
// Candle / OHLCV
// ============================================================

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// ============================================================
// Trading Signals
// ============================================================

export type TradingSignal =
  | "strong_buy"
  | "buy"
  | "neutral"
  | "sell"
  | "strong_sell"
  | "wait";

export type WyckoffSignal = "buy_signal" | "sell_signal" | "no_signal";

export type WyckoffPhase = "A" | "B" | "C" | "D" | "E" | "IDLE";

export type StateDirection =
  | "ACCUMULATION"
  | "DISTRIBUTION"
  | "TRENDING"
  | "IDLE";

// ============================================================
// Wyckoff State
// ============================================================

export interface StateEvidence {
  evidence_type: string;
  value: number;
  confidence: number;
  weight: number;
  description: string;
}

export interface WyckoffStateResult {
  current_state: string;
  phase: WyckoffPhase;
  direction: StateDirection;
  confidence: number;
  intensity: number;
  evidences: StateEvidence[];
  signal: WyckoffSignal;
  signal_strength: "strong" | "medium" | "weak" | "none";
  state_changed: boolean;
  previous_state: string | null;
  heritage_score: number;
  critical_levels: Record<string, number>;
}

// ============================================================
// Trading Range / FVG / Breakout
// ============================================================

export interface TradingRangeInfo {
  has_range: boolean;
  support: number | null;
  resistance: number | null;
  confidence: number;
  breakout_direction: "UP" | "DOWN" | null;
  resonance_score: number;
}

export interface FVGSignal {
  direction: "BULLISH" | "BEARISH";
  gap_top: number;
  gap_bottom: number;
  fill_ratio: number;
  timestamp: string | null;
}

export interface BreakoutInfo {
  is_valid: boolean;
  direction: number;
  breakout_level: number;
  breakout_strength: number;
  volume_confirmation: boolean;
}

// ============================================================
// Position / Order
// ============================================================

export interface Position {
  symbol: string;
  side?: "LONG" | "SHORT";
  entry_price?: number;
  current_price?: number;
  size?: number;
  pnl?: number;
  pnl_pct?: number;
  stop_loss?: number;
  take_profit?: number;
  leverage?: number;
}

export interface TradeRecord {
  entry_price: number;
  exit_price: number;
  side: "LONG" | "SHORT";
  size: number;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
  hold_bars: number;
  entry_state: string;
  timestamp?: string;
}

// ============================================================
// System Snapshot
// ============================================================

export interface PluginInfo {
  name: string;
  display_name: string;
  version: string;
  state: string;
}

export interface SystemSnapshot {
  uptime: number;
  is_running: boolean;
  plugin_count: number;
  plugins: PluginInfo[];
  orchestrator: OrchestratorStatus | null;
  positions: Position[] | null;
  evolution: EvolutionStatus | null;
  wyckoff_engine: WyckoffStateResult | null;
}

export interface OrchestratorStatus {
  mode?: string;
  last_decision?: {
    signal: TradingSignal;
    confidence: number;
    reasoning: string[];
    timestamp: string;
  };
  circuit_breaker?: {
    triggered: boolean;
    reason?: string;
  };
}

// ============================================================
// Evolution
// ============================================================

export interface EvolutionStatus {
  generation?: number;
  fitness?: number;
  sharpe_ratio?: number;
  degradation_rate?: number;
  pbo?: number;
  monte_carlo_p?: number;
  is_running?: boolean;
  best_config_hash?: string;
}

// ============================================================
// WebSocket Message Types
// ============================================================

export type WsTopicType =
  | "candles"
  | "wyckoff"
  | "positions"
  | "evolution"
  | "system_status";

export interface WsSubscribeMessage {
  type: "subscribe";
  topics: WsTopicType[];
}

export interface WsPingMessage {
  type: "ping";
}

export type WsClientMessage = WsSubscribeMessage | WsPingMessage;

export interface WsCandleUpdate {
  type: "candle_update";
  data: Candle;
  timestamp: string;
}

export interface WsWyckoffState {
  type: "wyckoff_state";
  data: WyckoffStateResult;
  timestamp: string;
}

export interface WsPositionUpdate {
  type: "position_update";
  data: Position[];
  timestamp: string;
}

export interface WsEvolutionProgress {
  type: "evolution_progress";
  data: EvolutionStatus;
  timestamp: string;
}

export interface WsSystemStatus {
  type: "system_status";
  data: Record<string, unknown>;
  timestamp: string;
}

export interface WsPong {
  type: "pong";
  timestamp: string;
}

export type WsServerMessage =
  | WsCandleUpdate
  | WsWyckoffState
  | WsPositionUpdate
  | WsEvolutionProgress
  | WsSystemStatus
  | WsPong;

// ============================================================
// Signal Alert (for SignalPanel)
// ============================================================

export interface SignalAlert {
  id: string;
  signal: TradingSignal;
  confidence: number;
  phase: WyckoffPhase;
  state: string;
  reasoning: string[];
  timestamp: string;
}

// ============================================================
// Log Entry
// ============================================================

export interface LogEntry {
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  message: string;
  module: string;
  timestamp: string;
}

// ============================================================
// Timeframe
// ============================================================

export const TIMEFRAMES = ["D1", "H4", "H1", "M15", "M5"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];
