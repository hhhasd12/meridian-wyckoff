# Meridian P0 —施工提示词

> 施工执行指令。架构设计见MERIDIAN\_ARCHITECTURE.md，理论见 SYSTEM\_DESIGN\_V3.md

## 1. P0 目标

做完后用户能：启动后端+前端→浏览器看到侧边栏+进化工作台→选标的周期加载K线→画平行通道/趋势线/事件气泡并自动保存→右侧面板看标注列表点击跳转→选中标注显示7维特征→切换周期标注跟随→Ctrl+Z撤销

P0不做：实盘数据、引擎检测、进化优化、交易、AI、监控

## 2. 启动方式

后端：`python -m uvicorn backend.main:app --reload --port 8000`
前端：`cd frontend && npm run dev`
前端技术栈：`npm i klinecharts zustand zundo dexie`

vite.config.ts需配置代理 `/api` → `http://localhost:8000`，`/ws` → `ws://localhost:8000`

## 3. 后端目录结构

```
backend/
├── main.py
├── core/
│   ├── __init__.py
│   ├── types.py               # BackendPlugin基类 + PluginContext
│   ├── plugin_manager.py
│   ├── event_bus.py
│   ├── api_registry.py
│   └── storage.py
├── plugins/
│   ├── datasource/
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   ├── local_loader.py    # TSV→Polars→binary
│   │   └── routes.py
│   └── annotation/
│       ├── __init__.py
│       ├── plugin.py
│       ├── drawing_store.py   # JSON CRUD
│       ├── feature_extractor.py
│       └── routes.py
└── storage/
    └── drawings/
```

pip安装：`fastapi uvicorn polars numpy aiosqlite pydantic-settings`## 4. 后端核心框架

### core/types.py

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable
from fastapi import APIRouter

class BackendPlugin(ABC):
    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    dependencies: list = []

    @abstractmethod
    async def on_init(self, ctx: 'PluginContext') -> None: ...
    @abstractmethod
    async def on_start(self) -> None: ...
    @abstractmethod
    async def on_stop(self) -> None: ...
    async def on_health_check(self) -> dict:
        return {"status": "ok"}
    def get_router(self) -> APIRouter | None:
        return Nonedef get_subscriptions(self) -> dict[str, Callable]:
        return {}

@dataclass
class PluginContext:
    event_bus: Any
    data_pipeline: Any
    storage: Any
    config: dict
    get_plugin: Callable
```

### core/event\_bus.py

```python
import asyncio
from collections import defaultdict

class EventBus:
    def __init__(self):
        self._subs = defaultdict(list)
    def subscribe(self, event_type, handler):
        self._subs[event_type].append(handler)
    def unsubscribe(self, event_type, handler):
        self._subs[event_type].remove(handler)
    async def publish(self, event_type, data=None):
        for h in self._subs.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(h): await h(data)
                else: h(data)
            except Exception as e:
                print(f"[EventBus] Error in {event_type}: {e}")
```

### core/plugin\_manager.py

```python
class PluginManager:
    def __init__(self):
        self.plugins = {}
    async def register(self, plugin):
        for dep in getattr(plugin, 'dependencies', []):
            if dep not in self.plugins:
                raise ValueError(f"{plugin.id} depends on {dep}")self.plugins[plugin.id] = plugin
    def get_plugin(self, pid):
        return self.plugins[pid]
    async def start_all(self):
        for p in self.plugins.values():
            await p.on_start()print(f"[PM] Started: {p.id}")
    async def stop_all(self):
        for p in reversed(list(self.plugins.values())):
            await p.on_stop()
    async def health_check(self):
        r = {pid: await p.on_health_check() for pid, p in self.plugins.items()}
        ok = all(v.get("status")=="ok" for v in r.values())
        return {"status": "ok" if ok else "degraded", "plugins": r}
```

### core/api\_registry.py

```python
class APIRegistry:
    def __init__(self, app):
        self.app = appdef register_routes(self, plugin_id, router):
        self.app.include_router(router, prefix=f"/api/{plugin_id}")
```

### core/storage.py

```python
import json
from pathlib import Path

STORAGE_ROOT = Path(__file__).parent.parent / "storage"

class StorageManager:
    def __init__(self):
        STORAGE_ROOT.mkdir(exist_ok=True)
        (STORAGE_ROOT / "drawings").mkdir(exist_ok=True)(STORAGE_ROOT / "evolution").mkdir(exist_ok=True)
    def read_json(self, category, name):
        p = STORAGE_ROOT / category / f"{name}.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else None
    def write_json(self, category, name, data):
        p = STORAGE_ROOT / category / f"{name}.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
