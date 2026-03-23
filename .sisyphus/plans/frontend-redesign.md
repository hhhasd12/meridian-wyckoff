# 威科夫引擎前端重构计划书

> **版本**: v0.1 草案
> **日期**: 2026-03-21
> **状态**: 讨论中

---

## 一、重构目标

1. **全中文化** — 所有UI文字100%中文
2. **双面板分离** — 实盘监控 与 进化优化 两个独立页面
3. **功能丰富度** — 充分展示后端18个插件的数据能力（当前只展示约25%）
4. **UI专业化** — TradingView暗色终端风格，丰富动效
5. **不改后端** — 纯前端重构，不修改 src/ 目录
6. **不加依赖** — 使用现有 React/Tailwind/LWC/Zustand/react-query/lucide-react

---

## 二、后端数据能力摸底

### 2.1 当前可用的API端点（7+1）

| 端点 | 说明 | 前端当前使用 |
|------|------|-------------|
| `GET /api/candles/{symbol}/{tf}` | K线数据 | ✅ 已用 |
| `GET /api/system/snapshot` | 系统全景快照 | ⚠️ 部分使用 |
| `GET /api/evolution/results` | 进化周期历史 | ✅ 已用 |
| `GET /api/evolution/latest` | 最新进化结果 | ❌ 未用 |
| `GET /api/trades` | 交易历史 | ✅ 已用 |
| `GET /api/advisor/latest` | AI顾问分析 | ✅ 已用 |
| `POST /api/config` | 更新配置 | ❌ 未用 |
| `WS /ws/realtime` | 实时推送(5主题) | ✅ 已用 |

### 2.2 snapshot 返回的完整数据（已有但未充分展示）

**orchestrator 编排器状态：**
- status(运行/停止), mode(模拟/实盘), symbols, timeframes
- decision_count, process_count, signal_count
- last_error, engine_loaded, circuit_breaker_tripped

**wyckoff_engine 引擎状态（关键！多TF数据）：**
- timeframes: ["H4","H1","M15"]
- state_machines: 每个TF独立的 current_state + direction + confidence
- last_candle_time, bar_index

**positions 持仓数据（有丰富字段未展示）：**
- symbol, side, size, entry_price, entry_time
- stop_loss, take_profit, signal_confidence
- wyckoff_state, entry_signal, status
- trailing_stop_activated, partial_profits_taken
- highest_price, lowest_price, leverage
- unrealized_pnl, unrealized_pnl_pct, risk_reward_ratio

**evolution 进化状态：**
- status(running/stopped), cycle_count

**plugins 插件列表（18个，完全未展示）：**
- name, display_name, version, state(ACTIVE/ERROR/...)

### 2.3 WS 推送的5个主题

| 主题 | 数据 | 频率 |
|------|------|------|
| candles | 最新K线(固定BTC/USDT H1) | 2秒 |
| wyckoff | 多TF状态机快照 | 2秒 |
| positions | 持仓列表(含完整字段) | 2秒 |
| evolution | 进化状态 | 2秒 |
| system_status | 系统状态+插件状态 | 2秒 |

### 2.4 已知后端缺失（不影响本次重构）

- `get_latest_signal()` 不存在 → latest_signal 始终为 null
- `get_recent_logs()` 不存在 → recent_logs 始终为 []
- `get_closed_trades()` 可能返回空 → 交易记录需graceful处理
- 市场体制、风控详情、交易统计 — snapshot不返回，需后续扩展后端

---

## 三、页面架构设计

### 3.1 导航结构

左侧边栏导航，两个主页面：

| 页面 | 图标 | 说明 |
|------|------|------|
| **实盘监控** | 📊 | 交易核心：K线+威科夫分析+持仓+信号 |
| **进化优化** | 🧬 | 进化系统：适应度+参数+WFA+AI顾问 |

侧边栏底部固定显示：
- 系统运行状态（运行中/已停止 + 脉冲动画）
- WebSocket连接状态
- 运行时长
- 插件健康摘要（如 "18/18 活跃"）

### 3.2 为什么是两个页面而不是四个？

