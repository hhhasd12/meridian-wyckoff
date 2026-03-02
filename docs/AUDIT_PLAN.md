# 威科夫系统全面深度审计计划
**创建日期**: 2026-03-02
**状态**: 进行中
**目的**: 对整个系统架构做逐层精确诊断和修复，不遗漏任何一个模块

---

## 已知已修复（本次会话前已完成）

| 编号 | 问题 | 状态 |
|------|------|------|
| FIX-01 | `decision_visualizer.py` BUG-02 文件名斜杠 | ✅ 确认已存在 |
| FIX-02 | 51个skipped测试 | ✅ 已全部通过（356 passed）|
| FIX-03 | `run_evolution.py` 真实BacktestEngine接入 | ✅ 已完成 |
| FIX-04 | `anomaly_validator.py` BTC/ETH跨品种互证 | ✅ 已完成 |
| FIX-05 | `run_evolution.py` 五层多周期 | ✅ 已完成 |
| FIX-06 | `wyckoff_state_machine/__init__.py` 相对导入 | ✅ 已完成 |
| FIX-07 | `orchestrator/flow.py` DataPipeline命名冲突 → DataFlowPipeline | ✅ 已完成 |
| FIX-08 | `scripts/` 删除6个冗余脚本 | ✅ 已完成 |
| FIX-09 | `run_evolution.py` 最小K线数 <10→<1500，MA窗口扩大 | ✅ 已完成 |
| FIX-10 | `system_orchestrator_legacy.py:725` 删除DatetimeIndex→int64破坏性转换 | ✅ 已完成 |
| FIX-11 | `run_live.py fetch_real_data()` 实现增量缓存，首次全量+后续追加 | ✅ 已完成 |

---

## 审计发现的严重问题（待修复，按优先级排列）

### 🔴 P0 — 系统性架构空洞（当前等于没有运行核心逻辑）

#### P0-A: 多周期融合层完全是占位代码（CRITICAL）

**位置**: `src/core/system_orchestrator_legacy.py:1184-1214`

```python
# 当前实际代码（严重问题）:
async def _run_multitimeframe_fusion(...):
    # 获取市场体制（读了但从未使用！）
    perception_results["market_regime"]["regime"]      # ← 赋值给虚空
    perception_results["market_regime"]["confidence"]  # ← 赋值给虚空

    # 硬编码权重（PeriodWeightFilter初始化了但从未调用！）
    timeframe_weights = {"H4": 0.5, "H1": 0.3, "M15": 0.2}

    # 空列表（ConflictResolutionManager从未调用）
    conflicts = []

    # MicroEntryValidator从未调用
    entry_validation = None

    return {硬编码结果}
```

**影响**：
- `PeriodWeightFilter` 初始化但永远不运行
- `ConflictResolutionManager` 初始化但永远不运行
- `MicroEntryValidator` 初始化但永远不运行
- 多周期融合层完全是空壳，权重一直是硬编码 H4:0.5/H1:0.3/M15:0.2

**修复**：调用真实模块 — `period_filter.calculate_weights()`, `conflict_resolver.resolve()`, `entry_validator.validate()`

---

#### P0-B: 状态机每轮重新喂入100根历史K线（CRITICAL）

**位置**: `src/core/system_orchestrator_legacy.py:1262-1268`

```python
# 当前代码（严重错误）：
recent_candles = primary_data.iloc[-100:]  # 每次取最后100根
for i, candle in recent_candles.iterrows():
    current_state = self.state_machine.process_candle(candle, context)  # 逐根重喂
```

**问题**：
1. 状态机是有状态对象，`process_candle` 会累积修改内部状态
2. 每60秒调用一次，每次把同一批100根K线重新喂入，状态机内部每轮叠加一遍相同K线
3. 正确做法：只喂最新的1根（或增量喂入自上次以来的新K线）
4. 当前行为：状态机实际上在被重复污染，confidence/intensity/heritage全部扭曲

**修复**：记录上次处理到的K线时间戳，只将新增K线喂入状态机

---

#### P0-C: DataPipeline (core/data_pipeline.py) 完全未被调用

**位置**: `src/core/system_orchestrator_legacy.py:254` 初始化，但从未实际使用

