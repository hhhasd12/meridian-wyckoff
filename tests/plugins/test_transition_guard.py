"""转换守卫单元测试

测试 TransitionGuard 的合法转换白名单和前置证据检查逻辑。
"""

import pytest
from typing import Dict, List, Set

from src.plugins.wyckoff_state_machine.transition_guard import TransitionGuard
from src.kernel.types import StateEvidence


# ============================================================
# 辅助工厂
# ============================================================


def _make_evidence(evidence_type: str, value: float = 1.0) -> StateEvidence:
    """快速构建一条 StateEvidence"""
    return StateEvidence(
        evidence_type=evidence_type,
        value=value,
        confidence=0.8,
        weight=1.0,
        description=f"test evidence: {evidence_type}",
    )


# ============================================================
# TestValidTransitions — 白名单路径验证
# ============================================================


class TestValidTransitions:
    """合法转换白名单测试"""

    def test_idle_to_accumulation(self) -> None:
        """IDLE 可进入吸筹入口 PS / SC"""
        assert TransitionGuard.is_valid_transition("IDLE", "PS") is True
        assert TransitionGuard.is_valid_transition("IDLE", "SC") is True

    def test_idle_to_distribution(self) -> None:
        """IDLE 可进入派发入口 PSY / BC"""
        assert TransitionGuard.is_valid_transition("IDLE", "PSY") is True
        assert TransitionGuard.is_valid_transition("IDLE", "BC") is True

    def test_invalid_from_idle(self) -> None:
        """IDLE 不能跳到中间节点 SPRING / JOC"""
        assert TransitionGuard.is_valid_transition("IDLE", "SPRING") is False
        assert TransitionGuard.is_valid_transition("IDLE", "JOC") is False

    def test_accumulation_sequence(self) -> None:
        """吸筹全链路：PS→SC→AR→ST→SPRING→LPS→mSOS→MSOS→JOC→BU→UPTREND"""
        chain = [
            ("PS", "SC"),
            ("SC", "AR"),
            ("AR", "ST"),
            ("ST", "SPRING"),
            ("SPRING", "LPS"),
            ("LPS", "mSOS"),
            ("mSOS", "MSOS"),
            ("MSOS", "JOC"),
            ("JOC", "BU"),
            ("BU", "UPTREND"),
        ]
        for from_st, to_st in chain:
            assert TransitionGuard.is_valid_transition(from_st, to_st) is True, (
                f"{from_st}→{to_st} 应合法"
            )

    def test_distribution_sequence(self) -> None:
        """派发全链路：PSY→BC→AR_DIST→ST_DIST→UT→UTAD→LPSY→mSOW→MSOW→DOWNTREND"""
        chain = [
            ("PSY", "BC"),
            ("BC", "AR_DIST"),
            ("AR_DIST", "ST_DIST"),
            ("ST_DIST", "UT"),
            ("UT", "UTAD"),
            ("UTAD", "LPSY"),
            ("LPSY", "mSOW"),
            ("mSOW", "MSOW"),
            ("MSOW", "DOWNTREND"),
        ]
        for from_st, to_st in chain:
            assert TransitionGuard.is_valid_transition(from_st, to_st) is True, (
                f"{from_st}→{to_st} 应合法"
            )

    def test_spring_can_fail_back_to_test(self) -> None:
        """SPRING 失败后可回退到 TEST"""
        assert TransitionGuard.is_valid_transition("SPRING", "TEST") is True

    def test_cross_direction_invalid(self) -> None:
        """不能从吸筹节点跳到派发节点（SC→PSY）"""
        assert TransitionGuard.is_valid_transition("SC", "PSY") is False

    def test_trend_to_re_accumulation(self) -> None:
        """UPTREND → RE_ACCUMULATION 合法"""
        assert TransitionGuard.is_valid_transition("UPTREND", "RE_ACCUMULATION") is True

    def test_re_accumulation_exits(self) -> None:
        """RE_ACCUMULATION 可恢复上涨或反转进入派发"""
        assert TransitionGuard.is_valid_transition("RE_ACCUMULATION", "UPTREND") is True
        assert TransitionGuard.is_valid_transition("RE_ACCUMULATION", "PSY") is True

    def test_downtrend_to_re_distribution(self) -> None:
        """DOWNTREND → RE_DISTRIBUTION 合法"""
        assert (
            TransitionGuard.is_valid_transition("DOWNTREND", "RE_DISTRIBUTION") is True
        )

    def test_get_valid_targets(self) -> None:
        """get_valid_targets 返回正确的目标集合"""
        targets: Set[str] = TransitionGuard.get_valid_targets("IDLE")
        assert targets == {"PS", "SC", "PSY", "BC"}

        targets_spring: Set[str] = TransitionGuard.get_valid_targets("SPRING")
        assert "LPS" in targets_spring
        assert "mSOS" in targets_spring
        assert "TEST" in targets_spring

        # 不存在的状态返回空集
        assert TransitionGuard.get_valid_targets("NONEXISTENT") == set()