之前我提议了四个页面（实盘/进化/风控/系统），但仔细想：

**风控中心的问题：** 当前后端 snapshot 不返回风控详细数据（日/周亏损、
回撤、熔断器详情）。如果单独做一个页面，内容会很空。所以风控相关信息
应该分散到它们各自归属的页面：
- 熔断器状态 → 实盘监控页（交易者需要实时知道）
- 进化相关的防过拟合 → 进化页面

**系统状态的问题：** 18个插件列表是"看一眼就够了"的信息，不值得独占
一个页面。放在侧边栏底部或实盘页面的某个折叠区即可。

**结论：两个页面就够了。** 信息按"谁关心"来分配，而不是按"后端模块"来分。

---

## 四、实盘监控页 — 详细设计

### 4.1 整体布局

三栏 + 底部Tab，与当前类似但大幅增强内容：

```
顶部栏: BTC/USDT 价格 | 时间周期选择 D1 H4 H1 M15 M5
左栏(~240px): 决策信息面板
中栏(弹性):   K线图表(上70%) + 底部Tab(下30%)
右栏(~260px): 威科夫状态面板
```

### 4.2 左栏 — 决策信息面板（当前无此面板，全新）

从上到下排列以下卡片：

**A. 编排器状态卡片**
- 运行模式：模拟盘/实盘
- 熔断器状态：正常(绿) / 已触发(红)
- 决策计数 / 处理计数 / 信号计数
- 最后错误信息（如有）
- 数据来源：snapshot.orchestrator

**B. 最新信号卡片（暂为占位，后续后端补充数据后激活）**
- 当前 latest_signal 为 null，展示"等待信号..."
- 预留位置：信号类型+置信度+入场价+止损+止盈+理由链
- 后续后端实现 get_latest_signal() 后自动激活

**C. 插件健康摘要（折叠式）**
- 默认收起，显示 "18/18 活跃"
- 展开后显示每个插件的 name + version + state
- 异常插件(非ACTIVE)高亮红色
- 数据来源：snapshot.plugins

### 4.3 中栏 — K线图表 + 底部Tab

**K线图表区域（保持现有，样式更新）：**
- LWC 图表 + 4个现有叠加层（WyckoffPhaseBg/SupportResistance/FvgZones/StateMarkers）
- 颜色更新为新色板
- 不改变图表逻辑，只改样式

**底部Tab（增强）：**

| Tab名 | 当前状态 | 改动 |
|--------|---------|------|
| 持仓 | 基础10列表格 | 增加：entry_signal, wyckoff_state, trailing_stop, unrealized_pnl, risk_reward_ratio |
| 交易记录 | 基础9列表格 | 增加：entry_time, exit_time（如后端返回）；无数据时友好提示 |
| 决策历史 | 无（全新） | 最近N条TradingDecision：信号类型+置信度+理由链。需后端配合 |
| 日志 | 依赖WS recent_logs | 后端暂无数据；保留UI，显示"日志服务未启用" |

### 4.4 右栏 — 威科夫状态面板（大幅增强）

**A. 当前状态大字展示（保持现有，中文化）**
- 阶段(Phase A-E) + 状态名 + 方向 + 置信度

**B. 阶段进度条（保持现有）**
- A → B → C → D → E 可视化

**C. 多时间框架状态对比（全新，核心增强）**
- 三行并排显示 H4 / H1 / M15 各自的：
  - current_state（如 SPRING / LPS / mSOS）
  - direction（吸筹/派发/趋势）
  - confidence（置信度百分比）
- 数据来源：snapshot.wyckoff_engine.state_machines
- 这是当前完全缺失的关键信息

**D. 证据链（保持现有，中文化）**

**E. 关键价位（保持现有，中文化）**

---

## 五、进化优化页 — 详细设计

### 5.1 整体布局

两栏 + 底部区域：

```
左栏(60%):  适应度曲线(上) + 最优参数面板(下)
右栏(40%):  WFA验证面板(上) + AI顾问分析(下)
底部:       进化历史表格 + 自我纠错状态条
```

