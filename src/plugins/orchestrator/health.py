"""
系统协调器 - 健康检查模块

负责系统健康状态监控和性能监控。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 详细的中文错误上下文记录
3. 支持依赖注入
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _setup_error_handler():
    """设置错误处理装饰器"""
    try:
        from src.utils.error_handler import error_handler

        return error_handler
    except ImportError:

        def error_handler_decorator(**kwargs):
            def decorator(func):
                return func

            return decorator

        return error_handler_decorator


error_handler = _setup_error_handler()


class HealthStatus(str, Enum):
    """健康状态枚举"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AlertLevel(str, Enum):
    """告警级别枚举"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealthChecker:
    """
    健康检查器 - 监控系统各模块的健康状态
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        初始化健康检查器

        Args:
            config: 配置字典
        """
        self._config = config or {}
        self._health_records: dict[str, dict[str, Any]] = {}
        self._last_check_time: Optional[datetime] = None
        self._check_interval = self._config.get("check_interval_seconds", 60)

        logger.info("HealthChecker initialized")

    @error_handler(logger=logger, reraise=False)
    def record_health(
        self,
        module_name: str,
        status: HealthStatus,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        记录模块健康状态

        Args:
            module_name: 模块名称
            status: 健康状态
            details: 详细信息
        """
        self._health_records[module_name] = {
            "status": status,
            "details": details or {},
            "timestamp": datetime.now(),
        }
        logger.debug(f"Health recorded for {module_name}: {status}")

    @error_handler(logger=logger, reraise=False, default_return=HealthStatus.UNKNOWN)
    def get_health_status(self, module_name: str) -> HealthStatus:
        """
        获取模块的健康状态

        Args:
            module_name: 模块名称

        Returns:
            健康状态
        """
        if module_name not in self._health_records:
            return HealthStatus.UNKNOWN

        return self._health_records[module_name].get("status", HealthStatus.UNKNOWN)

    @error_handler(logger=logger, reraise=False, default_return={})
    def get_all_health_status(self) -> dict[str, Any]:
        """
        获取所有模块的健康状态

        Returns:
            所有模块的健康状态字典
        """
        return {
            name: record["status"].value
            for name, record in self._health_records.items()
        }

    @error_handler(logger=logger, reraise=False, default_return=HealthStatus.HEALTHY)
    def get_overall_health(self) -> HealthStatus:
        """
        获取系统整体健康状态

        Returns:
            系统整体健康状态
        """
        if not self._health_records:
            return HealthStatus.UNKNOWN

        statuses = [r["status"] for r in self._health_records.values()]

        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED for s in statuses) or any(s == HealthStatus.UNKNOWN for s in statuses):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    @error_handler(logger=logger, reraise=False)
    def check_module_staleness(
        self, module_name: str, max_age_seconds: int = 300
    ) -> bool:
        """
        检查模块健康记录是否过期

        Args:
            module_name: 模块名称
            max_age_seconds: 最大过期时间（秒）

        Returns:
            是否过期
        """
        if module_name not in self._health_records:
            return True

        record_time = self._health_records[module_name].get("timestamp")
        if record_time is None:
            return True

        age = (datetime.now() - record_time).total_seconds()
        return age > max_age_seconds

    @error_handler(logger=logger, reraise=False)
    def clear_health_record(self, module_name: str) -> None:
        """
        清除模块的健康记录

        Args:
            module_name: 模块名称
        """
        if module_name in self._health_records:
            del self._health_records[module_name]
            logger.debug(f"Health record cleared for {module_name}")

    @error_handler(logger=logger, reraise=False)
    def clear_all_records(self) -> None:
        """清除所有健康记录"""
        self._health_records.clear()
        logger.info("All health records cleared")


# 导出
__all__ = ["AlertLevel", "HealthChecker", "HealthStatus"]
