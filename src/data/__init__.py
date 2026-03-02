"""
数据模块包

提供数据加载、清洗和特征计算功能。

模块结构：
- loader.py: 数据加载 (CSV/Excel/Parquet/JSON)
- cleaner.py: 数据清洗 (解决NumPy警告)
- feature_factory.py: 特征计算 (VWAP/RSI/MACD等)

导出：
- DataLoader: 本地数据加载器
- MarketDataLoader: 市场数据加载器
- DataCleaner: 数据清洗器
- FeatureFactory: 特征工厂
- 所有安全计算函数
"""

from .cleaner import DataCleaner, safe_divide, safe_mean, sanitize_dataframe
from .feature_factory import (
    FeatureFactory,
    calculate_atr,
    calculate_rsi,
    calculate_vwap,
)
from .loader import DataLoader, MarketDataLoader

__all__ = [
    # Loaders
    "DataLoader",
    "MarketDataLoader",
    # Cleaner
    "DataCleaner",
    "sanitize_dataframe",
    "safe_divide",
    "safe_mean",
    # Feature Factory
    "FeatureFactory",
    "calculate_vwap",
    "calculate_atr",
    "calculate_rsi",
]
