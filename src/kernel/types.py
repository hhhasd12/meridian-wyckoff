"""内核共享类型定义

定义插件系统的基础类型和业务共享类型，包括：

插件系统类型：
- PluginState: 插件生命周期状态枚举
- PluginType: 插件类型枚举（core/optional）
- PluginInfo: 插件运行时信息数据类
- PluginError: 插件专用异常类
- EventPriority: 事件优先级枚举
- HealthStatus: 健康检查状态枚举

业务共享类型：
- SystemMode: 系统运行模式枚举
- TradingSignal: 交易信号枚举
- WyckoffSignal: 威科夫信号枚举
- DecisionContext: 决策上下文数据类
- TradingDecision: 交易决策结果数据类

这些类型被内核层和插件层的所有模块共享。
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _safe_timestamp_to_iso(timestamp: Any) -> str:
    """安全地将时间戳转换为 ISO 格式字符串

    自动判断 int64 时间戳是秒还是毫秒：
    - 值 > 1e12 视为毫秒（如 1700000000000）
    - 值 <= 1e12 视为秒（如 1700000000）

    Args:
        timestamp: datetime 对象或 int/int64 时间戳

    Returns:
        ISO 格式时间戳字符串
    """
    if isinstance(timestamp, (int, np.integer)):
        ts_float = float(timestamp)
        # 自动判断：大于 1e12 视为毫秒，否则视为秒
        if ts_float > 1e12:
            ts_float /= 1000.0
        timestamp_dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        return timestamp_dt.isoformat()
    elif isinstance(timestamp, datetime):
        return timestamp.isoformat()
    else:
        return str(timestamp)


class PluginState(Enum):
    """插件生命周期状态

    状态转换图：
        UNLOADED → LOADING → ACTIVE
        ACTIVE → UNLOADING → UNLOADED
        任意状态 → ERROR
        ERROR → UNLOADING → UNLOADED（恢复路径）
    """

    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    ACTIVE = "ACTIVE"
    UNLOADING = "UNLOADING"
    ERROR = "ERROR"


class PluginType(Enum):
    """插件类型

    Attributes:
        CORE: 核心插件，系统启动时必须加载，不可禁用
        CONNECTOR: 连接器插件，负责外部数据源连接
        ANALYSIS: 分析插件，提供市场分析功能
        EXECUTOR: 执行插件，负责交易执行
        UI: 用户界面插件，提供可视化功能
        OPTIONAL: 可选插件，可按需启用/禁用
    """

    CORE = "core"
    CONNECTOR = "connector"
    ANALYSIS = "analysis"
    EXECUTOR = "executor"
    UI = "ui"
    OPTIONAL = "optional"


class EventPriority(Enum):
    """事件处理优先级

    数值越小优先级越高，HIGH 优先于 NORMAL 处理。
    """

    HIGH = 0
    NORMAL = 1
    LOW = 2


class HealthStatus(Enum):
    """健康检查状态

    Attributes:
        HEALTHY: 插件运行正常
        DEGRADED: 插件功能降级但仍可用
        UNHEALTHY: 插件不可用
        UNKNOWN: 无法确定健康状态
    """

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass
class PluginInfo:
    """插件运行时信息

    存储插件在运行时的元数据和状态信息，
    由 PluginManager 维护。

    Attributes:
        name: 插件唯一标识名
        display_name: 插件显示名称
        version: 插件版本号
        plugin_type: 插件类型（core/optional）
        state: 当前生命周期状态
        entry_point: 入口模块路径
        plugin_dir: 插件目录路径
        dependencies: 依赖的其他插件名列表
        capabilities: 插件提供的能力列表
        error_message: 最近一次错误信息
        load_time: 加载耗时（秒）
        last_health_check: 最近一次健康检查结果
        metadata: 额外的元数据
    """

    name: str
    display_name: str = ""
    version: str = "0.0.0"
    plugin_type: PluginType = PluginType.OPTIONAL
    state: PluginState = PluginState.UNLOADED
    entry_point: str = ""
    plugin_dir: str = ""
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    load_time: float = 0.0
    last_health_check: Optional["HealthCheckResult"] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """健康检查结果

    Attributes:
        status: 健康状态
        message: 状态描述信息
        details: 详细的检查指标
        timestamp: 检查时间戳
    """

    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class PluginError(Exception):
    """插件系统专用异常基类

    所有插件相关的异常都应继承此类，
    便于统一捕获和处理。

    Attributes:
        plugin_name: 触发异常的插件名称
        message: 异常描述信息
    """

    def __init__(self, message: str, plugin_name: Optional[str] = None) -> None:
        self.plugin_name = plugin_name
        self.message = message
        super().__init__(
            f"[Plugin: {plugin_name}] {message}" if plugin_name else message
        )


class PluginLoadError(PluginError):
    """插件加载失败异常"""

    pass


class PluginDependencyError(PluginError):
    """插件依赖解析失败异常

    Attributes:
        missing_dependencies: 缺失的依赖列表
    """

    def __init__(
        self,
        message: str,
        plugin_name: Optional[str] = None,
        missing_dependencies: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message, plugin_name)
        self.missing_dependencies = missing_dependencies or []


class PluginConfigError(PluginError):
    """插件配置错误异常"""

    pass


class ManifestValidationError(PluginError):
    """清单文件验证失败异常

    Attributes:
        validation_errors: 验证错误详情列表
    """

    def __init__(
        self,
        message: str,
        plugin_name: Optional[str] = None,
        validation_errors: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message, plugin_name)
        self.validation_errors = validation_errors or []


# 类型别名，方便其他模块引用
EventCallback = Callable[[str, Dict[str, Any]], None]
ConfigDict = Dict[str, Any]


# ============================================================
# 业务共享类型 - 从 system_orchestrator_legacy.py 提取
# ============================================================


class SystemMode(Enum):
    """系统运行模式

    Attributes:
        BACKTEST: 回测模式
        PAPER_TRADING: 模拟交易模式
        LIVE_TRADING: 实盘交易模式
        EVOLUTION: 进化模式（专注系统优化）
    """

    BACKTEST = "backtest"
    PAPER_TRADING = "paper"
    LIVE_TRADING = "live"
    EVOLUTION = "evolution"


class TradingSignal(Enum):
    """交易信号枚举

    Attributes:
        STRONG_BUY: 强烈买入信号
        BUY: 买入信号
        NEUTRAL: 中性信号
        SELL: 卖出信号
        STRONG_SELL: 强烈卖出信号
        WAIT: 等待确认信号
    """

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    WAIT = "wait"


class WyckoffSignal(Enum):
    """威科夫信号枚举

    Attributes:
        BUY_SIGNAL: 买入信号
        SELL_SIGNAL: 卖出信号
        NO_SIGNAL: 无信号
    """

    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"
    NO_SIGNAL = "no_signal"


@dataclass
class DecisionContext:
    """决策上下文 - 包含当前分析的所有相关信息

    Attributes:
        timestamp: 决策时间戳
        market_regime: 市场体制字符串
        regime_confidence: 体制判断置信度
        timeframe_weights: 各时间框架权重
        detected_conflicts: 检测到的冲突列表
        wyckoff_state: 威科夫状态
        wyckoff_confidence: 威科夫置信度
        breakout_status: 突破状态
        fvg_signals: FVG信号列表
        anomaly_flags: 异常标记列表
        circuit_breaker_status: 熔断器状态
    """

    timestamp: datetime
    market_regime: str
    regime_confidence: float
    timeframe_weights: Dict[str, float]
    detected_conflicts: List[Dict[str, Any]]
    wyckoff_state: Optional[Any] = None
    wyckoff_confidence: float = 0.0
    breakout_status: Optional[Dict[str, Any]] = None
    fvg_signals: List[Dict[str, Any]] = field(default_factory=list)
    anomaly_flags: List[Dict[str, Any]] = field(default_factory=list)
    circuit_breaker_status: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            包含所有字段的字典，时间戳转换为ISO格式字符串
        """
        logger.debug("Converting DecisionContext to dict")

        # 修复：时间戳可能是int64类型，自动判断秒/毫秒
        timestamp_str = _safe_timestamp_to_iso(self.timestamp)

        return {
            "timestamp": timestamp_str,
            "market_regime": self.market_regime,
            "regime_confidence": self.regime_confidence,
            "timeframe_weights": self.timeframe_weights,
            "detected_conflicts": self.detected_conflicts,
            "wyckoff_state": (str(self.wyckoff_state) if self.wyckoff_state else None),
            "wyckoff_confidence": self.wyckoff_confidence,
            "breakout_status": self.breakout_status,
            "fvg_signals": self.fvg_signals,
            "anomaly_flags": self.anomaly_flags,
            "circuit_breaker_status": self.circuit_breaker_status,
        }


