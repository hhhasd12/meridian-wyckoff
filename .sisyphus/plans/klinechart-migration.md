# KLineChart v10 迁移计划

> 从 Lightweight Charts v5.1 迁移到 KLineChart v10-beta
> 创建日期: 2026-03-23
> 预计工期: 3-5天（4 Wave）

## 迁移动机

1. LWC 无内置画线工具，全部自己写，交互 bug 频发（十字线锁定、拖拽冲突）
2. KLineChart 内置 20+ 画线工具（segment/ray/channel/fibonacci/annotation 等），拖拽交互开箱即用
3. KLineChart 的 Overlay 系统比 LWC 的 ISeriesPrimitive 更高层，自定义 overlay 更简洁
4. KLineChart 内置 30+ 技术指标（MA/EMA/BOLL/MACD/RSI 等），不需要后端算好传入
5. 零依赖，~40KB gzip，与 LWC 体积相当

## 影响范围

### 需要重写的文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `hooks/useChart.ts` | 165 | LWC 初始化 → KLC init() |
| `hooks/useOverlays.ts` | 85 | LWC ISeriesPrimitive → KLC registerOverlay |
| `components/ChartPanel.tsx` | 22 | 容器组件，改动小 |
| `components/AnalysisPage.tsx` | 1043 | 主战场：图表+标注+画线+十字线全部重写 |
| `components/BacktestViewer.tsx` | ~200 | 独立图表实例 |

### 需要重写的 chart-plugins（全部废弃，用 KLC Overlay 替代）

| 插件 | 行数 | KLC 替代方案 |
|------|------|-------------|
| `PhaseBgSegmented.ts` | ~130 | 自定义 Overlay: `wyckoffPhaseBg` |
| `WyckoffEventMarkers.ts` | ~150 | 自定义 Overlay: `wyckoffEventMarker` |
| `TRBoundaryBox.ts` | ~120 | 自定义 Overlay: `trBoundaryBox` |
| `AnnotationLayer.ts` | 200 | 自定义 Overlay: `wyckoffAnnotation` |
| `DrawingTools.ts` | 345 | **删除** — 直接用 KLC 内置 overlay |
| `WyckoffPhaseBg.ts` | ~80 | 合并到 `wyckoffPhaseBg` |
| `SupportResistance.ts` | ~100 | KLC 内置 `horizontalStraightLine` |
| `FvgZones.ts` | ~120 | 自定义 Overlay: `fvgZone` |
| `StateMarkers.ts` | ~90 | 合并到 `wyckoffEventMarker` |
| `TradeMarkers.ts` | ~150 | 自定义 Overlay: `tradeMarker` |

### 不需要改的

- **后端 API** — 完全不动，数据格式不变
- **store.ts** — 状态结构不变，只改消费方
- **api.ts** — REST/WS 调用不变
- **types/api.ts** — 大部分类型保留，DrawingData 改用 KLC 原生
- **其他页面组件** — TradingPage 布局、Sidebar 等不变

## Wave 1: 基础替换（TradingPage 图表）

> 目标：TradingPage 的 K 线图从 LWC 切换到 KLC，能显示 K 线和成交量

### T1.1 安装 KLineChart

- `npm install klinecharts@10.0.0-beta1`
- 移除 `lightweight-charts` 和 `fancy-canvas` 依赖
- 验证：`npm ls klinecharts` 确认版本

### T1.2 重写 useChart.ts

- 替换 `createChart()` → `klinecharts.init(container)`
- 数据加载：`chart.setDataLoader({ getBars: callback })` 或直接 `chart.applyNewData(bars)`
- 成交量：KLC 内置成交量指标 `chart.createIndicator('VOL')`
- 样式：`chart.setStyles({ candle: { ... }, grid: { ... } })` 匹配当前深色主题
- 十字线：KLC 默认自由移动，**无需特殊配置**（解决 Bug 1）
- ResizeObserver：`chart.resize()` 替代 LWC 的 `applyOptions({ width, height })`
- 清理：`klinecharts.dispose(container)` 替代 `chart.remove()`
- 导出：`ChartRefs` 类型改为 KLC 的 Chart 实例类型
- 验证：TradingPage K 线图正常显示，十字线自由移动

