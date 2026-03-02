"""
系统协调器 - 威科夫全自动逻辑引擎的核心调度模块
集成四个阶段的所有模块，实现完整的交易决策流水线

设计目标：
1. 统一调度所有模块，形成完整的交易决策系统
2. 管理实时数据流，从数据输入到交易信号输出
3. 协调自动化进化过程，实现系统的自我优化
4. 提供系统监控和健康检查接口
5. 支持实时交易和回测两种模式

架构流程：
数据输入 → 物理感知层 → 多周期融合 → 状态机决策 → 交易信号 → 自动化进化
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

# 导入所有核心模块
from .data_pipeline import DataPipeline
from .market_regime import RegimeDetector

try:
    from ..perception.fvg_detector import FVGDetector
except ImportError:
    # 备用导入方式
    from perception.fvg_detector import FVGDetector
from .anomaly_validator import AnomalyValidator
from .breakout_validator import BreakoutValidator
from .circuit_breaker import CircuitBreaker
from .curve_boundary import CurveBoundaryFitter

# 导入决策可视化模块
from .decision_visualizer import DecisionVisualizer
from .tr_detector import TRDetector

# 新实现的模块
try:
    from ..perception.candle_physical import (
        CandlePhysical,
        create_candle_from_dataframe_row,
    )
    from ..perception.pin_body_analyzer import (
        AnalysisContext,
        EffortResultType,
        MarketRegimeType,
        PinBodyAnalysisResult,
        analyze_pin_vs_body,
    )
except ImportError:
    # 备用导入方式
    from perception.candle_physical import (
        create_candle_from_dataframe_row,
    )
    from perception.pin_body_analyzer import (
        AnalysisContext,
        MarketRegimeType,
        analyze_pin_vs_body,
    )

from .conflict_resolver import ConflictResolutionManager
from .data_sanitizer import DataSanitizer, DataSanitizerConfig, MarketType

# 导入进化档案员
from .evolution_archivist import EvolutionArchivist, EvolutionEventType
from .micro_entry_validator import MicroEntryValidator

# Note: AccumulationPhase, DistributionPhase, TradingRangeState, WyckoffSignal
# are not directly exported from wyckoff_state_machine
# Using string types instead
from .mistake_book import MistakeBook
from .performance_monitor import (
    ModuleType,
    PerformanceMonitor,
)
from .period_weight_filter import PeriodWeightFilter
from .weight_variator import WeightVariator
from .wfa_backtester import WFABacktester
from .wyckoff_state_machine import EnhancedWyckoffStateMachine, StateConfig

logger = logging.getLogger(__name__)


class SystemMode(Enum):
    """系统运行模式"""

    BACKTEST = "backtest"  # 回测模式
    PAPER_TRADING = "paper"  # 模拟交易模式
    LIVE_TRADING = "live"  # 实盘交易模式
    EVOLUTION = "evolution"  # 进化模式（专注系统优化）


class TradingSignal(Enum):
    """交易信号枚举"""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    WAIT = "wait"  # 等待确认


class WyckoffSignal(Enum):
    """威科夫信号枚举"""

    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"
    NO_SIGNAL = "no_signal"


@dataclass
class DecisionContext:
    """决策上下文 - 包含当前分析的所有相关信息"""

    timestamp: datetime
    market_regime: str
    regime_confidence: float
    timeframe_weights: dict[str, float]
    detected_conflicts: list[dict[str, Any]]
    wyckoff_state: Optional[Any] = None
    wyckoff_confidence: float = 0.0
    breakout_status: Optional[dict[str, Any]] = None
    fvg_signals: list[dict[str, Any]] = field(default_factory=list)
    anomaly_flags: list[dict[str, Any]] = field(default_factory=list)
    circuit_breaker_status: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        import logging

        logger = logging.getLogger(__name__)
        logger.debug("Converting DecisionContext to dict")

        # 修复：时间戳可能是int64类型，需要转换为ISO格式字符串
        if isinstance(self.timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime再格式化为ISO
            timestamp_dt = datetime.fromtimestamp(float(self.timestamp) / 1000.0)
            timestamp_str = timestamp_dt.isoformat()
        else:
            # 如果是datetime对象，直接格式化为ISO
            timestamp_str = self.timestamp.isoformat()

        return {
            "timestamp": timestamp_str,
            "market_regime": self.market_regime,
            "regime_confidence": self.regime_confidence,
            "timeframe_weights": self.timeframe_weights,
            "detected_conflicts": self.detected_conflicts,
            "wyckoff_state": str(self.wyckoff_state) if self.wyckoff_state else None,
            "wyckoff_confidence": self.wyckoff_confidence,
            "breakout_status": self.breakout_status,
            "fvg_signals": self.fvg_signals,
            "anomaly_flags": self.anomaly_flags,
            "circuit_breaker_status": self.circuit_breaker_status,
        }


@dataclass
class TradingDecision:
    """交易决策结果"""

    signal: TradingSignal
    confidence: float
    context: DecisionContext
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    reasoning: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        import logging

        logger = logging.getLogger(__name__)
        logger.debug("Converting TradingDecision to dict")

        # 修复：时间戳可能是int64类型，需要转换为ISO格式字符串
        if isinstance(self.timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime再格式化为ISO
            timestamp_dt = datetime.fromtimestamp(float(self.timestamp) / 1000.0)
            timestamp_str = timestamp_dt.isoformat()
        else:
            # 如果是datetime对象，直接格式化为ISO
            timestamp_str = self.timestamp.isoformat()

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


class SystemOrchestrator:
    """
    系统协调器 - 统一调度所有模块
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """初始化系统协调器"""
        self.config = config or {}
        self.mode = SystemMode(self.config.get("mode", "paper"))

        # 初始化所有模块
        self._init_physical_perception()
        self._init_multitimeframe_fusion()
        self._init_state_machine()
        self._init_automation_evolution()

        # 决策可视化器
        self.decision_visualizer = DecisionVisualizer(
            self.config.get("decision_visualizer", {})
        )

        # 系统状态
        self.is_running = False
        self.start_time = None
        self.decision_history = []
        self.error_history = []
        self.previous_state = None  # 用于跟踪状态变化
        self.last_processed_candle_time = None  # P0-B: 增量喂入状态机

        logger.info(f"SystemOrchestrator initialized in {self.mode.value} mode")

    def _init_physical_perception(self):
        """初始化物理感知层模块"""
        logger.info("Initializing physical perception layer...")

        # 数据管道
        pipeline_config = self.config.get(
            "data_pipeline",
            {
                "redis_host": "localhost",
                "redis_port": 6379,
                "redis_db": 0,
                "cache_ttl": 3600,
            },
        )
        self.data_pipeline = DataPipeline(pipeline_config)

        # 数据清洗器（异常数据处理）
        sanitizer_config = self.config.get(
            "data_sanitizer",
            {
                "market_type": "CRYPTO",  # 默认加密货币市场
                "anomaly_threshold": 0.7,
                "max_volume_ratio": 10.0,
                "max_gap_atr_multiple": 5.0,
                "circuit_breaker_enabled": True,
            },
        )
        self.data_sanitizer = DataSanitizer(DataSanitizerConfig())
        # 应用用户配置
        if "market_type" in sanitizer_config:
            market_type_str = sanitizer_config["market_type"]
            try:
                self.data_sanitizer.market_type = MarketType(market_type_str)
            except ValueError:
                self.data_sanitizer.market_type = MarketType.CRYPTO

        # 市场体制检测
        regime_config = self.config.get(
            "market_regime",
            {
                "min_atr_multiplier": 1.5,
                "max_atr_multiplier": 2.5,
                "adx_threshold": 25,
            },
        )
        self.regime_detector = RegimeDetector(regime_config)

        # FVG检测
        fvg_config = self.config.get(
            "fvg_detector",
            {
                "fvg_threshold": 0.005,
                "min_body_ratio": 0.3,
                "lookback_periods": 50,
            },
        )
        self.fvg_detector = FVGDetector(fvg_config)

        # TR识别
        tr_config = self.config.get(
            "tr_detector",
            {
                "min_trading_range_bars": 20,
                "max_trading_range_bars": 100,
                "stability_threshold": 0.7,
            },
        )
        self.tr_detector = TRDetector(tr_config)

        # 曲线边界拟合
        curve_config = self.config.get(
            "curve_boundary",
            {
                "pivot_lookback": 5,
                "pivot_deviation": 1.0,
                "spline_smoothness": 0.5,
            },
        )
        self.curve_analyzer = CurveBoundaryFitter(curve_config)

        # 突破验证器
        breakout_config = self.config.get(
            "breakout_validator",
            {
                "retrace_threshold": 0.382,
                "min_confirmation_bars": 3,
                "max_retrace_depth": 0.618,
            },
        )
        self.breakout_validator = BreakoutValidator(breakout_config)

        # 异常验证器
        anomaly_config = self.config.get(
            "anomaly_validator",
            {
                "correlation_threshold": 0.7,
                "max_price_gap": 0.05,
                "min_volume_ratio": 0.5,
            },
        )
        self.anomaly_validator = AnomalyValidator(anomaly_config)

        # 熔断机制
        circuit_config = self.config.get(
            "circuit_breaker",
            {
                "max_consecutive_failures": 3,
                "cooldown_period": 300,
                "data_quality_threshold": 0.8,
            },
        )
        self.circuit_breaker = CircuitBreaker(circuit_config)

        logger.info("Physical perception layer initialized")

    def _init_multitimeframe_fusion(self):
        """初始化多周期融合层模块"""
        logger.info("Initializing multitimeframe fusion layer...")

        # 周期权重过滤器
        weight_config = self.config.get(
            "period_weight_filter",
            {
                "base_weights": {
                    "W1": 0.25,
                    "D1": 0.20,
                    "H4": 0.18,
                    "H1": 0.15,
                    "M15": 0.12,
                    "M5": 0.10,
                },
                "min_weight": 0.05,
                "volatility_adjustment": True,
            },
        )
        self.period_filter = PeriodWeightFilter(weight_config)

        # 冲突解决器
        conflict_config = self.config.get(
            "conflict_resolver",
            {
                "risk_adjustment_factor": 0.3,
                "min_confidence_threshold": 0.6,
                "max_position_size": 0.1,
            },
        )
        self.conflict_resolver = ConflictResolutionManager(conflict_config)

        # 微观入场验证器
        entry_config = self.config.get(
            "micro_entry_validator",
            {
                "structure_confirmation_bars": 3,
                "min_volume_spike": 1.5,
                "max_slippage": 0.001,
            },
        )
        self.entry_validator = MicroEntryValidator(entry_config)

        logger.info("Multitimeframe fusion layer initialized")

    def _init_state_machine(self):
        """初始化状态机决策层"""
        logger.info("Initializing state machine layer...")

        state_config_dict = self.config.get(
            "wyckoff_state_machine",
            {
                "transition_confidence": 0.75,
                "min_state_duration": 3,
                "max_state_duration": 20,
                "heritage_decay": 0.95,
            },
        )
        # 创建StateConfig对象
        state_config = StateConfig()
        state_config.update_from_dict(state_config_dict)
        self.state_machine = EnhancedWyckoffStateMachine(state_config)

        logger.info("State machine layer initialized")

    def _init_automation_evolution(self):
        """初始化自动化进化层"""
        logger.info("Initializing automation evolution layer...")

        # 错题本
        mistake_config = self.config.get(
            "mistake_book",
            {
                "max_records": 100,
                "auto_cleanup_days": 7,
                "min_learning_priority": 0.3,
            },
        )
        self.mistake_book = MistakeBook(mistake_config)

        # 权重变异算法
        variator_config = self.config.get(
            "weight_variator",
            {
                "mutation_rate": 0.3,
                "crossover_rate": 0.5,
                "population_size": 10,
                "max_generations": 5,
                "min_improvement": 0.01,
            },
        )
        self.weight_variator = WeightVariator(variator_config)

        # WFA回测引擎
        wfa_config = self.config.get(
            "wfa_backtester",
            {
                "train_days": 60,
                "test_days": 20,
                "step_days": 10,
                "min_performance_improvement": 0.01,
                "max_weight_change": 0.05,
                "smooth_factor": 0.3,
                "stability_threshold": 0.7,
            },
        )
        self.wfa_backtester = WFABacktester(wfa_config)

        # 进化档案员（异步向量化记忆系统）
        archivist_config = self.config.get(
            "evolution_archivist",
            {
                "storage_path": "./evolution_memory.jsonl",
                "max_queue_size": 1000,
                "process_interval": 1.0,
                "similarity_threshold": 0.7,
                "embedding_provider": {
                    "type": "mock",  # 可选: "mock", "openai", "ollama"
                },
            },
        )
        self.evolution_archivist = EvolutionArchivist(archivist_config)

        # 性能监控系统
        monitor_config = self.config.get(
            "performance_monitor",
            {
                "monitoring_interval": 60,
                "auto_recovery_enabled": True,
                "alert_levels": {
                    "WARNING": 0.05,
                    "ERROR": 0.10,
                    "CRITICAL": 0.20,
                },
            },
        )
        self.performance_monitor = PerformanceMonitor(monitor_config)

        # 注册所有模块到性能监控
        self._register_modules_to_monitor()

        logger.info("Automation evolution layer initialized")

    def _register_modules_to_monitor(self):
        """注册所有模块到性能监控系统"""
        modules = [
            ("data_pipeline", ModuleType.DATA_PIPELINE),
            ("data_sanitizer", ModuleType.PERCEPTION),
            ("regime_detector", ModuleType.PERCEPTION),
            ("fvg_detector", ModuleType.PERCEPTION),
            ("tr_detector", ModuleType.PERCEPTION),
            ("curve_analyzer", ModuleType.PERCEPTION),
            ("breakout_validator", ModuleType.PERCEPTION),
            ("anomaly_validator", ModuleType.PERCEPTION),
            ("circuit_breaker", ModuleType.PERCEPTION),
            ("period_filter", ModuleType.MULTITIMEFRAME),
            ("conflict_resolver", ModuleType.MULTITIMEFRAME),
            ("entry_validator", ModuleType.MULTITIMEFRAME),
            ("state_machine", ModuleType.STATEMACHINE),
            ("mistake_book", ModuleType.EVOLUTION),
            ("weight_variator", ModuleType.EVOLUTION),
            ("wfa_backtester", ModuleType.EVOLUTION),
            ("evolution_archivist", ModuleType.EVOLUTION),
        ]

        for module_name, module_type in modules:
            module_instance = getattr(self, module_name, None)
            if module_instance:
                self.performance_monitor.register_module(
                    module_name, module_type, module_instance
                )

    async def start(self):
        """启动系统"""
        if self.is_running:
            logger.warning("System is already running")
            return

        logger.info("Starting system orchestrator...")
        self.is_running = True
        self.start_time = datetime.now()

        # 进化档案员仅在 EVOLUTION 专用模式下启动后台线程
        # paper/live 交易模式下不启动，避免抢占 IO 并干扰交易决策路径
        if self.mode == SystemMode.EVOLUTION:
            self.evolution_archivist.start()
            logger.info("EvolutionArchivist backend thread started (EVOLUTION mode)")
        else:
            logger.info(
                f"EvolutionArchivist backend thread skipped in {self.mode.value} mode"
            )

        # 启动性能监控
        self.performance_monitor.start_monitoring()

        logger.info(f"System orchestrator started at {self.start_time}")

    async def stop(self):
        """停止系统"""
        if not self.is_running:
            logger.warning("System is not running")
            return

        logger.info("Stopping system orchestrator...")
        self.is_running = False

        # 仅在 EVOLUTION 模式下停止后台线程（与 start 保持对称）
        if self.mode == SystemMode.EVOLUTION:
            self.evolution_archivist.stop()

        # 停止性能监控
        self.performance_monitor.stop_monitoring()

        # 保存系统状态
        self._save_system_state()

        logger.info("System orchestrator stopped")

    async def process_market_data(
        self, symbol: str, timeframes: list[str], data_dict: dict[str, pd.DataFrame]
    ) -> TradingDecision:
        """
        处理市场数据，生成交易决策
        """
        logger.info(f"Processing market data for {symbol}")

        try:
            # 1. 检查熔断器
            if self.circuit_breaker.should_trip("data_processing"):
                logger.warning("Circuit breaker triggered, skipping processing")
                return TradingDecision(
                    signal=TradingSignal.WAIT,
                    confidence=0.0,
                    context=DecisionContext(
                        timestamp=datetime.now(),
                        market_regime="unknown",
                        regime_confidence=0.0,
                        timeframe_weights={},
                        detected_conflicts=[],
                    ),
                    reasoning=["Circuit breaker triggered"],
                )

            # 2. 验证数据质量
            validated_data = await self._validate_and_preprocess_data(
                symbol, timeframes, data_dict
            )

            # 3. 物理感知层分析
            perception_results = await self._run_physical_perception(
                symbol, validated_data
            )

            # 4. 多周期融合分析
            fusion_results = await self._run_multitimeframe_fusion(
                symbol, validated_data, perception_results
            )

            # 5. 状态机决策
            state_results = await self._run_state_machine_decision(
                symbol, validated_data, perception_results, fusion_results
            )

            # 6. 生成交易决策
            decision = await self._generate_trading_decision(
                symbol, perception_results, fusion_results, state_results
            )

            # 7. 记录决策历史
            self.decision_history.append(decision)

            # 8. 更新性能监控
            self.performance_monitor.record_success("system_orchestrator")

            logger.info(
                f"Decision generated: {decision.signal.value} "
                f"(confidence: {decision.confidence:.2f})"
            )

            return decision

        except Exception as e:
            logger.exception("Error processing market data")
            self.error_history.append(
                {
                    "timestamp": datetime.now(),
                    "error": str(e),
                    "symbol": symbol,
                }
            )

            # 记录错误到错题本
            self._record_error_to_mistake_book(e, symbol)

            # 更新性能监控
            self.performance_monitor.record_error("system_orchestrator", str(e))

            return TradingDecision(
                signal=TradingSignal.WAIT,
                confidence=0.0,
                context=DecisionContext(
                    timestamp=datetime.now(),
                    market_regime="unknown",
                    regime_confidence=0.0,
                    timeframe_weights={},
                    detected_conflicts=[],
                ),
                reasoning=[f"Processing error: {e!s}"],
            )

    def _convert_timestamps_to_unix_ms(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        将DataFrame索引从Timestamp对象转换为Unix毫秒整数（int64）

        根据TECH_SPECS.md规范，系统内部应使用Unix毫秒整数进行时间比较
        避免Timestamp对象与int之间的类型错误
        """
        if df.empty:
            return df

        df_copy = df.copy()

        try:
            # 检查索引类型
            if isinstance(df_copy.index, pd.DatetimeIndex):
                # 将DatetimeIndex转换为Unix毫秒整数
                # pandas Timestamp对象转换为int64得到的是纳秒，需要除以10^6得到毫秒
                unix_ms_index = df_copy.index.astype("int64") // 10**6  # 纳秒转毫秒
                df_copy.index = unix_ms_index.astype("int64")
                logger.debug(
                    f"转换索引: DatetimeIndex -> Unix毫秒整数 (int64), 样本: {df_copy.index[0] if len(df_copy) > 0 else 'N/A'}"
                )
            elif (
                hasattr(df_copy.index, "dtype")
                and df_copy.index.dtype == "datetime64[ns]"
            ):
                # 处理datetime64类型的索引
                unix_ms_index = df_copy.index.astype("int64") // 10**6
                df_copy.index = unix_ms_index.astype("int64")
                logger.debug(
                    f"转换索引: datetime64[ns] -> Unix毫秒整数 (int64), 样本: {df_copy.index[0] if len(df_copy) > 0 else 'N/A'}"
                )
            elif hasattr(df_copy.index, "dtype") and (
                df_copy.index.dtype in {"int64", "int32"}
            ):
                # 已经是整数类型，确保是int64
                df_copy.index = df_copy.index.astype("int64")
                logger.debug(
                    f"索引已为整数类型，确保为int64, 样本: {df_copy.index[0] if len(df_copy) > 0 else 'N/A'}"
                )
            else:
                logger.warning(
                    f"无法识别的索引类型: {type(df_copy.index)}, dtype: {getattr(df_copy.index, 'dtype', 'N/A')}, 保持原样"
                )

        except Exception:
            logger.exception("时间戳转换失败, 保持原始数据")
            return df

        return df_copy

    async def _validate_and_preprocess_data(
        self, symbol: str, timeframes: list[str], data_dict: dict[str, pd.DataFrame]
    ) -> dict[str, pd.DataFrame]:
        """验证和预处理数据"""
        validated_data = {}
        anomaly_events_by_timeframe = {}

        for timeframe in timeframes:
            if timeframe not in data_dict:
                logger.warning(f"Missing data for timeframe {timeframe}")
                continue

            data = data_dict[timeframe].copy()

            # 保持 DatetimeIndex 不变，下游模块（TR/FVG/可视化）均依赖 DatetimeIndex
            # 注：旧版曾将 DatetimeIndex 转为 int64，导致所有下游时间轴错乱，已移除

            # 使用数据清洗器检测异常
            try:
                # DataSanitizer接受DataFrame并返回清洗后的DataFrame和异常事件列表
                processed_df, anomalies = self.data_sanitizer.sanitize_dataframe(
                    df=data,
                    symbol=symbol,
                    exchange="binance",  # 默认为Binance，可根据配置调整
                )

                if anomalies:
                    logger.warning(
                        f"在{timeframe}时间框架检测到{len(anomalies)}个异常事件"
                    )
                    anomaly_events_by_timeframe[timeframe] = anomalies

                    # 记录异常事件到系统状态
                    for anomaly in anomalies:
                        self.error_history.append(
                            {
                                "timestamp": anomaly.raw_candle.timestamp,
                                "timeframe": timeframe,
                                "symbol": symbol,
                                "anomaly_type": anomaly.anomaly_types,
                                "event_category": anomaly.event_category,
                                "suggested_action": anomaly.suggested_action,
                            }
                        )

                # P0-C 修复: 调用 DataPipeline.validate_data_quality 进行数据质量验证
                try:
                    quality_result = self.data_pipeline.validate_data_quality(
                        processed_df, symbol
                    )
                    if not quality_result["is_valid"]:
                        logger.warning(
                            f"{timeframe} 数据质量问题: {quality_result['issues']}"
                        )
                    else:
                        logger.debug(
                            f"{timeframe} 数据质量正常: {quality_result['data_points']} 根K线"
                        )
                except Exception as e:
                    logger.warning(f"DataPipeline质量验证失败 {timeframe}: {e}")

                validated_data[timeframe] = processed_df

            except Exception:
                logger.exception(f"数据清洗失败 {timeframe}, 使用原始数据")
                validated_data[timeframe] = data.copy()

        # 如果有异常事件，可以传递给状态机分析
        if anomaly_events_by_timeframe:
            self._process_anomaly_events(anomaly_events_by_timeframe, symbol)

        # P0-C 修复: 调用 DataPipeline.align_timeframes 进行多周期节奏对齐（Rhythm Sync）
        # 大周期定方向，小周期定时机 — 将跨周期特征列合并到主时间框架数据
        try:
            from .data_pipeline import Timeframe as PipelineTF

            # 将 orchestrator 字符串键映射到 DataPipeline Timeframe 枚举
            _tf_str_to_enum = {
                "W": PipelineTF.W1,
                "D": PipelineTF.D1,
                "H4": PipelineTF.H4,
                "H1": PipelineTF.H1,
                "M15": PipelineTF.M15,
                "M5": PipelineTF.M5,
            }
            _tf_enum_dict = {
                _tf_str_to_enum[k]: v
                for k, v in validated_data.items()
                if k in _tf_str_to_enum and not v.empty
            }

            if len(_tf_enum_dict) >= 2:
                # 选取主时间框架作为对齐基准
                primary_tf_str = (
                    "H4" if "H4" in validated_data else next(iter(validated_data))
                )
                target_tf_enum = _tf_str_to_enum.get(primary_tf_str, PipelineTF.H4)
                # align_timeframes 是同步方法，将各周期数据重采样并附加为前缀列
                aligned_df = self.data_pipeline.align_timeframes(
                    _tf_enum_dict, target_tf_enum
                )
                if not aligned_df.empty and len(aligned_df) > 0:
                    validated_data[primary_tf_str] = aligned_df
                    extra_cols = [
                        c for c in aligned_df.columns
                        if c not in ("open", "high", "low", "close", "volume")
                    ]
                    logger.info(
                        f"DataPipeline Rhythm Sync 完成: 对齐至 {primary_tf_str}, "
                        f"新增跨周期列 {len(extra_cols)} 个: {extra_cols[:5]}"
                    )
        except Exception as e:
            logger.warning(f"DataPipeline align_timeframes 失败（跳过节奏对齐）: {e}")

        return validated_data

    def _process_anomaly_events(
        self, anomaly_events_by_timeframe: dict[str, list[Any]], symbol: str
    ):
        """处理异常事件，传递给状态机分析"""
        logger.info(f"处理{symbol}的异常事件")

        for timeframe, anomalies in anomaly_events_by_timeframe.items():
            logger.info(f"  {timeframe}: {len(anomalies)}个异常事件")

            for anomaly in anomalies:
                if hasattr(anomaly, "to_state_machine_input"):
                    try:
                        anomaly.to_state_machine_input()
                        # 这里可以将异常事件传递给状态机进行分析
                        # 例如：self.state_machine.process_anomaly_event(state_machine_input)
                        logger.debug(
                            f"    异常事件: {anomaly.event_category}, 建议: {anomaly.suggested_action}"
                        )
                    except Exception as e:
                        logger.warning(f"处理异常事件失败: {e}")

    def _calculate_candle_statistics(self, data: pd.DataFrame) -> dict[str, Any]:
        """计算K线统计数据，供针vs实体分析使用"""
        if len(data) < 20:
            return {"volatility_index": 1.0, "volume_ma20": 1.0, "avg_body_size": 1.0}

        try:
            # 计算ATR（平均真实范围）
            high_low = data["high"] - data["low"]
            high_close = abs(data["high"] - data["close"].shift(1))
            low_close = abs(data["low"] - data["close"].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            # 安全地获取iloc值
            tr_rolling_14 = tr.rolling(14).mean()
            atr14 = float(tr_rolling_14.values[-1]) if len(tr_rolling_14) > 0 else 1.0
            tr_rolling_50 = tr.rolling(50).mean()
            avg_atr = (
                float(tr_rolling_50.values[-1])
                if len(data) >= 50 and len(tr_rolling_50) > 0
                else atr14
            )

            # 波动率指数：当前ATR/平均ATR
            volatility_index = atr14 / avg_atr if avg_atr > 0 else 1.0

            # 成交量移动平均
            volume_rolling_20 = data["volume"].rolling(20).mean()
            volume_ma20 = (
                float(volume_rolling_20.values[-1])
                if len(volume_rolling_20) > 0
                else 1.0
            )

            # 平均实体大小
            body_sizes = abs(data["close"] - data["open"])
            avg_body_size = float(body_sizes.mean())

            # 简单趋势判断
            if len(data) >= 50:
                ma50 = data["close"].rolling(50).mean()
                current_close = (
                    float(data["close"].values[-1]) if len(data) > 0 else 0.0
                )
                ma50_last = float(ma50.values[-1]) if len(ma50) > 0 else current_close
                trend = "UPTREND" if current_close > ma50_last else "DOWNTREND"
                trend_strength = (
                    abs(current_close - ma50_last) / ma50_last if ma50_last > 0 else 0.0
                )
            else:
                trend = "NEUTRAL"
                trend_strength = 0.0

            return {
                "volatility_index": volatility_index,
                "volume_ma20": volume_ma20,
                "avg_body_size": avg_body_size,
                "atr14": atr14,
                "previous_close": float(data["close"].values[-2])
                if len(data) >= 2
                else None,
                "trend": trend,
                "trend_strength": trend_strength,
            }
        except Exception as e:
            logger.warning(f"计算K线统计数据失败: {e}")
            return {"volatility_index": 1.0, "volume_ma20": 1.0, "avg_body_size": 1.0}

    def _summarize_pin_body_analysis(
        self, results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """汇总针vs实体分析结果"""
        if not results:
            return {}

        pin_dominant_count = sum(1 for r in results if r.get("is_pin_dominant", False))
        body_dominant_count = sum(
            1 for r in results if r.get("is_body_dominant", False)
        )
        neutral_count = len(results) - pin_dominant_count - body_dominant_count

        avg_pin_strength = np.mean(
            [
                r.get("pin_strength", 0)
                for r in results
                if r.get("is_pin_dominant", False)
            ]
            or [0]
        )
        avg_body_strength = np.mean(
            [
                r.get("body_strength", 0)
                for r in results
                if r.get("is_body_dominant", False)
            ]
            or [0]
        )
        avg_confidence = np.mean([r.get("confidence", 0) for r in results])

        return {
            "total_candles": len(results),
            "pin_dominant_percent": pin_dominant_count / len(results) * 100,
            "body_dominant_percent": body_dominant_count / len(results) * 100,
            "neutral_percent": neutral_count / len(results) * 100,
            "avg_pin_strength": avg_pin_strength,
            "avg_body_strength": avg_body_strength,
            "avg_confidence": avg_confidence,
            "dominant_pattern": "PIN"
            if pin_dominant_count > body_dominant_count
            else "BODY"
            if body_dominant_count > pin_dominant_count
            else "NEUTRAL",
        }

    def _calculate_candle_physical_stats(self, data: pd.DataFrame) -> dict[str, Any]:
        """计算K线物理属性统计"""
        if len(data) < 10:
            return {}

        try:
            # 创建CandlePhysical对象列表
            candles = []
            for _, row in data.iloc[-10:].iterrows():  # 分析最近10根K线
                candle = create_candle_from_dataframe_row(row)
                candles.append(candle)

            # 计算统计信息
            body_sizes = [c.body for c in candles]
            shadow_sizes = [c.total_shadow for c in candles]
            body_ratios = [c.body_ratio for c in candles]

            # 形态统计
            doji_count = sum(1 for c in candles if c.is_doji)
            marubozu_count = sum(1 for c in candles if c.is_marubozu)
            hammer_count = sum(1 for c in candles if c.is_hammer)
            shooting_star_count = sum(1 for c in candles if c.is_shooting_star)

            return {
                "avg_body_size": np.mean(body_sizes) if body_sizes else 0,
                "avg_shadow_size": np.mean(shadow_sizes) if shadow_sizes else 0,
                "avg_body_ratio": np.mean(body_ratios) if body_ratios else 0,
                "doji_percent": doji_count / len(candles) * 100,
                "marubozu_percent": marubozu_count / len(candles) * 100,
                "hammer_percent": hammer_count / len(candles) * 100,
                "shooting_star_percent": shooting_star_count / len(candles) * 100,
                "sample_size": len(candles),
            }
        except Exception as e:
            logger.warning(f"计算K线物理属性统计失败: {e}")
            return {}

    async def _run_physical_perception(
        self, symbol: str, data_dict: dict[str, pd.DataFrame]
    ) -> dict[str, Any]:
        """运行物理感知层分析 - 使用实际模块实现"""
        logger.info("Running physical perception analysis with real modules...")

        # 使用最新数据（通常使用H4或D1）
        primary_tf = "H4" if "H4" in data_dict else next(iter(data_dict.keys()))
        primary_data = data_dict[primary_tf]

        # 初始化结果字典
        perception_results = {
            "market_regime": {"regime": "unknown", "confidence": 0.0},
            "trading_range": {"has_trading_range": False, "breakout_direction": None},
            "curve_boundary": {"has_curve": False, "curve_type": "none"},
            "fvg_signals": {"has_fvg": False, "fvg_signals": []},
            "breakout_status": None,
            "pin_body_analysis": {},
            "candle_physical_stats": {},
            "primary_timeframe": primary_tf,
            "primary_data": primary_data,  # 存储主时间框架数据供后续使用
        }

        try:
            # 1. 市场体制检测
            try:
                regime_result = self.regime_detector.detect_regime(primary_data)
                # 获取regime枚举对象，然后转换为字符串
                regime_enum = regime_result.get("regime")
                regime_str = (
                    regime_enum.value
                    if hasattr(regime_enum, "value")
                    else str(regime_enum)
                )

                perception_results["market_regime"] = {
                    "regime": regime_str,  # 存储为字符串
                    "confidence": regime_result.get("confidence", 0.0),
                    "details": regime_result.get("details", {}),
                }
                logger.info(
                    f"市场体制: {regime_str} (置信度: {regime_result.get('confidence', 0.0):.2f})"
                )
            except Exception as e:
                logger.warning(f"市场体制检测失败: {e}")

            # 2. 计算统计数据供针vs实体分析使用
            stats = self._calculate_candle_statistics(primary_data)

            # 3. TR识别（交易区间）
            try:
                tr_result = self.tr_detector.detect_trading_range(primary_data)
                if tr_result is not None:
                    perception_results["trading_range"] = {
                        "has_trading_range": True,
                        "breakout_direction": tr_result.breakout_direction.value
                        if tr_result.breakout_direction
                        else None,
                        "support": tr_result.lower_boundary,
                        "resistance": tr_result.upper_boundary,
                        "quality_score": tr_result.confidence,
                    }
                    logger.info(
                        f"TR识别: 支撑={tr_result.lower_boundary:.2f}, 阻力={tr_result.upper_boundary:.2f}"
                    )

                    # 触发TR检测可视化
                    try:
                        self.decision_visualizer.visualize_tr_detection(
                            data=primary_data,
                            symbol=symbol,
                            tr_result={
                                "detected": True,
                                "support": tr_result.lower_boundary,
                                "resistance": tr_result.upper_boundary,
                                "breakout_direction": tr_result.breakout_direction.value
                                if tr_result.breakout_direction
                                else None,
                                "confidence": tr_result.confidence,
                            },
                            geometric_analyzer=self.curve_analyzer,
                            timeframe=primary_tf,
                        )
                        logger.info(f"TR检测可视化已触发: {symbol}")
                    except Exception as viz_error:
                        logger.warning(f"TR检测可视化失败: {viz_error}")
                else:
                    perception_results["trading_range"] = {
                        "has_trading_range": False,
                        "breakout_direction": None,
                        "support": None,
                        "resistance": None,
                        "quality_score": 0.0,
                    }
            except Exception as e:
                logger.warning(f"TR识别失败: {e}")

            # 3.5 P2-A 修复：多周期TR共振检测
            # 在每个可用时间框架独立检测TR，计算支撑/阻力共振区（多周期重叠=高置信度）
            try:
                tr_by_timeframe = {}
                for _tf, _tf_data in data_dict.items():
                    if _tf == primary_tf:
                        continue  # 主时间框架已在上方检测，跳过
                    if len(_tf_data) < 50:
                        continue
                    try:
                        _tf_tr = self.tr_detector.detect_trading_range(_tf_data)
                        if _tf_tr is not None:
                            tr_by_timeframe[_tf] = {
                                "support": _tf_tr.lower_boundary,
                                "resistance": _tf_tr.upper_boundary,
                                "confidence": _tf_tr.confidence,
                            }
                    except Exception:
                        pass

                if tr_by_timeframe:
                    # 收集所有时间框架的支撑/阻力（含主时间框架）
                    _all_supports = [v["support"] for v in tr_by_timeframe.values() if v["support"] is not None]
                    _all_resistances = [v["resistance"] for v in tr_by_timeframe.values() if v["resistance"] is not None]
                    _primary_tr = perception_results.get("trading_range", {})
                    if _primary_tr.get("support") is not None:
                        _all_supports.append(_primary_tr["support"])
                    if _primary_tr.get("resistance") is not None:
                        _all_resistances.append(_primary_tr["resistance"])

                    _resonance_support = None
                    _resonance_resistance = None
                    _resonance_score = 0.0

                    # 支撑位共振：多周期支撑位相近（标准差/均值 < 5%）
                    if len(_all_supports) >= 2:
                        _support_mean = float(np.mean(_all_supports))
                        _support_spread = float(np.std(_all_supports)) / _support_mean if _support_mean > 0 else 1.0
                        if _support_spread < 0.05:
                            _resonance_support = _support_mean
                            _resonance_score += 0.5

                    # 阻力位共振：同理
                    if len(_all_resistances) >= 2:
                        _resistance_mean = float(np.mean(_all_resistances))
                        _resistance_spread = float(np.std(_all_resistances)) / _resistance_mean if _resistance_mean > 0 else 1.0
                        if _resistance_spread < 0.05:
                            _resonance_resistance = _resistance_mean
                            _resonance_score += 0.5

                    perception_results["tr_resonance"] = {
                        "timeframes_detected": list(tr_by_timeframe.keys()),
                        "resonance_support": _resonance_support,
                        "resonance_resistance": _resonance_resistance,
                        "resonance_score": _resonance_score,
                        "tr_by_timeframe": tr_by_timeframe,
                    }

                    # 共振强支撑/阻力追加到主TR结果，供下游感知层使用
                    if _resonance_score >= 1.0 and _resonance_support is not None and _resonance_resistance is not None:
                        perception_results["trading_range"]["resonance_support"] = _resonance_support
                        perception_results["trading_range"]["resonance_resistance"] = _resonance_resistance
                        logger.info(
                            f"多周期TR完全共振: 支撑 {_resonance_support:.2f}, 阻力 {_resonance_resistance:.2f}"
                            f" (共振分: {_resonance_score:.1f}, 参与框架: {list(tr_by_timeframe.keys())})"
                        )
                    elif _resonance_score > 0:
                        logger.info(
                            f"多周期TR部分共振: 参与框架 {list(tr_by_timeframe.keys())}"
                            f" (共振分: {_resonance_score:.1f})"
                        )
            except Exception as e:
                logger.warning(f"多周期TR共振检测失败（跳过）: {e}")

            # 4. 曲线边界拟合
            try:
                if len(primary_data) >= 20:  # 需要足够数据点
                    curve_result = self.curve_analyzer.detect_trading_range(
                        primary_data["high"], primary_data["low"], primary_data["close"]
                    )
                    if curve_result is not None:
                        perception_results["curve_boundary"] = {
                            "has_curve": True,
                            "curve_type": curve_result.get("upper_boundary", {}).get(
                                "boundary_type", "unknown"
                            ),
                            "boundary_lines": [],  # 暂时留空
                            "quality_score": curve_result.get("tr_confidence", 0.0),
                        }
                    else:
                        perception_results["curve_boundary"] = {
                            "has_curve": False,
                            "curve_type": "none",
                            "boundary_lines": [],
                            "quality_score": 0.0,
                        }
            except Exception as e:
                logger.warning(f"曲线边界拟合失败: {e}")

            # 5. FVG检测
            try:
                fvg_result = self.fvg_detector.detect_fvg_gaps(primary_data)
                perception_results["fvg_signals"] = {
                    "has_fvg": len(fvg_result) > 0,
                    "fvg_signals": fvg_result,
                    "total_fvg_count": len(fvg_result),
                }
                if fvg_result:
                    logger.info(f"FVG检测: 发现{len(fvg_result)}个信号")
            except Exception as e:
                logger.warning(f"FVG检测失败: {e}")

            # 6. 突破验证
            try:
                # 获取最新价格数据
                latest_prices = (
                    primary_data.iloc[-30:] if len(primary_data) >= 30 else primary_data
                )
                breakout_result = self.breakout_validator.detect_initial_breakout(
                    df=latest_prices,
                    support_level=perception_results["trading_range"].get("support"),
                    resistance_level=perception_results["trading_range"].get(
                        "resistance"
                    ),
                    current_atr=stats.get("atr14", 1.0),
                )
                perception_results["breakout_status"] = breakout_result
                if breakout_result and breakout_result.get("is_valid"):
                    logger.info(
                        f"突破验证: {breakout_result.get('direction')}突破 (置信度: {breakout_result.get('confidence', 0.0):.2f})"
                    )
            except Exception as e:
                logger.warning(f"突破验证失败: {e}")

            # 7. 针vs实体分析（对最近3根K线）
            try:
                recent_candles = (
                    primary_data.iloc[-3:] if len(primary_data) >= 3 else primary_data
                )
                pin_body_results = []

                for i, row in recent_candles.iterrows():
                    # 创建CandlePhysical对象
                    candle = create_candle_from_dataframe_row(row)

                    # 准备分析上下文
                    # 安全地转换market_regime为枚举
                    market_regime_str = perception_results["market_regime"]["regime"]
                    market_regime_enum = MarketRegimeType.UNKNOWN

                    if market_regime_str and market_regime_str != "unknown":
                        try:
                            # 确保字符串是大写的，以匹配枚举值
                            market_regime_str_upper = market_regime_str.upper()
                            market_regime_enum = MarketRegimeType(
                                market_regime_str_upper
                            )
                        except ValueError:
                            # 如果无法转换为有效的枚举，使用UNKNOWN
                            logger.warning(
                                f"无法识别的市场体制: {market_regime_str}, 使用UNKNOWN"
                            )
                            market_regime_enum = MarketRegimeType.UNKNOWN

                    context = AnalysisContext(
                        volatility_index=stats.get("volatility_index", 1.0),
                        market_regime=market_regime_enum,
                        volume_moving_avg=stats.get("volume_ma20", 1.0),
                        avg_body_size=stats.get("avg_body_size", 1.0),
                        previous_close=stats.get("previous_close"),
                        atr14=stats.get("atr14", 1.0),
                        tr_support=perception_results["trading_range"].get("support"),
                        tr_resistance=perception_results["trading_range"].get(
                            "resistance"
                        ),
                        trend=stats.get("trend", "NEUTRAL"),
                        trend_strength=stats.get("trend_strength", 0.0),
                    )

                    # 进行分析
                    result = analyze_pin_vs_body(candle, context)
                    pin_body_results.append(
                        {
                            "timestamp": i if isinstance(i, datetime) else row.name,
                            "is_pin_dominant": result.is_pin_dominant,
                            "is_body_dominant": result.is_body_dominant,
                            "pin_strength": result.pin_strength,
                            "body_strength": result.body_strength,
                            "effort_vs_result": result.effort_vs_result.value
                            if result.effort_vs_result
                            else None,
                            "confidence": result.confidence,
                        }
                    )

                perception_results["pin_body_analysis"] = {
                    "recent_results": pin_body_results,
                    "summary": self._summarize_pin_body_analysis(pin_body_results),
                }

            except Exception as e:
                logger.warning(f"针vs实体分析失败: {e}")

            # 8. K线物理属性统计
            try:
                physical_stats = self._calculate_candle_physical_stats(primary_data)
                perception_results["candle_physical_stats"] = physical_stats
            except Exception as e:
                logger.warning(f"K线物理属性统计失败: {e}")

        except Exception:
            logger.exception("物理感知层分析整体失败")

        return perception_results

    async def _run_multitimeframe_fusion(
        self,
        symbol: str,
        data_dict: dict[str, pd.DataFrame],
        perception_results: dict[str, Any],
    ) -> dict[str, Any]:
        """运行多周期融合分析"""
        logger.info("Running multitimeframe fusion analysis...")

        # 获取市场体制
        regime = perception_results["market_regime"]["regime"]
        regime_confidence = perception_results["market_regime"]["confidence"]

        # 1. 调用 PeriodWeightFilter 计算动态权重（基于市场体制）
        try:
            from .period_weight_filter import Timeframe
            raw_weights = self.period_filter.get_weights(regime)
            # 转换为字符串键，只保留当前可用的时间框架
            available_tfs = set(data_dict.keys())
            timeframe_weights = {
                tf.value: w
                for tf, w in raw_weights.items()
                if tf.value in available_tfs
            }
            # 归一化（只对可用周期）
            total_w = sum(timeframe_weights.values())
            if total_w > 0:
                timeframe_weights = {k: v / total_w for k, v in timeframe_weights.items()}
            logger.info(f"周期权重（{regime}体制）: {timeframe_weights}")
        except Exception as e:
            logger.warning(f"PeriodWeightFilter调用失败，使用默认权重: {e}")
            timeframe_weights = {"H4": 0.5, "H1": 0.3, "M15": 0.2}

        # 2. 从各时间框架真实数据计算各自趋势方向（供冲突检测使用）
        # 修复：不能所有周期都用同一 regime 标签，否则冲突检测永远盲
        def _tf_trend_state(df: pd.DataFrame) -> tuple[str, float]:
            """用MA20/MA50交叉计算该时间框架的趋势方向和置信度"""
            if len(df) < 20:
                return "NEUTRAL", 0.4
            close = df["close"]
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(min(50, len(df))).mean().iloc[-1])
            last_close = float(close.iloc[-1])
            # 趋势判定：ma20 > ma50 且价格 > ma20 → BULLISH
            if ma20 > ma50 and last_close > ma20:
                gap = (ma20 - ma50) / ma50 if ma50 > 0 else 0
                conf = min(0.9, 0.5 + gap * 10)
                return "BULLISH", conf
            elif ma20 < ma50 and last_close < ma20:
                gap = (ma50 - ma20) / ma50 if ma50 > 0 else 0
                conf = min(0.9, 0.5 + gap * 10)
                return "BEARISH", conf
            else:
                return "NEUTRAL", 0.4

        timeframe_states: dict = {}
        for tf, df in data_dict.items():
            state_label, tf_conf = _tf_trend_state(df)
            timeframe_states[tf] = {"state": state_label, "confidence": tf_conf}

        logger.info(f"各时间框架状态: { {k: v['state'] for k, v in timeframe_states.items()} }")

        # 3. 调用 ConflictResolutionManager 检测并解决冲突
        try:
            from datetime import datetime as _dt
            # 计算回调深度（用于冲突解决逻辑）
            _h4_candidate = data_dict.get("H4")
            h4_df = _h4_candidate if (_h4_candidate is not None and not _h4_candidate.empty) else data_dict.get(next(iter(data_dict)))
            correction_depth = 0.0
            volume_on_correction = "NORMAL"
            if h4_df is not None and len(h4_df) >= 10:
                recent = h4_df.iloc[-10:]
                high_max = float(recent["high"].max())
                low_min = float(recent["low"].min())
                last_close = float(recent["close"].iloc[-1])
                if high_max > low_min:
                    correction_depth = (high_max - last_close) / (high_max - low_min)
                avg_vol = float(recent["volume"].mean())
                last_vol = float(recent["volume"].iloc[-1])
                if avg_vol > 0:
                    vol_ratio = last_vol / avg_vol
                    volume_on_correction = "LOW_VOLUME" if vol_ratio < 0.7 else (
                        "HIGH_VOLUME" if vol_ratio > 1.5 else "NORMAL"
                    )

            market_context = {
                "regime": regime,
                "timestamp": _dt.now().isoformat(),
                "correction_depth": correction_depth,
                "volume_on_correction": volume_on_correction,
            }
            conflict_resolution = self.conflict_resolver.resolve_conflict(
                timeframe_states, market_context
            )
            conflict_type = conflict_resolution.get("conflict_type", "NO_CONFLICT")
            conflicts = [] if conflict_type == "NO_CONFLICT" else [conflict_resolution]
            resolved_decisions = [conflict_resolution]
            logger.info(f"冲突检测结果: {conflict_type}, 偏向: {conflict_resolution.get('primary_bias')}")
        except Exception as e:
            logger.warning(f"ConflictResolutionManager调用失败: {e}")
            conflicts = []
            resolved_decisions = []

        # 4. 调用 MicroEntryValidator（如果有M15数据和有效突破结构）
        # 修复：breakout_validator 真实输出key是 "direction"(int 1/-1)，不是 "has_breakout"
        entry_validation = None
        try:
            m15_data = data_dict.get("M15")
            breakout_status = perception_results.get("breakout_status")
            # 判断是否有真实突破：direction 为 1（上涨突破）或 -1（下跌突破），且有 breakout_level
            breakout_direction_int = breakout_status.get("direction") if breakout_status else None
            breakout_level = breakout_status.get("breakout_level") if breakout_status else None
            has_valid_breakout = (
                m15_data is not None
                and len(m15_data) >= 10
                and breakout_status is not None
                and breakout_direction_int in (1, -1)
                and breakout_level is not None
                and breakout_level > 0
            )
            if has_valid_breakout:
                # 将 int direction 转为 MicroEntryValidator 期望的字符串方向
                structure_direction = "RESISTANCE" if breakout_direction_int == 1 else "SUPPORT"
                # 结构类型：有突破强度较高时认为是 CREEK（溪流）突破；否则 PIVOT
                breakout_strength = breakout_status.get("breakout_strength", 0.5)
                structure_type = "CREEK" if breakout_strength >= 1.0 else "PIVOT"
                # 置信度：基于成交量确认和突破强度
                volume_conf = breakout_status.get("volume_confirmation", False)
                confidence = min(0.95, 0.6 + breakout_strength * 0.1 + (0.1 if volume_conf else 0.0))
                h4_structure = {
                    "type": structure_type,
                    "price_level": float(breakout_level),
                    "direction": structure_direction,
                    "confidence": confidence,
                }
                macro_bias = resolved_decisions[0].get("primary_bias", "NEUTRAL") if resolved_decisions else "NEUTRAL"
                if hasattr(macro_bias, "value"):
                    macro_bias = macro_bias.value
                elif not isinstance(macro_bias, str):
                    macro_bias = str(macro_bias)
                # 将 BULLISH/BEARISH/DEFERRED 映射为 MicroEntryValidator 期望的值
                if macro_bias not in ("BULLISH", "BEARISH", "NEUTRAL"):
                    macro_bias = "NEUTRAL"
                entry_validation = self.entry_validator.validate_entry(
                    h4_structure=h4_structure,
                    m15_data=m15_data,
                    m5_data=data_dict.get("M5"),
                    macro_bias=macro_bias,
                    market_context={"regime": regime, "timestamp": _dt.now().isoformat()},
                )
                logger.info(f"微观入场验证: {entry_validation.get('signal_type')} (结构: {structure_type}, 方向: {structure_direction})")
            else:
                logger.debug("无有效突破结构，跳过MicroEntryValidator")
        except Exception as e:
            logger.warning(f"MicroEntryValidator调用失败: {e}")
            entry_validation = None

        return {
            "timeframe_weights": timeframe_weights,
            "detected_conflicts": conflicts,
            "resolved_decisions": resolved_decisions,
            "entry_validation": entry_validation,
        }

    async def _run_state_machine_decision(
        self,
        symbol: str,
        data_dict: dict[str, pd.DataFrame],
        perception_results: dict[str, Any],
        fusion_results: dict[str, Any],
    ) -> dict[str, Any]:
        """运行状态机决策层"""
        logger.info("Running state machine decision layer...")

        # 获取主时间框架数据
        primary_tf = perception_results["primary_timeframe"]
        primary_data = data_dict[primary_tf]

        try:
            # 确保primary_data是DataFrame
            if not isinstance(primary_data, pd.DataFrame):
                logger.warning(f"primary_data不是DataFrame类型: {type(primary_data)}")
                # 尝试转换
                if hasattr(primary_data, "to_frame"):
                    primary_data = primary_data.to_frame().T
                else:
                    # 降级处理
                    return {
                        "wyckoff_state": "neutral",
                        "state_confidence": 0.5,
                        "state_signals": [],
                        "evidence_chain": [],
                        "state_direction": "UNKNOWN",
                        "state_intensity": 0.0,
                    }

            # 准备状态机上下文（补齐所有 detect_xx() 实际使用的字段）
            trading_range = perception_results["trading_range"]
            support_level = trading_range.get("support")
            resistance_level = trading_range.get("resistance")

            # 计算 avg_volume_20 / atr_14 / trend_direction 供22个检测方法使用
            _vol_20 = float(primary_data["volume"].rolling(20).mean().iloc[-1]) if len(primary_data) >= 20 else float(primary_data["volume"].mean()) if len(primary_data) > 0 else 1.0
            _high = primary_data["high"]
            _low = primary_data["low"]
            _close = primary_data["close"]
            if len(primary_data) >= 14:
                _tr_s = pd.concat([
                    _high - _low,
                    (_high - _close.shift()).abs(),
                    (_low - _close.shift()).abs()
                ], axis=1).max(axis=1)
                _atr14 = float(_tr_s.rolling(14).mean().iloc[-1])
            else:
                _atr14 = float((_high - _low).mean()) if len(primary_data) > 0 else 1.0

            # 趋势方向（用MA20/MA50交叉判断）
            if len(primary_data) >= 20:
                _ma20 = float(_close.rolling(20).mean().iloc[-1])
                _ma50 = float(_close.rolling(min(50, len(primary_data))).mean().iloc[-1])
                _last_c = float(_close.iloc[-1])
                if _ma20 > _ma50 and _last_c > _ma20:
                    _trend_dir = "UP"
                    _trend_str = min(1.0, (_ma20 - _ma50) / _ma50 * 10) if _ma50 > 0 else 0.5
                elif _ma20 < _ma50 and _last_c < _ma20:
                    _trend_dir = "DOWN"
                    _trend_str = min(1.0, (_ma50 - _ma20) / _ma50 * 10) if _ma50 > 0 else 0.5
                else:
                    _trend_dir = "SIDEWAYS"
                    _trend_str = 0.3
            else:
                _trend_dir = "UNKNOWN"
                _trend_str = 0.5

            # SC/AR关键价格水平（从状态机内部读取，供后续AR/ST检测使用）
            _sc_low = self.state_machine.critical_price_levels.get("SC_LOW")
            _bc_high = self.state_machine.critical_price_levels.get("BC_HIGH")

            context = {
                # 市场体制
                "market_regime": perception_results["market_regime"]["regime"],
                "regime_confidence": perception_results["market_regime"]["confidence"],
                # TR边界
                "trading_range": trading_range,
                "support": support_level,
                "resistance": resistance_level,
                "support_level": support_level,   # detect_ps/sc/ar 使用的字段名
                "resistance_level": resistance_level,
                # 感知层信号
                "fvg_signals": perception_results.get("fvg_signals", []),
                "breakout_status": perception_results.get("breakout_status"),
                # 融合层输出
                "timeframe_weights": fusion_results["timeframe_weights"],
                "detected_conflicts": fusion_results.get("detected_conflicts", []),
                # 技术指标（供22个 detect_xx() 方法使用，不再全部降级为默认值）
                "avg_volume_20": _vol_20,
                "atr_14": _atr14,
                "trend_direction": _trend_dir,
                "trend_strength": _trend_str,
                # 关键价格水平（AR/ST/TEST检测需要SC低点作为参照）
                "sc_low": _sc_low,
                "bc_high": _bc_high,
                # SC状态上下文（供AR检测使用）
                "has_sc": _sc_low is not None,
                "sc_confidence": self.state_machine.state_confidences.get("SC", 0.0) if hasattr(self.state_machine, "state_confidences") else 0.0,
            }

            # P0-B 修复: 增量喂入状态机，只喂自上次以来的新K线
            # 避免每轮把同一批100根K线重复喂入导致状态机内部积累扭曲
            if self.last_processed_candle_time is None:
                # 首次运行：喂入最后100根作为初始化（仅此一次）
                init_candles = (
                    primary_data.iloc[-100:] if len(primary_data) >= 100 else primary_data
                )
                for i, candle in init_candles.iterrows():
                    self.state_machine.process_candle(candle, context)
                if len(init_candles) > 0:
                    self.last_processed_candle_time = init_candles.index[-1]
                logger.info(f"状态机初始化：喂入 {len(init_candles)} 根历史K线")
            else:
                # 后续运行：只喂自上次时间戳之后的新K线
                new_candles = primary_data[
                    primary_data.index > self.last_processed_candle_time
                ]
                if len(new_candles) > 0:
                    for i, candle in new_candles.iterrows():
                        self.state_machine.process_candle(candle, context)
                    self.last_processed_candle_time = new_candles.index[-1]
                    logger.info(f"状态机增量喂入: {len(new_candles)} 根新K线")
                else:
                    logger.debug("无新K线，状态机跳过喂入")

            # 获取当前状态信息
            # 注意：EnhancedWyckoffStateMachine应该有get_current_state_info方法
            # 如果没有，我们需要使用其他方法获取状态信息
            state_info = {}
            if hasattr(self.state_machine, "get_current_state_info"):
                state_info = self.state_machine.get_current_state_info()
            else:
                # 降级：使用基本状态信息
                state_info = {
                    "current_state": self.state_machine.current_state,
                    "state_direction": self.state_machine.state_direction.value
                    if self.state_machine.state_direction
                    else "UNKNOWN",
                    "state_confidence": self.state_machine.state_confidences.get(
                        self.state_machine.current_state, 0.0
                    ),
                    "state_intensity": self.state_machine.state_intensities.get(
                        self.state_machine.current_state, 0.0
                    ),
                    "signals": [],
                    "evidence_chain": {},
                    "critical_price_levels": self.state_machine.critical_price_levels,
                    "alternative_paths_count": len(
                        self.state_machine.alternative_paths
                    ),
                    "heritage_chain_length": len(self.state_machine.heritage_chain),
                }

            # 转换信号格式以匹配系统期望
            formatted_signals = []
            for signal in state_info.get("signals", []):
                if signal["type"] == "buy_signal":
                    formatted_signals.append(
                        {
                            "type": WyckoffSignal.BUY_SIGNAL,
                            "confidence": signal["confidence"],
                            "description": signal["description"],
                            "strength": signal["strength"],
                            "action": signal["action"],
                        }
                    )
                elif signal["type"] == "sell_signal":
                    formatted_signals.append(
                        {
                            "type": WyckoffSignal.SELL_SIGNAL,
                            "confidence": signal["confidence"],
                            "description": signal["description"],
                            "strength": signal["strength"],
                            "action": signal["action"],
                        }
                    )
                else:
                    formatted_signals.append(
                        {
                            "type": WyckoffSignal.NO_SIGNAL,
                            "confidence": signal["confidence"],
                            "description": signal["description"],
                            "strength": signal["strength"],
                            "action": signal["action"],
                        }
                    )

            # 检查状态变化并触发可视化
            current_state = state_info["current_state"]
            if self.previous_state != current_state:
                try:
                    # 触发状态变化可视化
                    self.decision_visualizer.visualize_state_change(
                        data=primary_data,
                        symbol=symbol,
                        state_info={
                            "current_state": current_state,
                            "state_confidence": state_info["state_confidence"],
                            "state_direction": state_info.get(
                                "state_direction", "UNKNOWN"
                            ),
                            "state_intensity": state_info.get("state_intensity", 0.0),
                        },
                        previous_state=self.previous_state,
                        timeframe=primary_tf,
                    )
                    logger.info(
                        f"状态变化可视化已触发: {self.previous_state} -> {current_state}"
                    )
                except Exception as viz_error:
                    logger.warning(f"状态变化可视化失败: {viz_error}")

                # 更新前一个状态
                self.previous_state = current_state

            return {
                "wyckoff_state": current_state,
                "state_confidence": state_info["state_confidence"],
                "state_signals": formatted_signals,
                "evidence_chain": state_info.get("evidence_chain", {}),
                "state_direction": state_info.get("state_direction", "UNKNOWN"),
                "state_intensity": state_info.get("state_intensity", 0.0),
            }

        except Exception:
            logger.exception("状态机决策失败")
            return {
                "wyckoff_state": "neutral",
                "state_confidence": 0.5,
                "state_signals": [],
                "evidence_chain": [],
                "state_direction": "UNKNOWN",
                "state_intensity": 0.0,
            }

    async def _generate_trading_decision(
        self,
        symbol: str,
        perception_results: dict[str, Any],
        fusion_results: dict[str, Any],
        state_results: dict[str, Any],
    ) -> TradingDecision:
        """生成最终交易决策"""
        logger.info("Generating trading decision...")

        # 创建决策上下文
        context = DecisionContext(
            timestamp=datetime.now(),
            market_regime=perception_results["market_regime"]["regime"],
            regime_confidence=perception_results["market_regime"]["confidence"],
            timeframe_weights=fusion_results["timeframe_weights"],
            detected_conflicts=fusion_results["detected_conflicts"],
            wyckoff_state=state_results["wyckoff_state"],
            wyckoff_confidence=state_results["state_confidence"],
            breakout_status=perception_results.get("breakout_status"),
            fvg_signals=perception_results.get("fvg_signals", []),
        )

        # 决策逻辑
        signal = TradingSignal.NEUTRAL
        confidence = 0.0
        reasoning = []

        # 获取配置
        trading_mode = self.config.get("trading_mode", "spot")
        leverage = self.config.get("leverage", 1)
        allow_shorting = self.config.get("allow_shorting", False)

        # 基于威科夫状态机信号
        if state_results["wyckoff_state"]:
            wyckoff_signals = state_results.get("state_signals", [])
            if wyckoff_signals:
                # 提取最强的威科夫信号
                strongest_signal = max(
                    wyckoff_signals, key=lambda x: x.get("confidence", 0)
                )

                signal_type = strongest_signal.get("type")
                signal_confidence = strongest_signal.get("confidence", 0)

                if signal_type == WyckoffSignal.BUY_SIGNAL:
                    signal = (
                        TradingSignal.BUY
                        if signal_confidence < 0.8
                        else TradingSignal.STRONG_BUY
                    )
                    confidence = signal_confidence
                    reasoning.append(
                        f"Wyckoff buy signal (confidence: {signal_confidence:.2f})"
                    )
                    # 添加杠杆信息
                    if trading_mode == "futures":
                        reasoning.append(f"使用杠杆倍数: {leverage}x")
                elif signal_type == WyckoffSignal.SELL_SIGNAL:
                    signal = (
                        TradingSignal.SELL
                        if signal_confidence < 0.8
                        else TradingSignal.STRONG_SELL
                    )
                    confidence = signal_confidence
                    reasoning.append(
                        f"Wyckoff sell signal (confidence: {signal_confidence:.2f})"
                    )
                    # 添加杠杆信息
                    if trading_mode == "futures":
                        reasoning.append(f"使用杠杆倍数: {leverage}x")

        # 合约做空逻辑：如果允许做空且状态为派发阶段，考虑做空
        if allow_shorting and trading_mode == "futures":
            # 派发阶段状态列表
            distribution_states = [
                "PSY",
                "BC",
                "AR_DIST",
                "ST_DIST",
                "UT",
                "UTAD",
                "LPSY",
                "mSOW",
                "MSOW",
            ]
            current_state = state_results.get("wyckoff_state", "")
            state_direction = state_results.get("state_direction", "")
            state_results.get("state_intensity", 0.0)

            # 检查是否为派发阶段且趋势向下
            if (
                state_direction == "DISTRIBUTION"
                or current_state in distribution_states
            ):
                # 检查是否出现'Redistribution'小结构或'LPSY'
                # 'Redistribution'小结构：UT, UTAD, ST_DIST等
                redistribution_structures = ["UT", "UTAD", "ST_DIST"]
                if (
                    current_state in redistribution_structures
                    or current_state == "LPSY"
                ):
                    # 确认趋势向下（通过市场体制或价格趋势）
                    market_regime = perception_results["market_regime"]["regime"]
                    perception_results["market_regime"][
                        "confidence"
                    ]

                    # 如果市场体制为下跌或趋势向下，发出做空信号
                    if (
                        "BEARISH" in market_regime.upper()
                        or "DOWN" in market_regime.upper()
                        or state_direction == "DISTRIBUTION"
                    ):
                        # 计算做空信号置信度
                        short_confidence = min(
                            0.9, state_results.get("state_confidence", 0.5) * 1.2
                        )
                        # 如果当前信号不是卖出或强卖出，则覆盖为卖出信号
                        if signal not in [
                            TradingSignal.SELL,
                            TradingSignal.STRONG_SELL,
                        ]:
                            signal = (
                                TradingSignal.SELL
                                if short_confidence < 0.8
                                else TradingSignal.STRONG_SELL
                            )
                            confidence = max(confidence, short_confidence)
                            reasoning.append(
                                f"合约做空信号：检测到派发阶段小结构 {current_state}，趋势向下 (置信度: {short_confidence:.2f})"
                            )
                            # 添加杠杆信息
                            reasoning.append(f"使用杠杆倍数: {leverage}x")

        # 考虑突破状态
        breakout_status = perception_results.get("breakout_status")
        if breakout_status and breakout_status.get("is_valid"):
            breakout_direction = breakout_status.get("direction")
            breakout_status.get("confidence", 0)

            if breakout_direction == "bullish" and signal in [
                TradingSignal.BUY,
                TradingSignal.STRONG_BUY,
            ]:
                confidence = min(1.0, confidence + 0.1)
                reasoning.append("Confirmed bullish breakout")
            elif breakout_direction == "bearish" and signal in [
                TradingSignal.SELL,
                TradingSignal.STRONG_SELL,
            ]:
                confidence = min(1.0, confidence + 0.1)
                reasoning.append("Confirmed bearish breakout")

        # 考虑冲突解决结果
        resolved_decisions = fusion_results.get("resolved_decisions", [])
        if resolved_decisions:
            for decision in resolved_decisions:
                if decision.get("resolution") == "follow_larger_timeframe":
                    reasoning.append("Following larger timeframe direction")
                elif decision.get("resolution") == "reduce_position_size":
                    reasoning.append("Reducing position size due to conflict")

        # 如果没有明确信号，保持中性
        if confidence < 0.6:
            signal = TradingSignal.NEUTRAL
            reasoning.append(
                f"Low confidence ({confidence:.2f}), maintaining neutral position"
            )

        # 创建最终决策
        decision = TradingDecision(
            signal=signal, confidence=confidence, context=context, reasoning=reasoning
        )

        # P1-B 修复：MistakeBook 从真实决策结果中学习
        # 当置信度低或多周期冲突严重时，记录为潜在错误供进化层分析
        try:
            from .mistake_book import ErrorPattern, ErrorSeverity, MistakeType

            # 条件1：置信度过低（< 0.4）说明感知层与融合层不一致
            if confidence < 0.4:
                self.mistake_book.record_mistake(
                    mistake_type=MistakeType.MARKET_REGIME_ERROR,
                    severity=ErrorSeverity.MEDIUM,
                    context={
                        "market_regime": perception_results["market_regime"]["regime"],
                        "wyckoff_state": state_results.get("wyckoff_state"),
                        "signal": signal.value,
                        "confidence": confidence,
                        "timeframe_weights": fusion_results.get("timeframe_weights"),
                    },
                    expected="high_confidence_signal",
                    actual=f"low_confidence_{signal.value}",
                    confidence_before=confidence,
                    confidence_after=0.0,
                    impact_score=0.6,
                    module_name="generate_trading_decision",
                    timeframe=perception_results.get("primary_timeframe", "H4"),
                    patterns=[ErrorPattern.CONTEXT_SENSITIVITY_ERROR],
                )

            # 条件2：多周期冲突存在（ConflictResolver 检测到冲突）
            detected_conflicts = fusion_results.get("detected_conflicts", [])
            if detected_conflicts:
                self.mistake_book.record_mistake(
                    mistake_type=MistakeType.CONFLICT_RESOLUTION_ERROR,
                    severity=ErrorSeverity.HIGH,
                    context={
                        "conflicts": str(detected_conflicts[:2]),  # 只保存前2个避免过大
                        "wyckoff_state": state_results.get("wyckoff_state"),
                        "signal": signal.value,
                        "confidence": confidence,
                    },
                    expected="consistent_multi_timeframe_signal",
                    actual=f"conflicted_signal_{signal.value}",
                    confidence_before=confidence,
                    confidence_after=max(0.0, confidence - 0.2),
                    impact_score=0.7,
                    module_name="conflict_resolver",
                    timeframe=perception_results.get("primary_timeframe", "H4"),
                    patterns=[ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT],
                )

            # 条件3：状态机置信度与最终决策信号方向不一致
            state_direction = state_results.get("state_direction", "")
            state_conf = state_results.get("state_confidence", 0.0)
            if state_conf > 0.7 and signal in (TradingSignal.NEUTRAL,) and state_direction in ("ACCUMULATION", "DISTRIBUTION"):
                self.mistake_book.record_mistake(
                    mistake_type=MistakeType.STATE_MISJUDGMENT,
                    severity=ErrorSeverity.HIGH,
                    context={
                        "state_direction": state_direction,
                        "state_confidence": state_conf,
                        "final_signal": signal.value,
                        "market_regime": perception_results["market_regime"]["regime"],
                    },
                    expected=f"directional_signal_for_{state_direction}",
                    actual="neutral",
                    confidence_before=state_conf,
                    confidence_after=confidence,
                    impact_score=0.8,
                    module_name="wyckoff_state_machine",
                    timeframe=perception_results.get("primary_timeframe", "H4"),
                    patterns=[ErrorPattern.TIMING_ERROR],
                )
        except Exception as _mb_err:
            logger.debug(f"MistakeBook记录失败（非致命）: {_mb_err}")

        # 叙事性日志输出
        try:
            # 提取TR区间
            tr_info = perception_results.get("trading_range", {})
            support = tr_info.get("support")
            resistance = tr_info.get("resistance")

            # 【关键修复】正确获取当前价格
            # 1. 首先从感知结果中获取主时间框架数据
            current_price = None
            try:
                if "primary_data" in perception_results:
                    primary_data = perception_results["primary_data"]
                    if (
                        isinstance(primary_data, pd.DataFrame)
                        and not primary_data.empty
                    ):
                        # 获取最新收盘价
                        current_price = float(primary_data["close"].iloc[-1])
                        logger.debug(f"从primary_data获取当前价格: {current_price}")
            except Exception as e:
                logger.warning(f"从primary_data获取当前价格失败: {e}")

            # 2. 如果上述方法失败，尝试从突破状态获取
            if current_price is None:
                breakout_status = perception_results.get("breakout_status")
                if breakout_status and isinstance(breakout_status, dict):
                    if "current_price" in breakout_status:
                        current_price = breakout_status.get("current_price")
                        logger.debug(f"从breakout_status获取当前价格: {current_price}")
                    elif "breakout_price" in breakout_status:
                        current_price = breakout_status.get("breakout_price")
                        logger.debug(f"从breakout_price获取当前价格: {current_price}")

            # 获取威科夫状态
            wyckoff_state = state_results.get("wyckoff_state", "unknown")
            state_direction = state_results.get("state_direction", "UNKNOWN")

            # 【当前格局】
            if support is not None and resistance is not None:
                logger.info(
                    f"【当前格局】：识别出的 TR 区间 {support:.2f} - {resistance:.2f}"
                )
            elif support is not None:
                logger.info(f"【当前格局】：识别出支撑位 {support:.2f}，阻力位未知")
            elif resistance is not None:
                logger.info(f"【当前格局】：识别出阻力位 {resistance:.2f}，支撑位未知")
            else:
                logger.info("【当前格局】：未识别出明确 TR 区间")

            # 【价格定位】- 修复逻辑矛盾
            # 强制在有TR区间的情况下计算价格位置
            if support is not None and resistance is not None:
                # 有TR区间，必须计算价格位置
                if current_price is not None:
                    # 有当前价格，计算精确位置
                    if current_price < support:
                        deviation = (current_price - support) / support * 100
                        logger.info(
                            f"【价格定位】：当前 {current_price:.2f} 低于支撑位 {support:.2f}，偏离度 {deviation:.1f}% (Mark Down)"
                        )
                    elif current_price > resistance:
                        deviation = (current_price - resistance) / resistance * 100
                        logger.info(
                            f"【价格定位】：当前 {current_price:.2f} 高于阻力位 {resistance:.2f}，偏离度 {deviation:.1f}% (Mark Up)"
                        )
                    elif support <= current_price <= resistance:
                        deviation_from_support = (
                            (current_price - support) / support * 100
                        )
                        deviation_from_resistance = (
                            (current_price - resistance) / resistance * 100
                        )
                        logger.info(
                            f"【价格定位】：当前 {current_price:.2f} 位于 TR 区间内，距支撑 {deviation_from_support:.1f}%，距阻力 {deviation_from_resistance:.1f}%"
                        )
                else:
                    # 没有当前价格，但TR区间存在 - 这是关键修复点
                    logger.info(
                        f"【价格定位】：TR区间 {support:.2f} - {resistance:.2f} 已识别，但当前价格未知"
                    )
                    # 强制检查：如果系统检测到TR但无法获取价格，可能是数据源问题
                    logger.warning("价格数据缺失，无法计算精确位置")
            elif support is not None:
                # 只有支撑位
                if current_price is not None:
                    deviation = (current_price - support) / support * 100
                    position = "低于支撑" if current_price < support else "高于支撑"
                    logger.info(
                        f"【价格定位】：当前 {current_price:.2f} {position} {support:.2f}，偏离度 {deviation:.1f}%"
                    )
                else:
                    logger.info(
                        f"【价格定位】：支撑位 {support:.2f} 已识别，但当前价格未知"
                    )
            elif resistance is not None:
                # 只有阻力位
                if current_price is not None:
                    deviation = (current_price - resistance) / resistance * 100
                    position = "低于阻力" if current_price < resistance else "高于阻力"
                    logger.info(
                        f"【价格定位】：当前 {current_price:.2f} {position} {resistance:.2f}，偏离度 {deviation:.1f}%"
                    )
                else:
                    logger.info(
                        f"【价格定位】：阻力位 {resistance:.2f} 已识别，但当前价格未知"
                    )
            # 没有TR区间信息
            elif current_price is not None:
                logger.info(
                    f"【价格定位】：当前价格 {current_price:.2f}，未识别出TR区间"
                )
            else:
                logger.info("【价格定位】：价格和TR区间信息均不足")

            # 【威科夫定性】- 修复：添加价格相对于TR的位置判断
            # 首先检查价格是否低于TR下沿（Mark Down的关键信号）
            is_mark_down_by_price = False
            if current_price is not None and support is not None:
                if current_price < support:
                    is_mark_down_by_price = True
                    logger.info(
                        f"【价格信号】：当前价格 {current_price:.2f} 低于支撑位 {support:.2f}，处于 Mark Down 区域"
                    )

            # 然后结合威科夫状态进行定性
            if (
                "DISTRIBUTION" in state_direction
                or wyckoff_state
                in [
                    "PSY",
                    "BC",
                    "AR_DIST",
                    "ST_DIST",
                    "UT",
                    "UTAD",
                    "LPSY",
                    "mSOW",
                    "MSOW",
                ]
                or is_mark_down_by_price
            ):  # 添加价格条件
                logger.info("【威科夫定性】：当前处于 Mark Down (派发后下跌趋势)")
                if is_mark_down_by_price:
                    logger.info("【确认信号】：价格已跌破TR下沿，确认下跌趋势")
            elif "ACCUMULATION" in state_direction or wyckoff_state in [
                "PS",
                "SC",
                "AR",
                "ST",
                "UT_ACC",
                "UTAD_ACC",
                "LPS",
                "SOS",
                "MSOS",
            ]:
                logger.info("【威科夫定性】：当前处于 Accumulation (吸筹阶段)")
            elif "TRADING_RANGE" in state_direction or wyckoff_state in ["TR"]:
                logger.info("【威科夫定性】：当前处于 Trading Range (交易区间)")
            else:
                logger.info(
                    f"【威科夫定性】：当前状态 {wyckoff_state}，方向 {state_direction}"
                )

            # 【多空决策】
            # 计算乖离率（当前价格与支撑位的偏离度）
            deviation_rate = None
            if current_price is not None and support is not None:
                deviation_rate = abs(current_price - support) / support * 100

            if signal in [TradingSignal.BUY, TradingSignal.STRONG_BUY]:
                # 做多信号
                logger.info(
                    "【多空决策】：未检测到 Accumulation (吸筹) 结构，禁止抄底。"
                )
            elif signal in [TradingSignal.SELL, TradingSignal.STRONG_SELL]:
                # 做空信号
                if wyckoff_state == "LPSY":
                    logger.info(
                        "【多空决策】：趋势向下，检测到小级别 LPSY，建议开空。"
                    )
                else:
                    logger.info("【多空决策】：趋势向下，建议开空。")
            # 观望信号
            elif deviation_rate is not None and deviation_rate > 15:
                logger.info(
                    f"【多空决策】：趋势向下但乖离率过大（追空风险），等待反弹至 {resistance if resistance is not None else '阻力位'} 再空。"
                )
            else:
                logger.info("【多空决策】：趋势不明，等待确认信号。")
        except Exception as e:
            logger.warning(f"叙事性日志生成失败: {e}")

        return decision

    def _record_error_to_mistake_book(self, error: Exception, symbol: str):
        """记录错误到错题本"""
        logger.debug(f"Recording error to mistake book: {error}")
        try:
            # 根据错误类型分类
            error_str = str(error)
            mistake_type = "SYSTEM_ERROR"
            pattern = "UNKNOWN_ERROR"

            if "data" in error_str.lower():
                mistake_type = "DATA_PROCESSING_ERROR"
                pattern = "CORRELATION_ERROR"
            elif "timeout" in error_str.lower():
                mistake_type = "TIMING_ERROR"
                pattern = "TIMING_ERROR"
            elif "validation" in error_str.lower():
                mistake_type = "VALIDATION_ERROR"
                pattern = "FREQUENT_FALSE_POSITIVE"

            # 记录错误 - 简化实现
            try:
                # 使用字符串参数，避免类型错误
                self.mistake_book.record_mistake(
                    mistake_type=mistake_type,  # type: ignore[arg-type]
                    severity="MEDIUM",  # type: ignore[arg-type]
                    context={
                        "symbol": symbol,
                        "timestamp": datetime.now(),
                        "error": str(error),
                    },
                    module_name="system_orchestrator",
                    timeframe="unknown",
                    patterns=[pattern] if pattern else [],  # type: ignore[arg-type]
                )
            except Exception as e:
                logger.warning(f"Failed to record mistake: {e}")

        except Exception:
            logger.exception("Failed to record error to mistake book")

    def _save_system_state(self):
        """保存系统状态"""
        logger.debug("Saving system state")
        try:
            state_file = self.config.get("state_file", "system_state.json")
            state_data = {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "mode": self.mode.value,
                "decision_count": len(self.decision_history),
                "error_count": len(self.error_history),
                "performance_metrics": self.performance_monitor.get_dashboard(),
            }

            with open(state_file, "w") as f:
                json.dump(state_data, f, indent=2, default=str)

            logger.info(f"System state saved to {state_file}")

        except Exception:
            logger.exception("Failed to save system state")

    def get_system_status(self) -> dict[str, Any]:
        """获取系统状态"""
        logger.debug("Generating system status report")
        return {
            "is_running": self.is_running,
            "mode": self.mode.value,
            "uptime": (datetime.now() - self.start_time).total_seconds()
            if self.start_time
            else 0,
            "decision_count": len(self.decision_history),
            "error_count": len(self.error_history),
            "performance_dashboard": self.performance_monitor.get_dashboard(),
            "recent_decisions": [d.to_dict() for d in self.decision_history[-5:]]
            if self.decision_history
            else [],
        }

    async def run_evolution_cycle(self):
        """运行一个完整的进化周期"""
        logger.info("Starting evolution cycle...")

        # 1. 从错题本收集错误模式
        error_patterns = self.mistake_book.analyze_patterns()

        # 2. 生成新的权重配置 - 简化实现
        new_configs = [self.config.copy()]

        # 3. 使用WFA回测验证新配置 - 简化实现
        validation_results = []

        # 4. 选择最佳配置 - 简化实现
        best_config = self.config.copy()

        # 5. 应用新配置（如果优于当前配置）
        if best_config and best_config.get("composite_score", 0) > 0:
            logger.info(
                f"Applying new configuration with score: {best_config.get('composite_score', 0):.3f}"
            )

            # 记录进化日志到档案员
            self._record_evolution_logs(best_config)

            self.config.update(best_config.get("configuration", {}))

            # 更新所有模块配置
            self._update_module_configurations()

        # 6. 清理错题本
        self.mistake_book._auto_cleanup()
        logger.debug(
            f"Cleaned mistake book, remaining records: {len(self.mistake_book.records)}"
        )

        logger.info("Evolution cycle completed")

        return {
            "error_patterns_analyzed": len(error_patterns),
            "configs_generated": len(new_configs),
            "configs_validated": len(validation_results),
            "best_config_score": best_config.get("composite_score", 0)
            if best_config
            else 0,
            "config_updated": best_config is not None,
        }

    def _record_evolution_logs(self, best_config: dict[str, Any]):
        """记录进化日志到档案员"""
        try:
            # 从最佳配置中提取变化信息
            config_changes = best_config.get("configuration", {})
            composite_score = best_config.get("composite_score", 0)

            # 记录周期权重变化
            if "period_weight_filter" in config_changes:
                weight_config = config_changes["period_weight_filter"]

                # 记录基础权重变化
                if "weights" in weight_config:
                    weights = weight_config["weights"]
                    old_weights = self.config.get("period_weight_filter", {}).get(
                        "weights", {}
                    )

                    for timeframe, new_weight in weights.items():
                        old_weight = old_weights.get(timeframe, 0)
                        if old_weight != new_weight:
                            self.evolution_archivist.record_simple(
                                event_type=EvolutionEventType.WEIGHT_ADJUSTMENT,
                                module="period_weight_filter",
                                parameter=f"{timeframe}_weight",
                                old_value=old_weight,
                                new_value=new_weight,
                                reason=f"优化周期权重分布，提高系统性能 (得分: {composite_score:.3f})",
                                context={
                                    "composite_score": composite_score,
                                    "timeframe": timeframe,
                                    "error_patterns_count": len(
                                        self.mistake_book.records
                                    ),
                                },
                            )

            # 记录阈值参数变化
            if "threshold_parameters" in config_changes:
                threshold_config = config_changes["threshold_parameters"]
                old_thresholds = self.config.get("threshold_parameters", {})

                for param_name, new_value in threshold_config.items():
                    old_value = old_thresholds.get(param_name)
                    if old_value is not None and old_value != new_value:
                        self.evolution_archivist.record_simple(
                            event_type=EvolutionEventType.THRESHOLD_CHANGE,
                            module="threshold_parameters",
                            parameter=param_name,
                            old_value=old_value,
                            new_value=new_value,
                            reason=f"调整{param_name}阈值，优化信号质量 (得分: {composite_score:.3f})",
                            context={
                                "composite_score": composite_score,
                                "parameter": param_name,
                                "error_patterns_count": len(self.mistake_book.records),
                            },
                        )

            # 记录市场体制系数变化
            if "period_weight_filter" in config_changes:
                weight_config = config_changes["period_weight_filter"]
                if "regime_adjustments" in weight_config:
                    regime_adjustments = weight_config["regime_adjustments"]
                    old_adjustments = self.config.get("period_weight_filter", {}).get(
                        "regime_adjustments", {}
                    )

                    for regime, adjustments in regime_adjustments.items():
                        old_regime_adjustments = old_adjustments.get(regime, {})
                        for timeframe, new_coefficient in adjustments.items():
                            old_coefficient = old_regime_adjustments.get(timeframe, 1.0)
                            if old_coefficient != new_coefficient:
                                self.evolution_archivist.record_simple(
                                    event_type=EvolutionEventType.COEFFICIENT_ADJUSTMENT,
                                    module="period_weight_filter",
                                    parameter=f"{regime}_{timeframe}_coefficient",
                                    old_value=old_coefficient,
                                    new_value=new_coefficient,
                                    reason=f"调整{regime}市场体制下{timeframe}周期系数 (得分: {composite_score:.3f})",
                                    context={
                                        "composite_score": composite_score,
                                        "regime": regime,
                                        "timeframe": timeframe,
                                        "error_patterns_count": len(
                                            self.mistake_book.records
                                        ),
                                    },
                                )

            logger.info(f"已记录进化日志到档案员，配置得分: {composite_score:.3f}")

        except Exception:
            logger.exception("记录进化日志失败")

    def _update_module_configurations(self):
        """更新所有模块配置"""
        # 这是一个简化实现，实际应用中需要根据具体模块更新配置
        logger.info("更新模块配置...")

        # 这里可以添加具体模块的配置更新逻辑
        # 例如：
        # self.period_filter.update_config(self.config.get("period_weight_filter", {}))
        # self.weight_variator.update_config(self.config.get("weight_variator", {}))

        logger.info("模块配置更新完成")

    def _update_module_configurations(self):
        """更新所有模块的配置"""
        logger.debug("Starting module configuration updates")

        # 从自我修正工作流获取最新的优化配置
        # 注意：self_correction_workflow 属性可能不存在，需要检查
        try:
            # 尝试从配置中获取优化配置
            latest_configs = self.config.get("optimized_configs", {})
            if latest_configs:
                logger.info(
                    f"Found {len(latest_configs)} optimized configurations to apply"
                )

                # 应用配置到各个模块
                applied_count = 0
                for module_name, config_update in latest_configs.items():
                    try:
                        if self._apply_config_to_module(module_name, config_update):
                            applied_count += 1
                            logger.info(
                                f"Applied configuration update to {module_name}"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to apply config to {module_name}: {e}")

                logger.info(
                    f"Successfully applied {applied_count} configuration updates"
                )
                return applied_count
            logger.info("No optimized configurations available")
        except Exception:
            logger.exception("Error getting optimized configs")

        # 如果没有自我修正工作流或没有优化配置，使用默认配置更新逻辑
        logger.info("Using default configuration update logic")

        # 收集当前系统状态信息
        system_state = self._collect_system_state()

        # 基于系统状态调整配置
        config_updates = self._generate_config_updates_based_on_state(system_state)

        # 应用配置更新
        applied_count = 0
        for module_name, config_update in config_updates.items():
            try:
                if self._apply_config_to_module(module_name, config_update):
                    applied_count += 1
            except Exception as e:
                logger.warning(f"Failed to apply config to {module_name}: {e}")

        logger.info(
            f"Applied {applied_count} configuration updates based on system state"
        )
        return applied_count

    def _apply_config_to_module(
        self, module_name: str, config_update: dict[str, Any]
    ) -> bool:
        """将配置应用到指定模块"""
        try:
            # 根据模块名称映射到对应的模块实例
            module_map = {
                "data_pipeline": self.data_pipeline,
                "data_sanitizer": self.data_sanitizer,
                "regime_detector": self.regime_detector,
                "fvg_detector": self.fvg_detector,
                "tr_detector": self.tr_detector,
                "curve_analyzer": self.curve_analyzer,
                "breakout_validator": self.breakout_validator,
                "anomaly_validator": self.anomaly_validator,
                "circuit_breaker": self.circuit_breaker,
                "period_filter": self.period_filter,
                "conflict_resolver": self.conflict_resolver,
                "entry_validator": self.entry_validator,
                "state_machine": self.state_machine,
                "mistake_book": self.mistake_book,
                "weight_variator": self.weight_variator,
                "wfa_backtester": self.wfa_backtester,
                "performance_monitor": self.performance_monitor,
            }

            if module_name not in module_map:
                logger.warning(f"Unknown module: {module_name}")
                return False

            module = module_map[module_name]

            # 尝试更新模块配置
            if hasattr(module, "update_config"):
                module.update_config(config_update)
                logger.debug(
                    f"Updated config for {module_name} using update_config method"
                )
            elif hasattr(module, "config"):
                # 直接更新config属性
                if isinstance(module.config, dict):
                    module.config.update(config_update)
                else:
                    # 尝试通过属性设置
                    for key, value in config_update.items():
                        if hasattr(module, key):
                            setattr(module, key, value)
                logger.debug(
                    f"Updated config for {module_name} by updating config dict"
                )
            else:
                # 尝试通过重新初始化模块
                logger.warning(
                    f"Module {module_name} doesn't have config update interface"
                )
                return False

            return True

        except Exception:
            logger.exception(f"Error applying config to {module_name}")
            return False

    def _collect_system_state(self) -> dict[str, Any]:
        """收集当前系统状态信息"""
        state = {
            "timestamp": datetime.now(),
            "system_runtime": (datetime.now() - self.start_time).total_seconds()
            if self.start_time
            else 0,
            "decision_count": len(self.decision_history),
            "error_count": len(self.error_history),
            "is_running": self.is_running,
            "mode": self.mode.value,
        }

        # 收集模块健康状态
        if hasattr(self, "performance_monitor"):
            try:
                health_report = self.performance_monitor.get_health_report()
                state["module_health"] = health_report.get("module_health", {})
                state["system_score"] = health_report.get("system_score", 0)
            except Exception as e:
                logger.warning(f"Error getting health report: {e}")

        # 收集错误模式
        if hasattr(self, "mistake_book"):
            try:
                error_patterns = self.mistake_book.analyze_error_patterns()
                state["error_patterns"] = error_patterns
            except Exception as e:
                logger.warning(f"Error getting error patterns: {e}")

        return state

    def _generate_config_updates_based_on_state(
        self, system_state: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """基于系统状态生成配置更新"""
        config_updates = {}

        # 基于错误率调整配置
        error_count = system_state.get("error_count", 0)
        decision_count = system_state.get("decision_count", 1)  # 避免除零

        error_rate = error_count / decision_count

        # 如果错误率过高，降低灵敏度
        if error_rate > 0.1:  # 10%错误率
            logger.info(
                f"High error rate detected ({error_rate:.1%}), reducing sensitivity"
            )
            config_updates.update(
                {
                    "breakout_validator": {
                        "confirmation_bars": 5,  # 增加确认K线数
                        "pullback_tolerance": 0.015,  # 增加回踩容忍度
                    },
                    "entry_validator": {
                        "min_structure_score": 0.8,  # 提高结构分数要求
                        "max_age_hours": 24,  # 缩短结构有效期
                    },
                }
            )

        # 基于系统运行时间调整
        runtime_hours = system_state.get("system_runtime", 0) / 3600
        if runtime_hours > 24:  # 运行超过24小时
            logger.info(
                f"System running for {runtime_hours:.1f} hours, optimizing for stability"
            )
            config_updates.update(
                {
                    "data_pipeline": {
                        "cache_ttl": 7200,  # 延长缓存时间
                        "max_retries": 5,  # 增加重试次数
                    },
                    "circuit_breaker": {
                        "recovery_check_interval": 300,  # 延长恢复检查间隔
                    },
                }
            )

        # 基于模块健康状态调整
        module_health = system_state.get("module_health", {})
        for module_name, health_score in module_health.items():
            if health_score < 0.7:  # 健康分数低于70%
                logger.warning(f"Low health score for {module_name}: {health_score}")
                # 为该模块添加保守配置
                if module_name in ["tr_detector", "curve_analyzer"]:
                    config_updates[module_name] = {
                        "stability_threshold": 0.8,  # 提高稳定性要求
                        "min_samples": 50,  # 增加最小样本数
                    }

        return config_updates


async def main_example():
    """系统协调器使用示例"""

    # 创建配置
    config = {
        "mode": "paper",
        "data_pipeline": {
            "redis_host": "localhost",
            "redis_port": 6379,
        },
        "state_file": "system_state.json",
    }

    # 初始化系统协调器
    orchestrator = SystemOrchestrator(config)

    # 启动系统
    await orchestrator.start()

    # 创建模拟数据
    timeframes = ["H4", "H1", "M15"]
    # 映射到pandas频率字符串
    freq_map = {"H4": "4H", "H1": "1H", "M15": "15T"}
    data_dict = {}

    for tf in timeframes:
        freq = freq_map.get(tf, tf)
        dates = pd.date_range(end=datetime.now(), periods=100, freq=freq)
        data = pd.DataFrame(
            {
                "open": np.random.randn(len(dates)).cumsum() + 100,
                "high": np.random.randn(len(dates)).cumsum() + 101,
                "low": np.random.randn(len(dates)).cumsum() + 99,
                "close": np.random.randn(len(dates)).cumsum() + 100,
                "volume": np.random.randint(1000, 10000, len(dates)),
            },
            index=dates,
        )
        data_dict[tf] = data

    # 处理市场数据
    await orchestrator.process_market_data(
        symbol="BTC/USDT", timeframes=timeframes, data_dict=data_dict
    )

    # 显示决策结果

    # 获取系统状态
    orchestrator.get_system_status()

    # 运行进化周期
    await orchestrator.run_evolution_cycle()

    # 停止系统
    await orchestrator.stop()



if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 运行示例
    asyncio.run(main_example())
