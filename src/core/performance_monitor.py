"""
兼容层 shim — 向后兼容重导出

业务逻辑已迁移至 src/plugins/dashboard/performance_monitor.py
"""
import warnings as _warnings

_warnings.warn(
    "src.core.performance_monitor 已废弃，请改用 src.plugins.dashboard.performance_monitor",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.dashboard.performance_monitor import (  # noqa: F401, E402
    HealthStatus,
    AlertLevel,
    ModuleType,
    PerformanceMonitor,
)

__all__ = ["HealthStatus", "AlertLevel", "ModuleType", "PerformanceMonitor"]