### 5.2 左栏

**A. 适应度进化曲线（保持现有SVG图表，增强）**
- Best(绿线) + Avg(紫线)
- 颜色更新为新色板
- 增加：进化状态指示（运行中/空闲 + 脉冲动画）
- 增加：周期计数大字显示

**B. 最优参数面板（保持现有，中文化）**
- 周期权重条形图（H4/H1/M15/M5）
- 阈值参数键值对列表

### 5.3 右栏

**A. WFA 验证面板（保持现有，中文化增强）**
- WFA通过/未通过 大徽章
- OOS退化率进度条（颜色编码：<30%绿 / <50%黄 / >50%红）
- 防过拟合参数列表

**B. AI 顾问分析面板（大幅增强，结构化展示）**
当前是原始 key-value 列表，改为分区展示：
- 📊 轮次分析：analysis 文本（主要分析内容）
- ⚠️ 局部最优警告：plateau_warning（如有）
- 🔧 变异建议：mutation_advice（如有）
- 📋 错题本摘要：mistake_summary（如有）
- 无数据时显示说明文字，不显示空白

### 5.4 底部

**A. 进化历史表格（保持现有，中文化）**
- 表头：周期 / 代数 / 最佳适应度 / 均值 / WFA / OOS退化率

**B. 进化周期状态条（增强）**
- 当前周期数 / 最佳适应度 / WFA状态 / 运行指示灯
- 保持现有 StatusBar，中文化

---

## 六、侧边导航栏设计

### 6.1 结构

- 宽度：收起态 56px（仅图标） / 展开态 180px（图标+文字）
- 位置：左侧固定
- 切换方式：点击底部按钮展开/收起

### 6.2 导航项

- 📊 实盘监控（默认激活）
- 🧬 进化优化

### 6.3 底部状态区（固定在侧边栏底部）

- 系统状态指示灯：● 运行中(绿色脉冲) / ● 已停止(灰色)
- WS连接状态：已连接(绿) / 连接中(黄) / 已断开(红)
- 运行时长：如 "14h 32m"
- 插件摘要："18/18"（收起态）或 "18/18 插件活跃"（展开态）

### 6.4 不使用 react-router

约束要求不加新依赖。使用 Zustand store 管理当前页面：
- store 新增：activePage: 'trading' | 'evolution'
- App.tsx 根据 activePage 条件渲染对应页面组件

---

## 七、视觉规范

### 7.1 色彩体系（深灰 + TradingView风格）

**背景层次：**
- 最底层：#0b0e11（近黑，微蓝调）
- 面板表面：#141821
- 悬浮/弹层：#1c2030
- 悬停态：#252a35
- 边框：#2a3040

**语义色（Binance标准涨跌色）：**
- 涨/做多/盈利：#0ecb81
- 跌/做空/亏损：#f6465d
- 警告：#fcd535
- 信息/强调：#5b9cf6
- 进化/AI：#b98eff
- 技术指标：#36d9c4

**文字：**
- 主文字：#eaecef
- 次要文字：#848e9c
- 弱化文字：#474d57

### 7.2 字体

- UI文字：系统无衬线字体栈（-apple-system, Segoe UI, etc.）
- 数据/数字：JetBrains Mono 等宽字体（已配置）
- 全局添加 tabular-nums 确保数字对齐

### 7.3 间距与圆角

- 面板圆角：4px（rounded），不用 rounded-lg
- 数据行间距：space-y-1（4px），比当前更紧凑
- 面板标题：text-[10px] uppercase tracking-widest
- 面板间距：gap-1 ~ gap-2

### 7.4 动效规范

- 状态指示器：animate-ping 脉冲扩散（运行中/已连接）
- Tab切换：底部指示线滑动过渡 transition-all duration-200
- 面板折叠：width过渡动画 transition-all duration-300
- 数据加载：animate-pulse 骨架屏
- 侧边栏展开/收起：宽度过渡 transition-all duration-300
- 数据变化：关键数值变化时短暂高亮闪烁

---

## 八、中文化清单

### 8.1 需要翻译的英文字符串（约50+处）

