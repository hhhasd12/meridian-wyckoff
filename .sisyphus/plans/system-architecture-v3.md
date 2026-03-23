# 威科夫全自动逻辑引擎 v3.0 — 系统架构设计文档

**版本**: v3.0（从零设计重构）
**日期**: 2026-03-20
**状态**: 单一权威设计源（Single Source of Truth）

---

## 一、模块地图：职责与类型化接口

### 1.1 总体分层

```
┌─────────────────────────────────────────────────────────────┐
│  入口层   run.py → WyckoffApp (src/app.py)                  │
├─────────────────────────────────────────────────────────────┤
│  内核层   src/kernel/  [保留]                                │
│  EventBus · PluginManager · ConfigSystem · types.py         │
├─────────────────────────────────────────────────────────────┤
│  信号引擎 src/plugins/wyckoff_engine/  [重建]                │
│  WyckoffEngine — 唯一信号路径（实盘+进化共用）              │
├─────────────────────────────────────────────────────────────┤
│  分析插件层 src/plugins/                                     │
│  ┌──────────┐ ┌────────────┐ ┌──────────────────┐           │
│  │感知层    │ │融合层      │ │状态机层          │           │
│  │[保留]    │ │[保留]      │ │[重建]            │           │
│  │regime    │ │weight      │ │wyckoff_state_    │           │
│  │TR/FVG    │ │conflict    │ │  machine         │           │
│  │perception│ │micro_entry │ │                  │           │
│  └──────────┘ └────────────┘ └──────────────────┘           │
├─────────────────────────────────────────────────────────────┤
│  执行插件层                                                  │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────┐         │
│  │orchestrator│ │position_mgr  │ │exchange_conn   │         │
│  │[重建]      │ │[修复]        │ │[接通]          │         │
│  └────────────┘ └──────────────┘ └────────────────┘         │
├─────────────────────────────────────────────────────────────┤
│  进化插件层                                                  │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────┐         │
│  │evolution   │ │self_correct  │ │weight_system   │         │
│  │[重建]      │ │[修复]        │ │[修复]          │         │
│  └────────────┘ └──────────────┘ └────────────────┘         │
├─────────────────────────────────────────────────────────────┤
│  API层  src/api/  [重建]                                     │
│  辅助层 dashboard · agent_teams  [延后]                      │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 每个模块的接口定义

#### 内核层 — `src/kernel/types.py` 新增类型

```python
# === 新增：统一信号链类型 ===

@dataclass
class PerceptionResult:
    """感知层输出 — 替代 Dict[str, Any] 的散装字典"""
    market_regime: str                       # "TRENDING" | "RANGING" | "VOLATILE" | "UNKNOWN"
    regime_confidence: float                 # 0.0~1.0
    trading_range: Optional["TradingRangeInfo"]
    fvg_signals: List["FVGSignal"]
    breakout_status: Optional["BreakoutInfo"]
    pin_body_summary: Optional["PinBodySummary"]
    candle_physical: Optional["CandlePhysicalStats"]
    anomaly_events: List["AnomalyEvent"]
    timestamp: datetime

@dataclass
class TradingRangeInfo:
    """TR检测结果"""
    has_range: bool
    support: Optional[float]
    resistance: Optional[float]
    confidence: float
    breakout_direction: Optional[str]        # "UP" | "DOWN" | None
    resonance_score: float = 0.0             # 多TF共振分数

@dataclass
class FVGSignal:
    """FVG信号"""
    direction: str                           # "BULLISH" | "BEARISH"
    gap_top: float
    gap_bottom: float
    fill_ratio: float
    timestamp: datetime

@dataclass
class BreakoutInfo:
    """突破验证结果"""
    is_valid: bool
    direction: int                           # 1=向上, -1=向下, 0=无
    breakout_level: float
    breakout_strength: float
    volume_confirmation: bool

@dataclass
class PinBodySummary:
    """针体分析汇总"""
    dominant_pattern: str                    # "PIN" | "BODY" | "NEUTRAL"
    avg_pin_strength: float
    avg_body_strength: float
    avg_confidence: float

@dataclass
class CandlePhysicalStats:
    """K线物理属性统计"""
    avg_body_size: float
    avg_shadow_size: float
    avg_body_ratio: float
    doji_pct: float
    hammer_pct: float
    shooting_star_pct: float

@dataclass
class FusionResult:
    """多周期融合输出"""
    timeframe_weights: Dict[str, float]
    conflicts: List["TimeframeConflict"]
    resolved_bias: str                       # "BULLISH" | "BEARISH" | "NEUTRAL"
    entry_validation: Optional["EntryValidation"]
    timestamp: datetime

@dataclass
class TimeframeConflict:
    """时间框架冲突"""
    higher_tf: str
    higher_bias: str
    lower_tf: str
    lower_bias: str
    resolution: str                          # "follow_higher" | "reduce_size" | "wait"
    confidence_penalty: float

@dataclass
class EntryValidation:
    """微观入场验证"""
    is_valid: bool
    entry_grade: str                         # "A" | "B" | "C" | "D"
    m15_confirmation: bool
    m5_confirmation: bool
    optimal_entry_zone: Optional[float]

@dataclass
class WyckoffStateResult:
    """状态机输出"""
    current_state: str
    phase: str                               # "A" | "B" | "C" | "D" | "E" | "IDLE"
    direction: StateDirection
    confidence: float
    intensity: float
    evidences: List[StateEvidence]
    signal: WyckoffSignal
    signal_strength: str                     # "strong" | "medium" | "weak" | "none"
    state_changed: bool
    previous_state: Optional[str]
    heritage_score: float
    critical_levels: Dict[str, float]        # SC_LOW, BC_HIGH, etc.

@dataclass
class OrderRequest:
    """订单请求 — PositionManager → ExchangeExecutor"""
    symbol: str
    side: str                                # "BUY" | "SELL"
    order_type: str                          # "MARKET" | "LIMIT"
    size: float
    price: Optional[float]                   # 限价单必填
    stop_loss: Optional[float]
    take_profit: Optional[float]
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class OrderResult:
    """订单执行结果 — ExchangeExecutor → PositionManager"""
    success: bool
    order_id: str
    filled_price: float
    filled_size: float
    commission: float
    timestamp: datetime
    error_message: Optional[str] = None

# === 新增：进化系统类型 ===

@dataclass
class BarSignal:
    """逐K线信号 — WyckoffEngine 逐bar产出"""
    bar_index: int
    timestamp: datetime
    signal: TradingSignal
    confidence: float
    wyckoff_state: str
    phase: str
    evidences: List[StateEvidence]
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]

@dataclass
class BacktestTrade:
    """回测交易记录"""
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    side: str                                # "LONG" | "SHORT"
    size: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    hold_bars: int
    entry_state: str
    max_favorable: float                     # 最大有利偏移
    max_adverse: float                       # 最大不利偏移

@dataclass
class BacktestResult:
    """回测结果"""
    trades: List[BacktestTrade]
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_hold_bars: float
    config_hash: str                         # 配置指纹

@dataclass
class GAIndividual:
    """遗传算法个体"""
    config: Dict[str, Any]
    fitness: float
    generation: int
    config_hash: str
    backtest_result: Optional[BacktestResult] = None

@dataclass
class WFAWindow:
    """WFA滚动窗口"""
    train_start: int                         # bar索引
    train_end: int
    test_start: int
    test_end: int
    train_result: Optional[BacktestResult] = None
    test_result: Optional[BacktestResult] = None
```

### 1.3 模块接口签名

```python
# === WyckoffEngine（统一信号引擎） ===
class WyckoffEngine:
    def __init__(self, config: Dict[str, Any]) -> None: ...
    def reset(self) -> None: ...
    def process_bar(self, symbol: str, data_dict: Dict[str, pd.DataFrame]) -> BarSignal: ...
    def process_market_data(self, symbol: str, timeframes: List[str],
                           data_dict: Dict[str, pd.DataFrame]) -> Tuple[TradingDecision, EngineEvents]: ...
    # 内部分阶段
    def _run_perception(self, symbol: str, data_dict: Dict[str, pd.DataFrame]) -> PerceptionResult: ...
    def _run_fusion(self, data_dict: Dict[str, pd.DataFrame], perception: PerceptionResult) -> FusionResult: ...
    def _run_state_machine(self, data_dict: Dict[str, pd.DataFrame],
                           perception: PerceptionResult, fusion: FusionResult) -> WyckoffStateResult: ...
    def _generate_decision(self, perception: PerceptionResult, fusion: FusionResult,
                          state: WyckoffStateResult) -> TradingDecision: ...

# === WyckoffStateMachineV2（每TF独立实例） ===
class WyckoffStateMachineV2:
    def __init__(self, timeframe: str, config: StateConfig) -> None: ...
    def process_candle(self, candle: pd.Series, context: Dict[str, Any]) -> WyckoffStateResult: ...
    def get_phase(self) -> str: ...
    def get_evidence_chain(self) -> List[StateEvidence]: ...

# === OrchestratorPlugin（事件桥梁） ===
class OrchestratorPlugin(BasePlugin):
    def on_load(self) -> None: ...        # 订阅 data_pipeline.ohlcv_ready
    def _on_data_ready(self, event_name: str, data: Dict[str, Any]) -> None: ...
    # 调用 WyckoffEngine.process_market_data()
    # 发布 trading.signal（PositionManager 订阅的事件）

# === PositionManagerPlugin（接收信号，管理仓位） ===
class PositionManagerPlugin(BasePlugin):
    # 订阅 trading.signal
    # 调用 ExchangeExecutor 下单
    def _on_trading_signal(self, event_name: str, data: Dict[str, Any]) -> None: ...
    def _execute_order(self, request: OrderRequest) -> OrderResult: ...

# === ExchangeExecutor（统一执行接口） ===
class ExchangeExecutor:
    def execute(self, request: OrderRequest) -> OrderResult: ...
    def get_balance(self) -> float: ...
    def get_position(self, symbol: str) -> Optional[Dict]: ...

# === BarByBarBacktester（进化用逐bar回测） ===
class BarByBarBacktester:
    def __init__(self, engine: WyckoffEngine, config: Dict[str, Any]) -> None: ...
    def run(self, data_dict: Dict[str, pd.DataFrame],
            start_bar: int, end_bar: int) -> BacktestResult: ...

# === GeneticAlgorithm ===
class GeneticAlgorithm:
    def __init__(self, param_space: Dict[str, Tuple], population_size: int) -> None: ...
    def initialize_population(self) -> List[GAIndividual]: ...
    def evaluate(self, individual: GAIndividual,
                 evaluator: Callable[[Dict], BacktestResult]) -> float: ...
    def select(self, population: List[GAIndividual]) -> List[GAIndividual]: ...
    def crossover(self, parent_a: GAIndividual, parent_b: GAIndividual) -> GAIndividual: ...
    def mutate(self, individual: GAIndividual, mistake_patterns: List) -> GAIndividual: ...
    def evolve_generation(self) -> GAIndividual: ...

# === WFAValidator ===
class WFAValidator:
    def __init__(self, train_days: int, test_days: int, step_days: int) -> None: ...
    def generate_windows(self, total_bars: int) -> List[WFAWindow]: ...
    def validate(self, config: Dict, data_dict: Dict[str, pd.DataFrame],
                 backtester: BarByBarBacktester) -> Tuple[bool, float]: ...
