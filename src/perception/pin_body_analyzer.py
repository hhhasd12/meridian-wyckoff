"""
针vs实体辩证识别算法（analyze_pin_vs_body函数）
实现计划书第2.2节的"针与实体辩证识别算法"

设计原则：
1. 辩证识别：拒绝单一判定，实施证据加权与概率打分
2. 动态参数：所有阈值根据市场波动率和体制动态调整
3. 上下文敏感：考虑市场背景（趋势市、盘整市）调整判定标准
4. 多维度证据：成交量、影线比例、位置分析等多维度综合判断

核心算法：
1. 动态阈值计算：基于波动率指数(Volatility_Index)和市场体制(Market_Regime)
2. 针主导判定：影线 > 实体 × 动态阈值
3. 实体主导判定：实体 > 影线 × 动态阈值
4. 努力与结果分析：高成交量 + 小实体 = 主力介入信号
5. 位置分析：支撑阻力位附近的K线意义不同

使用示例：
    from .candle_physical import CandlePhysical
    from .pin_body_analyzer import analyze_pin_vs_body

    candle = CandlePhysical(open=100, high=110, low=95, close=105, volume=1500)
    context = {
        'volatility_index': 1.2,  # 当前ATR/平均ATR
        'market_regime': 'RANGING',  # 市场体制
        'volume_moving_avg': 1000,
        'avg_body_size': 5.0,
        'tr_support': 95,
        'tr_resistance': 110
    }

    result = analyze_pin_vs_body(candle, context)
    print(f"针主导: {result['is_pin_dominant']}, 置信度: {result['pin_strength']:.2f}")
    print(f"实体主导: {result['is_body_dominant']}, 置信度: {result['body_strength']:.2f}")
    print(f"努力结果: {result['effort_vs_result']}")
"""

import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Union

import numpy as np

# 导入CandlePhysical类
try:
    from .candle_physical import CandlePhysical
except ImportError:
    from candle_physical import CandlePhysical


class MarketRegimeType(Enum):
    """市场体制类型"""

    TRENDING = "TRENDING"  # 趋势市
    RANGING = "RANGING"  # 盘整市
    VOLATILE = "VOLATILE"  # 高波动市
    UNKNOWN = "UNKNOWN"  # 未知


class EffortResultType(Enum):
    """努力与结果类型"""

    HIGH_EFFORT_LOW_RESULT = "HIGH_EFFORT_LOW_RESULT"  # 高努力低结果（主力介入）
    LOW_EFFORT_HIGH_RESULT = "LOW_EFFORT_HIGH_RESULT"  # 低努力高结果（趋势延续）
    NORMAL = "NORMAL"  # 正常
    UNKNOWN = "UNKNOWN"  # 未知


@dataclass
class PinBodyAnalysisResult:
    """针vs实体分析结果"""

    is_pin_dominant: bool = False  # 针主导
    is_body_dominant: bool = False  # 实体主导
    pin_strength: float = 0.0  # 针强度 [0, 1]
    body_strength: float = 0.0  # 实体强度 [0, 1]
    effort_vs_result: Optional[EffortResultType] = None  # 努力与结果分析
    effort_ratio: Optional[float] = None  # 努力比率（成交量倍数）
    result_ratio: Optional[float] = None  # 结果比率（实体大小倍数）
    volume_confirmation: bool = False  # 成交量确认
    dynamic_thresholds_used: dict[str, float] = None  # 使用的动态阈值
    confidence: float = 0.0  # 总体置信度

    def __post_init__(self):
        if self.dynamic_thresholds_used is None:
            self.dynamic_thresholds_used = {}


