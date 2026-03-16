"""
熔断机制模块
加密市场保护机制：数据中断时强制停止交易，防止在异常市场条件下交易

设计目标：
1. 监控数据质量，检测数据中断和异常
2. 在检测到问题时自动触发熔断，停止所有交易活动
3. 提供熔断状态管理和恢复机制
4. 记录熔断事件和原因，便于审计
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import numpy as np


class CircuitBreakerStatus(Enum):
    """熔断器状态枚举"""

    NORMAL = "NORMAL"  # 正常状态，允许交易
    TRIPPED = "TRIPPED"  # 已触发熔断，停止交易
    RECOVERY = "RECOVERY"  # 恢复中，限制性交易
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"  # 手动覆盖


class MarketType(Enum):
    """市场类型枚举"""

    CRYPTO = "CRYPTO"  # 加密货币市场（7x24交易）
    STOCK = "STOCK"  # 股票市场（有交易时间限制）
    FOREX = "FOREX"  # 外汇市场（5x24交易）
    FUTURES = "FUTURES"  # 期货市场（有交易时间限制）


class TripReason(Enum):
    """熔断触发原因枚举"""

    DATA_FEED_INTERRUPTION = "DATA_FEED_INTERRUPTION"  # 数据流中断
    PRICE_ABNORMALITY = "PRICE_ABNORMALITY"  # 价格异常
    VOLUME_ABNORMALITY = "VOLUME_ABNORMALITY"  # 成交量异常
    EXCHANGE_CONNECTION_LOST = "EXCHANGE_CONNECTION_LOST"  # 交易所连接丢失
    HIGH_LATENCY = "HIGH_LATENCY"  # 高延迟
    MULTIPLE_FAILURES = "MULTIPLE_FAILURES"  # 多重故障
    MANUAL_TRIP = "MANUAL_TRIP"  # 手动触发
    MARKET_CLOSED = "MARKET_CLOSED"  # 市场关闭（非交易时间）


@dataclass
class CircuitBreakerEvent:
    """熔断事件记录"""

    event_id: str
    timestamp: datetime
    status: CircuitBreakerStatus
    reason: TripReason
    details: dict[str, Any]
    duration: Optional[timedelta] = None  # 熔断持续时间
    recovery_time: Optional[datetime] = None  # 预计恢复时间

    def __post_init__(self):
        if self.details is None:
            self.details = {}


@dataclass
class DataQualityMetrics:
    """数据质量指标"""

    timestamp: datetime
    symbol: str
    exchange: str

    # 数据完整性
    data_freshness_seconds: float  # 数据新鲜度（秒）
    missing_data_points: int  # 缺失数据点数量
    consecutive_missing: int  # 连续缺失次数

    # 数据合理性
    price_change_pct: float  # 价格变化百分比
    volume_change_pct: float  # 成交量变化百分比
    spread_pct: float  # 买卖价差百分比

    # 连接质量
    latency_ms: float  # 延迟（毫秒）
    success_rate: float  # 请求成功率
    error_count: int  # 错误计数

    # 计算得分
    @property
    def overall_score(self) -> float:
        """计算总体数据质量得分（0-1，越高越好）"""
        scores = []

        # 数据新鲜度得分（超过60秒为0分）
        freshness_score = max(0, 1 - self.data_freshness_seconds / 60)
        scores.append(freshness_score)

        # 数据完整性得分
        completeness_score = 1.0 if self.missing_data_points == 0 else 0.5
        scores.append(completeness_score)

        # 价格合理性得分（价格变化在10%以内为合理）
        price_score = 1.0 if abs(self.price_change_pct) <= 0.10 else 0.3
        scores.append(price_score)

        # 连接质量得分
        latency_score = 1.0 if self.latency_ms < 1000 else 0.5
        scores.append(latency_score)

        success_score = self.success_rate
        scores.append(success_score)

        return float(np.mean(scores)) if scores else 0.0


class CircuitBreaker:
    """
    熔断器

    主要功能：
    1. 持续监控数据质量和连接状态
    2. 在检测到问题时自动触发熔断
    3. 管理熔断状态和恢复过程
    4. 记录所有熔断事件

    熔断触发条件：
    1. 数据流中断 > 30秒
    2. 价格异常波动 > 20%
    3. 连续数据缺失 > 5次
    4. 交易所连接丢失 > 10秒
    5. 高延迟 > 2000ms
    6. 多重故障组合

    恢复条件：
    1. 数据质量恢复正常并保持稳定
    2. 手动恢复指令
    3. 定时自动恢复尝试
    """

    def __init__(
        self,
        trip_threshold: float = 0.3,
        recovery_threshold: float = 0.8,
        min_recovery_time: int = 60,
        max_trip_duration: int = 300,
        market_type: MarketType = MarketType.CRYPTO,
        enable_progressive_recovery: bool = True,
    ):
        """
        初始化熔断器

        Args:
            trip_threshold: 熔断触发阈值（数据质量得分低于此值触发）
            recovery_threshold: 恢复阈值（数据质量得分高于此值可恢复）
            min_recovery_time: 最小恢复时间（秒），触发后至少等待此时间才尝试恢复
            max_trip_duration: 最大熔断持续时间（秒），超过此时间强制尝试恢复
            market_type: 市场类型，影响熔断策略
            enable_progressive_recovery: 是否启用渐进式恢复
        """
        self.trip_threshold = trip_threshold
        self.recovery_threshold = recovery_threshold
        self.min_recovery_time = min_recovery_time
        self.max_trip_duration = max_trip_duration
        self.market_type = market_type
        self.enable_progressive_recovery = enable_progressive_recovery

        # 当前状态
        self.status = CircuitBreakerStatus.NORMAL
        self.trip_time: Optional[datetime] = None
        self.trip_reason: Optional[TripReason] = None
        self.trip_details: dict[str, Any] = {}

        # 历史事件记录
        self.event_history: list[CircuitBreakerEvent] = []

        # 数据质量历史记录
        self.quality_history: list[DataQualityMetrics] = []
        self.max_history_size = 100

        # 监控的交易所和交易对
        self.monitored_symbols: set[str] = set()
        self.monitored_exchanges: set[str] = set()

        # 手动覆盖标志
        self._manual_override_flag = False

        # 渐进式恢复状态
        self.progressive_recovery_stage = 0  # 0=正常，1=限制性交易，2=完全恢复
        self.progressive_recovery_start: Optional[datetime] = None

        # 日志记录器
        self.logger = logging.getLogger(__name__)

    def update_data_quality(self, metrics: DataQualityMetrics) -> bool:
        """
        更新数据质量指标并检查是否需要触发熔断

        Args:
            metrics: 数据质量指标

        Returns:
            是否触发了熔断（True=新触发熔断，False=未触发或已处于熔断状态）
        """
        # 记录质量指标
        self.quality_history.append(metrics)
        if len(self.quality_history) > self.max_history_size:
            self.quality_history.pop(0)

        # 更新监控列表
        self.monitored_symbols.add(metrics.symbol)
        self.monitored_exchanges.add(metrics.exchange)

        # 如果处于手动覆盖状态，不触发自动熔断
        if self.status == CircuitBreakerStatus.MANUAL_OVERRIDE:
            return False

        # 如果处于恢复状态，检查渐进式恢复
        if self.status == CircuitBreakerStatus.RECOVERY:
            recovered = self.check_progressive_recovery(metrics)
            if recovered:
                return True

        # 如果已处于熔断状态，检查是否可以恢复
        if self.status == CircuitBreakerStatus.TRIPPED:
            return self._check_recovery(metrics)

        # 正常状态：检查是否需要触发熔断
        should_trip, reason, details = self._evaluate_trip_conditions(metrics)

        if should_trip:
            assert reason is not None  # 当should_trip为True时，reason不会为None
            return self._trip_breaker(reason, details)

        return False

    def _evaluate_trip_conditions(
        self, metrics: DataQualityMetrics
    ) -> tuple[bool, Optional[TripReason], dict[str, Any]]:
        """
        评估熔断触发条件

        Returns:
            (是否触发, 触发原因, 详情)
        """
        details = {}
        reasons = []

        # 市场类型特定的阈值调整
        market_multiplier = self._get_market_sensitivity_multiplier()

        # 1. 数据流中断检查（根据市场类型调整阈值）
        freshness_threshold = 30 * market_multiplier
        if metrics.data_freshness_seconds > freshness_threshold:
            reasons.append(TripReason.DATA_FEED_INTERRUPTION)
            details["data_freshness"] = metrics.data_freshness_seconds
            details["threshold"] = freshness_threshold

        # 2. 连续数据缺失检查
        missing_threshold = 5
        if metrics.consecutive_missing > missing_threshold:
            reasons.append(TripReason.DATA_FEED_INTERRUPTION)
            details["consecutive_missing"] = metrics.consecutive_missing
            details["threshold"] = missing_threshold

        # 3. 价格异常检查（根据市场类型调整阈值）
        price_threshold = 0.20 * market_multiplier
        if abs(metrics.price_change_pct) > price_threshold:
            reasons.append(TripReason.PRICE_ABNORMALITY)
            details["price_change"] = metrics.price_change_pct
            details["threshold"] = price_threshold

        # 4. 成交量异常检查
        volume_threshold = 5.0
        if abs(metrics.volume_change_pct) > volume_threshold:
            reasons.append(TripReason.VOLUME_ABNORMALITY)
            details["volume_change"] = metrics.volume_change_pct
            details["threshold"] = volume_threshold

        # 5. 高延迟检查
        latency_threshold = 2000
        if metrics.latency_ms > latency_threshold:
            reasons.append(TripReason.HIGH_LATENCY)
            details["latency"] = metrics.latency_ms
            details["threshold"] = latency_threshold

        # 6. 低成功率检查
        success_threshold = 0.5
        if metrics.success_rate < success_threshold:
            reasons.append(TripReason.EXCHANGE_CONNECTION_LOST)
            details["success_rate"] = metrics.success_rate
            details["threshold"] = success_threshold

        # 7. 总体数据质量得分检查
        overall_score = metrics.overall_score
        adjusted_threshold = self.trip_threshold * market_multiplier
        if overall_score < adjusted_threshold:
            reasons.append(TripReason.MULTIPLE_FAILURES)
            details["overall_score"] = overall_score
            details["threshold"] = adjusted_threshold

        # 8. 市场关闭检查（仅对股票和期货市场）
        if self.market_type in [MarketType.STOCK, MarketType.FUTURES]:
            if self._is_market_closed(metrics.timestamp):
                reasons.append(TripReason.MARKET_CLOSED)
                details["market_closed"] = True

        # 判断是否触发
        if not reasons:
            return False, None, {}

        # 如果有多个原因，使用MULTIPLE_FAILURES作为主要原因
        main_reason = TripReason.MULTIPLE_FAILURES if len(reasons) > 1 else reasons[0]

        return True, main_reason, details

    def _get_market_sensitivity_multiplier(self) -> float:
        """
        获取市场敏感度乘数

        Returns:
            敏感度乘数（值越小越敏感）
        """
        if self.market_type == MarketType.CRYPTO:
            return 0.8  # 加密货币市场更敏感
        if self.market_type == MarketType.FOREX:
            return 0.9  # 外汇市场中等敏感
        if self.market_type == MarketType.STOCK:
            return 1.2  # 股票市场相对宽松
        if self.market_type == MarketType.FUTURES:
            return 1.1  # 期货市场中等宽松
        return 1.0

    def _is_market_closed(self, timestamp: datetime) -> bool:
        """
        检查市场是否关闭（简化实现）

        Args:
            timestamp: 时间戳

        Returns:
            是否关闭
        """
        # 简化实现：周末视为市场关闭
        if timestamp.weekday() >= 5:  # 5=周六，6=周日
            return True

        # 股票市场：美东时间9:30-16:00
        if self.market_type == MarketType.STOCK:
            hour = timestamp.hour
            # 简单判断：不在9-16点之间视为关闭
            if hour < 9 or hour >= 16:
                return True

        return False

    def _trip_breaker(self, reason: TripReason, details: dict[str, Any]) -> bool:
        """
        触发熔断

        Args:
            reason: 触发原因
            details: 触发详情

        Returns:
            True
        """
        # 如果已经处于熔断状态，不重复触发
        if self.status == CircuitBreakerStatus.TRIPPED:
            return False

        self.status = CircuitBreakerStatus.TRIPPED
        self.trip_time = datetime.now()
        self.trip_reason = reason
        self.trip_details = details

        # 记录事件
        event = CircuitBreakerEvent(
            event_id=f"trip_{len(self.event_history) + 1:04d}",
            timestamp=self.trip_time,
            status=self.status,
            reason=reason,
            details=details,
        )
        self.event_history.append(event)


        return True

    def _check_recovery(self, metrics: DataQualityMetrics) -> bool:
        """
        检查是否可以恢复

        Args:
            metrics: 当前数据质量指标

        Returns:
            是否已恢复（True=已恢复，False=仍处于熔断状态）
        """
        if self.trip_time is None:
            return False

        current_time = datetime.now()
        trip_duration = (current_time - self.trip_time).total_seconds()

        # 检查最小恢复时间
        if trip_duration < self.min_recovery_time:
            return False

        # 检查最大熔断持续时间
        if trip_duration > self.max_trip_duration:
            return self._recover_breaker(
                TripReason.MULTIPLE_FAILURES, {"forced_recovery": True}
            )

        # 检查数据质量是否达标
        overall_score = metrics.overall_score
        if overall_score >= self.recovery_threshold:
            # 还需要检查最近几次数据质量是否稳定
            recent_scores = [
                m.overall_score
                for m in self.quality_history[-5:]
                if hasattr(m, "overall_score")
            ]
            if len(recent_scores) >= 3:
                avg_recent_score = np.mean(recent_scores)
                if avg_recent_score >= self.recovery_threshold:
                    assert self.trip_reason is not None
                    return self._recover_breaker(
                        self.trip_reason, {"recovery_score": overall_score}
                    )

        return False

    def check_progressive_recovery(self, metrics: DataQualityMetrics) -> bool:
        """
        检查渐进式恢复状态

        Args:
            metrics: 当前数据质量指标

        Returns:
            是否进入下一阶段或完全恢复
        """
        if self.status != CircuitBreakerStatus.RECOVERY:
            return False

        if self.progressive_recovery_start is None:
            return False

        current_time = datetime.now()
        recovery_duration = (
            current_time - self.progressive_recovery_start
        ).total_seconds()

        # 检查数据质量是否稳定
        recent_scores = [
            m.overall_score
            for m in self.quality_history[-10:]
            if hasattr(m, "overall_score")
        ]

        if len(recent_scores) >= 5:
            avg_score = np.mean(recent_scores)
            score_std = np.std(recent_scores)

            # 第一阶段：限制性交易（至少30秒）
            if self.progressive_recovery_stage == 1:
                if recovery_duration >= 30 and avg_score >= 0.85 and score_std < 0.1:
                    # 进入第二阶段：完全恢复
                    self.status = CircuitBreakerStatus.NORMAL
                    self.progressive_recovery_stage = 0
                    self.progressive_recovery_start = None

                    event = CircuitBreakerEvent(
                        event_id=f"progressive_recovery_{len(self.event_history) + 1:04d}",
                        timestamp=current_time,
                        status=self.status,
                        reason=TripReason.MULTIPLE_FAILURES,
                        details={
                            "progressive_recovery": True,
                            "stage": "complete",
                            "avg_score": avg_score,
                            "duration": recovery_duration,
                        },
                    )
                    self.event_history.append(event)

                    return True

        return False

    def _recover_breaker(self, reason: TripReason, details: dict[str, Any]) -> bool:
        """
        恢复熔断

        Args:
            reason: 恢复原因（通常与触发原因相同）
            details: 恢复详情

        Returns:
            True
        """
        if self.enable_progressive_recovery and self.progressive_recovery_stage == 0:
            # 进入渐进式恢复第一阶段：限制性交易
            self.status = CircuitBreakerStatus.RECOVERY
            self.progressive_recovery_stage = 1
            self.progressive_recovery_start = datetime.now()
            recovery_type = "渐进式恢复第一阶段"
        else:
            # 直接完全恢复
            self.status = CircuitBreakerStatus.NORMAL
            self.progressive_recovery_stage = 0
            self.progressive_recovery_start = None
            recovery_type = "完全恢复"

        recovery_time = datetime.now()
        trip_duration = None
        if self.trip_time:
            trip_duration = recovery_time - self.trip_time

        # 记录恢复事件
        event = CircuitBreakerEvent(
            event_id=f"recovery_{len(self.event_history) + 1:04d}",
            timestamp=recovery_time,
            status=self.status,
            reason=reason,
            details={**details, "recovery_type": recovery_type},
            duration=trip_duration,
            recovery_time=recovery_time,
        )
        self.event_history.append(event)


        # 重置熔断时间
        self.trip_time = None
        self.trip_reason = None
        self.trip_details = {}

        return True

    def manual_trip(self, reason: str = "手动触发") -> bool:
        """
        手动触发熔断

        Args:
            reason: 手动触发原因

        Returns:
            是否成功触发
        """
        if self.status == CircuitBreakerStatus.TRIPPED:
            return False

        return self._trip_breaker(TripReason.MANUAL_TRIP, {"manual_reason": reason})

    def manual_recover(self) -> bool:
        """
        手动恢复熔断

        Returns:
            是否成功恢复
        """
        if self.status not in [
            CircuitBreakerStatus.TRIPPED,
            CircuitBreakerStatus.RECOVERY,
        ]:
            return False

        return self._recover_breaker(TripReason.MANUAL_TRIP, {"manual_recovery": True})

    def emergency_override(self, enable: bool = True, reason: str = "紧急情况") -> bool:
        """
        紧急手动覆盖（绕过所有保护）

        Args:
            enable: True=启用紧急覆盖，False=禁用
            reason: 紧急原因

        Returns:
            是否成功
        """
        if enable:
            old_status = self.status
            self.status = CircuitBreakerStatus.MANUAL_OVERRIDE
            self._manual_override_flag = True

            event = CircuitBreakerEvent(
                event_id=f"emergency_{len(self.event_history) + 1:04d}",
                timestamp=datetime.now(),
                status=self.status,
                reason=TripReason.MANUAL_TRIP,
                details={
                    "emergency_override": True,
                    "reason": reason,
                    "old_status": old_status.value,
                },
            )
            self.event_history.append(event)

            return True
        self.manual_override(False)
        return True

    def manual_override(self, enable: bool = True) -> None:
        """
        手动覆盖熔断器

        Args:
            enable: True=启用手动覆盖，False=禁用
        """
        self._manual_override_flag = enable
        if enable:
            self.status = CircuitBreakerStatus.MANUAL_OVERRIDE
        else:
            self.status = CircuitBreakerStatus.NORMAL

    def get_status_report(self) -> dict[str, Any]:
        """
        获取熔断器状态报告

        Returns:
            状态报告字典
        """
        current_time = datetime.now()

        report = {
            "status": self.status.value,
            "trip_time": self.trip_time.isoformat() if self.trip_time else None,
            "trip_reason": self.trip_reason.value if self.trip_reason else None,
            "trip_details": self.trip_details,
            "manual_override": self._manual_override_flag,
            "event_count": len(self.event_history),
            "monitored_symbols": list(self.monitored_symbols),
            "monitored_exchanges": list(self.monitored_exchanges),
        }

        # 计算熔断持续时间
        if self.trip_time:
            trip_duration = (current_time - self.trip_time).total_seconds()
            report["trip_duration_seconds"] = trip_duration
            report["estimated_recovery_time"] = (
                self.trip_time + timedelta(seconds=self.min_recovery_time)
            ).isoformat()

        # 添加最近的数据质量评分
        if self.quality_history:
            recent_metrics = self.quality_history[-1]
            report["recent_data_quality"] = {
                "overall_score": recent_metrics.overall_score,
                "data_freshness": recent_metrics.data_freshness_seconds,
                "price_change": recent_metrics.price_change_pct,
                "latency": recent_metrics.latency_ms,
                "success_rate": recent_metrics.success_rate,
            }

        return report

    def is_trading_allowed(self) -> bool:
        """
        检查是否允许交易

        Returns:
            True=允许交易，False=停止交易
        """
        if self.status == CircuitBreakerStatus.MANUAL_OVERRIDE:
            return True

        if self.status == CircuitBreakerStatus.RECOVERY:
            # 恢复状态：限制性交易（例如只允许平仓，不允许开新仓）
            return True

        return self.status == CircuitBreakerStatus.NORMAL

    def should_trip(self, context: str = "general") -> bool:
        """
        检查熔断器是否应该触发（是否处于熔断状态）

        Args:
            context: 检查上下文（用于日志记录）

        Returns:
            True=熔断已触发，False=正常状态
        """
        # 如果处于手动覆盖状态，永不触发
        if self.status == CircuitBreakerStatus.MANUAL_OVERRIDE:
            return False

        return self.status == CircuitBreakerStatus.TRIPPED

    def clear_history(self, keep_last_n: int = 10) -> None:
        """
        清空历史记录（保留最近N条）

        Args:
            keep_last_n: 保留最近N条记录
        """
        if len(self.event_history) > keep_last_n:
            self.event_history = self.event_history[-keep_last_n:]

        if len(self.quality_history) > keep_last_n:
            self.quality_history = self.quality_history[-keep_last_n:]


# 使用示例
if __name__ == "__main__":
    # 创建熔断器实例
    breaker = CircuitBreaker(
        trip_threshold=0.3,
        recovery_threshold=0.8,
        min_recovery_time=30,
        max_trip_duration=180,
    )


    # 测试1：正常数据质量
    normal_metrics = DataQualityMetrics(
        timestamp=datetime.now(),
        symbol="BTC/USDT",
        exchange="binance",
        data_freshness_seconds=2.5,
        missing_data_points=0,
        consecutive_missing=0,
        price_change_pct=0.01,
        volume_change_pct=0.5,
        spread_pct=0.02,
        latency_ms=150,
        success_rate=0.99,
        error_count=0,
    )

    tripped = breaker.update_data_quality(normal_metrics)

    # 测试2：数据流中断
    bad_metrics = DataQualityMetrics(
        timestamp=datetime.now(),
        symbol="BTC/USDT",
        exchange="binance",
        data_freshness_seconds=45.0,  # 45秒无数据
        missing_data_points=3,
        consecutive_missing=3,
        price_change_pct=0.25,  # 25%价格波动
        volume_change_pct=6.0,  # 6倍成交量
        spread_pct=0.05,
        latency_ms=2500,  # 2.5秒延迟
        success_rate=0.3,  # 30%成功率
        error_count=5,
    )

    tripped = breaker.update_data_quality(bad_metrics)

    # 测试3：手动恢复
    if breaker.status == CircuitBreakerStatus.TRIPPED:
        recovered = breaker.manual_recover()


    # 获取状态报告
    report = breaker.get_status_report()
    for key, value in report.items():
        if key not in ["trip_details", "recent_data_quality"]:
            pass
