# Meridian 前端面板施工提示词（2026-04-09）

## 概述

在进化工作台右侧栏新增3个面板，通过Tab切换。现有标注功能不受影响。

**架构决策**：
- 右侧栏顶部增加4个Tab：📋标注 | 🧪回测 | 🧬进化 |⚙️引擎
- 宽度从260px增至280px
- 每个Tab对应一个独立Panel组件
- 通过appStore新增 `focusBarIndex` 字段实现"点击事件定位到K线图"（事件无timestamp，仅有bar_index）

---

## 1. api.ts 修改

路径：`frontend/src/services/api.ts`

### 1.1 新增：Backtester 端点（3个）

```typescript
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
```

### 1.2 修复：Engine 端点（需要symbol/timeframe参数）

现有的4个engine端点缺少路径参数，需要修改为：

```typescript
// ── Engine 端点（修复） ──

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
```

删除原来的无参数版本 `engineStep()`（后端无此端点）。

---

## 2. appStore.ts 修改

路径：`frontend/src/stores/appStore.ts`

新增 `focusBarIndex` 字段，用于BacktestPanel点击事件时通知ChartWidget滚动定位。

**为什么用 bar_index 而不是 timestamp**：runner.py 输出的事件只有 bar_index（= sequence_end_bar），没有 timestamp。bar_index 与 ChartWidget 的数据索引一致（两者使用相同的 datasource K线数据）。

```typescript
interface AppState {
  symbol: string;
  timeframe: string;
  focusBarIndex: number | null;  // ← 新增
  setSymbol: (s: string) => void;
  setTimeframe: (tf: string) => void;
  setFocusBarIndex: (idx: number | null) => void;  // ← 新增
}
```

---

## 3. ChartWidget.tsx 修改

路径：`frontend/src/shared/chart/ChartWidget.tsx`

新增一个 `useEffect` 监听 `focusBarIndex` 变化，调用 KLineChart 的滚动方法：

```typescript
const focusBarIndex = useAppStore(s => s.focusBarIndex);

useEffect(() => {
  if (focusBarIndex === null || !chartRef.current) return;
  // KLineChart API: scrollToDataIndex(dataIndex)
  chartRef.current.scrollToDataIndex(focusBarIndex);
  // 消费后清空，防止重复触发
  useAppStore.getState().setFocusBarIndex(null);
}, [focusBarIndex]);
```

**注意**：需要确认 KLineChart 的实际 API 方法名。可能是 `scrollToDataIndex()` 或 `scrollByDataIndex()` 或其他。施工时查阅 KLineChart 文档确认。

---

## 4. BacktestPanel.tsx

路径：`frontend/src/plugins/evolution-workbench/panels/BacktestPanel.tsx`

### 4.1 后端响应数据结构

**POST /api/backtester/run返回（摘要，不含完整事件列表）：**
```json
{
  "run_id": "abc12345",
  "total_bars": 500,
  "total_events": 12,
  "total_transitions": 8,
  "score": {
    "detection_rate": 0.75,
    "false_positive_rate": 0.20,
    "phase_accuracy": 0.60,
    "avg_time_offset": 1.5,
    "matched_count": 6,
    "missed_count": 2,
    "false_positive_count": 3,
    "total_annotations": 8,
    "total_engine_events": 9,
    "matched": [{ "annotation": {...}, "engine_event": {...}, "offset": 1 }],
    "missed": [{ "event_type": "st", "bar_index": 42 }],
    "false_positives": [{ "bar_index": 55, "event_type": "ar", ... }],
    "note": "无标注数据时会出现此字段"
  }
}
```

**GET /api/backtester/history 返回：**
```json
{
  "runs": [{
    "run_id": "abc12345",
    "symbol": "ETHUSDT",
    "timeframe": "1d",
    "total_bars": 500,
    "total_events": 12,
    "score_summary": {
      "detection_rate": 0.75,
      "false_positive_rate": 0.20
    }
  }]
}
```

**GET /api/backtester/result/{run_id} 返回（完整数据）：**

⚠️ 以下字段来自 runner.py 实际代码（5.24KB），已验证。

