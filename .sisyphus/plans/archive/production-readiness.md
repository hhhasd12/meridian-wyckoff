# 威科夫引擎生产就绪修复计划

## TL;DR

> **目标**: 修复42个审计问题 + 4个新发现问题，让系统从"架构完整"升级到"生产安全"
> 
> **交付物**: 全部C/H/M/L级bug修复 + Kelly仓位 + Telegram告警 + Docker部署 + 审计日志
> 
> **预估工作量**: Large（8个Work Unit，约35个task）
> **并行执行**: YES — 8波
> **关键路径**: Unit 1(信号链) → Unit 2(杠杆) → Unit 3(风控) → Unit 5(交易所) → Unit 6(持久化)

---

## Context

### Original Request
v3架构重建(Phase 0-9)全部完成，859 tests passing。但4个探索代理并行审计发现42/45个报告的问题仍然存在。用户要求一次性全部修复，采用测试跟随策略。

### Metis Review
- **发现新bug NEW-1**: app.py发布`system.stopping`但position_manager订阅`system.shutdown`，关闭事件从未触发
- **风险警告**: Position dataclass改动影响859个测试 → 必须用`leverage: float = 1.0`默认值保持兼容
- **排序建议**: 信号链修复 → 资金安全 → 系统安全 → 新功能 → 文档清理
- **Windows注意**: 用`os.replace()`不用`os.rename()`做原子写入

---

## Work Objectives

### Core Objective
修复全部生产安全问题，使系统可以安全进入Phase A（真实交易所连通+Paper Trading）。

### Must Have
- 杠杆正确计算（PnL + 仓位大小）
- 亏损限制真正执行（日/周/回撤）
- 强平价格监控
- 交易所端止损单
- 平仓失败重试
- 纸盘滑点+手续费
- 事件链完整可用
- 做空条件逻辑修复
- 关闭/恢复安全
- 审计日志持久化

### Must NOT Have
- 不修改evolution/bar_by_bar_backtester.py的PnL公式（它有独立逻辑）
- 不改变_process_market_data()签名（双路径共享入口）
- 不引入新的外部依赖（Telegram用aiohttp/urllib）
- 不重构插件架构（M1耦合问题仅标记TODO，不做大改）

---

## Verification Strategy

- **Infrastructure exists**: YES (pytest)
- **Automated tests**: Tests-after
- **Framework**: pytest + pytest-asyncio
- **每个Unit完成后**: `pytest tests/ -v` 必须 ≥ 859 passed

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — 信号链修复 + 引擎bug):
├── Task 1-3:  Unit 1 信号链修复 [H5, M4, H6]
├── Task 4-5:  Unit 4 引擎bug修复 [H4, M6]
└── Task 6:    Unit 8a 文档清理 [L1-L7]

Wave 2 (After Wave 1 — 杠杆 + 风控，需要信号链工作):
├── Task 7-9:  Unit 2 杠杆全链路 [C1, C2]
├── Task 10-13: Unit 3 风控执行层 [C3, C4, C7, M8]
└── Task 14:   Unit 8b 配置清理 [M5, M7, L10]

Wave 3 (After Wave 2 — 交易所 + 持久化):
├── Task 15-18: Unit 5 交易所安全 [H2, H3, C6, M9]
├── Task 19-22: Unit 6 关闭与持久化 [C5, H7, H8, NEW-1]
└── Task 23:    Unit 8c 版本统一 [L3, L4, L8, L9]

Wave 4 (After Wave 3 — 新功能):
├── Task 24-26: Unit 7a Kelly仓位 + 反马丁
├── Task 27-29: Unit 7b Telegram告警插件
├── Task 30-31: Unit 7c 审计日志插件
└── Task 32:    Unit 7d 优雅降级分阶段

Wave 5 (After Wave 4 — 部署 + 最终验证):
├── Task 33-34: Unit 8d Docker部署
├── Task 35:    Unit 9 全量集成测试
└── Task 36:    Unit 10 README更新

Wave FINAL (After ALL — 4 parallel reviews):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

---

## TODOs

