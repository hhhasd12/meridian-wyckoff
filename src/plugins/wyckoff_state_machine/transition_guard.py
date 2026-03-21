"""转换守卫 — 只允许合法的父→子状态转换

设计原则：
1. VALID_TRANSITIONS 是硬编码的白名单，不可配置、不可进化
2. is_valid_transition() 是硬约束，不通过就不转换
3. check_prerequisite_evidence() 检查前置证据是否充足

从 system-architecture-v3.md §4.3 实现。
"""

import logging
from typing import Callable, Dict, List, Set

from src.kernel.types import StateEvidence

logger = logging.getLogger(__name__)


class TransitionGuard:
    """转换守卫 — 只允许合法的父→子转换"""

    # 合法转换表：from_state → Set[to_state]
    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        # 入口
        "IDLE": {"PS", "SC", "PSY", "BC"},
        # 吸筹阶段
        "PS": {"SC", "AR"},
        "SC": {"AR", "ST", "TEST"},
        "AR": {"ST", "TEST", "UTA"},
        "ST": {"TEST", "SPRING", "SO", "LPS"},
        "TEST": {"LPS", "mSOS", "SPRING", "SO"},
        "UTA": {"TEST", "LPS"},
        "SPRING": {"LPS", "mSOS", "TEST"},  # Spring后可回TEST(失败)
        "SO": {"LPS", "mSOS", "TEST"},
        "LPS": {"mSOS", "MSOS"},
        "mSOS": {"MSOS", "JOC"},
        "MSOS": {"JOC", "BU"},
        "JOC": {"BU"},
        "BU": {"UPTREND"},
        # 派发阶段
        "PSY": {"BC", "AR_DIST"},
        "BC": {"AR_DIST", "ST_DIST", "UT"},
        "AR_DIST": {"ST_DIST", "UT", "UTAD"},
        "ST_DIST": {"UT", "UTAD", "LPSY"},
        "UT": {"UTAD", "LPSY"},
        "UTAD": {"LPSY"},
        "LPSY": {"mSOW", "MSOW"},
        "mSOW": {"MSOW"},
        "MSOW": {"DOWNTREND"},
        # 趋势 → 再积累/再派发
        "UPTREND": {"RE_ACCUMULATION", "PSY"},
        "DOWNTREND": {"RE_DISTRIBUTION", "PS", "SC"},
        # 再积累/再派发 → 恢复趋势或反转
        "RE_ACCUMULATION": {"UPTREND", "PSY"},  # 继续上涨 或 转派发
        "RE_DISTRIBUTION": {"DOWNTREND", "PS"},  # 继续下跌 或 转吸筹
    }

    @staticmethod
    def is_valid_transition(from_state: str, to_state: str) -> bool:
        """检查状态转换是否合法

        Args:
            from_state: 当前状态
            to_state: 目标状态

        Returns:
            转换是否在白名单中
        """
        valid = TransitionGuard.VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid

    @staticmethod
    def get_valid_targets(from_state: str) -> Set[str]:
        """获取从当前状态可以转换到的所有合法目标

        Args:
            from_state: 当前状态

        Returns:
            合法目标状态集合
        """
        return TransitionGuard.VALID_TRANSITIONS.get(from_state, set())

    @staticmethod
    def check_prerequisite_evidence(
        to_state: str,
        evidence_chain: List[StateEvidence],
        critical_levels: Dict[str, float],
    ) -> bool:
        """检查前置证据是否充足

        例如：进入AR前必须有SC_LOW被记录。
        这确保状态机不会跳过关键步骤。

        Args:
            to_state: 目标状态
            evidence_chain: 当前证据链
            critical_levels: 关键价格水平字典

        Returns:
            前置证据是否充足
        """
        prerequisites: Dict[str, Callable[[], bool]] = {
            "AR": lambda: "SC_LOW" in critical_levels,
            "ST": lambda: "SC_LOW" in critical_levels,
            "SPRING": lambda: "SC_LOW" in critical_levels,
            "mSOS": lambda: any(
                e.evidence_type == "support_strength" for e in evidence_chain
            ),
            "JOC": lambda: "AR_HIGH" in critical_levels or "CREEK" in critical_levels,
            "AR_DIST": lambda: "BC_HIGH" in critical_levels,
            "UT": lambda: "BC_HIGH" in critical_levels,
            "UTAD": lambda: "BC_HIGH" in critical_levels,
        }

        check = prerequisites.get(to_state)
        if check is None:
            return True  # 无前置要求
        return check()