```json
{
  "run_id": "abc12345",
  "symbol": "ETHUSDT",
  "timeframe": "1d",
  "result": {
    "total_bars": 500,
    "events": [{
      "event_type": "sc",
      "event_result": "success",
      "bar_index": 10,
      "sequence_start_bar": 8,
      "sequence_length": 3,
      "position_in_range": 0.12,
      "volume_ratio": 2.3,
      "variant_tag": "climax"
    }],
    "transitions": [{
      "from_phase": "none",
      "to_phase": "a",
      "trigger_rule": "sc_confirmed",
      "bar_index": 15
    }],
    "timeline": [{
      "bar_index": 0,
      "phase": "none",
      "direction": null,
      "has_active_range": false,
      "events_this_bar": 0
    }]
  },
  "score": { ... }
}
```

**⚠️ 重要：事件没有 timestamp 字段！** 只有 bar_index。
"点击事件定位到K线图"需要使用 bar_index → scrollToDataIndex，不能用 timestamp。

### 4.2 组件状态

```typescript
const [loading, setLoading] = useState(false);
const [result, setResult] = useState<any>(null);        // 最近一次回测结果
const [history, setHistory] = useState<any[]>([]);       // 历史列表
const [detail, setDetail] = useState<any>(null);         // 展开的详情
const [view, setView] = useState<'trigger' | 'detail'>('trigger'); // 视图切换
```

### 4.3 UI布局（三区域纵向排列）

#### 区域A：触发区
```
┌─────────────────────────────┐
│🧪 回测                     │
│                             │
│  ETHUSDT · 1d               │  ← 从appStore读取，只读显示
│  [▶ 运行回测]               │  ← 按钮，loading时显示spinner
│                             │
│⚠ 需要先标注才能评分       │  ← 无标注时的提示（灰色小字）
└─────────────────────────────┘
```

-按钮点击 → `runBacktest(symbol, timeframe)` → loading → 结果写入state
- 按钮禁用条件：`loading === true`

#### 区域B：评分卡片（有结果时显示）
```
┌─────────────────────────────┐
│  检测率    75.0%    ████░░│  ← 绿色进度条
│  误报率    20.0%    ██░░░░  │  ← 红色进度条
│  阶段准确  60.0%    ███░░░  │  ←蓝色进度条
│  平均偏移  1.5 bars│  ← 纯文字
│─────────────────────────────│
│匹配 6 ·漏报 2 · 误报 3  │  ← 三色数字
│  标注 8 · 引擎 9 · 共500bar│
└─────────────────────────────┘
```

- `detection_rate` →绿色 `#26a69a`
- `false_positive_rate` → 红色 `#ef5350`
- `phase_accuracy` → 蓝色 `#42a5f5`
- 进度条用简单的div背景色+宽度百分比实现

#### 区域C：历史列表
```
┌─────────────────────────────┐
│📜 历史 (3)                │
│─────────────────────────────│
│  abc1231d  检测75% 误报20%│  ← 点击展开详情
│  def456  4h  检测60% 误报30%│
│  ghi789  1d  检测80% 误报15%│
└─────────────────────────────┘
```

- 组件挂载时 `fetchBacktestHistory()` 加载
- 回测完成后也刷新列表
- 点击某行→ `fetchBacktestResult(run_id)` → 切换到详情视图

#### 区域D：详情视图（点击历史项后显示）
```
┌─────────────────────────────┐
│  ← 返回    abc123           │  ← 返回按钮
│─────────────────────────────│
│  事件列表 (12)              │
│  🔴 SCbar:10  vol:2.3x✓ │  ← 点击 → setFocusBarIndex
│  🟢 AR  bar:18  vol:1.8x ✓ │
│  🔵 ST  bar:35  vol:0.6x ✓ │
│  ...│
│─────────────────────────────│
│  阶段转换 (8)│
│  bar:15  none → Asc_conf  │  ← 含trigger_rule
│  bar:42  A → B    st_conf   │
│  ...                        │
└─────────────────────────────┘
```

- 事件列表每行可点击 → `useAppStore.getState().setFocusBarIndex(event.bar_index)` → ChartWidget滚动到该位置
- 事件类型颜色复用 `wyckoffEvents.ts` 中的 `getEventColor()` 函数
- 事件类型显示大写（后端返回小写，前端 `.toUpperCase()`）
- 显示字段：event_type · bar_index · volume_ratio · variant_tag
- event_result用图标表示：success=✓绿 / failed=✗红

### 4.4 交互逻辑

