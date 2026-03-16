"""
兼容层 shim — 向后兼容重导出

威科夫Context构建器已迁移至 src/plugins/wyckoff_state_machine/context_builder.py
此文件仅保留向后兼容的导入路径，新代码请直接使用：
    from src.plugins.wyckoff_state_machine.context_builder import ...
"""

import warnings as _warnings

_warnings.warn(
    "src.core.wyckoff_context_builder 已废弃，"
    "请改用 src.plugins.wyckoff_state_machine.context_builder",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.wyckoff_state_machine.context_builder import (  # noqa: F401, E402
    KeyPriceLevels,
    KeyPriceTracker,
    TradingRange,
    TRDetector,
    TrendAnalyzer,
    TrendInfo,
    VolumeAnalyzer,
    VolumeProfile,
    WyckoffContextBuilder,
)

__all__ = [
    "TradingRange",
    "TrendInfo",
    "KeyPriceLevels",
    "VolumeProfile",
    "TRDetector",
    "TrendAnalyzer",
    "KeyPriceTracker",
    "VolumeAnalyzer",
    "WyckoffContextBuilder",
]