@dataclass
class AnalysisContext:
    """分析上下文（简化版）"""

    volatility_index: float = 1.0  # 波动率指数：当前ATR/平均ATR
    market_regime: MarketRegimeType = MarketRegimeType.UNKNOWN  # 市场体制
    volume_moving_avg: float = 1.0  # 成交量移动平均值
    avg_body_size: float = 1.0  # 平均实体大小
    previous_close: Optional[float] = None  # 前收盘价
    atr14: float = 1.0  # 14周期ATR
    tr_support: Optional[float] = None  # 交易区间支撑
    tr_resistance: Optional[float] = None  # 交易区间阻力
    trend: str = "NEUTRAL"  # 趋势方向：UPTREND/DOWNTREND/NEUTRAL
    trend_strength: float = 0.0  # 趋势强度 [0, 1]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "volatility_index": self.volatility_index,
            "market_regime": self.market_regime.value
            if self.market_regime
            else "UNKNOWN",
            "volume_moving_avg": self.volume_moving_avg,
            "avg_body_size": self.avg_body_size,
            "previous_close": self.previous_close,
            "atr14": self.atr14,
            "tr_support": self.tr_support,
            "tr_resistance": self.tr_resistance,
            "trend": self.trend,
            "trend_strength": self.trend_strength,
        }