```typescript
// 运行回测
const handleRun = async () => {
  setLoading(true);
  try {
    const res = await runBacktest(symbol, timeframe);
    setResult(res);
    // 刷新历史
    const hist = await fetchBacktestHistory();
    setHistory(hist.runs || []);
  } catch (e) {
    console.error('回测失败:', e);
  } finally {
    setLoading(false);
  }
};

// 查看详情
const handleViewDetail = async (runId: string) => {
  const detail = await fetchBacktestResult(runId);
  setDetail(detail);
  setView('detail');
};

// 点击事件定位（使用bar_index，事件无timestamp）
const handleEventClick = (barIndex: number) => {
  useAppStore.getState().setFocusBarIndex(barIndex);
};
```

---

## 5. EvolutionPanel.tsx

路径：`frontend/src/plugins/evolution-workbench/panels/EvolutionPanel.tsx`

### 5.1 后端响应数据结构

**POST /api/evolution/run 返回：**

⚠️ 以下字段来自 plugin.py 实际代码（12.35KB），已验证。此端点不接受 body 参数。

成功（有参数变化）：
```json
{
  "run_id": "uuid...",
  "status": "completed",
  "params_version": "v_evo_abc123",
  "changes": 3,
  "params_diff": {
    "st_max_distance_pct": { "before": 0.05, "after": 0.042 },
    "volume_climax_ratio": { "before": 3.0, "after": 2.8 }
  }
}
```

成功（无变化 / 无案例）：
```json
{ "run_id": "...", "status": "completed", "message": "无需优化" }
{ "run_id": "...", "status": "completed", "message": "无案例可优化" }
```

错误：
```json
{ "error": "插件未初始化" }
```

**GET /api/evolution/cases/stats 返回：**

⚠️ 以下字段来自 case_store.py get_stats() 实际代码（15.01KB），已验证。

```json
{
  "sc": {
    "event_type": "sc",
    "total": 5,
    "successes": 4,
    "rejected": 1,
    "avg_volume_ratio": 2.5,
    "avg_penetration_depth": 0.032,
    "avg_recovery_speed": 0.5,
    "avg_effort_vs_result": 0.3,
    "success_rate": 0.8
  },
  "ar": { ... },
  "st": { ... }
}
```

**注意字段名**：是 `successes`（复数）不是 `success`，无`failed` 字段。
`success_rate` 是计算字段 = successes / total。

**GET /api/evolution/params/current 返回：**
EngineParams 的完整 dict（嵌套结构，通过 `asdict()` 序列化），包含各事件类型的子参数。

**注意**：实际代码使用 `EngineParams`（不是 `EventEngineParams`），施工时先调一次此端点确认实际 JSON key 名称。

### 5.2 组件状态

```typescript
const [loading, setLoading] = useState(false);
const [stats, setStats] = useState<any>(null);
const [params, setParams] = useState<any>(null);
const [optimizeResult, setOptimizeResult] = useState<any>(null);
```

### 5.3 UI布局（三区域纵向排列）

#### 区域A：优化控制
```
┌─────────────────────────────┐
│  🧬 进化                    │
│                             │
│  [▶ 优化参数]               │  ← 按钮
│                             │
│  上次优化：修改了2个参数     │  ← 优化后显示diff摘要
│  · st_max_distance: 5%→4.2% │
│  · volume_climax: 3.0→2.8   │
└─────────────────────────────┘
```

- 优化按钮 → `runEvolution()` → 显示结果
- 检查返回的 `status` 和 `message` 字段处理边界情况（无案例/无变化）
- 有 `params_diff` 时显示diff列表，用绿色/红色标注变化方向（值变小=绿色收紧，值变大=红色放宽）
- 显示 `changes` 数量和 `params_version`

#### 区域B：案例统计
```
┌─────────────────────────────┐
│  📊 案例库                  │
│─────────────────────────────│
│  SC████░4/5   80%     │  ← 彩色进度条+成功率
│  AR   █████  3/3   100%    │
│  ST   ████░  6/8   75%     │
│  Spring ██░  2/4   50%     │
│  ...                        │
│─────────────────────────────│
│  总计: 23个案例             │
└─────────────────────────────┘
```

- 组件挂载时 `fetchEvolutionCaseStats()` 加载
- 每种事件类型一行：类型名 + 进度条 + successes/total + success_rate百分比
- 进度条宽度 = `success_rate * 100%`
- 进度条颜色：>80% 绿色，50-80% 蓝色，<50% 橙色
- 可选：鼠标悬停显示 avg_volume_ratio 和 avg_penetration_depth

