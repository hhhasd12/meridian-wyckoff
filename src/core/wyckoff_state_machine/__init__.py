"""
威科夫状态机包

包含威科夫理论的状态机实现，支持13个吸筹节点和9个派发节点的辩证状态转换。

模块结构：
- state_definitions.py: 枚举和数据类定义
- core.py: 核心状态机类 (WyckoffStateMachine)
- enhanced.py: 增强状态机类 (EnhancedWyckoffStateMachine)
- evidence_chain.py: 证据链管理器 (EvidenceChainManager)

导出类：
- WyckoffStateMachine: 核心威科夫状态机
- EnhancedWyckoffStateMachine: 增强版状态机
- EvidenceChainManager: 证据链管理器
- StateDirection: 状态方向枚举
- StateTransitionType: 状态转换类型枚举
- StateEvidence: 状态证据数据类
- StateDetectionResult: 状态检测结果数据类
- StateTransition: 状态转换记录数据类
- StatePath: 并行状态路径数据类
- StateConfig: 状态机配置类
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 数据类型从 kernel 导入（权威来源）
from src.kernel.types import (
    StateConfig,
    StateDetectionResult,
    StateDirection,
    StateEvidence,
    StatePath,
    StateTransition,
    StateTransitionType,
)

# 大类仍从 legacy 导入
from ..wyckoff_state_machine_legacy import (
    EnhancedWyckoffStateMachine,
    EvidenceChainManager,
    WyckoffStateMachine,
)

__all__ = [
    "EnhancedWyckoffStateMachine",
    "EvidenceChainManager",
    "StateConfig",
    "StateDetectionResult",
    "StateDirection",
    "StateEvidence",
    "StatePath",
    "StateTransition",
    "StateTransitionType",
    "WyckoffStateMachine",
]
