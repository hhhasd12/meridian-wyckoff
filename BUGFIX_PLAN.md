# 威科夫系统 — 彻底排查计划

> 状态：进行中 | 开始时间：2026-03-02
> 目标：让系统真正端到端运行，每个 cycle 产生不同结果，进化链路可验证

---

## 一、当前已确认的现象

```
Cycle #1  | Score=0.8060 Sharpe=0.9798 WinRate=0.00% Drawdown=4.24%
Cycle #2  | Score=0.8060 ...（完全一样）
...
Cycle #23 | Score=0.8060 ...（完全一样）
每个 cycle 1秒内完成
```

**结论**：整个进化链路没有真正运行。系统在某处短路，返回缓存/静态值。

---

## 二、系统完整链路图

```
run_evolution.py
    │
    ├─ load_evolution_data()          [数据层]
    │       └─ pkl / csv → DataFrame
    │
    ├─ MistakeBook                    [错题本层]
    │       └─ seed → analyze → generate_weight_adjustments
    │
    ├─ WeightVariator                 [变异层]
    │       └─ generate_initial_population → _mutate_configuration
    │
    ├─ WFABacktester                  [WFA层]
    │       └─ initialize_with_baseline → validate_mutations
    │               └─ _run_walk_forward_analysis
    │                       └─ performance_evaluator(config, data)  ← 关键断点
    │                               └─ real_performance_evaluator()
    │                                       └─ BacktestEngine.run()
    │                                               └─ 信号匹配 → 交易
    │
    └─ SelfCorrectionWorkflow         [协调层]
            └─ run_correction_cycle()
                    └─ _extract_metrics() → 打印输出
```

---

## 三、已排查问题清单

### P0 — 已修复（但效果未验证）

| # | 文件 | 问题 | 修复状态 |
|---|------|------|----------|
| F1 | `src/backtest/engine.py` | pandas Timestamp(tz-aware) 与 naive datetime 比较 → TypeError → `error_handler(reraise=False)` 静默吞掉 → 返回空 BacktestResult，WinRate=0% | ✅ 已修复：`_to_naive()` 统一类型 |
| F2 | `run_evolution.py` | MA 窗口公式 `min(int(n*0.2), int(50*threshold))` 在 n=2000 时永远等于35，config变异不影响窗口 | ✅ 已修复：窗口由 config 三类参数共同决定 |
| F3 | `src/core/wfa_backtester.py` | `_simulate_performance` 只用参数数量（complexity）评分，不同config得同分 | ✅ 已修复：用参数值指纹评分 |

### P0 — 尚未排查（高度怀疑）

| # | 文件 | 怀疑问题 | 排查方法 |
|---|------|----------|----------|
| U1 | `run_evolution.py` `_extract_metrics()` | 从 cycle result 提取指标的路径可能永远走"兜底"分支（baseline），导致每轮打印相同的 baseline 值 | 加 print 追踪 `wfa_report` 实际内容 |
| U2 | `SelfCorrectionWorkflow._generate_mutations()` | `generate_initial_population` 每次从 index 1 取，但每次都重新生成种群，变异是真实不同的吗？ | 打印 pop[1] 的 config 值对比 pop[0] |
| U3 | `WFABacktester.validate_mutations()` | `_check_weight_changes()` 平均变化 <= 5% 才通过，变异幅度太小可能全部被拒 | 打印 avg_change 值 |
| U4 | `WFABacktester._analyze_wfa_result()` | `min_window_count=5` 但 `max_windows=5`，窗口数不足时返回 `NEEDS_MORE_DATA`，不是 ACCEPTED 也不是 REJECTED | 检查实际 num_windows |
| U5 | `engine.run()` | `error_handler(reraise=False, default_return=BacktestResult())` — 只要 run() 内部任何地方报错，就静默返回空结果，外部无感知 | 临时改为 `reraise=True` 暴露真实错误 |
| U6 | `_extract_metrics()` | `best_perf` 从 `detail.get("performance")` 取，但 WFA 里 `performance` 字段是平均指标字典，可能没有 `COMPOSITE_SCORE` key | 打印实际 detail 结构 |

