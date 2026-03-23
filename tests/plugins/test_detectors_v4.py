"""Phase 3 检测器单元测试 — 22个 V4 检测器 + DetectorRegistry 集成

测试覆盖:
- 13 个吸筹检测器 (PS/SC/AR/ST/TEST/UTA/SPRING/SO/LPS/mSOS/MSOS/JOC/BU)
- 9 个派发检测器 (PSY/BC/AR_DIST/ST_DIST/UT/UTAD/LPSY/mSOW/MSOW)
- DetectorRegistry 集成 (注册/evaluate_expected/冷却)
"""

import pytest

from src.plugins.wyckoff_state_machine.detectors.accumulation import (
    PSDetector,
    SCDetector,
    ARDetector,
    STDetector,
    TestDetector,
    UTADetector,
    SpringDetector,
    SODetector,
    LPSDetector,
    MinorSOSDetector,
    MSOSDetector,
    JOCDetector,
    BUDetector,
)
from src.plugins.wyckoff_state_machine.detectors.distribution import (
    PSYDetector,
    BCDetector,
    ARDistDetector,
    STDistDetector,
    UTDetector,
    UTADDetector,
    LPSYDetector,
    MinorSOWDetector,
    MSOWDetector,
)
from src.plugins.wyckoff_state_machine.detector_registry import (
    NodeScore,
    DetectorRegistry,
)
from src.plugins.wyckoff_state_machine.principles.bar_features import (
    BarFeatures,
    StructureContext,
)
from src.plugins.wyckoff_state_machine.state_machine_v4 import WyckoffStateMachineV4


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _candle(open_=100.0, high=105.0, low=95.0, close=103.0, volume=1000.0):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _features(**kw):
    defaults = dict(
        supply_demand=0.0,
        cause_effect=0.0,
        effort_result=0.0,
        volume_ratio=1.0,
        price_range_ratio=1.0,
        body_ratio=0.5,
        is_stopping_action=False,
        spread_vs_volume_divergence=0.0,
    )
    defaults.update(kw)
    return BarFeatures(**defaults)


def _context(**kw):
    defaults = dict(
        current_phase="B",
        last_confirmed_event="ST",
        position_in_tr=0.5,
        distance_to_support=0.5,
        distance_to_resistance=0.5,
        test_quality=0.5,
        recovery_speed=0.5,
        swing_context="unknown",
        direction_bias=0.0,
        boundaries={"SC_LOW": {}, "AR_HIGH": {}},
    )
    defaults.update(kw)
    return StructureContext(**defaults)


# ---------------------------------------------------------------------------
# TestAccumulationDetectors
# ---------------------------------------------------------------------------