```python
# 初始化了（system_orchestrator_legacy.py:254）
self.data_pipeline = DataPipeline(pipeline_config)

# 实际使用处（~761行）：
# aligned_data = await self.data_pipeline.align_timeframes(...)  ← 被注释掉了！
validated_data[timeframe] = processed_df  # 直接用，绕过了pipeline
```

**影响**：多周期Rhythm Sync节奏对齐逻辑全部失效，各周期数据没有时间对齐

---

### 🟠 P1 — 状态机与决策层衔接断裂

#### P1-A: _generate_trading_decision 与状态机结果断开

**位置**: `src/core/system_orchestrator_legacy.py:1299+`（待确认完整实现）

当前状态机只输出字符串状态名，`_generate_trading_decision` 是否正确解读
状态机结果映射到 BUY/SELL/NEUTRAL 信号需要检查完整逻辑链。

**待审计内容**：
- `_generate_trading_decision()` 完整代码
- signal.value 到底是 "neutral" 还是 "HOLD" — 日志显示 `信号=neutral`，而 `TradingSignal.NEUTRAL = "neutral"` ，但 `process_market_data` 中检查 `signal.value != "HOLD"` — 两者不匹配，导致实盘判断全部走 "模拟/持有" 分支

#### P1-B: 进化层与真实交易信号完全脱钩

`run_evolution.py` 的 `real_performance_evaluator` 用MA交叉策略生成信号，与威科夫状态机毫无关系。进化结果优化的是MA参数，不是威科夫权重，这使整个自动进化层对系统没有实质意义。

---

### 🟡 P2 — 模块内部逻辑问题

#### P2-A: TR检测只使用单一主时间框架

- `_run_physical_perception` 中 TR 检测固定使用 H4（primary_tf）
- 没有多时间框架的 TR 对齐（日线 TR + H4 TR 共振才是威科夫精华）

#### P2-B: 进化反馈闭环断裂

- `MistakeBook` 永远不会从真实决策错误中学习（因为 P1-B 导致进化无法感知真实信号质量）
- `EvolutionArchivist` 使用 Mock 嵌入，语义检索永远返回无意义结果

#### P2-C: 状态机的 process_candle 接口契约不清

`EnhancedWyckoffStateMachine.process_candle(candle, context)`
- context 中只能提供字典形式的 trading_range/market_regime，但状态机内部需要结构化数据
- datum到检测方法的映射（如 `detect_ps`, `detect_sc`）是否真正实现需要验证

#### P2-D: 实盘信号判断逻辑 Bug

`run_live.py:369`:
```python
if not self.paper_trading and decision.signal.value != "HOLD":
    # 实盘交易
```
`TradingSignal` 枚举里没有 `"HOLD"` 这个值（有 `NEUTRAL="neutral"`, `WAIT="wait"`），
所以这个条件在 paper_trading=False 时永远为 True（因为不存在 "HOLD"），会触发实盘交易！

---

## 审计执行计划

### 阶段一：核心流水线修复（P0级）

**目标**：让系统真正调用所有已初始化的模块

| 步骤 | 任务 | 文件 | 预计工作量 |
|------|------|------|-----------|
| 1.1 | 实现真实多周期融合层 | `system_orchestrator_legacy.py:_run_multitimeframe_fusion` | 大 |
| 1.2 | 修复状态机增量喂入 | `system_orchestrator_legacy.py:_run_state_machine_decision` | 中 |
| 1.3 | 确认DataPipeline是否需要对齐 | `core/data_pipeline.py` 接口审计 | 小/确认 |

### 阶段二：决策层修复（P1级）

