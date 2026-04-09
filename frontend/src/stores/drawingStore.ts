import { create } from 'zustand';
import { temporal } from 'zundo';

interface Drawing {
  id: string;
  symbol: string;
  type: string;
  points: { time: number; price: number }[];
  properties: Record<string, any>;
  created_at: string;
  updated_at: string;
}

interface DrawingState {
  drawings: Map<string, Drawing>;
  selectedId: string | null;
  addDrawing: (d: Drawing) => void;
  updateDrawing: (id: string, u: Partial<Drawing>) => void;
  deleteDrawing: (id: string) => void;
  selectDrawing: (id: string | null) => void;
  loadDrawings: (arr: Drawing[]) => void;
}

export const useDrawingStore = create<DrawingState>()(
  temporal((set) => ({
    drawings: new Map(),
    selectedId: null,
    addDrawing: (d) => set((s) => {
      const m = new Map(s.drawings); m.set(d.id, d);
      return { drawings: m };
    }),
    updateDrawing: (id, u) => set((s) => {
      const m = new Map(s.drawings);
      const old = m.get(id);
      if (old) m.set(id, { ...old, ...u, updated_at: new Date().toISOString() });
      return { drawings: m };
    }),
    deleteDrawing: (id) => set((s) => {
      const m = new Map(s.drawings); m.delete(id);
      return { drawings: m, selectedId: s.selectedId === id ? null : s.selectedId };
    }),
    selectDrawing: (id) => set({ selectedId: id }),
    loadDrawings: (arr) => set(() => {
      const m = new Map<string, Drawing>();
      arr.forEach(d => m.set(d.id, d));
      return { drawings: m };
    }),
  }), { limit: 50 })
);