```

### main.py

````python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core.plugin_manager import PluginManager
from backend.core.event_bus import EventBus
from backend.core.api_registry import APIRegistry
from backend.core.storage import StorageManager
from backend.core.types import PluginContext

app = FastAPI(title="Meridian", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

pm = PluginManager()
bus = EventBus()
api_reg = APIRegistry(app)
store = StorageManager()

@app.on_event("startup")
async def startup():
    from backend.plugins.datasource.plugin import DataSourcePlugin
    from backend.plugins.annotation.plugin import AnnotationPlugin
    ctx = PluginContext(event_bus=bus, data_pipeline=None, storage=store, config={}, get_plugin=pm.get_plugin)
    for P in [DataSourcePlugin, AnnotationPlugin]:
        p = P()
        await pm.register(p)
        await p.on_init(ctx)r = p.get_router()
        if r: api_reg.register_routes(p.id, r)
        for et, h in p.get_subscriptions().items():
            bus.subscribe(et, h)
    await pm.start_all()

@app.on_event("shutdown")
async def shutdown():
    await pm.stop_all()

@app.get("/api/system/health")
async def health():
    return await pm.health_check()

@app.get("/api/system/plugins")
async def plugins():
    return [{"id":p.id,"name":p.name,"version":p.version} for p in pm.plugins.values()]
```## 5. 后端插件代码

### plugins/datasource/plugin.py
```python
from pathlib import Path
from backend.core.types import BackendPlugin
from .routes import create_router

class DataSourcePlugin(BackendPlugin):
    id = "datasource"
    name = "数据源"
    version = "0.1.0"
    async def on_init(self, ctx):
        self.ctx = ctx
        self.data_dir = Path(__file__).parent.parent.parent.parent / "data"
    async def on_start(self): pass
    async def on_stop(self): pass
    def get_router(self):
        return create_router(self)
````

### plugins/datasource/local\_loader.py

```python
import polars as pl
import numpy as np
from pathlib import Path

def load_tsv(filepath: Path) -> pl.DataFrame:
    df = pl.read_csv(filepath, separator="\t")
    col_map = {}
    for col in df.columns:
        lo = col.lower()
        if "time" in lo or "date" in lo: col_map[col] = "timestamp"
        elif lo in ("open","o"): col_map[col] = "open"
        elif lo in ("high","h"): col_map[col] = "high"
        elif lo in ("low","l"): col_map[col] = "low"
        elif lo in ("close","c"): col_map[col] = "close"
        elif "vol" in lo: col_map[col] = "volume"
    return df.rename(col_map).select(["timestamp","open","high","low","close","volume"])

def df_to_binary(df: pl.DataFrame) -> bytes:
    arr = np.column_stack([
        df["timestamp"].to_numpy(dtype=np.float64),
        df["open"].to_numpy(dtype=np.float64),
        df["high"].to_numpy(dtype=np.float64),
        df["low"].to_numpy(dtype=np.float64),
        df["close"].to_numpy(dtype=np.float64),
        df["volume"].to_numpy(dtype=np.float64),
    ])
    return arr.tobytes()
```

### plugins/datasource/routes.py

```python
from fastapi import APIRouter, Response
from .local_loader import load_tsv, df_to_binary

def create_router(plugin) -> APIRouter:
    router = APIRouter()

    @router.get("/candles/{symbol}/{timeframe}")
    async def get_candles(symbol: str, timeframe: str):
        data_dir = plugin.data_dir / symbol
        for ext in [".tsv", ".csv"]:
            fp = data_dir / f"{timeframe}{ext}"
            if fp.exists():
                return Response(content=df_to_binary(load_tsv(fp)),
                                media_type="application/octet-stream")
        return Response(status_code=404, content=f"Not found: {symbol}/{timeframe}")

    @router.get("/symbols")
    async def get_symbols():
        root = plugin.data_dir
        if not root.exists(): return []
        result = []
        for d in root.iterdir():
            if d.is_dir():
                tfs = [f.stem for f in d.glob("*.tsv")] + [f.stem for f in d.glob("*.csv")]
                result.append({"symbol": d.name, "timeframes": sorted(set(tfs))})
        return result

    return router
```

### plugins/annotation/plugin.py

```python
from backend.core.types import BackendPlugin
from .routes import create_router

class AnnotationPlugin(BackendPlugin):
    id = "annotation"
    name = "标注"
    version = "0.1.0"
    async def on_init(self, ctx):
        self.ctx = ctx
        self.storage = ctx.storage
    async def on_start(self): pass
    async def on_stop(self): pass
    def get_router(self):
        return create_router(self)
```

### plugins/annotation/drawing\_store.py

```python
class DrawingStore:
    def __init__(self, storage):
        self.storage = storage
    def get_all(self, symbol):
        return self.storage.read_json("drawings", symbol) or []
    def save_all(self, symbol, drawings):
        self.storage.write_json("drawings", symbol, drawings)def create(self, symbol, drawing):
        ds = self.get_all(symbol)
        ds.append(drawing)
        self.save_all(symbol, ds)
        return drawing
    def update(self, symbol, did, updates):
        ds = self.get_all(symbol)
        for i, d in enumerate(ds):
            if d["id"] == did:
                ds[i] = {**d, **updates}
                self.save_all(symbol, ds)
                return ds[i]
        return None
    def delete(self, symbol, did):
        ds = self.get_all(symbol)
        new = [d for d in ds if d["id"] != did]
        if len(new) < len(ds):
            self.save_all(symbol, new)return True
        return False
