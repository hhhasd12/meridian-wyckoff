"""
兼容层 shim — 向后兼容重导出

错误记录簿已迁移至 src/plugins/self_correction/mistake_book.py
此文件仅保留向后兼容的导入路径，新代码请直接使用：
    from src.plugins.self_correction.mistake_book import ...
"""

import warnings as _warnings

_warnings.warn(
    "src.core.mistake_book 已废弃，"
    "请改用 src.plugins.self_correction.mistake_book",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.self_correction.mistake_book import (  # noqa: F401, E402
    ErrorPattern,
    ErrorSeverity,
    MistakeBook,
    MistakeRecord,
    MistakeType,
)

__all__ = [
    "MistakeType",
    "ErrorSeverity",
    "ErrorPattern",
    "MistakeRecord",
    "MistakeBook",
]
