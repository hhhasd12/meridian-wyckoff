"""
冲突检测与解决模块
解决多周期融合中的信号冲突，特别是"日线派发vs4小时吸筹"等场景

设计原则：
1. 证据加权：使用周期权重过滤器进行加权决策
2. 辩证解决：考虑市场上下文、成交量、结构完整性
3. 渐进决策：从激进信号到确认信号的分层处理
4. 风险控制：冲突场景下降低仓位、严格风控
"""

from enum import Enum
from typing import Any, Optional

from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter, Timeframe


class ConflictType(Enum):
    """冲突类型枚举"""

    DISTRIBUTION_ACCUMULATION = "DISTRIBUTION_ACCUMULATION"  # 日线派发 vs 4小时吸筹
    TREND_CORRECTION = "TREND_CORRECTION"  # 大周期趋势 vs 小周期回调
    MULTI_TIMEFRAME_CONFLICT = "MULTI_TIMEFRAME_CONFLICT"  # 多时间框架混合冲突
    NO_CONFLICT = "NO_CONFLICT"  # 无冲突


class ResolutionBias(Enum):
    """解决偏向枚举"""

    BULLISH = "BULLISH"  # 看涨偏向
    BEARISH = "BEARISH"  # 看跌偏向
    NEUTRAL = "NEUTRAL"  # 中性偏向
    DEFERRED = "DEFERRED"  # 延迟决策（需要更多确认）


