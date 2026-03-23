# 状态机灵敏度调优 — 诊断报告

> 状态：待讨论
> 前置：Phase C Wave 1-3 完成 + 状态机识别层突破性修复
> 诊断日期：2026-03-23

## 当前表现（2000根H4 K线）

- **153次状态变化**，平均13.1根K线/转换
- **21个完整循环**（PS/SC/PSY/BC → UPTREND/DOWNTREND）
- 吸筹循环平均跨度：**30-89根**（5-15天H4）
- 派发循环平均跨度：**32-176根**（5-29天H4）
- IDLE重置仅3次（结构超时触发）

## 诊断：三大问题

### 问题1: 结构跑太快（核心问题）

典型吸筹应该是几周到几个月，但当前很多循环只有30-36根H4（5-6天）。

**根因**：状态机没有"最小结构持续时间"概念。每个事件只需3-5根K线确认就推进到下一个，整个结构几十根K线就跑完了。

**现实**：威科夫结构中，B阶段（TEST/LPS横盘）通常占整个结构的40-60%时间，可能持续几十到上百根H4。当前B阶段平均只有6-13根就被跳过了。

### 问题2: 横盘区间没有识别

**当前TR识别链路**：
```
engine._run_perception()
  → pattern_detection/tr_detector.py 检测TR
  → PerceptionResult.trading_range (support/resistance)
  → sm_context["tr_support/resistance"]
  → state_machine_v4._build_structure_context() 计算 position_in_tr
```

**问题**：
- TR检测器是独立的，和状态机的结构事件不关联
- 状态机确认了 SC→AR 后应该**锁定 SC_LOW~AR_HIGH 为TR边界**
- 但当前只记录了 critical_levels（SC_LOW/AR_HIGH），不用来约束后续事件的范围
- 横盘期间K线应该持续在 TR 内被标记为 TEST/LPS，而不是快速跳到 mSOS/JOC

### 问题3: 进化系统的策略参数需要重校准

V4状态机的行为和V2完全不同：
- 事件序列更明确（有完整的 A→B→C→D→E 阶段）
- 转换频率完全不同
- 信号产生位置变了（C阶段 SPRING/UTAD）

进化系统的评估器（BacktestEngine）依赖 process_bar() 输出的信号，信号变了，之前的最优参数全部失效。

## 改进方向（待讨论）

### 方向A: 增加结构内约束（最小停留时间）

给B阶段增加最小bar数要求：
- B阶段（TEST/LPS横盘）：最少20根H4才能进入C阶段
- 用 `bars_in_phase` 计数器
- 这会让状态机在横盘区间"安静下来"

### 方向B: TR锁定机制

SC→AR确认后，自动锁定 TR 边界：
- tr_support = SC_LOW（或ST重新测试的低点）
- tr_resistance = AR_HIGH
- 后续事件必须在这个TR范围内才合法
- 价格突破TR边界才触发C阶段事件（SPRING/UTAD/JOC）

### 方向C: 检测器精度提升

当前22个检测器大部分只用基础的 BarFeatures 评分，没有：
- 历史K线形态匹配
- 成交量剖面（Volume Profile）
- 支撑/阻力测试次数
- 趋势强度指标（ADX/MA斜率）

### 方向D: 进化系统重校准

等检测器精度提升后：
1. 重新跑进化（GA+WFA），找到V4状态机下的最优参数
2. 回测验证：Sharpe/MaxDD/WinRate
3. 可能需要调整策略族（从V4事件序列提取交易信号）

## 关键文件清单

| 文件 | 职责 | 行数 |
|------|------|------|
| `src/plugins/wyckoff_state_machine/state_machine_v4.py` | V4状态机核心 | ~895 |
| `src/plugins/wyckoff_state_machine/transition_guard.py` | 转换白名单 | 119 |
| `src/plugins/wyckoff_state_machine/detector_registry.py` | 检测器注册表 | ~100 |
| `src/plugins/wyckoff_state_machine/detectors/accumulation.py` | 吸筹检测器(13个) | ~500 |
| `src/plugins/wyckoff_state_machine/detectors/distribution.py` | 派发检测器(9个) | ~300 |
| `src/plugins/wyckoff_state_machine/principles/bar_features.py` | 三大原则打分器 | 295 |
| `src/plugins/pattern_detection/tr_detector.py` | TR识别器 | ~400 |
| `src/plugins/wyckoff_engine/engine.py` | 引擎（喂数据给状态机） | 1366 |

## 当前参数（StateConfig）

```python
STATE_MIN_CONFIDENCE = 0.25      # 假设产生门槛
CONFIRMATION_THRESHOLD = 0.8     # 确认累积质量阈值
MAX_HYPOTHESIS_BARS = 25         # 假设超时bar数
STATE_TIMEOUT_BARS = 20          # 状态超时（×2=40根无假设→IDLE重置）
SPRING_FAILURE_BARS = 5          # Spring失败判定
STATE_SWITCH_HYSTERESIS = 0.05   # 未使用
DIRECTION_SWITCH_PENALTY = 0.3   # 未使用
```
