# 前端核心 (core/) — Step 1

## 做什么
搭建前端骨架：插件注册机制 + 主布局 + 全局状态 + 后端通信。
做完后浏览器能看到侧边栏和空白内容区。

## 文件清单（按施工顺序）

### 1. types.ts — 前端插件接口
```typescript
import { ComponentType } from 'react';

export interface MeridianFrontendPlugin {
  id: string;
  name: string;
  icon: string;
  version: string;
  routes: { path: string; component: ComponentType; label?: string }[];
  onActivate?: () => void;
  onDeactivate?: () => void;
  dependencies?: string[];
}
```

### 2. PluginRegistry.ts — 插件注册表
```typescript
import { MeridianFrontendPlugin } from './types';

class Registry {
  private plugins = new Map<string, MeridianFrontendPlugin>();
  register(p: MeridianFrontendPlugin) { this.plugins.set(p.id, p); }
  getAll() { return Array.from(this.plugins.values()); }
  get(id: string) { return this.plugins.get(id); }
}
export const PluginRegistry = new Registry();
```

### 3. Sidebar.tsx — 侧边栏
左侧窄栏，每个插件一个图标按钮。点击切换活动插件。
```tsx
export function Sidebar({ plugins, activeId, onSwitch }: {
  plugins: MeridianFrontendPlugin[];
  activeId: string;
  onSwitch: (id: string) => void;
}) {
  return (
    <nav style={{
      width: 56, background: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', paddingTop: 12, gap: 4
    }}>
      {plugins.map(p => (
        <button key={p.id} onClick={() => onSwitch(p.id)} title={p.name}
          style={{
            width: 40, height: 40, borderRadius: 8, border: 'none',
            fontSize: 20, cursor: 'pointer',
            background: p.id === activeId ? 'var(--accent)' : 'transparent',
            color: 'var(--text-primary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
          {p.icon}
        </button>
      ))}
    </nav>
  );
}
```

### 4. AppShell.tsx — 主布局
侧边栏 + 活动插件的页面组件。
```tsx
import { useState } from 'react';
import { Sidebar } from './Sidebar';
import { PluginRegistry } from './PluginRegistry';

export function AppShell() {
  const plugins = PluginRegistry.getAll();
  const [activeId, setActiveId] = useState(plugins[0]?.id || '');
  const active = PluginRegistry.get(activeId);
  const Page = active?.routes[0]?.component;

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg-primary)' }}>
      <Sidebar plugins={plugins} activeId={activeId}
        onSwitch={(id) => {PluginRegistry.get(activeId)?.onDeactivate?.();
          setActiveId(id);
          PluginRegistry.get(id)?.onActivate?.();
        }} />
      <main style={{ flex: 1, overflow: 'hidden' }}>
        {Page && <Page />}
      </main>
    </div>
  );
}
```

### 5. stores/appStore.ts — 全局应用状态
```typescript
import { create } from 'zustand';

interface AppState {
  symbol: string;
  timeframe: string;
  setSymbol: (s: string) => void;
  setTimeframe: (tf: string) => void;
}

export const useAppStore = create<AppState>()((set) => ({
  symbol: 'ETHUSDT',
  timeframe: '1d',
  setSymbol: (symbol) => set({ symbol }),
  setTimeframe: (timeframe) => set({ timeframe }),
}));
```

### 6. stores/drawingStore.ts — 标注状态 + 撤销重做
```typescript
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
```

### 7. services/api.ts — 后端通信
```typescript
// K线数据（二进制）
export async function fetchCandles(symbol: string, tf: string) {
  const r = await fetch(`/api/datasource/candles/${symbol}/${tf}`);
  const buf = await r.arrayBuffer();
  return new Float64Array(buf);
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

// 标的列表
export const fetchSymbols = () =>
  fetch('/api/datasource/symbols').then(r => r.json());

// 标注CRUD
export const fetchDrawings = (s: string) =>
  fetch(`/api/annotation/drawings/${s}`).then(r => r.json());

export const saveDrawing = (s: string, d: any) =>
  fetch(`/api/annotation/drawings/${s}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(d)
  });

export const updateDrawingApi = (s: string, id: string, u: any) =>
  fetch(`/api/annotation/drawings/${s}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(u)
  });

export const deleteDrawingApi = (s: string, id: string) =>
  fetch(`/api/annotation/drawings/${s}/${id}`, { method: 'DELETE' });

// 特征
export const fetchFeatures = (s: string, id: string) =>
  fetch(`/api/annotation/features/${s}/${id}`).then(r => r.json());
```

### 8. services/cache.ts — IndexedDB 本地缓存
```typescript
import Dexie from 'dexie';

class MeridianCache extends Dexie {
  candles!: Dexie.Table<{ key: string; data: ArrayBuffer; timestamp: number }>;

  constructor() {
    super('meridian-cache');
    this.version(1).stores({ candles: 'key' });
  }

  async getCandles(symbol: string, tf: string) {
    const record = await this.candles.get(`${symbol}:${tf}`);
    return record?.data ?? null;
  }

  async setCandles(symbol: string, tf: string, data: ArrayBuffer) {
    await this.candles.put({
      key: `${symbol}:${tf}`,
      data,
      timestamp: Date.now()
    });
  }
}

export const cache = new MeridianCache();
```

### 9. themes/variables.css — 暗色主题
```css
:root {
  --bg-primary: #131722;
  --bg-secondary: #1e222d;
  --bg-sidebar: #0d1117;
  --bg-hover: #2a2e39;
  --border: #2a2e39;
  --accent: #2962ff;
  --accent-dim: #2962ff30;
  --text-primary: #d1d4dc;
  --text-muted: #787b86;
  --green: #26a69a;
  --red: #ef5350;
}

body {
  margin: 0;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

* { box-sizing: border-box; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #363a45; border-radius: 3px; }
```

### 10. main.tsx — 入口
```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './themes/variables.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

### 11. App.tsx — 注册插件 + 启动
```tsx
import { PluginRegistry } from './core/PluginRegistry';
import { AppShell } from './core/AppShell';
import { evolutionWorkbenchPlugin } from './plugins/evolution-workbench';

PluginRegistry.register(evolutionWorkbenchPlugin);

export function App() {
  return <AppShell />;
}
```

## 施工注意
- vite.config.ts 配置代理：`/api` → `http://localhost:6100`
- 安装依赖：`npm i klinecharts zustand zundo dexie`
- 先不管 Worker（Step 4 再加）
- 先不管图表（Step 2 再加），AppShell 里先放占位文字