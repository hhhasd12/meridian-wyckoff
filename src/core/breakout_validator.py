"""兼容层 shim — 向后兼容重导出（已废弃）

业务逻辑已迁移至 src.plugins.signal_validation.breakout_validator
"""
import warnings as _warnings

_warnings.warn(
    "src.core.breakout_validator 已废弃，请改用 src.plugins.signal_validation.breakout_validator",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.signal_validation.breakout_validator import (  # noqa: E402, F401
    BreakoutStatus,
    BreakoutValidator,
)

__all__ = ["BreakoutStatus", "BreakoutValidator"]
