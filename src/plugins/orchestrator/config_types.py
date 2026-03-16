"""
统一配置系统 - 威科夫全自动逻辑引擎的配置管理
实现计划书第2.4.2节和第2.5.3节的动态参数配置

设计原则：
1. 动态参数：所有阈值均为动态参数，可随市场波动率自动调整
2. 可进化参数：标记为_evolution_params的参数将被纳入自动进化范围
3. 类型安全：完整的类型提示和默认值
4. 序列化支持：支持JSON序列化和反序列化
5. 配置继承：支持配置继承和覆盖

包含的配置类：
1. TRConfig - 交易区间识别配置
2. DataSanitizerConfig - 数据清洗配置
3. PinBodyAnalyzerConfig - 针vs实体分析配置
4. MarketRegimeConfig - 市场体制检测配置
5. FVGConfig - FVG检测配置
6. WyckoffStateMachineConfig - 威科夫状态机配置
7. SystemOrchestratorConfig - 系统协调器配置
"""

import json
import warnings
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class MarketType(Enum):
    """市场类型"""

    STOCK = "STOCK"  # 股票市场
    CRYPTO = "CRYPTO"  # 加密货币市场
    FOREX = "FOREX"  # 外汇市场
    FUTURES = "FUTURES"  # 期货市场