class TestAccumulationDetectors:
    """13 个吸筹检测器测试"""

    def test_ps_detects_stopping_action(self):
        """PS: stopping_action=True + supply_demand>0 → NodeScore"""
        d = PSDetector()
        score = d.evaluate(
            _candle(),
            _features(supply_demand=0.4, is_stopping_action=True, volume_ratio=1.5),
            _context(),
        )
        assert score is not None
        assert score.event_name == "PS"
        assert score.confidence > 0.3

    def test_sc_detects_high_volume_drop(self):
        """SC: volume_ratio>2 + wide range + stopping → NodeScore"""
        d = SCDetector()
        score = d.evaluate(
            _candle(low=80.0),
            _features(
                volume_ratio=3.0,
                price_range_ratio=1.8,
                is_stopping_action=True,
                spread_vs_volume_divergence=0.5,
            ),
            _context(),
        )
        assert score is not None
        assert score.event_name == "SC"
        assert score.confidence >= 0.5

    def test_ar_detects_bounce(self):
        """AR: supply_demand>0.3 + volume shrink + near support → NodeScore"""
        d = ARDetector()
        score = d.evaluate(
            _candle(close=104.0),
            _features(supply_demand=0.4, volume_ratio=0.6, effort_result=0.3),
            _context(position_in_tr=0.3, distance_to_support=0.2),
        )
        assert score is not None
        assert score.event_name == "AR"
        assert score.confidence > 0.3

    def test_spring_detects_break_below(self):
        """SPRING: position_in_tr<0 + close>low → NodeScore"""
        d = SpringDetector()
        score = d.evaluate(
            _candle(low=90.0, close=98.0),
            _features(supply_demand=0.2, volume_ratio=0.8),
            _context(position_in_tr=-0.05, distance_to_support=0.02),
        )
        assert score is not None
        assert score.event_name == "SPRING"
        assert score.confidence > 0.3
        assert score.cooldown_bars == 3

    def test_joc_detects_breakout(self):
        """JOC: position_in_tr>1.0 + volume surge → NodeScore"""
        d = JOCDetector()
        score = d.evaluate(
            _candle(high=115.0, close=112.0),
            _features(volume_ratio=2.5, supply_demand=0.5, effort_result=0.4),
            _context(position_in_tr=1.1),
        )
        assert score is not None
        assert score.event_name == "JOC"
        assert score.confidence > 0.5

    def test_st_detects_support_test(self):
        """ST: near support + volume dry → NodeScore"""
        d = STDetector()
        score = d.evaluate(
            _candle(),
            _features(volume_ratio=0.5, body_ratio=0.3, supply_demand=0.1),
            _context(distance_to_support=0.05),
        )
        assert score is not None
        assert score.event_name == "ST"

    def test_lps_detects_higher_low(self):
        """LPS: higher low + vol dry + demand → NodeScore"""
        d = LPSDetector()
        score = d.evaluate(
            _candle(),
            _features(volume_ratio=0.5, supply_demand=0.3),
            _context(position_in_tr=0.25, recovery_speed=0.5),
        )
        assert score is not None
        assert score.event_name == "LPS"

    def test_TEST_positive(self):
        """TEST: near support + vol dry + high test quality → NodeScore"""
        d = TestDetector()
        score = d.evaluate(
            _candle(),
            _features(volume_ratio=0.5, supply_demand=0.2),
            _context(distance_to_support=0.05, test_quality=0.7),
        )
        assert score is not None
        assert score.event_name == "TEST"
        assert score.confidence > 0.3

    def test_TEST_negative(self):
        """TEST: far from support + high volume → None"""
        d = TestDetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=2.0, supply_demand=-0.3),
            _context(distance_to_support=0.8, test_quality=0.1),
        )
        assert result is None

    def test_UTA_positive(self):
        """UTA: high position + near resistance + low volume + supply → NodeScore"""
        d = UTADetector()
        score = d.evaluate(
            _candle(high=110.0, close=106.0),
            _features(volume_ratio=0.6, supply_demand=-0.2),
            _context(position_in_tr=0.9, distance_to_resistance=0.03),
        )
        assert score is not None
        assert score.event_name == "UTA"
        assert score.confidence > 0.3

    def test_UTA_negative(self):
        """UTA: low position + high volume → None"""
        d = UTADetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=2.0, supply_demand=0.5),
            _context(position_in_tr=0.3, distance_to_resistance=0.5),
        )
        assert result is None

    def test_SO_positive(self):
        """SO: low position + high volume + stopping action → NodeScore"""
        d = SODetector()
        score = d.evaluate(
            _candle(low=88.0, close=95.0),
            _features(
                volume_ratio=2.0,
                is_stopping_action=True,
                spread_vs_volume_divergence=0.4,
            ),
            _context(position_in_tr=0.05),
        )
        assert score is not None
        assert score.event_name == "SO"
        assert score.confidence > 0.3

    def test_SO_negative(self):
        """SO: high position + low volume → None"""
        d = SODetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=0.5),
            _context(position_in_tr=0.8),
        )
        assert result is None

    def test_mSOS_positive(self):
        """mSOS: bullish candle + upper TR + mild volume + demand → NodeScore"""
        d = MinorSOSDetector()
        score = d.evaluate(
            _candle(open_=98.0, close=104.0),
            _features(volume_ratio=1.3, supply_demand=0.3),
            _context(position_in_tr=0.6),
        )
        assert score is not None
        assert score.event_name == "mSOS"
        assert score.confidence > 0.3

    def test_mSOS_negative(self):
        """mSOS: bearish candle + low position + no demand → None"""
        d = MinorSOSDetector()
        result = d.evaluate(
            _candle(open_=105.0, close=98.0),
            _features(volume_ratio=0.5, supply_demand=-0.3),
            _context(position_in_tr=0.2),
        )
        assert result is None

    def test_MSOS_positive(self):
        """MSOS: high position + strong volume + demand + effort harmony → NodeScore"""
        d = MSOSDetector()
        score = d.evaluate(
            _candle(high=115.0, close=113.0),
            _features(
                volume_ratio=2.5,
                supply_demand=0.5,
                effort_result=0.4,
            ),
            _context(position_in_tr=0.9),
        )
        assert score is not None
        assert score.event_name == "MSOS"
        assert score.confidence > 0.5

    def test_MSOS_negative(self):
        """MSOS: low position + low volume + supply → None"""
        d = MSOSDetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=0.5, supply_demand=-0.3),
            _context(position_in_tr=0.3),
        )
        assert result is None

    def test_BU_positive(self):
        """BU: pullback zone + low volume + bullish candle + demand → NodeScore"""
        d = BUDetector()
        score = d.evaluate(
            _candle(open_=99.0, close=103.0),
            _features(volume_ratio=0.6, supply_demand=0.2),
            _context(position_in_tr=1.0),
        )
        assert score is not None
        assert score.event_name == "BU"
        assert score.confidence > 0.3

    def test_BU_negative(self):
        """BU: low position + high volume + bearish → None"""
        d = BUDetector()
        result = d.evaluate(
            _candle(open_=105.0, close=97.0),
            _features(volume_ratio=2.0, supply_demand=-0.3),
            _context(position_in_tr=0.3),
        )
        assert result is None

    def test_all_new_positives_have_evidences(self):
        """All 6 new accumulation detectors produce non-empty evidences"""
        cases = [
            (
                TestDetector(),
                _candle(),
                _features(volume_ratio=0.5, supply_demand=0.2),
                _context(distance_to_support=0.05, test_quality=0.7),
            ),
            (
                UTADetector(),
                _candle(high=110.0, close=106.0),
                _features(volume_ratio=0.6, supply_demand=-0.2),
                _context(position_in_tr=0.9, distance_to_resistance=0.03),
            ),
            (
                SODetector(),
                _candle(low=88.0),
                _features(
                    volume_ratio=2.0,
                    is_stopping_action=True,
                    spread_vs_volume_divergence=0.4,
                ),
                _context(position_in_tr=0.05),
            ),
            (
                MinorSOSDetector(),
                _candle(open_=98.0, close=104.0),
                _features(volume_ratio=1.3, supply_demand=0.3),
                _context(position_in_tr=0.6),
            ),
            (
                MSOSDetector(),
                _candle(high=115.0),
                _features(volume_ratio=2.5, supply_demand=0.5, effort_result=0.4),
                _context(position_in_tr=0.9),
            ),
            (
                BUDetector(),
                _candle(open_=99.0, close=103.0),
                _features(volume_ratio=0.6, supply_demand=0.2),
                _context(position_in_tr=1.0),
            ),
        ]
        for det, c, f, ctx in cases:
            score = det.evaluate(c, f, ctx)
            assert score is not None, f"{det.name} should detect"
            assert len(score.evidences) > 0, f"{det.name} should have evidences"

    def test_low_confidence_returns_none(self):
        """中性K线 → 所有检测器应返回 None"""
        neutral_f = _features()  # all defaults = neutral
        neutral_ctx = _context()
        candle = _candle()
        for det_cls in (
            PSDetector,
            SCDetector,
            ARDetector,
            STDetector,
            SpringDetector,
            JOCDetector,
            MSOSDetector,
        ):
            d = det_cls()
            result = d.evaluate(candle, neutral_f, neutral_ctx)
            assert result is None, f"{d.name} should return None for neutral candle"


