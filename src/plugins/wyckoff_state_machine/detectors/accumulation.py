"""吸筹阶段检测器 — 13个 NodeDetector 子类

从 AccumulationDetectorMixin 迁移而来。
每个检测器使用 BarFeatures 预计算值，保持精简（15-30行）。
"""

from typing import Dict, Optional

from .base_detector import (
    BarFeatures,
    NodeDetector,
    NodeScore,
    ParamSpec,
    StructureContext,
    make_evidence,
    make_score,
)


class PSDetector(NodeDetector):
    """初步支撑检测器 — 下跌趋势中首次出现支撑"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "supply_demand_threshold": 0.0,
            "volume_threshold": 1.2,
            "effort_threshold": -0.2,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "PS"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "supply_demand_threshold": ParamSpec(
                -0.5, 0.5, 0.0, self._params["supply_demand_threshold"]
            ),
            "volume_threshold": ParamSpec(
                0.5, 3.0, 1.2, self._params["volume_threshold"]
            ),
            "effort_threshold": ParamSpec(
                -1.0, 0.0, -0.2, self._params["effort_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0

        # 供需转向需求侧（看涨反转）
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.3
            evidences.append(
                make_evidence("supply_demand", features.supply_demand, 0.3, "需求进入")
            )

        # 停止行为（高量小实体 = 卖盘被吸收）
        if features.is_stopping_action:
            conf += 0.3
            evidences.append(make_evidence("stopping", 1.0, 0.3, "停止行为"))

        # 成交量放大
        if features.volume_ratio > self._params["volume_threshold"]:
            v_score = min(0.2, (features.volume_ratio - 1.0) * 0.2)
            conf += v_score
            evidences.append(
                make_evidence("volume", features.volume_ratio, v_score, "成交量放大")
            )

        # 下跌趋势中出现（supply_demand 负值说明前期偏供应）
        if features.effort_result < self._params["effort_threshold"]:
            conf += 0.1
            evidences.append(
                make_evidence(
                    "effort_result", features.effort_result, 0.1, "努力结果背离"
                )
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "PS", min(conf, 1.0), min(conf * 0.8, 1.0), evidences
        )


class SCDetector(NodeDetector):
    """抛售高潮检测器 — 恐慌性大量抛售形成底部"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "volume_threshold": 1.5,
            "range_threshold": 1.3,
            "divergence_threshold": 0.3,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "SC"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "volume_threshold": ParamSpec(
                0.5, 5.0, 1.5, self._params["volume_threshold"]
            ),
            "range_threshold": ParamSpec(
                0.5, 3.0, 1.3, self._params["range_threshold"]
            ),
            "divergence_threshold": ParamSpec(
                0.0, 1.0, 0.3, self._params["divergence_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0

        # 核心：高成交量 + 大振幅
        if features.volume_ratio > self._params["volume_threshold"]:
            v_score = min(0.4, features.volume_ratio / 5.0)
            conf += v_score
            evidences.append(
                make_evidence(
                    "volume_spike", features.volume_ratio, v_score, "恐慌放量"
                )
            )

        # 大振幅（价格范围大于均值）
        if features.price_range_ratio > self._params["range_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence(
                    "wide_range", features.price_range_ratio, 0.2, "大振幅K线"
                )
            )

        # 停止行为加分
        if features.is_stopping_action:
            conf += 0.2
            evidences.append(make_evidence("stopping", 1.0, 0.2, "停止行为"))

        # 努力结果背离（高努力低结果 = 卖盘被吸收）
        if features.spread_vs_volume_divergence > self._params["divergence_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence(
                    "effort_divergence",
                    features.spread_vs_volume_divergence,
                    0.15,
                    "努力结果背离",
                )
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "SC", min(conf, 1.0), min(conf * 0.9, 1.0), evidences
        )


