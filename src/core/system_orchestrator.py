"""
系统协调器向后兼容模块

此模块提供向后兼容导入，将 src.core.system_orchestrator 重定向到新包结构。

已废弃: 请使用 src.core.orchestrator 导入
"""

# 导入核心类 - 从legacy文件导入以保持枚举一致性
# 重新导出原始文件中的类以支持测试的mock
# 这些是原始system_orchestrator导入的模块
from src.core.data_pipeline import DataPipeline, Timeframe
from src.core.market_regime import RegimeDetector

# 向后兼容导入 - 从orchestrator包导入
from src.core.orchestrator import (
    AlertLevel,
    HealthStatus,
)
from src.core.system_orchestrator_legacy import (
    DecisionContext,
    SystemMode,
    SystemOrchestrator,
    TradingDecision,
    TradingSignal,
    WyckoffSignal,
)

try:
    from src.perception.fvg_detector import FVGDetector
except ImportError:
    try:
        from perception.fvg_detector import FVGDetector
    except ImportError:
        FVGDetector = None

from src.core.anomaly_validator import AnomalyValidator
from src.core.breakout_validator import BreakoutValidator
from src.core.circuit_breaker import CircuitBreaker
from src.core.conflict_resolver import (
    ConflictResolutionManager,
    ConflictType,
    ResolutionBias,
)
from src.core.curve_boundary import CurveBoundaryFitter
from src.core.data_sanitizer import DataSanitizer, DataSanitizerConfig, MarketType
from src.core.decision_visualizer import DecisionVisualizer
from src.core.evolution_archivist import EvolutionArchivist, EvolutionEventType
from src.core.micro_entry_validator import MicroEntryValidator
from src.core.mistake_book import ErrorPattern, ErrorSeverity, MistakeBook, MistakeType
from src.core.performance_monitor import (
    AlertLevel as PMAlertLevel,
)
from src.core.performance_monitor import (
    HealthStatus as PMHealthStatus,
)
from src.core.performance_monitor import (
    ModuleType,
    PerformanceMonitor,
)
from src.core.period_weight_filter import PeriodWeightFilter
from src.core.tr_detector import TRDetector
from src.core.weight_variator import WeightVariator
from src.core.wfa_backtester import PerformanceMetric, ValidationResult, WFABacktester

# 从wyckoff_state_machine包导入
from src.core.wyckoff_state_machine import EnhancedWyckoffStateMachine, StateConfig

# 为了向后兼容，同时导出
DataPipeline = DataPipeline
Timeframe = Timeframe
RegimeDetector = RegimeDetector
FVGDetector = FVGDetector if FVGDetector else None
TRDetector = TRDetector
CurveBoundaryFitter = CurveBoundaryFitter
BreakoutValidator = BreakoutValidator
AnomalyValidator = AnomalyValidator
CircuitBreaker = CircuitBreaker
DecisionVisualizer = DecisionVisualizer
DataSanitizer = DataSanitizer
DataSanitizerConfig = DataSanitizerConfig
MarketType = MarketType
PeriodWeightFilter = PeriodWeightFilter
ConflictResolutionManager = ConflictResolutionManager
ConflictType = ConflictType
ResolutionBias = ResolutionBias
MicroEntryValidator = MicroEntryValidator
EnhancedWyckoffStateMachine = EnhancedWyckoffStateMachine
StateConfig = StateConfig
MistakeBook = MistakeBook
MistakeType = MistakeType
ErrorSeverity = ErrorSeverity
ErrorPattern = ErrorPattern
WeightVariator = WeightVariator
WFABacktester = WFABacktester
PerformanceMetric = PerformanceMetric
ValidationResult = ValidationResult
PerformanceMonitor = PerformanceMonitor
ModuleType = ModuleType
PMHealthStatus = PMHealthStatus
PMAlertLevel = PMAlertLevel
EvolutionArchivist = EvolutionArchivist
EvolutionEventType = EvolutionEventType


__all__ = [
    "AlertLevel",
    "AnomalyValidator",
    "BreakoutValidator",
    "CircuitBreaker",
    "ConflictResolutionManager",
    "ConflictType",
    "CurveBoundaryFitter",
    # 导出类
    "DataPipeline",
    "DataSanitizer",
    "DataSanitizerConfig",
    "DecisionContext",
    "DecisionVisualizer",
    "EnhancedWyckoffStateMachine",
    "ErrorPattern",
    "ErrorSeverity",
    "EvolutionArchivist",
    "EvolutionEventType",
    "FVGDetector",
    "HealthStatus",
    "MarketType",
    "MicroEntryValidator",
    "MistakeBook",
    "MistakeType",
    "ModuleType",
    "PerformanceMetric",
    "PerformanceMonitor",
    "PeriodWeightFilter",
    "RegimeDetector",
    "ResolutionBias",
    "StateConfig",
    "SystemMode",
    # 核心类
    "SystemOrchestrator",
    "TRDetector",
    "Timeframe",
    "TradingDecision",
    "TradingSignal",
    "ValidationResult",
    "WFABacktester",
    "WeightVariator",
    "WyckoffSignal",
]