```

### plugins/annotation/feature\_extractor.py

```python
import numpy as np
import polars as pl

class FeatureExtractor:
    """提取标注事件的7维特征矩阵"""

    def extract(self, drawing: dict, candles: pl.DataFrame) -> dict:
        event_type = drawing.get("properties", {}).get("eventType")
        if not event_type:
            return {}

        event_time = drawing["points"][0]["time"]
        idx = candles.filter(pl.col("timestamp") <= event_time).height - 1
        if idx < 0:
            return {}

        bar = candles.row(idx, named=True)

        # 1. 量比
        lookback = min(20, idx)
        avg_vol = candles.slice(idx-lookback, lookback)["volume"].mean() if lookback > 0 else bar["volume"]
        volume_ratio = bar["volume"] / avg_vol if avg_vol > 0 else 1.0

        # 2. 下影线占比
        total_range = bar["high"] - bar["low"]wick_ratio = (min(bar["open"],bar["close"]) - bar["low"]) / total_range if total_range > 0 else 0

        # 3. 实体收盘位置 (0=底,1=顶)
        body_position = (bar["close"] - bar["low"]) / total_range if total_range > 0 else 0.5

        # 4. 距支撑
        lb = min(50, idx)
        recent_low = candles.slice(idx-lb, lb)["low"].min() if lb > 0 else bar["low"]
        support_distance = (bar["low"] - recent_low) / recent_low * 100 if recent_low > 0 else 0

        # 5. 努力回报率
        price_change = abs(bar["close"]-bar["open"]) / bar["open"] * 100 if bar["open"] > 0 else 0
        effort_result = price_change / volume_ratio if volume_ratio > 0 else 0

        # 6&7. 前序趋势
        tlb = min(50, idx)
        if tlb >=5:
            closes = candles.slice(idx-tlb, tlb)["close"].to_numpy()
            slope, _ = np.polyfit(np.arange(len(closes)), closes, 1)
            trend_length = tlb
            trend_slope = slope / closes.mean() if closes.mean() > 0 else 0else:
            trend_length, trend_slope = 0, 0.0

        # 后续结果
        subsequent = {}
        for ahead in [5, 10, 20]:
            fi = idx + ahead
            if fi < candles.height:
                fc = candles.row(fi, named=True)["close"]
                subsequent[f"{ahead}bar"] = round((fc-bar["close"])/bar["close"]*100, 2)

        return {
            "volume_ratio": round(volume_ratio, 2),
            "wick_ratio": round(wick_ratio, 3),
            "body_position": round(body_position, 3),
            "support_distance": round(support_distance, 2),
            "effort_result": round(effort_result, 3),
            "trend_length": trend_length,
            "trend_slope": round(trend_slope, 6),
            "subsequent_results": subsequent,
        }
```

### plugins/annotation/routes.py

```python
from fastapi import APIRouter, Request
from .drawing_store import DrawingStore

def create_router(plugin) -> APIRouter:
    router = APIRouter()
    store = DrawingStore(plugin.storage)

    @router.get("/drawings/{symbol}")
    async def get_drawings(symbol: str):
        return store.get_all(symbol)

    @router.post("/drawings/{symbol}")
    async def create_drawing(symbol: str, request: Request):
        drawing = await request.json()
        result = store.create(symbol, drawing)
        await plugin.ctx.event_bus.publish("annotation.created", result)
        return result

    @router.put("/drawings/{symbol}/{drawing_id}")
    async def update_drawing(symbol: str, drawing_id: str, request: Request):
        updates = await request.json()
        result = store.update(symbol, drawing_id, updates)
        if result:
            await plugin.ctx.event_bus.publish("annotation.updated", result)
            return result
        return {"error": "not found"}

    @router.delete("/drawings/{symbol}/{drawing_id}")
    async def delete_drawing(symbol: str, drawing_id: str):
        if store.delete(symbol, drawing_id):
            await plugin.ctx.event_bus.publish("annotation.deleted", drawing_id)
            return {"ok": True}
        return {"error": "not found"}

    return router
```

***

## 6. 前端目录结构

```
frontend/src/
├── main.tsx
├── App.tsx
├── core/
│   ├── types.ts               # MeridianFrontendPlugin接口
│   ├──PluginRegistry.ts
│   ├── AppShell.tsx
│   └── Sidebar.tsx
├── stores/
│   ├── appStore.ts            # symbol/timeframe/theme
│   └── drawingStore.ts        # drawings +undo/redo
├── shared/chart/
│   ├── ChartWidget.tsx
│   ├── DrawingToolbar.tsx
│   ├── chartUtils.ts          # Drawing↔Overlay映射
│   └── overlays/
│       ├── parallelChannel.ts
│       ├── callout.ts
│       └── phaseMarker.ts
├── plugins/evolution-workbench/
│   ├── index.ts
│   ├── EvolutionPage.tsx
│   └── panels/
│       ├── AnnotationPanel.tsx
│       └── FeaturePanel.tsx
├── services/
│   ├── api.ts
│   └── cache.ts
├── themes/
│   └── variables.css
└── utils/
    └── keyboard.ts
