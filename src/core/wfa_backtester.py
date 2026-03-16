"""
兼容层 shim — 向后兼容重导出

WFA 回测器已迁移至 src/plugins/evolution/wfa_backtester.py
此文件仅保留向后兼容的导入路径，新代码请直接使用：
    from src.plugins.evolution.wfa_backtester import ...
"""

import warnings as _warnings

_warnings.warn(
    "src.core.wfa_backtester 已废弃，"
    "请改用 src.plugins.evolution.wfa_backtester",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.evolution.wfa_backtester import (  # noqa: F401, E402
    PerformanceMetric,
    ValidationResult,
    WFABacktester,
)

__all__ = [
    "PerformanceMetric",
    "ValidationResult",
    "WFABacktester",
]