- [x] 1. **[H5] data_pipeline事件Schema修复**

  **What to do**:
  - 修改 `src/plugins/data_pipeline/plugin.py` 的 `_publish_ohlcv_ready()` 方法
  - 当前发送 `{df, symbol, timeframe}` 单TF格式
  - 改为：在内部累积同一symbol的多TF数据，全部就绪后发送 `{symbol, timeframes, data_dict: {tf: DataFrame}}`
  - 或者在orchestrator端适配：接收单TF事件，累积到dict，全部TF到齐后触发处理

  **Must NOT do**: 不修改 `_process_market_data()` 签名

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 1 | Blocks: Task 7-9 | Blocked By: None

  **References**:
  - `src/plugins/data_pipeline/plugin.py:397-412` — 当前 _publish_ohlcv_ready 发送格式
  - `src/plugins/orchestrator/plugin.py:122-144` — _on_data_ready 期望格式
  - `src/plugins/orchestrator/plugin.py:148-180` — _fetch_data_from_connector 轮询路径（不能破坏）

  **Acceptance Criteria**:
  - [ ] orchestrator的_on_data_ready能收到并处理data_pipeline事件
  - [ ] 轮询路径_fetch_data_from_connector仍正常工作
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **QA Scenarios**:
  ```
  Scenario: 事件驱动路径正常工作
    Tool: Bash (pytest)
    Steps:
      1. 编写测试：mock data_pipeline发送ohlcv_ready事件
      2. 验证orchestrator._on_data_ready收到并调用_process_market_data
      3. 验证返回TradingDecision（非None）
    Expected Result: orchestrator成功处理事件数据
    Evidence: .sisyphus/evidence/task-1-event-schema.txt

  Scenario: 轮询路径不受影响
    Tool: Bash (pytest)
    Steps:
      1. 运行现有orchestrator测试
      2. 验证_fetch_data_from_connector路径无回归
    Expected Result: 全部现有测试通过
    Evidence: .sisyphus/evidence/task-1-polling-path.txt
  ```

  **Commit**: YES (groups with Task 2,3)
  - Message: `fix(signal-path): repair event schema mismatch [H5]`
  - Files: `src/plugins/data_pipeline/plugin.py`, `src/plugins/orchestrator/plugin.py`

- [x] 2. **[M4] breakout_validator返回键名修复**

  **What to do**:
  - 修改 `src/plugins/wyckoff_engine/engine.py` 第487-498行
  - 当前用 `.get("is_valid", False)` 但validator返回的是 `status` 枚举
  - 修复：读取 `status` 字段并转换为 `is_valid` 布尔值
  - 或修改 breakout_validator 在返回dict中增加 `is_valid` 键

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 1 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/signal_validation/breakout_validator.py:86` — detect_initial_breakout返回格式
  - `src/plugins/wyckoff_engine/engine.py:487-498` — engine读取breakout结果

  **Acceptance Criteria**:
  - [ ] 当breakout_validator检测到有效突破时，engine.py中is_valid为True
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **QA Scenarios**:
  ```
  Scenario: 突破验证正确传递
    Tool: Bash (pytest)
    Steps:
      1. 构造含有效突破的数据
      2. 调用engine._run_perception()
      3. 检查返回的PerceptionResult.breakout_status.is_valid
    Expected Result: is_valid=True（而非恒False）
    Evidence: .sisyphus/evidence/task-2-breakout-valid.txt
  ```

  **Commit**: YES (groups with Task 1,3)

- [x] 3. **[H6] EventBus异步处理器支持**

  **What to do**:
  - 修改 `src/kernel/event_bus.py` 第309-319行
  - 当前sync emit遇到async handler直接skip+warning
  - 修复：检测是否有运行中的event loop，如有则schedule异步任务；如无则用asyncio.run()执行
  - 注意Windows兼容性

  **Must NOT do**: 不改变同步handler的执行行为

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 1 | Blocks: None | Blocked By: None

  **References**:
  - `src/kernel/event_bus.py:309-319` — 当前sync emit跳过async handler
  - `src/kernel/event_bus.py:281` — emit方法签名

  **Acceptance Criteria**:
  - [ ] sync emit不再跳过async handler
  - [ ] 不影响现有同步handler
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **QA Scenarios**:
  ```
  Scenario: 异步handler被正确调用
    Tool: Bash (pytest)
    Steps:
      1. 注册async handler到EventBus
      2. 用sync emit发布事件
      3. 验证async handler被调用
    Expected Result: handler执行完毕，无warning日志
    Evidence: .sisyphus/evidence/task-3-async-handler.txt
  ```

  **Commit**: YES (groups with Task 1,2)

- [x] 4. **[H4] 做空条件恒真bug修复**

  **What to do**:
  - 修改 `src/plugins/wyckoff_engine/engine.py` 第1013-1038行
  - `_generate_decision()` 中第3个or条件 `state.direction == StateDirection.DISTRIBUTION` 与外层if完全相同
  - 删除该冗余条件，只保留market_regime检查（BEARISH/DOWN）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 1 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/wyckoff_engine/engine.py:1013-1038` — _generate_decision做空逻辑

  **Acceptance Criteria**:
  - [ ] Distribution阶段+NEUTRAL regime不触发做空信号
  - [ ] Distribution阶段+BEARISH regime仍触发做空信号
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **QA Scenarios**:
  ```
  Scenario: NEUTRAL体制下不做空
    Tool: Bash (pytest)
    Steps:
      1. 构造state.direction=DISTRIBUTION, regime=NEUTRAL
      2. 调用_generate_decision
      3. 验证不产生SHORT信号
    Expected Result: signal != SELL
    Evidence: .sisyphus/evidence/task-4-short-fix.txt
  ```

  **Commit**: YES (groups with Task 5)
  - Message: `fix(engine): correct short-sell condition [H4,M6]`