**Header.tsx：** Running→运行中, Stopped→已停止
**WyckoffPanel.tsx：** Wyckoff State→威科夫状态, Current Phase→当前阶段,
  State→状态, Confidence→置信度, Signal→信号, Strength→强度,
  Heritage→遗产分数, Phase Progress→阶段进度, Evidence Chain→证据链,
  Critical Levels→关键价位, No evidence data→暂无证据数据
**SignalPanel.tsx：** Signals & Positions→信号与持仓, Recent Signals→最近信号,
  Open Positions→当前持仓, Entry→入场价, PnL→盈亏, SL→止损,
  Leverage→杠杆, No signals yet→暂无信号, No open positions→暂无持仓
**PositionsTab.tsx：** Symbol→交易对, Side→方向, Entry→入场价, Current→现价,
  Size→仓位, PnL→盈亏, SL→止损, TP→止盈, Lev→杠杆
**TradesTab.tsx：** Side→方向, Entry→入场价, Exit→出场价, Hold→持仓,
  Reason→原因, State→状态, bars→根K线
**EvolutionTab.tsx：** Cycles→周期数, Best Fitness→最佳适应度,
  EVOLVING→进化中, IDLE→空闲, Fitness Curve→适应度曲线,
  Best→最优, Avg→均值, Cycle/Fitness/WFA/OOS-DR→对应中文
**AdvisorTab.tsx：** AI Advisor Analysis→AI顾问分析
**LogsTab.tsx：** No log entries→暂无日志
**App.tsx底部Tab：** Positions→持仓, Trade History→交易记录,
  Evolution→进化, AI Analysis→AI分析, Logs→日志

### 8.2 已有中文（保持）

EvolutionTab中：最优参数、周期权重、阈值参数、验证状态、防过拟合、
  等待进化结果、需要≥2个Cycle绘制曲线、无参数数据、无验证数据、
  OOS退化率、无结构化参数
AdvisorTab中：加载顾问分析中、加载失败、暂无顾问分析数据、已加载

---

## 九、文件改动清单

### 9.1 修改的文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| tailwind.config.js | 重写 | 新色板+新间距+动画 |
| index.css | 重写 | CSS变量+组件层更新 |
| App.tsx | 重写 | 侧边栏导航+页面路由+数据层 |
| Header.tsx | 重写 | 简化为页面内顶部栏（移除导航职责） |
| WyckoffPanel.tsx | 大改 | 中文化+多TF状态对比 |
| SignalPanel.tsx | 大改 | 改为决策信息面板+中文化 |
| BottomTabs.tsx | 小改 | 中文化+样式更新 |
| PositionsTab.tsx | 中改 | 中文化+增加字段展示 |
| TradesTab.tsx | 小改 | 中文化+样式更新 |
| EvolutionTab.tsx | 大改 | 中文化+SVG颜色更新+分离子组件 |
| AdvisorTab.tsx | 大改 | 中文化+结构化展示 |
| LogsTab.tsx | 小改 | 中文化+无数据友好提示 |
| store.ts | 中改 | 增加 activePage+适配新数据字段 |
| types/api.ts | 中改 | 补充缺失的类型定义 |

### 9.2 新增的文件

| 文件 | 说明 |
|------|------|
| components/Sidebar.tsx | 侧边导航栏组件（方案B，~140px） |
| components/TradingPage.tsx | 实盘监控页面容器 |
| components/EvolutionPage.tsx | 进化优化页面容器 |
| components/SystemCard.tsx | 编排器状态+插件摘要卡片 |
| components/MultiTFStatus.tsx | 多时间框架状态对比组件 |
| components/DecisionHistoryTab.tsx | 决策历史Tab（全新） |
| components/AlertBanner.tsx | 顶部错误/告警横幅组件 |

### 9.3 不改动的文件

