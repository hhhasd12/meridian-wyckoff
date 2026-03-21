"""
威科夫状态机模块 - 兼容层 (Shim)

.. deprecated::
    此文件为兼容层，实际实现已拆分到以下模块：
    - state_machine_core.py: StateMachineCore 基类 + WyckoffStateMachine 组合类
    - accumulation_detectors.py: AccumulationDetectorMixin (吸筹检测方法)
    - distribution_detectors.py: DistributionDetectorMixin (派发检测方法)
    - enhanced_state_machine.py: EnhancedWyckoffStateMachine
    - evidence_chain.py: EvidenceChainManager

    新代码请直接从拆分后的模块导入。
    此文件保留仅为向后兼容，所有现有导入路径继续有效。
"""

# Re-export all public classes for backward compatibility
from src.plugins.wyckoff_state_machine.state_machine_core import (  # noqa: F401
    StateMachineCore,
    WyckoffStateMachine,
)
from src.plugins.wyckoff_state_machine.enhanced_state_machine import (  # noqa: F401
    EnhancedWyckoffStateMachine,
)
from src.plugins.wyckoff_state_machine.accumulation_detectors import (  # noqa: F401
    AccumulationDetectorMixin,
)
from src.plugins.wyckoff_state_machine.distribution_detectors import (  # noqa: F401
    DistributionDetectorMixin,
)

__all__ = [
    "WyckoffStateMachine",
    "EnhancedWyckoffStateMachine",
    "StateMachineCore",
    "AccumulationDetectorMixin",
    "DistributionDetectorMixin",
]