# ---------------------------------------------------------------------------
# TestDistributionDetectors
# ---------------------------------------------------------------------------


class TestDistributionDetectors:
    """9 个派发检测器测试"""

    def test_psy_detects_supply(self):
        """PSY: supply_demand<-0.2 + volume up → NodeScore"""
        d = PSYDetector()
        score = d.evaluate(
            _candle(close=97.0),
            _features(supply_demand=-0.3, volume_ratio=1.5, is_stopping_action=True),
            _context(position_in_tr=0.8),
        )
        assert score is not None
        assert score.event_name == "PSY"
        assert score.confidence > 0.3

    def test_bc_detects_climax(self):
        """BC: volume_ratio>2 + high position + divergence → NodeScore"""
        d = BCDetector()
        score = d.evaluate(
            _candle(high=120.0, close=118.0),
            _features(
                volume_ratio=2.5,
                price_range_ratio=1.8,
                spread_vs_volume_divergence=0.5,
            ),
            _context(position_in_tr=0.9),
        )
        assert score is not None
        assert score.event_name == "BC"
        assert score.confidence >= 0.5

    def test_utad_detects_overthrow(self):
        """UTAD: position_in_tr>1.0 + volume + supply → NodeScore"""
        d = UTADDetector()
        score = d.evaluate(
            _candle(high=115.0, close=108.0),
            _features(
                volume_ratio=2.0,
                supply_demand=-0.3,
                spread_vs_volume_divergence=0.3,
            ),
            _context(position_in_tr=1.1),
        )
        assert score is not None
        assert score.event_name == "UTAD"
        assert score.confidence > 0.3

    def test_msow_detects_breakdown(self):
        """MSOW: position_in_tr<0.05 + volume + strong supply → NodeScore"""
        d = MSOWDetector()
        score = d.evaluate(
            _candle(low=88.0, close=89.0),
            _features(
                volume_ratio=2.0,
                supply_demand=-0.5,
                body_ratio=0.7,
            ),
            _context(position_in_tr=0.02),
        )
        assert score is not None
        assert score.event_name == "MSOW"
        assert score.confidence >= 0.5

    def test_lpsy_detects_weak_rally(self):
        """LPSY: mid-range + vol dry + supply → NodeScore"""
        d = LPSYDetector()
        score = d.evaluate(
            _candle(),
            _features(volume_ratio=0.5, supply_demand=-0.2),
            _context(position_in_tr=0.5, last_confirmed_event="UTAD"),
        )
        assert score is not None
        assert score.event_name == "LPSY"

    def test_AR_DIST_positive(self):
        """AR_DIST: low volume + supply + position below mid + after BC → NodeScore"""
        d = ARDistDetector()
        score = d.evaluate(
            _candle(close=97.0),
            _features(volume_ratio=0.6, supply_demand=-0.3),
            _context(position_in_tr=0.4, last_confirmed_event="BC"),
        )
        assert score is not None
        assert score.event_name == "AR_DIST"
        assert score.confidence > 0.3

    def test_AR_DIST_negative(self):
        """AR_DIST: high volume + demand + high position → None"""
        d = ARDistDetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=2.0, supply_demand=0.5),
            _context(position_in_tr=0.9),
        )
        assert result is None

    def test_ST_DIST_positive(self):
        """ST_DIST: near resistance + low volume + supply + after BC → NodeScore"""
        d = STDistDetector()
        score = d.evaluate(
            _candle(high=112.0, close=110.0),
            _features(volume_ratio=0.6, supply_demand=-0.2),
            _context(position_in_tr=0.85, last_confirmed_event="AR_DIST"),
        )
        assert score is not None
        assert score.event_name == "ST_DIST"
        assert score.confidence > 0.3

    def test_ST_DIST_negative(self):
        """ST_DIST: low position + high volume + demand → None"""
        d = STDistDetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=2.0, supply_demand=0.5),
            _context(position_in_tr=0.3),
        )
        assert result is None

    def test_UT_positive(self):
        """UT: above resistance + small body + low volume + supply → NodeScore"""
        d = UTDetector()
        score = d.evaluate(
            _candle(open_=109.0, high=112.0, close=110.0),
            _features(volume_ratio=0.6, body_ratio=0.3, supply_demand=-0.2),
            _context(position_in_tr=1.0),
        )
        assert score is not None
        assert score.event_name == "UT"
        assert score.confidence > 0.3

    def test_UT_negative(self):
        """UT: low position + large body + high volume → None"""
        d = UTDetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=2.0, body_ratio=0.8, supply_demand=0.5),
            _context(position_in_tr=0.3),
        )
        assert result is None

    def test_mSOW_positive(self):
        """mSOW: near support + supply + mild volume + small body → NodeScore"""
        d = MinorSOWDetector()
        score = d.evaluate(
            _candle(low=90.0, close=93.0),
            _features(
                volume_ratio=1.3,
                supply_demand=-0.3,
                body_ratio=0.4,
            ),
            _context(position_in_tr=0.1),
        )
        assert score is not None
        assert score.event_name == "mSOW"
        assert score.confidence > 0.3

    def test_mSOW_negative(self):
        """mSOW: high position + no supply + low volume → None"""
        d = MinorSOWDetector()
        result = d.evaluate(
            _candle(),
            _features(volume_ratio=0.5, supply_demand=0.3),
            _context(position_in_tr=0.8),
        )
        assert result is None

    def test_all_new_positives_have_evidences(self):
        """All 4 new distribution detectors produce non-empty evidences"""
        cases = [
            (
                ARDistDetector(),
                _candle(close=97.0),
                _features(volume_ratio=0.6, supply_demand=-0.3),
                _context(position_in_tr=0.4, last_confirmed_event="BC"),
            ),
            (
                STDistDetector(),
                _candle(high=112.0, close=110.0),
                _features(volume_ratio=0.6, supply_demand=-0.2),
                _context(position_in_tr=0.85, last_confirmed_event="AR_DIST"),
            ),
            (
                UTDetector(),
                _candle(high=112.0, close=110.0),
                _features(volume_ratio=0.6, body_ratio=0.3, supply_demand=-0.2),
                _context(position_in_tr=1.0),
            ),
            (
                MinorSOWDetector(),
                _candle(low=90.0, close=93.0),
                _features(volume_ratio=1.3, supply_demand=-0.3, body_ratio=0.4),
                _context(position_in_tr=0.1),
            ),
        ]
        for det, c, f, ctx in cases:
            score = det.evaluate(c, f, ctx)
            assert score is not None, f"{det.name} should detect"
            assert len(score.evidences) > 0, f"{det.name} should have evidences"

    def test_low_confidence_returns_none(self):
        """中性K线 → 派发检测器应返回 None"""
        neutral_f = _features()
        neutral_ctx = _context()
        candle = _candle()
        for det_cls in (PSYDetector, BCDetector, UTADDetector, MSOWDetector):
            d = det_cls()
            result = d.evaluate(candle, neutral_f, neutral_ctx)
            assert result is None, f"{d.name} should return None for neutral candle"