- [x] 5. **[M6] WyckoffEnginePlugin暴露API**

  **What to do**:
  - 修改 `src/plugins/wyckoff_engine/plugin.py`
  - 添加 `get_current_state()` 方法，返回engine当前状态
  - 添加 `process_market_data()` 代理方法
  - 使api/app.py的调用不再返回None

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 1 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/wyckoff_engine/plugin.py` — 当前空壳
  - `src/api/app.py:222` — 调用engine.get_current_state()

  **Acceptance Criteria**:
  - [ ] plugin.get_current_state() 返回非None
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 4)

- [x] 6. **[L1-L7] 文档与依赖清理**

  **What to do**:
  - L1: config.yaml:278 更新 run_live.py → run.py
  - L2: README测试数量更新为当前实际值
  - L5: README/AGENTS.md删除agent_teams引用
  - L6: requirements.txt添加pytest-asyncio
  - L7: requirements.txt删除未使用依赖（vectorbt, backtesting, yfinance, redis, dash-bootstrap-components, ta-lib）

  **Must NOT do**: 不删除实际使用的依赖

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 1 | Blocks: None | Blocked By: None

  **Acceptance Criteria**:
  - [ ] config.yaml无过时引用
  - [ ] requirements.txt只含使用中的依赖+pytest-asyncio
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES
  - Message: `chore(docs): cleanup stale references [L1,L2,L5,L6,L7]`

- [x] 7. **[C1] Position类添加leverage字段 + PnL修复**

  **What to do**:
  - 采用 **Model A: Size放大** — size字段代表杠杆后数量，PnL公式不变
  - 修改 `src/plugins/position_manager/types.py` Position dataclass
  - 添加 `leverage: float = 1.0`（默认1.0保持859测试兼容，用于记录和显示）
  - PnL公式 `(exit-entry)*size` **不需要改**（size已是杠杆后数量）
  - 修复 `calculate_unrealized_pnl()` 中pnl_pct需要乘以leverage（百分比相对于保证金）
  - 修复 `_calculate_pnl_pct()` 同理：`pnl_pct = price_change_pct * leverage`
  - **关键**: position_manager.calculate_position_size()需要在Task 8中修改为输出杠杆后size

  **Must NOT do**: 不修改evolution/bar_by_bar_backtester.py的PnL公式

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: Task 10-13 | Blocked By: Task 1-3

  **References**:
  - `src/plugins/position_manager/types.py:40-128` — Position dataclass
  - `src/plugins/position_manager/position_manager.py:387-410` — _calculate_pnl
  - `src/plugins/exchange_connector/exchange_executor.py:479-484` — execute_trade_result PnL
  - 用 `lsp_find_references` 检查Position构造的所有调用点

  **Acceptance Criteria**:
  - [ ] Position(leverage=5)下1%价格变动，pnl_pct=5%（相对保证金）
  - [ ] pnl绝对值 = (exit-entry)*size（size已是杠杆后量，不额外乘）
  - [ ] 默认leverage=1.0不影响现有测试
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **QA Scenarios**:
  ```
  Scenario: 杠杆PnL正确计算
    Tool: Bash (pytest)
    Steps:
      1. 创建Position(entry_price=100, size=1, leverage=5)
      2. 计算unrealized_pnl(current_price=101)
      3. 断言pnl=5.0（1%×5倍=5%）
    Expected Result: pnl=5.0, pnl_pct=0.05
    Evidence: .sisyphus/evidence/task-7-leverage-pnl.txt
  ```

  **Commit**: YES (groups with Task 8,9)
  - Message: `fix(leverage): add leverage field, correct all PnL calculations [C1,C2]`

- [x] 8. **[C2] 仓位大小计算纳入杠杆**

  **What to do**:
  - 修改 `src/plugins/position_manager/position_manager.py:55-90`
  - `calculate_position_size()` 添加 `leverage` 参数
  - 修改 max_size_by_balance 考虑杠杆放大：`max_size = balance * max_pct * leverage / price`
  - 修改 `plugin.py:290-299` 传入leverage参数

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: None | Blocked By: Task 7

  **References**:
  - `src/plugins/position_manager/position_manager.py:55-90` — calculate_position_size
  - `src/plugins/position_manager/plugin.py:290-299` — 调用处
  - `config.yaml:17` — leverage配置值

  **Acceptance Criteria**:
  - [ ] leverage=5时仓位大小约为leverage=1的5倍
  - [ ] 不超过max_position_size限制
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 7,9)

- [x] 9. **[C1+C2] 杠杆集成测试**

  **What to do**:
  - 新建 `tests/plugins/test_leverage_integration.py`
  - 测试完整链路：开仓(带leverage) → 价格变动 → PnL计算 → 止损检查
  - 测试PositionJournal序列化/反序列化leverage字段

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: None | Blocked By: Task 7,8

  **Acceptance Criteria**:
  - [ ] 杠杆全链路端到端通过
  - [ ] Journal恢复后leverage值正确

  **Commit**: YES (groups with Task 7,8)

- [x] 10. **[C3] 亏损限制执行层实现**

  **What to do**:
  - 在 `src/plugins/risk_management/` 新建 `capital_guard.py`
  - 实现 `CapitalGuard` 类：读取config的daily_loss_limit/weekly_loss_limit/max_drawdown_limit
  - 跟踪每日/每周累计亏损，检查是否超限
  - 提供 `is_trading_allowed() -> bool` 接口
  - 超限时发布 `risk_management.circuit_breaker_tripped` 事件

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: Task 15-18 | Blocked By: Task 7-9

  **References**:
  - `config.yaml:108-110` — daily_loss_limit=0.05, weekly=0.1, max_drawdown=0.2
  - `src/plugins/risk_management/plugin.py` — 现有风控插件
  - `src/plugins/risk_management/circuit_breaker.py` — 现有熔断器（仅数据质量）

  **Acceptance Criteria**:
  - [ ] 日亏损>5%后is_trading_allowed()返回False
  - [ ] 周亏损>10%后同样阻止
  - [ ] 回撤>20%后同样阻止
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **QA Scenarios**:
  ```
  Scenario: 日亏损限制生效
    Tool: Bash (pytest)
    Steps:
      1. 初始化CapitalGuard(daily_limit=0.05, balance=10000)
      2. 记录亏损交易: -300, -200, -100 (累计-600 = 6%)
      3. 调用is_trading_allowed()
    Expected Result: False
    Evidence: .sisyphus/evidence/task-10-daily-limit.txt
  ```

  **Commit**: YES (groups with Task 11,12,13)
  - Message: `fix(risk): implement capital loss limits, liquidation guard [C3,C4,C7,M8]`

- [x] 11. **[C4] 强平价格监控**

  **What to do**:
  - 在 `capital_guard.py` 中添加 `check_liquidation_risk()` 方法
  - 根据leverage和保证金模式计算强平价格
  - 逐仓: liq_price = entry × (1 - 1/leverage × (1-buffer))
  - 价格逼近强平线(距离<liquidation_buffer)时发出告警+强制平仓

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: None | Blocked By: Task 7

  **References**:
  - `config.yaml:114` — liquidation_buffer: 0.1

  **Acceptance Criteria**:
  - [ ] 5x杠杆多头entry=100, 价格跌到82时触发预警（距强平80还有2.5%<10%buffer）
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 10,12,13)

- [x] 12. **[C7] PositionManager开仓前检查熔断器**

  **What to do**:
  - 修改 `src/plugins/position_manager/plugin.py` 的 `_try_open_position()`
  - 在方法开头添加熔断器检查：通过EventBus或直接引用获取熔断状态
  - 熔断激活时拒绝开仓并记录日志

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/position_manager/plugin.py:248-329` — _try_open_position
  - `src/plugins/orchestrator/plugin.py:206-209` — orchestrator层熔断检查（参考）

  **Acceptance Criteria**:
  - [ ] 熔断激活时_try_open_position返回且不开仓
  - [ ] 熔断恢复后可正常开仓
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 10,11,13)