### T1.3 重写 useOverlays.ts

- WyckoffPhaseBg → 注册自定义 Overlay `wyckoffPhaseBg`，用 `createPointFigures` 绘制背景色块
- SupportResistance → 用 KLC 内置 `horizontalStraightLine` overlay
- FvgZones → 注册自定义 Overlay `fvgZone`
- StateMarkers → 注册自定义 Overlay `wyckoffStateMarker`
- 数据更新：`chart.overrideOverlay()` 替代 primitive 的 setter
- 验证：TradingPage overlay 正常渲染

### T1.4 更新 ChartPanel.tsx

- 改 import 路径，传 KLC chart 实例而非 LWC refs
- 验证：TradingPage 完整功能正常

### T1.5 验证 TradingPage 不回归

- WS 实时推送正常
- PrinciplesPanel / SignalPanel 不受影响
- 30s 轮询数据正常刷新

## Wave 2: AnalysisPage 迁移（核心战场）

> 目标：AnalysisPage 完整迁移，包括分析 overlay、标注工具、画线工具

### T2.1 AnalysisPage 图表初始化

- 主图表：`init()` + `applyNewData()` + 自定义样式
- 置信度图表：KLC 支持 `createIndicator` 创建子窗格（pane），
  用自定义 Indicator 替代独立 chart 实例
- 或保留双 chart 实例方案，看 KLC 子窗格灵活度
- 十字线同步：`chart.subscribeAction('crosshair')` 替代 LWC 的 `subscribeCrosshairMove`

### T2.2 注册 4 个自定义 Overlay

每个 overlay 用 `klinecharts.registerOverlay()` 注册：

**wyckoffPhaseBg**（阶段背景色）
- `totalStep: 0`（非交互式，纯渲染）
- `createPointFigures`: 用 `rect` figure 绘制分段背景
- 数据通过 `extendData` 传入 PhaseSegment[]

**wyckoffEventMarker**（状态变化标记）
- `totalStep: 0`
- `createPointFigures`: 用 `circle` + `text` figure 在状态变化点绘制标记
- 颜色按 direction 分类（bullish=绿, bearish=红, neutral=灰）

**trBoundaryBox**（TR 区间矩形）
- `totalStep: 0`
- `createPointFigures`: 用 `rect` figure 绘制支撑/阻力区间
- 半透明填充 + 虚线边框

**wyckoffAnnotation**（用户标注）
- `totalStep: 2`（需要用户交互：拖拽选范围）
- 或 `totalStep: 0` + 通过 API 创建（程序化创建，非用户拖拽）
- event 类型：`rect` 背景 + 顶部 `text` 标签
- level 类型：`line` 水平虚线 + 右侧 `text` 标签

### T2.3 标注工具交互

- **event 模式**：用 KLC 内置拖拽能力
  - `chart.createOverlay('wyckoffAnnotation')` 进入绘制模式
  - 用户拖拽自动创建 overlay，**无需手动处理 mousedown/move/up**
  - `onDrawEnd` 回调 → POST 到后端保存
  - **彻底解决 Bug 2（拖拽冲突）**
- **level 模式**：`chart.createOverlay('horizontalStraightLine')` 
  - KLC 内置水平线，一键创建
  - `onDrawEnd` 回调 → POST 到后端保存
- **删除**：`chart.removeOverlay(id)` + DELETE 到后端

### T2.4 画线工具

- **完全删除** `DrawingTools.ts` 和所有手动事件处理代码
- 直接用 KLC 内置 overlay：
  - 线段 → `chart.createOverlay('segment')`
  - 射线 → `chart.createOverlay('rayLine')`  
  - 通道 → `chart.createOverlay('priceChannelLine')`
  - 斐波那契 → `chart.createOverlay('fibonacciLine')`（新增！）
- 工具栏按钮只需调用 `createOverlay(name)` 即可
- 清除绘图：`chart.removeOverlay()` 全部清除

### T2.5 Bar 详情面板