```

技术栈：`npm i klinecharts zustand zundo dexie`

## 7.前端核心代码

### core/types.ts

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

### core/PluginRegistry.ts

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

### core/AppShell.tsx

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
    <div style={{ display:'flex', height:'100vh', background:'var(--bg-primary)' }}>
      <Sidebar plugins={plugins} activeId={activeId} onSwitch={(id) => {PluginRegistry.get(activeId)?.onDeactivate?.();
        setActiveId(id);
        PluginRegistry.get(id)?.onActivate?.();
      }} />
      <main style={{ flex:1, overflow:'hidden' }}>
        {Page && <Page />}
      </main>
    </div>
  );
}
```

### core/Sidebar.tsx

```tsx
export function Sidebar({ plugins, activeId, onSwitch }: any) {
  return (
    <nav style={{
      width:56, background:'var(--bg-sidebar)', borderRight:'1px solid var(--border)',
      display:'flex', flexDirection:'column', alignItems:'center', paddingTop:12, gap:4
    }}>
      {plugins.map((p: any) => (
        <button key={p.id} onClick={() => onSwitch(p.id)} title={p.name}
          style={{
            width:40, height:40, borderRadius:8, border:'none', fontSize:20, cursor:'pointer',
            background: p.id===activeId ? 'var(--accent)' : 'transparent',
            color:'var(--text-primary)', display:'flex', alignItems:'center', justifyContent:'center'
          }}>
          {p.icon}
        </button>
      ))}
    </nav>
  );
}
```

### stores/appStore.ts

```typescript
import { create } from 'zustand';

interface AppState {
  symbol: string; timeframe: string;
  setSymbol: (s: string) => void;
  setTimeframe: (tf: string) => void;
}
export const useAppStore = create<AppState>()((set) => ({
  symbol: 'ETHUSDT', timeframe: '1d',
  setSymbol: (symbol) => set({ symbol }),
  setTimeframe: (timeframe) => set({ timeframe }),
}));
```

### stores/drawingStore.ts

```typescript
import { create } from 'zustand';
import { temporal } from 'zundo';

interface Drawing {
  id: string; symbol: string; type: string;
  points: { time: number; price: number }[];
  properties: Record<string, any>;
  created_at: string; updated_at: string;
}

interface State {
  drawings: Map<string, Drawing>;
  selectedId: string | null;
  addDrawing: (d: Drawing) => void;
  updateDrawing: (id: string, u: Partial<Drawing>) => void;
  deleteDrawing: (id: string) => void;
  selectDrawing: (id: string | null) => void;
  loadDrawings: (arr: Drawing[]) => void;
}

export const useDrawingStore = create<State>()(
  temporal((set) => ({
    drawings: new Map(), selectedId: null,
    addDrawing: (d) => set((s) => { const m = new Map(s.drawings); m.set(d.id, d); return { drawings: m }; }),
    updateDrawing: (id, u) => set((s) => {
      const m = new Map(s.drawings); const old = m.get(id);
      if (old) m.set(id, { ...old, ...u, updated_at: new Date().toISOString() });
      return { drawings: m };
    }),
    deleteDrawing: (id) => set((s) => {
      const m = new Map(s.drawings); m.delete(id);
      return { drawings: m, selectedId: s.selectedId===id ? null : s.selectedId };
    }),
    selectDrawing: (id) => set({ selectedId: id }),
    loadDrawings: (arr) => set(() => {
      const m = new Map<string, Drawing>(); arr.forEach(d => m.set(d.id, d));
      return { drawings: m };
    }),
  }), { limit: 50 })
);
```

### services/api.ts

```typescript
export async function fetchCandles(symbol: string, tf: string) {
  const r = await fetch(`/api/datasource/candles/${symbol}/${tf}`);
  const buf = await r.arrayBuffer();
  return new Float64Array(buf);
}

export function decodeCandlesFromBinary(raw: Float64Array) {
  const candles = [];
  for (let i = 0; i < raw.length; i += 6) {
    candles.push({ timestamp: raw[i], open: raw[i+1], high: raw[i+2], low: raw[i+3], close: raw[i+4], volume: raw[i+5] });
  }
  return candles;
}

export const fetchSymbols = () => fetch('/api/datasource/symbols').then(r => r.json());
export const fetchDrawings = (s: string) => fetch(`/api/annotation/drawings/${s}`).then(r => r.json());
export const saveDrawing = (s: string, d: any) => fetch(`/api/annotation/drawings/${s}`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(d) });
export const updateDrawingApi = (s: string, id: string, u: any) => fetch(`/api/annotation/drawings/${s}/${id}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(u) });
export const deleteDrawingApi = (s: string, id: string) => fetch(`/api/annotation/drawings/${s}/${id}`, { method:'DELETE' });
export const fetchFeatures = (s: string, id: string) => fetch(`/api/annotation/features/${s}/${id}`).then(r => r.json());
```

### services/cache.ts

````typescript
import Dexie from 'dexie';

class MeridianCache extends Dexie {
  candles!: Dexie.Table<{ key: string; data: ArrayBuffer; timestamp: number }>;
  constructor() { super('meridian-cache'); this.version(1).stores({ candles:'key' }); }
  async getCandles(s: string, tf: string) { return (await this.candles.get(`${s}:${tf}`))?.data ?? null; }
  async setCandles(s: string, tf: string, data: ArrayBuffer) { await this.candles.put({ key:`${s}:${tf}`, data, timestamp:Date.now() }); }
}
export const cache = new MeridianCache();
```## 8. KLineChart 集成