- [x] 13. **[M8] 连续亏损保护**

  **What to do**:
  - 在 `capital_guard.py` 中添加连续亏损计数器
  - 连续亏损N次后（默认5次）降低仓位至50%
  - 连续亏损2N次后停止交易
  - 连续盈利时恢复

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: None | Blocked By: Task 10

  **Acceptance Criteria**:
  - [ ] 连续亏损5次后仓位降半
  - [ ] 连续亏损10次后停止交易
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 10,11,12)

- [x] 14. **[M5,M7,L10] 配置清理**

  **What to do**:
  - M5: 统一timeframes格式，data_sources.crypto.timeframes改为["H4","H1","M15","M5"]
  - M7: anti_overfit.py Monte Carlo改用`np.random.RandomState(None)`或os.urandom种子
  - L10: config.yaml添加position_manager配置节

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2 | Blocks: None | Blocked By: None

  **Acceptance Criteria**:
  - [ ] grep config.yaml中timeframes格式统一
  - [ ] Monte Carlo每次运行结果不同
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES
  - Message: `fix(config): unify timeframes format, randomize MC seed [M5,M7,L10]`

- [x] 15. **[C6] 纸盘交易添加滑点和手续费模拟**

  **What to do**:
  - 修改 `src/plugins/exchange_connector/exchange_executor.py` 的 `_simulate_order()`
  - 添加 slippage_rate（默认0.0005=0.05%）和 commission_rate（默认0.001=0.1%）
  - 市价单：execution_price = price × (1 + slippage)（买入）或 × (1 - slippage)（卖出）
  - 扣除手续费：从paper_balance中扣除 execution_price × size × commission_rate

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: Task 7-9

  **References**:
  - `src/plugins/exchange_connector/exchange_executor.py:371-432` — _simulate_order
  - `src/plugins/evolution/bar_by_bar_backtester.py` — 参考其slippage/commission实现

  **Acceptance Criteria**:
  - [ ] 模拟买入价格 > 原始价格（含滑点）
  - [ ] paper_balance正确扣除手续费
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 16,17,18)
  - Message: `fix(exchange): add exchange SL/TP, order retry, slippage model [H2,H3,C6,M9]`

