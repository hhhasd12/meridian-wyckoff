"""市场体制检测插件包

提供 MarketRegime 枚举、RegimeDetector 检测器和 MarketRegimePlugin 插件类。

Usage:
    # 直接使用检测器（无需插件框架）
    from src.plugins.market_regime import MarketRegime, RegimeDetector

    # 作为插件使用（通过 PluginManager 加载）
    from src.plugins.market_regime import MarketRegimePlugin
"""

from src.plugins.market_regime.detector import (
    MarketRegime,
    RegimeDetector,
)
from src.plugins.market_regime.plugin import MarketRegimePlugin

__all__ = [
    "MarketRegime",
    "RegimeDetector",
    "MarketRegimePlugin",
]