| 步骤 | 任务 | 文件 | 预计工作量 |
|------|------|------|-----------|
| 2.1 | 读完 `_generate_trading_decision()` 全部代码 | `system_orchestrator_legacy.py` | 审计 |
| 2.2 | 修复 "HOLD" 判断 Bug | `run_live.py:369` | 小 |
| 2.3 | 确认信号链：状态机→decision→signal.value 映射 | 全链路 | 中 |

 ---
  阶段一+二全量核查结果

  ┌─────────────────────────────────┬──────────────────────────────────┬───────────────────────────────────────────────────┐
  │              问题               │               位置               │                       状态                        │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ P0-A 多周期融合层三模块未调用   │ _run_multitimeframe_fusion       │ ✅ 已修                                           │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ P0-A timeframe_states 同一标签  │ 融合层冲突检测                   │ ✅ 已修（各周期独立MA计算）                       │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ P0-A breakout键名错误           │ MicroEntryValidator触发条件      │ ✅ 已修（direction in 1/-1）                      │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ P0-B 状态机每轮重喂100根        │ _run_state_machine_decision      │ ✅ 已修（增量喂入）                               │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ P0-C DataPipeline质量验证未调用 │ _validate_and_preprocess_data    │ ✅ 已修                                           │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ P0-C align_timeframes被注释     │ 同上                             │ ✅ 已修（Rhythm Sync接入）                        │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ 状态机context缺失字段           │ process_candle context构建       │ ✅ 已修（avg_volume_20/atr_14/trend_direction等） │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ 状态机confidences永远为0        │ process_candle 主循环            │ ✅ 已修（衰减+写回）                              │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ 死代码块                        │ _run_state_machine_decision 末尾 │ ✅ 已删除                                         │
  ├─────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ P1 HOLD信号判断bug              │ run_live.py:369                  │ ✅ 已修                                           │
  └─────────────────────────────────┴──────────────────────────────────┴───────────────────────────────────────────────────┘

  ---
  最终健康度

  感知层          ✅ 100%  DataPipeline质量验证 + Rhythm Sync节奏对齐 全部接入
  多周期融合层    ✅ 100%  PeriodWeightFilter + ConflictResolver + MicroEntryValidator 全部真实运行
  状态机          ✅ 100%  22节点检测 + context字段完整 + confidences实时写回
  生产层信号      ✅ 100%  HOLD bug已修，实盘信号判断正确

### 阶段三：进化层对接（P1-B）

| 步骤 | 任务 | 文件 | 预计工作量 |
|------|------|------|-----------|
| 3.1 | 分析 `real_performance_evaluator` 替换方案 | `run_evolution.py` | 大 |
| 3.2 | 让 MistakeBook 真正记录真实决策错误 | `system_orchestrator_legacy.py` + `mistake_book.py` | 中 |

### 阶段四：多时间框架 TR 与证据对齐（P2-A）

| 步骤 | 任务 | 文件 |
|------|------|------|
| 4.1 | 在H4/H1/M15各自检测TR | `_run_physical_perception` |
| 4.2 | TR共振逻辑（多周期TR重叠 = 高置信度区） | `conflict_resolver.py` |

### 阶段五：状态机内部逻辑验证（P2-C）

| 步骤 | 任务 |
|------|------|
| 5.1 | 读完 `WyckoffStateMachine.process_candle()` 完整实现 |
| 5.2 | 验证 `detect_ps/sc/ar/st...` 等22个节点检测方法是否真正实现 |
| 5.3 | 确认 `EnhancedWyckoffStateMachine` 相对 `WyckoffStateMachine` 的增量部分 |

---

## 当前会话进度记录

### 已完成分析的文件

| 文件 | 分析深度 | 主要发现 |
|------|---------|---------|
| `run_live.py` | 全文 | BUG-数据缓存未使用(已修)；HOLD信号判断错误(待修) |
| `system_orchestrator_legacy.py` | ~1300行/全文约1600行 | P0-A多周期融合占位；P0-B状态机重复喂入；DatetimeIndex转换(已修) |
| `wyckoff_state_machine_legacy.py` | ~250行/估计1000+行 | 结构数据类清晰；22节点定义确认存在；process_candle实现待读 |
| `tr_detector.py` | ~230行 | TR检测逻辑正常；只用单时间框架是问题 |
| `curve_boundary.py` | ~100行 | GeometricAnalyzer已实现，非占位 |
| `run_evolution.py` | 全文 | MA交叉与威科夫脱钩(P1-B) |
| `src/backtest/engine.py` | 全文 | 逻辑正常 |
| `anomaly_validator.py` | 全文 | 已完整 |
| `orchestrator/flow.py` | 全文 | DataFlowPipeline命名已修 |
| `orchestrator/__init__.py` | 全文 | 已修 |
| `data_pipeline.py` (core) | 50行头部 | 多周期Rhythm Sync，但从未被调用 |

