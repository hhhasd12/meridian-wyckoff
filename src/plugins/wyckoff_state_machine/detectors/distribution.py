"""派发阶段检测器 — 9个 NodeDetector 子类

从 DistributionDetectorMixin 迁移而来，使用 BarFeatures 替代原始计算。
派发检测器是吸筹检测器的镜像：供需取反、支撑/阻力互换。
"""

from typing import Optional

from .base_detector import (
    BarFeatures,
    NodeDetector,
    NodeScore,
    StructureContext,
    make_evidence,
    make_score,
)


class PSYDetector(NodeDetector):
    """初步供应检测器 — 上涨趋势中第一次卖压出现"""

    @property
    def name(self) -> str:
        return "PSY"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        # 供应出现: supply_demand < 0
        if features.supply_demand < -0.1:
            conf += 0.3
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.3, "卖压出现")
            )
        # 放量
        if features.volume_ratio > 1.2:
            conf += 0.25
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.25, "量能放大")
            )
        # 接近阻力位
        if context.position_in_tr > 0.7:
            conf += 0.2
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.2, "接近阻力")
            )
        # 停止行为（高量小实体）
        if features.is_stopping_action:
            conf += 0.15
            evidences.append(make_evidence("stopping", 1.0, 0.15, "停止行为"))
        if conf < 0.2:
            return None
        return make_score("PSY", "PSY", min(conf, 1.0), min(conf * 0.8, 1.0), evidences)


class BCDetector(NodeDetector):
    """买入高潮检测器 — 高潮性放量冲顶，散户狂热买盘"""

    @property
    def name(self) -> str:
        return "BC"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        # 极端放量
        if features.volume_ratio > 2.0:
            conf += 0.35
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.35, "极端放量")
            )
        elif features.volume_ratio > 1.5:
            conf += 0.2
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.2, "放量")
            )
        # 宽振幅
        if features.price_range_ratio > 1.5:
            conf += 0.2
            evidences.append(
                make_evidence("range", features.price_range_ratio, 0.2, "大振幅")
            )
        # 努力结果背离（高努力低结果 = 供应吸收买盘）
        if features.spread_vs_volume_divergence > 0.3:
            conf += 0.2
            evidences.append(
                make_evidence(
                    "divergence",
                    features.spread_vs_volume_divergence,
                    0.2,
                    "努力结果背离",
                )
            )
        # 接近阻力
        if context.position_in_tr > 0.8:
            conf += 0.15
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.15, "顶部区域")
            )
        if conf < 0.3:
            return None
        return make_score("BC", "BC", min(conf, 1.0), min(conf * 0.9, 1.0), evidences)


class ARDistDetector(NodeDetector):
    """派发自动回落检测器 — BC后的自然回撤，买盘枯竭"""

    @property
    def name(self) -> str:
        return "AR_DIST"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        # 缩量下跌（买盘枯竭）
        if features.volume_ratio < 0.8:
            conf += 0.25
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.25, "缩量")
            )
        # 供应主导
        if features.supply_demand < -0.2:
            conf += 0.25
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.25, "供应主导")
            )
        # 从顶部回撤到中部
        if context.position_in_tr < 0.5:
            conf += 0.2
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.2, "回落至中下部")
            )
        # 前驱: BC
        if context.last_confirmed_event == "BC":
            conf += 0.2
            evidences.append(make_evidence("sequence", 1.0, 0.2, "BC后序"))
        if conf < 0.2:
            return None
        return make_score(
            "AR_DIST", "AR_DIST", min(conf, 1.0), min(conf * 0.8, 1.0), evidences
        )


