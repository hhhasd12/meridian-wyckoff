"""
兼容层 shim — 向后兼容重导出

业务逻辑已迁移至 src/plugins/evolution/archivist.py
"""
import warnings as _warnings

_warnings.warn(
    "src.core.evolution_archivist 已废弃，请改用 src.plugins.evolution.archivist",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.evolution.archivist import (  # noqa: F401, E402
    EvolutionEventType,
    EvolutionLog,
    EmbeddingProvider,
    EvolutionArchivist,
)

__all__ = [
    "EvolutionEventType",
    "EvolutionLog",
    "EmbeddingProvider",
    "EvolutionArchivist",
]
