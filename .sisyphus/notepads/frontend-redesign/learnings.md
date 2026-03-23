# 前端重构 — 研究笔记

## 研究日期：2026-03-22 凌晨

---

## 1. 最重要的参考项目

### dYdX v4-web（最匹配）
- GitHub: dydxprotocol/v4-web
- 技术栈完全一致：React + TypeScript + Vite + Tailwind CSS + TradingView Charts
- 暗色主题 #1C1C28 系列
- 经典三栏交易终端布局

### GMX Interface（架构参考）
- React + TypeScript + Vite + Tailwind CSS
- 深蓝黑 #16182e
- 代码分层：config → lib → domain → components → pages

### OpenBB（后端架构参考）
- Python FastAPI + React — 与我们的架构完全一致
- Bloomberg Terminal 风格多面板仪表盘
- 63,400 stars

### Tremor 组件库
- React + Tailwind CSS + Radix UI
- 35+ Dashboard 专用组件，可直接参考组件代码

---

## 2. TradingView 实际 DOM 分析要点

### 左侧工具栏
- 纯图标，48px 宽
- 每个工具组：主图标 + ▼展开按钮
- 分组间用间距分隔，不用分隔线
- 活跃状态：[pressed] + 视觉高亮

### 右侧面板栏
- 48px 图标，展开面板约 300px
- Watchlist, Alerts, Object tree, Screeners, Pine...
- 面板底部有 Hide Tab 关闭按钮

### TradingView 暗色主题精确色值
- 主背景: #131722 (≈ zinc-950)
- 面板: #1E222D (≈ zinc-900)
- 边框: #2A2E39 (≈ zinc-800)
- 主文字: #D1D4DC (≈ zinc-300)
- 次文字: #787B86 (≈ zinc-500)
- 主题蓝: #2962FF
- 涨: #26A69A
- 跌: #EF5350

### 活跃状态最佳实践
- 左边框 3px accent 色 + 半透明背景
- before伪元素实现竖线指示器

---

## 3. 侧边栏设计决策（基于研究修正）

原计划：方案B ~140px 文字+图标
研究发现：TradingView/Binance 都**不用传统侧边栏**

### 修正方案：混合式
我们的场景不同于 TV（我们不是画图工具），更接近"视图切换"
保持方案B（~140px 带文字）但参考 TV 的设计语言：
- 活跃状态用左边框高亮
- 底部状态区参考 Bloomberg 底部状态栏
- 模拟盘/实盘标识参考 TV 的 broker 按钮风格

---

## 4. 进化页面设计要点（来自 Optuna/Aim 研究）

### 布局模式（参考 Optuna StudyHistory）
- 全宽 fitness curve 图表在最上面
- 两列Grid：参数面板 + 验证面板
- 底部：数据表格

### Start/Stop 控制（参考 Aim MetricsBar）
- StatusBar 中嵌入 Start/Stop 按钮
- 运行中时显示 ProgressBar
- isRunning ? "停止进化" : "启动进化"

### 图表选择
- 保持现有手工 SVG 方案（零依赖，已工作）
- 不引入 Recharts（约束不加依赖）
- SVG 可增强：hover tooltip 用 Tailwind 实现

### AI Advisor 展示
- 嵌入进化页面，不单独 Tab
- 默认折叠，仅显示摘要，点击展开全文
- 参考 TensorBoard text dashboard

---

## 5. 错误/告警展示模式

### 双层机制（已确认）
- 严重（熔断）：顶部固定红色横幅，bg-red-500/10 + border-b
- 一般：侧边栏状态变红，点击展开
- Toast 通知留给未来（交易执行反馈）

### 实现参考
```
bg-red-500/10 text-red-400 border-b border-red-500/20
bg-amber-500/10 text-amber-400 border-b border-amber-500/20
```

---

## 6. 对计划书的修正

研究后发现需要调整：
1. TradingView 色值比我之前选的 Binance 色更适合
   → 考虑用 TV 色系 #131722/#1E222D 替代 #0b0e11/#141821
   → 但这个差异很小，实施时再决定
2. 侧边栏活跃状态：用左边框 3px accent 而非简单高亮
3. 进化页 AI Advisor 嵌入页面而非单独 Tab
4. Start/Stop 按钮直接放在 StatusBar 中
