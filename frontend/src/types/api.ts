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
  // Extended fields from backend
  signal_confidence?: number;
  wyckoff_state?: string;
  entry_signal?: string;
  status?: string;
  trailing_stop_activated?: boolean;
  partial_profits_taken?: number;
  highest_price?: number;
  lowest_price?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
  risk_reward_ratio?: number;
  entry_time?: string;
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
  status?: string;
  mode?: string;
  symbols?: string[];
  timeframes?: string[];
  decision_count?: number;
  process_count?: number;
  signal_count?: number;
  last_error?: string | null;
  engine_loaded?: boolean;
  circuit_breaker_tripped?: boolean;
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
  status?: string;
  generation?: number;
  fitness?: number;
  best_fitness?: number;
  avg_fitness?: number;
  sharpe_ratio?: number;
  degradation_rate?: number;
  pbo?: number;
  monte_carlo_p?: number;
  is_running?: boolean;
  cycle_count?: number;
  max_cycles?: number;
  best_config_hash?: string;
  population_size?: number;
  // 实时评估进度
  eval_completed?: number;
  eval_total?: number;
  eval_generation?: number;
  eval_elapsed?: number;
  eval_eta?: number;
  eval_workers?: number;
}

export interface EvolutionCycleResult {
  cycle: number;
  generation: number;
  best_fitness: number;
  avg_fitness: number;
  wfa_passed: boolean;
  oos_dr: number;
  aof_passed?: boolean | null;
  adopted?: boolean;
  timestamp?: string;
  config: Record<string, unknown>;
  best_config?: Record<string, unknown>;
  _file?: string;
}

export interface EvolutionResultsResponse {
  cycles: EvolutionCycleResult[];
  total: number;
}

export interface EvolutionLatestResponse {
  cycle: EvolutionCycleResult | null;
  total: number;
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

export interface WsServerPing {
  type: "ping";
  timestamp: string;
}

export type WsServerMessage =
  | WsCandleUpdate
  | WsWyckoffState
  | WsPositionUpdate
  | WsEvolutionProgress
  | WsSystemStatus
  | WsPong
  | WsServerPing;

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

// ============================================================
// Backtest Detail (from GET /api/backtest/{cycle}/detail)
// ============================================================

export interface RLEEntry {
  v: string;
  n: number;
}

export interface BacktestTradeRecord {
  entry_bar: number;
  exit_bar: number;
  entry_price: number;
  exit_price: number;
  side: "LONG" | "SHORT";
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
  hold_bars: number;
  entry_state: string;
}

export interface BacktestDetail {
  trades: BacktestTradeRecord[];
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  equity_curve: number[];
  equity_curve_full_length: number;
  bar_phases_rle: RLEEntry[];
  bar_states_rle: RLEEntry[];
}

export interface BacktestDetailResponse {
  cycle: number;
  generation: number;
  best_fitness: number;
  adopted: boolean;
  backtest_detail: BacktestDetail | null;
  total_cycles: number;
  error?: string;
}

// ============================================================
// State Machine Analysis (POST /api/analyze)
// ============================================================

export interface AnalyzeBarDetail {
  bar_index: number;
  timestamp: string;
  p: WyckoffPhase;       // phase
  s: string;             // state
  c: number;             // confidence
  ts: number | null;     // tr_support
  tr: number | null;     // tr_resistance
  tc: number | null;     // tr_confidence
  mr: string;            // market_regime
  d: string;             // direction
  ss: string;            // signal_strength
  sc: boolean;           // state_changed
  sig: string;           // signal
  cl: Record<string, number>; // critical_levels
  // V4 additions
  pr?: { sd: number; ce: number; er: number };
  bf?: { vr: number; br: number; sa: boolean };
  hyp?: { e: string; st: string | null; c: number; bh: number; cq: number };
  lce?: string;
}

export interface AnalyzeResponse {
  symbol: string;
  timeframe: string;
  total_bars: number;
  warmup_bars: number;
  bar_details: AnalyzeBarDetail[];
  candles?: Candle[];
  error?: string;
}

// ============================================================
// V4 State Machine (from GET /api/wyckoff/state)
// ============================================================

export interface V4HypothesisInfo {
  event_name: string;
  status: "hypothetical" | "testing" | "rejected" | "exhausted" | null;
  confidence: number;
  bars_held: number;
  confirmation_quality: number;
  rejection_reason: string | null;
}

export interface V4PrincipleScores {
  supply_demand: number;  // -1 ~ +1
  cause_effect: number;   // 0 ~ 1
  effort_result: number;  // -1 ~ +1
}

export interface V4BarFeatures {
  volume_ratio: number;
  body_ratio: number;
  is_stopping_action: boolean;
  spread_vs_volume_divergence: number;
}

export interface V4EvidenceItem {
  type: string;
  value: number;
  confidence: number;
  description: string;
}

export interface V4StateMachineEntry {
  current_state: string;
  direction: string | null;
  confidence: number;
  phase: string;
  last_confirmed_event: string;
  hypothesis: V4HypothesisInfo | null;
  boundaries: Record<string, number>;
  principles: V4PrincipleScores | null;
  bar_features: V4BarFeatures | null;
  recent_evidence: V4EvidenceItem[];
}

export interface V4WyckoffState {
  timeframes: string[];
  state_machines: Record<string, V4StateMachineEntry>;
  last_candle_time: string | null;
  bar_index: number;
}