---

## 四、排查执行计划（按优先级）

### 阶段 0：加探针，暴露真实数据流（1天）

**目标**：不改业务逻辑，只加临时 print，看清每一层的真实输出。

```
[ ] STEP-0.1  engine.run() — 改 reraise=True，让错误暴露
[ ] STEP-0.2  engine.run() — 在 _calculate_statistics 前 print trades 数量
[ ] STEP-0.3  real_performance_evaluator — print fast_window, slow_window, len(signals), len(trades)
[ ] STEP-0.4  WFABacktester._run_walk_forward_analysis — print num_windows
[ ] STEP-0.5  WFABacktester.validate_mutations — print 每个 config 的 avg_change, validation_decision
[ ] STEP-0.6  _extract_metrics — print wfa_report 的完整 keys 和 validation_details
[ ] STEP-0.7  _generate_mutations — print pop[0] vs pop[1] 的 confidence_threshold 值
```

**交付物**：一次完整 cycle 的全链路 print 日志，确认每层是否真实运行。

---

### 阶段 1：数据层验证（0.5天）

**目标**：确认进入 BacktestEngine 的数据是干净、有效的。

```
[ ] STEP-1.1  检查 H4 数据索引类型（tz-aware？naive？）
[ ] STEP-1.2  检查 close 列是否有 NaN，数量级是否合理（ETH价格应在100~5000）
[ ] STEP-1.3  检查 WFA 滑窗切片后的子DataFrame行数是否 >= slow_window
[ ] STEP-1.4  验证 pkl 加载后的 DataFrame 结构与 engine.run() 期望的一致性
```

---

### 阶段 2：BacktestEngine 单独验证（0.5天）

**目标**：确认 engine.run() 在真实数据上能正确执行 BUY/SELL。

```
[ ] STEP-2.1  写隔离测试：用真实 H4 数据 + 手动构造 BUY/SELL 信号 → 验证交易被执行
[ ] STEP-2.2  验证时间戳类型：H4数据的index类型 vs 信号的timestamp类型，print 对比
[ ] STEP-2.3  验证 trade.pnl 计算逻辑：SELL时 pnl = (sell_price - buy_price) * qty - commission
              注意：当前代码 trade.pnl 更新到 self.trades[-1]，若 BUY trade 之后有任何插入会错位
[ ] STEP-2.4  确认 winning_trades 统计：pnl > 0 才算赢，检查边界（pnl=0 算输）
```

---

### 阶段 3：performance_evaluator 链路验证（0.5天）

**目标**：确认 real_performance_evaluator 真正依赖 config，不同 config 产生不同结果。

```
[ ] STEP-3.1  用两个明显不同的 config（threshold=0.5 vs threshold=0.9）手动调用，print MA窗口值
[ ] STEP-3.2  验证 fast_window != slow_window，且有足够信号数量（至少10个）
[ ] STEP-3.3  print result.total_trades，确认 > 0
[ ] STEP-3.4  print COMPOSITE_SCORE，确认两个config得分不同
```

---

### 阶段 4：变异层验证（0.5天）

**目标**：确认 WeightVariator 生成的变异体与原始 config 真实不同。

```
[ ] STEP-4.1  print base_config vs pop[1].config 的所有叶子数值，确认有差异
[ ] STEP-4.2  检查 mutation_rate=0.3 下实际触发概率，是否需要提高到 0.8
[ ] STEP-4.3  检查 _random_mutate 是否正确找到参数路径（_find_parameter_path）
[ ] STEP-4.4  检查 max_mutation_percent=5% 是否太小，导致整数化后MA窗口不变
              例：threshold=0.70 vs 0.735（5%变异）→ fast_window 是否真的不同？
```

---

### 阶段 5：WFA 验证层（1天）

