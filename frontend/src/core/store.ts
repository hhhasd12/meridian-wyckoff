/** Zustand global store */

import { create } from "zustand";
import type {
  AnalyzeResponse,
  Candle,
  EvolutionCycleResult,
  EvolutionStatus,
  LogEntry,
  Position,
  SignalAlert,
  Timeframe,
  TradeRecord,
  V4WyckoffState,
  WyckoffStateResult,
} from "../types/api";
import type { WsStatus } from "./ws";

type PageId = "trading" | "evolution" | "analysis";

interface AppState {
  // Page navigation
  activePage: PageId;
  setActivePage: (p: PageId) => void;

  // Selection
  symbol: string;
  timeframe: Timeframe;
  setSymbol: (s: string) => void;
  setTimeframe: (tf: Timeframe) => void;

  // WebSocket
  wsStatus: WsStatus;
  setWsStatus: (s: WsStatus) => void;

  // Candle data (from REST initial + WS updates)
  candles: Candle[];
  setCandles: (c: Candle[]) => void;
  appendCandle: (c: Candle) => void;

  // Wyckoff state
  wyckoffState: WyckoffStateResult | null;
  setWyckoffState: (s: WyckoffStateResult) => void;

  // Positions
  positions: Position[];
  setPositions: (p: Position[]) => void;

  // Evolution
  evolution: EvolutionStatus | null;
  setEvolution: (e: EvolutionStatus) => void;

  // Evolution Cycles (history)
  evolutionCycles: EvolutionCycleResult[];
  setEvolutionCycles: (c: EvolutionCycleResult[]) => void;

  // Signals
  signals: SignalAlert[];
  addSignal: (s: SignalAlert) => void;

  // Trades
  trades: TradeRecord[];
  setTrades: (t: TradeRecord[]) => void;

  // Logs
  logs: LogEntry[];
  addLog: (l: LogEntry) => void;

  // System
  uptime: number;
  isRunning: boolean;
  setSystemInfo: (uptime: number, running: boolean) => void;

  // Advisor
  advisorAnalysis: Record<string, unknown> | null;
  setAdvisorAnalysis: (a: Record<string, unknown> | null) => void;

  // UI
  leftPanelOpen: boolean;
  rightPanelOpen: boolean;
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;
  activeBottomTab: string;
  setActiveBottomTab: (t: string) => void;

  // Analysis
  analysisData: AnalyzeResponse | null;
  setAnalysisData: (data: AnalyzeResponse | null) => void;
  isAnalyzing: boolean;
  setIsAnalyzing: (v: boolean) => void;

  // V4 State Machine
  v4State: V4WyckoffState | null;
  setV4State: (s: V4WyckoffState | null) => void;
}

const MAX_SIGNALS = 50;
const MAX_LOGS = 200;
const MAX_CANDLES = 1000;

export const useStore = create<AppState>((set) => ({
  // Page navigation
  activePage: "trading",
  setActivePage: (activePage) => set({ activePage }),

  // Selection
  symbol: "BTC/USDT",
  timeframe: "H4",
  setSymbol: (symbol) => set({ symbol }),
  setTimeframe: (timeframe) => set({ timeframe }),

  // WebSocket
  wsStatus: "disconnected",
  setWsStatus: (wsStatus) => set({ wsStatus }),

  // Candles
  candles: [],
  setCandles: (candles) => set({ candles: candles.slice(-MAX_CANDLES) }),
  appendCandle: (candle) =>
    set((state) => {
      const existing = state.candles;
      // If same timestamp, update last candle; otherwise append
      if (
        existing.length > 0 &&
        existing[existing.length - 1]!.timestamp === candle.timestamp
      ) {
        const updated = [...existing];
        updated[updated.length - 1] = candle;
        return { candles: updated };
      }
      return { candles: [...existing, candle].slice(-MAX_CANDLES) };
    }),

  // Wyckoff
  wyckoffState: null,
  setWyckoffState: (wyckoffState) => set({ wyckoffState }),

  // Positions
  positions: [],
  setPositions: (positions) => set({ positions }),

  // Evolution
  evolution: null,
  setEvolution: (evolution) => set({ evolution }),

  // Evolution Cycles
  evolutionCycles: [],
  setEvolutionCycles: (evolutionCycles) => set({ evolutionCycles }),

  // Signals
  signals: [],
  addSignal: (signal) =>
    set((state) => ({
      signals: [signal, ...state.signals].slice(0, MAX_SIGNALS),
    })),

  // Trades
  trades: [],
  setTrades: (trades) => set({ trades }),

  // Logs
  logs: [],
  addLog: (log) =>
    set((state) => ({
      logs: [log, ...state.logs].slice(0, MAX_LOGS),
    })),

  // System
  uptime: 0,
  isRunning: false,
  setSystemInfo: (uptime, isRunning) => set({ uptime, isRunning }),

  // Advisor
  advisorAnalysis: null,
  setAdvisorAnalysis: (advisorAnalysis) => set({ advisorAnalysis }),

  // UI
  leftPanelOpen: true,
  rightPanelOpen: true,
  toggleLeftPanel: () =>
    set((state) => ({ leftPanelOpen: !state.leftPanelOpen })),
  toggleRightPanel: () =>
    set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
  activeBottomTab: "positions",
  setActiveBottomTab: (activeBottomTab) => set({ activeBottomTab }),

  // Analysis
  analysisData: null,
  setAnalysisData: (analysisData) => set({ analysisData }),
  isAnalyzing: false,
  setIsAnalyzing: (isAnalyzing) => set({ isAnalyzing }),

  // V4 State Machine
  v4State: null,
  setV4State: (v4State) => set({ v4State }),
}));