class ARDetector(NodeDetector):
    """自动反弹检测器 — SC后的反弹，成交量收缩"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "supply_demand_threshold": 0.2,
            "volume_threshold": 1.0,
            "effort_threshold": 0.2,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "AR"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "supply_demand_threshold": ParamSpec(
                0.0, 0.8, 0.2, self._params["supply_demand_threshold"]
            ),
            "volume_threshold": ParamSpec(
                0.3, 2.0, 1.0, self._params["volume_threshold"]
            ),
            "effort_threshold": ParamSpec(
                0.0, 0.8, 0.2, self._params["effort_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0

        # 阳线反弹 + 供需转向需求
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.3
            evidences.append(
                make_evidence("demand", features.supply_demand, 0.3, "需求主导反弹")
            )

        # 成交量收缩（相对于SC的放量）
        if features.volume_ratio < self._params["volume_threshold"]:
            conf += 0.25
            evidences.append(
                make_evidence("vol_shrink", features.volume_ratio, 0.25, "量能收缩")
            )

        # 位于TR下部反弹
        if context.position_in_tr < 0.5 and context.distance_to_support < 0.3:
            conf += 0.2
            evidences.append(
                make_evidence("tr_pos", context.position_in_tr, 0.2, "从TR底部反弹")
            )

        # 努力结果和谐（量缩价涨 = 需求轻松推动）
        if features.effort_result > self._params["effort_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence("effort", features.effort_result, 0.15, "努力结果和谐")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "AR", min(conf, 1.0), min(conf * 0.8, 1.0), evidences
        )


class STDetector(NodeDetector):
    """二次测试检测器 — 回调测试SC区域，量缩不破底"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "distance_threshold": 0.15,
            "volume_threshold": 0.8,
            "body_ratio_threshold": 0.4,
            "supply_demand_threshold": -0.2,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "ST"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "distance_threshold": ParamSpec(
                0.02, 0.4, 0.15, self._params["distance_threshold"]
            ),
            "volume_threshold": ParamSpec(
                0.3, 2.0, 0.8, self._params["volume_threshold"]
            ),
            "body_ratio_threshold": ParamSpec(
                0.1, 0.8, 0.4, self._params["body_ratio_threshold"]
            ),
            "supply_demand_threshold": ParamSpec(
                -0.8, 0.2, -0.2, self._params["supply_demand_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0

        # 接近支撑位（TR底部）
        if context.distance_to_support < self._params["distance_threshold"]:
            conf += 0.3
            evidences.append(
                make_evidence(
                    "near_support", context.distance_to_support, 0.3, "接近支撑"
                )
            )

        # 成交量收缩（供应减少）
        if features.volume_ratio < self._params["volume_threshold"]:
            conf += 0.25
            evidences.append(
                make_evidence("vol_dry", features.volume_ratio, 0.25, "量能萎缩")
            )

        # 小实体（犹豫不决 = 卖压不足）
        if features.body_ratio < self._params["body_ratio_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence("small_body", features.body_ratio, 0.15, "实体缩小")
            )

        # 供需接近中性或偏需求
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence("balanced", features.supply_demand, 0.15, "供需趋于平衡")
            )

        # VOL-01: ST 量应小于 SC 量，否则惩罚
        sc_vol = context.event_volumes.get("SC")
        if sc_vol is not None and candle["volume"] > sc_vol:
            conf -= 0.2
            evidences.append(
                make_evidence("vol_01_penalty", candle["volume"], -0.2, "量超SC")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "ST", min(conf, 1.0), min(conf * 0.7, 1.0), evidences
        )


class TestDetector(NodeDetector):
    """测试检测器 — 测试前支撑位，量缩反弹"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "distance_threshold": 0.1,
            "volume_threshold": 0.7,
            "test_quality_threshold": 0.5,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "TEST"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "distance_threshold": ParamSpec(
                0.02, 0.3, 0.1, self._params["distance_threshold"]
            ),
            "volume_threshold": ParamSpec(
                0.3, 2.0, 0.7, self._params["volume_threshold"]
            ),
            "test_quality_threshold": ParamSpec(
                0.1, 1.0, 0.5, self._params["test_quality_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0

        # 接近支撑位
        if context.distance_to_support < self._params["distance_threshold"]:
            conf += 0.3
            evidences.append(
                make_evidence(
                    "test_support", context.distance_to_support, 0.3, "测试支撑"
                )
            )

        # 成交量收缩（供应枯竭）
        if features.volume_ratio < self._params["volume_threshold"]:
            conf += 0.25
            evidences.append(
                make_evidence("supply_dry", features.volume_ratio, 0.25, "供应枯竭")
            )

        # 测试质量
        if context.test_quality > self._params["test_quality_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("quality", context.test_quality, 0.2, "测试质量良好")
            )

        # 供需偏需求（反弹）
        if features.supply_demand > 0:
            conf += 0.15
            evidences.append(
                make_evidence("demand_bounce", features.supply_demand, 0.15, "需求反弹")
            )

        # VOL-06: 测试量应逐次递减（与前次测试量比较）
        prev_test_vol = context.event_volumes.get("TEST")
        if prev_test_vol is not None and candle["volume"] > prev_test_vol:
            conf -= 0.15
            evidences.append(
                make_evidence("vol_06_penalty", candle["volume"], -0.15, "量超前次测试")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "TEST", min(conf, 1.0), min(conf * 0.7, 1.0), evidences
        )


class UTADetector(NodeDetector):
    """上冲行为检测器 — 上冲突破阻力后回落（假突破）"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "position_threshold": 0.85,
            "volume_threshold": 0.8,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "UTA"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "position_threshold": ParamSpec(
                0.6, 1.0, 0.85, self._params["position_threshold"]
            ),
            "volume_threshold": ParamSpec(
                0.3, 2.0, 0.8, self._params["volume_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        close = float(candle.get("close", 0))
        high = float(candle.get("high", 0))

        # 位于TR上部
        if context.position_in_tr > self._params["position_threshold"]:
            conf += 0.3
            evidences.append(
                make_evidence("high_pos", context.position_in_tr, 0.3, "TR上部")
            )

        # 接近阻力位
        if context.distance_to_resistance < 0.05 and high > close:
            conf += 0.25
            evidences.append(
                make_evidence(
                    "resist_reject", context.distance_to_resistance, 0.25, "阻力拒绝"
                )
            )

        # 成交量较低（缺乏跟进买盘）
        if features.volume_ratio < self._params["volume_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("weak_vol", features.volume_ratio, 0.2, "跟进不足")
            )

        # 供需偏供应（回落）
        if features.supply_demand < 0:
            conf += 0.15
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.15, "供应压制")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "UTA", min(conf, 1.0), min(conf * 0.7, 1.0), evidences
        )


class SpringDetector(NodeDetector):
    """弹簧检测器 — 跌破支撑后快速反弹（假突破洗盘）"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "amplitude_ratio": 0.10,
            "volume_threshold": 1.0,
            "supply_demand_threshold": 0.1,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "SPRING"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "amplitude_ratio": ParamSpec(
                0.02, 0.25, 0.10, self._params["amplitude_ratio"]
            ),
            "volume_threshold": ParamSpec(
                0.3, 3.0, 1.0, self._params["volume_threshold"]
            ),
            "supply_demand_threshold": ParamSpec(
                -0.3, 0.5, 0.1, self._params["supply_demand_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        low = float(candle.get("low", 0))
        close = float(candle.get("close", 0))

        # VOL-05: Spring 量不能 >= SC 量（高量 Spring = 1号弹簧，高风险）
        sc_vol = context.event_volumes.get("SC")
        if sc_vol is not None and candle["volume"] >= sc_vol:
            return None  # FAIL-SP-01

        # 幅度约束: 跌破深度 ≤ TR高度 amplitude_ratio
        sc_low = context.boundaries.get("SC_LOW")
        ar_high = context.boundaries.get("AR_HIGH")
        if (
            sc_low is not None
            and ar_high is not None
            and isinstance(sc_low, (int, float))
            and isinstance(ar_high, (int, float))
        ):
            tr_height = ar_high - sc_low
            break_depth = sc_low - low
            if (
                tr_height > 0
                and break_depth > tr_height * self._params["amplitude_ratio"]
            ):
                return None  # 幅度超过区间比例

        # 核心：位于TR下方（跌破支撑）且收盘回到TR内
        if context.position_in_tr < 0.0 and close > low:
            conf += 0.35
            evidences.append(
                make_evidence(
                    "spring_action", context.position_in_tr, 0.35, "跌破后反弹"
                )
            )

        # 接近支撑位（即使没跌破，非常接近也有意义）
        if context.distance_to_support < 0.05:
            conf += 0.2
            evidences.append(
                make_evidence(
                    "at_support", context.distance_to_support, 0.2, "贴近支撑"
                )
            )

        # 成交量较低（缺乏跟进卖盘）
        if features.volume_ratio < self._params["volume_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("low_vol", features.volume_ratio, 0.2, "跟进卖盘不足")
            )

        # 供需转向需求
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence("demand_return", features.supply_demand, 0.15, "需求回归")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name,
            "SPRING",
            min(conf, 1.0),
            min(conf * 0.9, 1.0),
            evidences,
            cooldown_bars=3,
        )


class SODetector(NodeDetector):
    """震仓检测器 — 快速跌破支撑引发恐慌后反弹"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "position_threshold": 0.1,
            "volume_threshold": 1.5,
            "divergence_threshold": 0.2,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "SO"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "position_threshold": ParamSpec(
                0.0, 0.4, 0.1, self._params["position_threshold"]
            ),
            "volume_threshold": ParamSpec(
                0.5, 5.0, 1.5, self._params["volume_threshold"]
            ),
            "divergence_threshold": ParamSpec(
                0.0, 0.8, 0.2, self._params["divergence_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0

        # 位于TR下部或下方
        if context.position_in_tr < self._params["position_threshold"]:
            conf += 0.25
            evidences.append(
                make_evidence("low_pos", context.position_in_tr, 0.25, "TR底部区域")
            )

        # 成交量放大（恐慌性抛售）
        if features.volume_ratio > self._params["volume_threshold"]:
            v_s = min(0.3, features.volume_ratio / 5.0)
            conf += v_s
            evidences.append(
                make_evidence("panic_vol", features.volume_ratio, v_s, "恐慌放量")
            )

        # 停止行为
        if features.is_stopping_action:
            conf += 0.2
            evidences.append(make_evidence("stopping", 1.0, 0.2, "停止行为"))

        # 努力结果背离
        if features.spread_vs_volume_divergence > self._params["divergence_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence(
                    "divergence",
                    features.spread_vs_volume_divergence,
                    0.15,
                    "高努力低结果",
                )
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name,
            "SO",
            min(conf, 1.0),
            min(conf * 0.8, 1.0),
            evidences,
            cooldown_bars=3,
        )


class LPSDetector(NodeDetector):
    """最后支撑点检测器 — 更高低点 + 量缩 = 供应枯竭"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "position_low": 0.1,
            "position_high": 0.4,
            "volume_threshold": 0.7,
            "supply_demand_threshold": 0.1,
            "recovery_threshold": 0.3,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "LPS"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "position_low": ParamSpec(0.0, 0.3, 0.1, self._params["position_low"]),
            "position_high": ParamSpec(0.2, 0.6, 0.4, self._params["position_high"]),
            "volume_threshold": ParamSpec(
                0.3, 1.5, 0.7, self._params["volume_threshold"]
            ),
            "supply_demand_threshold": ParamSpec(
                -0.2, 0.5, 0.1, self._params["supply_demand_threshold"]
            ),
            "recovery_threshold": ParamSpec(
                0.1, 0.8, 0.3, self._params["recovery_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0

        # 在TR内偏下但高于前期低点（更高低点）
        if (
            self._params["position_low"]
            < context.position_in_tr
            < self._params["position_high"]
        ):
            conf += 0.3
            evidences.append(
                make_evidence("higher_low", context.position_in_tr, 0.3, "更高低点")
            )

        # 成交量收缩（供应枯竭）
        if features.volume_ratio < self._params["volume_threshold"]:
            conf += 0.25
            evidences.append(
                make_evidence("vol_dry", features.volume_ratio, 0.25, "供应枯竭")
            )

        # 供需偏需求
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("demand", features.supply_demand, 0.2, "需求主导")
            )

        # 恢复速度快（反弹有力）
        if context.recovery_speed > self._params["recovery_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence("recovery", context.recovery_speed, 0.15, "反弹有力")
            )

        # VOL-03: LPS 量应小于 Spring 量，否则惩罚
        spring_vol = context.event_volumes.get("SPRING")
        if spring_vol is not None and candle["volume"] > spring_vol:
            conf -= 0.15
            evidences.append(
                make_evidence("vol_03_penalty", candle["volume"], -0.15, "量超SPRING")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "LPS", min(conf, 1.0), min(conf * 0.8, 1.0), evidences
        )


class MinorSOSDetector(NodeDetector):
    """局部强势信号检测器 — 小幅突破近期阻力，量温和放大"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "position_threshold": 0.5,
            "volume_low": 1.0,
            "volume_high": 2.0,
            "supply_demand_threshold": 0.2,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "mSOS"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "position_threshold": ParamSpec(
                0.3, 0.8, 0.5, self._params["position_threshold"]
            ),
            "volume_low": ParamSpec(0.5, 2.0, 1.0, self._params["volume_low"]),
            "volume_high": ParamSpec(1.5, 4.0, 2.0, self._params["volume_high"]),
            "supply_demand_threshold": ParamSpec(
                0.0, 0.6, 0.2, self._params["supply_demand_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        close = float(candle.get("close", 0))
        open_p = float(candle.get("open", 0))

        # 阳线
        if close > open_p:
            conf += 0.2
            evidences.append(make_evidence("bullish", close - open_p, 0.2, "阳线"))

        # 位于TR中上部
        if context.position_in_tr > self._params["position_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("upper_tr", context.position_in_tr, 0.2, "TR中上部")
            )

        # 成交量温和放大
        if (
            self._params["volume_low"]
            < features.volume_ratio
            < self._params["volume_high"]
        ):
            conf += 0.2
            evidences.append(
                make_evidence("mild_vol", features.volume_ratio, 0.2, "温和放量")
            )

        # 供需偏需求
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("demand", features.supply_demand, 0.2, "需求偏强")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "mSOS", min(conf, 1.0), min(conf * 0.7, 1.0), evidences
        )


class MSOSDetector(NodeDetector):
    """整体强势信号检测器 — 大幅突破关键阻力，量显著放大"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "volume_gate": 1.5,
            "position_threshold": 0.8,
            "supply_demand_threshold": 0.4,
            "effort_threshold": 0.3,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "MSOS"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "volume_gate": ParamSpec(0.8, 3.0, 1.5, self._params["volume_gate"]),
            "position_threshold": ParamSpec(
                0.5, 1.0, 0.8, self._params["position_threshold"]
            ),
            "supply_demand_threshold": ParamSpec(
                0.1, 0.8, 0.4, self._params["supply_demand_threshold"]
            ),
            "effort_threshold": ParamSpec(
                0.1, 0.8, 0.3, self._params["effort_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        # VOL-07: MSOS 必须放量（volume_ratio > volume_gate）
        if features.volume_ratio < self._params["volume_gate"]:
            return None

        evidences = []
        conf = 0.0

        # 位于TR上部或上方
        if context.position_in_tr > self._params["position_threshold"]:
            conf += 0.3
            evidences.append(
                make_evidence("high_pos", context.position_in_tr, 0.3, "TR上部突破")
            )

        # 成交量显著放大
        if features.volume_ratio > self._params["volume_gate"]:
            v_s = min(0.3, features.volume_ratio / 5.0)
            conf += v_s
            evidences.append(
                make_evidence("strong_vol", features.volume_ratio, v_s, "显著放量")
            )

        # 供需强烈偏需求
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("strong_demand", features.supply_demand, 0.2, "强需求")
            )

        # 努力结果和谐
        if features.effort_result > self._params["effort_threshold"]:
            conf += 0.15
            evidences.append(
                make_evidence(
                    "effort_harmony", features.effort_result, 0.15, "量价和谐"
                )
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "MSOS", min(conf, 1.0), min(conf * 0.9, 1.0), evidences
        )


class JOCDetector(NodeDetector):
    """突破溪流检测器 — 突破关键阻力，量显著放大"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "volume_gate": 1.5,
            "position_threshold": 1.0,
            "supply_demand_threshold": 0.3,
            "effort_threshold": 0.3,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "JOC"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "volume_gate": ParamSpec(0.8, 3.0, 1.5, self._params["volume_gate"]),
            "position_threshold": ParamSpec(
                0.7, 1.5, 1.0, self._params["position_threshold"]
            ),
            "supply_demand_threshold": ParamSpec(
                0.1, 0.8, 0.3, self._params["supply_demand_threshold"]
            ),
            "effort_threshold": ParamSpec(
                0.1, 0.8, 0.3, self._params["effort_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        # VOL-08: JOC 必须放量（volume_ratio > volume_gate）
        if features.volume_ratio < self._params["volume_gate"]:
            return None

        evidences = []
        conf = 0.0

        # 核心：突破TR上沿
        if context.position_in_tr > self._params["position_threshold"]:
            conf += 0.35
            evidences.append(
                make_evidence("breakout", context.position_in_tr, 0.35, "突破TR上沿")
            )

        # 成交量显著放大
        if features.volume_ratio > self._params["volume_gate"]:
            v_s = min(0.3, features.volume_ratio / 4.0)
            conf += v_s
            evidences.append(
                make_evidence("vol_surge", features.volume_ratio, v_s, "突破放量")
            )

        # 强需求
        if features.supply_demand > self._params["supply_demand_threshold"]:
            conf += 0.2
            evidences.append(
                make_evidence("demand_surge", features.supply_demand, 0.2, "需求激增")
            )

        # 努力结果和谐（量价配合）
        if features.effort_result > self._params["effort_threshold"]:
            conf += 0.1
            evidences.append(
                make_evidence("effort_ok", features.effort_result, 0.1, "量价和谐")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "JOC", min(conf, 1.0), min(conf * 0.9, 1.0), evidences
        )


class BUDetector(NodeDetector):
    """回踩确认检测器 — 回踩突破位，量缩反弹确认"""

    def __init__(self) -> None:
        super().__init__()
        self._params = {
            "position_low": 0.9,
            "position_high": 1.1,
            "volume_threshold": 0.8,
            "min_confidence": 0.2,
        }

    @property
    def name(self) -> str:
        return "BU"

    def get_evolvable_params(self) -> Dict[str, ParamSpec]:
        return {
            "position_low": ParamSpec(0.6, 1.0, 0.9, self._params["position_low"]),
            "position_high": ParamSpec(0.9, 1.3, 1.1, self._params["position_high"]),
            "volume_threshold": ParamSpec(
                0.3, 1.5, 0.8, self._params["volume_threshold"]
            ),
            "min_confidence": ParamSpec(0.1, 0.5, 0.2, self._params["min_confidence"]),
        }

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        close = float(candle.get("close", 0))
        open_p = float(candle.get("open", 0))

        # 接近阻力转支撑（TR上沿附近）
        if (
            self._params["position_low"]
            < context.position_in_tr
            < self._params["position_high"]
        ):
            conf += 0.3
            evidences.append(
                make_evidence(
                    "pullback_zone", context.position_in_tr, 0.3, "回踩突破区域"
                )
            )

        # 成交量收缩
        if features.volume_ratio < self._params["volume_threshold"]:
            conf += 0.25
            evidences.append(
                make_evidence("low_vol", features.volume_ratio, 0.25, "回踩缩量")
            )

        # 阳线反弹（收盘 > 开盘）
        if close > open_p:
            conf += 0.2
            evidences.append(make_evidence("bounce", close - open_p, 0.2, "反弹阳线"))

        # 供需偏需求
        if features.supply_demand > 0:
            conf += 0.15
            evidences.append(
                make_evidence("demand_hold", features.supply_demand, 0.15, "需求承接")
            )

        if conf < self._params["min_confidence"]:
            return None
        return make_score(
            self.name, "BU", min(conf, 1.0), min(conf * 0.7, 1.0), evidences
        )


__all__ = [
    "PSDetector",
    "SCDetector",
    "ARDetector",
    "STDetector",
    "TestDetector",
    "UTADetector",
    "SpringDetector",
    "SODetector",
    "LPSDetector",
    "MinorSOSDetector",
    "MSOSDetector",
    "JOCDetector",
    "BUDetector",
]
