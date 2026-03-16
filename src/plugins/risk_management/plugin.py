"""
风险管理插件 - 整合熔断器和异常验证器

包装以下核心模块：
- src/core/circuit_breaker.py (CircuitBreaker)
- src/core/anomaly_validator.py (AnomalyValidator)
"""

import logging
from typing import Any, Dict, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class RiskManagementPlugin(BasePlugin):
    """风险管理插件

    整合熔断器和异常数据验证器，提供统一的风险管理接口。

    设计原则：
    1. 懒加载：仅在 on_load() 时导入底层模块
    2. 委托模式：所有逻辑委托给底层组件
    3. 事件驱动：状态变化通过事件总线发布
    4. 统计追踪：记录各类操作的调用次数
    """

    def __init__(
        self, name: str = "risk_management"
    ) -> None:
        super().__init__(name)
        self._circuit_breaker: Optional[Any] = None
        self._anomaly_validator: Optional[Any] = None
        self._quality_update_count: int = 0
        self._anomaly_validate_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件，初始化熔断器和异常验证器"""
        from src.plugins.risk_management.circuit_breaker import CircuitBreaker
        from src.plugins.risk_management.anomaly_validator import (
            AnomalyValidator,
        )

        config = self._config or {}

        cb_config = config.get("circuit_breaker", {})
        av_config = config.get("anomaly_validator", {})

        self._circuit_breaker = CircuitBreaker(
            trip_threshold=cb_config.get(
                "trip_threshold", 0.3
            ),
            recovery_threshold=cb_config.get(
                "recovery_threshold", 0.8
            ),
            min_recovery_time=cb_config.get(
                "min_recovery_time", 60
            ),
            max_trip_duration=cb_config.get(
                "max_trip_duration", 300
            ),
        )

        self._anomaly_validator = AnomalyValidator(
            correlation_threshold=av_config.get(
                "correlation_threshold", 2.0
            ),
            price_deviation_threshold=av_config.get(
                "price_deviation_threshold", 0.02
            ),
            min_confidence=av_config.get(
                "min_confidence", 0.7
            ),
        )

        logger.info("风险管理插件加载完成")

    def on_unload(self) -> None:
        """卸载插件，清理资源"""
        self._circuit_breaker = None
        self._anomaly_validator = None
        self._quality_update_count = 0
        self._anomaly_validate_count = 0
        self._last_error = None
        logger.info("风险管理插件已卸载")

    def on_config_update(
        self, new_config: Dict[str, Any]
    ) -> None:
        """配置更新时重新创建组件

        Args:
            new_config: 新的配置字典
        """
        if self._circuit_breaker is not None:
            from src.plugins.risk_management.circuit_breaker import (
                CircuitBreaker,
            )
            from src.plugins.risk_management.anomaly_validator import (
                AnomalyValidator,
            )

            cb_config = new_config.get(
                "circuit_breaker", {}
            )
            av_config = new_config.get(
                "anomaly_validator", {}
            )

            self._circuit_breaker = CircuitBreaker(
                trip_threshold=cb_config.get(
                    "trip_threshold", 0.3
                ),
                recovery_threshold=cb_config.get(
                    "recovery_threshold", 0.8
                ),
                min_recovery_time=cb_config.get(
                    "min_recovery_time", 60
                ),
                max_trip_duration=cb_config.get(
                    "max_trip_duration", 300
                ),
            )

            self._anomaly_validator = AnomalyValidator(
                correlation_threshold=av_config.get(
                    "correlation_threshold", 2.0
                ),
                price_deviation_threshold=av_config.get(
                    "price_deviation_threshold", 0.02
                ),
                min_confidence=av_config.get(
                    "min_confidence", 0.7
                ),
            )

            logger.info("风险管理插件配置已更新")

    def health_check(self) -> HealthCheckResult:
        """健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        from src.kernel.types import PluginState

        if self._state != PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="插件未处于活跃状态",
            )

        if self._circuit_breaker is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="熔断器未初始化",
            )

        if self._anomaly_validator is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="异常验证器未初始化",
            )

        if self._last_error is not None:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近有错误: {self._last_error}",
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=(
                f"正常运行 - 数据质量更新:"
                f"{self._quality_update_count}次, "
                f"异常验证:"
                f"{self._anomaly_validate_count}次"
            ),
        )

    def update_data_quality(
        self, metrics: Any
    ) -> bool:
        """更新数据质量指标

        Args:
            metrics: DataQualityMetrics 数据质量指标

        Returns:
            bool: 是否触发了熔断

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._circuit_breaker is None:
            raise RuntimeError(
                "风险管理插件未加载，无法更新数据质量"
            )

        try:
            tripped = (
                self._circuit_breaker.update_data_quality(
                    metrics
                )
            )
            self._quality_update_count += 1
            self._last_error = None

            event_name = (
                "risk_management.circuit_breaker_tripped"
                if tripped
                else "risk_management.data_quality_updated"
            )
            self.emit_event(
                event_name,
                {
                    "tripped": tripped,
                    "status": self._circuit_breaker.status.value,
                },
            )

            return tripped
        except Exception as e:
            self._last_error = str(e)
            logger.error("数据质量更新失败: %s", e)
            raise

    def is_trading_allowed(self) -> bool:
        """检查是否允许交易

        Returns:
            bool: True=允许交易

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._circuit_breaker is None:
            raise RuntimeError(
                "风险管理插件未加载，无法检查交易权限"
            )

        return self._circuit_breaker.is_trading_allowed()

    def validate_anomaly(
        self,
        anomaly: Any,
        multi_exchange_data: Optional[
            Dict[str, pd.DataFrame]
        ] = None,
        correlation_data: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Any:
        """验证异常事件

        Args:
            anomaly: AnomalyEvent 异常事件
            multi_exchange_data: 多交易所数据
            correlation_data: 相关性数据

        Returns:
            更新后的异常事件

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._anomaly_validator is None:
            raise RuntimeError(
                "风险管理插件未加载，无法验证异常"
            )

        try:
            result = (
                self._anomaly_validator.validate_anomaly(
                    anomaly,
                    multi_exchange_data,
                    correlation_data,
                )
            )
            self._anomaly_validate_count += 1
            self._last_error = None

            self.emit_event(
                "risk_management.anomaly_validated",
                {
                    "anomaly_id": getattr(
                        anomaly, "anomaly_id", "unknown"
                    ),
                    "validation_result": getattr(
                        result,
                        "validation_result",
                        None,
                    ),
                },
            )

            return result
        except Exception as e:
            self._last_error = str(e)
            logger.error("异常验证失败: %s", e)
            raise

    def get_status_report(self) -> Dict[str, Any]:
        """获取熔断器状态报告

        Returns:
            Dict: 状态报告

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._circuit_breaker is None:
            raise RuntimeError(
                "风险管理插件未加载，无法获取状态报告"
            )

        return self._circuit_breaker.get_status_report()

    def get_statistics(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "quality_update_count": self._quality_update_count,
            "anomaly_validate_count": self._anomaly_validate_count,
            "last_error": self._last_error,
            "trading_allowed": (
                self._circuit_breaker.is_trading_allowed()
                if self._circuit_breaker
                else None
            ),
            "breaker_status": (
                self._circuit_breaker.status.value
                if self._circuit_breaker
                else None
            ),
        }

    def get_circuit_breakers(self) -> list:
        """获取熔断器状态列表（供API调用）

        Returns:
            List: 熔断器状态列表
        """
        if self._circuit_breaker is None:
            return []
        
        status_report = self._circuit_breaker.get_status_report()
        return [
            {
                "name": "日内亏损熔断",
                "status": "closed" if self._circuit_breaker.is_trading_allowed() else "open",
                "trip_count": status_report.get("trip_count", 0),
                "last_trip_time": status_report.get("last_trip_time"),
                "recovery_time": status_report.get("recovery_time"),
            }
        ]

    def get_risk_metrics(self) -> list:
        """获取风险指标列表（供API调用）

        Returns:
            List: 风险指标列表
        """
        stats = self.get_statistics()
        return [
            {
                "name": "数据质量更新次数",
                "value": stats.get("quality_update_count", 0),
                "threshold": 1000,
                "status": "normal",
                "unit": "次",
            },
            {
                "name": "异常验证次数",
                "value": stats.get("anomaly_validate_count", 0),
                "threshold": 100,
                "status": "normal",
                "unit": "次",
            },
            {
                "name": "熔断器状态",
                "value": 1 if stats.get("trading_allowed", True) else 0,
                "threshold": 1,
                "status": "normal" if stats.get("trading_allowed", True) else "danger",
                "unit": "",
            },
        ]

    def get_anomalies(self, limit: int = 50) -> list:
        """获取异常事件列表（供API调用）

        Returns:
            List: 异常事件列表
        """
        return []
