"""
异常数据清洗模块（DataSanitizer类）
实现计划书第2.5节的异常数据清洗模块

设计原则（根据计划书第2.5.4节）：
1. **异常即信号原则**：VSA分析的核心就是异常。禁止对价格跳空、极端成交量等异常数据进行平滑或插值处理。
2. **事件封装传递**：检测到异常时，将其封装为Anomaly_Event对象，包含原始数据、异常类型、严重度评分。
3. **市场类型敏感处理**：
   - 股票市场：允许有限的插值（如停牌导致的零成交量）
   - 加密/外汇市场：禁止插值。数据中断时触发熔断机制
4. **熔断机制保护**：加密/外汇市场检测到数据中断时，触发系统熔断，强制空仓或停止交易。
5. **可追溯分析**：记录所有异常事件、熔断激活/解除时间、状态机处理结果。

核心功能：
1. 异常检测（成交量异常、价格跳空、时间戳错误、范围异常）
2. 异常事件封装（AnomalyEvent对象）
3. 市场类型敏感处理
4. 熔断机制集成
5. 数据质量验证

注意：本模块与现有的anomaly_validator.py和circuit_breaker.py协同工作，
而非替换它们。DataSanitizer作为数据预处理层，anomaly_validator作为验证层，
circuit_breaker作为保护层。
"""

import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

# 导入现有模块
try:
    from src.plugins.risk_management.anomaly_validator import (
        AnomalyType,
        AnomalyValidator,
        ValidationResult,
    )
    from src.plugins.risk_management.circuit_breaker import (
        CircuitBreaker,
        CircuitBreakerStatus,
    )
except ImportError:
    AnomalyValidator = None
    AnomalyType = None
    ValidationResult = None
    CircuitBreaker = None
    CircuitBreakerStatus = None


class MarketType(Enum):
    """市场类型（影响数据处理策略）"""

    STOCK = "STOCK"  # 股票市场（允许有限插值）
    CRYPTO = "CRYPTO"  # 加密货币市场（禁止插值，触发熔断）
    FOREX = "FOREX"  # 外汇市场（禁止插值，触发熔断）
    FUTURES = "FUTURES"  # 期货市场


class AnomalySeverity(Enum):
    """异常严重程度"""

    INFO = "INFO"  # 信息级异常（可忽略）
    WARNING = "WARNING"  # 警告级异常（需关注）
    ERROR = "ERROR"  # 错误级异常（需处理）
    CRITICAL = "CRITICAL"  # 严重异常（触发熔断）


@dataclass
class RawCandle:
    """原始K线数据结构（不修改）"""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: Optional[str] = None
    exchange: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
            "exchange": self.exchange,
        }


@dataclass
class AnomalyEvent:
    """
    异常事件对象 - 用于封装异常K线数据，而非清洗

    根据计划书第365-392行的设计，VSA分析的核心就是异常，
    异常是主力资金留下的"脚印"，应作为信号分析而非噪声清洗。
    """

    raw_candle: RawCandle  # 原始K线数据（不修改）
    anomaly_types: list[str]  # 异常类型列表
    anomaly_score: float  # 异常严重度分数 [0-1]
    market_type: MarketType  # 市场类型：STOCK/CRYPTO/FOREX
    impact_score: float = 0.0  # 市场影响评分（由状态机计算）
    main_intent: Optional[str] = None  # 主力意图分析结果
    event_category: Optional[str] = None  # 自动分类的事件类型
    suggested_action: Optional[str] = None  # 建议处理动作

    def __post_init__(self):
        """自动分类异常事件类型"""
        if "EXTREME_GAP" in self.anomaly_types:
            self.event_category = "PRICE_GAP_EVENT"
            self.suggested_action = "ANALYZE_AS_BREAKOUT_OR_EXHAUSTION"
        elif "ZERO_VOLUME" in self.anomaly_types:
            self.event_category = "LIQUIDITY_EVENT"
            self.suggested_action = "CHECK_EXCHANGE_STATUS"
        elif "EXTREME_VOLUME" in self.anomaly_types:
            self.event_category = "VOLUME_CLIMAX_EVENT"
            self.suggested_action = "ANALYZE_AS_SC_OR_BC"
        else:
            self.event_category = "GENERIC_ANOMALY"
            self.suggested_action = "PASS_TO_STATE_MACHINE"

    def to_state_machine_input(self) -> dict[str, Any]:
        """
        转换为状态机输入格式（计划书第393-411行）
        """
        return {
            "type": "ANOMALY_EVENT",
            "event_category": self.event_category,
            "anomaly_score": self.anomaly_score,
            "raw_data": self.raw_candle.to_dict(),
            "market_context": self.market_type.value,
            "suggested_analysis": self.suggested_action,
            "timestamp": self.raw_candle.timestamp,
        }