| 文件 | 原因 |
|------|------|
| ChartPanel.tsx | 图表容器逻辑不变 |
| hooks/useChart.ts | 图表初始化逻辑不变（颜色通过CSS变量更新） |
| hooks/useOverlays.ts | 叠加层逻辑不变 |
| chart-plugins/*.ts | 4个图表插件逻辑不变 |
| core/api.ts | API调用不变 |
| core/ws.ts | WebSocket管理不变 |
| main.tsx | 入口不变 |

---

## 十、实施阶段

### Phase 1：基础设施（色彩+导航+路由）
- 更新 tailwind.config.js 色板
- 更新 index.css 组件样式
- 新建 Sidebar.tsx 侧边导航
- 改写 App.tsx 为侧边栏+页面路由结构
- store.ts 增加 activePage 状态
- 验证：npm run build 通过

### Phase 2：实盘监控页
- 新建 TradingPage.tsx 页面容器
- 改写 Header.tsx 为页面内顶部栏
- 新建 SystemCard.tsx 编排器+插件卡片
- 改写 WyckoffPanel.tsx：中文化 + 新建 MultiTFStatus.tsx
- 改写 SignalPanel.tsx → 决策信息面板
- 更新 BottomTabs/PositionsTab/TradesTab/LogsTab：中文化+增强
- 验证：npm run build 通过

### Phase 3：进化优化页
- 新建 EvolutionPage.tsx 页面容器
- 改写 EvolutionTab.tsx：中文化+SVG颜色+样式增强
- 改写 AdvisorTab.tsx：中文化+结构化展示
- 验证：npm run build 通过

### Phase 4：类型+数据层适配
- 更新 types/api.ts 补充缺失类型
- 更新 store.ts 适配新数据结构
- 确保所有组件正确消费新数据
- 验证：npm run build 通过

### Phase 5：动效+打磨
- 添加动画效果（脉冲、过渡、骨架屏）
- 图表色彩同步（useChart.ts 中的LWC配色）
- chart-plugins 中的硬编码颜色同步
- 最终构建验证

---

## 十一、讨论记录与决策

### 11.1 已确认的决策

**Q1: 页面架构 — 侧边栏做"视图切换"而非"页面导航"**
两个视图（实盘/进化）都保持在内存中，切换瞬时，不销毁组件。
未来实盘和进化同时跑时，各自独立刷新，切换查看即可。

**Q2: 进化控制按钮 — 必须有**
需要新增后端API：POST /api/evolution/start 和 POST /api/evolution/stop。
后端 evolution 插件已有 start_evolution() 和 stop_evolution() 方法，
只需在 src/api/app.py 中暴露为REST端点。
→ 这要求**小范围修改后端**（仅新增2个路由，不改现有逻辑）。

**Q3: 日志 — 保留，需要优化**
后端 AuditLoggerPlugin 暂无 get_recent_logs() 方法。
方案：后端新增该方法（读取 JSONL 文件尾部），通过 WS 推送。
→ 这要求**小范围修改后端**。

**Q4: 报错传递到前端**
当前 snapshot.orchestrator.last_error 每30秒轮询可获取。
实时报错需后端在错误发生时通过 WS system_status 推送。
方案：在 system_status WS 主题中附加 last_error 字段。
→ 这要求**小范围修改后端**。

**Q5: 图表颜色 — 后期再改，本次不动**
chart-plugins/ 和 hooks/ 中的 LWC 配色暂不修改。

### 11.2 部署架构确认

**一键启动已支持：**
1. 构建前端：cd frontend && npm run build
2. 启动系统：python run.py --mode=api
3. 访问：http://localhost:9527（后端自动托管前端静态文件）

**Docker部署：**
docker-compose.yml 已配置，端口9527，一个容器全搞定。
前端构建产物在 frontend/dist/ 中，后端启动时自动挂载。

**服务器部署：** 与本地相同，只需要把代码部署到服务器即可。

### 11.3 关于"不改后端"约束的修正

原始约束是"不修改后端代码"。但以下功能**必须小改后端**：
1. 进化控制API（2个新路由）
2. 日志获取方法（1个新方法）
3. 错误推送（WS主题扩展）

**修正为：** 后端仅做最小必要扩展（新增API端点），不改现有逻辑。
这部分改动会在前端重构完成后单独执行。

### 11.4 多TF对比解释

"多TF对比"= 同时展示 H4、H1、M15 三个时间周期的威科夫状态：
- H4: SPRING（弹簧）| 吸筹 | 置信度 72%
- H1: LPS（最后支撑）| 吸筹 | 置信度 65%
- M15: mSOS（小力量信号）| 吸筹 | 置信度 58%

这个数据 snapshot.wyckoff_engine.state_machines 已经返回了，
只是当前前端完全没展示。展示方式：三行竖排，每行一个TF。

---

### 11.5 最终确认（第二轮讨论）

**侧边栏风格：** 方案B — 功能性工具栏（~140px，文字+图标+底部状态）
**实盘页布局：** 左(威科夫面板) + 中(图表+底部Tab) + 右(决策信息面板)
**数据刷新策略：** 切换到视图时才刷新，非活跃视图不轮询
**图表颜色：** 后期再改，本次不动

### 11.6 第三轮确认（最终决策）

**决策历史Tab：** 加入。实盘监控页底部Tab增加"决策历史"，展示最近N条
TradingDecision（signal/confidence/reasoning）。需后端新增API或扩展snapshot。

**进化配置展示：** 要。进化优化页显示GA参数（population_size/mutation_rate等），
让用户知道当前进化在用什么配置跑。数据来源：evolution.get_current_config()。

**侧边栏状态区：** 显示当前交易对（BTC/USDT）+ 当前选中时间周期（H4）+
运行状态 + WS连接 + 运行时长 + 插件计数。

**错误展示：** 双层机制：
- 严重错误（熔断器触发）：页面顶部红色横幅告警，可关闭
- 一般错误（last_error）：侧边栏状态区变红色，点击展开看详情
- 数据来源：snapshot.orchestrator.last_error + circuit_breaker_tripped

---

## 十二、后端最小扩展清单（前端重构后执行）

| 改动 | 文件 | 说明 |
|------|------|------|
| 新增 POST /api/evolution/start | src/api/app.py | 调用 evolution.start_evolution() |
| 新增 POST /api/evolution/stop | src/api/app.py | 调用 evolution.stop_evolution() |
| 新增 GET /api/decisions | src/api/app.py | 调用 orchestrator.get_decision_history() |
| 新增 GET /api/evolution/config | src/api/app.py | 调用 evolution.get_current_config() |
| 新增 get_recent_logs() | audit_logger/plugin.py | 读取JSONL尾部N行 |
| WS system_status 扩展 | src/api/app.py | 附加 orchestrator.last_error |

---

## 十三、设计研究结论（2026-03-22 凌晨补充）

### 13.1 参考项目

| 项目 | Stars | 为什么参考 |
|------|-------|----------|
| dYdX v4-web | 107 | 技术栈完全一致(React+Tailwind+Vite+TV Charts)，生产级交易终端 |
| GMX Interface | 231 | 代码分层优秀(config→lib→domain→components→pages) |
| OpenBB | 63,400 | Python FastAPI + React 架构与我们完全一致 |
| Optuna Dashboard | 757 | 超参数优化可视化，与进化页面高度对应 |
| Aim | 6,000 | 训练曲线可视化+Start/Stop控制模式最佳 |

### 13.2 TradingView 真实色值（从DOM抓取）

- 主背景: #131722
- 面板: #1E222D
- 边框: #2A2E39
- 主文字: #D1D4DC
- 次文字: #787B86
- 涨: #26A69A / 跌: #EF5350

**决策：** 采用 TradingView 色系而非之前的 Binance 色系，更适合长时间盯盘。

### 13.3 基于研究的设计调整

1. **侧边栏活跃状态** — 左边框 3px accent色 + 半透明背景（TV模式）
2. **进化页 AI Advisor** — 嵌入页面内（折叠式），不单独Tab
3. **Start/Stop 按钮** — 直接放在进化页 StatusBar 中
4. **图表库** — 保持手工SVG（不加依赖），可增强hover效果
5. **模拟盘/实盘标识** — 顶部醒目标签(amber=模拟, red=实盘)