@dataclass
class TRConfig:
    """
    交易区间识别配置（计划书第2.4.2节）

    稳定性锁定参数（可动态调整），所有阈值均为动态参数，可随市场波动率自动调整
    """

    # 稳定性锁定参数
    TR_LOCK_MIN_QUALITY: float = 0.7  # TR质量最低要求
    TR_BREAKOUT_PERCENT: float = 1.5  # 突破百分比阈值（%）
    TR_CONFIRMATION_BARS: int = 3  # 突破确认所需K线数
    TR_MIN_BARS: int = 20  # 最小区间长度

    # 稳定性判定阈值
    SLOPE_STABILITY_THRESHOLD: float = 0.8  # 斜率稳定性阈值
    BOUNDARY_STABILITY_THRESHOLD: float = 0.75  # 边界稳定性阈值

    # 自动进化标识（这些参数将被纳入权重调整范围）
    _evolution_params: list[str] = field(
        default_factory=lambda: [
            "TR_BREAKOUT_PERCENT",
            "TR_CONFIRMATION_BARS",
            "SLOPE_STABILITY_THRESHOLD",
            "BOUNDARY_STABILITY_THRESHOLD",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（排除私有属性）"""
        data = asdict(self)
        # 移除私有属性
        data.pop("_evolution_params", None)
        return data

    def get_evolution_params(self) -> dict[str, float]:
        """获取可进化参数"""
        params = {}
        for param_name in self._evolution_params:
            if hasattr(self, param_name):
                params[param_name] = getattr(self, param_name)
        return params

    def update_from_dict(self, updates: dict[str, Any]):
        """从字典更新配置"""
        if not updates:
            return
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                warnings.warn(f"TRConfig没有参数'{key}'，跳过更新")


@dataclass
class DataSanitizerConfig:
    """
    数据清洗配置（计划书第2.5.3节）

    动态参数配置，所有阈值根据市场波动率动态调整
    """

    # 市场类型配置
    MARKET_TYPE: MarketType = MarketType.CRYPTO  # STOCK/CRYPTO/FOREX

    # 异常检测阈值（根据市场波动率动态调整）
    ANOMALY_THRESHOLD: float = 0.7  # 异常分数阈值
    MAX_VOLUME_RATIO: float = 10.0  # 最大成交量倍数
    MAX_GAP_ATR_MULTIPLE: float = 5.0  # 最大跳空ATR倍数

    # 熔断机制参数
    CIRCUIT_BREAKER_ENABLED: bool = True
    CIRCUIT_BREAKER_RECOVERY_BARS: int = 5  # 恢复所需正常K线数
    CIRCUIT_BREAKER_MAX_DURATION: dict[str, int] = field(
        default_factory=lambda: {
            MarketType.STOCK.value: 3600,  # 股票市场：1小时
            MarketType.CRYPTO.value: 900,  # 加密市场：15分钟
            MarketType.FOREX.value: 1800,  # 外汇市场：30分钟
        }
    )

    # 自动进化标识
    _evolution_params: list[str] = field(
        default_factory=lambda: [
            "ANOMALY_THRESHOLD",
            "MAX_VOLUME_RATIO",
            "MAX_GAP_ATR_MULTIPLE",
            "CIRCUIT_BREAKER_RECOVERY_BARS",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        # 转换枚举为字符串
        if isinstance(data["MARKET_TYPE"], MarketType):
            data["MARKET_TYPE"] = data["MARKET_TYPE"].value
        # 移除私有属性
        data.pop("_evolution_params", None)
        return data

    def get_evolution_params(self) -> dict[str, Any]:
        """获取可进化参数"""
        params = {}
        for param_name in self._evolution_params:
            if hasattr(self, param_name):
                params[param_name] = getattr(self, param_name)
        return params

    def update_from_dict(self, updates: dict[str, Any]):
        """从字典更新配置"""
        if not updates:
            return
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                warnings.warn(f"DataSanitizerConfig没有参数'{key}'，跳过更新")


@dataclass
class PinBodyAnalyzerConfig:
    """
    针vs实体分析配置（计划书第2.2节）

    动态参数系统：所有阈值根据市场波动率和体制动态调整
    """

    # 基础阈值（正常波动率下的经验值）
    BASE_PIN_THRESHOLD: float = 1.5  # 针主导的基础阈值：影线 > 1.5倍实体
    BASE_BODY_THRESHOLD: float = 2.0  # 实体主导的基础阈值：实体 > 2.0倍影线
    BASE_VOLUME_SPIKE: float = 1.8  # 成交量爆发阈值：成交量 > 1.8倍移动平均
    BASE_EFFORT_THRESHOLD: float = 2.0  # 高努力阈值：成交量 > 2.0倍移动平均
    BASE_RESULT_THRESHOLD: float = 0.5  # 低结果阈值：实体 < 0.5倍平均实体

    # 市场体制调整因子
    TRENDING_BODY_THRESHOLD_FACTOR: float = 0.9  # 趋势市实体阈值因子
    TRENDING_PIN_THRESHOLD_FACTOR: float = 1.1  # 趋势市针阈值因子
    RANGING_PIN_THRESHOLD_FACTOR: float = 0.9  # 盘整市针阈值因子
    RANGING_BODY_THRESHOLD_FACTOR: float = 1.1  # 盘整市实体阈值因子

    # 自动进化标识
    _evolution_params: list[str] = field(
        default_factory=lambda: [
            "BASE_PIN_THRESHOLD",
            "BASE_BODY_THRESHOLD",
            "BASE_VOLUME_SPIKE",
            "BASE_EFFORT_THRESHOLD",
            "BASE_RESULT_THRESHOLD",
        ]
    )

    def calculate_dynamic_thresholds(
        self, volatility_index: float, market_regime: str
    ) -> dict[str, Any]:
        """
        计算动态阈值（计划书第2.2节算法）

        Args:
            volatility_index: 波动率指数（当前ATR/平均ATR）
            market_regime: 市场体制（'TRENDING', 'RANGING', 'VOLATILE', 'UNKNOWN'）

        Returns:
            动态阈值字典
        """
        # 动态调整：高波动时需要更大的针/实体比例
        dynamic_pin_threshold = self.BASE_PIN_THRESHOLD * volatility_index
        dynamic_body_threshold = self.BASE_BODY_THRESHOLD * volatility_index

        # 市场体制调整
        if market_regime == "TRENDING":
            dynamic_body_threshold *= self.TRENDING_BODY_THRESHOLD_FACTOR
            dynamic_pin_threshold *= self.TRENDING_PIN_THRESHOLD_FACTOR
        elif market_regime == "RANGING":
            dynamic_pin_threshold *= self.RANGING_PIN_THRESHOLD_FACTOR
            dynamic_body_threshold *= self.RANGING_BODY_THRESHOLD_FACTOR

        return {
            "pin_threshold": dynamic_pin_threshold,
            "body_threshold": dynamic_body_threshold,
            "volume_spike_threshold": self.BASE_VOLUME_SPIKE / volatility_index,
            "effort_threshold": self.BASE_EFFORT_THRESHOLD / volatility_index,
            "result_threshold": self.BASE_RESULT_THRESHOLD * volatility_index,
            "volatility_factor": volatility_index,
            "market_regime": market_regime,
        }

    def update_from_dict(self, updates: dict[str, Any]):
        """从字典更新配置"""
        if not updates:
            return
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                warnings.warn(f"PinBodyAnalyzerConfig没有参数'{key}'，跳过更新")


@dataclass
class MarketRegimeConfig:
    """市场体制检测配置"""

    # ATR乘数阈值
    MIN_ATR_MULTIPLIER: float = 1.5  # 最小ATR乘数（低波动）
    MAX_ATR_MULTIPLIER: float = 2.5  # 最大ATR乘数（高波动）

    # ADX阈值
    ADX_THRESHOLD: float = 25.0  # ADX趋势阈值

    # 移动平均周期
    ATR_PERIOD: int = 14  # ATR计算周期
    ADX_PERIOD: int = 14  # ADX计算周期

    # 自动进化标识
    _evolution_params: list[str] = field(
        default_factory=lambda: [
            "MIN_ATR_MULTIPLIER",
            "MAX_ATR_MULTIPLIER",
            "ADX_THRESHOLD",
        ]
    )

    def get_evolution_params(self) -> dict[str, float]:
        """获取可进化参数"""
        params = {}
        for param_name in self._evolution_params:
            if hasattr(self, param_name):
                params[param_name] = getattr(self, param_name)
        return params

    def update_from_dict(self, updates: dict[str, Any]):
        """从字典更新配置"""
        if not updates:
            return
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                warnings.warn(f"MarketRegimeConfig没有参数'{key}'，跳过更新")


@dataclass
class FVGConfig:
    """FVG检测配置"""

    FVG_THRESHOLD: float = 0.005  # FVG阈值（0.5%）
    MIN_BODY_RATIO: float = 0.3  # 最小实体比例
    LOOKBACK_PERIODS: int = 50  # 回看周期数

    # 自动进化标识
    _evolution_params: list[str] = field(
        default_factory=lambda: ["FVG_THRESHOLD", "MIN_BODY_RATIO"]
    )

    def get_evolution_params(self) -> dict[str, float]:
        """获取可进化参数"""
        params = {}
        for param_name in self._evolution_params:
            if hasattr(self, param_name):
                params[param_name] = getattr(self, param_name)
        return params

    def update_from_dict(self, updates: dict[str, Any]):
        """从字典更新配置"""
        if not updates:
            return
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                warnings.warn(f"FVGConfig没有参数'{key}'，跳过更新")


@dataclass
class WyckoffStateMachineConfig:
    """威科夫状态机配置"""

    TRANSITION_CONFIDENCE: float = 0.75  # 状态转换置信度阈值
    MIN_STATE_DURATION: int = 3  # 最小状态持续时间（K线数）
    MAX_STATE_DURATION: int = 20  # 最大状态持续时间（K线数）
    HERITAGE_DECAY: float = 0.95  # 强度遗产衰减系数

    # 状态重置参数
    STATE_TIMEOUT_BARS: int = 50  # 状态超时K线数
    SPRING_FAILURE_BARS: int = 5  # Spring失败确认K线数
    STATE_SWITCH_HYSTERESIS: float = 0.15  # 状态切换滞后性阈值（15%）

    # 自动进化标识
    _evolution_params: list[str] = field(
        default_factory=lambda: [
            "TRANSITION_CONFIDENCE",
            "MIN_STATE_DURATION",
            "MAX_STATE_DURATION",
            "HERITAGE_DECAY",
            "STATE_SWITCH_HYSTERESIS",
        ]
    )

    def get_evolution_params(self) -> dict[str, float]:
        """获取可进化参数"""
        params = {}
        for param_name in self._evolution_params:
            if hasattr(self, param_name):
                params[param_name] = getattr(self, param_name)
        return params

    def update_from_dict(self, updates: dict[str, Any]):
        """从字典更新配置"""
        if not updates:
            return
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                warnings.warn(f"WyckoffStateMachineConfig没有参数'{key}'，跳过更新")


@dataclass
class SystemOrchestratorConfig:
    """系统协调器配置"""

    # 运行模式
    MODE: str = "paper"  # backtest/paper/live/evolution

    # 时间框架权重配置
    TIMEFRAME_WEIGHTS: dict[str, float] = field(
        default_factory=lambda: {
            "W1": 0.25,  # 周线
            "D1": 0.20,  # 日线
            "H4": 0.18,  # 4小时
            "H1": 0.15,  # 1小时
            "M15": 0.12,  # 15分钟
            "M5": 0.10,  # 5分钟
        }
    )

    # 最小权重限制
    MIN_TIMEFRAME_WEIGHT: float = 0.05

    # 子模块配置引用
    tr_config: Optional[TRConfig] = None
    data_sanitizer_config: Optional[DataSanitizerConfig] = None
    pin_body_config: Optional[PinBodyAnalyzerConfig] = None
    market_regime_config: Optional[MarketRegimeConfig] = None
    fvg_config: Optional[FVGConfig] = None
    wyckoff_config: Optional[WyckoffStateMachineConfig] = None

    def __post_init__(self):
        """初始化默认子配置"""
        if self.tr_config is None:
            self.tr_config = TRConfig()
        if self.data_sanitizer_config is None:
            self.data_sanitizer_config = DataSanitizerConfig()
        if self.pin_body_config is None:
            self.pin_body_config = PinBodyAnalyzerConfig()
        if self.market_regime_config is None:
            self.market_regime_config = MarketRegimeConfig()
        if self.fvg_config is None:
            self.fvg_config = FVGConfig()
        if self.wyckoff_config is None:
            self.wyckoff_config = WyckoffStateMachineConfig()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "MODE": self.MODE,
            "TIMEFRAME_WEIGHTS": self.TIMEFRAME_WEIGHTS,
            "MIN_TIMEFRAME_WEIGHT": self.MIN_TIMEFRAME_WEIGHT,
            "tr_config": self.tr_config.to_dict() if self.tr_config else {},
            "data_sanitizer_config": self.data_sanitizer_config.to_dict()
            if self.data_sanitizer_config
            else {},
            "pin_body_config": asdict(self.pin_body_config)
            if self.pin_body_config
            else {},
            "market_regime_config": asdict(self.market_regime_config)
            if self.market_regime_config
            else {},
            "fvg_config": asdict(self.fvg_config) if self.fvg_config else {},
            "wyckoff_config": asdict(self.wyckoff_config)
            if self.wyckoff_config
            else {},
        }

    def save_to_file(self, filepath: str):
        """保存配置到文件"""
        import os

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, filepath: str) -> "SystemOrchestratorConfig":
        """从文件加载配置"""
        with open(filepath) as f:
            data = json.load(f)

        config = cls()

        # 更新基本属性
        if "MODE" in data:
            config.MODE = data["MODE"]
        if "TIMEFRAME_WEIGHTS" in data:
            config.TIMEFRAME_WEIGHTS = data["TIMEFRAME_WEIGHTS"]
        if "MIN_TIMEFRAME_WEIGHT" in data:
            config.MIN_TIMEFRAME_WEIGHT = data["MIN_TIMEFRAME_WEIGHT"]

        # 更新子配置
        if data.get("tr_config"):
            config.tr_config = TRConfig()
            config.tr_config.update_from_dict(data["tr_config"])

        if data.get("data_sanitizer_config"):
            config.data_sanitizer_config = DataSanitizerConfig()
            # 处理枚举类型
            ds_data = data["data_sanitizer_config"].copy()
            if "MARKET_TYPE" in ds_data:
                try:
                    ds_data["MARKET_TYPE"] = MarketType(ds_data["MARKET_TYPE"])
                except ValueError:
                    ds_data["MARKET_TYPE"] = MarketType.CRYPTO
            config.data_sanitizer_config.update_from_dict(ds_data)

        # 其他子配置类似处理（简化）

        return config


# 全局默认配置
DEFAULT_CONFIG = SystemOrchestratorConfig()


def create_default_config() -> SystemOrchestratorConfig:
    """创建默认配置"""
    import logging

    logger = logging.getLogger(__name__)
    logger.debug("Creating default configuration")
    return SystemOrchestratorConfig()


def load_config(config_path: Optional[str] = None) -> SystemOrchestratorConfig:
    """加载配置（从文件或使用默认）"""
    if config_path:
        try:
            return SystemOrchestratorConfig.load_from_file(config_path)
        except Exception as e:
            warnings.warn(f"加载配置文件失败 {config_path}: {e}，使用默认配置")

    return create_default_config()


# 测试代码
if __name__ == "__main__":

    # 创建默认配置
    config = create_default_config()


    # 测试动态阈值计算
    thresholds = config.pin_body_config.calculate_dynamic_thresholds(
        volatility_index=1.2, market_regime="RANGING"
    )

    # 测试配置序列化
    config_dict = config.to_dict()

    # 测试可进化参数
    tr_evolution_params = config.tr_config.get_evolution_params()