# ---------------------------------------------------------------------------
# TestRegistryIntegration
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    """DetectorRegistry + WyckoffStateMachineV4 集成测试"""

    def test_v4_registers_all_22(self):
        """WyckoffStateMachineV4 应注册全部 22 个检测器"""
        v4 = WyckoffStateMachineV4()
        names = v4._registry.list_names()
        assert len(names) == 22, f"Expected 22, got {len(names)}: {names}"

    def test_evaluate_expected_filters(self):
        """evaluate_expected 只运行 expected_events 中的检测器"""
        reg = DetectorRegistry()
        reg.register(PSDetector())
        reg.register(SCDetector())
        reg.register(ARDetector())

        results = reg.evaluate_expected(
            expected_events=["SC"],
            candle=_candle(low=80.0),
            features=_features(
                volume_ratio=3.0,
                price_range_ratio=2.0,
                is_stopping_action=True,
                spread_vs_volume_divergence=0.5,
            ),
            context=_context(),
        )
        # SC 应该被检测到，PS 和 AR 不在 expected 中不应被运行
        event_names = [r.event_name for r in results]
        assert "SC" in event_names
        assert "PS" not in event_names
        assert "AR" not in event_names

    def test_all_detectors_have_name(self):
        """每个检测器都应有非空字符串 name"""
        all_cls = [
            PSDetector,
            SCDetector,
            ARDetector,
            STDetector,
            TestDetector,
            UTADetector,
            SpringDetector,
            SODetector,
            LPSDetector,
            MinorSOSDetector,
            MSOSDetector,
            JOCDetector,
            BUDetector,
            PSYDetector,
            BCDetector,
            ARDistDetector,
            STDistDetector,
            UTDetector,
            UTADDetector,
            LPSYDetector,
            MinorSOWDetector,
            MSOWDetector,
        ]
        for cls in all_cls:
            d = cls()
            assert isinstance(d.name, str) and len(d.name) > 0, (
                f"{cls.__name__}.name is invalid"
            )

    def test_all_detectors_accept_interface(self):
        """所有检测器的 evaluate(candle, features, context) 接口均可调用"""
        all_cls = [
            PSDetector,
            SCDetector,
            ARDetector,
            STDetector,
            TestDetector,
            UTADetector,
            SpringDetector,
            SODetector,
            LPSDetector,
            MinorSOSDetector,
            MSOSDetector,
            JOCDetector,
            BUDetector,
            PSYDetector,
            BCDetector,
            ARDistDetector,
            STDistDetector,
            UTDetector,
            UTADDetector,
            LPSYDetector,
            MinorSOWDetector,
            MSOWDetector,
        ]
        candle = _candle()
        features = _features()
        ctx = _context()
        for cls in all_cls:
            d = cls()
            result = d.evaluate(candle, features, ctx)
            assert result is None or isinstance(result, NodeScore), (
                f"{d.name} returned unexpected type: {type(result)}"
            )

    def test_cooldown_blocks_detection(self):
        """冷却期内检测器不应被运行"""
        reg = DetectorRegistry()
        reg.register(SCDetector())
        reg.set_cooldown("SC", 3)

        results = reg.evaluate_expected(
            expected_events=["SC"],
            candle=_candle(low=80.0),
            features=_features(volume_ratio=3.0, price_range_ratio=2.0),
            context=_context(),
        )
        assert len(results) == 0, "SC should be blocked by cooldown"

        # tick 3 次后冷却结束
        reg.tick_cooldowns()
        reg.tick_cooldowns()
        reg.tick_cooldowns()

        results2 = reg.evaluate_expected(
            expected_events=["SC"],
            candle=_candle(low=80.0),
            features=_features(
                volume_ratio=3.0,
                price_range_ratio=2.0,
                is_stopping_action=True,
                spread_vs_volume_divergence=0.5,
            ),
            context=_context(),
        )
        assert len(results2) > 0, "SC should fire after cooldown expires"