#### 区域C：当前参数
```
┌─────────────────────────────┐
│  ⚙ 参数 v1712345_abc│  ← 版本号
│─────────────────────────────│
│  SC         │
│    volume_climax    3.0x│
│    min_range_pct    0.5%    │
│  ST                         │
│    max_distance     5.0%    │
│    volume_dryup     0.8x    │
│  Spring     │
│    penetrate_depth0.3%    │
│  ...                        │
└─────────────────────────────┘
```

- 组件挂载时 `fetchCurrentParams()` 加载
- 按事件类型分组显示关键参数
- 只显示最重要的参数（不要全部展开，太多了）
- 关键参数列表（从optimizer.py的PARAM_MAPPINGS提取）：
  - SC: `volume_climax_ratio`
  - AR: `ar_min_bounce_pct`
  - ST: `st_max_distance_pct`, `volume_dryup_ratio`
  - Spring: `penetrate_min_depth`
  - Breakout: `breakout_depth`

### 5.4 参数路径映射

后端params是嵌套结构。前端显示时需要按路径读取：

```typescript
// 从嵌套params中按路径取值
function getParam(params: any, path: string): any {
  return path.split('.').reduce((obj, key) => obj?.[key], params);
}

// 关键参数展示列表
const KEY_PARAMS = [
  { group: 'SC/BC', path: 'sc.volume_climax_ratio', label: '量比阈值', unit: 'x' },
  { group: 'AR', path: 'ar.min_bounce_pct', label: '最小反弹', unit: '%' },
  { group: 'ST', path: 'st.max_distance_pct', label: '最大距离', unit: '%' },
  { group: 'ST', path: 'st.volume_dryup_ratio', label: '缩量阈值', unit: 'x' },
  { group: 'Spring', path: 'spring.penetrate_min_depth', label: '穿越深度', unit: '%' },
  { group: 'Breakout', path: 'breakout.breakout_depth', label: '突破深度', unit: '%' },
];
```

**⚠️ 注意**：以上路径名是基于optimizer.py PARAM_MAPPINGS推断的。施工时需要先调一次 `GET /api/evolution/params/current` 确认实际的JSON key名称，然后调整路径。

---

## 6. EngineStatePanel.tsx

路径：`frontend/src/plugins/evolution-workbench/panels/EngineStatePanel.tsx`

### 6.1 后端响应数据结构

**GET /api/engine/state/{symbol}/{tf} 返回：**
```json
{
  "symbol": "ETHUSDT",
  "timeframe": "1d",
  "current_phase": "b",
  "structure_type": "accumulation",
  "direction": "bullish",
  "confidence": 0.72,
  "active_range": null,
  "bar_count": 150,
  "params_version": "v1712345_abc",
  "recent_events": [{
    "event_id": "...",
    "event_type": "sc",
    "event_result": "success",
    "start_bar": 10,
    "end_bar": 12,
    "price_extreme": 3200.5,
    "confidence": 0.85
  }]
}
```

### 6.2 组件状态

```typescript
const [state, setState] = useState<any>(null);
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
```

### 6.3 UI布局

#### 区域A：状态概览
```
┌─────────────────────────────┐
│  ⚙ 引擎状态                │
│                             │
│  [刷新]                     │
│                             │
│        Phase B              │  ← 大字，阶段颜色
│     ACCUMULATION            │  ← 结构类型
│       ▲ Bullish             │  ← 方向+箭头，绿色/红色
│                             │
│  信心:████████░░ 72%      │  ← 进度条
│  K线: 150 根                │
│  参数: v1712..abc           │
└─────────────────────────────┘
```

- 阶段显示大写字母+全名：`Phase A` / `Phase B` / `Phase C` / `Phase D` / `Phase E`
- 方向：bullish=绿色▲ / bearish=红色▼ / neutral=灰色●
- 结构类型：ACCUMULATION=绿底/ DISTRIBUTION=红底 / UNKNOWN=灰底
- 信心值进度条：>70%绿色，40-70%蓝色，<40%橙色

#### 区域B：最近事件
```
┌─────────────────────────────┐
│  📡 最近事件 (5)            │
│─────────────────────────────│
│🔴 SC  bar:10✓ 0.85     │  ← 类型·位置·结果·信心
│  🟢 AR  bar:18  ✓ 0.72     │
│  🔵 ST  bar:35  ✓ 0.90     │
│  🟡 Spring bar:52✓ 0.65│
│  🟣 JOC bar:68 ✓ 0.78│
└─────────────────────────────┘
```

