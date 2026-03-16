"""
兼容层 shim — 向后兼容重导出

业务逻辑已迁移至 src/plugins/weight_system/period_weight_filter.py
"""
import warnings as _warnings

_warnings.warn(
    "src.core.period_weight_filter 已废弃，请改用 src.plugins.weight_system.period_weight_filter",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.weight_system.period_weight_filter import (  # noqa: F401, E402
    Timeframe,
    PeriodWeightFilter,
)

__all__ = ["Timeframe", "PeriodWeightFilter"]