# ============================================================
# TestPrerequisiteEvidence — 前置证据检查
# ============================================================


class TestPrerequisiteEvidence:
    """前置证据充足性测试"""

    def test_ar_requires_sc_low(self) -> None:
        """AR 需要 critical_levels 中包含 SC_LOW"""
        critical: Dict[str, float] = {"SC_LOW": 95.0}
        result = TransitionGuard.check_prerequisite_evidence("AR", [], critical)
        assert result is True

    def test_ar_without_sc_low_fails(self) -> None:
        """AR 缺少 SC_LOW 时返回 False"""
        result = TransitionGuard.check_prerequisite_evidence("AR", [], {})
        assert result is False

    def test_spring_requires_sc_low(self) -> None:
        """SPRING 需要 SC_LOW"""
        assert (
            TransitionGuard.check_prerequisite_evidence("SPRING", [], {"SC_LOW": 90.0})
            is True
        )
        assert TransitionGuard.check_prerequisite_evidence("SPRING", [], {}) is False

    def test_ut_requires_bc_high(self) -> None:
        """UT 需要 BC_HIGH"""
        assert (
            TransitionGuard.check_prerequisite_evidence("UT", [], {"BC_HIGH": 110.0})
            is True
        )
        assert TransitionGuard.check_prerequisite_evidence("UT", [], {}) is False

    def test_joc_requires_ar_high_or_creek(self) -> None:
        """JOC 需要 AR_HIGH 或 CREEK"""
        # AR_HIGH 满足
        assert (
            TransitionGuard.check_prerequisite_evidence("JOC", [], {"AR_HIGH": 105.0})
            is True
        )
        # CREEK 满足
        assert (
            TransitionGuard.check_prerequisite_evidence("JOC", [], {"CREEK": 106.0})
            is True
        )
        # 两者都没有
        assert TransitionGuard.check_prerequisite_evidence("JOC", [], {}) is False

    def test_no_prerequisite_states(self) -> None:
        """PS, SC, PSY, BC 等无前置要求的状态永远返回 True"""
        no_prereq_states = ["PS", "SC", "PSY", "BC", "BU", "UPTREND", "DOWNTREND"]
        for state in no_prereq_states:
            assert TransitionGuard.check_prerequisite_evidence(state, [], {}) is True, (
                f"{state} 不应有前置要求"
            )

    def test_msos_requires_support_evidence(self) -> None:
        """mSOS 需要证据链中包含 support_strength 类型证据"""
        # 有 support_strength 证据
        chain_with: List[StateEvidence] = [
            _make_evidence("support_strength", 0.85),
        ]
        assert (
            TransitionGuard.check_prerequisite_evidence("mSOS", chain_with, {}) is True
        )

        # 无 support_strength 证据
        chain_without: List[StateEvidence] = [
            _make_evidence("volume_ratio", 1.5),
        ]
        assert (
            TransitionGuard.check_prerequisite_evidence("mSOS", chain_without, {})
            is False
        )

        # 空证据链
        assert TransitionGuard.check_prerequisite_evidence("mSOS", [], {}) is False