- `chart.subscribeAction('crosshair')` 获取当前 hover 的 bar index
- `chart.getDataList()[index]` 获取 bar 数据
- 映射到 barDetailMap 显示详情，逻辑不变

## Wave 3: BacktestViewer + 剩余页面

### T3.1 BacktestViewer.tsx 迁移

- 独立 chart 实例 → KLC init()
- EquityChart（折线图）→ KLC 自定义 Indicator 或独立 chart
- TradeMarkers → 注册自定义 Overlay `tradeMarker`（开仓▲/平仓▼标记）
- 验证：进化页面回测可视化正常

### T3.2 清理 LWC 依赖

- 删除所有旧 chart-plugins/*.ts 文件
- 删除 `package.json` 中 `lightweight-charts` 和 `fancy-canvas`
- 删除 `types/api.ts` 中 DrawingData 接口（改用 KLC 原生）
- `npm prune` 清理
- 验证：`npm run build` 零错误

## Wave 4: 打磨 + 验收

### T4.1 样式统一

- KLC 深色主题匹配当前 `#0d1117` 背景
- K 线颜色 upColor/downColor 匹配现有 `#3fb950` / `#f85149`
- 网格线颜色 `#1c2128` 匹配
- 十字线样式匹配

### T4.2 功能验收

- [ ] TradingPage K 线正常显示 + WS 实时更新
- [ ] TradingPage overlay（阶段背景/支撑阻力/FVG/状态标记）正常
- [ ] AnalysisPage 分析功能正常（POST /api/analyze → 渲染结果）
- [ ] AnalysisPage 标注工具正常（event 拖拽 + level 点击 + 删除）
- [ ] AnalysisPage 画线工具正常（线段/射线/通道/斐波那契）
- [ ] AnalysisPage 十字线自由移动 + Bar 详情同步
- [ ] AnalysisPage AI 诊断面板正常
- [ ] AnalysisPage 标注对比面板正常
- [ ] BacktestViewer 回测可视化正常
- [ ] `npm run build` 零错误零警告
- [ ] 无 console 报错

### T4.3 前端 build 验证

- `npm run build` 确认打包成功
- 检查 bundle size 变化（应该差不多，~40KB → ~40KB）

## KLC vs LWC API 映射速查

| LWC API | KLC API |
|---------|---------|
| `createChart(container, opts)` | `init(container, opts)` |
| `chart.addSeries(CandlestickSeries)` | 内置（init 即 K 线） |
| `chart.addSeries(HistogramSeries)` | `chart.createIndicator('VOL')` |
| `series.setData(data)` | `chart.applyNewData(data)` |
| `series.update(bar)` | `chart.updateData(bar)` |
| `series.attachPrimitive(p)` | `registerOverlay()` + `createOverlay()` |
| `chart.subscribeCrosshairMove(cb)` | `chart.subscribeAction('crosshair', cb)` |
| `chart.subscribeClick(cb)` | `chart.subscribeAction('click', cb)` |
| `chart.applyOptions({handleScroll})` | `chart.setScrollEnabled(bool)` |
| `chart.remove()` | `dispose(container)` |
| `CrosshairMode.Normal` | 默认行为（无需配置） |
| N/A | `chart.createOverlay('segment')` 内置画线 |
| N/A | `chart.createOverlay('fibonacciLine')` 内置斐波那契 |
| N/A | `chart.createIndicator('MA')` 内置指标 |

## 风险与注意事项

1. **v10 是 beta** — 可能有 API 变动。锁定 `10.0.0-beta1` 版本
2. **自定义 Overlay 的 createPointFigures** — 需要用 KLC 的 Figure 原语
   （rect/circle/line/text/polygon），与 LWC 的 Canvas 直接绘制不同
3. **置信度子图表** — KLC 的子窗格（pane）API 与 LWC 独立 chart 不同，
   需要验证 `createIndicator` 能否满足需求
4. **数据格式** — KLC 用 `{ timestamp, open, high, low, close, volume }`，
   与现有 Candle 类型基本一致，只需 timestamp 从 ISO string 转 ms
5. **实时更新** — KLC 用 `chart.updateData(bar)` 替代 LWC 的 `series.update(bar)`