class ConflictResolutionManager:
    """
    冲突解决管理器

    功能：
    1. 检测多周期信号冲突
    2. 应用辩证解决逻辑
    3. 生成带权重的最终决策
    4. 管理激进/确认信号分层
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化冲突解决管理器

        Args:
            config: 配置字典，包含以下参数：
                - weight_filter_config: 周期权重过滤器配置
                - conflict_threshold: 冲突检测阈值（默认0.3）
                - resolution_threshold: 解决偏向阈值（默认0.1）
                - max_position_size: 冲突场景最大仓位（默认0.5）
                - require_micro_confirmation: 是否需要微观确认（默认True）
        """
        self.config = config or {}

        # 初始化周期权重过滤器
        weight_filter_config = self.config.get("weight_filter_config", {})
        self.weight_filter = PeriodWeightFilter(weight_filter_config)

        # 冲突检测阈值（置信度差异）
        self.conflict_threshold = self.config.get("conflict_threshold", 0.3)

        # 解决偏向阈值（10%差异）
        self.resolution_threshold = self.config.get("resolution_threshold", 0.1)

        # 冲突场景最大仓位（50%）
        self.max_position_size = self.config.get("max_position_size", 0.5)

        # 是否需要微观确认
        self.require_micro_confirmation = self.config.get(
            "require_micro_confirmation", True
        )

        # 冲突解决历史记录
        self.resolution_history = []

    def detect_conflict(
        self, timeframe_states: dict[str, dict[str, Any]]
    ) -> tuple[ConflictType, dict[str, Any]]:
        """
        检测时间框架状态冲突

        Args:
            timeframe_states: 各时间框架状态字典
                              键为时间框架字符串，值为包含'state'和'confidence'的字典
                              state可选值: "BULLISH", "BEARISH", "NEUTRAL"

        Returns:
            (冲突类型, 冲突详情字典)
        """
        if timeframe_states is None or len(timeframe_states) == 0:
            return ConflictType.NO_CONFLICT, {"reason": "无状态数据"}

        # 提取主要时间框架状态
        d1_state = timeframe_states.get("D", {}).get("state", "NEUTRAL")
        h4_state = timeframe_states.get("H4", {}).get("state", "NEUTRAL")
        timeframe_states.get("H1", {}).get("state", "NEUTRAL")

        # 检测多时间框架混合冲突
        states = [s.get("state", "NEUTRAL") for s in timeframe_states.values()]
        bull_count = states.count("BULLISH")
        bear_count = states.count("BEARISH")

        if bull_count > 0 and bear_count > 0:
            # 存在多头和空头混合
            total = len(states)
            if bull_count / total >= 0.4 and bear_count / total >= 0.4:
                conflict_detail = {
                    "type": ConflictType.MULTI_TIMEFRAME_CONFLICT,
                    "bull_count": bull_count,
                    "bear_count": bear_count,
                    "total_timeframes": total,
                    "bull_ratio": bull_count / total,
                    "bear_ratio": bear_count / total,
                    "timeframe_states": timeframe_states,
                }
                return ConflictType.MULTI_TIMEFRAME_CONFLICT, conflict_detail

        # 检测日线派发 vs 4小时吸筹冲突
        if d1_state == "BEARISH" and h4_state == "BULLISH":
            d1_conf = timeframe_states.get("D", {}).get("confidence", 0.0)
            h4_conf = timeframe_states.get("H4", {}).get("confidence", 0.0)

            # 日线派发 vs 4小时吸筹冲突：只要状态相反就视为冲突
            # 置信度差异作为冲突强度参考，但不作为冲突存在的前提条件
            conflict_detail = {
                "type": ConflictType.DISTRIBUTION_ACCUMULATION,
                "d1_state": d1_state,
                "d1_confidence": d1_conf,
                "h4_state": h4_state,
                "h4_confidence": h4_conf,
                "confidence_gap": abs(d1_conf - h4_conf),
                "timeframe_states": timeframe_states,
            }
            return ConflictType.DISTRIBUTION_ACCUMULATION, conflict_detail

        # 检测趋势 vs 回调冲突（大周期趋势 vs 小周期反向）
        weekly_state = timeframe_states.get("W", {}).get("state", "NEUTRAL")

        if weekly_state in ["BULLISH", "BEARISH"]:
            # 检查小周期是否与大周期反向
            conflicting_timeframes = []
            for tf in ["D", "H4", "H1"]:
                tf_state = timeframe_states.get(tf, {}).get("state", "NEUTRAL")
                tf_conf = timeframe_states.get(tf, {}).get("confidence", 0.0)

                if (
                    weekly_state == "BULLISH"
                    and tf_state == "BEARISH"
                    and tf_conf >= 0.5
                ) or (
                    weekly_state == "BEARISH"
                    and tf_state == "BULLISH"
                    and tf_conf >= 0.5
                ):
                    conflicting_timeframes.append(
                        {"timeframe": tf, "state": tf_state, "confidence": tf_conf}
                    )

            if conflicting_timeframes:
                conflict_detail = {
                    "type": ConflictType.TREND_CORRECTION,
                    "weekly_state": weekly_state,
                    "weekly_confidence": timeframe_states.get("W", {}).get(
                        "confidence", 0.0
                    ),
                    "conflicting_timeframes": conflicting_timeframes,
                    "timeframe_states": timeframe_states,
                }
                return ConflictType.TREND_CORRECTION, conflict_detail

        return ConflictType.NO_CONFLICT, {"timeframe_states": timeframe_states}

    def resolve_distribution_accumulation_conflict(
        self, conflict_detail: dict[str, Any], market_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        解决日线派发 vs 4小时吸筹冲突

        实现计划书中的辩证解决逻辑：
        1. 验证日线派发结构的完整性
        2. 分析4小时吸筹的真实性
        3. 应用周期权重过滤器
        4. 生成风险调整决策

        Args:
            conflict_detail: 冲突详情字典
            market_context: 市场上下文，包含成交量、波动率等信息

        Returns:
            解决决策字典
        """
        # 注意: d1_state, d1_confidence, h4_state, h4_confidence
        # 从 conflict_detail 中提取，由下游方法直接使用

        # 1. 验证日线派发结构的完整性
        d1_score = self._evaluate_distribution_structure(
            conflict_detail, market_context
        )

        # 2. 分析4小时吸筹的真实性
        h4_score = self._evaluate_accumulation_quality(conflict_detail, market_context)

        # 3. 应用周期权重过滤器（使用市场体制）
        regime = market_context.get("regime", "UNKNOWN")
        weights = self.weight_filter.get_weights(regime)
        d1_weight = weights.get(Timeframe.DAILY, 0.2)
        h4_weight = weights.get(Timeframe.H4, 0.18)

        # 加权得分
        weighted_score = (d1_score * d1_weight + h4_score * h4_weight) / (
            d1_weight + h4_weight
        )

        # 4. 辩证决策（基于计划书中的逻辑）
        if d1_score >= 0.7 and h4_score <= 0.4:
            # 日线派发主导，4小时吸筹虚弱
            resolution = {
                "primary_bias": ResolutionBias.BEARISH,
                "confidence": d1_score,
                "allowed_actions": ["SHORT_ONLY", "NO_LONG"],
                "risk_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "conflict_resolution": "D1_DOMINANT_WEAK_H4",
                "micro_confirmation_required": False,
                "reason": "日线派发结构完整，4小时吸筹质量差",
            }
        elif d1_score >= 0.6 and h4_score >= 0.7:
            # 双方都有力，需要微观确认
            resolution = {
                "primary_bias": ResolutionBias.NEUTRAL,
                "confidence": (d1_score + h4_score) / 2,
                "allowed_actions": ["SCALP_LONG", "REDUCED_SIZE"],
                "risk_multiplier": 0.5,
                "position_size_multiplier": self.max_position_size,
                "conflict_resolution": "CONFLICT_REQUIRES_M15_CONFIRMATION",
                "micro_confirmation_required": True,
                "reason": "日线派发与4小时吸筹均有力，需要微观确认",
            }
        elif d1_score <= 0.4 and h4_score >= 0.7:
            # 4小时吸筹主导
            resolution = {
                "primary_bias": ResolutionBias.BULLISH,
                "confidence": h4_score,
                "allowed_actions": ["LONG_ONLY", "NO_SHORT"],
                "risk_multiplier": 0.8,
                "position_size_multiplier": 0.8,
                "conflict_resolution": "H4_DOMINANT_WEAK_D1",
                "micro_confirmation_required": True,
                "reason": "4小时吸筹质量高，日线派发结构弱",
            }
        else:
            # 模糊冲突，延迟决策
            resolution = {
                "primary_bias": ResolutionBias.DEFERRED,
                "confidence": weighted_score,
                "allowed_actions": ["NO_TRADE", "OBSERVE_ONLY"],
                "risk_multiplier": 0.3,
                "position_size_multiplier": 0.0,
                "conflict_resolution": "DEFERRED_DECISION",
                "micro_confirmation_required": True,
                "reason": f"冲突模糊（D1={d1_score:.2f}, H4={h4_score:.2f}），需要更多确认",
            }

        # 添加详细评分信息
        resolution.update(
            {
                "d1_distribution_score": d1_score,
                "h4_accumulation_score": h4_score,
                "weighted_score": weighted_score,
                "weights_used": {"D1": d1_weight, "H4": h4_weight},
                "regime": regime,
            }
        )

        return resolution

    def _evaluate_distribution_structure(
        self, conflict_detail: dict[str, Any], market_context: dict[str, Any]
    ) -> float:
        """
        评估日线派发结构的完整性

        评分维度：
        1. 派发阶段节点完整性（PSY→BC→AR→ST→LPSY）
        2. 成交量特征（上涨缩量/下跌放量）
        3. 价格行为（高点降低，低点降低）
        4. 市场上下文（是否在历史高位）

        Returns:
            派发结构评分（0-1）
        """
        # 简化实现：基于置信度和市场上下文
        base_score = conflict_detail["d1_confidence"]

        # 检查成交量特征
        volume_analysis = market_context.get("volume_analysis", {})
        if volume_analysis.get("distribution_pattern", False):
            base_score *= 1.2  # 增强20%

        # 检查价格行为
        price_action = market_context.get("price_action", {})
        if price_action.get("lower_highs_lower_lows", False):
            base_score *= 1.1  # 增强10%

        # 检查市场位置
        market_position = market_context.get("market_position", "MID")
        if market_position == "HIGH":
            base_score *= 1.15  # 高位派发可能性增加

        return min(base_score, 1.0)

    def _evaluate_accumulation_quality(
        self, conflict_detail: dict[str, Any], market_context: dict[str, Any]
    ) -> float:
        """
        评估4小时吸筹的真实性

        评分维度：
        1. 吸筹阶段节点完整性（PS→SC→AR→ST→...）
        2. 成交量健康度（上涨放量/下跌缩量）
        3. 价格行为（低点抬高，测试支撑）
        4. 是否为"派发区间内的再吸筹"

        Returns:
            吸筹质量评分（0-1）
        """
        base_score = conflict_detail["h4_confidence"]

        # 检查成交量健康度
        volume_analysis = market_context.get("volume_analysis", {})
        if volume_analysis.get("accumulation_pattern", False):
            base_score *= 1.2  # 增强20%

        # 检查价格行为
        price_action = market_context.get("price_action", {})
        if price_action.get("higher_lows", False):
            base_score *= 1.1  # 增强10%

        # 检查是否为"再吸筹"（在派发区间内）
        # 如果是再吸筹，质量分数应降低
        if market_context.get("is_reaccumulation", False):
            base_score *= 0.7  # 降低30%

        return min(base_score, 1.0)

    def resolve_trend_correction_conflict(
        self, conflict_detail: dict[str, Any], market_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        解决趋势 vs 回调冲突

        决策原则：
        1. 趋势优先：大周期趋势通常比小周期回调更重要
        2. 回调深度：浅回调可能是趋势延续，深回调可能反转
        3. 成交量验证：回调是否缩量，反弹是否放量
        4. 结构完整性：回调是否破坏关键结构位

        Args:
            conflict_detail: 冲突详情字典
            market_context: 市场上下文

        Returns:
            解决决策字典
        """
        weekly_state = conflict_detail["weekly_state"]
        weekly_confidence = conflict_detail["weekly_confidence"]
        conflicting_tfs = conflict_detail["conflicting_timeframes"]

        # 分析回调深度和成交量
        correction_depth = market_context.get("correction_depth", 0.0)
        volume_on_correction = market_context.get("volume_on_correction", "NORMAL")

        # 决策逻辑
        if weekly_confidence >= 0.7:
            # 强趋势
            if correction_depth <= 0.382:  # 浅回调（小于38.2%）
                # 趋势延续可能性高
                resolution = {
                    "primary_bias": ResolutionBias.BULLISH
                    if weekly_state == "BULLISH"
                    else ResolutionBias.BEARISH,
                    "confidence": weekly_confidence,
                    "allowed_actions": ["TREND_FOLLOWING", "IGNORE_CORRECTION"],
                    "risk_multiplier": 0.9,
                    "position_size_multiplier": 0.9,
                    "conflict_resolution": "TREND_DOMINANT_SHALLOW_CORRECTION",
                    "micro_confirmation_required": False,
                    "reason": f"强{weekly_state}趋势，浅回调（{correction_depth:.1%}），趋势延续可能性高",
                }
            elif volume_on_correction == "LOW_VOLUME":
                # 缩量回调，健康修正
                resolution = {
                    "primary_bias": ResolutionBias.BULLISH
                    if weekly_state == "BULLISH"
                    else ResolutionBias.BEARISH,
                    "confidence": weekly_confidence * 0.8,
                    "allowed_actions": ["TREND_FOLLOWING", "ADD_ON_CORRECTION"],
                    "risk_multiplier": 0.8,
                    "position_size_multiplier": 0.8,
                    "conflict_resolution": "TREND_DOMINANT_LOW_VOLUME_CORRECTION",
                    "micro_confirmation_required": True,
                    "reason": f"{weekly_state}趋势，缩量回调，健康修正",
                }
            else:
                # 放量深回调，可能反转
                resolution = {
                    "primary_bias": ResolutionBias.NEUTRAL,
                    "confidence": 0.5,
                    "allowed_actions": ["REDUCED_SIZE", "WAIT_FOR_CONFIRMATION"],
                    "risk_multiplier": 0.4,
                    "position_size_multiplier": self.max_position_size * 0.5,
                    "conflict_resolution": "TREND_WITH_DEEP_CORRECTION",
                    "micro_confirmation_required": True,
                    "reason": f"{weekly_state}趋势，但回调较深（{correction_depth:.1%}）且放量，需谨慎",
                }
        else:
            # 弱趋势，回调可能反转
            resolution = {
                "primary_bias": ResolutionBias.NEUTRAL,
                "confidence": 0.4,
                "allowed_actions": ["NO_TRADE", "OBSERVE_ONLY"],
                "risk_multiplier": 0.3,
                "position_size_multiplier": 0.0,
                "conflict_resolution": "WEAK_TREND_CONFLICT",
                "micro_confirmation_required": True,
                "reason": f"弱{weekly_state}趋势，与小周期反向信号冲突，需要更多确认",
            }

        resolution.update(
            {
                "weekly_state": weekly_state,
                "weekly_confidence": weekly_confidence,
                "correction_depth": correction_depth,
                "volume_on_correction": volume_on_correction,
                "conflicting_timeframes_count": len(conflicting_tfs),
            }
        )

        return resolution

    def resolve_multi_timeframe_conflict(
        self, conflict_detail: dict[str, Any], market_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        解决多时间框架混合冲突

        使用周期权重过滤器进行加权决策

        Args:
            conflict_detail: 冲突详情字典
            market_context: 市场上下文

        Returns:
            解决决策字典
        """
        timeframe_states = conflict_detail["timeframe_states"]
        regime = market_context.get("regime", "UNKNOWN")

        # 使用周期权重过滤器进行加权决策
        decision = self.weight_filter.get_weighted_decision(timeframe_states, regime)

        # 根据加权结果生成解决决策
        primary_bias = decision["primary_bias"]
        confidence = decision["confidence"]

        if confidence >= 0.6:
            # 较高置信度
            if primary_bias in ["BULLISH", "BEARISH"]:
                resolution = {
                    "primary_bias": ResolutionBias[primary_bias],
                    "confidence": confidence,
                    "allowed_actions": [f"{primary_bias}_ONLY", "NORMAL_SIZE"],
                    "risk_multiplier": 0.8,
                    "position_size_multiplier": 0.8,
                    "conflict_resolution": "WEIGHTED_CLEAR_BIAS",
                    "micro_confirmation_required": False,
                    "reason": f"加权决策显示清晰{primary_bias}偏向（置信度{confidence:.2f}）",
                }
            else:
                resolution = {
                    "primary_bias": ResolutionBias.NEUTRAL,
                    "confidence": confidence,
                    "allowed_actions": ["REDUCED_SIZE", "SCALP_ONLY"],
                    "risk_multiplier": 0.6,
                    "position_size_multiplier": self.max_position_size,
                    "conflict_resolution": "WEIGHTED_NEUTRAL",
                    "micro_confirmation_required": True,
                    "reason": f"加权决策显示中性偏向（置信度{confidence:.2f}）",
                }
        else:
            # 低置信度，延迟决策
            resolution = {
                "primary_bias": ResolutionBias.DEFERRED,
                "confidence": confidence,
                "allowed_actions": ["NO_TRADE", "OBSERVE_ONLY"],
                "risk_multiplier": 0.3,
                "position_size_multiplier": 0.0,
                "conflict_resolution": "LOW_CONFIDENCE_DEFERRED",
                "micro_confirmation_required": True,
                "reason": f"加权决策置信度低（{confidence:.2f}），需要更多确认",
            }

        # 添加加权决策详情
        resolution.update(
            {
                "weighted_decision": decision,
                "regime": regime,
                "bull_ratio": conflict_detail.get("bull_ratio", 0.0),
                "bear_ratio": conflict_detail.get("bear_ratio", 0.0),
            }
        )

        return resolution

    def resolve_conflict(
        self,
        timeframe_states: dict[str, dict[str, Any]],
        market_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        主解决函数：检测并解决冲突

        Args:
            timeframe_states: 各时间框架状态字典
            market_context: 市场上下文

        Returns:
            解决决策字典
        """
        # 1. 检测冲突
        conflict_type, conflict_detail = self.detect_conflict(timeframe_states)

        # 2. 记录冲突
        conflict_record = {
            "timestamp": market_context.get("timestamp", "未知时间"),
            "conflict_type": conflict_type.value,
            "conflict_detail": conflict_detail,
            "market_context": market_context,
        }
        self.resolution_history.append(conflict_record)

        # 3. 根据冲突类型解决
        if conflict_type == ConflictType.NO_CONFLICT:
            # 无冲突，使用加权决策
            regime = market_context.get("regime", "UNKNOWN")
            decision = self.weight_filter.get_weighted_decision(
                timeframe_states, regime
            )

            resolution = {
                "conflict_type": "NO_CONFLICT",
                "primary_bias": ResolutionBias[decision["primary_bias"]],
                "confidence": decision["confidence"],
                "allowed_actions": ["NORMAL_TRADING"],
                "risk_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "conflict_resolution": "NO_CONFLICT_CLEAR_SIGNAL",
                "micro_confirmation_required": False,
                "reason": "多周期信号一致，无冲突",
                "weighted_decision": decision,
            }

        elif conflict_type == ConflictType.DISTRIBUTION_ACCUMULATION:
            resolution = self.resolve_distribution_accumulation_conflict(
                conflict_detail, market_context
            )
            resolution["conflict_type"] = "DISTRIBUTION_ACCUMULATION"

        elif conflict_type == ConflictType.TREND_CORRECTION:
            resolution = self.resolve_trend_correction_conflict(
                conflict_detail, market_context
            )
            resolution["conflict_type"] = "TREND_CORRECTION"

        elif conflict_type == ConflictType.MULTI_TIMEFRAME_CONFLICT:
            resolution = self.resolve_multi_timeframe_conflict(
                conflict_detail, market_context
            )
            resolution["conflict_type"] = "MULTI_TIMEFRAME_CONFLICT"

        else:
            # 未知冲突类型
            resolution = {
                "conflict_type": "UNKNOWN",
                "primary_bias": ResolutionBias.DEFERRED,
                "confidence": 0.0,
                "allowed_actions": ["NO_TRADE", "OBSERVE_ONLY"],
                "risk_multiplier": 0.1,
                "position_size_multiplier": 0.0,
                "conflict_resolution": "UNKNOWN_CONFLICT_TYPE",
                "micro_confirmation_required": True,
                "reason": f"未知冲突类型: {conflict_type}",
            }

        # 4. 添加元数据
        resolution.update(
            {
                "timestamp": market_context.get("timestamp", "未知时间"),
                "timeframe_states_summary": {
                    tf: {
                        "state": s.get("state", "NEUTRAL"),
                        "confidence": s.get("confidence", 0.0),
                    }
                    for tf, s in timeframe_states.items()
                },
                "market_regime": market_context.get("regime", "UNKNOWN"),
            }
        )

        # 5. 记录解决结果
        conflict_record["resolution"] = resolution

        return resolution

    def get_resolution_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        获取冲突解决历史

        Args:
            limit: 返回记录数量限制

        Returns:
            冲突解决历史列表
        """
        return self.resolution_history[-limit:]

    def clear_history(self) -> None:
        """清空解决历史"""
        self.resolution_history.clear()


# 使用示例
if __name__ == "__main__":
    # 创建冲突解决管理器
    resolver = ConflictResolutionManager()

    # 示例1：日线派发 vs 4小时吸筹冲突
    timeframe_states_1 = {
        "W": {"state": "NEUTRAL", "confidence": 0.5},
        "D": {"state": "BEARISH", "confidence": 0.8},
        "H4": {"state": "BULLISH", "confidence": 0.7},
        "H1": {"state": "NEUTRAL", "confidence": 0.5},
        "M15": {"state": "BULLISH", "confidence": 0.6},
        "M5": {"state": "BULLISH", "confidence": 0.7},
    }

    market_context_1 = {
        "regime": "RANGING",
        "volume_analysis": {
            "distribution_pattern": True,
            "accumulation_pattern": False,
        },
        "price_action": {"lower_highs_lower_lows": True, "higher_lows": False},
        "market_position": "HIGH",
        "timestamp": "2024-01-20 10:00:00",
    }

    resolution_1 = resolver.resolve_conflict(timeframe_states_1, market_context_1)

    # 示例2：无冲突场景
    timeframe_states_2 = {
        "W": {"state": "BULLISH", "confidence": 0.8},
        "D": {"state": "BULLISH", "confidence": 0.7},
        "H4": {"state": "BULLISH", "confidence": 0.6},
        "H1": {"state": "BULLISH", "confidence": 0.5},
        "M15": {"state": "BULLISH", "confidence": 0.6},
        "M5": {"state": "BULLISH", "confidence": 0.7},
    }

    market_context_2 = {"regime": "TRENDING", "timestamp": "2024-01-20 10:00:00"}

    resolution_2 = resolver.resolve_conflict(timeframe_states_2, market_context_2)

    # 获取解决历史