### shared/chart/overlays/parallelChannel.ts
```typescript
import { registerOverlay } from 'klinecharts';

registerOverlay({
  name: 'parallelChannel',
  totalStep: 3,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    const figs: any[] = [];
    const color = overlay.extendData?.color || '#2196F3';
    if (coordinates.length >= 2) {
      figs.push({ type:'line', attrs:{ coordinates:[coordinates[0],coordinates[1]] }, styles:{ style:'solid', color, size:1.5 } });
    }
    if (coordinates.length >= 3) {
      const oY = coordinates[2].y - coordinates[0].y;
      figs.push({ type:'line', attrs:{ coordinates:[
        { x:coordinates[0].x, y:coordinates[0].y+oY },
        { x:coordinates[1].x, y:coordinates[1].y+oY }
      ]}, styles:{ style:'solid', color, size:1.5 } });
      figs.push({ type:'polygon', attrs:{ coordinates:[
        coordinates[0], coordinates[1],
        { x:coordinates[1].x, y:coordinates[1].y+oY },
        { x:coordinates[0].x, y:coordinates[0].y+oY }
      ]}, styles:{ style:'fill', color: color+'15' } });
    }
    return figs;
  },
  performEventPressedMove: ({ currentStep, points, performPoint }) => {
    if (currentStep === 3) performPoint.timestamp = points[0].timestamp;
  }
});
````

### shared/chart/overlays/callout.ts

```typescript
import { registerOverlay } from 'klinecharts';

registerOverlay({
  name: 'callout',
  totalStep: 2,
  needDefaultPointFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    if (!coordinates.length) return [];
    const p = coordinates[0];
    const text = overlay.extendData?.text || 'SC';
    const color = overlay.extendData?.color || '#FF5252';
    return [
      { type:'rectText', attrs:{ x:p.x, y:p.y-25, text, align:'center', baseline:'middle' },
        styles:{ style:'fill', color:'#FFF', size:11, family:'monospace', backgroundColor:color, borderRadius:3, paddingLeft:4, paddingRight:4, paddingTop:2, paddingBottom:2 } },
      { type:'line', attrs:{ coordinates:[{ x:p.x, y:p.y-14 }, p] },
        styles:{ style:'dashed', color, size:1, dashedValue:[3,3] } }
    ];
  }
});
```

### shared/chart/overlays/phaseMarker.ts

```typescript
import { registerOverlay } from 'klinecharts';

registerOverlay({
  name: 'phaseMarker',
  totalStep: 2,
  needDefaultPointFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    if (!coordinates.length) return [];
    const p = coordinates[0];
    const text = overlay.extendData?.text || 'Phase A';
    const color = overlay.extendData?.color || '#FFC107';
    return [{ type:'rectText', attrs:{ x:p.x, y:p.y, text, align:'center', baseline:'top' },
      styles:{ style:'stroke', color, size:10, borderColor:color, borderSize:1, borderRadius:2, paddingLeft:6, paddingRight:6, paddingTop:2, paddingBottom:2 } }];
  }
});
```

### shared/chart/chartUtils.ts

```typescript
const TYPE_MAP: Record<string,string> = {
  trend_line:'segment', parallel_channel:'parallelChannel',
  horizontal_line:'horizontalStraightLine', vertical_line:'verticalStraightLine',
  rectangle:'rect', callout:'callout', phase_marker:'phaseMarker'
};
const REV: Record<string,string> = {};
Object.entries(TYPE_MAP).forEach(([k,v]) => REV[v]=k);

export function drawingToOverlay(d: any) {
  return {
    id: d.id, name: TYPE_MAP[d.type]||d.type,
    points: d.points.map((p:any) => ({ timestamp:p.time, value:p.price })),
    extendData: { color:d.properties.color, text:d.properties.text||d.properties.eventType, eventType:d.properties.eventType, phase:d.properties.phase },
    lock: false
  };
}

export function overlayToDrawing(o: any, symbol: string, tf: string) {
  return {
    id: o.id||crypto.randomUUID(), symbol,
    type: REV[o.name]||o.name,
    points: (o.points||[]).map((p:any) => ({ time:p.timestamp, price:p.value })),
    properties: { color:o.extendData?.color, text:o.extendData?.text, eventType:o.extendData?.eventType, phase:o.extendData?.phase, timeframe:tf },
    created_at: new Date().toISOString(), updated_at: new Date().toISOString()
  };
}