@dataclass
class HistoricalContext:
    """历史上下文数据（用于异常检测）"""

    volume_ma20: float = 0.0  # 20周期成交量移动平均
    volume_ma50: float = 0.0  # 50周期成交量移动平均
    previous_close: Optional[float] = None  # 前收盘价
    atr14: float = 1.0  # 14周期ATR
    avg_body_size: float = 1.0  # 平均实体大小
    price_ma50: Optional[float] = None  # 50周期价格移动平均
    recent_candles: list[RawCandle] = field(default_factory=list)  # 最近K线


class DataSanitizerConfig:
    """
    数据清洗配置类（计划书第574-600行）

    动态参数配置，所有阈值均为动态参数，可随市场波动率自动调整
    """

    def __init__(self):
        # 市场类型配置
        self.MARKET_TYPE = MarketType.CRYPTO  # STOCK/CRYPTO/FOREX

        # 异常检测阈值（根据市场波动率动态调整）
        self.ANOMALY_THRESHOLD = 0.7  # 异常分数阈值
        self.MAX_VOLUME_RATIO = 10.0  # 最大成交量倍数
        self.MAX_GAP_ATR_MULTIPLE = 5.0  # 最大跳空ATR倍数
        self.MAX_RANGE_ATR_MULTIPLE = 4.0  # 最大价格范围ATR倍数

        # 时间戳一致性检查
        self.MAX_TIMESTAMP_GAP_SECONDS = 3600  # 最大时间戳间隔（秒）
        self.ALLOW_TIMESTAMP_OVERLAP = False  # 是否允许时间戳重叠

        # 熔断机制参数
        self.CIRCUIT_BREAKER_ENABLED = True
        self.CIRCUIT_BREAKER_RECOVERY_BARS = 5  # 恢复所需正常K线数
        self.CIRCUIT_BREAKER_MAX_DURATION = {
            MarketType.STOCK.value: 3600,  # 股票市场：1小时
            MarketType.CRYPTO.value: 900,  # 加密市场：15分钟
            MarketType.FOREX.value: 1800,  # 外汇市场：30分钟
        }

        # 数据插值配置（仅股票市场）
        self.STOCK_INTERPOLATION_ENABLED = True
        self.MAX_INTERPOLATION_GAP_BARS = 3  # 最大插值K线数

        # 自动进化标识（这些参数将被纳入权重调整范围）
        self._evolution_params = [
            "ANOMALY_THRESHOLD",
            "MAX_VOLUME_RATIO",
            "MAX_GAP_ATR_MULTIPLE",
            "MAX_RANGE_ATR_MULTIPLE",
            "CIRCUIT_BREAKER_RECOVERY_BARS",
        ]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "MARKET_TYPE": self.MARKET_TYPE.value,
            "ANOMALY_THRESHOLD": self.ANOMALY_THRESHOLD,
            "MAX_VOLUME_RATIO": self.MAX_VOLUME_RATIO,
            "MAX_GAP_ATR_MULTIPLE": self.MAX_GAP_ATR_MULTIPLE,
            "MAX_RANGE_ATR_MULTIPLE": self.MAX_RANGE_ATR_MULTIPLE,
            "MAX_TIMESTAMP_GAP_SECONDS": self.MAX_TIMESTAMP_GAP_SECONDS,
            "ALLOW_TIMESTAMP_OVERLAP": self.ALLOW_TIMESTAMP_OVERLAP,
            "CIRCUIT_BREAKER_ENABLED": self.CIRCUIT_BREAKER_ENABLED,
            "CIRCUIT_BREAKER_RECOVERY_BARS": self.CIRCUIT_BREAKER_RECOVERY_BARS,
            "CIRCUIT_BREAKER_MAX_DURATION": self.CIRCUIT_BREAKER_MAX_DURATION,
            "STOCK_INTERPOLATION_ENABLED": self.STOCK_INTERPOLATION_ENABLED,
            "MAX_INTERPOLATION_GAP_BARS": self.MAX_INTERPOLATION_GAP_BARS,
        }