```

---

## 二、数据流图：从原始OHLCV到交易执行

```
                        ┌─────────────────────────┐
                        │  DataPipeline Plugin    │
                        │  输入: 交易所 REST API   │
                        │  输出: Dict[str, DF]     │
                        │  事件: data_pipeline.    │
                        │        ohlcv_ready       │
                        └───────────┬─────────────┘
                                    │
                    Dict[str, pd.DataFrame]
                    {"H4": DF, "H1": DF, "M15": DF}
                    每个DF: DatetimeIndex + [open,high,low,close,volume] float64
                                    │
                        ┌───────────▼─────────────┐
                        │  OrchestratorPlugin     │
                        │  (事件桥梁)              │
                        │  订阅: ohlcv_ready       │
                        │  调用: WyckoffEngine     │
                        └───────────┬─────────────┘
                                    │
                                    ▼
            ┌───────────────────────────────────────────┐
            │         WyckoffEngine.process_market_data │
            │         (唯一信号路径)                     │
            │                                           │
            │  ┌──────────────────────────────────┐     │
            │  │ 阶段1: 感知层 _run_perception    │     │
            │  │ 输入: Dict[str, DF]               │     │
            │  │ 输出: PerceptionResult            │     │
            │  │                                    │     │
            │  │ ① RegimeDetector.detect_regime     │     │
            │  │   DF → {regime, confidence}        │     │
            │  │ ② TRDetector.detect_trading_range  │     │
            │  │   DF → TradingRangeInfo            │     │
            │  │ ③ FVGDetector.detect_fvg_gaps      │     │
            │  │   DF → List[FVGSignal]             │     │
            │  │ ④ BreakoutValidator.detect          │     │
            │  │   DF+TR → BreakoutInfo             │     │
            │  │ ⑤ PinBodyAnalyzer.analyze           │     │
            │  │   DF → PinBodySummary              │     │
            │  │ ⑥ AnomalyValidator.validate         │     │
            │  │   DF → List[AnomalyEvent]          │     │
            │  └──────────────┬───────────────────┘     │
            │                 │ PerceptionResult         │
            │  ┌──────────────▼───────────────────┐     │
            │  │ 阶段2: 融合层 _run_fusion        │     │
            │  │ 输入: Dict[str,DF]+Perception     │     │
            │  │ 输出: FusionResult                │     │
            │  │                                    │     │
            │  │ ① PeriodWeightFilter.get_weights   │     │
            │  │   regime → Dict[TF, weight]        │     │
            │  │ ② ConflictResolver.resolve          │     │
            │  │   TF_states → List[Conflict]       │     │
            │  │ ③ MicroEntryValidator.validate      │     │
            │  │   M15+M5+breakout → EntryValidation│     │
            │  └──────────────┬───────────────────┘     │
            │                 │ FusionResult              │
            │  ┌──────────────▼───────────────────┐     │
            │  │ 阶段3: 状态机 _run_state_machine │     │
            │  │ 输入: DF+Perception+Fusion        │     │
            │  │ 输出: WyckoffStateResult          │     │
            │  │                                    │     │
            │  │ 每个TF → 独立StateMachine实例     │     │
            │  │ 主TF结果 + 辅TF参考 → 最终状态   │     │
            │  │ 转换守卫检查 parent→child          │     │
            │  │ 证据链 StateEvidence 保持全流程   │     │
            │  └──────────────┬───────────────────┘     │
            │                 │ WyckoffStateResult        │
            │  ┌──────────────▼───────────────────┐     │
            │  │ 阶段4: 决策 _generate_decision   │     │
            │  │ 输入: Perception+Fusion+State     │     │
            │  │ 输出: TradingDecision             │     │
            │  │                                    │     │
            │  │ 信号映射 + 置信度计算 + 推理链   │     │
            │  │ 熔断器检查                         │     │
            │  └──────────────┬───────────────────┘     │
            └─────────────────┼───────────────────────┘
                              │
                   TradingDecision + EngineEvents
                              │
                ┌─────────────▼───────────────┐
                │  OrchestratorPlugin         │
                │  发布事件: trading.signal    │
                │  payload: {                  │
                │    symbol, signal, confidence│
                │    wyckoff_state, phase,     │
                │    evidences, entry_price,   │
                │    stop_loss, take_profit,   │
                │    reasoning, df             │
                │  }                           │
                └─────────────┬───────────────┘
                              │
                ┌─────────────▼───────────────┐
                │  PositionManagerPlugin      │
                │  订阅: trading.signal        │
                │                              │
                │  ① 检查现有持仓              │
                │  ② 风险检查(仓位/熔断)       │
                │  ③ 生成 OrderRequest          │
                │  ④ 调用 ExchangeExecutor     │
                │  ⑤ 发布 position.opened      │
                └─────────────┬───────────────┘
                              │
                     OrderRequest
                              │
                ┌─────────────▼───────────────┐
                │  ExchangeExecutor           │
                │  paper_trading=true:         │
                │    → 模拟撮合 → OrderResult  │
                │  paper_trading=false:        │
                │    → ccxt下单 → OrderResult  │
                └─────────────────────────────┘
```

---

## 三、事件目录

| 事件名称 | 发布者 | payload类型 | 订阅者 |
|---|---|---|---|
| `data_pipeline.ohlcv_ready` | DataPipelinePlugin | `{symbol: str, timeframes: List[str], data: Dict[str, DF]}` | OrchestratorPlugin |
| `market_regime.detected` | OrchestratorPlugin（代发） | `{symbol, regime, confidence, details}` | Dashboard |
| `trading.signal` | **OrchestratorPlugin** | `{symbol, signal: TradingSignal, confidence, wyckoff_state, phase, evidences: List[StateEvidence], entry_price, stop_loss, take_profit, reasoning: List[str], df: DF}` | **PositionManagerPlugin** |
| `position.opened` | PositionManagerPlugin | `Position.to_dict()` | OrchestratorPlugin, MistakeBook, Dashboard |
| `position.closed` | PositionManagerPlugin | `TradeResult.to_dict()` | OrchestratorPlugin, MistakeBook, Dashboard |
| `position.updated` | PositionManagerPlugin | `{symbol, unrealized_pnl, trailing_stop}` | Dashboard |
| `position.partial_close` | PositionManagerPlugin | `{...TradeResult, remaining_size}` | Dashboard |
| `market.price_update` | DataPipelinePlugin | `{symbol, price, timestamp}` | PositionManagerPlugin |
| `risk.circuit_breaker_tripped` | CircuitBreaker | `{reason, cooldown_seconds}` | OrchestratorPlugin（阻止新信号） |
| `evolution.cycle_complete` | EvolutionPlugin | `{generation, best_fitness, best_config}` | Dashboard |
| `system.shutdown` | WyckoffApp | `{}` | PositionManagerPlugin（强制平仓） |

**关键修复**：原架构中 `orchestrator.decision_made` → (空) → `position_manager` 订阅 `trading.signal` 的断链现在被消除。OrchestratorPlugin 直接发布 `trading.signal`，PositionManager 直接订阅。

---

## 四、状态机设计

### 4.1 状态全集：22+4 = 26状态

```
吸筹阶段 (13): PS → SC → AR → ST → TEST → UTA → SPRING → SO → LPS → mSOS → MSOS → JOC → BU
派发阶段 (9):  PSY → BC → AR_DIST → ST_DIST → UT → UTAD → LPSY → mSOW → MSOW
趋势状态 (2):  UPTREND, DOWNTREND
再积累/再派发 (2): RE_ACCUMULATION, RE_DISTRIBUTION
空闲 (1):     IDLE
```

### 4.2 阶段标签（Phase A-E）

```python
PHASE_MAP = {
    # 吸筹阶段
    "PS": "A", "SC": "A", "AR": "A", "ST": "A",
    "TEST": "B", "UTA": "B", "SPRING": "C", "SO": "C",
    "LPS": "C", "mSOS": "C",
    "MSOS": "D", "JOC": "D",
    "BU": "E",
    # 派发阶段
    "PSY": "A", "BC": "A", "AR_DIST": "A", "ST_DIST": "A",
    "UT": "B", "UTAD": "C",
    "LPSY": "C", "mSOW": "D",
    "MSOW": "D",
    # 特殊
    "IDLE": "IDLE", "UPTREND": "MARKUP",
    "DOWNTREND": "MARKDOWN",
    "RE_ACCUMULATION": "B",  # 在上升趋势中的B阶段
    "RE_DISTRIBUTION": "B",  # 在下降趋势中的B阶段
}
```

### 4.3 转换守卫（Parent-Child强制）

```python
# 状态定义中已有 parent_states 字段，但当前代码未强制检查
# 新设计：转换守卫作为硬约束

class TransitionGuard:
    """转换守卫 — 只允许合法的父→子转换"""

    # 合法转换表：from_state → Set[to_state]
    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        "IDLE":      {"PS", "SC", "PSY", "BC"},  # 可以进入吸筹或派发Phase A
        "PS":        {"SC", "AR"},
        "SC":        {"AR", "ST", "TEST"},
        "AR":        {"ST", "TEST", "UTA"},
        "ST":        {"TEST", "SPRING", "SO", "LPS"},
        "TEST":      {"LPS", "mSOS", "SPRING", "SO"},
        "UTA":       {"TEST", "LPS"},
        "SPRING":    {"LPS", "mSOS", "TEST"},  # Spring后可回TEST(失败)
        "SO":        {"LPS", "mSOS", "TEST"},
        "LPS":       {"mSOS", "MSOS"},
        "mSOS":      {"MSOS", "JOC"},
        "MSOS":      {"JOC", "BU"},
        "JOC":       {"BU"},
        "BU":        {"UPTREND"},
        # 派发
        "PSY":       {"BC", "AR_DIST"},
        "BC":        {"AR_DIST", "ST_DIST", "UT"},
        "AR_DIST":   {"ST_DIST", "UT", "UTAD"},
        "ST_DIST":   {"UT", "UTAD", "LPSY"},
        "UT":        {"UTAD", "LPSY"},
        "UTAD":      {"LPSY"},
        "LPSY":      {"mSOW", "MSOW"},
        "mSOW":      {"MSOW"},
        "MSOW":      {"DOWNTREND"},
        # 趋势 → 再积累/再派发
        "UPTREND":   {"RE_ACCUMULATION", "PSY"},
        "DOWNTREND": {"RE_DISTRIBUTION", "PS", "SC"},
        # 再积累/再派发 → 恢复趋势或反转
        "RE_ACCUMULATION":  {"UPTREND", "PSY"},  # 继续上涨 或 转派发
        "RE_DISTRIBUTION":  {"DOWNTREND", "PS"},  # 继续下跌 或 转吸筹
    }

    @staticmethod
    def is_valid_transition(from_state: str, to_state: str) -> bool:
        valid = TransitionGuard.VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid

    @staticmethod
    def check_prerequisite_evidence(
        to_state: str,
        evidence_chain: List[StateEvidence],
        critical_levels: Dict[str, float],
    ) -> bool:
        """检查前置证据是否充足
        例如：进入AR前必须有SC_LOW被记录
        """
        prerequisites = {
            "AR":   lambda: "SC_LOW" in critical_levels,
            "ST":   lambda: "SC_LOW" in critical_levels,
            "SPRING": lambda: "SC_LOW" in critical_levels,
            "mSOS": lambda: any(e.evidence_type == "support_strength" for e in evidence_chain),
            "JOC":  lambda: "AR_HIGH" in critical_levels or "CREEK" in critical_levels,
            "AR_DIST": lambda: "BC_HIGH" in critical_levels,
            "UT":   lambda: "BC_HIGH" in critical_levels,
            "UTAD": lambda: "BC_HIGH" in critical_levels,
        }
        check = prerequisites.get(to_state)
        if check is None:
            return True  # 无前置要求
        return check()
```

### 4.4 每TF独立实例

```python
class WyckoffStateMachineV2:
    """每个时间框架拥有独立的状态机实例"""

    def __init__(self, timeframe: str, config: StateConfig) -> None:
        self.timeframe = timeframe
        self.config = config
        self.current_state = "IDLE"
        self.phase = "IDLE"
        self.direction = StateDirection.IDLE
        self.evidence_chain: List[StateEvidence] = []
        self.critical_levels: Dict[str, float] = {}
        self.state_history: List[StateTransition] = []
        self.bars_in_state: int = 0

        # 检测器（Mixin方式保留）
        self._accum_detector = AccumulationDetectorMixin()
        self._dist_detector = DistributionDetectorMixin()

    def process_candle(self, candle: pd.Series, context: Dict[str, Any]) -> WyckoffStateResult:
        """处理单根K线，返回完整的结果（包含证据链）"""
        # 1. 运行所有检测器
        candidates = self._detect_all_states(candle, context)
        # 2. 过滤：只保留合法转换
        valid = [c for c in candidates
                 if TransitionGuard.is_valid_transition(self.current_state, c.state_name)
                 and TransitionGuard.check_prerequisite_evidence(
                     c.state_name, self.evidence_chain, self.critical_levels)]
        # 3. 选择最佳
        if valid:
            best = max(valid, key=lambda c: c.confidence)
            if best.confidence > self.config.STATE_MIN_CONFIDENCE:
                self._transition_to(best)
        # 4. 构建结果（证据链贯穿）
        return WyckoffStateResult(
            current_state=self.current_state,
            phase=PHASE_MAP.get(self.current_state, "IDLE"),
            direction=self.direction,
            confidence=self.state_confidences.get(self.current_state, 0.0),
            intensity=self.state_intensities.get(self.current_state, 0.0),
            evidences=self.evidence_chain[-20:],  # 保留最近20条证据
            signal=self._derive_signal(),
            signal_strength=self._derive_signal_strength(),
            state_changed=(self._state_changed_this_bar),
            previous_state=self._previous_state,
            heritage_score=self._heritage_score,
            critical_levels=dict(self.critical_levels),
        )
```

### 4.5 证据链全流程保持

```
AccumulationDetector.detect_sc()
    → List[StateEvidence] （volume_ratio, price_action, context, trend）
        → StateMachineV2.evidence_chain.extend(evidences)
            → WyckoffStateResult.evidences
                → TradingDecision.context.evidences （追加到reasoning）
                    → trading.signal 事件 payload.evidences
                        → API 响应 JSON
                        → MistakeBook 记录（带完整证据链）
```

### 4.6 再积累/再派发判定

```python
def _detect_re_accumulation(self, candle: pd.Series, context: Dict) -> Optional[StateDetectionResult]:
    """在上升趋势中检测再积累
    条件：
    1. 当前处于 UPTREND
    2. 价格回调但不跌破前一波LPS
    3. 成交量收缩
    4. 形成更高的支撑
    """
    if self.current_state != "UPTREND":
        return None
    # ... 检测逻辑，返回 StateDetectionResult

def _detect_re_distribution(self, candle: pd.Series, context: Dict) -> Optional[StateDetectionResult]:
    """在下降趋势中检测再派发
    条件：
    1. 当前处于 DOWNTREND
    2. 价格反弹但不突破前一波LPSY
    3. 成交量放大
    4. 形成更低的阻力
    """
    if self.current_state != "DOWNTREND":
        return None
    # ... 检测逻辑
