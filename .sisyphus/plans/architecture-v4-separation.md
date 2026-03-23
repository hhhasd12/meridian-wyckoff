# 架构 v4.0：识别层/交易层分离 + 策略族

> 日期：2026-03-22
> 状态：待审核
> 前置：Wave 1 状态机可视化已完成，numpy round bug 已修复

## 核心目标

将 WyckoffEngine 从"既识别又交易"的单体，拆成两个独立层：

```
当前（v3.0）:
  OHLCV → WyckoffEngine.process_bar() → BarSignal（混合：state + signal + entry_price）
                                          ↓
                                    Orchestrator → PositionManager（单一链路）

目标（v4.0）:
  OHLCV → RecognitionEngine.recognize() → StateLabel（纯识别：phase/state/confidence/TR）
                                            ↓
                                      StrategyRouter.route(state_label)
                                            ↓
                                    ┌───────┴────────┐
                                    策略A          策略B          策略C
                                 （弹簧板）    （趋势延续）    （派发做空）
                                    └───────┬────────┘
                                            ↓
                                      TradingSignal → PositionManager
```

## 设计原则

1. **识别层只输出标签** — 不含任何交易信号（buy/sell），只说"现在是什么状态"
2. **交易层根据标签选策略** — 不同状态挂不同策略，策略可独立进化
3. **向后兼容** — 旧接口（process_bar）保留为 facade，内部调新架构
4. **渐进式迁移** — 不推翻重写，一步步拆

## 当前耦合分析

### WyckoffEngine 内部四阶段

```
process_bar():
  阶段1: _run_perception()    → PerceptionResult   ← 纯识别 ✅
  阶段2: _run_fusion()        → FusionResult        ← 纯融合 ✅
  阶段3: _run_state_machine() → WyckoffStateResult  ← 纯识别 ✅
  阶段4: _generate_decision() → TradingDecision     ← ⚠️ 交易决策
```

关键耦合点在 `_generate_decision()`（engine.py L949-L1101）：
- 读取 `state.signal`（WyckoffSignal.BUY/SELL）→ 转成 TradingSignal
- 读取 `state.signal_strength` → 决定 STRONG_BUY 还是 BUY
- 读取 `perception.breakout_status` → 调整 confidence
- 硬编码合约做空逻辑（trading_mode/leverage/allow_shorting）
- 低置信度阈值 `< 0.6` → 强制 NEUTRAL

**问题**：这些逻辑应该属于"策略"，不属于"识别引擎"。

### StateMachineV2 的 signal 耦合

```python
# wyckoff_state_machine/state_machine_v2.py
class StateMachineV2:
    def generate_signals(self, state, phase, ...) -> WyckoffSignal:
        # 根据 state+phase 判断 buy/sell/no_signal
```

状态机内部已经在生成交易信号了。这是最深层的耦合。

---

## 重构方案（4 Phase）

### Phase 1：定义 StateLabel 接口（0.5 天）

新建纯识别输出类型，不含任何交易信号：

```python
# src/kernel/types.py 新增
@dataclass
class StateLabel:
    """识别层纯输出 — 只描述市场状态，不含交易决策"""
    # 威科夫阶段
    phase: str              # "A"|"B"|"C"|"D"|"E"|"IDLE"
    state: str              # "PS"|"SC"|"AR"|"ST"|"SPRING"|...
    direction: str          # "ACCUMULATION"|"DISTRIBUTION"|"TRENDING"|"IDLE"
    confidence: float       # 0.0~1.0
    state_changed: bool
    previous_state: Optional[str]
    heritage_score: float
    
    # TR 边界
    tr_support: Optional[float]
    tr_resistance: Optional[float]
    tr_confidence: Optional[float]
    
    # 市场环境
    market_regime: str      # "TRENDING"|"RANGING"|"VOLATILE"|"UNKNOWN"
    regime_confidence: float
    
    # 关键水平
    critical_levels: Dict[str, float]
    
    # 感知层原始信号（供策略层使用）
    breakout_valid: bool
    breakout_direction: int  # 1=UP, -1=DOWN, 0=NONE
    fvg_signals: List[Dict]
    candle_stats: Dict[str, float]  # ATR, body_ratio 等
```

**关键区别**：没有 `signal`、`signal_strength`、`entry_price`、`stop_loss`。

改动文件：
- `src/kernel/types.py` — 新增 StateLabel dataclass

### Phase 2：抽取 RecognitionEngine（1 天）

从 WyckoffEngine 抽取识别逻辑为独立类：

```python
# src/plugins/wyckoff_engine/recognition.py 新建
class RecognitionEngine:
    """纯识别引擎 — 输入 OHLCV，输出 StateLabel"""
    
    def __init__(self, config: Dict):
        self._perception = PerceptionLayer(config)
        self._fusion = FusionLayer(config) 
        self._state_machine = StateMachineV2(config)
    
    def recognize(self, symbol: str, data_dict: Dict) -> StateLabel:
        """逐bar识别 — 只输出状态标签"""
        perception = self._run_perception(symbol, data_dict)
        fusion = self._run_fusion(data_dict, perception)
        state = self._run_state_machine(data_dict, perception, fusion)
        
        return StateLabel(
            phase=state.phase,
            state=state.current_state,
            direction=state.direction.value,
            confidence=state.confidence,
            # ... 纯状态数据，无交易信号
        )
```

改动文件：
- `src/plugins/wyckoff_engine/recognition.py` — 新建，从 engine.py 提取阶段1-3
- `src/plugins/wyckoff_engine/engine.py` — 内部改用 RecognitionEngine
- 不改外部接口，process_bar() 保持不变（facade）

### Phase 3：策略族框架（1.5 天）

新建策略路由器和策略基类：

