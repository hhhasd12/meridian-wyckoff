# V4 状态机端到端上线计划

> 目标：让你能在浏览器K线图上看到 V4 状态机的实时标注（PS/SC/AR/ST...），
> 并通过三大原则分数面板判断识别是否正确。

## 当前状态

- ✅ V4 状态机框架完成（打分器 + 推进器 + 22检测器 + 边界管理）
- ✅ 78 个新单元测试全部通过
- ✅ engine.py / plugin.py 已切换到 V4
- ✅ 前端有 StateMarkers 组件（K线图上标注状态事件）
- ❌ V4 新概念（hypothesis/BarFeatures/三大原则分数）未暴露到 API
- ❌ 前端未连接 V4 数据
- ❌ 检测器灵敏度未调优（真实数据上可能全停在 IDLE）
- ❌ 交易策略层未适配 V4 信号

## Phase A：API 数据管道（让后端输出 V4 数据）

### A-1. 扩展 WyckoffEngine 状态输出
文件：`src/plugins/wyckoff_engine/plugin.py` `get_current_state()`
- 添加 V4 三层语义：`hypothesis`（当前假设）、`hypothesis_status`、`bars_held`
- 添加三大原则分数：`supply_demand`、`cause_effect`、`effort_result`
- 添加 BarFeatures 快照：`volume_ratio`、`body_ratio`、`is_stopping_action`
- 添加边界信息：`boundaries`（SC_LOW/AR_HIGH 等关键价位）

### A-2. 扩展 API snapshot 端点
文件：`src/api/app.py` `/api/system/snapshot`
- 在 snapshot 响应中包含 A-1 的新字段
- 添加 `/api/wyckoff/state` 专用端点（轻量，只返回状态机数据）

### A-3. WebSocket 推送 V4 状态变化
文件：`src/api/app.py` WebSocket handler
- 状态变化时推送 `wyckoff_state` topic 消息
- 包含完整的三层语义 + 三大原则分数

## Phase B：前端可视化（让你看到状态标注）

### B-1. 更新 TypeScript 类型定义
文件：`frontend/src/types/api.ts`
- 添加 V4 新字段类型：`HypothesisInfo`、`PrincipleScores`、`BoundaryInfo`

### B-2. K线图状态标注增强
文件：`frontend/src/chart-plugins/StateMarkers.ts`
- 在每根K线上标注当前识别的事件（PS/SC/AR 等）
- 颜色区分已确认 vs 假设中（实线 vs 虚线）
- 关键价位水平线（SC_LOW、AR_HIGH 等）

### B-3. 三大原则分数面板
文件：新建 `frontend/src/components/PrinciplesPanel.tsx`
- 供需分数条（-1 ~ +1，红绿渐变）
- 因果累积度条（0 ~ 1）
- 努力结果和谐度条（-1 ~ +1）
- 实时更新（WebSocket 驱动）

### B-4. 状态机时间线面板
文件：新建 `frontend/src/components/StateMachinePanel.tsx`
- 当前阶段（A/B/C/D/E）
- 已确认事件链（PS → SC → AR → ST → ...）
- 活跃假设状态（HYPOTHETICAL/TESTING + 置信度 + 持续K线数）
- 关键价位列表（SC_LOW=xxx, AR_HIGH=xxx）

## Phase C：真实数据验证（调优检测器）

### C-1. 获取历史数据
- 使用 `fetch_data.py` 拉取 BTC/USDT H4 最近 2000 根K线

### C-2. 运行 V4 并输出诊断报告
- 写一个 `scripts/v4_diagnosis.py` 脚本
- 逐根喂K线，记录每根的 BarFeatures + 状态变化
- 输出：状态转换时间线 + 停留在 IDLE 的比例

### C-3. 调优检测器阈值
- 根据 C-2 的诊断，调整各检测器的置信度阈值
- 目标：在已知的威科夫结构区域能正确识别 ≥70% 的事件
- 关键：PS/SC 是入口事件，如果它们检测不到，后续全部停滞

## Phase D：交易策略适配（最后做）

### D-1. Orchestrator 适配
- 基于 V4 的 WyckoffStateResult.signal 做交易决策
- 接口不变（WyckoffSignal.BUY_SIGNAL/SELL_SIGNAL），逻辑需要重新验证

### D-2. Position Manager 验证
- 确认 trading.signal 事件格式与 V4 输出一致
- 端到端：V4 识别 Spring → BUY_SIGNAL → 开仓

### D-3. 进化系统适配
- 回测器使用 V4 引擎
- 调优 V4 检测器参数使回测能产出有意义的交易

## 执行顺序

```
Phase A (API) → Phase B (前端) → Phase C (调优) → Phase D (交易)
     半天          1-2天           1天              1天
```

Phase A+B 完成后你就能在浏览器里看到 V4 的实时状态标注。
Phase C 是你看着前端微调检测器灵敏度的过程。
Phase D 是确认交易链路正常后最后接入的。

## 关键约束

- WyckoffEngine.process_bar() → BarSignal 接口不变
- 前端现有的K线图（LWC v5.1）保持不动，只新增状态标注层
- 不改 WebSocket 协议基础结构，只增加 topic
