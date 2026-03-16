"""兼容层 shim — 向后兼容重导出（已废弃）

业务逻辑已迁移至 src.plugins.signal_validation.micro_entry_validator
"""
import warnings as _warnings

_warnings.warn(
    "src.core.micro_entry_validator 已废弃，请改用 src.plugins.signal_validation.micro_entry_validator",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.signal_validation.micro_entry_validator import (  # noqa: E402, F401
    EntrySignalType,
    MicroEntryValidator,
    StructureType,
)

__all__ = ["EntrySignalType", "MicroEntryValidator", "StructureType"]