class STDistDetector(NodeDetector):
    """派发二次测试检测器 — 反弹测试BC高点但未能突破"""

    @property
    def name(self) -> str:
        return "ST_DIST"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        # 接近阻力但未突破
        if 0.7 < context.position_in_tr < 0.95:
            conf += 0.3
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.3, "接近阻力未突破")
            )
        # 缩量（买盘乏力）
        if features.volume_ratio < 0.8:
            conf += 0.25
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.25, "缩量反弹")
            )
        # 供应信号
        if features.supply_demand < 0:
            conf += 0.2
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.2, "供应压力")
            )
        # 前驱: AR_DIST 或 BC
        if context.last_confirmed_event in ("AR_DIST", "BC"):
            conf += 0.15
            evidences.append(make_evidence("sequence", 1.0, 0.15, "AR_DIST/BC后序"))

        # VOL-02: ST_DIST 量应小于 BC 量，否则惩罚
        bc_vol = context.event_volumes.get("BC")
        if bc_vol is not None and candle["volume"] > bc_vol:
            conf -= 0.2
            evidences.append(
                make_evidence("vol_02_penalty", candle["volume"], -0.2, "量超BC")
            )

        if conf < 0.2:
            return None
        return make_score(
            "ST_DIST", "ST_DIST", min(conf, 1.0), min(conf * 0.8, 1.0), evidences
        )


class UTDetector(NodeDetector):
    """上冲测试检测器 — 突破阻力后迅速回落，假突破"""

    @property
    def name(self) -> str:
        return "UT"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        # 突破阻力后回落: position_in_tr > 1.0 表示超出TR上沿
        if context.position_in_tr > 0.95:
            conf += 0.3
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.3, "突破阻力区域")
            )
        # 小实体（缺乏跟进）
        if features.body_ratio < 0.4:
            conf += 0.2
            evidences.append(
                make_evidence("body", features.body_ratio, 0.2, "小实体无跟进")
            )
        # 缩量（缺乏跟进买盘）
        if features.volume_ratio < 0.8:
            conf += 0.2
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.2, "缩量假突破")
            )
        # 供应信号
        if features.supply_demand < -0.1:
            conf += 0.15
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.15, "供应出现")
            )
        if conf < 0.2:
            return None
        return make_score("UT", "UT", min(conf, 1.0), min(conf * 0.85, 1.0), evidences)


class UTADDetector(NodeDetector):
    """上冲后派发检测器 — C阶段强力突破阻力后回落，确认派发方向"""

    @property
    def name(self) -> str:
        return "UTAD"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        high = float(candle.get("high", 0))

        # 幅度约束: 突破高度 ≤ TR高度 10%
        sc_low = context.boundaries.get("SC_LOW")
        ar_high = context.boundaries.get("AR_HIGH")
        bc_high = context.boundaries.get("BC_HIGH")
        resistance = bc_high if bc_high is not None else ar_high
        support = sc_low
        if (
            support is not None
            and resistance is not None
            and isinstance(support, (int, float))
            and isinstance(resistance, (int, float))
        ):
            tr_height = resistance - support
            break_depth = high - resistance
            if tr_height > 0 and break_depth > tr_height * 0.10:
                return None  # 幅度超过区间10%

        # 突破阻力区域
        if context.position_in_tr > 1.0:
            conf += 0.3
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.3, "突破TR上沿")
            )
        # 放量（派发活动，与UT不同UTAD有量）
        if features.volume_ratio > 1.5:
            conf += 0.25
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.25, "放量派发")
            )
        # 供应出现
        if features.supply_demand < -0.2:
            conf += 0.2
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.2, "强供应")
            )
        # 努力结果背离
        if features.spread_vs_volume_divergence > 0.2:
            conf += 0.15
            evidences.append(
                make_evidence(
                    "divergence",
                    features.spread_vs_volume_divergence,
                    0.15,
                    "放量未涨",
                )
            )
        if conf < 0.3:
            return None
        return make_score(
            "UTAD", "UTAD", min(conf, 1.0), min(conf * 0.9, 1.0), evidences
        )


