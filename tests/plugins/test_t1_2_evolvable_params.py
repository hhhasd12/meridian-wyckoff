"""T1.2 测试 — 验证22个检测器全部暴露 get_evolvable_params()

测试覆盖:
1. 所有22个检测器 get_evolvable_params() 返回非空 dict
2. 每个 ParamSpec 满足 min < max, default 在 [min, max] 范围内
3. set_params() 可以修改参数
4. 修改参数后 evaluate() 不报错
"""

import pytest
from dataclasses import fields as dataclass_fields

from src.plugins.wyckoff_state_machine.detector_registry import ParamSpec
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
from src.plugins.wyckoff_state_machine.principles.bar_features import (
    BarFeatures,
    StructureContext,
)

# 所有22个检测器类
ALL_DETECTORS = [
    # 吸筹 13
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
    # 派发 9
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


def _make_candle() -> dict:
    """创建最小化测试K线"""
    return {
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000.0,
    }


def _make_features() -> BarFeatures:
    """创建最小化 BarFeatures"""
    return BarFeatures(
        supply_demand=0.0,
        cause_effect=0.0,
        effort_result=0.0,
        volume_ratio=1.0,
        body_ratio=0.5,
        is_stopping_action=False,
        price_range_ratio=1.0,
        spread_vs_volume_divergence=0.0,
    )


def _make_context() -> StructureContext:
    """创建最小化 StructureContext"""
    return StructureContext(
        current_phase="B",
        last_confirmed_event="",
        position_in_tr=0.5,
        distance_to_support=0.1,
        distance_to_resistance=0.1,
        test_quality=0.5,
        recovery_speed=0.3,
        swing_context="sideways",
        direction_bias=0.0,
        boundaries={},
        event_volumes={},
    )


class TestAllDetectorsHaveEvolvableParams:
    """验证所有22个检测器都暴露了可进化参数"""

    @pytest.mark.parametrize("detector_cls", ALL_DETECTORS, ids=lambda c: c.__name__)
    def test_get_evolvable_params_non_empty(self, detector_cls):
        """每个检测器 get_evolvable_params() 返回非空 dict"""
        detector = detector_cls()
        params = detector.get_evolvable_params()
        assert isinstance(params, dict), f"{detector_cls.__name__} 返回类型错误"
        assert len(params) > 0, f"{detector_cls.__name__} 返回空 dict"

    @pytest.mark.parametrize("detector_cls", ALL_DETECTORS, ids=lambda c: c.__name__)
    def test_param_spec_validity(self, detector_cls):
        """每个 ParamSpec 满足 min < max, default 在范围内"""
        detector = detector_cls()
        params = detector.get_evolvable_params()
        for name, spec in params.items():
            assert isinstance(spec, ParamSpec), (
                f"{detector_cls.__name__}.{name} 不是 ParamSpec"
            )
            assert spec.min < spec.max, (
                f"{detector_cls.__name__}.{name}: min={spec.min} >= max={spec.max}"
            )
            assert spec.min <= spec.default <= spec.max, (
                f"{detector_cls.__name__}.{name}: "
                f"default={spec.default} 不在 [{spec.min}, {spec.max}] 范围内"
            )
            assert spec.min <= spec.current <= spec.max, (
                f"{detector_cls.__name__}.{name}: "
                f"current={spec.current} 不在 [{spec.min}, {spec.max}] 范围内"
            )

    @pytest.mark.parametrize("detector_cls", ALL_DETECTORS, ids=lambda c: c.__name__)
    def test_has_min_confidence_param(self, detector_cls):
        """每个检测器都应有 min_confidence 参数"""
        detector = detector_cls()
        params = detector.get_evolvable_params()
        assert "min_confidence" in params, (
            f"{detector_cls.__name__} 缺少 min_confidence 参数"
        )


class TestSetParams:
    """验证 set_params() 正确更新参数"""

    @pytest.mark.parametrize("detector_cls", ALL_DETECTORS, ids=lambda c: c.__name__)
    def test_set_params_updates_values(self, detector_cls):
        """set_params 可以修改已有参数"""
        detector = detector_cls()
        params = detector.get_evolvable_params()

        # 取第一个参数，设置为 min 和 max 的中点
        first_key = next(iter(params))
        spec = params[first_key]
        new_val = (spec.min + spec.max) / 2.0
        detector.set_params({first_key: new_val})

        # 验证 _params 已更新
        assert detector._params[first_key] == pytest.approx(new_val)

        # 再次调 get_evolvable_params，current 应该反映新值
        updated = detector.get_evolvable_params()
        assert updated[first_key].current == pytest.approx(new_val)

    @pytest.mark.parametrize("detector_cls", ALL_DETECTORS, ids=lambda c: c.__name__)
    def test_set_params_ignores_unknown_keys(self, detector_cls):
        """set_params 应忽略不存在的 key"""
        detector = detector_cls()
        original_params = dict(detector._params)
        detector.set_params({"nonexistent_key_xyz": 999.0})
        assert detector._params == original_params


class TestEvaluateAfterParamChange:
    """验证修改参数后 evaluate() 不报错"""

    @pytest.mark.parametrize("detector_cls", ALL_DETECTORS, ids=lambda c: c.__name__)
    def test_evaluate_after_set_params(self, detector_cls):
        """修改参数后 evaluate 应正常运行（不抛异常）"""
        detector = detector_cls()
        params = detector.get_evolvable_params()

        # 将所有参数设为 min 值
        min_params = {k: v.min for k, v in params.items()}
        detector.set_params(min_params)

        candle = _make_candle()
        features = _make_features()
        context = _make_context()

        # 不应抛异常（返回值可以是 None 或 NodeScore）
        result = detector.evaluate(candle, features, context)
        assert result is None or hasattr(result, "confidence")

    @pytest.mark.parametrize("detector_cls", ALL_DETECTORS, ids=lambda c: c.__name__)
    def test_evaluate_with_max_params(self, detector_cls):
        """将参数设为 max 值后 evaluate 也不报错"""
        detector = detector_cls()
        params = detector.get_evolvable_params()

        max_params = {k: v.max for k, v in params.items()}
        detector.set_params(max_params)

        candle = _make_candle()
        features = _make_features()
        context = _make_context()

        result = detector.evaluate(candle, features, context)
        assert result is None or hasattr(result, "confidence")


class TestDetectorCount:
    """验证检测器数量正确"""

    def test_total_detector_count(self):
        """应有22个检测器"""
        assert len(ALL_DETECTORS) == 22

    def test_accumulation_count(self):
        """吸筹检测器应有13个"""
        acc_detectors = ALL_DETECTORS[:13]
        assert len(acc_detectors) == 13

    def test_distribution_count(self):
        """派发检测器应有9个"""
        dist_detectors = ALL_DETECTORS[13:]
        assert len(dist_detectors) == 9