def analyze_pin_vs_body(
    candle: Union[CandlePhysical, dict[str, float]],
    context: Union[AnalysisContext, dict[str, Any]],
) -> PinBodyAnalysisResult:
    """
    分析单根K线的针与实体关系，使用动态参数系统

    基于计划书第2.2节的算法实现，包含：
    1. 动态阈值计算（基于波动率和市场体制）
    2. 针主导判定
    3. 实体主导判定
    4. 努力与结果分析
    5. 成交量确认

    Args:
        candle: CandlePhysical对象或包含OHLCV的字典
        context: AnalysisContext对象或包含上下文信息的字典

    Returns:
        PinBodyAnalysisResult: 分析结果对象

    Raises:
        ValueError: 如果输入数据无效
    """
    # 1. 参数标准化
    if isinstance(candle, dict):
        candle = CandlePhysical(**candle)
    elif not isinstance(candle, CandlePhysical):
        raise ValueError(
            f"candle参数必须是CandlePhysical对象或字典，当前类型: {type(candle)}"
        )

    if isinstance(context, dict):
        context_dict = context
        # 转换market_regime为枚举（处理字符串或枚举对象）
        if "market_regime" in context_dict:
            regime_value = context_dict["market_regime"]

            if isinstance(regime_value, MarketRegimeType):
                # 已经是枚举对象，直接使用
                context_dict["market_regime"] = regime_value
            elif isinstance(regime_value, str):
                # 是字符串，尝试转换为枚举
                try:
                    # 确保字符串是大写的，以匹配枚举值
                    regime_str_upper = regime_value.upper()
                    context_dict["market_regime"] = MarketRegimeType(regime_str_upper)
                except ValueError:
                    context_dict["market_regime"] = MarketRegimeType.UNKNOWN
            else:
                # 其他类型，使用UNKNOWN
                context_dict["market_regime"] = MarketRegimeType.UNKNOWN

        context = AnalysisContext(**context_dict)
    elif not isinstance(context, AnalysisContext):
        raise ValueError(
            f"context参数必须是AnalysisContext对象或字典，当前类型: {type(context)}"
        )

    # 2. 初始化结果
    result = PinBodyAnalysisResult()

    # 3. 计算基础指标
    body_size = candle.body
    shadow_size = candle.total_shadow
    total_range = candle.total_range

    if total_range <= 0:
        warnings.warn(f"K线总范围为零或负数: {total_range}")
        return result

    # 4. ===== 动态参数计算 =====
    # 基础阈值（正常波动率下的经验值）
    BASE_PIN_THRESHOLD = 1.5  # 针主导的基础阈值：影线 > 1.5倍实体
    BASE_BODY_THRESHOLD = 2.0  # 实体主导的基础阈值：实体 > 2.0倍影线
    BASE_VOLUME_SPIKE = 1.8  # 成交量爆发阈值：成交量 > 1.8倍移动平均
    BASE_EFFORT_THRESHOLD = 2.0  # 高努力阈值：成交量 > 2.0倍移动平均
    BASE_RESULT_THRESHOLD = 0.5  # 低结果阈值：实体 < 0.5倍平均实体

    # 波动率因子：当前ATR相对于历史平均ATR的比例
    # 示例：低波动时0.8，正常时1.0，高波动时1.5
    volatility_factor = context.volatility_index

    # 动态调整：高波动时需要更大的针/实体比例
    dynamic_pin_threshold = BASE_PIN_THRESHOLD * volatility_factor
    dynamic_body_threshold = BASE_BODY_THRESHOLD * volatility_factor

    # 市场体制调整：趋势市实体阈值降低，盘整市针阈值降低
    if context.market_regime == MarketRegimeType.TRENDING:
        dynamic_body_threshold *= 0.9  # 趋势中实体更容易出现
        dynamic_pin_threshold *= 1.1  # 趋势中针更少见
    elif context.market_regime == MarketRegimeType.RANGING:
        dynamic_pin_threshold *= 0.9  # 盘整中针更常见
        dynamic_body_threshold *= 1.1  # 盘整中实体更少见

    # 记录使用的动态阈值
    result.dynamic_thresholds_used = {
        "pin_threshold": dynamic_pin_threshold,
        "body_threshold": dynamic_body_threshold,
        "volatility_factor": volatility_factor,
        "regime_factor": context.market_regime.value,
        "base_pin_threshold": BASE_PIN_THRESHOLD,
        "base_body_threshold": BASE_BODY_THRESHOLD,
    }

    # 5. ===== 针主导判定（使用动态阈值） =====
    if shadow_size > body_size * dynamic_pin_threshold:
        result.is_pin_dominant = True
        result.pin_strength = shadow_size / total_range

        # 成交量爆发阈值也动态调整
        dynamic_volume_spike = BASE_VOLUME_SPIKE / volatility_factor
        # 低波动时成交量爆发更显著（阈值降低），高波动时阈值提高
        if candle.volume > context.volume_moving_avg * dynamic_volume_spike:
            result.pin_strength *= 1.5
            result.volume_confirmation = True
            result.confidence += 0.2

    # 6. ===== 实体主导判定（使用动态阈值） =====
    elif body_size > shadow_size * dynamic_body_threshold:
        result.is_body_dominant = True
        result.body_strength = body_size / total_range

        # 位置加成：在支撑阻力位附近的实体更有意义
        if _is_at_support_resistance(candle, context):
            result.body_strength *= 1.3
            result.confidence += 0.1

    # 7. ===== 努力与结果分析（使用动态阈值） =====
    effort = candle.volume
    result_size = body_size

    # 动态调整努力与结果阈值
    dynamic_effort_threshold = BASE_EFFORT_THRESHOLD / volatility_factor
    dynamic_result_threshold = BASE_RESULT_THRESHOLD * volatility_factor

    if (
        effort > context.volume_moving_avg * dynamic_effort_threshold
        and result_size < context.avg_body_size * dynamic_result_threshold
    ):
        result.effort_vs_result = EffortResultType.HIGH_EFFORT_LOW_RESULT
        result.effort_ratio = effort / context.volume_moving_avg
        result.result_ratio = result_size / context.avg_body_size
        result.confidence += 0.15

    elif (
        effort < context.volume_moving_avg * 0.7
        and result_size > context.avg_body_size * 1.5
    ):
        result.effort_vs_result = EffortResultType.LOW_EFFORT_HIGH_RESULT
        result.confidence += 0.1

    # 8. ===== 置信度计算 =====
    # 基础置信度基于针/实体强度
    if result.is_pin_dominant:
        result.confidence += result.pin_strength * 0.4
    elif result.is_body_dominant:
        result.confidence += result.body_strength * 0.4

    # 成交量确认加成
    if result.volume_confirmation:
        result.confidence += 0.1

    # 努力结果分析加成
    if result.effort_vs_result == EffortResultType.HIGH_EFFORT_LOW_RESULT:
        result.confidence += 0.15
    elif result.effort_vs_result == EffortResultType.LOW_EFFORT_HIGH_RESULT:
        result.confidence += 0.1

    # 限制置信度范围
    result.confidence = min(max(result.confidence, 0.0), 1.0)

    return result


