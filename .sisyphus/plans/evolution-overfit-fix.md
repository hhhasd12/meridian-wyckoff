# 进化系统过拟合修复计划

> **目标**: 修复7大过拟合根因，让WFA通过率>0，OOS-DR从225%降到<40%
> **前提**: 953 tests passing，进化已跑14315 cycles但fitness~0.47、WFA全部失败
> **预估**: 7个Task，3个Wave

---

## 诊断摘要

| # | 根因 | 严重度 | 文件 | 行号 |
|---|------|--------|------|------|
| 1 | GA评估与WFA验证用同一数据集(2000bars反复优化) | 致命 | run_evolution.py | 216,261,273 |
| 2 | WFA测试段包含训练段数据(状态泄漏) | 致命 | wfa_validator.py | 200-201 |
| 3 | fitness函数对"不交易"给高分(0trades=0.575>best0.47) | 严重 | evaluator.py | 157-163 |
| 4 | Sharpe年化因子错误(sqrt(6) vs sqrt(252)不一致) | 严重 | bar_by_bar_backtester.py | 509-531 |
| 5 | mutation_rate=0.9太高+population=20太小 | 严重 | genetic_algorithm.py | 72-82 |
| 6 | WFA窗口75%重叠，独立性差 | 中等 | wfa_validator.py | 26-35 |
| 7 | AntiOverfitGuard从未执行(backtest_result=None) | 致命 | run_evolution.py | 277 |

---

## Wave 1: 致命修复（数据隔离+防过拟合激活）

### Task 1: 分离GA训练集与WFA验证集
**文件**: `run_evolution.py` L216, L261, L273
**修改**:
- L216后: 将trimmed_data按70/30分割为`ga_train_data`和`wfa_holdout_data`
- L261: `ga.evaluate_population(evaluator, ga_train_data)` — GA只在训练集评估
- L273: `wfa.validate(best.config, wfa_holdout_data)` — WFA只在holdout集验证
- holdout数据GA从未见过，OOS估计才有意义
**验收**: GA fitness在训练集计算，WFA在独立holdout集验证，两者无交集

### Task 2: 修复WFA测试段数据泄漏
**文件**: `wfa_validator.py` L200-201
**修改**:
- L200: `test_data = self._slice_data(data_dict, h4, window.test_start, window.test_end)`
  改为从test_start开始（不是train_start），给50-bar warmup而非整个训练段
- 或: 为测试段创建独立的WyckoffEngine实例，不继承训练段状态
**验收**: 测试段评估不包含训练段数据，引擎状态独立初始化

### Task 3: 激活AntiOverfitGuard
**文件**: `run_evolution.py` L277, `genetic_algorithm.py`
**修改**:
- 在GA的`evaluate_population()`中，评估后将BacktestResult存入`individual.backtest_result`
- 确保L277的`if best.backtest_result is not None`条件为True
- 五层防过拟合(MBL/OOS-DR/DSR/MonteCarlo/CPCV)开始真正执行
**验收**: 每个cycle的verdict_info非空，AntiOverfit检查输出可见

---

## Wave 2: 适应度函数+Sharpe修复

### Task 4: 重设计COMPOSITE_SCORE适应度函数
**文件**: `evaluator.py` L157-163
**修改**:
- 添加硬约束: `if total_trades < 10: return 0.0` — 不交易=零分
- 合并重复权重: stability(=1-drawdown)与(1-drawdown)合并，释放权重给trade_count
- Sharpe sigmoid: Sharpe≤0时得0分（不是0.5）
- 新增trade_count激励: `min(trades, expected) / expected * 0.10`
- 建议新权重: sharpe*0.30 + drawdown*0.20 + win_rate*0.15 + PF*0.15 + trade_count*0.10 + calmar*0.10
**验收**: 0 trades → fitness=0; 合理交易策略 > 不交易策略

### Task 5: 统一Sharpe年化因子
**文件**: `bar_by_bar_backtester.py` L509-531, `numba_accelerator.py` L1047
**修改**:
- 统一为per-bar equity returns计算Sharpe（不是per-trade）
- H4频率年化: `annual_factor = 6 * 365 = 2190`, `sqrt(2190) ≈ 46.8`
- bar_by_bar和numba两个路径使用完全相同的公式
- 修复L511 calmar定义: `calmar = annual_return / max_drawdown`（不是sharpe/drawdown）
**验收**: 两个代码路径对同一数据产生相同Sharpe值

---

## Wave 3: GA参数+WFA窗口优化

### Task 6: 优化GA超参数
**文件**: `run_evolution.py` L237-246, `genetic_algorithm.py` L72-82
**修改**:
- `mutation_rate`: 0.9 → 0.25（每参数25%概率变异）
- `population_size`: 20 → 50（增加搜索空间覆盖）
- `mutation_strength`: 0.15 → 0.10（精细搜索）
- `convergence_patience`: 5 → 15（给更多时间收敛）
- 实际使用`diversity_penalty`（当前定义了但未读取）
- 将ATR止损/止盈倍数(atr_sl_mult/atr_tp_mult)纳入进化参数空间
**验收**: 种群能稳定收敛，fitness曲线呈上升趋势而非随机跳动

### Task 7: 优化WFA窗口配置
**文件**: `wfa_validator.py` L26-35
**修改**:
- `train_bars`: 600 → 300（缩短训练以减少状态泄漏）
- `test_bars`: 200 → 300（增大测试集，更可靠的OOS估计）
- `step_bars`: 150 → 300（=test_bars，消除窗口重叠）
- `min_windows`: 2 → 3（增加统计可靠性）
- WFA ratio计算: 添加train_sharpe最小值过滤(>0.05)防止除零波动
**验收**: WFA窗口无重叠，min_windows≥3，OOS-DR估计可靠

---

## 验证标准

```bash
pytest tests/ -v  # ≥ 953 passed
python run_evolution.py  # 运行5个cycle后:
  # - fitness应>不交易基线(0.575→之前的，新函数下应=0)
  # - AntiOverfit verdict_info非空
  # - WFA至少有1个cycle通过（OOS-DR<0.4）
  # - 不同cycle间fitness有明显差异（非全部相同）
```

## 成功指标

| 指标 | 修复前 | 修复后目标 |
|------|--------|-----------|
| WFA通过率 | 0% | >20% |
| OOS-DR | 225% | <40% |
| 0-trade fitness | 0.575(高分) | 0.0(零分) |
| AntiOverfit执行 | 从未 | 每个cycle |
| Sharpe一致性 | 6.5倍差异 | 两路径一致 |
