"""兼容层 shim — 向后兼容重导出（已废弃）

业务逻辑已迁移到 src/plugins/pattern_detection/tr_detector.py
"""
import warnings as _warnings

_warnings.warn(
    "src.core.tr_detector 已废弃，请改用 src.plugins.pattern_detection.tr_detector",
    DeprecationWarning,
    stacklevel=2,
)
from src.plugins.pattern_detection.tr_detector import (  # noqa: E402, F401
    BreakoutDirection,
    TradingRange,
    TRDetector,
    TRStatus,
)

__all__ = ["TRStatus", "BreakoutDirection", "TradingRange", "TRDetector"]