**目标**：确认 WFABacktester 真正运行了多个滑窗回测，且能区分好坏 config。

```
[ ] STEP-5.1  确认 num_windows 实际值（配置 train=300, test=100, step=200, 数据2000根
              → 最多 (2000-300-100)/200 + 1 ≈ 9 个窗口，但 max_windows=5，实际=5）
[ ] STEP-5.2  确认 min_window_count=2（已在config设置），_analyze_wfa_result 不会因窗口不足拒绝
[ ] STEP-5.3  确认 improvement_vs_baseline 计算：baseline_composite 是否正确初始化
[ ] STEP-5.4  确认 stability_threshold（默认0.7）是否太高，导致变异全被拒
[ ] STEP-5.5  确认 require_statistical_significance=True 且窗口只有5个时，
              is_statistically_significant 逻辑是否合理
[ ] STEP-5.6  确认 max_weight_change=5% 是否兼容变异幅度（两个矛盾的限制是否同时触发）
```

---

### 阶段 6：SelfCorrectionWorkflow 协调层（0.5天）

**目标**：确认 run_correction_cycle 各阶段真正运行并传递正确数据。

```
[ ] STEP-6.1  确认 _run_error_analysis 返回 success=True
              （min_errors_for_correction=5，seed了15个，应通过）
[ ] STEP-6.2  确认 _generate_mutations 返回的 mutation_details 中 _config_full 非 None
[ ] STEP-6.3  确认 _validate_mutations 从 mutation_details 正确提取 mutated_configs
[ ] STEP-6.4  确认 _extract_metrics 里 wfa_report["validation_details"] 非空
              且 detail["performance"] 包含 COMPOSITE_SCORE
[ ] STEP-6.5  确认 _update_configuration 在有改进时真正更新了 self.current_config
```

---

### 阶段 7：核心逻辑完整性（2天）

**目标**：确认系统实现了设计文档中描述的核心机制，而不是空壳。

```
[ ] STEP-7.1  WyckoffStateMachine：是否真正被调用？engine.run的 state_machine 参数传 None
              → 状态机根本没参与回测，周期权重无法影响状态判断
[ ] STEP-7.2  PeriodWeightFilter：period_weight_filter.weights 是否真正被任何计算使用？
              目前只作为 MA 窗口的间接输入，威科夫多周期融合逻辑是否实现？
[ ] STEP-7.3  ConflictResolver：多周期冲突解决是否工作？
[ ] STEP-7.4  MarketRegime：市场体制识别是否接入 config 的 regime_weights？
[ ] STEP-7.5  MistakeBook → WeightVariator 的反馈路径：
              错误模式分析结果是否真正指导了变异方向？还是随机变异？
[ ] STEP-7.6  进化结果持久化：被接受的最佳 config 是否真正写入 self.current_config？
              下一轮是否基于更新后的 config 生成变异？
```

---

## 五、已知的结构性缺陷

### 5.1 error_handler 是全局异常黑洞

```python
# engine.py - 这是最危险的模式
@error_handler(logger=logger, reraise=False, default_return=BacktestResult())
def run(self, data, state_machine, signals):
    ...
```

任何内部错误（TypeError、KeyError、除零等）都被静默吞掉，返回空的 BacktestResult。
**修复方向**：排查期间全部改为 `reraise=True`，或至少加 `print("ERROR in run:", e)` 在 except 块。

### 5.2 日志级别掩盖了所有内部错误

```python
# run_evolution.py
logging.basicConfig(level=logging.WARNING, ...)  # 所有 INFO/DEBUG/ERROR 全被过滤
```

内部模块的 `logger.error(...)` 被 WARNING 级别过滤掉。
**修复方向**：排查期间改为 `level=logging.DEBUG`。

### 5.3 WFA 窗口数 vs 最小窗口数的矛盾

```python
"min_window_count": 2,   # config里设置
"max_windows": 5,        # config里设置
# 但 WFABacktester.__init__ 里：
self.min_window_count = self.config.get("min_window_count", 5)  # 默认5！
```

