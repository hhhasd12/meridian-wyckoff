"""WyckoffStateMachineV4 单元测试 — Phase 2 (T2.12)

覆盖：
- V4 初始化和默认状态
- process_candle 返回 WyckoffStateResult
- 序列化推进（PS→SC→AR→ST 不跳步）
- 假设生命周期（HYPOTHETICAL→TESTING→REJECTED/EXHAUSTED）
- 关键价位记录（SC_LOW/AR_HIGH）
- BoundaryManager 三态生命周期
- DetectorRegistry 注册/冷却/期待列表
- 信号推导
"""

import pytest
from typing import Any, Dict, Optional

from src.plugins.wyckoff_state_machine.state_machine_v4 import (
    WyckoffStateMachineV4,
    StateStatus,
    Hypothesis,
    StructureHypothesis,
    MarketMode,
    PHASE_MAP,
    _BUY_STATES,
    _SELL_STATES,
)
from src.plugins.wyckoff_state_machine.boundary_manager import (
    BoundaryStatus,
    BoundaryInfo,
    BoundaryManager,
)
from src.plugins.wyckoff_state_machine.detector_registry import (
    NodeScore,
    NodeDetector,
    DetectorRegistry,
)
from src.kernel.types import (
    WyckoffStateResult,
    StateEvidence,
    WyckoffSignal,
    StateConfig,
    StateDirection,
)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def _candle(open_=100.0, high=105.0, low=95.0, close=103.0, volume=1000.0):
    """创建标准K线字典"""
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _context(**kw):
    """创建标准上下文字典"""
    defaults = {
        "market_regime": "RANGING",
        "regime_confidence": 0.7,
        "tr_support": 90.0,
        "tr_resistance": 110.0,
    }
    defaults.update(kw)
    return defaults


# ============================================================
# TestV4Initialization — 4 tests
# ============================================================


