"""
兼容层 shim — 向后兼容重导出

自我纠错工作流已迁移至 src/plugins/self_correction/workflow.py
此文件仅保留向后兼容的导入路径，新代码请直接使用：
    from src.plugins.self_correction.workflow import ...
"""

import warnings as _warnings

_warnings.warn(
    "src.core.self_correction_workflow 已废弃，"
    "请改用 src.plugins.self_correction.workflow",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.self_correction.workflow import (  # noqa: F401, E402
    CorrectionResult,
    CorrectionStage,
    SelfCorrectionWorkflow,
)

__all__ = [
    "CorrectionStage",
    "CorrectionResult",
    "SelfCorrectionWorkflow",
]