def _is_at_support_resistance(candle: CandlePhysical, context: AnalysisContext) -> bool:
    """
    检查K线是否在支撑阻力位附近

    Args:
        candle: K线物理属性对象
        context: 分析上下文

    Returns:
        bool: 是否在支撑阻力位附近
    """
    tolerance_pct = 0.02  # 2%容忍度

    if context.tr_support:
        distance_to_support = abs(candle.low - context.tr_support) / context.tr_support
        if distance_to_support < tolerance_pct:
            return True

    if context.tr_resistance:
        distance_to_resistance = (
            abs(candle.high - context.tr_resistance) / context.tr_resistance
        )
        if distance_to_resistance < tolerance_pct:
            return True

    return False


def analyze_candle_series(
    candles: list[Union[CandlePhysical, dict[str, float]]],
    context: Union[AnalysisContext, dict[str, Any]],
) -> list[PinBodyAnalysisResult]:
    """
    分析K线序列的针vs实体模式

    Args:
        candles: CandlePhysical对象列表或字典列表
        context: 分析上下文（可为单个或列表）

    Returns:
        List[PinBodyAnalysisResult]: 分析结果列表
    """
    results = []

    for i, candle in enumerate(candles):
        # 如果是字典列表，需要确保每个字典都有OHLCV
        candle_obj = CandlePhysical(**candle) if isinstance(candle, dict) else candle

        result = analyze_pin_vs_body(candle_obj, context)
        results.append(result)

    return results


def get_dominant_pattern_statistics(
    results: list[PinBodyAnalysisResult],
) -> dict[str, Any]:
    """
    统计针vs实体分析结果的模式分布

    Args:
        results: PinBodyAnalysisResult列表

    Returns:
        Dict: 统计信息
    """
    total = len(results)
    if total == 0:
        return {}

    pin_dominant_count = sum(1 for r in results if r.is_pin_dominant)
    body_dominant_count = sum(1 for r in results if r.is_body_dominant)
    neutral_count = total - pin_dominant_count - body_dominant_count

    # 计算平均强度
    avg_pin_strength = np.mean(
        [r.pin_strength for r in results if r.is_pin_dominant] or [0]
    )
    avg_body_strength = np.mean(
        [r.body_strength for r in results if r.is_body_dominant] or [0]
    )
    avg_confidence = np.mean([r.confidence for r in results])

    # 努力结果统计
    high_effort_count = sum(
        1
        for r in results
        if r.effort_vs_result == EffortResultType.HIGH_EFFORT_LOW_RESULT
    )
    low_effort_count = sum(
        1
        for r in results
        if r.effort_vs_result == EffortResultType.LOW_EFFORT_HIGH_RESULT
    )

    return {
        "total_candles": total,
        "pin_dominant_percent": pin_dominant_count / total * 100,
        "body_dominant_percent": body_dominant_count / total * 100,
        "neutral_percent": neutral_count / total * 100,
        "avg_pin_strength": avg_pin_strength,
        "avg_body_strength": avg_body_strength,
        "avg_confidence": avg_confidence,
        "high_effort_count": high_effort_count,
        "low_effort_count": low_effort_count,
        "high_effort_percent": high_effort_count / total * 100 if total > 0 else 0,
        "low_effort_percent": low_effort_count / total * 100 if total > 0 else 0,
    }