- [x] 16. **[H2] 交易所端止损单**

  **What to do**:
  - 修改 `exchange_executor.py` 的 `_place_order()` 方法
  - 支持 `STOP_MARKET` 订单类型
  - 开仓成功后，自动向交易所提交止损单（STOP_MARKET）
  - 纸盘模式：在内部维护pending_stop_orders列表，价格触发时执行
  - 在 `kernel/types.py` OrderType枚举中添加 `STOP_MARKET`

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: Task 7

  **References**:
  - `src/plugins/exchange_connector/exchange_executor.py:166-220` — _place_order
  - `src/kernel/types.py` — OrderType枚举

  **Acceptance Criteria**:
  - [ ] 开仓后验证交易所有pending STOP_MARKET订单
  - [ ] 价格触发止损时自动执行
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 15,17,18)

- [x] 17. **[H3] 平仓失败重试机制**

  **What to do**:
  - 修改 `src/plugins/position_manager/plugin.py` 的 `_execute_exit()`
  - 添加重试逻辑：失败后指数退避重试，最多3次
  - 3次都失败后：触发CRITICAL告警，将失败请求加入pending_exits队列
  - 添加定时检查pending_exits队列的逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/position_manager/plugin.py:411-447` — _execute_exit
  - `src/utils/error_handler.py` — 现有retry装饰器

  **Acceptance Criteria**:
  - [ ] 第1次失败后等待1秒重试
  - [ ] 3次失败后仓位加入pending队列
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 15,16,18)

- [x] 18. **[M9] 部分成交处理 + 订单状态增强**

  **What to do**:
  - 修改 `exchange_executor.py`
  - 添加部分成交处理：PARTIAL状态时按实际成交量更新仓位
  - 添加超时处理：限价单30秒未全部成交时取消剩余
  - 在kernel/types.py OrderStatus中添加EXPIRED状态

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: None

  **Acceptance Criteria**:
  - [ ] 部分成交时仓位按实际成交量记录
  - [ ] 超时后剩余部分被取消
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 15,16,17)

- [x] 19. **[NEW-1+C5] 关闭事件名修复 + 市价平仓**

  **What to do**:
  - 修复事件名不匹配：`app.py:226` 发布 `system.stopping` 但 `plugin.py:106` 订阅 `system.shutdown`
  - 统一为一个事件名（推荐改app.py为`system.shutdown`）
  - 修复 `_on_shutdown()`：从ExchangeExecutor获取当前市场价而非用entry_price
  - 如无法获取市价，用最后已知价格而非入场价

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: None

  **References**:
  - `src/app.py:226` — 发布system.stopping
  - `src/plugins/position_manager/plugin.py:106` — 订阅system.shutdown
  - `src/plugins/position_manager/plugin.py:534-542` — _on_shutdown用entry_price

  **Acceptance Criteria**:
  - [ ] shutdown事件正确触发_on_shutdown
  - [ ] 平仓使用市场价而非入场价
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **QA Scenarios**:
  ```
  Scenario: 关闭时正确平仓
    Tool: Bash (pytest)
    Steps:
      1. 创建WyckoffApp，加载position_manager
      2. 模拟开仓(entry=100)，当前价=110
      3. 触发shutdown
      4. 验证平仓PnL基于110而非100
    Expected Result: PnL > 0（而非恒为0）
    Evidence: .sisyphus/evidence/task-19-shutdown.txt
  ```

  **Commit**: YES (groups with Task 20,21,22)
  - Message: `fix(persistence): atomic writes, shutdown event, journal fsync [C5,H7,H8,NEW-1]`

- [x] 20. **[H7] PositionJournal原子写入 + fsync**

  **What to do**:
  - 修改 `src/plugins/position_manager/position_journal.py` 的 `_append_entry()`
  - 添加 `f.flush()` + `os.fsync(f.fileno())` 确保数据落盘
  - compact()方法改用原子写入：写入临时文件 → `os.replace()`（Windows兼容）

  **Must NOT do**: 不用os.rename()（Windows上目标存在时失败）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/position_manager/position_journal.py:57-68` — _append_entry
  - `src/plugins/position_manager/position_journal.py:198-223` — compact

  **Acceptance Criteria**:
  - [ ] _append_entry后数据立即持久化
  - [ ] compact使用临时文件+os.replace原子替换
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 19,21,22)

