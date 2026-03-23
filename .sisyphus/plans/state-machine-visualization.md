# 状态机可视化 + 架构演进计划

> 日期：2026-03-22
> 状态：Wave 1 已完成 ✅，Wave 2-4 待执行
> 前置：进化系统正在跑（checkpoint/resume 已就绪），回测数据后端已完成

## 背景

### 今天完成了什么

| 功能 | 文件 | 状态 |
|------|------|------|
| Checkpoint/Resume 断点续传 | genetic_algorithm.py, plugin.py | ✅ |
| BacktestResult 扩展 (equity_curve + bar_phases + bar_states) | types.py, bar_by_bar_backtester.py | ✅ |
| 回测详情 API | api/app.py `GET /api/backtest/{cycle}/detail` | ✅ |
| 进化结果持久化 (trades + equity + phases RLE) | plugin.py `_save_cycle_result` | ✅ |
| 前端回测可视化 (StatsBar + EquityChart + TradesTable) | BacktestViewer.tsx, TradeMarkers.ts | ✅ |
| 进化实时进度推送 | GA progress_callback → WebSocket → 前端进度条 | ✅ |
| 进化页面布局重构 (上下分割) | EvolutionPage.tsx | ✅ |
| Lifespan shutdown 保存 checkpoint | api/app.py lifespan | ✅ |
| population_size 30→24 | config.yaml | ✅ |

### 当前最迫切的问题

**状态机可视化 ≠ 回测可视化。**

- 回测可视化看的是"交易结果"——在哪开仓平仓、赚了亏了
- 状态机可视化看的是"识别过程"——22 个状态在 K 线上做了什么判断

没有状态机可视化，进化就是黑盒。fitness=0.29 背后状态机画的区间对不对、
阶段判断准不准，完全看不到。

### 架构分歧

用户讨论文档（的判断非常敏锐.txt）提出的架构与当前系统的差异：

| 文档主张 | 当前系统 | 差距 |
|---------|---------|------|
| 多识别模块（震仓_快速型/缓跌型） | 单一 StateMachineV2 | 大 |
| 识别层只输出状态标签，不带交易信号 | WyckoffEngine 既识别又带 signal | 中 |
| 策略族（不同阶段挂不同策略） | 单链路 Orchestrator→PositionManager | 大 |
| 通用多市场（A股/加密/期货） | 硬编码 ETH | 中 |

**结论：先可视化，看清系统在做什么，再决定是否重构架构。**

---

## Wave 1：状态机可视化（P0，3-4 天）— ✅ 已完成

目标：在前端 K 线图上看到 22 个威科夫状态的完整标注过程。

### 1.1 后端：BarSignal 逐 bar 数据补全 — ✅ 已完成

**改动：**
- `src/kernel/types.py`: BarSignal 新增 11 个字段（tr_support/resistance/confidence, market_regime, direction, signal_strength, state_changed, previous_state, heritage_score, critical_levels）
- `src/kernel/types.py`: 新建 BarDetail dataclass，BacktestResult 新增 bar_details 字段
- `src/plugins/wyckoff_engine/engine.py`: process_bar() 填充所有新字段
- `src/plugins/evolution/bar_by_bar_backtester.py`: 逐bar循环收集 BarDetail，传入 BacktestResult
- `src/plugins/evolution/plugin.py`: _serialize_backtest_detail() 新增 bar_details 序列化（delta压缩critical_levels）
- 测试验证：85/85 passed + 23/23 API tests passed

### 1.2 后端：独立分析 API — ✅ 已完成

- `src/api/app.py`: POST /api/analyze 端点，输入 symbol/bars，逐bar跑 WyckoffEngine.process_bar()，输出逐bar的 phase/state/confidence/TR/critical_levels

### 1.3 前端：chart plugins — ✅ 已完成

- `PhaseBgSegmented.ts`: ISeriesPrimitive，按阶段分段背景色（A灰/B黄/C绿/D蓝/E紫）
- `WyckoffEventMarkers.ts`: 状态转换标记（看涨▲绿/看跌▼红/中性●灰 + 文字标签）
- `TRBoundaryBox.ts`: TR区间半透明矩形，透明度随置信度缩放

### 1.4 前端：分析页面 — ✅ 已完成

- `AnalysisPage.tsx`: 上方K线图(含3 overlay) + 下方置信度曲线 + Bar详情面板
- Sidebar 新增"状态分析"导航，App.tsx 路由更新
- store.ts 新增 analysisData/isAnalyzing 状态
- 构建验证：tsc --noEmit + vite build 零错误

---

## Wave 2：进化→实盘闭环（P0，1.5 天）

目标：进化跑出最优参数后，能一键应用到实盘配置。

### 2.1 后端：配置应用 API

- `POST /api/evolution/apply` —— 读取进化最优 config，写入 config.yaml
- diff 对比：返回变更前后的参数差异
- 热加载：写入后通知 ConfigSystem 重新加载

### 2.2 前端：配置对比 + 一键应用

- 进化页面加「应用最优参数」按钮
- 弹窗显示左右分栏 diff（当前配置 vs 进化最优）
- 确认后调用 apply API
- 二次确认：写入前提示风险

**预估：** 1-1.5 天

---

## Wave 3：架构评估（P1，先看 Wave 1 结果再定）

**前提：** Wave 1 状态机可视化完成后，用户能看到系统的识别过程。
基于看到的问题，决定是否需要以下重构：

### 3.1 识别/交易分离评估

**问题：** WyckoffEngine.process_bar() 既输出 phase/state（识别），
又输出 signal/signal_strength（交易信号）。

**评估点：**
- signal 的生成逻辑是否依赖 phase/state？（大概率是）
- 分离后 signal 从哪里生成？（独立的 SignalGenerator？）
- 分离的收益是什么？（可以为不同市场挂不同的 signal 生成器）

### 3.2 多状态机 / 策略族评估

**问题：** 当前单一 StateMachineV2 用一套逻辑识别所有变体。

**评估点：**
- 可视化后，状态机在哪些场景识别不准？
- 不准的原因是参数问题（进化能解决）还是逻辑问题（需要新模块）？
- 如果需要新模块，是加子状态机还是改现有逻辑？

**决策时机：** Wave 1 完成，用户看完可视化结果后讨论。

---

## Wave 4：后续增强（P2）

| 需求 | 说明 | 依赖 |
|------|------|------|
| 手动回测验证 | 前端指定时间范围 + 参数，跑独立回测 | Wave 1 的 analyze API |
| 多币种支持 | 去掉 ETHUSDT 硬编码，支持选币种 | 数据层改动 |
| 交易所连接验证 | exchange_connector 端到端测试 | 实盘前必做 |
| A 股数据适配 | 准备 A 股 OHLCV 数据，跑进化 | 数据格式对齐 |
| 回测 K 线叠加交易标记 | TradeMarkers 接到实际 K 线图 | Wave 1 |

---

## 执行顺序

```
Wave 1（状态机可视化）
├── 1.1 后端 BarSignal 补全        ← 半天
├── 1.2 后端 analyze API           ← 2-3h
├── 1.3 前端 chart plugins         ← 1.5-2 天（子代理）
└── 1.4 前端分析页面               ← 1 天（子代理）
    ↓
Wave 2（进化→实盘闭环）             ← 1-1.5 天
    ↓
Wave 3（架构评估，看 Wave 1 结果决定）
    ↓
Wave 4（后续增强，按需）
```

**总预估：Wave 1 + Wave 2 = 5-6 天工作量。**
