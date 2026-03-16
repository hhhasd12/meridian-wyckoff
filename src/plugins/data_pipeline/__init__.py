"""数据管道插件包

提供多数据源 OHLCV 数据获取、缓存、验证功能。
"""

from src.plugins.data_pipeline.plugin import DataPipelinePlugin

__all__ = ["DataPipelinePlugin"]
