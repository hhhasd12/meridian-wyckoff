import { create } from 'zustand';

interface AppState {
  symbol: string;
  timeframe: string;
  focusBarIndex: number | null;
  setSymbol: (s: string) => void;
  setTimeframe: (tf: string) => void;
  setFocusBarIndex: (idx: number | null) => void;
}

export const useAppStore = create<AppState>()((set) => ({
  symbol: 'ETHUSDT',
  timeframe: '1d',
  focusBarIndex: null,
  setSymbol: (symbol) => set({ symbol }),
  setTimeframe: (timeframe) => set({ timeframe }),
  setFocusBarIndex: (focusBarIndex) => set({ focusBarIndex }),
}));
