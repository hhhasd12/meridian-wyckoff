# Decisions — Full System Cleanup

## 2026-03-21 Task 13: Evolution Overfit 7根因审计

### 根因 1: GA评估与WFA验证用同一数据集(2000bars反复优化)
**判定**: ❌ 仍存在
**证据**: `run_evolution.py:261,273` — `ga.evaluate_population(evaluator, trimmed_data)` 和 `wfa.validate(best.config, trimmed_data)` 使用完全相同的 `trimmed_data`
**说明**: GA训练和WFA验证未做数据分离，无 70/30 分割

### 根因 2: WFA测试段包含训练段数据(状态泄漏)
**判定**: ⚠️ 部分修复
**证据**: `wfa_validator.py:200-204` — 测试段数据从 `train_start` 切起（而非 `test_start`），但注入了 `__test_start_ts__` 和 `__warmup_bars__` 元数据让评估器只统计测试段信号
**说明**: 引擎仍处理训练段数据（用于 warmup），但信号统计已限制在测试段。状态泄漏减轻但未完全消除。

### 根因 3: fitness函数对"不交易"给高分(0trades=0.575>best0.47)
**判定**: ❌ 仍存在
**证据**: `evaluator.py:157-163` — composite 计算无交易数量约束。0 trades 时 drawdown=0, stability=1.0, win_rate=0 → composite≈0.50+，高于实际交易策略
**说明**: 缺少 `if total_trades < 10: return 0.0` 硬约束

### 根因 4: Sharpe年化因子错误(sqrt(6) vs sqrt(252)不一致)
**判定**: ⚠️ 部分修复
**证据**: `bar_by_bar_backtester.py:509-531` — 使用 `annual_factor=6.0`，基于 per-trade returns 计算而非 per-bar equity returns。numba_accelerator.py 已删除(死代码清理)消除了双路径不一致
**说明**: 只剩一条代码路径(bar_by_bar)，一致性问题消失。但 annual_factor=6 的语义存疑（注释说"约6 trades/年"）

### 根因 5: mutation_rate=0.9太高+population=20太小
**判定**: ❌ 仍存在
**证据**: `genetic_algorithm.py:73,77,78,82` — `population_size=20`, `mutation_rate=0.9`, `mutation_strength=0.15`, `convergence_patience=5`。`run_evolution.py:237-246` 使用完全相同的默认值
**说明**: 未调整。0.9 mutation_rate 基本等于随机搜索

### 根因 6: WFA窗口75%重叠，独立性差
**判定**: ❌ 仍存在
**证据**: `wfa_validator.py:28-30` — `train_bars=600, test_bars=200, step_bars=150`。step_bars=150 < test_bars=200，窗口重叠率 = (200-150)/200 = 25%（原报告说75%重叠可能计算有误，实际约25%重叠）
**说明**: step_bars 应等于 test_bars 以消除重叠

### 根因 7: AntiOverfitGuard从未执行(backtest_result=None)
**判定**: ❌ 仍存在
**证据**: `run_evolution.py:277` — `if best.backtest_result is not None:` 条件守卫。GA 的 `evaluate_population()` 未将 BacktestResult 存入 individual。`genetic_algorithm.py` 中 Individual 有 `backtest_result` 字段但评估时从不赋值
**说明**: 条件永远为 False，五层防过拟合从不执行

### 审计汇总

| # | 根因 | 判定 |
|---|------|------|
| 1 | GA/WFA 同一数据集 | ❌ 仍存在 |
| 2 | WFA 测试段数据泄漏 | ⚠️ 部分修复 |
| 3 | 0-trade 高适应度 | ❌ 仍存在 |
| 4 | Sharpe 年化不一致 | ⚠️ 部分修复(单路径) |
| 5 | GA 超参数过激 | ❌ 仍存在 |
| 6 | WFA 窗口重叠 | ❌ 仍存在 |
| 7 | AntiOverfit 从不执行 | ❌ 仍存在 |

**结论**: 7 个根因中 5 个仍完整存在，2 个部分修复。进化系统过拟合问题尚未解决。
