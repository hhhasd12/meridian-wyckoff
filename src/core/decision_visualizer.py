"""
兼容层 shim — 向后兼容重导出

业务逻辑已迁移至 src/plugins/dashboard/decision_visualizer.py
"""
import warnings as _warnings

_warnings.warn(
    "src.core.decision_visualizer 已废弃，请改用 src.plugins.dashboard.decision_visualizer",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.dashboard.decision_visualizer import (  # noqa: F401, E402
    PlotStyle,
    DecisionVisualizer,
)

__all__ = ["PlotStyle", "DecisionVisualizer"]