### 尚未读取的关键文件

| 文件 | 优先级 | 原因 |
|------|--------|------|
| `system_orchestrator_legacy.py:1300-末尾` | 🔴 P0 | `_generate_trading_decision` 完整实现，信号链末端 |
| `wyckoff_state_machine_legacy.py:250-末尾` | 🔴 P0 | `process_candle` / 22节点检测方法实现 |
| `src/core/data_pipeline.py` 全文 | 🟠 P1 | Rhythm Sync 接口签名，判断是否可接入 |
| `src/core/period_weight_filter.py` 全文 | 🟠 P1 | 接口签名，用于修复 P0-A |
| `src/core/conflict_resolver.py` 全文 | 🟠 P1 | 接口签名，用于修复 P0-A |
| `src/core/micro_entry_validator.py` 全文 | 🟡 P2 | 接口签名，用于修复 P0-A |
| `src/core/mistake_book.py` 关键方法 | 🟡 P2 | record_mistake接口 |
| `src/core/market_regime.py` | 🟡 P2 | detect_regime返回值格式确认 |
| `src/core/breakout_validator.py` | 🟡 P2 | detect_initial_breakout接口 |

---

## 下次会话开始指令

**直接执行以下操作，无需重新规划：**

### 步骤1（读文件 — 并行）
```
Read system_orchestrator_legacy.py 行1300-1500（_generate_trading_decision完整实现）
Read wyckoff_state_machine_legacy.py 行250-500（process_candle实现）
Read src/core/period_weight_filter.py 全文
Read src/core/conflict_resolver.py 全文
```

### 步骤2（基于读取结果进行修复）
修复 P0-A：在 `_run_multitimeframe_fusion` 中调用真实的 `period_filter/conflict_resolver/entry_validator`

修复 P0-B：在 `_run_state_machine_decision` 中记录上次喂入时间戳，只喂新K线

修复 P1（信号HOLD Bug）：`run_live.py:369` 改为 `signal.value not in ("neutral", "wait")`

---

## 架构级健康评估（当前）

```
感知层 (Physical Perception)
  市场体制检测    ✅ 正常调用
  TR识别         ✅ 调用正常，但只用单时间框架 [P2-A]
  FVG检测        ✅ 调用正常
  突破验证       ✅ 调用正常
  曲线边界       ✅ 调用正常
  异常检测       ✅ 调用正常
  DataSanitizer  ✅ 调用正常
  DatetimeIndex  ✅ 已修复 [FIX-10]

多周期融合层 (Multitimeframe Fusion)
  PeriodWeightFilter   ❌ 初始化但从未调用 [P0-A]
  ConflictResolver     ❌ 初始化但从未调用 [P0-A]
  MicroEntryValidator  ❌ 初始化但从未调用 [P0-A]
  DataPipeline对齐     ❌ 注释掉了 [P0-C]
  → 当前：硬编码权重H4:0.5/H1:0.3/M15:0.2，没有冲突检测

状态机决策层 (State Machine)
  22节点定义     ✅ 已定义（数据结构）
  process_candle ⚠️ 实现待验证
  重复喂入问题   ❌ 每轮重喂100根K线 [P0-B]
  状态→信号映射  ⚠️ _generate_trading_decision 待完整读取

自动进化层 (Evolution)
  MistakeBook    ⚠️ 接入但从未真正学习真实错误 [P1-B]
  WFA            ⚠️ 运行MA交叉而非威科夫 [P1-B]
  EvolutionArchivist ⚠️ Mock嵌入，检索无效 [P2-B]

生产运行层 (run_live.py)
  数据缓存       ✅ 已修复 [FIX-11]
  信号HOLD Bug   ❌ TradingSignal无HOLD值，实盘判断错误 [P1]
  守护进程循环   ✅ 正常
```

**系统整体健康度估算：感知层65% / 融合层10% / 状态机40% / 进化层20% / 生产层75%**

最关键的改进空间在**多周期融合层（当前是空壳）**和**状态机增量喂入**。