```

---

## 五、进化管线设计

### 5.1 逐bar回测适配器

```python
class BarByBarBacktester:
    """逐K线回测器 — 使用 WyckoffEngine 的 process_bar() 接口"""

    def __init__(self, engine: WyckoffEngine, trade_config: Dict[str, Any]) -> None:
        self.engine = engine
        self.max_positions = trade_config.get("max_positions", 1)
        self.risk_per_trade = trade_config.get("risk_per_trade", 0.02)
        self.slippage = trade_config.get("slippage", 0.001)

    def run(self, data_dict: Dict[str, pd.DataFrame],
            start_bar: int, end_bar: int) -> BacktestResult:
        """从 start_bar 到 end_bar 逐bar运行引擎

        关键：
        - warmup期（前50根K线）只跑引擎不开仓
        - 每根K线调用 engine.process_bar()
        - 按信号开平仓，记录每笔交易
        """
        self.engine.reset()
        trades: List[BacktestTrade] = []
        open_position: Optional[Dict] = None
        equity_curve: List[float] = [10000.0]

        primary_tf = self._get_primary_tf(data_dict)
        total_bars = len(data_dict[primary_tf])

        for bar_idx in range(start_bar, min(end_bar, total_bars)):
            # 构建截止当前bar的数据切片
            sliced = {tf: df.iloc[:bar_idx+1] for tf, df in data_dict.items()}
            if len(sliced[primary_tf]) < 50:  # warmup
                continue

            signal = self.engine.process_bar("BTC/USDT", sliced)

            current_price = float(data_dict[primary_tf].iloc[bar_idx]["close"])

            # 管理持仓
            if open_position:
                # 检查止损/止盈
                trade = self._check_exit(open_position, bar_idx, current_price, signal)
                if trade:
                    trades.append(trade)
                    open_position = None

            # 开仓
            if not open_position and signal.signal != TradingSignal.NEUTRAL:
                if signal.confidence >= 0.6:
                    open_position = self._open(signal, bar_idx, current_price)

            # 更新权益曲线
            equity = self._calc_equity(equity_curve[-1], open_position, current_price)
            equity_curve.append(equity)

        # 强制平掉未关闭持仓
        if open_position:
            trades.append(self._force_close(open_position, end_bar-1,
                          float(data_dict[primary_tf].iloc[min(end_bar-1, total_bars-1)]["close"])))

        return self._calc_metrics(trades, equity_curve)
```

### 5.2 评估器接口

```python
class IEvaluator(Protocol):
    """评估器协议 — GA 和 WFA 都通过此接口评估配置"""
    def evaluate(self, config: Dict[str, Any]) -> BacktestResult: ...

class StandardEvaluator:
    """标准评估器 — 封装 BarByBarBacktester"""

    def __init__(self, data_dict: Dict[str, pd.DataFrame],
                 start_bar: int, end_bar: int) -> None:
        self.data_dict = data_dict
        self.start_bar = start_bar
        self.end_bar = end_bar

    def evaluate(self, config: Dict[str, Any]) -> BacktestResult:
        engine = WyckoffEngine(config)
        backtester = BarByBarBacktester(engine, config.get("trading", {}))
        return backtester.run(self.data_dict, self.start_bar, self.end_bar)
```

### 5.3 GA集成

```python
class GeneticAlgorithm:
    """遗传算法 — 真正会运行的版本"""

    def __init__(self, param_space: Dict[str, Tuple[float, float, float]],
                 population_size: int = 20,
                 elite_count: int = 4,
                 mutation_rate: float = 0.2,
                 crossover_rate: float = 0.7) -> None:
        self.param_space = param_space  # {param_name: (min, max, step)}
        self.population_size = population_size
        self.elite_count = elite_count
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.population: List[GAIndividual] = []
        self.generation = 0
        self.best_ever: Optional[GAIndividual] = None

    def initialize_population(self) -> List[GAIndividual]:
        """随机初始化种群"""
        population = []
        for _ in range(self.population_size):
            config = {}
            for param, (lo, hi, step) in self.param_space.items():
                steps = int((hi - lo) / step)
                config[param] = lo + random.randint(0, steps) * step
            individual = GAIndividual(
                config=config, fitness=0.0,
                generation=0, config_hash=self._hash(config))
            population.append(individual)
        self.population = population
        return population

    def fitness_function(self, result: BacktestResult) -> float:
        """适应度函数 — 综合多指标"""
        if result.total_trades < 5:
            return 0.0
        return (
            result.sharpe_ratio * 0.3
            + result.win_rate * 0.2
            + result.profit_factor * 0.2
            + (1.0 - result.max_drawdown) * 0.2
            + min(1.0, result.total_trades / 30) * 0.1  # 交易频率奖励
        )

    def crossover(self, a: GAIndividual, b: GAIndividual) -> GAIndividual:
        """均匀交叉"""
        child_config = {}
        for param in self.param_space:
            child_config[param] = a.config[param] if random.random() < 0.5 else b.config[param]
        return GAIndividual(
            config=child_config, fitness=0.0,
            generation=self.generation + 1,
            config_hash=self._hash(child_config))

    def mutate(self, ind: GAIndividual,
               mistake_patterns: Optional[List] = None) -> GAIndividual:
        """定向变异 — 结合错题本的失败模式"""
        config = dict(ind.config)
        for param, (lo, hi, step) in self.param_space.items():
            if random.random() < self.mutation_rate:
                # 错题本定向：如果有对应参数的错误模式，偏向修正方向
                direction = self._get_mutation_direction(param, mistake_patterns)
                delta = direction * step * random.randint(1, 3)
                config[param] = max(lo, min(hi, config[param] + delta))
        return GAIndividual(
            config=config, fitness=0.0,
            generation=self.generation + 1,
            config_hash=self._hash(config))

    def evolve_generation(self, evaluator: IEvaluator) -> GAIndividual:
        """演化一代"""
        # 1. 评估所有个体
        for ind in self.population:
            if ind.backtest_result is None:
                ind.backtest_result = evaluator.evaluate(ind.config)
                ind.fitness = self.fitness_function(ind.backtest_result)

        # 2. 排序（精英保留）
        self.population.sort(key=lambda x: x.fitness, reverse=True)
        elites = self.population[:self.elite_count]

        # 3. 选择（锦标赛）
        parents = self._tournament_select(self.population, self.population_size - self.elite_count)

        # 4. 交叉 + 变异
        offspring = []
        for i in range(0, len(parents) - 1, 2):
            if random.random() < self.crossover_rate:
                child = self.crossover(parents[i], parents[i+1])
            else:
                child = GAIndividual(config=dict(parents[i].config), fitness=0.0,
                                     generation=self.generation+1,
                                     config_hash=self._hash(parents[i].config))
            child = self.mutate(child)
            offspring.append(child)

        # 5. 组合新种群
        self.population = elites + offspring
        self.generation += 1

        # 6. 更新全局最优
        current_best = self.population[0]
        if self.best_ever is None or current_best.fitness > self.best_ever.fitness:
            self.best_ever = current_best

        return current_best
```

### 5.4 WFA协议

```python
class WFAValidator:
    """Walk-Forward Analysis 验证器"""

    def __init__(self, train_bars: int = 1440,   # 60天 × 24bar/天(H1)
                 test_bars: int = 480,            # 20天
                 step_bars: int = 240) -> None:   # 10天
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.step_bars = step_bars

    def generate_windows(self, total_bars: int) -> List[WFAWindow]:
        """生成滚动窗口序列"""
        windows = []
        start = 0
        while start + self.train_bars + self.test_bars <= total_bars:
            windows.append(WFAWindow(
                train_start=start,
                train_end=start + self.train_bars,
                test_start=start + self.train_bars,
                test_end=start + self.train_bars + self.test_bars,
            ))
            start += self.step_bars
        return windows

    def validate(self, config: Dict[str, Any],
                 data_dict: Dict[str, pd.DataFrame],
                 backtester_factory: Callable) -> Tuple[bool, float]:
        """验证配置的跨窗口稳定性

        Returns:
            (accepted: bool, oos_score: float)
        """
        windows = self.generate_windows(len(next(iter(data_dict.values()))))
        if len(windows) < 3:
            return False, 0.0

        oos_scores = []
        for w in windows:
            # 训练集评估
            train_eval = StandardEvaluator(data_dict, w.train_start, w.train_end)
            train_result = train_eval.evaluate(config)
            w.train_result = train_result

            # 测试集评估
            test_eval = StandardEvaluator(data_dict, w.test_start, w.test_end)
            test_result = test_eval.evaluate(config)
            w.test_result = test_result

            if train_result.total_trades >= 3 and test_result.total_trades >= 1:
                oos_scores.append(test_result.sharpe_ratio)

        if len(oos_scores) < 2:
            return False, 0.0

        avg_oos = float(np.mean(oos_scores))
        stability = 1.0 - float(np.std(oos_scores)) / (abs(avg_oos) + 1e-6)

        # 接受条件：OOS平均夏普 > 0.3 且 稳定性 > 0.5
        accepted = avg_oos > 0.3 and stability > 0.5
        return accepted, avg_oos
```

### 5.5 向量化/并行化策略

```
优先级：
1. 感知层向量化：RegimeDetector/TRDetector 已用 pandas 向量化运算 [保留]
2. GA个体并行评估：每个个体的 evaluate() 互不依赖
   → 使用 concurrent.futures.ProcessPoolExecutor(max_workers=4)
3. WFA窗口并行：每个窗口的 train+test 独立
   → 使用 ProcessPoolExecutor
4. 不做：逐bar回测无法并行（每bar依赖前bar状态）
```

---

## 六、执行管线设计

### 6.1 Decision → Risk → Position → Exchange

```python
# OrchestratorPlugin._on_data_ready() 中：
def _on_data_ready(self, event_name: str, data: Dict[str, Any]) -> None:
    symbol = data["symbol"]
    data_dict = data["data"]
    timeframes = data["timeframes"]

    # 1. 调用统一引擎
    decision, events = self._engine.process_market_data(symbol, timeframes, data_dict)

    # 2. 熔断检查
    if self._circuit_breaker_active:
        decision = TradingDecision(signal=TradingSignal.NEUTRAL, ...)
        return

    # 3. 发布 trading.signal（PositionManager订阅）
    self.emit_event("trading.signal", {
        "symbol": symbol,
        "signal": decision.signal,
        "confidence": decision.confidence,
        "wyckoff_state": decision.context.wyckoff_state,
        "phase": events.new_state,  # 阶段信息
        "evidences": [e.__dict__ for e in decision.context.evidences] if hasattr(decision.context, 'evidences') else [],
        "entry_price": decision.entry_price,
        "stop_loss": decision.stop_loss,
        "take_profit": decision.take_profit,
        "reasoning": decision.reasoning,
        "df": data_dict.get("H4"),  # 用于止损计算
        "account_balance": self._get_account_balance(),
    })
```

### 6.2 PositionManager → ExchangeExecutor 接通

```python
# PositionManagerPlugin._try_open_position() 修改：
def _try_open_position(self, ...):
    # ... 现有逻辑保持 ...
    position = self._manager.open_position(...)

    if position:
        self._open_count += 1
        self.emit_event("position.opened", position.to_dict())

        # 新增：调用 ExchangeExecutor 实际下单
        exchange = self.get_plugin("exchange_connector")
        if exchange and exchange.is_active:
            order_request = OrderRequest(
                symbol=symbol,
                side="BUY" if side == PositionSide.LONG else "SELL",
                order_type="MARKET",
                size=position.size,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
            )
            result = exchange.execute(order_request)
            if not result.success:
                logger.error("下单失败: %s", result.error_message)
                # 回滚内部持仓
                self._manager.force_close(symbol, position.entry_price)
```

### 6.3 Paper/Live同路径

```python
class ExchangeExecutor:
    def execute(self, request: OrderRequest) -> OrderResult:
        if self.paper_trading:
            return self._paper_execute(request)
        else:
            return self._live_execute(request)

    def _paper_execute(self, request: OrderRequest) -> OrderResult:
        """模拟执行 — 立即成交，加滑点"""
        slippage = request.price * 0.001 if request.price else 0
        filled_price = (request.price or self._last_price) + slippage
        # ... 记录到 paper_positions
        return OrderResult(success=True, order_id=str(self._order_count),
                          filled_price=filled_price, filled_size=request.size,
                          commission=filled_price * request.size * 0.001,
                          timestamp=datetime.now(timezone.utc))

    def _live_execute(self, request: OrderRequest) -> OrderResult:
        """实盘执行 — ccxt下单"""
        # 复用现有 place_order 逻辑
        # ...
```

---

## 七、配置模式

### 7.1 分层结构

```yaml
# config.yaml
# ========== 系统级 ==========
paper_trading: true
symbols: ["BTC/USDT"]
timeframes: ["H4", "H1", "M15"]
historical_days: 90
processing_interval: 60