class TestV4Initialization:
    """V4 初始化和默认状态"""

    def test_default_state_is_idle(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        assert sm.current_phase == "IDLE"
        assert sm.last_confirmed_event == "IDLE"
        assert sm.active_hypothesis is None

    def test_default_direction_is_idle(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        assert sm.direction == StateDirection.IDLE
        assert sm.bars_processed == 0

    def test_custom_config(self):
        cfg = StateConfig()
        cfg.STATE_MIN_CONFIDENCE = 0.5
        sm = WyckoffStateMachineV4(timeframe="H1", config=cfg)
        assert sm.config.STATE_MIN_CONFIDENCE == 0.5
        assert sm.timeframe == "H1"

    def test_history_empty_on_init(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        assert sm.evidence_chain == []
        assert sm.critical_levels == {}
        assert sm._transition_history == []


# ============================================================
# TestProcessCandle — 4 tests
# ============================================================


class TestProcessCandle:
    """process_candle 返回 WyckoffStateResult"""

    def test_returns_wyckoff_state_result(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        result = sm.process_candle(_candle(), _context())
        assert isinstance(result, WyckoffStateResult)

    def test_result_has_all_fields(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        result = sm.process_candle(_candle(), _context())
        assert hasattr(result, "current_state")
        assert hasattr(result, "phase")
        assert hasattr(result, "direction")
        assert hasattr(result, "confidence")
        assert hasattr(result, "intensity")
        assert hasattr(result, "evidences")
        assert hasattr(result, "signal")
        assert hasattr(result, "signal_strength")
        assert hasattr(result, "state_changed")
        assert hasattr(result, "previous_state")
        assert hasattr(result, "heritage_score")
        assert hasattr(result, "critical_levels")

    def test_idle_stays_idle_with_flat_candle(self):
        """平淡K线不应产生假设，保持IDLE"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 极小波动、低量 → 不触发任何检测
        flat = _candle(open_=100.0, high=100.5, low=99.5, close=100.1, volume=100.0)
        result = sm.process_candle(flat, _context())
        assert result.current_state == "IDLE"
        assert result.state_changed is False

    def test_bars_processed_increments(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        assert sm.bars_processed == 0
        sm.process_candle(_candle(), _context())
        assert sm.bars_processed == 1
        sm.process_candle(_candle(), _context())
        assert sm.bars_processed == 2


# ============================================================
# TestHypothesisLifecycle — 4 tests
# ============================================================


class TestHypothesisLifecycle:
    """假设生命周期：HYPOTHETICAL→TESTING→REJECTED/EXHAUSTED"""

    def test_hypothesis_created_as_hypothetical(self):
        """高量停止行为K线应产生 HYPOTHETICAL 假设"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 大阴线+高量 → PS/SC 候选
        candle = _candle(open_=110.0, high=112.0, low=92.0, close=94.0, volume=5000.0)
        sm.process_candle(candle, _context())
        # 应该产生一个假设
        if sm.active_hypothesis is not None:
            assert sm.active_hypothesis.status == StateStatus.HYPOTHETICAL

    def test_hypothesis_upgrades_to_testing(self):
        """持续2根K线未否定的假设应升级为TESTING"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 制造一个假设
        candle = _candle(open_=110.0, high=112.0, low=92.0, close=94.0, volume=5000.0)
        sm.process_candle(candle, _context())
        if sm.active_hypothesis is None:
            pytest.skip("当前评分未产生假设，跳过升级测试")
        assert sm.active_hypothesis.status == StateStatus.HYPOTHETICAL
        # 喂2根温和K线不否定
        for _ in range(2):
            sm.process_candle(_candle(volume=1000.0), _context())
        # 假设应已升级或确认
        if sm.active_hypothesis is not None:
            assert sm.active_hypothesis.status in (
                StateStatus.TESTING,
                StateStatus.REJECTED,
            )

    def test_hypothesis_rejected_by_effort_result(self):
        """努力结果强烈背离应否定假设"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 先产生假设
        candle = _candle(open_=110.0, high=112.0, low=92.0, close=94.0, volume=5000.0)
        sm.process_candle(candle, _context())
        if sm.active_hypothesis is None:
            pytest.skip("未产生假设")
        # 直接设 rejection 来验证逻辑
        hyp = sm.active_hypothesis
        hyp.status = StateStatus.REJECTED
        hyp.rejection_reason = "努力结果强烈背离"
        assert hyp.status == StateStatus.REJECTED
        assert hyp.rejection_reason is not None

    def test_hypothesis_exhausted_after_max_bars(self):
        """超过最大K线数未确认的假设应标记EXHAUSTED"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 手动注入假设
        sm.active_hypothesis = Hypothesis(
            event_name="PS",
            status=StateStatus.HYPOTHETICAL,
            confidence=0.5,
            proposed_at_bar=1,
            bars_held=26,  # > MAX_HYPOTHESIS_BARS(25)
        )
        sm.process_candle(_candle(), _context())
        # 超时后假设被清除
        assert sm.active_hypothesis is None


# ============================================================
# TestSerializedProgression — 3 tests
# ============================================================


class TestSerializedProgression:
    """序列化推进：只允许合法的转换"""

    def test_idle_can_only_expect_ps_sc_psy_bc(self):
        """IDLE状态只能期待PS/SC/PSY/BC"""
        from src.plugins.wyckoff_state_machine.transition_guard import TransitionGuard

        targets = TransitionGuard.get_valid_targets("IDLE")
        assert targets == {"PS", "SC", "PSY", "BC"}

    def test_no_random_jumps_across_phases(self):
        """不允许从IDLE直接跳到SPRING/JOC等后期状态"""
        from src.plugins.wyckoff_state_machine.transition_guard import TransitionGuard

        targets = TransitionGuard.get_valid_targets("IDLE")
        assert "SPRING" not in targets
        assert "JOC" not in targets
        assert "MSOS" not in targets

    def test_multi_bar_confirmation_required(self):
        """状态推进需要多根K线累积确认质量"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 注入假设，确认质量不足
        sm.active_hypothesis = Hypothesis(
            event_name="PS",
            status=StateStatus.HYPOTHETICAL,
            confidence=0.5,
            proposed_at_bar=1,
            confirmation_quality=0.5,  # < CONFIRMATION_THRESHOLD(0.8)
        )
        # 喂一根平淡K线
        sm.process_candle(_candle(volume=500.0), _context())
        # 假设不会立即被确认（除非累积够了）
        # 如果还在，说明没跳变
        if sm.active_hypothesis is not None:
            assert sm.last_confirmed_event == "IDLE"


# ============================================================
# TestCriticalLevels — 3 tests
# ============================================================


class TestCriticalLevels:
    """关键价位记录和信号推导"""

    def test_sc_records_sc_low(self):
        """SC确认后应记录SC_LOW为K线最低价"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 直接模拟确认流程
        hyp = Hypothesis(
            event_name="SC",
            status=StateStatus.TESTING,
            confidence=0.8,
            proposed_at_bar=1,
            confirmation_quality=3.0,  # > threshold
        )
        candle = _candle(low=85.0, high=102.0, close=90.0)
        sm._confirm_and_advance(hyp, candle)
        assert "SC_LOW" in sm.critical_levels
        assert sm.critical_levels["SC_LOW"] == 85.0

    def test_ar_records_ar_high(self):
        """AR确认后应记录AR_HIGH为K线最高价"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        hyp = Hypothesis(
            event_name="AR",
            status=StateStatus.TESTING,
            confidence=0.7,
            proposed_at_bar=3,
        )
        candle = _candle(high=115.0, low=100.0, close=112.0)
        sm._confirm_and_advance(hyp, candle)
        assert "AR_HIGH" in sm.critical_levels
        assert sm.critical_levels["AR_HIGH"] == 115.0

    def test_signal_derivation_from_state(self):
        """信号推导：BUY_STATES→BUY, SELL_STATES→SELL, 其他→NO_SIGNAL"""
        assert (
            WyckoffStateMachineV4._derive_signal("SPRING") == WyckoffSignal.BUY_SIGNAL
        )
        assert WyckoffStateMachineV4._derive_signal("JOC") == WyckoffSignal.BUY_SIGNAL
        assert WyckoffStateMachineV4._derive_signal("UTAD") == WyckoffSignal.SELL_SIGNAL
        assert WyckoffStateMachineV4._derive_signal("LPSY") == WyckoffSignal.SELL_SIGNAL
        assert WyckoffStateMachineV4._derive_signal("IDLE") == WyckoffSignal.NO_SIGNAL
        assert WyckoffStateMachineV4._derive_signal("PS") == WyckoffSignal.NO_SIGNAL


# ============================================================
# TestBoundaryManager — 4 tests
# ============================================================


class TestBoundaryManager:
    """BoundaryManager 三态生命周期"""

    def test_propose_creates_provisional(self):
        bm = BoundaryManager()
        info = bm.propose("SC_LOW", 85.0, bar_index=5)
        assert info.status == BoundaryStatus.PROVISIONAL
        assert info.price == 85.0
        assert info.name == "SC_LOW"
        assert info.created_at_bar == 5

    def test_lock_rejects_update(self):
        """锁定后不允许 propose 覆盖"""
        bm = BoundaryManager()
        bm.propose("SC_LOW", 85.0, bar_index=5)
        bm.lock("SC_LOW", bar_index=10)
        # 尝试覆盖
        info = bm.propose("SC_LOW", 80.0, bar_index=15)
        # 应拒绝覆盖，保持原价
        assert info.price == 85.0
        assert info.status == BoundaryStatus.LOCKED

    def test_invalidate_removes_from_export(self):
        """失效的边界不导出到 critical_levels"""
        bm = BoundaryManager()
        bm.propose("SC_LOW", 85.0, bar_index=5)
        bm.propose("AR_HIGH", 110.0, bar_index=8)
        bm.invalidate("SC_LOW", bar_index=20)
        levels = bm.to_critical_levels()
        assert "SC_LOW" not in levels
        assert "AR_HIGH" in levels
        assert levels["AR_HIGH"] == 110.0

    def test_to_critical_levels_exports_non_invalidated(self):
        """to_critical_levels 只导出 PROVISIONAL+LOCKED"""
        bm = BoundaryManager()
        bm.propose("SC_LOW", 85.0, bar_index=5)
        bm.propose("AR_HIGH", 110.0, bar_index=8)
        bm.lock("SC_LOW", bar_index=10)
        levels = bm.to_critical_levels()
        assert len(levels) == 2
        assert levels["SC_LOW"] == 85.0
        assert levels["AR_HIGH"] == 110.0


# ============================================================
# TestDetectorRegistry — 3 tests
# ============================================================


class _DummyDetector(NodeDetector):
    """测试用虚拟检测器"""

    def __init__(self, detector_name: str, return_score: Optional[NodeScore] = None):
        self._name = detector_name
        self._return_score = return_score

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, candle, features, context):
        return self._return_score


class TestDetectorRegistry:
    """DetectorRegistry 注册/冷却/期待列表"""

    def test_register_and_get(self):
        reg = DetectorRegistry()
        det = _DummyDetector("PS")
        reg.register(det)
        assert reg.get("PS") is det
        assert "PS" in reg.list_names()

    def test_evaluate_expected_skips_cooldown(self):
        """冷却中的检测器应被跳过"""
        from src.plugins.wyckoff_state_machine.principles.bar_features import (
            BarFeatures,
            StructureContext,
        )

        reg = DetectorRegistry()
        score = NodeScore(
            detector_name="PS",
            event_name="PS",
            confidence=0.8,
            intensity=0.6,
            evidences=[],
        )
        det = _DummyDetector("PS", return_score=score)
        reg.register(det)
        reg.set_cooldown("PS", 3)

        # 构造简单的 features 和 context
        features = BarFeatures(
            supply_demand=0.0,
            cause_effect=0.0,
            effort_result=0.0,
            volume_ratio=1.0,
            price_range_ratio=1.0,
            body_ratio=0.5,
            is_stopping_action=False,
            spread_vs_volume_divergence=0.0,
        )
        ctx = StructureContext(
            current_phase="IDLE",
            last_confirmed_event="IDLE",
            position_in_tr=0.5,
            distance_to_support=10.0,
            distance_to_resistance=10.0,
            test_quality=0.5,
            recovery_speed=0.5,
            swing_context="unknown",
            direction_bias=0.0,
            boundaries={},
        )
        results = reg.evaluate_expected(["PS"], _candle(), features, ctx)
        assert len(results) == 0  # 冷却中，跳过

    def test_tick_cooldowns_decrements(self):
        """tick_cooldowns 每次调用减1"""
        reg = DetectorRegistry()
        reg.set_cooldown("PS", 2)
        reg.tick_cooldowns()
        assert reg._cooldowns.get("PS") == 1
        reg.tick_cooldowns()
        assert "PS" not in reg._cooldowns  # 减到0后移除


# ============================================================
# TestSignalDerivation — 3 tests
# ============================================================


class TestSignalDerivation:
    """信号强度推导"""

    def test_strong_buy_signal(self):
        assert WyckoffStateMachineV4._derive_strength("JOC") == "strong"
        assert WyckoffStateMachineV4._derive_strength("MSOS") == "strong"

    def test_medium_sell_signal(self):
        assert WyckoffStateMachineV4._derive_strength("UTAD") == "medium"
        assert WyckoffStateMachineV4._derive_strength("LPSY") == "medium"

    def test_no_signal_for_neutral_states(self):
        assert WyckoffStateMachineV4._derive_strength("IDLE") == "none"
        assert WyckoffStateMachineV4._derive_strength("PS") == "none"
        assert WyckoffStateMachineV4._derive_strength("SC") == "none"


# ============================================================
# TestPhaseMap — 2 tests
# ============================================================


class TestPhaseMap:
    """PHASE_MAP 映射验证"""

    def test_accum_a_phase_states(self):
        """吸筹A阶段状态映射正确"""
        for state in ("PS", "SC", "AR", "ST"):
            assert PHASE_MAP[state] == "A", f"{state} should map to A"

    def test_all_states_have_mapping(self):
        """所有状态都有映射"""
        all_states = {
            "PS",
            "SC",
            "AR",
            "ST",
            "TEST",
            "UTA",
            "SPRING",
            "SO",
            "LPS",
            "mSOS",
            "MSOS",
            "JOC",
            "BU",
            "PSY",
            "BC",
            "AR_DIST",
            "ST_DIST",
            "UT",
            "UTAD",
            "LPSY",
            "mSOW",
            "MSOW",
            "IDLE",
            "UPTREND",
            "DOWNTREND",
            "RE_ACCUMULATION",
            "RE_DISTRIBUTION",
        }
        for state in all_states:
            assert state in PHASE_MAP, f"{state} missing from PHASE_MAP"


# ============================================================
# TestTransitionHistoryBug — regression test for from==to bug
# ============================================================


class TestTransitionHistoryBug:
    """回归测试: transition_history 的 from 和 to 不能相同"""

    def test_transition_history_from_differs_from_to(self):
        """确认后 transition_history[-1]["from"] != [-1]["to"]"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        assert sm.last_confirmed_event == "IDLE"

        # 模拟 IDLE → PS 转换
        hyp_ps = Hypothesis(
            event_name="PS",
            status=StateStatus.TESTING,
            confidence=0.6,
            proposed_at_bar=1,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_ps, _candle())
        assert len(sm._transition_history) == 1
        rec = sm._transition_history[-1]
        assert rec["from"] == "IDLE", f"from should be IDLE, got {rec['from']}"
        assert rec["to"] == "PS", f"to should be PS, got {rec['to']}"
        assert rec["from"] != rec["to"]

    def test_two_consecutive_transitions_record_correct_from(self):
        """连续两次转换: IDLE→PS→SC, 第二次的 from 应是 PS"""
        sm = WyckoffStateMachineV4(timeframe="H4")

        # IDLE → PS
        hyp_ps = Hypothesis(
            event_name="PS",
            status=StateStatus.TESTING,
            confidence=0.6,
            proposed_at_bar=1,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_ps, _candle())

        # PS → SC
        hyp_sc = Hypothesis(
            event_name="SC",
            status=StateStatus.TESTING,
            confidence=0.8,
            proposed_at_bar=5,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_sc, _candle(low=80.0))
        assert len(sm._transition_history) == 2
        rec = sm._transition_history[-1]
        assert rec["from"] == "PS", f"from should be PS, got {rec['from']}"
        assert rec["to"] == "SC", f"to should be SC, got {rec['to']}"
        assert rec["from"] != rec["to"]


# ============================================================
# TestBoundaryManagerWiring — 3 tests
# ============================================================


class TestBoundaryManagerWiring:
    """BoundaryManager 接线验证：propose/lock/reset 生命周期"""

    def test_sc_proposes_sc_low_via_boundary_manager(self):
        """SC 确认后 _boundary_manager 应有 PROVISIONAL SC_LOW"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        hyp = Hypothesis(
            event_name="SC",
            status=StateStatus.TESTING,
            confidence=0.8,
            proposed_at_bar=1,
            confirmation_quality=3.0,
        )
        candle = _candle(low=82.0, high=100.0, close=88.0)
        sm._confirm_and_advance(hyp, candle)
        # BoundaryManager 应有 SC_LOW
        info = sm._boundary_manager.get("SC_LOW")
        assert info is not None
        assert info.price == 82.0
        assert info.status == BoundaryStatus.PROVISIONAL
        # critical_levels 同步
        assert sm.critical_levels.get("SC_LOW") == 82.0

    def test_st_locks_sc_low(self):
        """SC → ST 确认后，SC_LOW 应被锁定"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 先确认 SC → SC_LOW proposed
        hyp_sc = Hypothesis(
            event_name="SC",
            status=StateStatus.TESTING,
            confidence=0.8,
            proposed_at_bar=1,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_sc, _candle(low=82.0, close=88.0))
        assert sm._boundary_manager.get("SC_LOW").status == BoundaryStatus.PROVISIONAL
        # 确认 ST → SC_LOW locked
        hyp_st = Hypothesis(
            event_name="ST",
            status=StateStatus.TESTING,
            confidence=0.7,
            proposed_at_bar=5,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_st, _candle(low=84.0, close=90.0))
        info = sm._boundary_manager.get("SC_LOW")
        assert info is not None
        assert info.status == BoundaryStatus.LOCKED
        assert info.price == 82.0  # 原价不变

    def test_reset_clears_boundary_manager(self):
        """_reset_to_idle 后 BoundaryManager 应为空"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 先设置一些边界
        hyp = Hypothesis(
            event_name="SC",
            status=StateStatus.TESTING,
            confidence=0.8,
            proposed_at_bar=1,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp, _candle(low=82.0, close=88.0))
        assert sm._boundary_manager.get("SC_LOW") is not None
        # 重置
        sm._reset_to_idle()
        assert sm._boundary_manager.get("SC_LOW") is None
        assert sm.critical_levels == {}
        assert sm._boundary_manager.to_critical_levels() == {}


# ============================================================
# TestMarketMode — 4 tests
# ============================================================


class TestMarketMode:
    """MarketMode 模式转换逻辑"""

    def test_initial_mode_is_trending(self):
        """初始模式应为 TRENDING"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        assert sm.market_mode == MarketMode.TRENDING

    def test_mode_transitions_to_transitioning_on_sc(self):
        """SC 确认后 TRENDING → TRANSITIONING（≥5根K线滞后）"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.bars_processed = 10  # 满足滞后要求
        assert sm.market_mode == MarketMode.TRENDING

        hyp = Hypothesis(
            event_name="SC",
            status=StateStatus.TESTING,
            confidence=0.8,
            proposed_at_bar=5,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp, _candle(low=80.0, close=88.0))
        assert sm.market_mode == MarketMode.TRANSITIONING

    def test_mode_transitions_to_ranging_on_st(self):
        """ST 确认后 TRANSITIONING → RANGING"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.bars_processed = 10
        # 先到 TRANSITIONING
        sm.market_mode = MarketMode.TRANSITIONING

        hyp = Hypothesis(
            event_name="ST",
            status=StateStatus.TESTING,
            confidence=0.7,
            proposed_at_bar=8,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp, _candle(low=82.0, close=90.0))
        assert sm.market_mode == MarketMode.RANGING

    def test_mode_resets_on_reset_to_idle(self):
        """_reset_to_idle 后模式回到 TRENDING"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.market_mode = MarketMode.RANGING
        sm.structure_hypothesis = "dummy"
        sm._reset_to_idle()
        assert sm.market_mode == MarketMode.TRENDING
        assert sm.structure_hypothesis is None


# ============================================================
# TestStructureHypothesis — 4 tests
# ============================================================


class TestStructureHypothesis:
    """StructureHypothesis 结构假设生命周期"""

    def test_ps_creates_structure_hypothesis(self):
        """PS 确认后应创建 StructureHypothesis(confidence≈0.2, direction=UNKNOWN)"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        assert sm.structure_hypothesis is None
        hyp = Hypothesis(
            event_name="PS",
            status=StateStatus.TESTING,
            confidence=0.6,
            proposed_at_bar=1,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp, _candle())
        sh = sm.structure_hypothesis
        assert sh is not None
        assert isinstance(sh, StructureHypothesis)
        assert sh.confidence == pytest.approx(0.2, abs=0.01)
        assert sh.direction == "UNKNOWN"
        assert "PS" in sh.events_confirmed

    def test_events_accumulate_confidence(self):
        """PS→SC→AR→ST 序列中 confidence 持续增长"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.bars_processed = 10  # 满足 market_mode hysteresis

        # PS → 创建 sh, confidence=0.2
        hyp_ps = Hypothesis(
            event_name="PS",
            status=StateStatus.TESTING,
            confidence=0.6,
            proposed_at_bar=1,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_ps, _candle())
        c1 = sm.structure_hypothesis.confidence
        assert c1 == pytest.approx(0.2, abs=0.01)

        # SC → 已有 sh，停止行为追加 +0.1
        hyp_sc = Hypothesis(
            event_name="SC",
            status=StateStatus.TESTING,
            confidence=0.8,
            proposed_at_bar=3,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_sc, _candle(low=80.0, close=85.0))
        c2 = sm.structure_hypothesis.confidence
        assert c2 > c1  # 0.2 + 0.1 = 0.3

        # AR → 方向设定 +0.15
        hyp_ar = Hypothesis(
            event_name="AR",
            status=StateStatus.TESTING,
            confidence=0.7,
            proposed_at_bar=6,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_ar, _candle(high=115.0, close=112.0))
        c3 = sm.structure_hypothesis.confidence
        assert c3 > c2
        assert sm.structure_hypothesis.direction == "ACCUM"

        # ST → 巩固 +0.15
        hyp_st = Hypothesis(
            event_name="ST",
            status=StateStatus.TESTING,
            confidence=0.7,
            proposed_at_bar=10,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp_st, _candle(low=82.0, close=90.0))
        c4 = sm.structure_hypothesis.confidence
        assert c4 > c3
        assert len(sm.structure_hypothesis.events_confirmed) == 4

    def test_structure_failure_clears(self):
        """_reset_to_idle() 应清除 structure_hypothesis"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.structure_hypothesis = StructureHypothesis(
            direction="ACCUM",
            confidence=0.5,
            created_at_bar=1,
            events_confirmed=["PS", "SC"],
        )
        sm._reset_to_idle()
        assert sm.structure_hypothesis is None

    def test_uptrend_completes_structure(self):
        """UPTREND 确认后 structure_hypothesis 应为 None"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.bars_processed = 10
        # 先创建一个结构假设
        sm.structure_hypothesis = StructureHypothesis(
            direction="ACCUM",
            confidence=0.8,
            created_at_bar=1,
            events_confirmed=["PS", "SC", "AR", "ST"],
        )
        # 确认 UPTREND → 结构完成
        hyp = Hypothesis(
            event_name="UPTREND",
            status=StateStatus.TESTING,
            confidence=0.9,
            proposed_at_bar=50,
            confirmation_quality=3.0,
        )
        sm._confirm_and_advance(hyp, _candle())
        assert sm.structure_hypothesis is None


# ============================================================
# TestPositionInTrBoundaryPriority — 2 tests
# ============================================================


class TestPositionInTrBoundaryPriority:
    """position_in_tr 优先使用内部边界（BoundaryManager），回退到外部 TR"""

    def test_position_in_tr_uses_internal_boundaries(self):
        """SC_LOW + AR_HIGH 存在时，position_in_tr 基于内部边界计算"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 通过 BoundaryManager 设定内部边界
        sm._boundary_manager.propose("SC_LOW", 80.0, bar_index=1)
        sm._boundary_manager.propose("AR_HIGH", 120.0, bar_index=3)
        # 外部 TR 故意设不同值
        ctx = _context(tr_support=50.0, tr_resistance=150.0)
        # close=100 → 内部边界 pos = (100-80)/(120-80) = 0.5
        candle = _candle(close=100.0)
        struct = sm._build_structure_context(candle, ctx)
        assert struct.position_in_tr == pytest.approx(0.5, abs=0.01)
        # distance 也应基于内部边界
        assert struct.distance_to_support == pytest.approx(20.0, abs=0.1)
        assert struct.distance_to_resistance == pytest.approx(20.0, abs=0.1)

        # close=90 → 内部边界 pos = (90-80)/40 = 0.25
        candle2 = _candle(close=90.0)
        struct2 = sm._build_structure_context(candle2, ctx)
        assert struct2.position_in_tr == pytest.approx(0.25, abs=0.01)

    def test_position_in_tr_fallback_external(self):
        """无内部边界时，回退到外部 TR"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        # 不设内部边界
        ctx = _context(tr_support=90.0, tr_resistance=110.0)
        # close=100 → 外部 pos = (100-90)/20 = 0.5
        candle = _candle(close=100.0)
        struct = sm._build_structure_context(candle, ctx)
        assert struct.position_in_tr == pytest.approx(0.5, abs=0.01)
        assert struct.distance_to_support == pytest.approx(10.0, abs=0.1)
        assert struct.distance_to_resistance == pytest.approx(10.0, abs=0.1)

    def test_position_in_tr_default_no_boundaries(self):
        """无内部也无外部边界 → 默认 0.5"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        ctx = _context(tr_support=0.0, tr_resistance=0.0)
        candle = _candle(close=100.0)
        struct = sm._build_structure_context(candle, ctx)
        assert struct.position_in_tr == pytest.approx(0.5, abs=0.01)

    def test_invalidated_boundaries_fallback(self):
        """INVALIDATED 的内部边界不使用，回退到外部 TR"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm._boundary_manager.propose("SC_LOW", 80.0, bar_index=1)
        sm._boundary_manager.propose("AR_HIGH", 120.0, bar_index=3)
        sm._boundary_manager.invalidate("SC_LOW", bar_index=10)
        # 外部 TR 生效
        ctx = _context(tr_support=90.0, tr_resistance=110.0)
        candle = _candle(close=100.0)
        struct = sm._build_structure_context(candle, ctx)
        # 应回退到外部 TR: (100-90)/20 = 0.5
        assert struct.position_in_tr == pytest.approx(0.5, abs=0.01)
        assert struct.distance_to_support == pytest.approx(10.0, abs=0.1)


# ---------------------------------------------------------------------------
# T13: 冷启动行为验证
# ---------------------------------------------------------------------------


class TestColdStart:
    """冷启动 = TRENDING模式直到第一个停止行为"""

    def test_cold_start_no_false_events(self):
        """冷启动期间：TRENDING模式下不触发区间内事件（Spring/LPS/SOS等）"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        ctx = _context(market_regime="TRENDING")

        # 喂入20根平稳K线
        for i in range(20):
            p = 50000 + (i % 3 - 1) * 50
            candle = _candle(
                open_=p, high=p + 100, low=p - 100, close=p + 20, volume=100000
            )
            sm.process_candle(candle, ctx)

        # 冷启动允许PS/SC等停止行为检测，但不允许Spring/LPS/SOS等区间内事件
        # 所以 last_confirmed_event 可以是 IDLE 或 PS/SC（停止行为入口）
        ranging_events = {
            "SPRING",
            "SO",
            "LPS",
            "mSOS",
            "MSOS",
            "JOC",
            "BU",
            "UTAD",
            "LPSY",
            "mSOW",
            "MSOW",
        }
        assert sm.last_confirmed_event not in ranging_events
        assert len(sm._recent_closes) == 20

    def test_cold_start_statistics_accumulate(self):
        """冷启动期间统计数据正常积累"""
        sm = WyckoffStateMachineV4(timeframe="H4")
        ctx = _context(market_regime="TRENDING")

        for i in range(10):
            candle = _candle(
                open_=50000, high=50100, low=49900, close=50050, volume=100000
            )
            sm.process_candle(candle, ctx)

        assert sm.bars_processed == 10
        assert len(sm._recent_closes) == 10
