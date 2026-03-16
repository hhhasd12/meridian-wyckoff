"""
兼容层 shim — 向后兼容重导出

数据清洗器已迁移至 src/plugins/data_pipeline/data_sanitizer.py
此文件仅保留向后兼容的导入路径，新代码请直接使用：
    from src.plugins.data_pipeline.data_sanitizer import ...
"""

import warnings as _warnings

_warnings.warn(
    "src.core.data_sanitizer 已废弃，"
    "请改用 src.plugins.data_pipeline.data_sanitizer",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.data_pipeline.data_sanitizer import (  # noqa: F401, E402
    AnomalyEvent,
    AnomalySeverity,
    DataSanitizer,
    DataSanitizerConfig,
    HistoricalContext,
    MarketType,
    RawCandle,
)

__all__ = [
    "MarketType",
    "AnomalySeverity",
    "RawCandle",
    "AnomalyEvent",
    "HistoricalContext",
    "DataSanitizerConfig",
    "DataSanitizer",
]