```python
# src/plugins/strategy_router/base_strategy.py
class BaseStrategy(ABC):
    """策略基类 — 每个策略针对特定的威科夫阶段"""
    
    @property
    @abstractmethod
    def target_states(self) -> Set[str]:
        """该策略适用的威科夫状态集合"""
        ...
    
    @abstractmethod
    def evaluate(self, label: StateLabel, candle_stats: Dict) -> TradingSignal:
        """评估是否出信号"""
        ...
    
    @abstractmethod  
    def calculate_position(self, label: StateLabel) -> PositionSizing:
        """计算仓位大小"""
        ...

# src/plugins/strategy_router/plugin.py
class StrategyRouterPlugin(BasePlugin):
    """策略路由器 — 根据 StateLabel 选择并执行策略"""
    
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
    
    def on_load(self):
        # 注册内置策略
        self._strategies["spring_board"] = SpringBoardStrategy(self.config)
        self._strategies["trend_continuation"] = TrendContinuationStrategy(self.config)
        self._strategies["distribution_short"] = DistributionShortStrategy(self.config)
    
    def route(self, label: StateLabel) -> Optional[TradingDecision]:
        """根据状态标签路由到匹配的策略"""
        for name, strategy in self._strategies.items():
            if label.state in strategy.target_states:
                signal = strategy.evaluate(label, label.candle_stats)
                if signal != TradingSignal.NEUTRAL:
                    return TradingDecision(signal=signal, ...)
        return None  # 无匹配策略 → 不交易
```

**初始策略模块（3 个）：**

| 策略 | 适用状态 | 逻辑 |
|------|---------|------|
| `SpringBoardStrategy` | SPRING, TEST, SC | 弹簧板/震仓：跌破支撑后放量收回 → BUY |
| `TrendContinuationStrategy` | SOS, LPS, BU, JOC | 趋势延续：回踩不破 + 量增 → BUY |
| `DistributionShortStrategy` | UT, UTAD, LPSY, SOW | 派发做空：合约模式下看跌 → SELL |

改动文件：
- `src/plugins/strategy_router/` — 新建插件目录
  - `plugin-manifest.yaml`
  - `plugin.py` — StrategyRouterPlugin
  - `base_strategy.py` — BaseStrategy ABC
  - `strategies/spring_board.py`
  - `strategies/trend_continuation.py`  
  - `strategies/distribution_short.py`
- `config.yaml` — 新增 strategy_router 配置节

### Phase 4：事件链路改接（0.5 天）

重构事件流，把 StrategyRouter 插入链路：

```
当前链路:
  orchestrator._on_data_ready()
    → self._engine.process_market_data()  ← 内部生成 TradingDecision
    → emit("trading.signal", decision)
    → position_manager._on_trading_signal()

新链路:
  orchestrator._on_data_ready()
    → recognition_engine.recognize()      ← 纯识别，输出 StateLabel
    → emit("wyckoff.state_label", label)  ← 新事件
    → strategy_router._on_state_label()   ← 路由到策略
    → strategy.evaluate(label)            ← 策略生成信号
    → emit("trading.signal", decision)    ← 复用现有下游
    → position_manager._on_trading_signal()  ← 不变
```

改动文件：
- `src/plugins/orchestrator/plugin.py` — 改 emit 事件
- `src/plugins/strategy_router/plugin.py` — 订阅 `wyckoff.state_label`
- `src/kernel/types.py` — 无需改（StateLabel 在 Phase 1 已加）

---

## 不动的部分（向后兼容）

| 模块 | 是否改动 | 说明 |
|------|---------|------|
| WyckoffEngine.process_bar() | 保留 | facade，内部调 RecognitionEngine + 旧 _generate_decision |
| BarByBarBacktester | 不改 | 继续用 process_bar()，进化系统不受影响 |
| PositionManager | 不改 | 继续订阅 trading.signal |
| 前端 AnalysisPage | 不改 | POST /api/analyze 继续用 process_bar() |
| 前端 TradingPage | 不改 | WS 推送格式不变 |
| 1282 个测试 | 不应破坏 | facade 保证兼容 |

---

## 进化系统如何适配

当前进化是调 WyckoffEngine 的参数。分离后：

- **识别层参数**（TR检测灵敏度、状态转换阈值）→ 识别进化
- **策略层参数**（止损倍数、仓位比例、置信度阈值）→ 策略进化

两层可以**独立进化**：
1. 先固定策略参数，进化识别参数 → 让状态机更准
2. 再固定识别参数，进化策略参数 → 让交易更赚
3. 交替进化 → 逐步收敛

这正是讨论文档中说的"无限进化"路径。

---

## 执行顺序

```
Phase 1（StateLabel 类型定义）          ← 0.5 天
    ↓
Phase 2（RecognitionEngine 抽取）       ← 1 天
    ↓
Phase 3（策略族框架 + 3 个初始策略）    ← 1.5 天
    ↓
Phase 4（事件链路改接）                 ← 0.5 天
    ↓
验证：全量测试 + 分析页面 + 进化跑通
```

**总预估：3.5 天。**

---

## 风险点

1. **StateMachineV2 内部的 signal 生成** — generate_signals() 需要保留给 facade，但新链路不用它
2. **进化回测的一致性** — process_bar() facade 必须产出与旧版完全一致的结果
3. **策略参数空间** — 新增策略后，进化的参数空间变大，GA 收敛可能变慢

---

## 审核检查清单

- [ ] StateLabel 是否覆盖了所有识别输出？
- [ ] 3 个初始策略是否覆盖了常见交易场景？
- [ ] 事件链路改接后，下游模块（position_manager/telegram/audit_logger）是否不受影响？
- [ ] 进化系统如何切换"识别进化"和"策略进化"模式？
- [ ] facade 的 process_bar() 是否 100% 向后兼容？