# ========== 插件级 ==========
plugins:
  market_regime:
    atr_period: 14
    adx_period: 14
    regime_thresholds:
      trending_adx: 25
      volatile_atr_ratio: 1.5

  wyckoff_engine:
    primary_timeframe: "H4"

    state_machine:                        # ← 可被进化修改
      SPRING_FAILURE_BARS: 5
      STATE_TIMEOUT_BARS: 20
      STATE_MIN_CONFIDENCE: 0.35
      PATH_SELECTION_THRESHOLD: 0.35
      STATE_SWITCH_HYSTERESIS: 0.05
      DIRECTION_SWITCH_PENALTY: 0.3

    trading:
      trading_mode: "spot"                # spot | futures
      leverage: 1
      allow_shorting: false
      risk_per_trade: 0.02
      min_confidence: 0.6

  position_manager:
    max_positions: 3
    min_confidence: 0.65
    stop_loss:
      method: "atr"                       # atr | percent | support
      atr_multiplier: 2.0
      max_loss_pct: 0.05
    take_profit:
      method: "rr_ratio"
      risk_reward: 2.5
    trailing_stop:
      activation_pct: 0.03
      trail_pct: 0.015

  exchange_connector:
    default_exchange: "binance"
    initial_balance: 10000.0

  evolution:
    enabled: false                        # 只在 --mode=evolution 时启用
    population_size: 20
    generations: 10
    elite_count: 4
    mutation_rate: 0.2
    crossover_rate: 0.7
    wfa:
      train_bars: 1440
      test_bars: 480
      step_bars: 240
    param_space:                          # ← 可进化参数及范围
      STATE_MIN_CONFIDENCE: [0.2, 0.8, 0.05]
      STATE_TIMEOUT_BARS: [10, 40, 5]
      SPRING_FAILURE_BARS: [3, 10, 1]
      PATH_SELECTION_THRESHOLD: [0.2, 0.8, 0.05]
      STATE_SWITCH_HYSTERESIS: [0.02, 0.15, 0.01]
      DIRECTION_SWITCH_PENALTY: [0.1, 0.5, 0.05]

  # ========== 硬编码（不可配置） ==========
  # - 吸筹13状态 + 派发9状态的名称和层级关系
  # - 转换守卫的合法转换表
  # - OHLCV DataFrame格式
  # - 事件名称字符串
```

### 7.2 配置分类

| 类别 | 可配置 | 可进化 | 示例 |
|------|-------|-------|------|
| 系统参数 | ✅ YAML | ❌ | symbols, timeframes, paper_trading |
| 感知阈值 | ✅ YAML | ❌ | atr_period, adx_period |
| 状态机参数 | ✅ YAML | ✅ GA | STATE_MIN_CONFIDENCE, SPRING_FAILURE_BARS |
| 交易参数 | ✅ YAML | ❌ | risk_per_trade, max_positions |
| 状态定义 | ❌ 硬编码 | ❌ | 22状态名称、parent_states |
| 证据权重 | ✅ YAML | ✅ GA | detect_sc中volume_weight=0.35等 |

---

## 八、实施阶段：依赖排序构建序列

### Phase 0：清理（1天）

```
任务：
1. 删除待删代码（~6200行）
   - src/plugins/orchestrator/system_orchestrator_legacy.py
   - src/plugins/orchestrator/config.py, flow.py, health.py, registry.py
   - src/plugins/evolution/archivist.py（旧版）
   - src/plugins/agent_teams/strategy_optimizer_agent.py
   - src/plugins/agent_teams/backtest_validator_agent.py
   - src/plugins/agent_teams/backtest/engine.py
   - src/plugins/agent_teams/communication/message_bus.py
   - src/plugins/agent_teams/visualization/ (全部)
   - src/plugins/agent_teams/plugin.py

2. 在 src/kernel/types.py 中添加所有新dataclass
   （PerceptionResult, FusionResult, WyckoffStateResult,
     OrderRequest, OrderResult, BarSignal, BacktestTrade,
     BacktestResult, GAIndividual, WFAWindow 等）

依赖：无
```

### Phase 1：状态机重建（3天）

```
任务：
1. 新建 src/plugins/wyckoff_state_machine/transition_guard.py
   - TransitionGuard 类
   - VALID_TRANSITIONS 表
   - check_prerequisite_evidence()

2. 重建 src/plugins/wyckoff_state_machine/state_machine_v2.py
   - WyckoffStateMachineV2 类
   - 每TF独立实例
   - 阶段标签 (Phase A-E)
   - 证据链全流程传递
   - 再积累/再派发检测

3. 重建 src/plugins/wyckoff_state_machine/distribution_detectors.py
   - 9个派发检测器与吸筹同等质量
   - 修复：所有检测器必须将证据append到evidences列表
   - 修复：所有检测器必须在高置信度时记录critical_price_levels

4. 保留 accumulation_detectors.py（仅修复evidence传递）

5. 测试：tests/plugins/test_state_machine_v2.py

依赖：Phase 0（types.py中的新类型）
```

### Phase 2：统一信号引擎重建（2天）

```
任务：
1. 重建 src/plugins/wyckoff_engine/engine.py
   - _run_perception() 返回 PerceptionResult（非Dict）
   - _run_fusion() 返回 FusionResult（非Dict）
   - _run_state_machine() 使用 StateMachineV2 per-TF
   - 新增 process_bar() 方法（逐bar接口，供进化用）
   - _generate_decision() 返回 TradingDecision（证据贯穿）

2. 修复 Phase 3 空桩：状态机决策层当前返回空字典
   填充完整逻辑，连接到 StateMachineV2

3. 测试：tests/plugins/test_wyckoff_engine.py

依赖：Phase 1（StateMachineV2）
```

### Phase 3：事件链接通（1天）

```
任务：
1. 重建 src/plugins/orchestrator/plugin.py
   - 持有 WyckoffEngine 实例
   - _on_data_ready(): 调用 engine.process_market_data()
   - 发布 trading.signal（而非 orchestrator.decision_made）
   - 消除事件断链

2. 修复 src/plugins/position_manager/plugin.py
   - _on_trading_signal() 中调用 ExchangeExecutor
   - 接通 position → exchange 路径

3. 修复 src/plugins/exchange_connector/plugin.py
   - 暴露 execute(OrderRequest) → OrderResult 接口
   - 注册事件 position.opened 后自动挂止损单

4. 测试：tests/plugins/test_signal_chain.py（端到端事件链）

依赖：Phase 2（WyckoffEngine）
```

### Phase 4：进化系统重建（3天）

```
任务：
1. 新建 src/plugins/evolution/bar_by_bar_backtester.py
   - BarByBarBacktester 类

2. 新建 src/plugins/evolution/evaluator.py
   - StandardEvaluator 类

3. 新建 src/plugins/evolution/genetic_algorithm.py
   - GeneticAlgorithm 类（真正的crossover/mutate/select）
   - 与 MistakeBook 集成（定向变异）

4. 重建 src/plugins/evolution/wfa_validator.py
   - 使用 BarByBarBacktester
   - 正确的 train/test 边界

5. 重建 src/plugins/evolution/plugin.py
   - 进化主循环
   - GA → WFA → 配置应用

6. 重建 run_evolution.py
   - 使用新 GA + WFA

7. 测试：tests/plugins/test_evolution.py

依赖：Phase 2（WyckoffEngine.process_bar()）
```

### Phase 5：API层重建（2天）

```
任务：
1. 重建 src/api/app.py
   - 通过 PluginManager 获取插件引用（非私有属性访问）
   - JWT 认证（简单 bearer token）
   - WebSocket 健壮化（心跳 + 重连）
   - RESTful 端点通过插件公共API

2. 端点设计：
   GET  /api/v1/status          → orchestrator.get_system_status()
   GET  /api/v1/positions       → position_manager.get_all_positions()
   GET  /api/v1/trades          → position_manager.get_trade_history()
   GET  /api/v1/state           → engine.get_current_state()
   POST /api/v1/evolution/start → evolution.start_evolution()
   POST /api/v1/evolution/stop  → evolution.stop_evolution()
   WS   /ws/signals             → 实时 trading.signal 事件流

3. 测试：tests/api/test_api.py

依赖：Phase 3（信号链完整）
```

### Phase 6：权重系统修复（1天）

```
任务：
1. 修复 src/plugins/weight_system/period_weight_filter.py
   - regime权重键名匹配实际regime字符串
   - 删除死方法

2. 修复 src/plugins/self_correction/workflow.py
   - 连接新 GA + WFA
   - MistakeBook → GA.mutate() 的 mistake_patterns 传递

3. 测试：tests/plugins/test_weight_system.py

依赖：Phase 4（新GA）
```

### 总体时间线

| 阶段 | 天数 | 累计 | 关键产出 |
|------|------|------|---------|
| Phase 0: 清理+类型 | 1 | 1 | 干净代码库 + 完整类型系统 |
| Phase 1: 状态机 | 3 | 4 | 22+4状态 + 转换守卫 + 证据链 |
| Phase 2: 信号引擎 | 2 | 6 | 唯一信号路径 + process_bar |
| Phase 3: 事件链 | 1 | 7 | 端到端：数据→信号→持仓→交易所 |
| Phase 4: 进化系统 | 3 | 10 | 逐bar回测 + GA + WFA |
| Phase 5: API | 2 | 12 | RESTful + WebSocket + 认证 |
| Phase 6: 权重修复 | 1 | 13 | 完整闭环 |

---

## 九、文件/目录结构

```
src/
├── kernel/                          [保留 — 不修改]
│   ├── types.py                     ← 追加新 dataclass（~200行）
│   ├── base_plugin.py               [不变]
│   ├── plugin_manifest.py           [不变]
│   ├── plugin_manager.py            [不变]
│   ├── event_bus.py                 [不变]
│   └── config_system.py             [不变]
│
├── plugins/
│   ├── wyckoff_state_machine/
│   │   ├── state_machine_v2.py      ★ 新建：WyckoffStateMachineV2
│   │   ├── transition_guard.py      ★ 新建：转换守卫
│   │   ├── accumulation_detectors.py [修复：证据传递]
│   │   ├── distribution_detectors.py ★ 重建：9个检测器全面重写
│   │   ├── state_machine_core.py    → 重命名为 state_machine_core_legacy.py
│   │   ├── enhanced_state_machine.py → 重命名为 enhanced_state_machine_legacy.py
│   │   ├── context_builder.py       [保留]
│   │   ├── plugin.py                [修改：使用V2]
│   │   └── wyckoff_state_machine_legacy.py [保留 — 进化对照基准]
│   │
│   ├── wyckoff_engine/
│   │   ├── engine.py                ★ 重建：统一信号引擎V2
│   │   ├── plugin.py                [修改：暴露process_bar]
│   │   └── engine_legacy.py         → 旧engine.py重命名保留
│   │
│   ├── orchestrator/
│   │   ├── plugin.py                ★ 重建：事件桥梁+WyckoffEngine
│   │   └── plugin-manifest.yaml     [不变]
│   │   （删除: system_orchestrator_legacy.py, config.py,
│   │           flow.py, health.py, registry.py）
│   │
│   ├── position_manager/
│   │   ├── plugin.py                [修复：接通ExchangeExecutor]
│   │   ├── position_manager.py      [保留]
│   │   ├── stop_loss_executor.py    [保留]
│   │   ├── signal_exit_logic.py     [保留]
│   │   └── types.py                 [保留]
│   │
│   ├── exchange_connector/
│   │   ├── plugin.py                [修复：暴露execute()接口]
│   │   └── exchange_executor.py     [修复：OrderRequest/Result类型化]
│   │
│   ├── evolution/
│   │   ├── plugin.py                ★ 重建：进化主循环
│   │   ├── bar_by_bar_backtester.py ★ 新建：逐bar回测器
│   │   ├── evaluator.py             ★ 新建：标准评估器
│   │   ├── genetic_algorithm.py     ★ 新建：遗传算法
│   │   ├── wfa_validator.py         ★ 新建：WFA验证器（替代旧wfa_backtester.py）
│   │   ├── evolution_storage.py     [保留]
│   │   ├── wfa_backtester.py        → 重命名为 wfa_backtester_legacy.py
│   │   └── weight_variator_legacy.py [保留 — 仅供参考]
│   │   （删除: archivist.py）
│   │
│   ├── perception/                  [保留 — 不修改]
│   ├── market_regime/               [保留 — 不修改]
│   ├── pattern_detection/           [保留 — 不修改]
│   ├── signal_validation/           [保留 — 不修改]
│   ├── risk_management/             [保留 — 不修改]
│   ├── data_pipeline/               [保留 — 不修改]
│   ├── weight_system/               [修复：键名匹配]
│   ├── self_correction/             [修复：连接新GA]
│   ├── dashboard/                   [延后]
│   └── agent_teams/                 [延后 + 删除死文件]
│
├── api/
│   └── app.py                       ★ 重建：RESTful + 认证 + 健壮WS
│
└── utils/                           [保留 — 不修改]

tests/
├── plugins/
│   ├── test_state_machine_v2.py     ★ 新建
│   ├── test_transition_guard.py     ★ 新建
│   ├── test_wyckoff_engine.py       ★ 新建
│   ├── test_signal_chain.py         ★ 新建（端到端事件链测试）
│   ├── test_bar_by_bar_backtest.py  ★ 新建
│   ├── test_genetic_algorithm.py    ★ 新建
│   ├── test_wfa_validator.py        ★ 新建
│   └── test_evolution_pipeline.py   ★ 新建
└── api/
    └── test_api.py                  ★ 新建
