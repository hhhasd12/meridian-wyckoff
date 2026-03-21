"""
威科夫状态机 - 派发检测 Mixin

包含派发阶段的检测方法：
PSY, BC, AR_DIST, ST_DIST, UT, UTAD, LPSY, mSOW, MSOW

每个 detect_* 方法返回 dict[str, Any]，包含 confidence, intensity, evidences。

从 wyckoff_state_machine_legacy.py 拆分而来。
"""

import logging
from typing import Any, TYPE_CHECKING

import pandas as pd

from src.kernel.types import StateEvidence

if TYPE_CHECKING:
    from src.kernel.types import StateTransition

logger = logging.getLogger(__name__)


class DistributionDetectorMixin:
    """派发阶段检测 Mixin

    提供派发节点的检测方法，通过多继承混入 WyckoffStateMachine。
    """

    # 类型存根 — 实际属性由 StateMachineCore.__init__ 创建，
    # 此处仅为 Pyright 提供类型信息。
    if TYPE_CHECKING:
        critical_price_levels: dict[str, float]
        state_history: list[StateTransition]

    def detect_psy(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测初步供应

        PSY（初步供应）特征：
        1. 价格上涨至阻力位遇阻
        2. 成交量放大（供应进入）
        3. 可能出现上影线或阴线（供应压力）
        4. 通常出现在上涨趋势后，派发阶段开始

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否在阻力位出现供应迹象
        supply_detected = False
        # 获取关键阻力位（交易区间上沿、前期高点）
        tr_resistance = context.get("tr_resistance")
        previous_highs = [level for level in [tr_resistance] if level is not None]

        if previous_highs:
            resistance_level = max(previous_highs)
            # 价格接近阻力位（最高价达到阻力位附近）
            if high >= resistance_level * 0.98:
                # 检查是否有供应迹象（上影线长、阴线）
                upper_shadow = high - max(open_price, close)
                body_size = abs(close - open_price)
                if body_size > 0:
                    shadow_ratio = upper_shadow / body_size
                    # 长上影线或阴线表示供应
                    if shadow_ratio > 1.5 or close < open_price:
                        supply_detected = True

        price_score = 0.9 if supply_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"PSY价格行为评分: {price_score:.2f} (供应检测: {supply_detected})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # PSY成交量应放大（供应进入）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1.5倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"PSY成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # PSY通常在上涨趋势后出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["UPTREND", "BULLISH", "DISTRIBUTION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3

        # 检查前驱状态（如果有状态历史）
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["BU", "JOC"]:
                regime_score = min(1.0, regime_score + 0.2)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"PSY市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.3 + regime_score * 0.1

        # 记录关键价格水平
        if supply_detected and overall_confidence >= 0.6:
            self.critical_price_levels["PSY_HIGH"] = high

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_bc(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测买入高潮

        BC（买入高潮）特征：
        1. 价格大幅上涨至新高（高潮性买盘）
        2. 成交量极高（散户狂热）
        3. 长上影线或反转形态（供应突然出现）
        4. 通常出现在派发初期，PSY之后

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否出现高潮性上涨和反转迹象
        climax_detected = False
        # 计算价格范围和影线
        abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        min(open_price, close) - low
        total_range = high - low

        if total_range > 0:
            # 长上影线比例（供应迹象）
            upper_shadow_ratio = upper_shadow / total_range
            # 价格创新高（相对于上下文）
            price_high_context = context.get("price_high_20", high * 0.9)
            if high >= price_high_context:
                # 反转特征：长上影线或收盘接近最低价
                if upper_shadow_ratio > 0.3 or close < open_price * 0.99:
                    climax_detected = True
                    # 记录BC高点和低点
                    self.critical_price_levels["BC_HIGH"] = high
                    self.critical_price_levels["BC_LOW"] = low

        price_score = 0.9 if climax_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"BC价格行为评分: {price_score:.2f} (高潮检测: {climax_detected})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # BC成交量应极高（狂热买盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于2倍）
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"BC成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # BC通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "UPTREND", "BULLISH"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "PSY":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"BC市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.4 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_ar_dist(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """检测派发阶段自动回落

        AR_DIST（自动回落）特征：
        1. 价格从BC高点快速回落
        2. 成交量收缩（买盘枯竭）
        3. 回落幅度适中（20%-50%回撤）
        4. 通常出现在BC之后，ST_DIST之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否从BC高点回落
        ar_detected = False
        # 获取BC高点
        bc_high = self.critical_price_levels.get("BC_HIGH")

        if bc_high:
            # 计算回落幅度
            decline_height = bc_high - low
            bc_range = context.get("bc_range", high - low)  # BC价格范围
            if bc_range > 0:
                decline_ratio = decline_height / bc_range
                # AR回落幅度通常在20%-50%之间
                optimal_decline_min = 0.2
                optimal_decline_max = 0.5

                if optimal_decline_min <= decline_ratio <= optimal_decline_max:
                    ar_detected = True

        price_score = 0.9 if ar_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"AR_DIST价格行为评分: {price_score:.2f} (自动回落检测: {ar_detected})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # AR_DIST成交量应收缩（买盘枯竭）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"AR_DIST成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # AR_DIST通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "BC":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"AR_DIST市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        # 记录关键价格水平
        if ar_detected and overall_confidence >= 0.6:
            self.critical_price_levels["AR_DIST_LOW"] = low

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_st_dist(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """检测派发阶段二次测试

        ST_DIST（二次测试）特征：
        1. 价格反弹至BC或AR_DIST高点附近但未能突破
        2. 成交量收缩（买盘乏力）
        3. 可能形成上影线或阴线（供应压力）
        4. 通常出现在AR_DIST之后，UT之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否测试前期高点但失败
        st_dist_detected = False
        # 获取BC高点和AR_DIST高点
        bc_high = self.critical_price_levels.get("BC_HIGH")
        ar_dist_high = context.get("ar_dist_high")
        resistance_levels = [
            level for level in [bc_high, ar_dist_high] if level is not None
        ]

        if resistance_levels:
            resistance_level = max(resistance_levels)
            # 价格接近阻力位但未突破（最高价接近阻力位）
            if abs(high - resistance_level) / resistance_level < 0.02:  # 2%以内
                # 收盘价低于阻力位（测试失败）
                if close < resistance_level:
                    st_dist_detected = True

        price_score = 0.9 if st_dist_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"ST_DIST价格行为评分: {price_score:.2f} (二次测试检测: {st_dist_detected})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # ST_DIST成交量应收缩（买盘乏力）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"ST_DIST成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # ST_DIST通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["BC", "AR_DIST"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"ST_DIST市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_ut(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测上冲测试

        UT（上冲测试）特征：
        1. 价格上冲突破前期高点（如BC高点）但未能站稳
        2. 收盘价回落至高点下方（假突破）
        3. 成交量较低（缺乏跟进买盘）
        4. 通常出现在ST_DIST之后，UTAD之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否上冲突破但回落
        upthrust_detected = False
        # 获取BC高点或前期阻力位
        bc_high = self.critical_price_levels.get("BC_HIGH")
        resistance_levels = [level for level in [bc_high] if level is not None]

        if resistance_levels:
            resistance_level = max(resistance_levels)
            # 检查是否上冲突破（最高价高于阻力位）
            if high > resistance_level:
                # 检查是否回落（收盘价低于阻力位）
                if close < resistance_level:
                    upthrust_detected = True

        price_score = 0.9 if upthrust_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"UT价格行为评分: {price_score:.2f} (上冲检测: {upthrust_detected})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # UT成交量应较低（缺乏跟进买盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量越低，置信度越高（小于1倍平均成交量）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"UT成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # UT通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "ST_DIST":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"UT市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_utad(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测上冲后的派发

        UTAD（上冲后的派发）特征：
        1. 价格上冲突破后出现派发迹象（供应增加）
        2. 成交量放大（派发活动）
        3. 价格未能维持高位，收盘价接近低点
        4. 通常出现在UT之后，LPSY之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否上冲后派发（长上影线或阴线）
        utad_detected = False
        # 计算上影线比例
        upper_shadow = high - max(open_price, close)
        abs(close - open_price)
        total_range = high - low

        if total_range > 0:
            upper_shadow_ratio = upper_shadow / total_range
            # 长上影线或阴线表示派发
            if upper_shadow_ratio > 0.3 or close < open_price:
                utad_detected = True

        price_score = 0.9 if utad_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"UTAD价格行为评分: {price_score:.2f} (上冲后派发检测: {utad_detected})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # UTAD成交量应放大（派发活动）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1.5倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"UTAD成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # UTAD通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "UT":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"UTAD市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.4 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_lpsy(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测最后供应点

        LPSY（最后供应点）特征：
        1. 价格形成更低的高点（相对于BC或UT高点）
        2. 成交量收缩（买盘枯竭）
        3. 价格下跌迹象（供应进入）
        4. 通常出现在UT或UTAD之后

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否形成更低的高点
        lower_high_detected = False
        # 获取前期高点（BC高点、UT高点）
        bc_high = self.critical_price_levels.get("BC_HIGH")
        ut_high = context.get("ut_high")
        previous_highs = [level for level in [bc_high, ut_high] if level is not None]

        if previous_highs:
            highest_previous = max(previous_highs)
            # 当前高点低于前期高点（形成更低的高点）
            if high < highest_previous:
                lower_high_detected = True

        # 检查是否为阴线或上影线较长（供应压力）
        is_bearish = close < open_price
        upper_shadow = high - max(open_price, close)
        total_range = high - low
        upper_shadow_ratio = upper_shadow / total_range if total_range > 0 else 0.0

        bearish_score = 0.7 if is_bearish or upper_shadow_ratio > 0.3 else 0.3

        price_score = 0.9 if lower_high_detected else 0.3
        price_score = price_score * 0.7 + bearish_score * 0.3  # 结合高低点和K线形态
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"LPSY价格行为评分: {price_score:.2f} (更低高点: {lower_high_detected}, 看跌: {is_bearish})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # LPSY成交量应收缩（买盘枯竭）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"LPSY成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # LPSY通常在派发后期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4  # 上涨趋势中LPSY可能性较低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["UT", "UTAD", "ST_DIST"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"LPSY市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.3 + regime_score * 0.2

        # 记录关键价格水平
        if overall_confidence >= 0.6:
            self.critical_price_levels["LPSY_HIGH"] = high

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_msow(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测整体弱势

        MSOW（整体弱势）特征：
        1. 价格创新低或接近前期低点
        2. 成交量放大（供应增加）
        3. 价格下跌延续（需求薄弱）
        4. 通常出现在LPSY或mSOW之后，下跌趋势开始前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否创新低或接近前期低点
        weakness_detected = False
        # 获取前期低点（BC低点、AR_DIST低点等）
        bc_low = self.critical_price_levels.get("BC_LOW")
        ar_dist_low = context.get("ar_dist_low")
        previous_lows = [level for level in [bc_low, ar_dist_low] if level is not None]

        if previous_lows:
            lowest_previous = min(previous_lows)
            # 当前低点接近或低于前期低点
            if low <= lowest_previous * 1.02:  # 至少达到98% (允许2%误差)
                weakness_detected = True

        # 检查是否为阴线或下影线较短（弱势特征）
        is_bearish = close < open_price
        lower_shadow = min(open_price, close) - low
        total_range = high - low
        lower_shadow_ratio = lower_shadow / total_range if total_range > 0 else 0.0

        # 弱势特征：阴线且下影线短（缺乏买盘支撑）
        weakness_score = 0.8 if is_bearish and lower_shadow_ratio < 0.2 else 0.3

        price_score = 0.9 if weakness_detected else 0.3
        price_score = price_score * 0.7 + weakness_score * 0.3  # 结合低点和K线形态
        confidence_factors.append(("price_action", price_score, 0.50))
        evidences.append(
            StateEvidence(
                evidence_type="price_action",
                value=price_score,
                confidence=price_score,
                weight=0.7,
                description=f"MSOW价格行为评分: {price_score:.2f} (弱势检测: {weakness_detected}, 看跌: {is_bearish})",
            )
        )

        # 2. 成交量分析（权重：30%）
        # MSOW成交量应放大（供应增加）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        evidences.append(
            StateEvidence(
                evidence_type="volume_ratio",
                value=volume_ratio,
                confidence=volume_score,
                weight=0.8,
                description=f"MSOW成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
            )
        )

        # 3. 市场上下文分析（权重：20%）
        # MSOW通常在派发末期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "DOWNTREND"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.2  # 上涨趋势中MSOW可能性很低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["LPSY", "mSOW"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))
        evidences.append(
            StateEvidence(
                evidence_type="market_context",
                value=regime_score,
                confidence=regime_score,
                weight=0.5,
                description=f"MSOW市场上下文评分: {regime_score:.2f} (体制: {market_regime})",
            )
        )

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.3 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_minor_sow(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """SM-C1: 检测局部弱势信号（minor Sign of Weakness）

        与 MSOW（整体弱势）的区别：
        - mSOW 关注局部跌破：价格跌破近期支撑但幅度较小，成交量温和放大
        - MSOW 关注整体跌破：价格大幅跌破关键支撑（如 AR 低点），成交量显著放大

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典，包含置信度、强度和证据列表
        """
        evidences: list[StateEvidence] = []
        confidence_factors: list[float] = []

        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        close = float(candle["close"])
        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        volume = float(candle["volume"])

        vol_mean = context.get("volume_mean", context.get("avg_volume_20", volume))
        vol_ratio = volume / vol_mean if vol_mean > 0 else 1.0

        # 获取近期低点作为局部支撑
        recent_low = context.get("recent_low", low)

        # 条件1：阴线（收盘 < 开盘）
        is_bearish = close < open_price
        if is_bearish:
            confidence_factors.append(0.3)
            evidences.append(
                StateEvidence(
                    evidence_type="price_action",
                    value=0.3,
                    confidence=0.3,
                    weight=0.6,
                    description="mSOW阴线确认: 收盘价低于开盘价",
                )
            )

        # 条件2：价格接近或跌破近期低点（局部跌破）
        if recent_low > 0:
            proximity = (recent_low - close) / recent_low if recent_low != 0 else 0
            if proximity > -0.01:  # 接近或跌破近期低点1%以内
                prox_score = min(0.3, max(0.1, proximity * 10))
                confidence_factors.append(0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="price_action",
                        value=proximity,
                        confidence=prox_score,
                        weight=0.7,
                        description=f"mSOW接近/跌破近期低点 proximity={proximity:.4f}",
                    )
                )

        # 条件3：成交量温和放大
        if vol_ratio > 1.0:
            vol_score = min(0.3, (vol_ratio - 1.0) * 0.3)
            confidence_factors.append(vol_score)
            evidences.append(
                StateEvidence(
                    evidence_type="volume_ratio",
                    value=vol_ratio,
                    confidence=vol_score,
                    weight=0.8,
                    description=f"mSOW成交量温和放大 vol_ratio={vol_ratio:.2f}",
                )
            )

        # 条件4：前驱状态检查
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["UT", "UTAD", "ST_DIST", "LPSY"]:
                confidence_factors.append(0.2)
                evidences.append(
                    StateEvidence(
                        evidence_type="market_context",
                        value=0.2,
                        confidence=0.2,
                        weight=0.5,
                        description=f"mSOW前驱状态支持: {last_state}",
                    )
                )

        confidence = min(1.0, sum(confidence_factors))

        return {
            "confidence": confidence,
            "intensity": vol_ratio,
            "evidences": evidences,
        }