- [x] 21. **[H8] 恢复持仓后验证市场价**

  **What to do**:
  - 修改 `src/plugins/position_manager/plugin.py` 的 `_recover_positions()`
  - 恢复后：获取当前市场价格
  - 检查每个恢复的持仓：止损是否已被击穿
  - 如已击穿：立即标记为需要平仓
  - 更新unrealized_pnl

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: Task 7

  **References**:
  - `src/plugins/position_manager/plugin.py:110-129` — _recover_positions

  **Acceptance Criteria**:
  - [ ] 恢复后如果价格已穿止损，立即触发平仓
  - [ ] 恢复后unrealized_pnl反映当前市价
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 19,20,22)

- [x] 22. **启动对账 + 审计日志**

  **What to do**:
  - 在position_manager/plugin.py添加`_reconcile_with_exchange()`
  - 启动时对比journal持仓 vs exchange持仓，报告差异
  - 新建 `src/plugins/audit_logger/` 插件
  - 订阅trading.signal + position.opened + position.closed事件
  - 写入 `logs/audit.jsonl`，每条包含timestamp+event+完整context+config_hash

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: None

  **References**:
  - v3架构文档 十六.2 — reconcile_on_startup设计
  - v3架构文档 十六.8 — 审计日志格式

  **Acceptance Criteria**:
  - [ ] 启动时输出对账结果日志
  - [ ] audit.jsonl记录每笔交易决策完整上下文
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 19,20,21)

- [x] 23. **[L3,L4,L8,L9,M10] 版本统一 + API认证 + 杂项**

  **What to do**:
  - L3: pyproject.toml version改为"3.0.0"
  - L4: run.py版本标识改为v3.0
  - L8: api/app.py添加简单Bearer Token认证（环境变量WYCKOFF_API_TOKEN）
  - L9: 添加funding rate监控提示（config中标记为TODO，不实现完整功能）
  - M10: position_manager添加相关性检查注释/TODO标记

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 3 | Blocks: None | Blocked By: None

  **Acceptance Criteria**:
  - [ ] 所有文件版本号统一为3.0
  - [ ] 无API_TOKEN时POST请求返回401
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES
  - Message: `chore(infra): unify versions, add API auth [L3,L4,L8,L9,M10]`

