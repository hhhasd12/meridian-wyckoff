HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- "威科夫引擎前端重构 — 全中文 + 双面板 + UI美化"
- "我们要完全重新设计前端样式，我们要先设计，再说，设计要十分精美。不要命令行那种，比不上交易所的前端，但是也要十分舒适和舒畅，先讨论设计，制定计划，然后再说其他的。"
- "深灰色，侧边导航栏，TV风格，字体不懂，你来安排，适合风格就行，动画要丰富动效。这些都是次要的，主要的是功能的丰富程度，我们的后端，需要的重要的部分都要能看到"
- "进化控制按钮一定要有"
- "日志肯定要啊，但是需要进行一定的优化"
- "报错怎么出现？能不能稳定传递到前端？"

GOAL
----
执行前端重构计划书(.sisyphus/plans/frontend-redesign.md, 562行)，实现全中文化+侧边导航双视图+功能丰富+TradingView暗色风格的专业交易终端前端。

WORK COMPLETED
--------------
- 我完整读取了所有22个前端文件（~2000行）和后端API层（src/api/app.py 641行）
- 我深度分析了18个后端插件的数据输出能力，发现当前前端只展示约25%的后端能力
- 我研究了8个开源交易终端项目(dYdX/GMX/Uniswap/OpenBB/Optuna/Aim等)
- 我抓取了TradingView实际DOM，获取了精确的暗色主题色值和布局模式
- 我编写了完整的设计计划书（562行）和研究笔记
- 我与用户进行了3轮设计讨论，确认了所有关键决策
- 代码尚未开始修改

CURRENT STATE
-------------
- 前端代码全部是原始状态，未做任何修改
- 计划书和研究笔记已就绪
- npm run build 当前可以通过（需验证）
- 后端18个插件全部ACTIVE，1143 tests passing

PENDING TASKS
-------------
Todo list (0/11 completed):
1. Phase 1: tailwind.config.js 新色板 + index.css 组件样式更新
2. Phase 1: 新建 Sidebar.tsx 侧边导航栏（方案B，~140px，文字+图标+底部状态）
3. Phase 1: store.ts 增加 activePage 状态 + types/api.ts 补充类型
4. Phase 1: App.tsx 重写为侧边栏+页面路由结构 → npm run build 验证
5. Phase 2: 新建 TradingPage.tsx + Header.tsx 改为页内顶栏 + 中文化
6. Phase 2: WyckoffPanel.tsx 中文化 + 新建 MultiTFStatus.tsx 多TF对比
7. Phase 2: SignalPanel.tsx → 决策信息面板(编排器状态+信号+插件) + 中文化
8. Phase 2: BottomTabs/PositionsTab/TradesTab/LogsTab 中文化+增强 → npm run build 验证
9. Phase 3: 新建 EvolutionPage.tsx + EvolutionTab.tsx 中文化+SVG颜色+样式增强
10. Phase 3: AdvisorTab.tsx 中文化+结构化展示 → npm run build 验证
11. Phase 4: 动效添加（脉冲/过渡/骨架屏/闪烁）+ 最终构建验证

KEY FILES
---------
- .sisyphus/plans/frontend-redesign.md - 完整设计计划书(562行，必读)
- .sisyphus/notepads/frontend-redesign/learnings.md - 研究笔记(TV色值/参考项目/设计调整)
- frontend/src/App.tsx - 主入口，需重写为侧边栏+页面路由
- frontend/src/core/store.ts - Zustand状态管理，需增加activePage
- frontend/src/types/api.ts - 类型定义，需补充
- frontend/tailwind.config.js - Tailwind主题，需重写色板
- frontend/src/index.css - 全局样式，需重写
- frontend/src/components/EvolutionTab.tsx - 最复杂组件(425行)
- frontend/src/components/WyckoffPanel.tsx - 威科夫面板(193行)
- src/api/app.py - 后端API(641行，不改但需理解)

IMPORTANT DECISIONS
-------------------
- 两个视图(实盘/进化)通过Zustand activePage切换，不用react-router
- 侧边栏方案B：~140px宽，文字+图标+底部状态区，活跃状态用左边框3px accent
- 色彩采用TradingView色系：#131722(背景)/#1E222D(面板)/#2A2E39(边框)
- 涨跌色: #26A69A(涨)/#EF5350(跌) — TV标准色
- 切换视图时才刷新数据，非活跃视图不轮询
- 图表颜色(chart-plugins/hooks)本次不改
- 错误双层展示：严重(熔断)=顶部红色横幅，一般=侧边栏变红
- 进化控制Start/Stop按钮放在StatusBar中
- AI Advisor嵌入进化页面（折叠式），不单独Tab
- 底部Tab新增"决策历史"Tab
- 侧边栏底部显示：交易对+时间周期+运行状态+WS连接+运行时长+插件计数
- 模拟盘/实盘标识：amber=模拟, red=实盘

EXPLICIT CONSTRAINTS
--------------------
- 不修改后端代码（src/目录不动） — 但后续需小改后端新增进化控制API
- 不加新npm依赖（用现有React/Tailwind/LWC/Zustand/react-query/lucide-react）
- npm run build 必须成功
- 保持与后端API兼容性
- 写入内容每次最大不超过200行，100行为标准（AGENTS.md规则）
- 所有面向用户的输出必须使用中文

CONTEXT FOR CONTINUATION
------------------------
- 计划书是权威参考：.sisyphus/plans/frontend-redesign.md（先读这个）
- 研究笔记有TV精确色值和设计调整：.sisyphus/notepads/frontend-redesign/learnings.md
- 后端snapshot返回多TF状态机数据(wyckoff_engine.state_machines)，当前前端未展示
- 后端3个方法不存在：get_latest_signal()/get_recent_logs()/get_closed_trades()
- WS recent_logs始终为空，日志Tab需graceful处理
- EvolutionTab.tsx(425行)有SVG硬编码颜色需同步更新
- 现有底部Tab状态(BottomTabs)用本地useState，未连接store的activeBottomTab
- 建议实施顺序严格按Phase 1→2→3→4，每Phase结束npm run build验证