class LPSYDetector(NodeDetector):
    """最后供应点检测器 — 弱势反弹无法触及阻力，D阶段确认"""

    @property
    def name(self) -> str:
        return "LPSY"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        # 反弹高点递降（position_in_tr 明显低于前高）
        if 0.3 < context.position_in_tr < 0.7:
            conf += 0.3
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.3, "更低高点")
            )
        # 缩量（买盘枯竭）
        if features.volume_ratio < 0.7:
            conf += 0.25
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.25, "缩量反弹")
            )
        # 供应信号
        if features.supply_demand < -0.1:
            conf += 0.2
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.2, "供应压制")
            )
        # 前驱: UT/UTAD/ST_DIST
        if context.last_confirmed_event in ("UT", "UTAD", "ST_DIST", "mSOW"):
            conf += 0.15
            evidences.append(make_evidence("sequence", 1.0, 0.15, "派发后序"))

        # VOL-04: LPSY 量应小于 SOW/mSOW 量（如果存在）
        sow_vol = context.event_volumes.get("MSOW") or context.event_volumes.get("mSOW")
        if sow_vol is not None and candle["volume"] > sow_vol:
            conf -= 0.15
            evidences.append(
                make_evidence("vol_04_penalty", candle["volume"], -0.15, "量超SOW")
            )

        if conf < 0.2:
            return None
        return make_score(
            "LPSY", "LPSY", min(conf, 1.0), min(conf * 0.8, 1.0), evidences
        )


class MinorSOWDetector(NodeDetector):
    """局部弱势信号检测器 — 短暂跌破支撑，供应初现"""

    @property
    def name(self) -> str:
        return "mSOW"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        evidences = []
        conf = 0.0
        # 接近或跌破支撑
        if context.position_in_tr < 0.15:
            conf += 0.3
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.3, "接近/跌破支撑")
            )
        # 供应主导
        if features.supply_demand < -0.15:
            conf += 0.2
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.2, "供应主导")
            )
        # 温和放量（不像 MSOW 那样极端放量）
        if 1.0 < features.volume_ratio < 1.8:
            conf += 0.2
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.2, "温和放量")
            )
        # 小实体（犹豫，非决定性跌破）
        if features.body_ratio < 0.5:
            conf += 0.1
            evidences.append(
                make_evidence("body", features.body_ratio, 0.1, "小实体犹豫")
            )
        if conf < 0.2:
            return None
        return make_score(
            "mSOW", "mSOW", min(conf, 1.0), min(conf * 0.8, 1.0), evidences
        )


class MSOWDetector(NodeDetector):
    """整体弱势信号检测器 — 强力跌破支撑，确认派发完成"""

    @property
    def name(self) -> str:
        return "MSOW"

    def evaluate(
        self, candle: dict, features: BarFeatures, context: StructureContext
    ) -> Optional[NodeScore]:
        # VOL-09: MSOW 必须放量（volume_ratio > 1.5）
        if features.volume_ratio < 1.5:
            return None

        evidences = []
        conf = 0.0
        # 跌破支撑（position_in_tr < 0 表示低于TR下沿）
        if context.position_in_tr < 0.05:
            conf += 0.3
            evidences.append(
                make_evidence("position", context.position_in_tr, 0.3, "跌破支撑")
            )
        # 放量（供应猛增）
        if features.volume_ratio > 1.5:
            conf += 0.25
            evidences.append(
                make_evidence("volume", features.volume_ratio, 0.25, "放量下跌")
            )
        # 强供应
        if features.supply_demand < -0.3:
            conf += 0.2
            evidences.append(
                make_evidence("supply", features.supply_demand, 0.2, "强供应主导")
            )
        # 大实体阴线（决定性跌破）
        if features.body_ratio > 0.6:
            conf += 0.15
            evidences.append(
                make_evidence("body", features.body_ratio, 0.15, "大实体决定性")
            )
        if conf < 0.3:
            return None
        return make_score(
            "MSOW", "MSOW", min(conf, 1.0), min(conf * 0.9, 1.0), evidences
        )
