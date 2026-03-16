"""兼容层 shim — 向后兼容重导出（已废弃）

业务逻辑已迁移至 src.plugins.data_pipeline.data_pipeline
"""
import warnings as _warnings

_warnings.warn(
    "src.core.data_pipeline 已废弃，请改用 src.plugins.data_pipeline.data_pipeline",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.data_pipeline.data_pipeline import (  # noqa: E402, F401
    DataPipeline,
    DataRequest,
    DataSource,
    Timeframe,
)

__all__ = ["DataPipeline", "DataRequest", "DataSource", "Timeframe"]
