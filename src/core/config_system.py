"""
兼容层 shim — 向后兼容重导出

业务配置类已迁移至 src/plugins/orchestrator/config_types.py
此文件仅保留向后兼容的导入路径，新代码请直接使用：
    from src.plugins.orchestrator.config_types import ...

注意：此文件与 src/kernel/config_system.py（YAML 配置系统）用途不同。
"""

import warnings as _warnings

_warnings.warn(
    "src.core.config_system 已废弃，请改用 src.plugins.orchestrator.config_types",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.orchestrator.config_types import (  # noqa: F401, E402
    DataSanitizerConfig,
    FVGConfig,
    MarketRegimeConfig,
    MarketType,
    PinBodyAnalyzerConfig,
    SystemOrchestratorConfig,
    TRConfig,
    WyckoffStateMachineConfig,
    create_default_config,
    load_config,
)

__all__ = [
    "MarketType",
    "TRConfig",
    "DataSanitizerConfig",
    "PinBodyAnalyzerConfig",
    "MarketRegimeConfig",
    "FVGConfig",
    "WyckoffStateMachineConfig",
    "SystemOrchestratorConfig",
    "create_default_config",
    "load_config",
]