const TF_HIER = ['5m','15m','1h','4h','1d','1w'];
export function shouldShowDrawing(drawingTf: string, currentTf: string) {
  return TF_HIER.indexOf(drawingTf) >= TF_HIER.indexOf(currentTf);
}
```

### shared/chart/ChartWidget.tsx

````tsx
import { useRef, useEffect } from 'react';
import { init, dispose, Chart } from 'klinecharts';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { fetchCandles, decodeCandlesFromBinary } from '../../services/api';
import { drawingToOverlay, shouldShowDrawing } from './chartUtils';
import './overlays/parallelChannel';
import './overlays/callout';
import './overlays/phaseMarker';

export function ChartWidget({ currentTool}: { currentTool?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<Chart|null>(null);
  const { symbol, timeframe } = useAppStore();
  const { drawings } = useDrawingStore();

  useEffect(() => {
    if (!ref.current) return;
    chart.current = init(ref.current, {
      styles: {
        grid: { show:true, horizontal:{color:'#1e222d'}, vertical:{color:'#1e222d'} },
        candle: { type:'candle_solid', bar:{ upColor:'#26a69a', downColor:'#ef5350', noChangeColor:'#888' } }
      }
    });
    chart.current.createIndicator('VOL', false, { id:'vol' });
    return () => { if(ref.current) dispose(ref.current); };
  }, []);

  useEffect(() => {
    if (!chart.current) return;
    (async () => {
      const raw = await fetchCandles(symbol, timeframe);
      chart.current!.applyNewData(decodeCandlesFromBinary(raw));
    })();
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!chart.current) return;
    chart.current.removeOverlay();
    drawings.forEach(d => {
      if (shouldShowDrawing(d.properties.timeframe||timeframe, timeframe))
        chart.current!.createOverlay(drawingToOverlay(d));
    });
  }, [drawings, timeframe]);

  useEffect(() => {
    if (!chart.current || !currentTool || currentTool==='cursor') return;
    const name = { trend_line:'segment', parallel_channel:'parallelChannel', horizontal_line:'horizontalStraightLine', vertical_line:'verticalStraightLine', callout:'callout', phase_marker:'phaseMarker' }[currentTool];
    if (name) chart.current.createOverlay({ name });
  }, [currentTool]);

  return <div ref={ref} style={{ width:'100%', height:'100%', background:'#131722' }} />;
}
```## 9. 进化工作台插件

### plugins/evolution-workbench/index.ts
```typescript
import { MeridianFrontendPlugin } from '../../core/types';
import { EvolutionPage } from './EvolutionPage';

export const evolutionWorkbenchPlugin: MeridianFrontendPlugin = {
  id: 'evolution-workbench', name: '进化工作台', icon: '📐', version: '0.1.0',
  routes: [{ path: '/evolution', component: EvolutionPage }],
};
````

### plugins/evolution-workbench/EvolutionPage.tsx

```tsx
import { useState, useCallback } from 'react';
import { ChartWidget } from '../../shared/chart/ChartWidget';
import {AnnotationPanel } from './panels/AnnotationPanel';
import { FeaturePanel } from './panels/FeaturePanel';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { overlayToDrawing } from '../../shared/chart/chartUtils';
import { saveDrawing } from '../../services/api';

const TOOLS = [
  { id:'cursor', icon:'↗', key:'1' }, { id:'trend_line', icon:'╱', key:'2' },
  { id:'parallel_channel', icon:'▱', key:'3' }, { id:'horizontal_line', icon:'─', key:'4' },
  { id:'vertical_line', icon:'│', key:'5' }, { id:'callout', icon:'💬', key:'6' },
  { id:'phase_marker', icon:'🏷', key:'7' },
];