@dataclass
class TradingDecision:
    """交易决策结果

    Attributes:
        signal: 交易信号
        confidence: 决策置信度
        context: 决策上下文
        entry_price: 入场价格
        stop_loss: 止损价格
        take_profit: 止盈价格
        position_size: 仓位大小
        reasoning: 决策理由列表
        timestamp: 决策时间戳
    """

    signal: TradingSignal
    confidence: float
    context: DecisionContext
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    reasoning: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            包含所有字段的字典，时间戳转换为ISO格式字符串
        """
        logger.debug("Converting TradingDecision to dict")

        # 修复：时间戳可能是int64类型，自动判断秒/毫秒
        timestamp_str = _safe_timestamp_to_iso(self.timestamp)

        return {
            "signal": self.signal.value,
            "confidence": self.confidence,
            "context": self.context.to_dict(),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": self.position_size,
            "reasoning": self.reasoning,
            "timestamp": timestamp_str,
        }


# ============================================================
# 威科夫状态机类型 (从 wyckoff_state_machine_legacy.py 提取)
# ============================================================


class StateDirection(Enum):
    """状态方向枚举

    定义威科夫理论中的四种市场状态方向。
    """

    ACCUMULATION = "ACCUMULATION"  # 吸筹阶段
    DISTRIBUTION = "DISTRIBUTION"  # 派发阶段
    TRENDING = "TRENDING"  # 趋势阶段
    IDLE = "IDLE"  # 空闲状态


class StateTransitionType(Enum):
    """状态转换类型枚举

    定义状态机中四种转换方式。
    """

    LINEAR = "LINEAR"  # 线性转换（按标准顺序）
    NONLINEAR = "NONLINEAR"  # 非线性跳转
    RESET = "RESET"  # 状态重置
    PARALLEL = "PARALLEL"  # 并行路径


@dataclass
class StateEvidence:
    """状态证据

    记录支持某个状态判断的单条证据。

    Attributes:
        evidence_type: 证据类型，如'volume_ratio', 'pin_strength'等
        value: 证据值
        confidence: 证据置信度 0-1
        weight: 证据权重 0-1
        description: 证据描述
    """

    evidence_type: str
    value: float
    confidence: float
    weight: float
    description: str


@dataclass
class StateDetectionResult:
    """状态检测结果

    记录一次状态检测的完整结果。

    Attributes:
        state_name: 检测到的状态名称
        confidence: 总体置信度 0-1
        intensity: 状态强度 0-1
        evidences: 证据列表
        heritage_score: 遗产分数
        timestamp: 检测时间戳
    """

    state_name: str
    confidence: float
    intensity: float
    evidences: List[StateEvidence]
    heritage_score: float = 0.0
    timestamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class StateTransition:
    """状态转换记录

    记录一次状态转换的完整信息。

    Attributes:
        from_state: 源状态
        to_state: 目标状态
        timestamp: 转换时间戳
        confidence: 转换置信度
        transition_type: 转换类型
        evidences: 触发转换的证据
        heritage_transfer: 遗产传递量
    """

    from_state: str
    to_state: str
    timestamp: datetime
    confidence: float
    transition_type: StateTransitionType
    evidences: List[StateEvidence]
    heritage_transfer: float = 0.0


@dataclass
class StatePath:
    """并行状态路径

    跟踪一条可能的状态演进路径。

    Attributes:
        path_id: 路径唯一标识
        states: 路径上的状态序列
        current_state: 当前状态
        confidence: 路径置信度
        age_bars: 路径年龄（K线数）
        evidence_strength: 证据强度总和
        heritage_score: 路径遗产分数
    """

    path_id: str
    states: List[str]
    current_state: str
    confidence: float
    age_bars: int = 0
    evidence_strength: float = 0.0
    heritage_score: float = 0.0

    def add_state(self, state_name: str, confidence: float) -> None:
        """添加状态到路径"""
        self.states.append(state_name)
        self.current_state = state_name
        self.confidence = confidence

    def increment_age(self) -> None:
        """增加路径年龄"""
        self.age_bars += 1


class StateConfig:
    """状态机配置

    包含威科夫状态机的所有可调参数，支持自动进化。

    Attributes:
        SPRING_FAILURE_BARS: Spring失败判定所需K线数
        STATE_TIMEOUT_BARS: 状态超时判定所需K线数
        STATE_MIN_CONFIDENCE: 状态最小置信度
        PATH_MAX_AGE_BARS: 路径最大年龄（K线数）
        PATH_SELECTION_THRESHOLD: 路径选择阈值
        STATE_SWITCH_HYSTERESIS: 状态切换滞后性
        DIRECTION_SWITCH_PENALTY: 方向切换惩罚
    """

    def __init__(self) -> None:
        # 状态重置参数
        self.SPRING_FAILURE_BARS = 5
        self.STATE_TIMEOUT_BARS = 20

        # 非线性检测参数
        self.STATE_MIN_CONFIDENCE = 0.35
        self.PATH_MAX_AGE_BARS = 10
        self.PATH_SELECTION_THRESHOLD = 0.35

        # 状态切换滞后性参数（防止"精神分裂"）
        self.STATE_SWITCH_HYSTERESIS = 0.05
        self.DIRECTION_SWITCH_PENALTY = 0.3

        # 自动进化标识
        self._evolution_params = [
            "SPRING_FAILURE_BARS",
            "STATE_TIMEOUT_BARS",
            "STATE_MIN_CONFIDENCE",
            "PATH_SELECTION_THRESHOLD",
            "STATE_SWITCH_HYSTERESIS",
            "DIRECTION_SWITCH_PENALTY",
        ]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def update_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """从字典更新配置"""
        for key, value in config_dict.items():
            if hasattr(self, key) and key in self._evolution_params:
                setattr(self, key, value)


# ============================================================
# 进化模块类型 - 从 weight_variator_legacy.py 和 evolution/operators.py 提取
# ============================================================


class MutationType(Enum):
    """变异类型枚举

    定义权重变异算法中支持的变异操作类型。
    """

    THRESHOLD_ADJUSTMENT = "THRESHOLD_ADJUSTMENT"  # 阈值调整
    WEIGHT_ADJUSTMENT = "WEIGHT_ADJUSTMENT"  # 权重调整
    PARAMETER_TUNING = "PARAMETER_TUNING"  # 参数调优
    STRUCTURAL_CHANGE = "STRUCTURAL_CHANGE"  # 结构性改变
    COEFFICIENT_ADJUSTMENT = "COEFFICIENT_ADJUSTMENT"  # 系数调整


# ============================================================
# v3.0 新增：统一信号链类型
# 替代 Dict[str, Any] 的散装字典，实现类型安全的全链路传递
# ============================================================


@dataclass
class TradingRangeInfo:
    """TR检测结果"""

    has_range: bool
    support: Optional[float]
    resistance: Optional[float]
    confidence: float
    breakout_direction: Optional[str] = None  # "UP" | "DOWN" | None
    resonance_score: float = 0.0  # 多TF共振分数


@dataclass
class FVGSignal:
    """FVG信号"""

    direction: str  # "BULLISH" | "BEARISH"
    gap_top: float
    gap_bottom: float
    fill_ratio: float
    timestamp: Optional[datetime] = None


@dataclass
class BreakoutInfo:
    """突破验证结果"""

    is_valid: bool
    direction: int  # 1=向上, -1=向下, 0=无
    breakout_level: float
    breakout_strength: float
    volume_confirmation: bool


@dataclass
class PinBodySummary:
    """针体分析汇总"""

    dominant_pattern: str  # "PIN" | "BODY" | "NEUTRAL"
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
class AnomalyEvent:
    """异常事件"""

    event_type: str
    severity: float
    description: str
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerceptionResult:
    """感知层输出 — 替代 Dict[str, Any] 的散装字典"""

    market_regime: str  # "TRENDING" | "RANGING" | "VOLATILE" | "UNKNOWN"
    regime_confidence: float  # 0.0~1.0
    trading_range: Optional[TradingRangeInfo]
    fvg_signals: List[FVGSignal]
    breakout_status: Optional[BreakoutInfo]
    pin_body_summary: Optional[PinBodySummary]
    candle_physical: Optional[CandlePhysicalStats]
    anomaly_events: List[AnomalyEvent]
    timestamp: Optional[datetime] = None


@dataclass
class TimeframeConflict:
    """时间框架冲突"""

    higher_tf: str
    higher_bias: str
    lower_tf: str
    lower_bias: str
    resolution: str  # "follow_higher" | "reduce_size" | "wait"
    confidence_penalty: float


@dataclass
class EntryValidation:
    """微观入场验证"""

    is_valid: bool
    entry_grade: str  # "A" | "B" | "C" | "D"
    m15_confirmation: bool
    m5_confirmation: bool
    optimal_entry_zone: Optional[float] = None


@dataclass
class FusionResult:
    """多周期融合输出"""

    timeframe_weights: Dict[str, float]
    conflicts: List[TimeframeConflict]
    resolved_bias: str  # "BULLISH" | "BEARISH" | "NEUTRAL"
    entry_validation: Optional[EntryValidation]
    timestamp: Optional[datetime] = None


@dataclass
class WyckoffStateResult:
    """状态机输出"""

    current_state: str
    phase: str  # "A" | "B" | "C" | "D" | "E" | "IDLE"
    direction: StateDirection
    confidence: float
    intensity: float
    evidences: List[StateEvidence]
    signal: WyckoffSignal
    signal_strength: str  # "strong" | "medium" | "weak" | "none"
    state_changed: bool
    previous_state: Optional[str]
    heritage_score: float
    critical_levels: Dict[str, float] = field(
        default_factory=dict
    )  # SC_LOW, BC_HIGH, etc.


# ============================================================
# v3.0 新增：进化系统类型
# ============================================================


@dataclass
class BarSignal:
    """逐K线信号 — WyckoffEngine 逐bar产出"""

    bar_index: int
    timestamp: Optional[datetime]
    signal: TradingSignal
    confidence: float
    wyckoff_state: str
    phase: str
    evidences: List[StateEvidence]
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class BacktestTrade:
    """回测交易记录"""

    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    side: str  # "LONG" | "SHORT"
    size: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    hold_bars: int
    entry_state: str
    max_favorable: float  # 最大有利偏移
    max_adverse: float  # 最大不利偏移


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
    config_hash: str  # 配置指纹


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

    train_start: int  # bar索引
    train_end: int
    test_start: int
    test_end: int
    train_result: Optional[BacktestResult] = None
    test_result: Optional[BacktestResult] = None


# ================================================================
# 订单与执行相关类型（Phase 3 新增）
# ================================================================


class OrderSide(Enum):
    """订单方向"""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型"""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(Enum):
    """订单状态"""

    NEW = "new"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass
class OrderRequest:
    """订单请求

    Attributes:
        symbol: 交易对
        side: 买卖方向
        order_type: 订单类型
        size: 下单数量
        price: 价格（限价单必填，市价单可选）
        stop_loss: 止损价格
        take_profit: 止盈价格
        leverage: 杠杆倍数
        metadata: 附加信息（如信号来源、置信度）
    """

    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderResult:
    """订单执行结果

    Attributes:
        order_id: 订单ID
        status: 订单状态
        filled_size: 已成交数量
        filled_price: 成交均价
        timestamp: 成交时间
        raw: 交易所原始返回
        error: 错误信息（仅在失败时）
    """

    order_id: str
    status: OrderStatus
    filled_size: float
    filled_price: float
    timestamp: datetime
    raw: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_filled(self) -> bool:
        """是否完全成交"""
        return self.status == OrderStatus.FILLED

    @property
    def is_error(self) -> bool:
        """是否执行失败"""
        return self.status in (OrderStatus.ERROR, OrderStatus.REJECTED)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "order_id": self.order_id,
            "status": self.status.value,
            "filled_size": self.filled_size,
            "filled_price": self.filled_price,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
        }