# ---------------------------------------------------------------------------
# TestVolumeConstraints
# ---------------------------------------------------------------------------


class TestVolumeConstraints:
    """VOL 约束测试 — 量价验证规则"""

    def test_ST_vol01_penalty(self):
        """VOL-01: ST with volume > SC volume → conf reduced by 0.2"""
        d = STDetector()
        # 基线：无 event_volumes，正常检测
        base_score = d.evaluate(
            _candle(volume=2000),
            _features(volume_ratio=0.5, body_ratio=0.3, supply_demand=0.1),
            _context(distance_to_support=0.05),
        )
        assert base_score is not None

        # 有 SC volume 且当前量超过 SC → 惩罚
        penalized = d.evaluate(
            _candle(volume=2000),
            _features(volume_ratio=0.5, body_ratio=0.3, supply_demand=0.1),
            _context(
                distance_to_support=0.05,
                event_volumes={"SC": 1500},
            ),
        )
        # 可能变为 None（conf 降到 <0.2）或者 conf 显著降低
        if penalized is not None:
            assert penalized.confidence < base_score.confidence

    def test_spring_vol05_reject(self):
        """VOL-05: Spring with volume >= SC volume → None (FAIL-SP-01)"""
        d = SpringDetector()
        # 正常 Spring（低量）
        normal = d.evaluate(
            _candle(low=90.0, close=98.0, volume=500),
            _features(supply_demand=0.2, volume_ratio=0.8),
            _context(position_in_tr=-0.05, distance_to_support=0.02),
        )
        assert normal is not None

        # Spring 量 >= SC 量 → 拒绝
        rejected = d.evaluate(
            _candle(low=90.0, close=98.0, volume=2000),
            _features(supply_demand=0.2, volume_ratio=0.8),
            _context(
                position_in_tr=-0.05,
                distance_to_support=0.02,
                event_volumes={"SC": 1500},
            ),
        )
        assert rejected is None

    def test_MSOS_requires_volume(self):
        """VOL-07: MSOS with volume_ratio < 1.5 → None"""
        d = MSOSDetector()
        # 低量 → 拒绝
        result = d.evaluate(
            _candle(high=115.0, close=113.0),
            _features(
                volume_ratio=1.2,
                supply_demand=0.5,
                effort_result=0.4,
            ),
            _context(position_in_tr=0.9),
        )
        assert result is None

        # 高量 → 通过
        result2 = d.evaluate(
            _candle(high=115.0, close=113.0),
            _features(
                volume_ratio=2.5,
                supply_demand=0.5,
                effort_result=0.4,
            ),
            _context(position_in_tr=0.9),
        )
        assert result2 is not None

    def test_ST_DIST_vol02_penalty(self):
        """VOL-02: ST_DIST with volume > BC volume → conf reduced"""
        d = STDistDetector()
        # 基线：无 event_volumes
        base = d.evaluate(
            _candle(high=112.0, close=110.0, volume=2000),
            _features(volume_ratio=0.6, supply_demand=-0.2),
            _context(position_in_tr=0.85, last_confirmed_event="AR_DIST"),
        )
        assert base is not None

        # 有 BC volume 且当前量超过 BC → 惩罚
        penalized = d.evaluate(
            _candle(high=112.0, close=110.0, volume=2000),
            _features(volume_ratio=0.6, supply_demand=-0.2),
            _context(
                position_in_tr=0.85,
                last_confirmed_event="AR_DIST",
                event_volumes={"BC": 1500},
            ),
        )
        if penalized is not None:
            assert penalized.confidence < base.confidence

    def test_MSOW_requires_volume(self):
        """VOL-09: MSOW with volume_ratio < 1.5 → None"""
        d = MSOWDetector()
        # 低量 → 拒绝
        result = d.evaluate(
            _candle(low=88.0, close=89.0),
            _features(
                volume_ratio=1.2,
                supply_demand=-0.5,
                body_ratio=0.7,
            ),
            _context(position_in_tr=0.02),
        )
        assert result is None

        # 高量 → 通过
        result2 = d.evaluate(
            _candle(low=88.0, close=89.0),
            _features(
                volume_ratio=2.0,
                supply_demand=-0.5,
                body_ratio=0.7,
            ),
            _context(position_in_tr=0.02),
        )
        assert result2 is not None
