"""
威科夫状态机 - 吸筹检测 Mixin

包含吸筹阶段的检测方法：
PS, SC, AR, ST, TEST, UTA, SPRING, SO, LPS, mSOS, MSOS, JOC, BU

每个 detect_* 方法返回 dict[str, Any]，包含 confidence, intensity, evidences。
辅助方法 _analyze_* 提供细粒度的证据分析。

从 wyckoff_state_machine_legacy.py 拆分而来。
"""

import logging
from typing import Any, Optional, TYPE_CHECKING

import pandas as pd

from src.kernel.types import StateEvidence

if TYPE_CHECKING:
    from src.kernel.types import StateTransition

logger = logging.getLogger(__name__)


class AccumulationDetectorMixin:
    """吸筹阶段检测 Mixin

    提供吸筹节点的检测方法，通过多继承混入 WyckoffStateMachine。
    """

    # 类型存根 — 实际属性由 StateMachineCore.__init__ 创建，
    # 此处仅为 Pyright 提供类型信息。
    if TYPE_CHECKING:
        critical_price_levels: dict[str, float]
        state_history: list[StateTransition]

    # ===== 状态检测方法（占位符，需要后续实现） =====

    # ===== SC检测辅助方法 =====

    def _analyze_volume_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析成交量特征以检测SC

        SC成交量特征：
        1. 成交量显著高于平均水平（恐慌性抛售）
        2. 可能伴随成交量尖峰

        Returns:
            成交量证据，或None（如果无法分析）
        """
        if "volume" not in candle:
            return None

        volume = float(candle["volume"])

        # 获取历史成交量上下文
        avg_volume = context.get("avg_volume_20", volume * 1.5)  # 默认值
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

        # 计算成交量置信度
        confidence = min(1.0, volume_ratio / 3.0)  # 3倍成交量达到最大置信度

        return StateEvidence(
            evidence_type="volume_ratio",
            value=volume_ratio,
            confidence=confidence,
            weight=0.8,  # 成交量在SC检测中权重较高
            description=f"成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
        )

    def _analyze_price_action_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析价格行为特征以检测SC

        SC价格特征：
        1. 长阴线或长下影线
        2. 大幅下跌
        3. 可能的针形K线

        Returns:
            价格行为证据，或None（如果无法分析）
        """
        required_fields = ["open", "high", "low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # 1. 计算价格变动幅度
        price_range = high - low
        if price_range == 0:
            return None

        # 计算下跌幅度（如果是阴线）
        is_bearish = close < open_price
        bearish_strength = (open_price - close) / price_range if is_bearish else 0.0

        # 2. 计算下影线比例（针形特征）
        lower_shadow_ratio = (
            (min(open_price, close) - low) / price_range if price_range > 0 else 0.0
        )

        # 3. 计算整体波动率（相对于ATR）
        atr = context.get("atr_14", price_range * 2)  # 默认值
        volatility_ratio = price_range / atr if atr > 0 else 1.0

        # 综合评分：SC通常有较强的下跌和长下影线
        price_score = (
            bearish_strength * 0.4 + lower_shadow_ratio * 0.4 + volatility_ratio * 0.2
        )

        return StateEvidence(
            evidence_type="price_action",
            value=price_score,
            confidence=min(1.0, price_score * 1.5),  # 调整置信度范围
            weight=0.7,
            description=f"价格行为评分: {price_score:.2f} (下跌强度: {bearish_strength:.2f}, 下影线: {lower_shadow_ratio:.2f}, 波动率: {volatility_ratio:.2f}x)",
        )

    def _analyze_context_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析市场上下文以检测SC

        SC上下文特征：
        1. 出现在下跌趋势后
        2. 可能接近支撑位
        3. 市场体制可能是下跌或盘整

        Returns:
            上下文证据，或None（如果无法分析）
        """
        # 检查市场体制
        market_regime = context.get("market_regime", "UNKNOWN")

        # SC通常在下跌趋势或盘整底部出现
        regime_score = 0.5  # 默认

        if market_regime in ["DOWNTREND", "BEARISH", "ACCUMULATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.2

        # 检查是否接近支撑位
        support_level = context.get("support_level")
        current_price = float(candle["close"])

        support_score = 0.5
        if support_level is not None:
            distance_pct = abs(current_price - support_level) / support_level * 100
            if distance_pct < 2.0:  # 接近支撑位
                support_score = 0.8

        # 综合上下文评分
        context_score = regime_score * 0.6 + support_score * 0.4

        return StateEvidence(
            evidence_type="market_context",
            value=context_score,
            confidence=context_score,
            weight=0.5,
            description=f"市场上下文评分: {context_score:.2f} (体制: {market_regime}, 接近支撑: {support_score:.2f})",
        )

    def _analyze_trend_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析趋势特征以检测SC

        SC趋势特征：
        1. 出现在下跌趋势后
        2. 可能伴随趋势加速

        Returns:
            趋势证据，或None（如果无法分析）
        """
        # 获取趋势信息
        trend_direction = context.get("trend_direction", "UNKNOWN")
        trend_strength = context.get("trend_strength", 0.5)

        # SC通常出现在下跌趋势中
        trend_score = 0.5  # 默认

        if trend_direction == "DOWN":
            trend_score = 0.7 + trend_strength * 0.3  # 下跌趋势越强，SC可能性越高
        elif trend_direction == "UP":
            trend_score = 0.3 - trend_strength * 0.2  # 上涨趋势中SC可能性低

        return StateEvidence(
            evidence_type="trend_alignment",
            value=trend_score,
            confidence=trend_score,
            weight=0.4,
            description=f"趋势对齐评分: {trend_score:.2f} (方向: {trend_direction}, 强度: {trend_strength:.2f})",
        )

    def detect_ps(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测初步支撑

        PS特征：
        1. 下跌趋势中首次出现支撑
        2. 成交量可能放大（初期买盘进入）
        3. 价格出现反弹迹象
        4. 可能形成锤子线或刺透形态

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
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

        # 1. 价格行为分析（权重：40%）
        # 检查是否为支撑形态（如锤子线、刺透形态等）
        is_bullish_reversal = False
        # 简单判断：收盘价高于开盘价，且下影线较长
        body_size = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)
        shadow_ratio = 0.0

        if body_size > 0:
            shadow_ratio = lower_shadow / body_size
            # 锤子线特征：下影线至少是实体的2倍，上影线很短
            if shadow_ratio > 2.0 and upper_shadow < body_size * 0.3:
                is_bullish_reversal = True

        price_score = 0.7 if is_bullish_reversal else 0.3
        confidence_factors.append(("price_action", price_score, 0.40))
        if is_bullish_reversal:
            evidences.append(
                StateEvidence(
                    evidence_type="price_action",
                    value=shadow_ratio,
                    confidence=price_score,
                    weight=0.6,
                    description=f"看涨反转形态 shadow_ratio={shadow_ratio:.2f}",
                )
            )

        # 2. 成交量分析（权重：30%）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio > 1.2:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_ratio",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.5,
                    description=f"成交量放大 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：30%）
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.8  # 下跌趋势中PS可能性高
            evidences.append(
                StateEvidence(
                    evidence_type="market_context",
                    value=regime_score,
                    confidence=regime_score,
                    weight=0.5,
                    description=f"下跌趋势中出现支撑 regime={market_regime}",
                )
            )
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.2

        confidence_factors.append(("context", regime_score, 0.30))

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

    def detect_sc(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测抛售高潮

        SC特征：
        1. 高成交量（恐慌性抛售）
        2. 大幅下跌（长阴线或长下影线）
        3. 针形K线特征（下影线长）
        4. 出现在下跌趋势后

        Args:
            candle: 单根K线数据，需包含open, high, low, close, volume
            context: 上下文信息，可包含市场体制、TR边界等

        Returns:
            检测结果字典，包含置信度、强度和证据列表
        """
        evidences = []
        confidence_factors = []

        # 检查必需的数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        # 1. 成交量分析（权重：35%）
        volume_evidence = self._analyze_volume_for_sc(candle, context)
        if volume_evidence:
            evidences.append(volume_evidence)
            confidence_factors.append(("volume", volume_evidence.confidence, 0.35))

        # 2. 价格行为分析（权重：30%）
        price_evidence = self._analyze_price_action_for_sc(candle, context)
        if price_evidence:
            evidences.append(price_evidence)
            confidence_factors.append(("price_action", price_evidence.confidence, 0.30))

        # 3. 市场上下文分析（权重：20%）
        context_evidence = self._analyze_context_for_sc(candle, context)
        if context_evidence:
            evidences.append(context_evidence)
            confidence_factors.append(("context", context_evidence.confidence, 0.20))

        # 4. 趋势分析（权重：15%）
        trend_evidence = self._analyze_trend_for_sc(candle, context)
        if trend_evidence:
            evidences.append(trend_evidence)
            confidence_factors.append(("trend", trend_evidence.confidence, 0.15))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度（基于成交量比例和价格波动）
        volume_intensity = volume_evidence.value if volume_evidence else 1.0
        price_intensity = price_evidence.value if price_evidence else 0.5
        overall_intensity = volume_intensity * 0.6 + price_intensity * 0.4

        # 记录关键价格水平（SC低点）— 仅在置信度足够时更新
        if overall_confidence >= 0.6:
            sc_low = float(candle["low"])
            self.critical_price_levels["SC_LOW"] = sc_low

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    # ===== AR检测辅助方法 =====

    def _analyze_volume_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR成交量特征

        AR成交量特征：
        1. 成交量收缩（相对于SC的恐慌性抛售）
        2. 买盘温和恢复

        Returns:
            成交量证据
        """
        if "volume" not in candle:
            return None

        current_volume = float(candle["volume"])

        # 获取SC成交量（如果可用）
        sc_volume = context.get(
            "sc_volume", current_volume * 2.0
        )  # 默认SC成交量是当前2倍
        sc_volume_ratio = sc_volume / current_volume if current_volume > 0 else 1.0

        # AR成交量应小于SC成交量（收缩）
        volume_contraction = min(
            1.0, sc_volume_ratio / 3.0
        )  # SC成交量是AR3倍时达到最大置信度

        # 计算成交量置信度
        confidence = volume_contraction

        return StateEvidence(
            evidence_type="volume_contraction",
            value=volume_contraction,
            confidence=confidence,
            weight=0.7,
            description=f"成交量收缩比率: {sc_volume_ratio:.2f}x (SC成交量: {sc_volume:.0f}, AR成交量: {current_volume:.0f})",
        )

    def _analyze_bounce_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR价格反弹特征

        AR价格特征：
        1. 从SC低点反弹
        2. 反弹幅度适中（20%-50%回撤）
        3. 通常为阳线

        Returns:
            反弹证据
        """
        required_fields = ["open", "high", "low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # 获取SC低点
        sc_low = context.get("sc_low", low * 0.95)  # 默认SC低点比当前低点低5%

        # 计算反弹幅度（从SC低点到当前收盘价）
        bounce_height = close - sc_low
        sc_range = context.get("sc_range", high - low)  # SC价格范围

        if sc_range <= 0:
            return None

        bounce_ratio = bounce_height / sc_range

        # AR反弹幅度通常在20%-50%之间
        optimal_bounce_min = 0.2
        optimal_bounce_max = 0.5

        if bounce_ratio < optimal_bounce_min:
            bounce_score = bounce_ratio / optimal_bounce_min
        elif bounce_ratio > optimal_bounce_max:
            bounce_score = max(
                0, 1.0 - (bounce_ratio - optimal_bounce_max) / optimal_bounce_max
            )
        else:
            bounce_score = 1.0

        # 检查是否为阳线（AR通常为阳线）
        is_bullish = close > open_price
        bullish_score = 0.8 if is_bullish else 0.3

        # 综合反弹评分
        bounce_score_final = bounce_score * 0.7 + bullish_score * 0.3

        return StateEvidence(
            evidence_type="bounce_strength",
            value=bounce_score_final,
            confidence=bounce_score_final,
            weight=0.8,
            description=f"反弹强度: {bounce_score_final:.2f} (反弹幅度: {bounce_ratio:.1%}, SC低点: {sc_low:.2f}, 阳线: {is_bullish})",
        )

    def _analyze_context_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR市场上下文

        AR上下文特征：
        1. 出现在SC之后
        2. 市场体制可能从下跌转为盘整

        Returns:
            上下文证据
        """
        # 检查是否检测到SC
        has_sc = context.get("has_sc", False)
        sc_confidence = context.get("sc_confidence", 0.0)

        # SC存在且置信度高时，AR可能性高
        sc_score = sc_confidence if has_sc else 0.2

        # 检查市场体制
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5  # 默认

        if market_regime in ["ACCUMULATION", "CONSOLIDATION", "TRANSITION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.4  # 仍在下跌趋势中，但可能出现AR

        # 综合上下文评分
        context_score = sc_score * 0.6 + regime_score * 0.4

        return StateEvidence(
            evidence_type="ar_context",
            value=context_score,
            confidence=context_score,
            weight=0.5,
            description=f"AR上下文评分: {context_score:.2f} (有SC: {has_sc}, SC置信度: {sc_confidence:.2f}, 市场体制: {market_regime})",
        )

    def _analyze_trend_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR趋势特征

        AR趋势特征：
        1. 下跌趋势缓解
        2. 可能转为横盘或微幅上涨

        Returns:
            趋势证据
        """
        # 获取趋势信息
        trend_direction = context.get("trend_direction", "UNKNOWN")
        trend_strength = context.get("trend_strength", 0.5)

        # AR出现在下跌趋势缓解时
        trend_score = 0.5  # 默认

        if trend_direction == "DOWN":
            # 下跌趋势中，但强度减弱有利于AR
            trend_score = 0.6 - (trend_strength * 0.3)  # 下跌趋势越弱，AR可能性越高
        elif trend_direction == "SIDEWAYS":
            trend_score = 0.7  # 横盘有利于AR
        elif trend_direction == "UP":
            trend_score = 0.3  # 上涨趋势中AR可能性低

        return StateEvidence(
            evidence_type="trend_for_ar",
            value=trend_score,
            confidence=trend_score,
            weight=0.4,
            description=f"AR趋势评分: {trend_score:.2f} (趋势方向: {trend_direction}, 趋势强度: {trend_strength:.2f})",
        )

    def detect_ar(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测自动反弹

        AR特征：
        1. 成交量收缩（相对于SC的恐慌性抛售）
        2. 价格从SC低点反弹
        3. 反弹幅度适中（不是V型反转）
        4. 通常伴随买盘温和恢复

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

        # 1. 成交量分析（权重：30%）：AR成交量应收缩
        volume_evidence = self._analyze_volume_for_ar(candle, context)
        if volume_evidence:
            evidences.append(volume_evidence)
            confidence_factors.append(("volume", volume_evidence.confidence, 0.30))

        # 2. 价格反弹分析（权重：35%）：从SC低点反弹
        bounce_evidence = self._analyze_bounce_for_ar(candle, context)
        if bounce_evidence:
            evidences.append(bounce_evidence)
            confidence_factors.append(("bounce", bounce_evidence.confidence, 0.35))

        # 3. 市场上下文分析（权重：20%）：是否在SC之后
        context_evidence = self._analyze_context_for_ar(candle, context)
        if context_evidence:
            evidences.append(context_evidence)
            confidence_factors.append(("context", context_evidence.confidence, 0.20))

        # 4. 趋势缓和分析（权重：15%）：下跌趋势缓解
        trend_evidence = self._analyze_trend_for_ar(candle, context)
        if trend_evidence:
            evidences.append(trend_evidence)
            confidence_factors.append(("trend", trend_evidence.confidence, 0.15))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度（基于反弹幅度和成交量收缩程度）
        bounce_intensity = bounce_evidence.value if bounce_evidence else 0.5
        volume_intensity = volume_evidence.value if volume_evidence else 0.5
        overall_intensity = bounce_intensity * 0.6 + volume_intensity * 0.4

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    # ===== ST检测辅助方法 =====

    def _analyze_volume_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST成交量特征

        ST成交量特征：
        1. 成交量进一步收缩（相对于AR）
        2. 买盘犹豫，卖盘枯竭

        Returns:
            成交量证据
        """
        if "volume" not in candle:
            return None

        current_volume = float(candle["volume"])

        # 获取AR成交量（如果可用）
        ar_volume = context.get(
            "ar_volume", current_volume * 1.5
        )  # 默认AR成交量是当前1.5倍
        ar_volume_ratio = ar_volume / current_volume if current_volume > 0 else 1.0

        # ST成交量应小于AR成交量（进一步收缩）
        volume_contraction = min(
            1.0, ar_volume_ratio / 2.0
        )  # AR成交量是ST2倍时达到最大置信度

        # 计算成交量置信度
        confidence = volume_contraction

        return StateEvidence(
            evidence_type="volume_contraction_st",
            value=volume_contraction,
            confidence=confidence,
            weight=0.7,
            description=f"ST成交量收缩比率: {ar_volume_ratio:.2f}x (AR成交量: {ar_volume:.0f}, ST成交量: {current_volume:.0f})",
        )

    def _analyze_retracement_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST价格回撤特征

        ST价格特征：
        1. 回调测试SC低点区域
        2. 回调幅度有限（AR反弹幅度的30%-70%）
        3. 不跌破SC低点

        Returns:
            回撤证据
        """
        required_fields = ["high", "low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # 获取SC低点和AR高点
        sc_low = context.get("sc_low", low * 0.98)  # 默认SC低点比当前低点低2%
        ar_high = context.get("ar_high", high * 1.02)  # 默认AR高点比当前高点高2%

        # 计算AR反弹幅度
        ar_bounce = ar_high - sc_low
        if ar_bounce <= 0:
            return None

        # 计算当前价格从AR高点的回撤幅度
        current_price = close
        retracement = ar_high - current_price
        retracement_ratio = retracement / ar_bounce if ar_bounce > 0 else 0.0

        # ST回撤幅度通常在30%-70%之间
        optimal_retracement_min = 0.3
        optimal_retracement_max = 0.7

        if retracement_ratio < optimal_retracement_min:
            retracement_score = retracement_ratio / optimal_retracement_min
        elif retracement_ratio > optimal_retracement_max:
            retracement_score = max(
                0,
                1.0
                - (retracement_ratio - optimal_retracement_max)
                / optimal_retracement_max,
            )
        else:
            retracement_score = 1.0

        # 检查是否跌破SC低点（不应跌破）
        above_sc = current_price > sc_low
        sc_penalty = 0.2 if not above_sc else 0.0

        # 综合回撤评分
        retracement_score_final = max(0, retracement_score - sc_penalty)

        return StateEvidence(
            evidence_type="retracement_strength",
            value=retracement_score_final,
            confidence=retracement_score_final,
            weight=0.8,
            description=f"ST回撤强度: {retracement_score_final:.2f} (回撤幅度: {retracement_ratio:.1%}, SC低点: {sc_low:.2f}, AR高点: {ar_high:.2f}, 高于SC: {above_sc})",
        )

    def _analyze_context_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST市场上下文

        ST上下文特征：
        1. 出现在AR之后
        2. 市场体制可能为盘整或吸筹

        Returns:
            上下文证据
        """
        # 检查是否检测到AR
        has_ar = context.get("has_ar", False)
        ar_confidence = context.get("ar_confidence", 0.0)

        # AR存在且置信度高时，ST可能性高
        ar_score = ar_confidence if has_ar else 0.2

        # 检查市场体制
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5  # 默认

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3  # 仍在下跌趋势中，ST可能性较低

        # 综合上下文评分
        context_score = ar_score * 0.7 + regime_score * 0.3

        return StateEvidence(
            evidence_type="st_context",
            value=context_score,
            confidence=context_score,
            weight=0.5,
            description=f"ST上下文评分: {context_score:.2f} (有AR: {has_ar}, AR置信度: {ar_confidence:.2f}, 市场体制: {market_regime})",
        )

    def _analyze_support_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST支撑测试特征

        ST支撑特征：
        1. SC低点支撑有效
        2. 价格在SC区域获得支撑

        Returns:
            支撑证据
        """
        required_fields = ["low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        low = float(candle["low"])
        close = float(candle["close"])

        # 获取SC低点
        sc_low = context.get("sc_low", low * 0.98)

        # 计算价格与SC低点的距离
        distance_to_sc = close - sc_low
        sc_range = context.get("sc_range", distance_to_sc * 2)  # 默认SC范围

        if sc_range <= 0:
            return None

        # 价格在SC低点上方附近获得支撑
        proximity_ratio = distance_to_sc / sc_range if sc_range > 0 else 0.0

        # 理想情况：价格在SC低点上方5%-20%范围内
        optimal_proximity_min = 0.05
        optimal_proximity_max = 0.20

        if proximity_ratio < optimal_proximity_min:
            proximity_score = proximity_ratio / optimal_proximity_min
        elif proximity_ratio > optimal_proximity_max:
            proximity_score = max(
                0,
                1.0 - (proximity_ratio - optimal_proximity_max) / optimal_proximity_max,
            )
        else:
            proximity_score = 1.0

        # 检查是否跌破SC低点
        above_sc = close > sc_low
        sc_penalty = 0.3 if not above_sc else 0.0

        # 综合支撑评分
        support_score = max(0, proximity_score - sc_penalty)

        return StateEvidence(
            evidence_type="support_strength",
            value=support_score,
            confidence=support_score,
            weight=0.6,
            description=f"ST支撑强度: {support_score:.2f} (距离SC: {proximity_ratio:.1%}, SC低点: {sc_low:.2f}, 高于SC: {above_sc})",
        )

    def detect_st(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测二次测试

        ST特征：
        1. 成交量进一步收缩（相对于AR）
        2. 价格回调测试SC低点区域，但不跌破SC低点
        3. 回调幅度有限（通常为AR反弹幅度的50%左右）
        4. 可能出现缩量小阴线或十字星

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

        # 1. 成交量分析（权重：30%）：ST成交量应进一步收缩
        volume_evidence = self._analyze_volume_for_st(candle, context)
        if volume_evidence:
            evidences.append(volume_evidence)
            confidence_factors.append(("volume", volume_evidence.confidence, 0.30))

        # 2. 价格回调分析（权重：35%）：测试SC区域但不跌破
        retracement_evidence = self._analyze_retracement_for_st(candle, context)
        if retracement_evidence:
            evidences.append(retracement_evidence)
            confidence_factors.append(
                ("retracement", retracement_evidence.confidence, 0.35)
            )

        # 3. 市场上下文分析（权重：20%）：是否在AR之后
        context_evidence = self._analyze_context_for_st(candle, context)
        if context_evidence:
            evidences.append(context_evidence)
            confidence_factors.append(("context", context_evidence.confidence, 0.20))

        # 4. 支撑测试分析（权重：15%）：SC低点支撑有效性
        support_evidence = self._analyze_support_for_st(candle, context)
        if support_evidence:
            evidences.append(support_evidence)
            confidence_factors.append(("support", support_evidence.confidence, 0.15))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度（基于成交量收缩程度和支撑强度）
        volume_intensity = volume_evidence.value if volume_evidence else 0.5
        support_intensity = support_evidence.value if support_evidence else 0.5
        overall_intensity = volume_intensity * 0.5 + support_intensity * 0.5

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_test(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测测试状态

        TEST特征：
        1. 价格测试前支撑位（如SC低点、SPRING低点）
        2. 成交量收缩（供应不足）
        3. 价格反弹迹象（测试成功）
        4. 通常在SC/AR/ST之后出现

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：40%）
        # 检查是否测试关键支撑位
        test_success = False
        # 获取关键支撑位（SC低点、SPRING低点等）
        sc_low = self.critical_price_levels.get("SC_LOW")
        spring_low = self.critical_price_levels.get("SPRING_LOW")
        support_levels = [level for level in [sc_low, spring_low] if level is not None]

        if support_levels:
            # 计算价格与最近支撑位的距离
            nearest_support = min(support_levels, key=lambda x: abs(x - low))
            distance_pct = abs(low - nearest_support) / nearest_support * 100
            # 测试成功：价格接近支撑位并反弹（收盘高于开盘）
            if distance_pct < 1.0 and close > open_price:
                test_success = True
                evidences.append(
                    StateEvidence(
                        evidence_type="price_action",
                        value=distance_pct,
                        confidence=0.8,
                        weight=0.7,
                        description=f"测试支撑位成功 support={nearest_support:.2f} "
                        f"distance={distance_pct:.2f}%",
                    )
                )

        price_score = 0.8 if test_success else 0.3
        confidence_factors.append(("price_action", price_score, 0.40))

        # 2. 成交量分析（权重：30%）
        # TEST成交量应收缩（供应不足）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio < 1.0:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_contraction",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.6,
                    description=f"成交量收缩 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：30%）
        # TEST通常在吸筹阶段出现（SC/AR/ST之后）
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
            evidences.append(
                StateEvidence(
                    evidence_type="market_context",
                    value=regime_score,
                    confidence=regime_score,
                    weight=0.5,
                    description=f"吸筹阶段测试 regime={market_regime}",
                )
            )
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.6  # 下跌趋势中也可能出现测试

        # 检查前驱状态（如果有状态历史）
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SC", "AR", "ST"]:
                regime_score = min(1.0, regime_score + 0.2)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.30))

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

    def detect_spring(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """检测弹簧状态

        SPRING特征：
        1. 价格跌破关键支撑位（如SC低点）
        2. 快速反弹回支撑位上方（假突破）
        3. 成交量相对较低（缺乏跟进卖盘）
        4. 通常出现在吸筹后期（SC/AR/ST之后）

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否跌破关键支撑位并反弹
        spring_detected = False
        # 获取关键支撑位（SC低点）
        sc_low = self.critical_price_levels.get("SC_LOW")
        spring_low = self.critical_price_levels.get("SPRING_LOW")
        support_levels = [level for level in [sc_low, spring_low] if level is not None]

        if support_levels:
            nearest_support = min(support_levels, key=lambda x: abs(x - low))
            # 检查是否跌破支撑位（最低价低于支撑位）
            if low < nearest_support:
                # 检查是否反弹回支撑位上方（收盘价高于支撑位）
                if close > nearest_support:
                    spring_detected = True
                    evidences.append(
                        StateEvidence(
                            evidence_type="price_action",
                            value=(nearest_support - low) / nearest_support,
                            confidence=0.9,
                            weight=0.8,
                            description=f"跌破支撑位后反弹 low={low:.2f} "
                            f"< support={nearest_support:.2f} "
                            f"< close={close:.2f}",
                        )
                    )

        price_score = 0.9 if spring_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))
        if not spring_detected:
            evidences.append(
                StateEvidence(
                    evidence_type="price_action",
                    value=0.0,
                    confidence=0.3,
                    weight=0.4,
                    description="未检测到弹簧形态",
                )
            )

        # 2. 成交量分析（权重：30%）
        # SPRING成交量应较低（缺乏跟进卖盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量越低，置信度越高（小于1倍平均成交量）
        volume_score = max(0.0, 1.0 - volume_ratio * 0.8)  # 0倍得1分，1.25倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio < 1.0:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_contraction",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.6,
                    description=f"成交量收缩 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：20%）
        # SPRING通常在吸筹阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.6

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SC", "AR", "ST", "TEST"]:
                regime_score = min(1.0, regime_score + 0.2)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 记录弹簧低点 — 仅在置信度足够时更新
        if spring_detected and overall_confidence >= 0.6:
            self.critical_price_levels["SPRING_LOW"] = low

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_so(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测震仓状态

        SO（震仓）特征：
        1. 价格快速跌破支撑位，引发恐慌
        2. 成交量放大（恐慌性抛售）
        3. 快速反弹回支撑位上方
        4. 通常出现在吸筹阶段，清洗弱手

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否跌破支撑并快速反弹
        shakeout_detected = False
        # 获取关键支撑位
        sc_low = self.critical_price_levels.get("SC_LOW")
        support_levels = [level for level in [sc_low] if level is not None]

        if support_levels:
            nearest_support = min(support_levels, key=lambda x: abs(x - low))
            # 检查是否跌破支撑位（最低价明显低于支撑位）
            if low < nearest_support * 0.99:  # 至少跌破1%
                # 检查是否反弹回支撑位附近（收盘价接近或高于支撑位）
                if close > nearest_support * 0.995:
                    shakeout_detected = True
                    evidences.append(
                        StateEvidence(
                            evidence_type="price_action",
                            value=(nearest_support - low) / nearest_support,
                            confidence=0.9,
                            weight=0.8,
                            description=f"跌破支撑后反弹 low={low:.2f} < support={nearest_support:.2f}",
                        )
                    )

        price_score = 0.9 if shakeout_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # SO成交量应放大（恐慌性抛售）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1.5倍）
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio > 1.5:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_expansion",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.6,
                    description=f"成交量放大 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：20%）
        # SO通常在吸筹阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.6

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SC", "AR", "ST", "TEST"]:
                regime_score = min(1.0, regime_score + 0.2)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.20))

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

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_lps(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测最后支撑点

        LPS（最后支撑点）特征：
        1. 价格形成更高的低点（相对于SC或SPRING低点）
        2. 成交量收缩（供应枯竭）
        3. 价格反弹迹象（需求进入）
        4. 通常出现在SPRING或TEST之后

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["low", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        low = float(candle["low"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否形成更高的低点
        higher_low_detected = False
        # 获取前期低点（SC低点、SPRING低点）
        sc_low = self.critical_price_levels.get("SC_LOW")
        spring_low = self.critical_price_levels.get("SPRING_LOW")
        previous_lows = [level for level in [sc_low, spring_low] if level is not None]

        if previous_lows:
            lowest_previous = min(previous_lows)
            # 当前低点高于前期低点（形成更高的低点）
            if low > lowest_previous:
                higher_low_detected = True
                evidences.append(
                    StateEvidence(
                        evidence_type="higher_low",
                        value=(low - lowest_previous) / lowest_previous,
                        confidence=0.9,
                        weight=0.7,
                        description=f"更高低点 low={low:.2f} > previous={lowest_previous:.2f}",
                    )
                )

        price_score = 0.9 if higher_low_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # LPS成交量应收缩（供应枯竭）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio < 1.0:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_contraction",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.6,
                    description=f"成交量收缩 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：20%）
        # LPS通常在吸筹后期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.4  # 下跌趋势中LPS可能性较低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SPRING", "TEST", "SO"]:
                regime_score = min(1.0, regime_score + 0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.20))

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

    def detect_minor_sos(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """检测局部强势信号（minor Sign of Strength）

        与 MSOS（整体强势）的区别：
        - mSOS 关注局部突破：价格突破近期阻力但幅度较小，成交量温和放大
        - MSOS 关注整体突破：价格大幅突破关键阻力（如 AR 高点），成交量显著放大

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典，包含置信度、强度和证据列表
        """
        evidences: list[StateEvidence] = []
        confidence_factors: list[float] = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        # 基本价格数据
        close = float(candle["close"])
        open_price = float(candle["open"])
        high = float(candle["high"])
        volume = float(candle["volume"])

        # 获取成交量均值
        vol_mean = context.get("volume_mean", context.get("avg_volume_20", volume))
        vol_ratio = volume / vol_mean if vol_mean > 0 else 1.0

        # 获取近期高点作为局部阻力
        recent_high = context.get("recent_high", high)

        # 条件1：阳线（收盘 > 开盘）
        is_bullish = close > open_price
        if is_bullish:
            confidence_factors.append(0.3)
            evidences.append(
                StateEvidence(
                    evidence_type="price_action",
                    value=close - open_price,
                    confidence=0.3,
                    weight=0.5,
                    description="阳线确认",
                )
            )

        # 条件2：价格接近或突破近期高点（局部突破）
        if recent_high > 0:
            proximity = (close - recent_high) / recent_high if recent_high != 0 else 0
            if proximity > -0.01:  # 接近或突破近期高点1%以内
                confidence_factors.append(0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="breakout",
                        value=proximity,
                        confidence=0.3,
                        weight=0.6,
                        description=f"接近/突破近期高点 proximity={proximity:.4f}",
                    )
                )

        # 条件3：成交量温和放大（不需要像 MSOS 那样显著放大）
        if vol_ratio > 1.0:
            vol_score = min(0.3, (vol_ratio - 1.0) * 0.3)
            confidence_factors.append(vol_score)
            evidences.append(
                StateEvidence(
                    evidence_type="volume_expansion",
                    value=vol_ratio,
                    confidence=vol_score,
                    weight=0.5,
                    description=f"成交量温和放大 vol_ratio={vol_ratio:.2f}",
                )
            )

        # 条件4：前驱状态检查
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SPRING", "TEST", "ST", "LPS"]:
                confidence_factors.append(0.2)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=0.2,
                        confidence=0.2,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence = min(1.0, sum(confidence_factors))

        return {
            "confidence": confidence,
            "intensity": vol_ratio,
            "evidences": evidences,
        }

    def detect_msos(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测整体强势状态

        mSOS/MSOS（强势信号）特征：
        1. 价格创新高或接近前期高点
        2. 成交量放大（需求进入）
        3. 价格回调幅度小（供应薄弱）
        4. 通常出现在LPS之后，JOC之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["high", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        high = float(candle["high"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否创新高或接近前期高点
        strength_detected = False
        # 获取前期高点（SC高点、AR高点等）
        sc_high = self.critical_price_levels.get("SC_HIGH")
        ar_high = self.critical_price_levels.get("AR_HIGH")
        previous_highs = [level for level in [sc_high, ar_high] if level is not None]

        if previous_highs:
            highest_previous = max(previous_highs)
            # 当前高点接近或超过前期高点
            if high >= highest_previous * 0.98:  # 至少达到98%
                strength_detected = True
                evidences.append(
                    StateEvidence(
                        evidence_type="breakout",
                        value=high / highest_previous,
                        confidence=0.9,
                        weight=0.7,
                        description=f"接近/突破前期高点 high={high:.2f} "
                        f"vs previous={highest_previous:.2f}",
                    )
                )

        price_score = 0.9 if strength_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # 强势信号成交量应放大（需求进入）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio > 1.2:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_expansion",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.6,
                    description=f"成交量放大 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：20%）
        # 强势信号通常在吸筹后期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3  # 下跌趋势中强势信号可能性低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["LPS", "mSOS"]:
                regime_score = min(1.0, regime_score + 0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.20))

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

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_joc(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测突破溪流

        JOC（突破溪流）特征：
        1. 价格突破关键阻力位（如交易区间上沿）
        2. 成交量显著放大（需求强劲）
        3. 突破幅度较大（显示力度）
        4. 通常出现在MSOS之后，BU之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["high", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        high = float(candle["high"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否突破关键阻力位
        breakout_detected = False
        # 获取关键阻力位（交易区间上沿、前期高点）
        tr_resistance = context.get("tr_resistance")
        previous_highs = [level for level in [tr_resistance] if level is not None]

        if previous_highs:
            resistance_level = max(previous_highs)
            # 价格突破阻力位（收盘价高于阻力位）
            if close > resistance_level:
                breakout_detected = True
                # 记录JOC高点
                self.critical_price_levels["JOC_HIGH"] = high
                evidences.append(
                    StateEvidence(
                        evidence_type="breakout",
                        value=(close - resistance_level) / resistance_level,
                        confidence=0.9,
                        weight=0.8,
                        description=f"突破阻力位 close={close:.2f} > resistance={resistance_level:.2f}",
                    )
                )

        price_score = 0.9 if breakout_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # JOC成交量应显著放大（需求强劲）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于2倍）
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio > 1.5:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_expansion",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.7,
                    description=f"成交量显著放大 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：20%）
        # JOC通常在吸筹末期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3  # 下跌趋势中JOC可能性低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["MSOS", "mSOS"]:
                regime_score = min(1.0, regime_score + 0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.20))

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

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_bu(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测回踩确认

        BU（回踩确认）特征：
        1. 价格回踩突破位（JOC高点或阻力转支撑）
        2. 成交量收缩（供应缺乏）
        3. 价格在支撑位反弹（确认支撑有效）
        4. 通常出现在JOC之后，确认突破有效

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否回踩突破位并反弹
        backup_confirmed = False
        # 获取JOC高点或突破位
        joc_high = self.critical_price_levels.get("JOC_HIGH")
        tr_resistance = context.get("tr_resistance")
        breakout_levels = [
            level for level in [joc_high, tr_resistance] if level is not None
        ]

        if breakout_levels:
            breakout_level = max(breakout_levels)  # 突破位作为支撑
            # 价格回踩突破位（最低价接近突破位）
            if abs(low - breakout_level) / breakout_level < 0.02:  # 2%以内
                # 收盘价高于开盘价（反弹迹象）
                if close > open_price:
                    backup_confirmed = True
                    evidences.append(
                        StateEvidence(
                            evidence_type="pullback",
                            value=abs(low - breakout_level) / breakout_level,
                            confidence=0.9,
                            weight=0.7,
                            description=f"回踩突破位确认 low={low:.2f} ~ breakout={breakout_level:.2f}",
                        )
                    )

        price_score = 0.9 if backup_confirmed else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # BU成交量应收缩（缺乏供应）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio < 1.0:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_contraction",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.6,
                    description=f"成交量收缩 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：20%）
        # BU通常在突破后出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION", "UPTREND"]:
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
            if last_state == "JOC":
                regime_score = min(1.0, regime_score + 0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.20))

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

    def detect_uta(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测上冲行为

        UTA（上冲行为）特征：
        1. 价格上冲突破阻力位但未能站稳
        2. 收盘价回落至阻力位下方（假突破）
        3. 成交量相对较低（缺乏跟进买盘）
        4. 通常出现在AR之后，TEST之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences: list[StateEvidence] = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["high", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        high = float(candle["high"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否上冲突破但回落
        upthrust_detected = False
        # 获取关键阻力位（AR高点、前期高点）
        ar_high = self.critical_price_levels.get("AR_HIGH")
        tr_resistance = context.get("tr_resistance")
        resistance_levels = [
            level for level in [ar_high, tr_resistance] if level is not None
        ]

        if resistance_levels:
            resistance_level = max(resistance_levels)
            # 检查是否上冲突破（最高价高于阻力位）
            if high > resistance_level:
                # 检查是否回落（收盘价低于阻力位）
                if close < resistance_level:
                    upthrust_detected = True
                    evidences.append(
                        StateEvidence(
                            evidence_type="upthrust",
                            value=(high - resistance_level) / resistance_level,
                            confidence=0.9,
                            weight=0.8,
                            description=f"上冲回落 high={high:.2f} "
                            f"> resistance={resistance_level:.2f} "
                            f"> close={close:.2f}",
                        )
                    )

        price_score = 0.9 if upthrust_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # UTA成交量应较低（缺乏跟进买盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量越低，置信度越高（小于1倍平均成交量）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))
        if volume_ratio < 1.0:
            evidences.append(
                StateEvidence(
                    evidence_type="volume_contraction",
                    value=volume_ratio,
                    confidence=volume_score,
                    weight=0.6,
                    description=f"成交量收缩 vol_ratio={volume_ratio:.2f}",
                )
            )

        # 3. 市场上下文分析（权重：20%）
        # UTA通常在吸筹阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "AR":
                regime_score = min(1.0, regime_score + 0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="predecessor_state",
                        value=regime_score,
                        confidence=regime_score,
                        weight=0.4,
                        description=f"前驱状态支持: {last_state}",
                    )
                )

        confidence_factors.append(("context", regime_score, 0.20))

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