def get_recommendation(
    result: PinBodyAnalysisResult, context: AnalysisContext
) -> dict[str, Any]:
    """
    根据分析结果生成交易建议

    Args:
        result: 针vs实体分析结果
        context: 分析上下文

    Returns:
        Dict: 交易建议
    """
    recommendation = {
        "action": "HOLD",
        "confidence": result.confidence,
        "reason": "",
        "risk_level": "MEDIUM",
    }

    if result.is_pin_dominant:
        # 针主导可能表示反转或犹豫
        if result.effort_vs_result == EffortResultType.HIGH_EFFORT_LOW_RESULT:
            # 高努力低结果：主力介入，可能反转
            recommendation["action"] = "WATCH_REVERSAL"
            recommendation["reason"] = "针主导+高努力低结果，主力可能介入"
            recommendation["risk_level"] = (
                "HIGH" if result.confidence > 0.7 else "MEDIUM"
            )
        elif result.volume_confirmation:
            # 针主导+成交量爆发：重要信号
            recommendation["action"] = "CONSIDER_ENTRY"
            recommendation["reason"] = "针主导+成交量爆发，市场犹豫但活跃"
            recommendation["risk_level"] = "MEDIUM"
        else:
            # 普通针主导：市场犹豫
            recommendation["action"] = "WAIT"
            recommendation["reason"] = "针主导，市场犹豫，等待确认"
            recommendation["risk_level"] = "LOW"

    elif result.is_body_dominant:
        # 实体主导表示趋势延续
        if _is_at_support_resistance:
            # 在关键位置的实体主导
            recommendation["action"] = "CONSIDER_TREND_FOLLOW"
            recommendation["reason"] = "实体主导+关键位置，趋势可能延续"
            recommendation["risk_level"] = "MEDIUM"
        elif result.body_strength > 0.7:
            # 强实体主导
            recommendation["action"] = "TREND_CONFIRMED"
            recommendation["reason"] = "强实体主导，趋势明确"
            recommendation["risk_level"] = "LOW"
        else:
            # 普通实体主导
            recommendation["action"] = "HOLD"
            recommendation["reason"] = "实体主导，趋势延续中"
            recommendation["risk_level"] = "LOW"

    # 努力结果分析
    if result.effort_vs_result == EffortResultType.HIGH_EFFORT_LOW_RESULT:
        recommendation["reason"] += " | 高努力低结果（主力活动）"
    elif result.effort_vs_result == EffortResultType.LOW_EFFORT_HIGH_RESULT:
        recommendation["reason"] += " | 低努力高结果（趋势顺畅）"

    return recommendation


# 测试代码
if __name__ == "__main__":

    # 创建测试K线
    test_candles = [
        CandlePhysical(open=100, high=115, low=95, close=101, volume=2000),  # 长上影线
        CandlePhysical(open=100, high=101, low=85, close=99, volume=1800),  # 长下影线
        CandlePhysical(open=100, high=120, low=100, close=118, volume=1200),  # 大实体
        CandlePhysical(open=100, high=101, low=99, close=100.5, volume=500),  # 十字星
    ]

    # 创建测试上下文
    test_context = AnalysisContext(
        volatility_index=1.2,  # 较高波动
        market_regime=MarketRegimeType.RANGING,  # 盘整市
        volume_moving_avg=1000,
        avg_body_size=5.0,
        previous_close=99,
        atr14=2.0,
        tr_support=95,
        tr_resistance=115,
        trend="NEUTRAL",
        trend_strength=0.3,
    )

    # 测试单根K线分析
    result1 = analyze_pin_vs_body(test_candles[0], test_context)

    # 测试K线序列分析
    results = analyze_candle_series(test_candles, test_context)
    stats = get_dominant_pattern_statistics(results)


    # 测试交易建议
    for i, (candle, result) in enumerate(zip(test_candles, results)):
        recommendation = get_recommendation(result, test_context)

    # 测试动态阈值效果
    high_vol_context = AnalysisContext(
        volatility_index=1.5,
        market_regime=MarketRegimeType.TRENDING,
        volume_moving_avg=1000,
        avg_body_size=5.0,
    )
    result_high_vol = analyze_pin_vs_body(test_candles[0], high_vol_context)

    low_vol_context = AnalysisContext(
        volatility_index=0.8,
        market_regime=MarketRegimeType.RANGING,
        volume_moving_avg=1000,
        avg_body_size=5.0,
    )
    result_low_vol = analyze_pin_vs_body(test_candles[0], low_vol_context)