- [x] 24. **Kelly仓位 + 反马丁格尔实现**

  **What to do**:
  - 在 `position_manager/position_manager.py` 添加 `fractional_kelly()` 方法
  - 参数：win_rate, avg_win, avg_loss, kelly_fraction=0.25, max_position_pct=0.20
  - 公式：full_kelly = (win_rate * b - q) / b; result = full_kelly * fraction / leverage
  - 添加 `anti_martingale_adjustment()`: 连赢加仓(×1.2/次,上限3x)，回撤>10%仓位减半

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 4 | Blocks: None | Blocked By: Task 7-9

  **References**:
  - v3架构文档 十二.2-十二.4 — Kelly公式和反马丁设计
  - `src/plugins/position_manager/position_manager.py:55-90` — 现有calculate_position_size

  **Acceptance Criteria**:
  - [ ] 55%胜率, 2:1盈亏比, 5x杠杆 → 仓位≈1%资本
  - [ ] 回撤>10%时仓位自动减半
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 25,26)
  - Message: `feat(plugins): add Kelly sizing, Telegram alerts, audit logger`

- [x] 25. **Telegram告警插件**

  **What to do**:
  - 新建 `src/plugins/telegram_notifier/` 插件目录
  - plugin-manifest.yaml + plugin.py
  - 订阅事件：position.opened, position.closed, risk_management.circuit_breaker_tripped, system.shutdown
  - 使用aiohttp或urllib发送Telegram Bot API消息
  - 配置：bot_token和chat_id通过环境变量 WYCKOFF_TELEGRAM_BOT_TOKEN / WYCKOFF_TELEGRAM_CHAT_ID

  **Must NOT do**: 不引入python-telegram-bot等新依赖

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 4 | Blocks: None | Blocked By: None

  **References**:
  - v3架构文档 十六.6 — AlertChannel/TelegramAlert设计
  - `src/plugins/evolution_advisor/plugin.py` — 参考插件结构

  **Acceptance Criteria**:
  - [ ] 插件加载成功（无token时graceful降级）
  - [ ] 交易开仓/平仓事件触发通知方法调用
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 24,26)

- [x] 26. **引擎优雅降级分阶段**

  **What to do**:
  - 修改 `src/plugins/wyckoff_engine/engine.py`
  - 四个阶段(_run_perception, _run_fusion, _run_state_machine, _generate_decision)各自独立try/except
  - 感知层失败 → 返回默认PerceptionResult(regime=UNKNOWN)，继续fusion
  - 融合层失败 → 返回默认FusionResult(bias=NEUTRAL)，继续状态机
  - 状态机失败 → 返回默认WyckoffStateResult(state=IDLE)，继续决策
  - 决策层失败 → 返回NEUTRAL信号

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 4 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/wyckoff_engine/engine.py:1219-1237` — 当前最外层degradation

  **Acceptance Criteria**:
  - [ ] 感知层抛异常时仍返回有效TradingDecision
  - [ ] 状态机抛异常时仍返回NEUTRAL决策
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES (groups with Task 24,25)

- [x] 27. **[M1] 引擎耦合标记 + validate_ohlcv**

  **What to do**:
  - M1: 在engine.py的12个插件import上方添加 `# TODO: 解耦 — 通过EventBus或接口注入替代直接import`
  - M2/M3: 标记为长期重构TODO（不在本轮改动）
  - 新建 `src/plugins/data_pipeline/ohlcv_validator.py`
  - 实现 validate_ohlcv(): high≥max(open,close), low≤min(open,close), volume≥0, 时间连续性, NaN检查
  - 在DataPipelinePlugin获取数据后调用

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 4 | Blocks: None | Blocked By: None

  **References**:
  - `src/plugins/wyckoff_engine/engine.py:46-71` — 12个直接import
  - v3架构文档 十六.5 — validate_ohlcv设计

  **Acceptance Criteria**:
  - [ ] 每个import有TODO注释
  - [ ] validate_ohlcv检测到high<open时返回错误
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES
  - Message: `feat(data): add OHLCV validation, mark coupling TODOs [M1,M2,M3]`

