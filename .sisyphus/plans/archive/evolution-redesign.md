# 进化子系统架构重设计方案

> 版本: v1.0
> 日期: 2026-03-20
> 基础: 架构重组v3.0完成 + 5个探索Agent全量代码分析 + Oracle架构咨询
> 前提: 565测试通过, WyckoffEngine(961行)已创建, 15个审计bug已修复

---

## 0. 现状诊断

### 核心问题：进化是瞎的

当前 `run_evolution.py` 的 `real_performance_evaluator` 对 WyckoffEngine 做**一次性全量调用**：

```python
# run_evolution.py:292-294 — 致命缺陷
decision, engine_events = wyckoff_engine.process_market_data(
    symbol="EVOLUTION", timeframes=list(tf_data.keys()), data_dict=tf_data
)
```

引擎接收完整数据集(~2000根H4)，但只返回**最后一根K线的决策**。后续代码(297-320行)最多生成**1个信号**。
BacktestEngine拿到0-1个信号遍历100+根K线 → Sharpe≈0, WinRate=0%或100%, DrawDown≈0。

**结果**: 所有变异配置得分几乎相同，选择压力为零，GA等于随机搜索。

### 第二个致命问题：状态机是空壳

`WyckoffEngine._run_state_machine_decision()` (engine.py:725-759) **只有类型检查，没有业务逻辑**：

```python
def _run_state_machine_decision(self, data_dict, perception, fusion):
    events = EngineEvents()
    primary_data = data_dict[perception["primary_timeframe"]]
    try:
        if not isinstance(primary_data, pd.DataFrame):  # 正常数据一定是DataFrame
            ...  # 非DataFrame的降级处理
    except Exception:
        ...  # 异常降级
    # ← 当primary_data IS DataFrame时，直接落到这里
    # ← 隐式返回None
    # ← 第948行解包 state_results, state_events = ... 会抛TypeError
```

这意味着 `process_market_data()` 对正常DataFrame输入**一定崩溃**。进化调用时被上层吞掉异常或根本没走到这里。22节点威科夫状态机(`EnhancedWyckoffStateMachine`)已实例化但**从未被调用**。

### 问题全景

| # | 问题 | 严重度 | 位置 |
|---|------|--------|------|
| 1 | 只取最后一根K线决策，进化无选择压力 | **致命** | run_evolution.py:292 |
| 2 | 状态机方法是空壳，返回None | **致命** | engine.py:725-759 |
| 3 | WyckoffEngine零测试 | 高 | 无test文件 |
| 4 | 只进化~8个参数(系统有400+) | 中 | run_evolution.py:168-217 |
| 5 | 评估无向量加速，大数据慢 | 中 | 整个评估链路 |
| 6 | WFA元数据注入到data_dict中(类型不安全) | 低 | wfa_backtester.py:523 |

---

## 1. 设计方案总览

### 方案选型

逐根回测有三种方案：

| 方案 | 描述 | 复杂度 | 性能 | 风险 |
|------|------|--------|------|------|
| A: 增长切片 | 每根H4 bar调用`process_market_data(data[:i])` | **低** | O(n²)但引擎内部只看尾部，实际可接受 | 低 |
| B: 增量接口 | 新增`process_bar()`单根喂入 | 高 | O(n) | 高，需重构所有子模块 |
| C: 全量向量化 | 重写感知/融合/状态机为numpy向量运算 | 极高 | O(n) | 极高，状态机天然是串行的 |

**选择方案A**。理由：
1. WyckoffEngine内部的感知阶段只看最近3-30根K线（FVG看最近3根，物理统计看最近10根，突破验证看最近30根），不是全量遍历。所以虽然DataFrame在增长，但计算量基本恒定。
2. 400根H4 bar × 每次~10ms = ~4秒/评估。10个种群 × 5个WFA窗口 = 50次评估 × 4秒 = ~200秒。用4核并行→~50秒/轮。完全可接受。
3. 零引擎改动，不碰已有逻辑，回归风险最低。
4. 未来如果性能真的不够，可以渐进升级到方案B，不影响外部接口。

