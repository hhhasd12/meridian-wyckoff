"""兼容层 shim — 向后兼容重导出（已废弃）

业务逻辑已迁移至 src.plugins.pattern_detection.curve_boundary
"""
import warnings as _warnings

_warnings.warn(
    "src.core.curve_boundary 已废弃，请改用 src.plugins.pattern_detection.curve_boundary",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.pattern_detection.curve_boundary import (  # noqa: E402, F401
    BoundaryType,
    CurveBoundaryFitter,
    GeometricAnalyzer,
)

__all__ = ["BoundaryType", "CurveBoundaryFitter", "GeometricAnalyzer"]
