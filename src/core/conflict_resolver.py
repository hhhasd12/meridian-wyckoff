"""兼容层 shim — 向后兼容重导出（已废弃）

业务逻辑已迁移至 src.plugins.signal_validation.conflict_resolver
"""
import warnings as _warnings

_warnings.warn(
    "src.core.conflict_resolver 已废弃，请改用 src.plugins.signal_validation.conflict_resolver",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.signal_validation.conflict_resolver import (  # noqa: E402, F401
    ConflictResolutionManager,
    ConflictType,
    ResolutionBias,
)

__all__ = ["ConflictResolutionManager", "ConflictType", "ResolutionBias"]