### 新架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    run_evolution.py (入口)                    │
│                                                              │
│  ┌─ EvolutionEvaluator ────────────────────────────────┐    │
│  │                                                      │    │
│  │  ┌─ BarByBarAdapter ─────────────────────────────┐  │    │
│  │  │                                                │  │    │
│  │  │  for bar_idx in range(warmup, len(h4)):        │  │    │
│  │  │    data_slice = build_slice_up_to(bar_idx)     │  │    │
│  │  │    decision = engine.process_market_data(slice) │  │    │
│  │  │    if signal_control.should_emit(decision):     │  │    │
│  │  │      signals.append(decision)                   │  │    │
│  │  │                                                │  │    │
│  │  │  WyckoffEngine (不修改，直接复用)              │  │    │
│  │  └────────────────────────────────────────────────┘  │    │
│  │                                                      │    │
│  │  BacktestEngine.run(h4_data, signals)                │    │
│  │  → BacktestResult (trades, equity, metrics)          │    │
│  │                                                      │    │
│  │  MistakeBook.record_mistakes(losing_trades)          │    │
│  │  → 返回标准化指标 dict                               │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  SelfCorrectionWorkflow (不修改，只替换evaluator)            │
│    Stage 1: MistakeBook → 错误分析                           │
│    Stage 2: WeightVariator → GA变异                          │
│    Stage 3: WFABacktester → 滚动窗口验证                     │
│      └─ 对每个config × 每个窗口调用 EvolutionEvaluator       │
│    Stage 4: 配置更新 + fitness回传                           │
│    Stage 5: 评估                                             │
└─────────────────────────────────────────────────────────────┘
```

### 关键设计决策

1. **不修改WyckoffEngine** — 它是实盘和进化共用的唯一信号源，只做外部包装
2. **不修改SelfCorrectionWorkflow** — 只替换传入的evaluator函数
3. **新增2个文件** — `bar_by_bar_adapter.py` + `evaluator.py`，放在 `src/plugins/evolution/`
4. **并行化在种群层面** — 每个config独立评估，用ProcessPoolExecutor
5. **状态机空壳先补默认返回值** — 阻止崩溃，让感知+融合阶段先产生信号

---

## 2. 接口定义

### 2.1 BarByBarAdapter — 逐根K线适配器

**文件**: `src/plugins/evolution/bar_by_bar_adapter.py`

```python
@dataclass
class BarSignal:
    """单根K线产生的信号"""
    bar_idx: int
    timestamp: datetime
    signal: str          # "BUY" | "SELL"
    confidence: float
    reasoning: List[str]
    wyckoff_state: str
    market_regime: str

@dataclass
class SignalControl:
    """信号节流控制（防止信号刷屏）"""
    cooldown_bars: int = 8        # 同方向冷却期
    last_signal_bar: int = -999
    last_signal_direction: str = "NEUTRAL"

    def should_emit(
        self, bar_idx: int, signal: str,
        confidence: float, threshold: float,
    ) -> bool:
        """检查信号是否通过冷却和阈值过滤"""
        if signal == "NEUTRAL" or signal == "WAIT":
            return False
        if confidence < threshold:
            return False
        if (bar_idx - self.last_signal_bar) < self.cooldown_bars:
            if signal == self.last_signal_direction:
                return False
        return True

    def record_emission(self, bar_idx: int, signal: str) -> None:
        self.last_signal_bar = bar_idx
        self.last_signal_direction = signal