- [x] 28. **自定义RateLimiter**

  **What to do**:
  - 在 `src/plugins/exchange_connector/` 新建 `rate_limiter.py`
  - 实现滑动窗口限频器：max_requests=1100/60s（留100余量）
  - 在ExchangeExecutor每个API调用前await acquire()
  - 超限时自动等待并记录日志

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 4 | Blocks: None | Blocked By: None

  **References**:
  - v3架构文档 十六.4 — RateLimiter设计

  **Acceptance Criteria**:
  - [ ] 1100请求/分钟后自动等待
  - [ ] 等待后成功执行请求
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES
  - Message: `feat(exchange): add custom rate limiter`

- [x] 29. **Docker部署方案**

  **What to do**:
  - 新建 `Dockerfile`（python:3.11-slim基础镜像）
  - 新建 `docker-compose.yml`（restart:always, volume挂载data/logs/config, healthcheck）
  - 新建 `.dockerignore`
  - healthcheck使用 `python health_check.py`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 5 | Blocks: None | Blocked By: None

  **References**:
  - v3架构文档 十六.7 — Docker部署方案设计

  **Acceptance Criteria**:
  - [ ] `docker build -t wyckoff .` 成功
  - [ ] `docker run --rm wyckoff python -c "from src.app import WyckoffApp; print('OK')"` 输出OK
  - [ ] `pytest tests/ -v` ≥ 859 passed

  **Commit**: YES
  - Message: `chore(infra): add Docker deployment [Dockerfile, docker-compose]`

- [x] 30. **全量集成测试**

  **What to do**:
  - 新建 `tests/integration/test_production_readiness.py`
  - 测试杠杆PnL全链路：开仓(leverage=5) → 价格变动1% → 验证PnL=5%
  - 测试风控链路：累计亏损>daily_limit → 验证开仓被拒
  - 测试止损链路：价格触发止损 → 验证exchange有STOP_MARKET订单执行
  - 测试关闭链路：shutdown → 验证用市价平仓
  - 测试恢复链路：journal恢复 → 验证止损检查

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 5 | Blocks: None | Blocked By: ALL previous tasks

  **Acceptance Criteria**:
  - [ ] 5个集成测试全部通过
  - [ ] `pytest tests/ -v` ≥ 900 passed（含新增测试）

  **Commit**: YES
  - Message: `test(integration): add production readiness verification tests`

- [x] 31. **README + AGENTS.md 最终更新**

  **What to do**:
  - README.md: 更新版本号v3.0、测试数量、模块状态、路线图
  - AGENTS.md: 更新测试命令、版本信息
  - 删除对agent_teams的所有引用
  - 添加Docker启动说明

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**: Wave 5 | Blocks: None | Blocked By: Task 30

  **Acceptance Criteria**:
  - [ ] 版本号一致为v3.0
  - [ ] 无过时引用
  - [ ] Docker启动说明存在

  **Commit**: YES
  - Message: `docs: update README and AGENTS.md for v3.0 production release`

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  读取本计划。对每个"Must Have"验证实现存在。对每个"Must NOT Have"搜索违规。检查evidence文件。
  Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  运行 `pytest tests/ -v`。检查所有修改文件：无`as any`/空catch/console.log/注释代码。
  Output: `Tests [N pass] | Files [N clean] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  从clean state执行每个Unit的QA场景。测试跨Unit集成。
  Output: `Scenarios [N/N pass] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  对每个task检查实际diff vs spec。检测scope creep和遗漏。
  Output: `Tasks [N/N compliant] | VERDICT`

---

## Commit Strategy

- Unit 1: `fix(signal-path): repair event schema, breakout validation, async emit [H5,M4,H6]`
- Unit 2: `fix(leverage): add leverage field, correct all PnL calculations [C1,C2]`
- Unit 3: `fix(risk): implement capital loss limits, liquidation guard [C3,C4,C7,M8]`
- Unit 4: `fix(engine): correct short-sell condition, fix plugin shell [H4,M6]`
- Unit 5: `fix(exchange): add exchange SL/TP, order retry, slippage model [H2,H3,C6,M9]`
- Unit 6: `fix(persistence): atomic writes, shutdown event, journal fsync [C5,H7,H8,NEW-1]`
- Unit 7: `feat(plugins): add Kelly sizing, Telegram alerts, audit logger`
- Unit 8: `chore(infra): Docker, docs cleanup, version strings [L1-L10,M5,M7]`

## Success Criteria

```bash
pytest tests/ -v  # Expected: ≥ 900 passed, 0 failed
# 全部 C1-C7 修复验证
# 全部 H2-H8 修复验证
# Docker build 成功
```