config 传入 `min_window_count=2`，但 key 名必须精确匹配，需验证是否正确传入。

### 5.4 _extract_metrics 的兜底路径永远被触发

```python
def _extract_metrics(result):
    # 优先：WFA各变异的测试性能
    for detail in wfa_report.get("validation_details", []):
        perf = _pick(detail.get("performance") or {})
        # 但 "performance" key 在 validation_detail 里实际叫什么？
        # wfa_backtester.py line 313: {"performance": wfa_result.get("test_performance", {})}
        # test_performance 是平均值字典，没有 COMPOSITE_SCORE key！
        # → best_perf 永远为空 → 走兜底路径 → 打印 baseline 的固定值
```

**这很可能是每轮数字完全一样的直接原因。**

### 5.5 trade.pnl 只更新最后一笔 BUY，存在覆盖风险

```python
elif direction == "SELL" and self.position > 0:
    trade = self.trades[-1]   # 假设最后一笔是匹配的 BUY
    trade.pnl = pnl           # 覆盖 pnl
```

如果连续两个 BUY 信号，`self.trades[-1]` 就不是当前持仓对应的 BUY 了。
应该记录买入时的 index，SELL 时精确匹配。

### 5.6 种群进化未持久化

```python
# SelfCorrectionWorkflow._generate_mutations()
self.weight_variator.generate_initial_population(self.current_config)
# 每次调用都重新生成种群！
# 等于每轮都从 baseline 重新开始，没有跨代积累
```

**修复方向**：首次调用后保存种群，后续调用 `evolve_population()` 而非重新初始化。

---

## 六、排查优先顺序

```
Priority 1 (今天)：
  → STEP-0 系列：加探针，看清每层真实输出
  → 重点：打印 detail["performance"] 的实际结构（5.4 的问题）

Priority 2 (明天)：
  → STEP-2：BacktestEngine 隔离测试
  → STEP-3：performance_evaluator 差异性验证
  → 修复 5.1（reraise）和 5.2（日志级别）

Priority 3 (后天)：
  → STEP-4/5/6：变异层 + WFA层 + 协调层逐一验证
  → 修复 5.3（min_window_count key）和 5.4（_extract_metrics 路径）
  → 修复 5.6（种群不持久化）

Priority 4 (本周内)：
  → STEP-7：核心逻辑完整性
  → 威科夫状态机真正接入回测
  → 多周期权重真正影响信号生成
```

---

## 七、验证标准（Done 的定义）

系统真正打通的标准：

```
✓ 相邻两个 cycle 的数字不同（Score、Sharpe、WinRate、Drawdown 至少有一个变化）
✓ WinRate > 0%（有真实 BUY/SELL 交易执行）
✓ 每个 cycle 耗时 > 1秒（真实回测在跑，不是缓存）
✓ 能打印：本轮MA窗口 fast=X slow=Y，交易次数=N
✓ 连续10轮中至少有1轮 Score > baseline（进化有正向效果）
✓ config 中 confidence_threshold 变化 ±0.1 → Score 明显不同（敏感性验证）
```

---

## 八、文件修改记录

| 日期 | 文件 | 修改内容 | 验证状态 |
|------|------|----------|----------|
| 2026-03-02 | `src/backtest/engine.py` | 修复时间戳 tz 比较问题，_to_naive() | 未验证 |
| 2026-03-02 | `run_evolution.py` | 修复 MA 窗口计算，引入 config 三参数驱动 | 未验证 |
| 2026-03-02 | `src/core/wfa_backtester.py` | 修复 _simulate_performance，改为参数值指纹评分 | 未验证 |

---

## 九、下一步行动

**立即执行**：写一个 `debug_probe.py`，在不改业务逻辑的前提下，端到端打印完整数据流，确认哪一层真正在运行，哪一层在返回缓存值。

```bash
python debug_probe.py  # 目标：在 30 行输出中看清每层的真实状态
```