export function EvolutionPage() {
  const [tool, setTool] = useState('cursor');
  const { symbol, timeframe, setTimeframe } = useAppStore();
  const { addDrawing, selectedId, drawings } = useDrawingStore();
  const sel = selectedId ? drawings.get(selectedId) : null;

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <header style={{ height:44, background:'var(--bg-secondary)', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', padding:'0 12px', gap:8 }}>
        <span style={{ fontWeight:600 }}>{symbol}</span>
        {['5m','15m','1h','4h','1d','1w'].map(tf =>
          <button key={tf} onClick={() => setTimeframe(tf)} style={{
            padding:'4px 8px', borderRadius:4, border:'none', cursor:'pointer', fontSize:12,
            background: tf===timeframe ? 'var(--accent)' : 'transparent', color:'var(--text-primary)'
          }}>{tf}</button>
        )}
      </header>
      <div style={{ flex:1, display:'flex', overflow:'hidden' }}>
        <div style={{ width:48, background:'var(--bg-secondary)', borderRight:'1px solid var(--border)', display:'flex', flexDirection:'column', alignItems:'center', paddingTop:8, gap:2 }}>
          {TOOLS.map(t =>
            <button key={t.id} onClick={() => setTool(t.id)} title={`${t.id} (${t.key})`} style={{
              width:36, height:36, borderRadius:6, border:'none', cursor:'pointer', fontSize:16,
              background: t.id===tool ? 'var(--accent)' : 'transparent', color:'var(--text-primary)',
              display:'flex', alignItems:'center', justifyContent:'center'
            }}>{t.icon}</button>
          )}
        </div>
        <div style={{ flex:1 }}>
          <ChartWidget currentTool={tool} />
        </div><aside style={{ width:280, background:'var(--bg-secondary)', borderLeft:'1px solid var(--border)', overflow:'auto' }}>
          <AnnotationPanel />
          {sel && <FeaturePanel drawing={sel} />}
        </aside>
      </div><footer style={{ height:24, background:'var(--bg-secondary)', borderTop:'1px solid var(--border)', display:'flex', alignItems:'center', padding:'0 12px', fontSize:11, color:'var(--text-muted)' }}>
        <span>自动保存 ✓</span>
        <span style={{ marginLeft:'auto' }}>标注: {drawings.size} · {symbol} · {timeframe}</span>
      </footer>
    </div>
  );
}
```

### plugins/evolution-workbench/panels/AnnotationPanel.tsx

```tsx
import { useDrawingStore } from '../../../stores/drawingStore';

const COLORS: Record<string,string> = { SC:'#ef5350', BC:'#ef5350', AR:'#26a69a', ST:'#42a5f5', Spring:'#ffc107', UTAD:'#ffc107', SOS:'#66bb6a', SOW:'#ff7043', JOC:'#ab47bc' };

export function AnnotationPanel() {
  const { drawings, selectedId, selectDrawing } = useDrawingStore();
  const sorted = Array.from(drawings.values()).filter(d => d.properties.eventType).sort((a,b) => a.points[0]?.time - b.points[0]?.time);

  return (
    <div style={{ padding:8 }}>
      <h3 style={{ fontSize:12, color:'var(--text-muted)', margin:'0 0 8px' }}>📋 标注管理 ({sorted.length})</h3>
      {sorted.map(d => (
        <button key={d.id} onClick={() => selectDrawing(d.id)} style={{
          display:'flex', alignItems:'center', gap:8, padding:'6px 8px', borderRadius:4,
          border:'none', cursor:'pointer', width:'100%', textAlign:'left', fontSize:12,
          background: d.id===selectedId ? 'var(--accent-dim)' : 'transparent', color:'var(--text-primary)'
        }}>
          <span style={{ width:8, height:8, borderRadius:'50%', background:COLORS[d.properties.eventType]||'#888', flexShrink:0 }} />
          <span style={{ fontWeight:600 }}>{d.properties.eventType}</span><span style={{ color:'var(--text-muted)' }}>{new Date(d.points[0]?.time).toLocaleDateString()}</span>
          <span style={{ color:'var(--text-muted)', marginLeft:'auto' }}>{d.properties.timeframe}</span>
        </button>
      ))}
      {!sorted.length && <p style={{ fontSize:11, color:'var(--text-muted)', textAlign:'center', padding:16 }}>暂无标注</p>}
    </div>
  );
}
```

### plugins/evolution-workbench/panels/FeaturePanel.tsx

```tsx
import { useEffect, useState } from 'react';
import { fetchFeatures } from '../../../services/api';

export function FeaturePanel({ drawing }: { drawing: any }) {
  const [feat, setFeat] = useState<any>(null);
  useEffect(() => { fetchFeatures(drawing.symbol, drawing.id).then(setFeat); }, [drawing.id]);

  const f = feat?.features || {};
  const rows = [['量比',f.volume_ratio?`${f.volume_ratio}x`:'-'],['下影线',f.wick_ratio?`${(f.wick_ratio*100).toFixed(0)}%`:'-'],['实体位置',f.body_position?`${(f.body_position*100).toFixed(0)}%`:'-'],['距支撑',f.support_distance?`${f.support_distance}%`:'-'],['恐慌度',f.effort_result?.toFixed(3)||'-'],['趋势长度',f.trend_length?`${f.trend_length}根`:'-'],['趋势斜率',f.trend_slope?.toFixed(4)||'-']];

  return (
    <div style={{ padding:8, borderTop:'1px solid var(--border)' }}>
      <h3 style={{ fontSize:12, color:'var(--text-muted)', margin:'0 0 8px' }}>🔬 特征 — {drawing.properties.eventType||'?'}</h3>
      <table style={{ width:'100%', fontSize:11 }}><tbody>
        {rows.map(([l,v]) => <tr key={l as string}><td style={{ color:'var(--text-muted)', padding:'3px 0' }}>{l}</td><td style={{ textAlign:'right' }}>{v}</td></tr>)}
      </tbody></table>{f.subsequent_results && <div style={{ marginTop:8, fontSize:10}}>
        {Object.entries(f.subsequent_results).map(([k,v]:any) =>
          <span key={k} style={{ marginRight:8, color: v>0?'#26a69a':v<0?'#ef5350':'#888' }}>{k}: {v>0?'+':''}{v}%</span>
        )}
      </div>}
    </div>
  );
}
```

## 10. 主题与入口

### themes/variables.css

```css
:root {
  --bg-primary: #131722; --bg-secondary: #1e222d; --bg-sidebar: #0d1117;
  --bg-hover: #2a2e39; --border: #2a2e39;
  --accent: #2962ff; --accent-dim: #2962ff30;
  --text-primary: #d1d4dc; --text-muted: #787b86;
  --green: #26a69a; --red: #ef5350;
}
body { margin:0; background:var(--bg-primary); color:var(--text-primary); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
* { box-sizing:border-box; }
::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-thumb { background:#363a45; border-radius:3px; }
```

### main.tsx

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './themes/variables.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
```

### App.tsx

```tsx
import { PluginRegistry } from './core/PluginRegistry';
import { AppShell } from './core/AppShell';
import { evolutionWorkbenchPlugin } from './plugins/evolution-workbench';

PluginRegistry.register(evolutionWorkbenchPlugin);

export function App() { return <AppShell />; }
```

## 11. 快捷键

### utils/keyboard.ts

```typescript
export function setupKeyboard(setTool: (t:string)=>void,undo: ()=>void, redo: ()=>void, del: ()=>void) {
  const map: Record<string,string> = { '1':'cursor','2':'trend_line','3':'parallel_channel','4':'horizontal_line','5':'vertical_line','6':'callout','7':'phase_marker' };
  const h = (e: KeyboardEvent) => {
    if (map[e.key]) { setTool(map[e.key]); return; }
    if (e.key==='Escape') setTool('cursor');
    if (e.key==='Delete') del();
    if (e.ctrlKey && e.key==='z') { e.preventDefault(); undo(); }
    if (e.ctrlKey && e.key==='y') { e.preventDefault(); redo(); }
  };
  window.addEventListener('keydown', h);
  return () => window.removeEventListener('keydown', h);
}
```

## 12. 验收标准（19条）

| #  | 功能    | 条件                                         |
| -- | ----- | ------------------------------------------ |
| 1  | 启动    | 后端+前端启动 →浏览器看到侧边栏+进化工作台                    |
| 2  | K线    | 选ETHUSDT日线 → 图表显示K线+成交量                    |
| 3  | 周期    | 切换5m/1H/4H/D → 图表更新                        |
| 4  | 趋势线   | 画线 → 松开后保持                                 |
| 5  | 通道    | 画平行通道 → 半透明填充                              |
| 6  | 水平线   | 画水平线 → 延伸两端                                |
| 7  | 气泡    | 画事件气泡 → 文字标记                               |
| 8  | 拖拽    | 点击标注 → 拖锚点 →跟随                             |
| 9  | 删除    | 选中 → Del → 删除                              |
| 10 | 撤销    | Ctrl+Z → 撤销                                |
| 11 | 保存    | 画完 → 刷新 → 标注仍在                             |
| 12 | 面板    | 右侧标注列表 → 点击跳转                              |
| 13 | 特征    | 选中事件标注 → 显示7维特征                            |
| 14 | 多周期   | 日线标注 → 切4H →仍可见                            |
| 15 | 快捷键   | 数字键切工具、Esc回光标                              |
| 16 | 插件栏   | 侧边栏📐图标 → 点击无报错                            |
| 17 | 健康    | GET /api/system/health → 200               |
| 18 | 标的    | GET /api/datasource/symbols → 列表           |
| 19 | 保存API | POST /api/annotation/drawings/ETHUSDT → 成功 |

## 13. 施工顺序

**Day 1: 后端**

1. 创建backend/目录结构
2. 实现core/（types,plugin\_manager,event\_bus,api\_registry,storage）
3. 实现datasource插件（local\_loader+routes）
4. 实现annotation插件（drawing\_store+routes）
5. 实现main.py
6. 验证：GET /api/system/health → 200

**Day 2: 前端核心**

1. 初始化frontend/（Vite+React+TS）
2. 安装依赖（klinecharts,zustand,zundo,dexie）
3. 实现core/（types,PluginRegistry,AppShell,Sidebar）
4. 实现stores/（appStore,drawingStore）
5. 实现services/（api.ts,cache.ts）
6. 实现ChartWidget +注册3个自定义Overlay
7. 验证：浏览器 → 侧边栏 + K线图表

**Day 3: 画图工具**

1. 实现DrawingToolbar
2. 实现Drawing↔Overlay映射（chartUtils）
3. 对接绘制完成回调 → store → POST后端
4. 从后端加载Drawing →渲染到图表
5. 验证：画通道/线/气泡 → 刷新后仍在

**Day 4: 面板+收尾**

1. 实现AnnotationPanel
2. 实现FeaturePanel
3. 实现快捷键
4. 实现多周期同步
5. 主题CSS
6. 全部19条验收通过 ✓

***

**注意事项：**

- 不要自己渲染K线，用KLineChart
- 不要自己画标注，用KLineChart Overlay
- 不要存像素坐标，只存数据坐标（timestamp+price）
- 自动保存用debounce 1秒
- KLineChart用v10.x，文档：<https://klinecharts.com/>
- 旧代码在src/目录，P0用新的backend/目录