```

### 新增文件清单（10个 → 已完成全部核心文件）

| 文件 | 预估行数 | 实际行数 | 状态 |
|------|---------|---------|------|
| `state_machine_v2.py` | ~600 | 801 | ✅ P1 |
| `transition_guard.py` | ~150 | 119 | ✅ P1 |
| `bar_by_bar_backtester.py` | ~300 | ~500 | ✅ P4 |
| `evaluator.py` | ~100 | 190 | ✅ P4 |
| `genetic_algorithm.py` | ~400 | ~460 | ✅ P4 |
| `wfa_validator.py` | ~200 | 366 | ✅ P4 |
| `anti_overfit.py` | — | ~260 | ✅ P4（计划外新增） |
| `test_state_machine_v2.py` | ~400 | — | ✅ P1 |
| `test_signal_chain.py` | ~200 | — | ✅ P3 |
| `test_genetic_algorithm.py` | ~300 | ~100 | ✅ P4 |
| `test_wfa_validator.py` | ~200 | ~100 | ✅ P4 |
| `test_evolution_pipeline.py` | — | ~100 | ✅ P4（计划外新增） |
| `test_anti_overfit.py` | — | ~160 | ✅ P4（计划外新增） |

### 修改文件清单（8个）

| 文件 | 修改范围 | 内容 |
|------|---------|------|
| `kernel/types.py` | +200行 | 新增所有共享dataclass |
| `distribution_detectors.py` | 全面重写 | 9个检测器修复证据传递 |
| `wyckoff_engine/engine.py` | 全面重写 | 类型化接口 + process_bar |
| `orchestrator/plugin.py` | 重大修改 | 持有Engine + 发布trading.signal |
| `position_manager/plugin.py` | 小改 | 接通ExchangeExecutor |
| `exchange_connector/plugin.py` | 小改 | 暴露execute()接口 |
| `evolution/plugin.py` | 重大修改 | 进化主循环连接新GA |
| `api/app.py` | 全面重写 | RESTful + 认证 | ✅ P5 |

### 删除文件清单（~12个，~6200行）

| 文件 | 行数 |
|------|------|
| `orchestrator/system_orchestrator_legacy.py` | ~800 |
| `orchestrator/config.py` | ~200 |
| `orchestrator/flow.py` | ~300 |
| `orchestrator/health.py` | ~200 |
| `orchestrator/registry.py` | ~200 |
| `evolution/archivist.py` | ~400 |
| `agent_teams/strategy_optimizer_agent.py` | ~600 |
| `agent_teams/backtest_validator_agent.py` | ~500 |
| `agent_teams/backtest/engine.py` | ~800 |
| `agent_teams/communication/message_bus.py` | ~300 |
| `agent_teams/visualization/*` | ~1500 |
| `agent_teams/plugin.py` | ~400 |

---

## 附录：七大问题的解决方案映射

| 问题 | 解决方案 | 所在Phase |
|------|---------|-----------|
| 1. 两条信号路径 | WyckoffEngine 是唯一路径；实盘用 `process_market_data()`，进化用 `process_bar()`，内部逻辑完全相同 | Phase 2 |
| 2. 事件断链 | Orchestrator 直接发布 `trading.signal`，PositionManager 直接订阅 | Phase 3 |
| 3. Exchange未接通 | PositionManager 在开平仓时调用 `ExchangeExecutor.execute()` | Phase 3 |
| 4. 状态机无父子守卫 | `TransitionGuard.is_valid_transition()` + `check_prerequisite_evidence()` 作为硬约束 | Phase 1 |
| 5. 证据被丢弃 | `StateEvidence` 列表从检测器 → StateMachine → WyckoffStateResult → TradingDecision → 事件 → API 全链路传递 | Phase 1+2 |
| 6. 多TF共享实例 | `WyckoffStateMachineV2` 每个TF创建独立实例，WyckoffEngine 内部维护 `Dict[str, StateMachineV2]` | Phase 1+2 |
| 7. 无再积累/再派发 | 新增 `RE_ACCUMULATION` 和 `RE_DISTRIBUTION` 状态，在 UPTREND/DOWNTREND 中检测横盘并切入 | Phase 1 |

---

---

## 十、过拟合防护体系

### 10.1 核心原则

**小资金做大 + 5倍杠杆 = 最怕过拟合。** 过拟合的策略在实盘上会快速亏损，杠杆放大亏损速度。进化系统必须有多层防护，宁可错杀好参数，也不能让过拟合参数上实盘。

### 10.2 五层防护（由粗到细）

```
Layer 1: 最小回测长度（MBL）
  ↓ 数据够不够？不够直接拒绝
Layer 2: Walk-Forward Analysis + OOS退化率
  ↓ 样本外表现是否显著退化？
Layer 3: Deflated Sharpe Ratio（DSR）
  ↓ 考虑多重测试后，Sharpe还显著吗？
Layer 4: Monte Carlo排列检验
  ↓ 策略能否打败随机排列？
Layer 5: CPCV（定期，非每轮）
  ↓ 所有组合交叉验证的过拟合概率
```

### 10.3 Layer 1: 最小回测长度（MBL）

**作用**: 如果数据太短，任何统计指标都不可靠。直接拒绝。

```python
def minimum_backtest_length(
    target_sharpe: float,
    skewness: float = 0.0,
    kurtosis: float = 5.0,  # 加密货币典型值
    frequency: int = 1460,  # H4: 6根/天 × 243交易日
) -> int:
    """最小回测长度（根数）
    SR=1.0 → 需要约4年H4数据
    SR=2.0 → 需要约1年H4数据
    """
    if target_sharpe == 0:
        return float('inf')
    n_star = (
        1 + (1 - skewness * target_sharpe
             + (kurtosis - 1) / 4 * target_sharpe**2)
    ) / (target_sharpe**2)
    return int(np.ceil(n_star * frequency))
```

**集成点**: WFA入口检查。数据不足 → 返回 `NEEDS_MORE_DATA`，不运行进化。

### 10.4 Layer 2: OOS退化率

**作用**: 检测样本内(IS)和样本外(OOS)性能差距。退化率>40% = 过拟合风险高。

```python
def oos_degradation_ratio(wfa_windows: List[WFAWindow]) -> float:
    """OOS退化率 = 1 - (OOS_Sharpe / IS_Sharpe)
    > 0.4 = 过拟合风险高，拒绝
    > 0.6 = 几乎肯定过拟合
    """
    ratios = []
    for w in wfa_windows:
        if w.train_result and w.test_result:
            is_sharpe = w.train_result.sharpe_ratio
            oos_sharpe = w.test_result.sharpe_ratio
            if is_sharpe > 0:
                ratios.append(1.0 - oos_sharpe / is_sharpe)
    return float(np.mean(ratios)) if ratios else 1.0
```

**集成点**: `WFAValidator.validate()` 的接受条件新增 `oos_dr < 0.4`。

### 10.5 Layer 3: Deflated Sharpe Ratio（DSR）

**作用**: 测试了N个配置，最好的Sharpe可能只是运气。DSR扣除"多重测试"的膨胀。

```python
def deflated_sharpe_ratio(
    observed_sr: float,
    all_tested_srs: List[float],
    n_trades: int,
    skewness: float = 0.0,
    kurtosis: float = 5.0,
) -> float:
    """Deflated Sharpe Ratio (Bailey & De Prado, 2014)
    返回概率 [0,1]。< 0.95 = Sharpe可能是运气
    """
    N = len(all_tested_srs)
    gamma = 0.5772
    expected_max_sr = (
        (1 - gamma) * stats.norm.ppf(1 - 1/N)
        + gamma * stats.norm.ppf(1 - 1/(N * 2.71828))
    )
    sr_std = max(np.std(all_tested_srs), 1e-10)
    test_stat = (observed_sr - expected_max_sr) * np.sqrt(n_trades - 1) / sr_std
    return float(stats.norm.cdf(test_stat))
```

**集成点**: GA `fitness_function()` 中，用DSR替代原始Sharpe作为评分依据。跟踪所有测试过的Sharpe值。

### 10.6 Layer 4: Monte Carlo排列检验

**作用**: 打乱信号时序，看策略是否能打败随机。p>0.1 = 没有真正的择时能力。

```python
def monte_carlo_test(
    strategy_returns: np.ndarray,
    n_permutations: int = 1000,
) -> float:
    """返回p值。< 0.05 = 策略有真正的择时能力"""
    observed = np.mean(strategy_returns) / (np.std(strategy_returns) + 1e-10)
    perm_sharpes = []
    rng = np.random.RandomState(42)
    for _ in range(n_permutations):
        shuffled = rng.permutation(strategy_returns)
        perm_sharpes.append(np.mean(shuffled) / (np.std(shuffled) + 1e-10))
    return float(np.mean(np.array(perm_sharpes) >= observed))
```

**集成点**: WFA接受mutation后，额外运行Monte Carlo。p>0.1 → 降低mutation的fitness。

### 10.7 Layer 5: CPCV（定期验证）

**作用**: 组合清洗交叉验证。不是每轮进化都跑，而是每50轮做一次全面检查。

- 6组数据 × C(6,2)=15种组合 → 15次独立回测
- 计算PBO（过拟合概率）：PBO < 0.5 = 策略可能有真实边际
- 成本高（15次回测），所以只定期运行

**集成点**: 每50轮进化后运行。PBO > 0.5 → 回滚到上一个验证通过的配置。

---

## 十一、向量化加速策略

### 11.1 问题：数据增长导致进化变慢

随着交易时间增加，历史数据不断增长。逐bar回测如果用纯Python，速度会成瓶颈：

```
当前数据量:  ~2000根H4 × 5TF → 单次评估~4秒  → 50次评估/轮 → ~200秒/轮
1年后:       ~4000根H4 × 5TF → 单次评估~8秒  → 50次评估/轮 → ~400秒/轮
3年后:       ~8000根H4 × 5TF → 单次评估~16秒 → 50次评估/轮 → ~800秒/轮
```

### 11.2 两层加速架构

状态机**不能**完全向量化（每个状态依赖前一个状态），但可以用**两层架构**：

```
Pass 1（向量化）: 预计算所有无状态特征 → NumPy一次算完
  ATR、ADX、MA、成交量比、FVG、支撑阻力、K线物理属性
  速度：0.1ms/2000根（vs 纯Python循环 50ms）

Pass 2（Numba编译）: 运行状态机 → @njit编译为机器码
  22节点状态转换、证据积累、信号生成
  速度：0.5ms/2000根（vs 纯Python循环 50ms）

Pass 3（向量化）: 回测模拟 → NumPy计算权益曲线
  逐bar持仓、止损止盈、手续费
  速度：0.1ms/2000根（vs 纯Python循环 20ms）
```

### 11.3 Pass 1: 特征预计算

```python
def precompute_features(data_dict: Dict[str, pd.DataFrame]) -> Dict[str, np.ndarray]:
    """一次性预计算所有指标，返回numpy数组

    只计算一次，所有GA个体共用同一份特征数组。
    只有权重/阈值不同，特征值相同。
    """
    h4 = data_dict["H4"]
    close = h4["close"].values
    high = h4["high"].values
    low = h4["low"].values
    volume = h4["volume"].values

    return {
        "close": close,
        "high": high,
        "low": low,
        "volume": volume,
        "atr": _vectorized_atr(high, low, close, period=14),
        "adx": _vectorized_adx(high, low, close, period=14),
        "volume_ma20": _rolling_mean(volume, 20),
        "volume_ratio": volume / (_rolling_mean(volume, 20) + 1e-10),
        "body_ratio": np.abs(close - h4["open"].values) / (high - low + 1e-10),
        "upper_shadow": (high - np.maximum(close, h4["open"].values)) / (high - low + 1e-10),
        "lower_shadow": (np.minimum(close, h4["open"].values) - low) / (high - low + 1e-10),
    }
```

**关键优化**: 这些特征对所有GA个体都相同（特征不依赖config参数），所以每轮进化只计算一次，20个个体共用。

### 11.4 Pass 2: Numba状态机

```python
from numba import njit

@njit(cache=True)
def state_machine_numba(
    close: np.ndarray,
    volume_ratio: np.ndarray,
    atr: np.ndarray,
    lower_shadow: np.ndarray,
    # Config参数（不同GA个体不同）
    min_confidence: float,
    spring_failure_bars: int,
    direction_penalty: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Numba编译的状态机 — 比纯Python快100-500x

    返回: (states数组, confidence数组)
    """
    n = len(close)
    states = np.zeros(n, dtype=np.int32)
    confidences = np.zeros(n, dtype=np.float64)
    current_state = 0  # IDLE
    bars_in_state = 0
    sc_low = 0.0

    for i in range(50, n):  # 跳过warmup
        bars_in_state += 1
        conf = 0.0

        if current_state == 0:  # IDLE → PS/SC
            if volume_ratio[i] > 2.0 and close[i] < close[i-1]:
                current_state = 2  # SC
                sc_low = close[i]
                conf = min(volume_ratio[i] / 4.0, 1.0)
                bars_in_state = 0

        elif current_state == 2:  # SC → AR
            if close[i] > close[i-1] and bars_in_state < 10:
                current_state = 3  # AR
                conf = 0.6
                bars_in_state = 0

        # ... 其余状态转换 ...

        states[i] = current_state
        confidences[i] = conf

    return states, confidences
```

### 11.5 Pass 3: 向量化回测

```python
@njit(cache=True)
def vectorized_backtest(
    close: np.ndarray,
    signals: np.ndarray,       # 1=BUY, -1=SELL, 0=HOLD
    confidences: np.ndarray,
    atr: np.ndarray,
    min_confidence: float,
    atr_sl_mult: float = 2.0,
    commission: float = 0.001,
) -> Tuple[np.ndarray, int, int]:
    """Numba编译的回测引擎

    返回: (equity_curve, total_trades, winning_trades)
    """
    n = len(close)
    equity = np.ones(n) * 10000.0
    position = 0.0  # 0=空仓, >0=多头数量
    entry_price = 0.0
    stop_loss = 0.0
    total_trades = 0
    winning_trades = 0

    for i in range(1, n):
        equity[i] = equity[i-1]

        # 检查止损
        if position > 0 and close[i] < stop_loss:
            pnl = (close[i] - entry_price) * position
            equity[i] += pnl - abs(pnl) * commission
            total_trades += 1
            if pnl > 0:
                winning_trades += 1
            position = 0.0

        # 开仓
        if position == 0 and signals[i] == 1 and confidences[i] > min_confidence:
            risk = equity[i] * 0.02  # 2%风险
            stop_dist = atr[i] * atr_sl_mult
            position = risk / stop_dist
            entry_price = close[i]
            stop_loss = close[i] - stop_dist
            equity[i] -= close[i] * position * commission

    return equity, total_trades, winning_trades
```

### 11.6 性能预估

```
                纯Python    Numba编译    加速比
Pass 1 特征:    50ms        0.1ms       500x  (NumPy向量化)
Pass 2 状态机:  50ms        0.5ms       100x  (Numba @njit)
Pass 3 回测:    20ms        0.1ms       200x  (Numba @njit)
总计/次:        120ms       0.7ms       170x

50次评估/轮:    6秒          35ms
4核并行:       1.5秒         9ms

目标: 单轮进化 < 1秒（当前~200秒）
```

### 11.7 实施节奏

- **Phase 4（进化重建）**: 先用纯Python实现正确逻辑，确保逐bar回测能产生有意义的信号
- **Phase 4完成后**: 抽取纯数值计算部分，用Numba加速
- **不要一开始就做向量化** — 先保证正确性，再优化速度

---

## 十二、小资金复利 + 5倍杠杆仓位管理

### 12.1 核心目标

小资金做大 = **复利增长最大化 + 爆仓概率最小化**。5倍杠杆意味着20%反向波动就爆仓，所以仓位管理比信号质量更重要。

### 12.2 1/4 Kelly公式仓位

```python
def fractional_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_fraction: float = 0.25,  # 1/4 Kelly
    max_position_pct: float = 0.20,
) -> float:
    """1/4 Kelly — 牺牲25%增长率，换75%波动降低
    Full Kelly增长最快但波动巨大，不适合小账户。
    """
    if avg_loss == 0:
        return max_position_pct
    b = avg_win / abs(avg_loss)
    q = 1 - win_rate
    full_kelly = (win_rate * b - q) / b
    return min(max(0, full_kelly * kelly_fraction), max_position_pct)
```

### 12.3 ATR波动率调整仓位

```python
def volatility_adjusted_size(
    equity: float,
    risk_pct: float,         # 每笔风险占比，如0.02=2%
    entry_price: float,
    atr: float,
    atr_multiplier: float,   # 止损=ATR×此值
    max_leverage: float = 5.0,
    max_position_pct: float = 0.25,
) -> Dict[str, float]:
    """ATR波动率调整仓位
    波动大→仓位小, 波动小→仓位大, 风险暴露恒定
    """
    stop_distance = atr * atr_multiplier
    dollar_risk = equity * risk_pct
    units = dollar_risk / stop_distance
    notional = units * entry_price
    max_notional = equity * max_leverage * max_position_pct
    if notional > max_notional:
        units = max_notional / entry_price
        notional = max_notional
    return {
        "units": units,
        "notional": notional,
        "leverage_used": notional / equity,
        "stop_distance": stop_distance,
        "actual_risk_pct": (units * stop_distance) / equity,
    }
```

### 12.4 反马丁格尔 + 回撤保护

```
赢了加仓（复利加速）:
  连胜1次: 基础仓位 × 1.2
  连胜3次: 基础仓位 × 1.2³ = 1.73
  上限: 3倍基础仓位

输了减仓（保护本金）:
  回撤 > 10%: 仓位减半
  回撤 > 15%: 仓位降到25%
  回撤 > 20%: 停止交易，等待人工确认
```

### 12.5 杠杆使用规则

```
永远不用满杠杆:
  可用杠杆: 5x
  正常使用: 2-3x（留40%缓冲应对极端行情）
  高置信度: 最多4x
  低置信度: 1x或不开仓

体制联动:
  TRENDING:   允许3-4x（趋势明确）
  RANGING:    最多2x（方向不确定）
  VOLATILE:   最多1x或不交易（高波动=高风险）
```

---

## 十三、前端设计（从零构建）

### 13.1 技术选型

| 组件 | 选择 | 原因 |
|------|------|------|
| 框架 | React 18 + TypeScript + Vite | 标准，编译快 |
| 图表 | **TradingView Lightweight Charts v5.1** | 47kB, 专为金融设计, 插件系统可画威科夫标注 |
| 样式 | Tailwind CSS | 暗色主题，可维护 |
| 状态 | Zustand | 轻量全局状态 |
| 数据获取 | TanStack Query | REST缓存 + 自动刷新 |
| 图标 | Lucide React | 轻量 |

### 13.2 统一API设计（4个接口）

**REST（3个，一次性获取静态/大数据）：**

```
GET  /api/candles/{symbol}/{tf}  → 历史K线（初始加载）
GET  /api/system/snapshot        → 系统全局状态快照
POST /api/config                 → 更新配置
```

**WebSocket（1个，基于主题订阅推送全部实时数据）：**

```
WS   /ws/realtime

客户端发:  {"type": "subscribe", "topics": ["candles","wyckoff","positions","evolution"]}
服务端推:  {"type": "candle_update",       "data": {...}}
           {"type": "wyckoff_state",       "data": {...}}
           {"type": "position_update",     "data": {...}}
           {"type": "signal_alert",        "data": {...}}
           {"type": "evolution_progress",  "data": {...}}
           {"type": "advisor_analysis",    "data": {...}}
           {"type": "system_status",       "data": {...}}
```

### 13.3 页面布局

```
┌──────────────────────────────────────────────────────────────────┐
│  Header: ETH/USDT │ [D1][H4][H1][M15][M5] │ ● Running │ 09:42  │
├──────────┬─────────────────────────────────┬────────────────────┤
│ 左面板    │   主图表区 (65%)                │ 右面板              │
│ 可折叠    │                                 │ 可折叠              │
│          │  ┌─────────────────────────┐    │                    │
│ 威科夫    │  │ TradingView LWC         │    │ 实时信号            │
│ 状态机    │  │ K线 + 威科夫标注         │    │ ├ BUY conf=0.78    │
│          │  │ FVG区域 + 支撑阻力       │    │ ├ Phase: C         │
│ Phase    │  │ 阶段背景色               │    │ └ Spring detected  │
│ [A][B]   │  └─────────────────────────┘    │                    │
│ [C►][D]  │  ┌─────────────────────────┐    │ 仓位               │
│ [E]      │  │ 成交量柱状图             │    │ ├ LONG 3842.5     │
│          │  └─────────────────────────┘    │ ├ PnL: +1.53%     │
│ 证据链    │                                 │ └ SL: 3790.0      │
│ ├SC 0.82 │                                 │                    │
│ ├AR 0.65 │                                 │ 杠杆: 2.3x         │
│ └ST 0.71 │                                 │ 回撤: 2.1%         │
├──────────┴─────────────────────────────────┴────────────────────┤
│  底部Tab: [持仓] [交易历史] [进化监控] [AI分析] [日志]           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ 进化监控:                                                   │ │
│  │ Gen: 42 │ Fitness: 0.73 │ Sharpe: 1.82 │ DSR: 0.96        │ │
│  │ OOS退化率: 0.28 │ PBO: 0.35 │ Monte Carlo p: 0.02         │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

### 13.4 LWC威科夫覆盖层插件

```typescript
// 4个自定义插件，利用LWC v5的Plugin System

// 1. WyckoffPhaseBg — Pane Primitive
//    在K线图背景画阶段颜色（Phase A=灰, B=黄, C=绿, D=蓝, E=紫）

// 2. SupportResistance — Series Primitive
//    画支撑/阻力水平线（SC_LOW, AR_HIGH, BC_HIGH等关键价位）

// 3. FvgZones — Series Primitive
//    画FVG缺口区域（半透明矩形，牛市绿色/熊市红色）

// 4. StateMarkers — Series Primitive
//    在K线上标记状态事件（SC/AR/Spring/JOC等文字标签）
```

### 13.5 前端文件结构

```
frontend/
├── index.html
├── package.json             # React 18, LWC 5.1, Tailwind, Zustand, TanStack
├── tailwind.config.js
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── App.tsx              # 三栏布局骨架
    ├── index.css            # Tailwind + 暗色主题变量
    ├── types/api.ts         # 与后端types.py一一对应的TS类型
    ├── core/
    │   ├── api.ts           # 3个REST端点的客户端 (~80行)
    │   ├── ws.ts            # WebSocket主题订阅管理器 (~120行)
    │   └── store.ts         # Zustand全局状态 (~60行)
    ├── hooks/
    │   ├── useChart.ts      # LWC初始化+实时更新 (~100行)
    │   └── useOverlays.ts   # 威科夫覆盖层管理 (~80行)
    ├── components/
    │   ├── Header.tsx       # 交易对+TF选择+系统状态 (~60行)
    │   ├── ChartPanel.tsx   # 主K线图容器 (~120行)
    │   ├── WyckoffPanel.tsx # 状态机+证据链 (~150行)
    │   ├── SignalPanel.tsx  # 实时信号+仓位+风险 (~120行)
    │   ├── BottomTabs.tsx   # Tab容器 (~40行)
    │   ├── PositionsTab.tsx # 持仓表 (~80行)
    │   ├── TradesTab.tsx    # 交易历史表 (~80行)
    │   ├── EvolutionTab.tsx # 进化监控 (~120行)
    │   ├── AdvisorTab.tsx   # AI分析展示 (~80行)
    │   └── LogsTab.tsx      # 系统日志 (~60行)
    └── chart-plugins/
        ├── WyckoffPhaseBg.ts   # 阶段背景色 (~80行)
        ├── SupportResistance.ts # 支撑阻力线 (~60行)
        ├── FvgZones.ts         # FVG区域 (~70行)
        └── StateMarkers.ts     # 状态事件标记 (~60行)

共19个源文件，预估 ~2200行
```

---

## 十四、进化顾问 AI Agent

### 14.1 定位

LLM是**镜子不是手** — 帮你看清进化在干什么，不碰控制面板。

### 14.2 做什么 / 不做什么

| ✅ 做 | ❌ 不做 |
|-------|---------|
| 每轮进化后分析为什么成功/失败 | 直接修改参数 |
| MistakeBook错误模式翻译成人话 | 实时交易决策 |
| 建议下一轮变异方向 | 替代GA/WFA |
| 检测进化是否卡在局部最优 | 任何低延迟操作 |
| WFA验证结果的第二意见 | 自主执行交易 |

### 14.3 架构

```
src/plugins/evolution_advisor/
├── plugin-manifest.yaml
├── plugin.py          # 订阅 evolution.cycle_complete 事件
├── advisor.py         # LLM分析逻辑 (~200行)
└── prompts.py         # Prompt模板
```

### 14.4 工作流程

```
进化循环完成
  → EventBus: evolution.cycle_complete
    → EvolutionAdvisorPlugin（异步，不阻塞进化）
      → 收集: MistakeBook模式 + Config变化 + 性能趋势
      → 调用LLM (GPT-4o-mini或Ollama, ~3秒)
      → 存入日志
      → WebSocket推送: advisor.analysis
        → 前端 AdvisorTab 显示
```

### 14.5 成本

| 模型 | 每轮成本 | 每月(24轮/天) | 备注 |
|------|---------|-------------|------|
| GPT-4o-mini | $0.003 | $2.10 | 推荐 |
| 本地Ollama | $0 | 电费 | 需要GPU |

### 14.6 实施时机

**Phase 7（Phase 4进化重建之后）。** 得先有能工作的进化系统，Agent才有东西可分析。

---

## 十五、更新后的实施阶段（替代第八章）

### Phase 0: 清理 [1天] ✅ COMPLETED (2026-03-19)

```
删除: ✅
  - src/plugins/agent_teams/（全部，~6000行）
  - frontend/（全部，3757行）
  - src/plugins/orchestrator/ 死文件（~1700行）
  - src/plugins/evolution/archivist.py
新增: ✅
  - src/kernel/types.py 追加新 dataclass（WyckoffStateResult, OrderRequest 等）
净删除: ~12000行
依赖: 无
```

### Phase 1: 状态机重建 [3天] ✅ COMPLETED (2026-03-20)

```
新建: ✅
  - transition_guard.py（转换守卫，119行）→ VALID_TRANSITIONS + check_prerequisite_evidence
  - state_machine_v2.py（每TF独立实例，801行）→ WyckoffStateMachineV2 + PHASE_MAP
重写: ✅
  - distribution_detectors.py（9个检测器，全部补 StateEvidence 证据链 + critical_levels）
修复: ✅
  - accumulation_detectors.py（10个检测器 string→StateEvidence 迁移完成）
删除:
  - wyckoff_phase_detector.py（统一为Mixin系统）→ 延后，V2已解耦
新增: ✅
  - 再积累/再派发检测 (_detect_re_accumulation + _detect_re_distribution)
  - 趋势恢复检测 (_detect_trend_resumption)
  - 感知层(CandlePhysical/PinBody/FVG)集成到检测器 → 延后至 Phase 2
测试: ✅
  - test_state_machine_v2.py（44 tests, all passing）
  - test_transition_guard.py（20 tests, all passing）
  - 全量测试: 611 passed, 0 failed
依赖: Phase 0
```

### Phase 2: WyckoffEngine 重建 [2天] ✅ COMPLETED

```
重建: ✅
  - engine.py（类型化接口 + process_bar() + StateMachineV2 per-TF）
测试: ✅
  - test_wyckoff_engine.py（P0-P3共21个测试）
  - 全量测试: 632 passed, 0 failed
依赖: Phase 1
```

### Phase 3: 事件链接通 [1天] ✅ COMPLETED

```
重建: ✅
  - orchestrator/plugin.py（持有Engine + 发布trading.signal + run_loop双模式）
修复: ✅
  - position_manager/plugin.py（接通ExchangeExecutor + PositionJournal崩溃恢复）
  - exchange_connector/exchange_executor.py（execute(OrderRequest)→OrderResult主接口）
新增: ✅
  - kernel/types.py: OrderRequest/OrderResult/OrderSide/OrderType/OrderStatus
  - position_manager/position_journal.py（JSONL持久化 + 崩溃恢复对账）
测试: ✅
  - test_signal_chain.py（16 tests, all passing）
  - 全量测试: 648 passed, 0 failed
依赖: Phase 2
  - test_signal_chain.py（端到端事件链）
依赖: Phase 2
```

### Phase 4: 进化系统重建 [3天] ✅ COMPLETED (2026-03-20)

```
新建: ✅
  - evolution/bar_by_bar_backtester.py（逐bar回测 + SignalControl节流，~500行）
  - evolution/evaluator.py（标准评估器，~190行）— 上个session完成
  - evolution/genetic_algorithm.py（真正的GA：锦标赛选择/均匀交叉/高斯变异/精英保留，~460行）
  - evolution/wfa_validator.py（WFA滚动窗口验证，~366行）— 上个session完成
  - evolution/anti_overfit.py（MBL+OOS-DR+DSR+MonteCarlo+CPCV五层防护，~260行）
重建: ✅
  - evolution/plugin.py（GA+WFA+AntiOverfit进化主循环，~230行）
  - run_evolution.py（使用新GA+WFA替代旧real_performance_evaluator，~230行）
修复: ✅
  - self_correction/mistake_book.py（新增 record_trade_mistake() 简化接口）
测试: ✅
  - test_evolution_pipeline.py（端到端管线测试，6 tests）
  - test_genetic_algorithm.py（GA单元测试，12 tests）
  - test_wfa_validator.py（WFA验证器测试，9 tests）
  - test_anti_overfit.py（防过拟合测试，14 tests）
  - 全量测试: 689 passed, 0 failed
依赖: Phase 2
```

### Phase 5: 后端API [1天] ✅ COMPLETED (2026-03-20)

```
重建: ✅
  - src/api/app.py（948行→445行，30端点→4端点）
    - GET /api/candles/{symbol}/{tf} — 历史K线
    - GET /api/system/snapshot — 系统全景快照
    - POST /api/config — 配置更新
    - WS /ws/realtime — 主题订阅推送（心跳60s + 推送2s）
  - 零私有属性访问，全部通过 get_plugin() + list_plugins() 公共API
  - CORS 支持（环境变量 WYCKOFF_CORS_ORIGINS）
新建: ✅
  - tests/api/__init__.py
  - tests/api/test_api.py（18 tests, all passing）
测试: ✅
  - 全量测试: 707 passed, 0 failed
依赖: Phase 3
```

### Phase 6: 前端从零构建 [3天] ✅ COMPLETED (2026-03-21)

```
新建整个 frontend/ 目录: ✅
  - 23个源文件，2337行代码
  - 技术栈: React 18 + TypeScript + Vite + Tailwind CSS + Zustand + TanStack Query
  - LWC v5.1 K线图（CandlestickSeries + HistogramSeries via addSeries() API）
  - 4个威科夫 LWC 自定义 Primitive 覆盖层:
    - WyckoffPhaseBg (Pane Primitive — 阶段背景色，drawBackground)
    - SupportResistance (Series Primitive — S/R虚线 + 标签)
    - FvgZones (Series Primitive — FVG半透明矩形)
    - StateMarkers (Series Primitive — 状态事件标记)
  - WebSocket 管理器: 主题订阅 + 30s心跳 + 指数退避重连(最多20次)
  - Zustand store: candle追加去重(同时间戳覆盖)
  - Vite proxy: /api → :9527, /ws → ws://:9527
  - 暗色主题 (GitHub Dark 色系)
验证: ✅
  - TypeScript: tsc --noEmit → 0 errors
  - Production build: vite build → 383 kB JS (120 kB gzipped)
  - npm install: 142 packages
修复: ✅
  - lightweight-charts ^5.1.1 → ^5.1.0（5.1.1 不存在）
  - addCandlestickSeries → addSeries(CandlestickSeries, opts) (LWC v5 API变更)
依赖: Phase 5
```

### Phase 7: 进化顾问 AI Agent [1天] ✅ COMPLETED (2026-03-20)

```
新建: ✅
  - src/plugins/evolution_advisor/plugin-manifest.yaml（订阅 evolution.cycle_complete）
  - src/plugins/evolution_advisor/__init__.py
  - src/plugins/evolution_advisor/plugin.py（243行 — 事件订阅 + 异步分析 + 公共查询API）
  - src/plugins/evolution_advisor/advisor.py（275行 — OpenAI/Ollama双后端 + 4种分析能力）
  - src/plugins/evolution_advisor/prompts.py（192行 — 4种Prompt模板）
  - tests/plugins/test_evolution_advisor.py（31 tests, all passing）
功能: ✅
  - 每轮进化后分析成功/失败原因
  - MistakeBook 错误模式翻译成人话
  - 检测进化是否卡在局部最优（fitness停滞检测）
  - 建议下一轮变异方向
  - 双后端：OpenAI GPT-4o-mini (~$0.003/轮) + Ollama (本地免费)
测试: ✅
  - 全量测试: 738 passed, 0 failed
依赖: Phase 4
```

### Phase 8: 权重修复 + Numba加速 + 集成测试 [2天] ✅ COMPLETED (2026-03-20)

```
修复: ✅
  - weight_system/period_weight_filter.py（regime keys 已验证匹配，无死方法）
  - self_correction/workflow.py（已重写：WeightVariator+WFABacktester → GeneticAlgorithm+WFAValidator+StandardEvaluator）
  - self_correction/plugin.py（新增 set_historical_data()，更新文档）
  - tests/plugins/test_self_correction_workflow.py（23 tests passing）
加速: ✅
  - evolution/numba_accelerator.py（1081行 — 三层Pass架构）
    - Pass 1: precompute_features() NumPy向量化预计算15种特征
    - Pass 2: state_machine_numba() @njit编译27状态威科夫状态机
    - Pass 3: vectorized_backtest() @njit编译回测引擎（多空+ATR止损止盈+超时）
    - AcceleratedEvaluator 封装类（与StandardEvaluator格式兼容）
    - Numba降级处理：NumPy版本不兼容时自动降级纯Python（HAS_NUMBA标志）
  - tests/plugins/test_numba_accelerator.py（46 tests, all passing）
    - 正确性测试：辅助函数/特征预计算/状态机/回测/集成（41 tests）
    - 性能基准测试：NumPy vs Python对比/Numba编译缓存/端到端速度（5 tests）
集成: ✅
  - 全量 plugin 测试: 660 passed, 0 failed
依赖: Phase 4+7
```

### Phase 9: E2E 全链路集成测试 [1天] ✅ COMPLETED (2026-03-21)

```
背景: ✅
  - Phase 0~8 的测试全部是"零件测试"：每个插件独立测试通过，但从未真正装配运行
  - 797 个 plugin tests 中 43% 是 mock-heavy 插件包装测试，只验证委托不验证逻辑
  - WyckoffApp.start() 从未被真实执行过（test_app.py 全是 @patch mock）
  - 类比：每个零件单独质检通过，但从来没有人坐进去开过一圈
新建: ✅
  1. tests/integration/test_e2e_full_pipeline.py（19 tests）
     - P0: WyckoffApp 真实加载 16 个插件，验证全部 ACTIVE
     - P1: 合成 OHLCV → OrchestratorPlugin._process_market_data() → TradingDecision
     - P1: 事件链 ohlcv_ready → trading.signal → position.opened
     - P1: 完整周期 开仓 → 止损触发 → 平仓 → 验证 PnL
     - P1: flat/up/down/spring 4种趋势数据全部产出决策
     - P2: 熔断阻断信号 + 恢复后恢复信号 + 空数据不崩溃
  2. tests/integration/test_api_integration.py（11 tests）
     - REST: 真实 WyckoffApp 注入 app_state，非 mock
     - GET /api/candles 返回数据 + limit 参数
     - GET /api/system/snapshot 16 个插件 + uptime + state
     - POST /api/config 更新成功 + 422 验证
     - WS: ping/pong + subscribe + invalid JSON + 多次 ping
  3. tests/integration/test_multi_plugin_event_chain.py（8 tests）
     - 多插件事件链: data_ready → signal（via 真实 Orchestrator）
     - 验证 orchestrator/position_manager 订阅正确事件
     - 连续 3 批数据处理不崩溃
     - 错误隔离: 一个 handler 崩溃不影响其他
     - 所有活跃插件均有 EventBus 注入
  4. tests/integration/test_perception_real_data.py（14 tests）
     - FVGDetector: detect_fvg_gaps 趋势/横盘/最少K线
     - CandlePhysical: 创建 + 方向 + 影线 + 实体比 + 批量
     - PinBodyAnalyzer: analyze_pin_vs_body 各形态
     - 感知层插件可通过 WyckoffApp 加载
  5. tests/integration/test_self_correction_loop.py（10 tests）
     - MistakeBook: 记录 + 模式分析
     - GeneticAlgorithm: 初始化 + 种群 + 一代进化
     - WFAValidator: 实例化 + 窗口创建
     - AntiOverfitGuard: 实例化
修复: ✅
  - src/plugins/wyckoff_engine/plugin.py — WyckoffEnginePlugin.__init__()
    不接受 name 参数（PluginManager 调用 plugin_class(name=name) 时崩溃）
    修复: 添加 name: str = "wyckoff_engine" 参数
测试: ✅
  - 全量测试: 859 passed, 0 failed, 9.46s
  - 新增: 62 个真实集成测试（零 mock）
  - 测试分层变化:
    - 真实逻辑测试: 285 → 347 (40%)
    - 集成测试: 46 → 108 (13%)
    - Mock-heavy: 345 → 345 (40%)
依赖: Phase 0~8 全部
```

### 进度总览

```
Phase 0: 清理                   [1天]  ✅ COMPLETED  ← 无依赖
Phase 1: 状态机重建              [3天]  ✅ COMPLETED  ← P0
Phase 2: WyckoffEngine重建      [2天]  ✅ COMPLETED  ← P1
Phase 3: 事件链接通              [1天]  ✅ COMPLETED  ← P2
  ↑ 到这里系统能Paper Trading
Phase 4: 进化系统重建            [3天]  ✅ COMPLETED  ← P2（可与P3并行）
  ↑ 到这里进化能真正工作
Phase 5: 后端API                [1天]  ✅ COMPLETED  ← P3
Phase 7: AI Agent               [1天]  ✅ COMPLETED  ← P4
Phase 8: 加速+集成              [2天]  ✅ COMPLETED  ← P4+P7
  ↑ 到这里后端全链路完成
Phase 6: 前端构建                [3天]  ✅ COMPLETED  ← P5
  ↑ 到这里前端可视化完成
Phase 9: E2E集成测试             [1天]  ✅ COMPLETED  ← ALL
  ↑ 到这里全链路验证完成（859 tests passing）
────────────────────────────────────
总计: 18天 — 全部完成 ✅
```

### 系统现状评估（2026-03-21）

```
已完成:
  ✅ 16个插件全部加载并达到 ACTIVE 状态
  ✅ 数据 → 分析 → 信号 → 开仓 → 止损/止盈 → 平仓 全链路验证
  ✅ REST API 4端点 + WebSocket 主题订阅 + 前端 React Dashboard
  ✅ 859 tests passing (含62个零mock集成测试)
  ✅ TypeScript 前端零类型错误, 生产构建 120kB gzipped

未完成 — 投入实盘前必须做:
  ❌ 真实交易所连通测试（Binance API 数据拉取 + 模拟下单验证）
  ❌ Paper Trading 长时间稳定性测试（至少连续运行24h无崩溃）
  ❌ 进化系统端到端验证（用真实历史数据跑1轮完整 GA→WFA→参数更新）
  ❌ Docker 部署方案（Dockerfile + docker-compose + healthcheck）
  ❌ Telegram 告警对接（交易信号 + 系统错误 + 熔断通知）
  ❌ 数据备份策略（position_journal + evolution_memory + config）

建议上线路径:
  Phase A: 交易所连通 + Paper Trading 稳定性 [2天]
           → 真实 Binance API 数据流 + 7×24h Paper 运行
  Phase B: 进化系统实战验证 [3天]
           → 用 90 天 BTC/ETH 真实历史跑完整进化流程
  Phase C: 运维部署 [1天]
           → Docker 打包 + Telegram + 数据备份 + 监控
  Phase D: 小资金实盘试运行 [持续]
           → $100-500 起步，3x杠杆，仅 BTC/USDT，观察1周
```

---

## 附录：更新后的问题解决方案映射

| # | 问题 | 解决方案 | Phase |
|---|------|---------|-------|
| 1 | 两条信号路径 | WyckoffEngine唯一路径 | P2 |
| 2 | 事件断链 | Orchestrator直接发布trading.signal | P3 |
| 3 | Exchange未接通 | PositionManager调用ExchangeExecutor | P3 |
| 4 | 状态机无守卫 | TransitionGuard硬约束 | P1 |
| 5 | 证据被丢弃 | 检测器→状态机→决策→事件→API全链路 | P1+P2 |
| 6 | 多TF共享实例 | 每TF独立StateMachineV2 | P1+P2 |
| 7 | 无再积累/再派发 | 新增RE_ACCUMULATION/RE_DISTRIBUTION | P1 |
| 8 | 进化只看最后一根 | BarByBarBacktester逐根回测 | P4 |
| 9 | GA从不crossover | 重写GA，真正的选择+交叉+变异 | P4 |
| 10 | 过拟合无防护 | 5层防护(MBL+OOS-DR+DSR+MC+CPCV) | P4 |
| 11 | 数据增长性能瓶颈 | 两层加速(NumPy预计算+Numba状态机) | P8 |
| 12 | 小资金仓位管理 | 1/4 Kelly + ATR调整 + 反马丁 + 杠杆规则 | P4 |
| 13 | 前端全是问题 | 从零构建 LWC+React+统一API | P5+P6 |
| 14 | Agent Teams冗余 | 删除，替换为轻量EvolutionAdvisor | P0+P7 |
| 15 | PhaseDetector双系统 | 删除PhaseDetector，统一Mixin | P1 |
| 16 | 感知层未集成 | CandlePhysical/PinBody集成到检测器 | P1 |

---

*本文档为 v3.0 架构设计的唯一权威来源。所有实施工作必须严格遵循此设计。*

---

## 十六、生产运维

### 16.1 崩溃恢复 + 状态持久化

**问题**: 系统崩溃后忘记有持仓 → 5倍杠杆下无人看管 → 爆仓。

**方案**: 每次持仓变化写入磁盘，启动时从磁盘恢复。

```python
class PositionJournal:
    """持仓日志 — 每次变化立即写盘"""
    def __init__(self, path: str = "data/positions.jsonl"):
        self.path = path

    def record(self, action: str, position: Dict) -> None:
        """追加写入(OPEN/CLOSE/PARTIAL_CLOSE/UPDATE_SL)"""
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(),
                 "action": action, "position": position}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def load_open_positions(self) -> List[Dict]:
        """启动时重建当前持仓状态"""
        positions: Dict[str, Dict] = {}
        with open(self.path) as f:
            for line in f:
                entry = json.loads(line)
                sym = entry["position"]["symbol"]
                if entry["action"] == "OPEN":
                    positions[sym] = entry["position"]
                elif entry["action"] in ("CLOSE", "LIQUIDATED"):
                    positions.pop(sym, None)
        return list(positions.values())
```

**集成点**: PositionManager open/close/update时调用`journal.record()`。启动时`journal.load_open_positions()`恢复。

### 16.2 交易所状态对账

**问题**: 重启后内部状态与交易所实际持仓不一致。

```python
async def reconcile_on_startup(
    exchange: ExchangeExecutor,
    journal: PositionJournal,
    position_manager: PositionManager,
) -> List[str]:
    """启动对账 — 三方比对(日志 vs 内存 vs 交易所)"""
    warnings = []
    # 1. 从日志恢复
    journal_positions = journal.load_open_positions()
    # 2. 从交易所查询
    exchange_positions = await exchange.get_all_positions()

    journal_symbols = {p["symbol"] for p in journal_positions}
    exchange_symbols = {p["symbol"] for p in exchange_positions}

    # 孤儿持仓：交易所有，日志没有 → 危险！
    orphans = exchange_symbols - journal_symbols
    for sym in orphans:
        warnings.append(f"ORPHAN: {sym} 在交易所有持仓但日志无记录")

    # 幽灵持仓：日志有，交易所没有 → 已被清算？
    ghosts = journal_symbols - exchange_symbols
    for sym in ghosts:
        warnings.append(f"GHOST: {sym} 日志有记录但交易所无持仓(可能已被清算)")

    # 同步：以交易所为准
    for pos in exchange_positions:
        position_manager.sync_from_exchange(pos)

    return warnings
```

**规则**: 启动时必须对账。有孤儿持仓 → 发告警，不自动平仓（可能是用户手动开的）。有幽灵持仓 → 标记为已清算。

### 16.3 订单状态机

**问题**: 系统假设下单=立即全部成交。实际可能部分成交、超时、被拒。

```
订单生命周期:
  PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                     → REJECTED
                     → CANCELLED
                     → EXPIRED (超时未成交)

规则:
  PARTIALLY_FILLED: 按实际成交量更新持仓，剩余继续等待或取消
  REJECTED: 记录原因，不重试（可能是余额不足/价格异常）
  超时(30秒未成交): 取消订单，按已成交部分更新持仓
```

**集成点**: ExchangeExecutor.execute()返回后，启动异步轮询订单状态直到终态(FILLED/CANCELLED/EXPIRED)。

### 16.4 API限频

**问题**: Binance 1200请求/分钟，超限封IP。

```python
class RateLimiter:
    """滑动窗口限频器"""
    def __init__(self, max_requests: int = 1100, window_sec: int = 60):
        self.max_requests = max_requests  # 留100余量
        self.window_sec = window_sec
        self.timestamps: List[float] = []

    async def acquire(self) -> None:
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.window_sec]
        if len(self.timestamps) >= self.max_requests:
            wait = self.timestamps[0] + self.window_sec - now
            logger.warning("限频等待 %.1f秒", wait)
            await asyncio.sleep(wait)
        self.timestamps.append(time.time())
```

**集成点**: ExchangeExecutor每个API调用前`await rate_limiter.acquire()`。

### 16.5 数据完整性检查

```python
def validate_ohlcv(df: pd.DataFrame) -> List[str]:
    """OHLCV数据有效性检查"""
    errors = []
    # 基本关系
    if (df["high"] < df[["open","close"]].max(axis=1)).any():
        errors.append("high < max(open,close)")
    if (df["low"] > df[["open","close"]].min(axis=1)).any():
        errors.append("low > min(open,close)")
    # 时间连续性
    diffs = df.index.to_series().diff().dropna()
    expected = diffs.mode()[0]
    gaps = diffs[diffs > expected * 1.5]
    if len(gaps) > 0:
        errors.append(f"{len(gaps)}个时间缺口")
    # 新鲜度
    age = datetime.now(timezone.utc) - df.index[-1].to_pydatetime()
    if age.total_seconds() > 3600:
        errors.append(f"数据过期: {age}")
    return errors
```

**集成点**: DataPipeline获取数据后、发布ohlcv_ready前运行。有致命错误→触发熔断。

### 16.6 监控告警

**现有资产**: `performance_monitor.py`(1085行)已有4级告警系统，但只写日志。

**需要做的**: 把`_notify_critical_alert()`接通真实通知渠道。

```python
class AlertChannel:
    """告警通道 — 至少实现一种"""
    async def send(self, level: str, message: str) -> None: ...

class TelegramAlert(AlertChannel):
    """Telegram机器人告警（推荐）"""
    def __init__(self, bot_token: str, chat_id: str): ...
    async def send(self, level: str, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        await httpx.post(url, json={"chat_id": self.chat_id, "text": f"[{level}] {message}"})
```

**必须告警的事件**:

| 事件 | 级别 | 说明 |
|------|------|------|
| 持仓开启/关闭 | INFO | 每笔交易通知 |
| 熔断触发 | CRITICAL | 立即通知 |
| 数据过期>5分钟 | WARNING | 可能断网 |
| 交易所连接断开 | CRITICAL | 立即通知 |
| 系统启动/停止 | INFO | 感知系统存活 |
| 孤儿持仓发现 | CRITICAL | 启动对账异常 |
| 进化完成一轮 | INFO | 附带fitness摘要 |

### 16.7 部署方案

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "run.py", "--mode=trading"]
```

```yaml
# docker-compose.yml
services:
  wyckoff:
    build: .
    restart: always        # 崩溃自动重启
    env_file: .env
    volumes:
      - ./data:/app/data   # 持仓日志+历史数据持久化
      - ./logs:/app/logs   # 日志持久化
      - ./config.yaml:/app/config.yaml
    healthcheck:
      test: ["CMD", "python", "health_check.py"]
      interval: 60s
      timeout: 10s
      retries: 3
```

### 16.8 审计日志

**规则**: 每笔交易决策必须记录完整上下文，不可篡改。

```python
# 审计日志格式 — 追加写入 logs/audit.jsonl
{
    "timestamp": "2026-03-20T09:42:15Z",
    "event": "SIGNAL_GENERATED",
    "signal": "BUY",
    "confidence": 0.78,
    "wyckoff_state": "SPRING",
    "phase": "C",
    "evidences": [...],
    "config_hash": "a3f2b1c4",
    "reasoning": ["SC detected", "Volume climax", "Price at support"],
}
{
    "timestamp": "2026-03-20T09:42:16Z",
    "event": "ORDER_PLACED",
    "symbol": "ETHUSDT",
    "side": "BUY",
    "size": 0.15,
    "price": 3842.5,
    "stop_loss": 3790.0,
    "leverage": 2.3,
    "risk_pct": 0.02,
    "config_hash": "a3f2b1c4",
}
```

**config_hash**: 每笔交易记录当时的配置指纹，进化改了参数后可追溯哪个配置产生了哪笔交易。

### 16.9 优雅降级

```
如果某个分析模块出错，不应该整个系统崩溃:

RegimeDetector出错   → regime=UNKNOWN, confidence=0 → 继续但降低仓位
TRDetector出错       → tr=None → 继续，状态机少一个输入
FVGDetector出错      → fvg=[] → 继续
StateMachine出错     → state=IDLE, confidence=0 → 发NEUTRAL信号
PositionManager出错  → 不开新仓，保持现有仓位
Exchange出错         → 重试3次，仍失败→熔断+告警
```

**实现**: WyckoffEngine各阶段已有try/except，但需要确保降级结果是类型安全的PerceptionResult/FusionResult/WyckoffStateResult，而不是None。

### 16.10 已有资产纳入设计

以下代码库中已有的功能正式纳入架构设计（之前设计书遗漏）：

| 模块 | 位置 | 纳入方式 |
|------|------|---------|
| retry装饰器+指数退避 | `src/utils/error_handler.py` | 所有Exchange/DataPipeline调用包装retry |
| 764行熔断器(8种触发) | `circuit_breaker.py` | Phase 3接通事件链时集成 |
| 性能监控+告警框架 | `performance_monitor.py` | 16.6中接通Telegram |
| 多级止盈分批平仓 | `stop_loss_executor.py` | Phase 3中保留并接入 |
| 信号反转+超时退出 | `signal_exit_logic.py` | Phase 3中保留并接入 |
| 进化状态持久化 | `evolution_storage.py` | Phase 4中复用 |

### 16.11 实施时机

| 项 | 何时做 | 阶段 |
|---|--------|------|
| 数据完整性检查 | Phase 2（引擎重建时） | 引擎调用前验证 |
| 优雅降级 | Phase 2（引擎重建时） | 每个阶段的try/except |
| API限频 | Phase 3（事件链接通时） | ExchangeExecutor内 |
| 订单状态机 | Phase 3（事件链接通时） | ExchangeExecutor内 |
| 崩溃恢复+对账 | Phase 3（事件链接通时） | PositionManager启动 |
| 审计日志 | Phase 3（事件链接通时） | 信号+订单事件 |
| 监控告警(Telegram) | Phase 5（API重建时） | 通知渠道 |
| 部署方案(Docker) | Phase 8（集成测试时） | 最后打包 |

---

## 附录B：完整问题清单（更新至22项）

| # | 问题 | 解决方案 | Phase |
|---|------|---------|-------|
| 1 | 两条信号路径 | WyckoffEngine唯一路径 | P2 |
| 2 | 事件断链 | Orchestrator直接发布trading.signal | P3 |
| 3 | Exchange未接通 | PositionManager调用ExchangeExecutor | P3 |
| 4 | 状态机无守卫 | TransitionGuard硬约束 | P1 |
| 5 | 证据被丢弃 | 全链路StateEvidence传递 | P1+P2 |
| 6 | 多TF共享实例 | 每TF独立StateMachineV2 | P1+P2 |
| 7 | 无再积累/再派发 | 新增RE_ACCUMULATION/RE_DISTRIBUTION | P1 |
| 8 | 进化只看最后一根 | BarByBarBacktester逐根回测 | P4 |
| 9 | GA从不crossover | 重写GA | P4 |
| 10 | 过拟合无防护 | 5层防护(MBL+OOS-DR+DSR+MC+CPCV) | P4 |
| 11 | 数据增长性能瓶颈 | NumPy预计算+Numba状态机 | P8 |
| 12 | 小资金仓位管理 | 1/4 Kelly + ATR + 反马丁 + 杠杆规则 | P4 |
| 13 | 前端全是问题 | 从零构建 LWC+React+统一API | P5+P6 |
| 14 | Agent Teams冗余 | 删除，替换为EvolutionAdvisor | P0+P7 |
| 15 | PhaseDetector双系统 | 删除PhaseDetector，统一Mixin | P1 |
| 16 | 感知层未集成 | CandlePhysical/PinBody集成到检测器 | P1 |
| 17 | **崩溃后丢失持仓** | PositionJournal持久化+启动对账 | P3 |
| 18 | **部分成交未处理** | 订单状态机(NEW→PARTIAL→FILLED) | P3 |
| 19 | **API限频** | RateLimiter滑动窗口 | P3 |
| 20 | **数据完整性** | OHLCV验证+缺口检测+新鲜度检查 | P2 |
| 21 | **无监控告警** | Telegram通知+性能监控接通 | P5 |
| 22 | **无部署方案** | Docker+docker-compose+healthcheck | P8 |

---

*本文档为 v3.0 架构设计的唯一权威来源。所有实施工作必须严格遵循此设计。*
*最后更新: 2026-03-21 — Phase 0~9 全部完成（859 tests passing），下一步: 交易所连通 + Paper Trading 稳定性验证*