class DataSanitizer:
    """
    数据清洗器（计划书第414-570行）

    检测K线异常，但不清洗数据。异常数据封装为AnomalyEvent对象，
    供状态机分析主力意图。
    """

    def __init__(self, config: Optional[DataSanitizerConfig] = None):
        self.config = config or DataSanitizerConfig()
        self.market_type = self.config.MARKET_TYPE

        # 熔断机制状态
        self.circuit_breaker_active = False
        self.circuit_breaker_start_time: Optional[datetime] = None
        self.circuit_breaker_recovery_count = 0

        # 异常事件历史记录
        self.anomaly_history: list[dict[str, Any]] = []
        self.consecutive_anomalies = 0

        # 初始化现有模块（如果可用）
        self.anomaly_validator = None
        self.circuit_breaker = None

        try:
            self.anomaly_validator = AnomalyValidator()
            self.circuit_breaker = CircuitBreaker()
        except Exception as e:
            warnings.warn(f"无法初始化辅助模块: {e}")

    def sanitize_candle(
        self,
        raw_candle: Union[RawCandle, dict[str, Any]],
        historical_context: Optional[HistoricalContext] = None,
    ) -> tuple[Union[RawCandle, AnomalyEvent], bool, Optional[AnomalyEvent]]:
        """
        检测K线异常，但不清洗数据（计划书第422-469行）

        返回: (data_object, is_anomaly, anomaly_event)
        - 正常数据: 返回原始K线
        - 异常数据: 返回AnomalyEvent对象，供状态机分析主力意图

        Args:
            raw_candle: 原始K线数据
            historical_context: 历史上下文

        Returns:
            Tuple: (处理后的数据对象, 是否为异常, 异常事件对象)
        """
        # 1. 参数标准化
        if isinstance(raw_candle, dict):
            raw_candle = RawCandle(**raw_candle)

        if historical_context is None:
            historical_context = HistoricalContext()

        # 2. 检查熔断机制（加密/外汇市场）
        if self._check_circuit_breaker(raw_candle, historical_context):
            return self._handle_circuit_breaker(raw_candle, historical_context)

        # 3. 异常检测
        anomaly_checks = self._perform_anomaly_checks(raw_candle, historical_context)

        # 4. 计算异常分数
        anomaly_score = sum(check["score"] for check in anomaly_checks)
        is_anomaly = anomaly_score > self.config.ANOMALY_THRESHOLD

        if is_anomaly:
            # 异常数据 → 创建AnomalyEvent对象（不修改原始数据）
            anomaly_types = [
                check["type"] for check in anomaly_checks if check["score"] > 0
            ]
            anomaly_event = AnomalyEvent(
                raw_candle=raw_candle,
                anomaly_types=anomaly_types,
                anomaly_score=anomaly_score,
                market_type=self.market_type,
            )

            # 记录异常事件
            self._record_anomaly_event(anomaly_event, anomaly_score)

            # 检查是否需要触发熔断（加密/外汇市场的数据中断）
            if self._should_trigger_circuit_breaker(anomaly_types, historical_context):
                self._activate_circuit_breaker(anomaly_event)

            return anomaly_event, True, anomaly_event

        # 5. 正常数据 → 直接返回原始K线
        # 重置连续异常计数
        self.consecutive_anomalies = 0

        # 如果熔断激活中，增加恢复计数
        if self.circuit_breaker_active:
            self.circuit_breaker_recovery_count += 1
            if (
                self.circuit_breaker_recovery_count
                >= self.config.CIRCUIT_BREAKER_RECOVERY_BARS
            ):
                self._deactivate_circuit_breaker()

        return raw_candle, False, None

    def _to_unix_ms(self, timestamp) -> int:
        """
        将时间戳转换为Unix毫秒整数

        支持的类型：
        - datetime.datetime
        - pandas.Timestamp
        - int (假设已经是Unix毫秒)
        - float (假设是Unix毫秒，转换为整数)
        """
        from datetime import datetime

        import pandas as pd

        if isinstance(timestamp, (int, np.integer)):
            # 假设已经是Unix毫秒
            return int(timestamp)
        if isinstance(timestamp, float):
            # 假设是Unix毫秒，转换为整数
            return int(timestamp)
        if isinstance(timestamp, pd.Timestamp):
            # pandas Timestamp: 转换为Unix毫秒整数
            # .value 属性返回纳秒，除以10**6得到毫秒
            return int(timestamp.value // 10**6)
        if isinstance(timestamp, datetime):
            # datetime对象: 转换为Unix毫秒整数
            # 使用timestamp()方法返回浮点秒数，乘以1000得到毫秒
            return int(timestamp.timestamp() * 1000)
        # 其他类型尝试转换
        try:
            # 尝试转换为pandas Timestamp然后转换
            ts = pd.Timestamp(timestamp)
            return int(ts.value // 10**6)
        except Exception as e:
            raise TypeError(f"无法转换时间戳类型 {type(timestamp)} 为Unix毫秒整数: {e}")

    def _perform_anomaly_checks(
        self, candle: RawCandle, context: HistoricalContext
    ) -> list[dict[str, Any]]:
        """
        执行异常检查（计划书第433-469行）

        Returns:
            List[Dict]: 异常检查结果列表
        """
        return [
            self._check_volume_anomaly(candle, context),
            self._check_price_gap(candle, context),
            self._check_timestamp_consistency(candle, context),
            self._check_range_anomaly(candle, context),
        ]

    def _check_volume_anomaly(
        self, candle: RawCandle, context: HistoricalContext
    ) -> dict[str, Any]:
        """
        检查成交量异常（VSA分析的核心就是异常，不应清洗）

        计划书第540-551行
        """
        if candle.volume == 0:
            return {
                "type": "ZERO_VOLUME",
                "score": 1.0,
                "severity": AnomalySeverity.CRITICAL,
            }

        # 使用50周期移动平均
        if context.volume_ma50 > 0:
            volume_ratio = candle.volume / context.volume_ma50
            if volume_ratio > self.config.MAX_VOLUME_RATIO:
                return {
                    "type": "EXTREME_VOLUME",
                    "score": 0.8,
                    "severity": AnomalySeverity.ERROR,
                    "details": {"volume_ratio": volume_ratio},
                }

        return {"type": "NORMAL", "score": 0.0, "severity": AnomalySeverity.INFO}

    def _check_price_gap(
        self, candle: RawCandle, context: HistoricalContext
    ) -> dict[str, Any]:
        """
        检查价格跳空（异常就是信号，不应平滑）

        计划书第553-568行
        """
        if context.previous_close is None:
            return {"type": "NORMAL", "score": 0.0, "severity": AnomalySeverity.INFO}

        gap_percent = abs(candle.open - context.previous_close) / context.previous_close
        gap_abs = abs(candle.open - context.previous_close)  # 价格绝对值
        atr_multiple = (
            gap_abs / context.atr14 if context.atr14 > 0 else 0
        )  # 同单位（价格/价格）

        if atr_multiple > self.config.MAX_GAP_ATR_MULTIPLE:
            return {
                "type": "EXTREME_GAP",
                "score": 0.9,
                "severity": AnomalySeverity.ERROR,
                "details": {"gap_percent": gap_percent, "atr_multiple": atr_multiple},
            }

        return {"type": "NORMAL", "score": 0.0, "severity": AnomalySeverity.INFO}

    def _check_timestamp_consistency(
        self, candle: RawCandle, context: HistoricalContext
    ) -> dict[str, Any]:
        """检查时间戳一致性"""
        if not context.recent_candles:
            return {"type": "NORMAL", "score": 0.0, "severity": AnomalySeverity.INFO}

        last_candle = context.recent_candles[-1]
        # 转换为Unix毫秒整数，避免Timestamp与int的类型比较错误
        ts1 = self._to_unix_ms(candle.timestamp)
        ts2 = self._to_unix_ms(last_candle.timestamp)
        time_gap_ms = ts1 - ts2  # 毫秒差
        time_gap = time_gap_ms / 1000.0  # 转换为秒

        if time_gap > self.config.MAX_TIMESTAMP_GAP_SECONDS:
            return {
                "type": "TIMESTAMP_GAP",
                "score": 0.6,
                "severity": AnomalySeverity.WARNING,
                "details": {"time_gap_seconds": time_gap},
            }

        # 检查时间戳重叠
        if not self.config.ALLOW_TIMESTAMP_OVERLAP and time_gap < 0:
            return {
                "type": "TIMESTAMP_OVERLAP",
                "score": 0.7,
                "severity": AnomalySeverity.ERROR,
                "details": {"time_gap_seconds": time_gap},
            }

        return {"type": "NORMAL", "score": 0.0, "severity": AnomalySeverity.INFO}

    def _check_range_anomaly(
        self, candle: RawCandle, context: HistoricalContext
    ) -> dict[str, Any]:
        """检查价格范围异常"""
        price_range = candle.high - candle.low
        atr_multiple = price_range / context.atr14 if context.atr14 > 0 else 0

        if atr_multiple > self.config.MAX_RANGE_ATR_MULTIPLE:
            return {
                "type": "EXTREME_RANGE",
                "score": 0.7,
                "severity": AnomalySeverity.WARNING,
                "details": {"range_atr_multiple": atr_multiple},
            }

        # 检查价格是否超出合理范围
        if context.price_ma50 is not None:
            deviation = abs(candle.close - context.price_ma50) / context.price_ma50
            if deviation > 0.5:  # 50%偏离
                return {
                    "type": "PRICE_DEVIATION",
                    "score": 0.5,
                    "severity": AnomalySeverity.WARNING,
                    "details": {"deviation_percent": deviation * 100},
                }

        return {"type": "NORMAL", "score": 0.0, "severity": AnomalySeverity.INFO}

    def _check_circuit_breaker(
        self, candle: RawCandle, context: HistoricalContext
    ) -> bool:
        """
        检查熔断机制是否激活

        计划书第471-487行
        """
        if not self.circuit_breaker_active:
            return False

        # 检查熔断是否超时
        if self.circuit_breaker_start_time:
            # 转换为Unix毫秒整数，避免Timestamp与int的类型比较错误
            ts1 = self._to_unix_ms(candle.timestamp)
            ts2 = self._to_unix_ms(self.circuit_breaker_start_time)
            time_since_activation_ms = ts1 - ts2  # 毫秒差
            time_since_activation = time_since_activation_ms / 1000.0  # 转换为秒
            max_duration = self.config.CIRCUIT_BREAKER_MAX_DURATION.get(
                self.market_type.value, 3600
            )

            if time_since_activation > max_duration:
                self._deactivate_circuit_breaker()
                return False

        return self.circuit_breaker_active

    def _should_trigger_circuit_breaker(
        self, anomaly_types: list[str], context: HistoricalContext
    ) -> bool:
        """
        判断是否应该触发熔断机制

        计划书第489-504行
        """
        if self.market_type == MarketType.STOCK:
            return False  # 股票市场允许插值

        # 加密/外汇市场：零成交量或极端跳空且连续出现
        if "ZERO_VOLUME" in anomaly_types or "EXTREME_GAP" in anomaly_types:
            # 检查是否连续异常
            recent_anomalies = len(
                [e for e in self.anomaly_history[-3:] if e.get("score", 0) > 0.8]
            )
            return recent_anomalies >= 2

        return False

    def _activate_circuit_breaker(self, anomaly_event: AnomalyEvent):
        """
        激活熔断机制

        计划书第506-514行
        """
        self.circuit_breaker_active = True
        self.circuit_breaker_start_time = anomaly_event.raw_candle.timestamp
        self.circuit_breaker_recovery_count = 0

        # 如果circuit_breaker模块可用，也触发它
        if self.circuit_breaker:
            try:
                self.circuit_breaker.manual_trip(
                    f"data_sanitizer: {anomaly_event.event_category} ({self.market_type.value})"
                )
            except Exception as e:
                warnings.warn(f"无法触发外部熔断器: {e}")

    def _deactivate_circuit_breaker(self):
        """
        解除熔断机制

        计划书第516-522行
        """
        self.circuit_breaker_active = False
        self.circuit_breaker_start_time = None
        self.circuit_breaker_recovery_count = 0

        # 如果circuit_breaker模块可用，也恢复它
        if self.circuit_breaker:
            try:
                self.circuit_breaker.manual_recover()
            except Exception as e:
                warnings.warn(f"无法恢复外部熔断器: {e}")

    def _handle_circuit_breaker(
        self, raw_candle: RawCandle, context: HistoricalContext
    ):
        """
        熔断状态下的数据处理

        计划书第524-538行
        """
        circuit_event = AnomalyEvent(
            raw_candle=raw_candle,
            anomaly_types=["CIRCUIT_BREAKER_ACTIVE"],
            anomaly_score=1.0,
            market_type=self.market_type,
        )
        circuit_event.event_category = "CIRCUIT_BREAKER_EVENT"
        circuit_event.suggested_action = "STOP_TRADING_UNTIL_RECOVERY"

        return circuit_event, True, circuit_event

    def _record_anomaly_event(self, anomaly_event: AnomalyEvent, score: float):
        """记录异常事件"""
        self.anomaly_history.append(
            {
                "timestamp": anomaly_event.raw_candle.timestamp,
                "event": anomaly_event,
                "score": score,
                "market_type": self.market_type.value,
            }
        )

        # 限制历史记录长度
        if len(self.anomaly_history) > 1000:
            self.anomaly_history = self.anomaly_history[-1000:]

        # 更新连续异常计数
        if score > 0.7:  # 严重异常
            self.consecutive_anomalies += 1
        else:
            self.consecutive_anomalies = max(0, self.consecutive_anomalies - 1)

    def get_anomaly_statistics(self, last_n: int = 100) -> dict[str, Any]:
        """获取异常统计信息"""
        if not self.anomaly_history:
            return {}

        recent_events = (
            self.anomaly_history[-last_n:] if last_n > 0 else self.anomaly_history
        )

        # 统计异常类型
        anomaly_counts = {}
        for event in recent_events:
            anomaly_event = event.get("event")
            if anomaly_event and hasattr(anomaly_event, "anomaly_types"):
                for anomaly_type in anomaly_event.anomaly_types:
                    anomaly_counts[anomaly_type] = (
                        anomaly_counts.get(anomaly_type, 0) + 1
                    )

        # 计算平均分数
        avg_score = np.mean([e.get("score", 0) for e in recent_events])

        return {
            "total_events": len(recent_events),
            "avg_anomaly_score": avg_score,
            "anomaly_type_counts": anomaly_counts,
            "consecutive_anomalies": self.consecutive_anomalies,
            "circuit_breaker_active": self.circuit_breaker_active,
            "circuit_breaker_recovery_count": self.circuit_breaker_recovery_count,
        }

    def sanitize_dataframe(
        self,
        df: pd.DataFrame,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> tuple[pd.DataFrame, list[AnomalyEvent]]:
        """
        清洗DataFrame数据

        Args:
            df: 包含OHLCV列的DataFrame
            symbol: 交易对符号
            exchange: 交易所名称

        Returns:
            Tuple: (清洗后的DataFrame, 异常事件列表)
        """
        if df.empty:
            return df, []

        # 确保DataFrame包含必要列
        required_columns = ["open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required_columns):
            raise ValueError(f"DataFrame必须包含以下列: {required_columns}")

        # 按时间排序
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp")
        elif df.index.name == "timestamp" or df.index.dtype == "datetime64[ns]":
            df = df.sort_index()
        elif hasattr(df.index, "dtype") and df.index.dtype in ("int64", "int32", "int"):
            # 整数索引（可能是Unix毫秒时间戳），也按索引排序
            df = df.sort_index()

        # 处理每一行
        anomalies = []
        processed_rows = []

        # 构建历史上下文
        context = HistoricalContext()
        if len(df) >= 20:
            context.volume_ma20 = df["volume"].rolling(20).mean().iloc[-1]
        if len(df) >= 50:
            context.volume_ma50 = df["volume"].rolling(50).mean().iloc[-1]
            context.price_ma50 = df["close"].rolling(50).mean().iloc[-1]

        # 计算ATR
        if len(df) >= 14:
            high_low = df["high"] - df["low"]
            high_close = abs(df["high"] - df["close"].shift(1))
            low_close = abs(df["low"] - df["close"].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            context.atr14 = tr.rolling(14).mean().iloc[-1]

        # 计算平均实体大小
        body_sizes = abs(df["close"] - df["open"])
        context.avg_body_size = body_sizes.mean() if not body_sizes.empty else 1.0

        for idx, (i, row) in enumerate(df.iterrows()):
            # 创建RawCandle对象
            # 处理多种时间戳格式：Timestamp对象、datetime对象、Unix毫秒整数
            if isinstance(row.name, pd.Timestamp):
                timestamp = row.name.to_pydatetime()
            elif isinstance(row.name, datetime):
                timestamp = row.name
            elif isinstance(row.name, (int, np.integer)):
                # Unix毫秒整数 -> datetime
                try:
                    timestamp = datetime.fromtimestamp(row.name / 1000.0)
                except (ValueError, TypeError):
                    timestamp = datetime.now()
            else:
                # 尝试通用转换
                try:
                    timestamp = pd.to_datetime(i).to_pydatetime()
                except Exception:
                    timestamp = datetime.now()
            raw_candle = RawCandle(
                timestamp=timestamp,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                symbol=symbol,
                exchange=exchange,
            )

            # 更新历史上下文
            if idx > 0:
                context.previous_close = df.iloc[idx - 1]["close"]
            context.recent_candles.append(raw_candle)
            if len(context.recent_candles) > 20:
                context.recent_candles.pop(0)

            # 清洗K线
            _sanitized_data, is_anomaly, anomaly_event = self.sanitize_candle(
                raw_candle, context
            )

            if is_anomaly and anomaly_event:
                anomalies.append(anomaly_event)
                # 对于异常数据，仍然保留原始数据（不插值）
                processed_rows.append(raw_candle.to_dict())
            else:
                processed_rows.append(raw_candle.to_dict())

        # 创建处理后的DataFrame
        processed_df = pd.DataFrame(processed_rows)
        if not processed_df.empty and "timestamp" in processed_df.columns:
            # 设置索引并确保索引为Unix毫秒整数
            processed_df = processed_df.set_index("timestamp")

            # 如果索引是datetime对象，转换为Unix毫秒整数
            if isinstance(processed_df.index, pd.DatetimeIndex):
                # 转换为Unix毫秒整数
                unix_ms_index = processed_df.index.astype("int64") // 10**6
                processed_df.index = unix_ms_index.astype("int64")
            elif (
                hasattr(processed_df.index, "dtype")
                and processed_df.index.dtype == "datetime64[ns]"
            ):
                # 处理datetime64类型的索引
                unix_ms_index = processed_df.index.astype("int64") // 10**6
                processed_df.index = unix_ms_index.astype("int64")

        return processed_df, anomalies


# 测试代码
if __name__ == "__main__":
    # 创建测试数据
    test_dates = pd.date_range("2024-01-01", periods=100, freq="H")
    test_data = {
        "open": 100 + np.random.randn(100) * 2,
        "high": 100 + np.random.randn(100) * 2.5,
        "low": 100 + np.random.randn(100) * 2.5,
        "close": 100 + np.random.randn(100) * 2,
        "volume": 1000 + np.random.randn(100) * 200,
    }

    # 添加一些异常
    test_data["volume"][50] = 0  # 零成交量
    test_data["open"][60] = test_data["close"][59] * 1.1  # 跳空
    test_data["volume"][70] = 20000  # 极端成交量

    df = pd.DataFrame(test_data, index=test_dates)

    # 测试加密市场（禁止插值，触发熔断）
    crypto_config = DataSanitizerConfig()
    crypto_config.MARKET_TYPE = MarketType.CRYPTO
    crypto_sanitizer = DataSanitizer(crypto_config)

    processed_df, anomalies = crypto_sanitizer.sanitize_dataframe(
        df, symbol="BTC/USDT", exchange="binance"
    )

    if anomalies:
        pass

    stats = crypto_sanitizer.get_anomaly_statistics()

    # 测试股票市场（允许插值）
    stock_config = DataSanitizerConfig()
    stock_config.MARKET_TYPE = MarketType.STOCK
    stock_sanitizer = DataSanitizer(stock_config)

    processed_df_stock, anomalies_stock = stock_sanitizer.sanitize_dataframe(
        df, symbol="AAPL", exchange="NASDAQ"
    )

    # 测试单根K线清洗
    test_candle = RawCandle(
        timestamp=datetime.now(),
        open=100,
        high=110,
        low=95,
        close=101,
        volume=0,  # 零成交量
        symbol="ETH/USDT",
        exchange="binance",
    )

    context = HistoricalContext(
        volume_ma50=1000,
        previous_close=99,
        atr14=2.0,
        avg_body_size=5.0,
    )

    result, is_anomaly, anomaly_event = crypto_sanitizer.sanitize_candle(
        test_candle, context
    )

    if is_anomaly and anomaly_event:
        # 测试状态机输入转换
        state_machine_input = anomaly_event.to_state_machine_input()