- 事件颜色复用 wyckoffEvents.ts
- event_result: success=✓绿色 / failed=✗红色/ skipped=○灰色
- 点击事件行不需要定位功能（引擎事件没有timestamp，只有bar_index）

### 6.4 数据加载

```typescript
const { symbol, timeframe } = useAppStore();

const loadState = async () => {
  setLoading(true);
  setError(null);
  try {
    const s = await fetchEngineState(symbol, timeframe);
    setState(s);
  } catch (e: any) {
    setError(e.message || '加载失败');
    setState(null);
  } finally {
    setLoading(false);
  }
};

//挂载时加载 + symbol/timeframe变化时重新加载
useEffect(() => { loadState(); }, [symbol, timeframe]);
```

**注意**：引擎状态需要引擎先处理过数据才有内容。如果引擎未运行，后端可能返回默认空状态或404。面板需要优雅处理这种情况，显示"引擎未运行，请先运行回测或启动引擎"。

---

## 7. EvolutionPage.tsx 修改

路径：`frontend/src/plugins/evolution-workbench/EvolutionPage.tsx`

### 7.1 新增导入

```typescript
import { BacktestPanel } from './panels/BacktestPanel';
import { EvolutionPanel } from './panels/EvolutionPanel';
import { EngineStatePanel } from './panels/EngineStatePanel';
```

### 7.2 新增Tab状态

```typescript
type SidebarTab = 'annotate' | 'backtest' | 'evolution' | 'engine';
const [activeTab, setActiveTab] = useState<SidebarTab>('annotate');
```

### 7.3 右侧栏改造

将现有的右侧栏：
```tsx
<div style={{ width: 260, borderLeft: '1px solid var(--border)', overflow: 'auto', background: 'var(--bg-secondary)' }}>
  <AnnotationPanel />
  {sel &&<FeaturePanel drawing={sel} />}
</div>
```

替换为：
```tsx
<div style={{
  width: 280,
  borderLeft: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  background: 'var(--bg-secondary)',
}}>
  {/* Tab栏 */}
  <div style={{
    display: 'flex',
    borderBottom: '1px solid var(--border)',
    flexShrink: 0,
  }}>
    {([
      { id: 'annotate', icon: '📋', label: '标注' },
      { id: 'backtest', icon: '🧪', label: '回测' },
      { id: 'evolution', icon: '🧬', label: '进化' },
      { id: 'engine', icon: '⚙', label: '引擎' },
    ] as const).map(tab => (
      <button
        key={tab.id}
        onClick={() => setActiveTab(tab.id)}
        style={{
          flex: 1,
          padding: '8px 0',
          border: 'none',
          cursor: 'pointer',
          fontSize: 11,
          background: activeTab === tab.id ? 'var(--bg-primary)' : 'transparent',
          color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
          borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
        }}
      >
        {tab.icon} {tab.label}
      </button>
    ))}
  </div>

  {/* Tab内容 */}
  <div style={{ flex: 1, overflow: 'auto' }}>
    {activeTab === 'annotate' && (
      <>
        <AnnotationPanel />
        {sel && <FeaturePanel drawing={sel} />}
      </>
    )}
    {activeTab === 'backtest' &&<BacktestPanel />}
    {activeTab === 'evolution' && <EvolutionPanel />}
    {activeTab === 'engine' && <EngineStatePanel />}
  </div>
</div>
```

### 7.4 Footer更新

```tsx
<div style={{
  padding: '4px 12px',
  borderTop: '1px solid var(--border)',
  fontSize: 11,
  color: 'var(--text-muted)',
  display: 'flex',
  justifyContent: 'space-between',
}}>
  <span>标注: {drawings.size} · {symbol} · {timeframe}</span>
  <span style={{ color: 'var(--text-muted)' }}>Meridian</span>
</div>
```

---

## 8. 样式规范

所有面板统一遵循现有设计语言：

### 8.1 通用样式

