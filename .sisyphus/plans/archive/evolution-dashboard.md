# 进化仪表盘开发计划

## 目标
让进化过程在前端实时可视化：适应度曲线、种群状态、WFA结果、防过拟合检查、交易记录。

## 现状分析
- 前端 EvolutionTab 存在但是空壳（6个"—"卡片）
- 后端 get_evolution_status() 只返回 {status, cycle_count, start_time}
- 进化插件不发送任何事件到事件总线
- WebSocket 已有 evolution_progress 通道但无数据
- run_evolution.py 是独立脚本，不经过 API 服务器

## 架构决策
**关键问题**：run_evolution.py 独立运行，不经过 WyckoffApp/API。
**方案**：进化仪表盘读取 evolution_results/ 目录的 JSON 文件 + 后端轮询。
不改 run_evolution.py 的运行方式，只加 API 读取层。

## Must Have
1. 适应度曲线图（每代 best/avg fitness 随时间变化）
2. 当前最优参数展示（权重分布、阈值）
3. WFA 验证结果（OOS退化率、通过/失败）
4. 五层防过拟合状态面板（5个指标的通过/失败）
5. 进化盘交易统计（胜率、Sharpe、最大回撤）
6. 实时进度信息（当前代数/Cycle数）

## Must NOT Have
1. 不改 run_evolution.py 的运行机制（它保持独立脚本）
2. 不引入新的前端依赖（用现有 Recharts 或纯 CSS）
3. 不做实时 WebSocket 推送（轮询 evolution_results/ 即可）
4. 不做进化控制（启动/停止按钮 — 进化用终端管理）

## 实施分波

### Wave A: 后端 API（2个新端点）
- Task A1: GET /api/evolution/results — 读取 evolution_results/*.json，返回所有 cycle 结果
- Task A2: GET /api/evolution/latest — 返回最新一个 cycle 的详细信息

### Wave B: 前端类型 + Store
- Task B1: 扩展 types/api.ts — EvolutionCycleResult 类型
- Task B2: 扩展 store.ts — evolutionResults 切片 + fetch action
- Task B3: 扩展 api.ts — fetchEvolutionResults() 调用

### Wave C: 前端组件（重写 EvolutionTab）
- Task C1: FitnessChart — 折线图（generation vs best/avg fitness）
- Task C2: BestConfigPanel — 当前最优参数可视化（权重饼图或条形图）
- Task C3: ValidationPanel — WFA + AntiOverfit 5层状态
- Task C4: EvolutionStatsPanel — 进化盘交易统计摘要
- Task C5: 组装到 EvolutionTab.tsx 替换空壳

### Wave D: 轮询 + 集成
- Task D1: App.tsx 添加 evolution results 轮询（30秒间隔）
- Task D2: 端到端测试（后端API + 前端渲染）

## 验证标准
- pytest tests/ ≥ 953 passed
- 前端 tsc 0 errors
- 前端 vite build 成功
- API 端点返回正确 JSON