class BarByBarAdapter:
    """包装WyckoffEngine，实现逐根K线回测

    核心逻辑：
    1. 以H4为锚定时间框架
    2. 每根H4 bar，构建截止到该bar时间戳的多TF数据切片
    3. 调用 engine.process_market_data(切片)
    4. 收集信号，经过SignalControl过滤
    """

    def __init__(
        self,
        config: Dict[str, Any],
        warmup_bars: int = 50,
        anchor_tf: str = "H4",
    ) -> None: ...

    def evaluate(
        self,
        symbol: str,
        data_dict: Dict[str, pd.DataFrame],
        test_start_idx: Optional[int] = None,
    ) -> List[BarSignal]:
        """逐根K线生成信号

        Args:
            symbol: 交易对
            data_dict: 多TF数据 {"H4": df, "H1": df, ...}
            test_start_idx: 仅统计此index之后的信号（之前为warmup）

        Returns:
            List[BarSignal] 所有通过过滤的信号
        """
        engine = WyckoffEngine(self.config)
        signals: List[BarSignal] = []
        control = SignalControl(
            cooldown_bars=self.config.get("signal_control", {}).get("cooldown_bars", 8)
        )
        threshold = self.config.get("threshold_parameters", {}).get("confidence_threshold", 0.3)

        anchor_data = data_dict[self.anchor_tf]
        start = max(self.warmup_bars, test_start_idx or 0)

        for bar_idx in range(start, len(anchor_data)):
            # 构建时间对齐的数据切片
            slice_dict = self._build_slice_up_to(bar_idx, anchor_data, data_dict)
            if not slice_dict:
                continue

            # 调用引擎（引擎看到的是截止到当前bar的数据，无前视偏差）
            decision, events = engine.process_market_data(
                symbol=symbol,
                timeframes=list(slice_dict.keys()),
                data_dict=slice_dict,
            )

            # 信号过滤
            signal_val = decision.signal.value
            direction = self._map_signal(signal_val)
            if direction and control.should_emit(bar_idx, direction, decision.confidence, threshold):
                signals.append(BarSignal(
                    bar_idx=bar_idx,
                    timestamp=anchor_data.index[bar_idx],
                    signal=direction,
                    confidence=decision.confidence,
                    reasoning=decision.reasoning,
                    wyckoff_state=decision.context.wyckoff_state if decision.context else "unknown",
                    market_regime=decision.context.market_regime if decision.context else "unknown",
                ))
                control.record_emission(bar_idx, direction)

            # 早期终止：200根bar后0信号，跳过剩余
            if bar_idx > start + 200 and len(signals) == 0:
                break

        return signals

    def _build_slice_up_to(
        self, bar_idx: int,
        anchor_data: pd.DataFrame,
        all_tf_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        """构建截止到anchor_data[bar_idx]时间戳的多TF数据切片

        关键：对每个TF，只包含 timestamp <= 当前H4 bar的时间戳
        这保证了因果律（无前视偏差）
        """
        current_time = anchor_data.index[bar_idx]
        result: Dict[str, pd.DataFrame] = {}
        for tf_name, tf_df in all_tf_data.items():
            sliced = tf_df.loc[tf_df.index <= current_time]
            if len(sliced) >= 20:  # 最少20根用于指标计算
                result[tf_name] = sliced
        return result

    @staticmethod
    def _map_signal(signal_val: str) -> Optional[str]:
        if signal_val in ("buy", "strong_buy"):
            return "BUY"
        elif signal_val in ("sell", "strong_sell"):
            return "SELL"
        return None
```

### 2.2 EvolutionEvaluator — 标准化评估器

**文件**: `src/plugins/evolution/evaluator.py`

```python
class EvolutionEvaluator:
    """标准化评估器 — 替代broken的real_performance_evaluator

    职责：
    1. 用BarByBarAdapter逐根生成信号
    2. 用BacktestEngine模拟交易
    3. 计算标准化性能指标
    4. 记录亏损交易到MistakeBook
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0005,
        warmup_bars: int = 50,
        mistake_book: Optional[MistakeBook] = None,
    ) -> None: ...

    def __call__(
        self,
        config: Dict[str, Any],
        data: Dict[str, pd.DataFrame],
    ) -> Dict[str, float]:
        """评估单个配置的性能 — WFABacktester的回调接口

        处理WFA元数据：
        - data.pop("__test_start_ts__"): 仅对此时间戳之后的bar打分
        - data.pop("__warmup_bars__"): 指标预热期

        Returns:
            {"SHARPE_RATIO": float, "MAX_DRAWDOWN": float, "WIN_RATE": float,
             "PROFIT_FACTOR": float, "CALMAR_RATIO": float, "TOTAL_TRADES": int,
             "COMPOSITE_SCORE": float}
        """
        # 1. 提取WFA元数据（从data_dict中pop出来，不传给引擎）
        test_start_ts = data.pop("__test_start_ts__", None)
        warmup = data.pop("__warmup_bars__", self.warmup_bars)

        # 2. 计算test_start_idx
        h4 = data.get("H4")
        test_start_idx = None
        if test_start_ts is not None:
            test_start_idx = h4.index.searchsorted(test_start_ts)

        # 3. 逐根生成信号
        adapter = BarByBarAdapter(config, warmup_bars=warmup)
        bar_signals = adapter.evaluate("EVOLUTION", data, test_start_idx)

        # 4. 转换为BacktestEngine格式
        signals = [{"timestamp": s.timestamp, "signal": s.signal,
                     "reason": f"conf={s.confidence:.2f}"} for s in bar_signals]

        # 5. 运行回测
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
            slippage_rate=self.slippage_rate,
        )
        result = engine.run(h4, state_machine=None, signals=signals)

        # 6. 记录亏损到MistakeBook
        if self.mistake_book:
            for trade in result.trades:
                if trade.pnl < 0:
                    self.mistake_book.record_mistake(...)

        # 7. 返回标准化指标
        return self._compute_metrics(result)

    @staticmethod
    def _compute_metrics(result: BacktestResult) -> Dict[str, float]:
        """从BacktestResult计算标准化指标"""
        ...
```

### 2.3 多TF时间对齐协议

```
时间轴: ──────────────────────────────────►
H4:     [0]  [1]  [2]  [3]  ... [bar_idx]  [bar_idx+1] ...
H1:     [0][1][2][3] [4][5][6][7] ...       │
M15:    [0]..[15] [16]..[31] ...            │
M5:     [0]..[47] [48]..[95] ...            │
                                            │
                              current_time ─┘

对于 bar_idx 处的H4 bar（时间戳 T）：
├── H4:  data[:bar_idx+1]    (包含当前bar)
├── H1:  data[index <= T]    (~4× H4根数)
├── M15: data[index <= T]    (~16× H4根数)
├── M5:  data[index <= T]    (~48× H4根数)
└── D1:  data[index <= T]    (~1/6× H4根数)

关键：每个TF只包含已收盘的K线（timestamp <= T）
这复现了实盘中引擎在H4 bar收盘时做决策的行为
```

---

## 3. 状态管理协议

| 场景 | 动作 | 原因 |
|------|------|------|
| 新WFA窗口开始 | `engine = WyckoffEngine(config)` 新实例 | 窗口间完全独立 |
| 同一窗口内逐根推进 | **不reset** | 状态机需要跨bar积累证据 |
| 新种群成员评估 | 新实例 `WyckoffEngine(new_config)` | 不同config = 不同引擎 |
| 实盘引擎 | **永远不碰** | 进化创建独立实例，实盘引擎不受影响 |

**实现规则**: `BarByBarAdapter.evaluate()` 在方法入口创建新 `WyckoffEngine(config)`，方法结束引擎被GC。适配器本身无状态。

---

## 4. 性能优化策略

### 4.1 性能预算

```
单次评估 (400根H4 × 5TF):
  引擎内部每次调用: ~10ms（感知只看尾部数据）
  400次调用: ~4秒
  + BacktestEngine: ~0.1秒
  = ~4秒/评估

单轮进化:
  10个种群 × 5个WFA窗口 = 50次评估
  串行: 50 × 4秒 = 200秒
  4核并行: ~50秒
  目标: < 60秒/轮 ✓
```

### 4.2 并行策略：种群级别 ProcessPoolExecutor

```python
from concurrent.futures import ProcessPoolExecutor

def evaluate_population(
    configs: List[Dict[str, Any]],
    data_dict: Dict[str, pd.DataFrame],
    evaluator: EvolutionEvaluator,
    max_workers: int = 4,
) -> List[Dict[str, float]]:
    """并行评估所有种群成员"""
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(evaluator, config, data_dict.copy())
            for config in configs
        ]
        return [f.result() for f in futures]
```

注意：每个worker ~50MB内存（WyckoffEngine + 数据拷贝），4 worker = ~200MB，可接受。

### 4.3 早期终止

```python
# 在 BarByBarAdapter.evaluate() 内：
if bar_idx > start + 200 and len(signals) == 0:
    logger.debug("早期终止：200根bar后0信号")
    break
```

200根H4 ≈ 33天无信号 → 这个config基本无用，跳过剩余节省~50%时间。

### 4.4 未来优化方向（本轮不做）

| 优化 | 预期提升 | 代价 |
|------|---------|------|
| 预计算指标数组(ATR/ADX/MA) | 2-3× | 需修改引擎内部 |
| process_bar()增量接口 | 5-10× | 大规模重构 |
| Cython/Numba加速状态机 | 3-5× | 依赖管理复杂 |

---

## 5. WyckoffEngine 测试策略

### 5.1 测试Fixture设计

**文件**: `tests/plugins/test_wyckoff_engine.py`

需要3类测试数据生成器：

```python
def make_ohlcv(n: int, trend: str = "flat", seed: int = 42) -> pd.DataFrame:
    """生成n根OHLCV数据

    trend:
      "flat"   — 价格在100±5%震荡，成交量稳定
      "up"     — 价格从100涨到150，成交量递增
      "down"   — 价格从150跌到100，成交量递增
      "spring" — 先跌后涨（模拟威科夫Spring）
    """
    ...

def make_multi_tf_data(h4_bars: int = 200, trend: str = "flat") -> Dict[str, pd.DataFrame]:
    """生成时间对齐的多TF数据
    H4: h4_bars根
    H1: h4_bars * 4根
    M15: h4_bars * 16根
    M5: h4_bars * 48根
    D1: h4_bars // 6根
    """
    ...
```

### 5.2 测试分级

**P0 — 冒烟测试（必须第一轮写）**

| 测试 | 断言 |
|------|------|
| `test_engine_init` | WyckoffEngine() 不抛异常 |
| `test_engine_init_with_config` | WyckoffEngine(config) 正确初始化11个子组件 |
| `test_process_returns_correct_types` | 返回 `(TradingDecision, EngineEvents)` |
| `test_decision_has_required_fields` | signal, confidence, context, reasoning 非None |
| `test_confidence_in_range` | 0.0 <= confidence <= 1.0 |
| `test_signal_is_valid_enum` | signal ∈ TradingSignal |
| `test_reset_clears_state` | reset()后再调用 = 全新实例的结果 |

**P1 — 感知阶段测试**

| 测试 | 断言 |
|------|------|
| `test_perception_returns_regime` | perception["market_regime"]["regime"] ∈ MarketRegime |
| `test_perception_detects_tr` | 给定区间数据 → tr_detected == True |
| `test_perception_pin_body` | 给定长上影线 → pin_body有结果 |
| `test_perception_fvg` | 给定跳空数据 → fvg_signals非空 |

**P2 — 方向正确性测试**

| 测试 | 断言 |
|------|------|
| `test_uptrend_bias_bullish` | 强上涨数据 → signal偏向BUY |
| `test_downtrend_bias_bearish` | 强下跌数据 → signal偏向SELL |
| `test_flat_bias_neutral` | 震荡数据 → signal偏向NEUTRAL |
| `test_config_sensitivity` | 不同config → 不同confidence |
| `test_no_lookahead` | 注入未来异常数据(price=999999) → 引擎不受影响 |

**P3 — 边界条件**

| 测试 | 断言 |
|------|------|
| `test_empty_dataframe` | 不崩溃，返回NEUTRAL |
| `test_single_row` | 不崩溃 |
| `test_missing_timeframes` | 部分TF缺失时优雅降级 |
| `test_nan_values` | NaN不导致崩溃 |
| `test_state_machine_stub` | 当前空壳返回neutral/0.5 |

### 5.3 覆盖率目标

| 模块 | 目标 | 说明 |
|------|------|------|
| WyckoffEngine | >80% | 核心引擎 |
| BarByBarAdapter | >90% | 新代码，必须扎实 |
| EvolutionEvaluator | >85% | 新代码 |
| 端到端集成 | ≥3个测试 | config→adapter→backtest→metrics |

---

## 6. 实施阶段（依赖排序）

### Phase 1: 修复状态机空壳 [0.5天]

**前提**: 无（第一步必须做）
**目标**: `_run_state_machine_decision()` 不再返回None

修复方式：在try块的DataFrame正常路径末尾加上默认返回值（不实现完整状态机逻辑，那是未来的事）。

```python
# engine.py:725-759 — 在try块末尾添加
try:
    if not isinstance(primary_data, pd.DataFrame):
        ...  # 现有降级逻辑
    # ↓ 新增：DataFrame正常路径的默认返回
    return {
        "wyckoff_state": "neutral",
        "state_confidence": 0.5,
        "state_signals": [],
        "evidence_chain": [],
        "state_direction": "UNKNOWN",
        "state_intensity": 0.0,
    }, events
except Exception:
    ...  # 现有异常降级
```

**验证**: `process_market_data()` 对正常DataFrame数据不再崩溃。565测试仍通过。

### Phase 2: WyckoffEngine 单元测试 [1-2天]

**前提**: Phase 1（引擎不崩溃才能测）
**目标**: P0 + P1 测试全部通过

交付物：
- `tests/fixtures/ohlcv_generator.py` — 测试数据生成器
- `tests/plugins/test_wyckoff_engine.py` — P0(7个) + P1(4个) + P2(5个) + P3(5个) ≈ 21个测试
- 覆盖率 >80%

### Phase 3: BarByBarAdapter + EvolutionEvaluator [1-2天]

**前提**: Phase 1（引擎可调用）
**目标**: 逐根回测产生有意义的信号数量

交付物：
- `src/plugins/evolution/bar_by_bar_adapter.py` — ~150行
- `src/plugins/evolution/evaluator.py` — ~120行
- `tests/plugins/test_bar_by_bar_adapter.py` — ~10个测试
- `tests/plugins/test_evolution_evaluator.py` — ~8个测试

**验证**: 400根H4数据 → 生成 5-50 个信号（而非0-1个）

### Phase 4: 替换 real_performance_evaluator [0.5天]

**前提**: Phase 3（新evaluator可用）
**目标**: run_evolution.py 使用新评估器

改动范围（仅 `run_evolution.py`）：
1. 删除 `real_performance_evaluator()` 函数（~180行）
2. 导入 `EvolutionEvaluator`
3. 替换 `workflow.set_performance_evaluator()` 的参数

```python
# 改动前 (run_evolution.py:587-590)
def performance_evaluator(cfg, data):
    return real_performance_evaluator(cfg, data, mistake_book=mistake_book)
workflow.set_performance_evaluator(performance_evaluator)

# 改动后
from src.plugins.evolution.evaluator import EvolutionEvaluator
evaluator = EvolutionEvaluator(mistake_book=mistake_book)
workflow.set_performance_evaluator(evaluator)
```

**验证**: 运行一轮进化循环，确认WFA窗口中每个config产生>5笔交易。

### Phase 5: 并行化 + 集成测试 [1天]

**前提**: Phase 4（端到端可用）
**目标**: 性能达标 + 端到端集成验证

交付物：
- WFABacktester中集成 ProcessPoolExecutor
- 3个端到端集成测试
- 性能基准：单轮进化 <60秒 (4核)

### Phase 6: 扩展进化参数 [未来，本轮不做]

**前提**: Phase 5完成，进化已有真实选择压力
**等Phase 1-5验证通过后再考虑**：
- 感知阈值（FVG, 突破, 针体）
- 风控参数（止损%，trailing ATR倍数）
- 参数重要性排序（MistakeBook驱动）

### 进度总览

```
Phase 1: 修复状态机空壳     [0.5天] ← 无依赖，第一步
Phase 2: WyckoffEngine测试  [1-2天] ← 依赖Phase 1
Phase 3: Adapter+Evaluator  [1-2天] ← 依赖Phase 1，可与Phase 2并行
Phase 4: 替换评估器         [0.5天] ← 依赖Phase 3
Phase 5: 并行化+集成测试    [1天]   ← 依赖Phase 4
──────────────────────────────────────
总计: 4-6天
```

---

## 7. 风险分析

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 逐根回测太慢(>10min/评估) | 低 | 高 | 早期终止 + 种群级并行。实测估计~4秒/400bar |
| 状态机跨bar状态积累错误 | 中 | 高 | Phase 2 reset测试：reset()后 = 新实例结果 |
| 多TF时间对齐off-by-one | 中 | 中 | 单测注入未来数据(price=999999)，引擎看到则测试失败 |
| 状态机空壳导致信号不够丰富 | **确定** | 中 | 当前只有感知+融合信号，无状态机信号。但已足够给进化提供选择压力。状态机实现是后续单独的工作 |
| 565测试回归 | 低 | 中 | 新增文件不碰已有代码。仅改 run_evolution.py（无测试覆盖） |
| 并行化内存爆炸 | 低 | 中 | 默认 max_workers=4，每个~50MB，共~200MB |
| WFA __test_start_ts__ dict注入类型不安全 | 中 | 低 | evaluator.__call__ 第一步 pop 元数据，不传给引擎 |

### 需要注意的坑

1. **`datetime.now(timezone.utc)`** — engine.py 融合阶段(L648)用墙钟时间而非K线时间构建 `market_context`。回测时这个时间戳是错的，但不影响信号逻辑（只是元数据），暂不修。

2. **WFA data dict 类型污染** — `wfa_backtester.py:523` 往 `Dict[str, pd.DataFrame]` 里塞 `__test_start_ts__`（datetime类型）和 `__warmup_bars__`（int类型）。EvolutionEvaluator必须在第一步 `pop()` 掉这些，否则传给引擎会出问题。

3. **BacktestEngine 的局限** — 当前 BacktestEngine (agent_teams/backtest/engine.py) 不支持止损/止盈（审计中已标记）。本轮只用它做基础模拟，止损/止盈的加入是后续工作。

4. **data.pop() 会修改原始dict** — 如果WFA对同一个data_dict调用多个config的evaluator，第二次调用时 `__test_start_ts__` 已经被pop掉了。需要在WFA侧每次传副本，或者evaluator里用 `data.get()` + 手动排除。

---

## 8. 与上一轮重组的关系

上一轮(v3.0)完成的事：
- ✅ 统一信号引擎 WyckoffEngine (961行)
- ✅ 删除4725行死代码/重复代码
- ✅ 修复15个审计bug
- ✅ 统一进化路径(4→1)、评估器(3→1)、UI(3→1)

本轮要做的事：
- 🔧 修复状态机空壳（让引擎真正可用）
- 🔧 逐根K线回测（让进化真正能看见信号）
- 🔧 WyckoffEngine单元测试（让引擎有质量保障）
- 🔧 标准化评估器接口（让进化闭环运转）
- 🔧 并行加速（让进化实际可用）

下一轮要做的事（本轮不碰）：
- 📋 实现完整的状态机逻辑（22节点威科夫状态转换）
- 📋 扩展进化参数空间（从~28个到更多）
- 📋 BacktestEngine加止损/止盈
- 📋 WFA元数据改为独立参数（不污染data dict）

---

*文档结束*
*生成方式: 5个explore agent全量代码分析 + Oracle架构咨询 + 人工综合*
*涉及代码: engine.py(961行), run_evolution.py(672行), workflow.py(950行), wfa_backtester.py(843行), weight_variator_legacy.py(1132行), types.py(629行), FULL_AUDIT.md(511行)*