```typescript
// 面板容器
const panelStyle = { padding: 8 };

// 面板标题
const titleStyle = { fontSize: 13, fontWeight: 600, marginBottom: 8 };

// 分隔线
const dividerStyle = { borderTop: '1px solid var(--border)', margin: '8px 0' };

// 按钮（主要）
const primaryButtonStyle = {
  width: '100%',
  padding: '8px 12px',
  borderRadius: 6,
  border: 'none',
  cursor: 'pointer',
  fontSize: 12,
  fontWeight: 600,
  background: 'var(--accent)',
  color: '#fff',
};

// 按钮（禁用）
const disabledButtonStyle = {
  ...primaryButtonStyle,
  opacity: 0.5,
  cursor: 'not-allowed',
};

// 列表项
const listItemStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '6px 8px',
  borderRadius: 4,
  border: 'none',
  cursor: 'pointer',
  width: '100%',
  textAlign: 'left' as const,
  fontSize: 12,
  background: 'transparent',
  color: 'var(--text-primary)',
};

// 进度条容器
const progressBarContainer = {
  height: 4,
  borderRadius: 2,
  background: 'var(--bg-primary)',
  overflow: 'hidden',
};

// 空状态
const emptyStyle = {
  fontSize: 11,
  color: 'var(--text-muted)',
  textAlign: 'center' as const,
  padding: 16,
};
```

### 8.2 颜色映射

```typescript
// 事件类型颜色（与AnnotationPanel一致）
const EVENT_COLORS: Record<string, string> = {
  sc: '#ef5350', bc: '#ef5350',
  ar: '#26a69a',
  st: '#42a5f5',
  spring: '#ffc107', utad: '#ffc107',
  sos: '#66bb6a', sow: '#ff7043',
  joc: '#ab47bc',
};

// 方向颜色
const DIRECTION_COLORS = {
  bullish: '#26a69a',
  bearish: '#ef5350',
  neutral: '#787b86',
};

// 结构类型颜色
const STRUCTURE_COLORS = {
  accumulation: '#26a69a20',  // 半透明绿
  distribution: '#ef535020',  // 半透明红
  unknown: '#787b8620',       // 半透明灰
};
```

---

## 9. 验收标准

### ✅ V1：回测面板
1. 点击"运行回测"按钮 → 显示loading → 返回四维评分
2. 评分以进度条+数字形式展示
3. 历史列表显示过往回测记录
4. 点击历史项→ 展开详情 → 显示事件列表和阶段转换
5. 点击事件行 → K线图通过 bar_index 滚动到对应位置

### ✅ V2：进化面板
1. 点击"优化参数"按钮 → 显示优化结果diff
2. 案例统计按事件类型分组显示数量和成功率
3. 当前参数按分组显示关键参数值

### ✅ V3：引擎状态面板
1. 显示当前阶段（大字）、方向（颜色）、结构类型
2. 信心值以进度条展示
3. 最近事件列表显示类型、位置、结果、信心值
4. symbol/timeframe切换时自动刷新

### ✅ V4：不破坏现有功能
1. 标注Tab的AnnotationPanel +FeaturePanel功能不变
2. 画图工具、快捷键、自动保存不受影响
3. Tab切换流畅，无闪烁

---

## 10. 施工顺序

1. **api.ts** — 新增3个backtester端点 + 修复4个engine端点（10分钟）
2. **appStore.ts** — 新增focusBarIndex字段（5分钟）
3. **EngineStatePanel.tsx** — 最简单的面板，先热手（20分钟）
4. **EvolutionPanel.tsx** — 中等复杂度（30分钟）
5. **BacktestPanel.tsx** — 最复杂，有视图切换+事件定位（40分钟）
6. **EvolutionPage.tsx** — Tab集成（15分钟）
7. **ChartWidget.tsx** — focusBarIndex监听（5分钟）
8. **验证** — 启动前后端，逐个Tab测试（15分钟）

---

## 11. 注意事项

1. **端口**：后端6100，前端5173，vite代理已配置
2. **引擎状态可能为空**：引擎未运行时，API可能返回默认空状态或404。面板需要优雅处理
3. **进化优化可能无案例**：案例库为空时，优化会返回空diff。面板需要提示"案例不足"
4. **事件类型大小写**：后端返回小写（`sc`），前端显示大写（`SC`）。用`.toUpperCase()`
5. **不要引入新依赖**：只用React + Zustand + 现有api.ts封装
6. **所有console.log，不用alert**
7. **参数路径可能不准确**：KEY_PARAMS中的路径是推断的，施工时先调一次API确认实际JSON结构再调整
8. **KLineChart滚动API需确认**：`scrollToDataIndex()` 是推断的方法名，施工时查阅 KLineChart 文档确认实际方法名
9. **runner.py已验证版本**：数据结构基于 runner.py 5.24KB版本（使用 create_isolated_instance + 三引擎直接调用）
10. **事件无timestamp**：runner.py输出的事件只有bar_index（=sequence_end_bar），没有timestamp字段。定位功能使用bar_index实现