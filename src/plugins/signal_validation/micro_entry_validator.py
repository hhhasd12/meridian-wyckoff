"""
微观入场验证器模块
实现15分钟/5分钟级别的精确入场点确认，采用"结构确认"替代"时间确认"

设计原则：
1. 结构确认优先：价格突破H4关键结构位 + M15站稳3根K线
2. 成交量健康：突破放量/站稳缩量
3. 微观威科夫结构：M15/M5级别的威科夫微观形态识别
4. 多时间框架对齐：确保微观入场与宏观方向一致
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd


class EntrySignalType(Enum):
    """入场信号类型枚举"""

    AGGRESSIVE_ENTRY = "AGGRESSIVE_ENTRY"  # 激进入场（基于微观预判）
    CONFIRMED_ENTRY = "CONFIRMED_ENTRY"  # 确认入场（结构确认完成）
    REJECTED = "REJECTED"  # 拒绝入场
    DEFERRED = "DEFERRED"  # 延迟决策（需要更多确认）


class StructureType(Enum):
    """关键结构类型枚举"""

    CREEK = "CREEK"  # 溪流（阻力位）
    ICE = "ICE"  # 冰层（支撑位）
    TRENDLINE = "TRENDLINE"  # 趋势线
    PIVOT = "PIVOT"  # 枢轴点
    FVG = "FVG"  # 公允价值缺口
    UNKNOWN = "UNKNOWN"  # 未知结构


class MicroEntryValidator:
    """
    微观入场验证器

    功能：
    1. 验证H4关键结构位的突破与站稳
    2. 分析M15/M5级别的成交量健康度
    3. 识别微观威科夫结构（弹簧、测试等）
    4. 生成精确入场信号和风险管理参数
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化微观入场验证器

        Args:
            config: 配置字典，包含以下参数：
                - min_confirmation_bars: 最小确认K线数（默认3）
                - volume_threshold: 成交量阈值（突破时至少1.5倍平均）
                - structure_types: 关注的关键结构类型列表
                - max_slippage_pct: 最大滑点百分比（默认0.1%）
                - require_alignment: 是否需要多时间框架对齐（默认True）
        """
        self.config = config or {}

        # 基础配置
        self.min_confirmation_bars = self.config.get("min_confirmation_bars", 3)
        self.volume_threshold = self.config.get("volume_threshold", 1.5)
        self.max_slippage_pct = self.config.get("max_slippage_pct", 0.001)  # 0.1%
        self.require_alignment = self.config.get("require_alignment", True)

        # 关注的结构类型
        self.structure_types = self.config.get(
            "structure_types", ["CREEK", "ICE", "TRENDLINE", "PIVOT", "FVG"]
        )

        # 验证历史记录
        self.validation_history = []

        # 当前监控的关键结构
        self.monitored_structures = {}

    def validate_entry(
        self,
        h4_structure: dict[str, Any],  # H4关键结构信息
        m15_data: pd.DataFrame,  # M15 K线数据（至少10根）
        m5_data: Optional[pd.DataFrame],  # M5 K线数据（可选，用于精确点位）
        macro_bias: str,  # 宏观偏向（"BULLISH", "BEARISH", "NEUTRAL"）
        market_context: dict[str, Any],  # 市场上下文
    ) -> dict[str, Any]:
        """
        验证微观入场条件

        验证流程：
        1. 检查H4关键结构位是否有效
        2. 验证M15级别的突破与站稳
        3. 分析成交量健康度
        4. 检查微观威科夫结构
        5. 验证多时间框架对齐
        6. 生成入场信号和风险管理参数

        Args:
            h4_structure: H4关键结构信息
            m15_data: M15 K线数据（需要包含OHLCV列）
            m5_data: M5 K线数据（可选）
            macro_bias: 宏观偏向
            market_context: 市场上下文

        Returns:
            验证结果字典
        """
        validation_result = {
            "timestamp": market_context.get("timestamp", datetime.now()),
            "h4_structure": h4_structure,
            "macro_bias": macro_bias,
            "market_regime": market_context.get("regime", "UNKNOWN"),
        }

        # 1. 检查H4关键结构位是否有效
        structure_valid, structure_reason = self._validate_h4_structure(h4_structure)
        if not structure_valid:
            result = self._create_rejected_result(
                validation_result, f"H4结构无效: {structure_reason}"
            )
            self.validation_history.append(result)
            return result

        # 2. 验证M15级别的突破与站稳
        breakout_valid, breakout_details = self._validate_breakout_confirmation(
            h4_structure, m15_data
        )
        if not breakout_valid:
            result = self._create_deferred_result(
                validation_result,
                f"突破确认不足: {breakout_details.get('reason', '未知原因')}",
                breakout_details,
            )
            self.validation_history.append(result)
            return result

        # 3. 分析成交量健康度
        volume_valid, volume_analysis = self._analyze_volume_health(
            h4_structure, m15_data, breakout_details
        )
        if not volume_valid:
            result = self._create_deferred_result(
                validation_result,
                f"成交量不健康: {volume_analysis.get('reason', '未知原因')}",
                {**breakout_details, **volume_analysis},
            )
            self.validation_history.append(result)
            return result

        # 4. 检查微观威科夫结构
        wyckoff_valid, wyckoff_analysis = self._analyze_micro_wyckoff(
            h4_structure, m15_data, m5_data, macro_bias
        )

        # 5. 验证多时间框架对齐（如果需要）
        alignment_valid = True
        if self.require_alignment:
            alignment_valid, _alignment_analysis = self._validate_timeframe_alignment(
                macro_bias, h4_structure, m15_data, market_context
            )

        # 6. 综合评估
        overall_score = self._calculate_overall_score(
            breakout_details, volume_analysis, wyckoff_analysis, alignment_valid
        )

        # 7. 生成入场信号
        if overall_score >= 0.7 and alignment_valid:
            # 确认入场信号
            signal_type = EntrySignalType.CONFIRMED_ENTRY
            signal_reason = "结构确认完成，成交量健康，多时间框架对齐"
        elif overall_score >= 0.5 and wyckoff_valid:
            # 激进入场信号（基于微观威科夫结构）
            signal_type = EntrySignalType.AGGRESSIVE_ENTRY
            signal_reason = "微观威科夫结构良好，但结构确认未完成"
        elif overall_score >= 0.4:
            # 延迟决策
            signal_type = EntrySignalType.DEFERRED
            signal_reason = f"综合评分不足（{overall_score:.2f}），需要更多确认"
        else:
            # 拒绝入场
            result = self._create_rejected_result(
                validation_result, f"综合评分过低（{overall_score:.2f}），拒绝入场"
            )
            self.validation_history.append(result)
            return result

        # 8. 生成入场参数
        entry_params = self._generate_entry_parameters(
            h4_structure, m15_data, m5_data, overall_score, signal_type
        )

        # 9. 构建最终结果
        result = {
            **validation_result,
            "signal_type": signal_type.value,
            "signal_reason": signal_reason,
            "overall_score": overall_score,
            "breakout_analysis": breakout_details,
            "volume_analysis": volume_analysis,
            "wyckoff_analysis": wyckoff_analysis,
            "alignment_valid": alignment_valid,
            "entry_parameters": entry_params,
            "validation_timestamp": datetime.now(),
        }

        # 10. 记录验证历史
        self.validation_history.append(result)

        return result

    def _validate_h4_structure(self, h4_structure: dict[str, Any]) -> tuple[bool, str]:
        """验证H4关键结构位是否有效"""
        structure_type = h4_structure.get("type", "UNKNOWN")
        price_level = h4_structure.get("price_level", 0.0)
        confidence = h4_structure.get("confidence", 0.0)

        # 检查结构类型
        if structure_type not in self.structure_types:
            return False, f"不支持的结构类型: {structure_type}"

        # 检查价格水平有效性
        if price_level <= 0:
            return False, f"无效的价格水平: {price_level}"

        # 检查置信度
        if confidence < 0.6:
            return False, f"结构置信度不足: {confidence:.2f}"

        # 检查结构是否过期（如果提供时间戳）
        timestamp = h4_structure.get("timestamp")
        if timestamp:
            try:
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age_hours = (datetime.now() - timestamp).total_seconds() / 3600
                if age_hours > 48:  # 超过48小时的结构可能失效
                    return False, f"结构已过期（{age_hours:.1f}小时）"
            except Exception:
                pass

        return True, "H4结构有效"

    def _validate_breakout_confirmation(
        self, h4_structure: dict[str, Any], m15_data: pd.DataFrame
    ) -> tuple[bool, dict[str, Any]]:
        """
        验证M15级别的突破与站稳

        条件：
        1. 价格突破H4关键结构位
        2. 突破后至少站稳N根K线（默认3根）
        3. 站稳期间未跌破结构位（允许小幅回踩）
        """
        if len(m15_data) < self.min_confirmation_bars + 2:
            return False, {
                "reason": f"M15数据不足，需要至少{self.min_confirmation_bars + 2}根K线"
            }

        h4_structure.get("type", "UNKNOWN")
        price_level = h4_structure.get("price_level", 0.0)
        direction = h4_structure.get(
            "direction", "UNKNOWN"
        )  # "RESISTANCE" or "SUPPORT"

        # 获取最近K线数据
        recent_data = m15_data.tail(self.min_confirmation_bars + 2)
        closes = recent_data["close"].values
        highs = recent_data["high"].values
        lows = recent_data["low"].values

        # 根据方向检查突破
        if direction == "RESISTANCE":
            # 阻力位突破：需要价格上涨突破
            # 检查最近一根K线是否突破
            latest_close = closes[-1]
            latest_high = highs[-1]

            if latest_high <= price_level:
                return False, {
                    "reason": f"价格未突破阻力位 {price_level}，最高价 {latest_high}",
                    "latest_close": latest_close,
                    "latest_high": latest_high,
                    "price_level": price_level,
                }

            # 检查突破后是否站稳
            # 获取突破后的K线（不包括突破K线本身）
            post_breakout_closes = closes[-(self.min_confirmation_bars) :]
            post_breakout_lows = lows[-(self.min_confirmation_bars) :]

            # 检查是否站稳（收盘价保持在结构位之上）
            confirmation_count = 0
            for i in range(len(post_breakout_closes)):
                if post_breakout_closes[i] > price_level * 0.995:  # 允许0.5%回踩
                    confirmation_count += 1

            if confirmation_count >= self.min_confirmation_bars:
                return True, {
                    "breakout_type": "RESISTANCE_BREAKOUT",
                    "breakout_price": latest_high,
                    "confirmation_bars": confirmation_count,
                    "min_close_above": min(post_breakout_closes),
                    "max_retracement_pct": (price_level - min(post_breakout_lows))
                    / price_level
                    * 100
                    if len(post_breakout_lows) > 0
                    else 0,
                }
            return False, {
                "reason": f"突破后站稳不足，仅{confirmation_count}/{self.min_confirmation_bars}根K线站稳",
                "breakout_price": latest_high,
                "confirmation_bars": confirmation_count,
                "required_bars": self.min_confirmation_bars,
            }

        if direction == "SUPPORT":
            # 支撑位突破：需要价格下跌突破（用于做空）
            latest_close = closes[-1]
            latest_low = lows[-1]

            if latest_low >= price_level:
                return False, {
                    "reason": f"价格未突破支撑位 {price_level}，最低价 {latest_low}",
                    "latest_close": latest_close,
                    "latest_low": latest_low,
                    "price_level": price_level,
                }

            # 检查突破后是否站稳
            post_breakout_closes = closes[-(self.min_confirmation_bars) :]
            post_breakout_highs = highs[-(self.min_confirmation_bars) :]

            confirmation_count = 0
            for i in range(len(post_breakout_closes)):
                if post_breakout_closes[i] < price_level * 1.005:  # 允许0.5%回踩
                    confirmation_count += 1

            if confirmation_count >= self.min_confirmation_bars:
                return True, {
                    "breakout_type": "SUPPORT_BREAKOUT",
                    "breakout_price": latest_low,
                    "confirmation_bars": confirmation_count,
                    "max_close_below": max(post_breakout_closes),
                    "max_retracement_pct": (max(post_breakout_highs) - price_level)
                    / price_level
                    * 100
                    if len(post_breakout_highs) > 0
                    else 0,
                }
            return False, {
                "reason": f"突破后站稳不足，仅{confirmation_count}/{self.min_confirmation_bars}根K线站稳",
                "breakout_price": latest_low,
                "confirmation_bars": confirmation_count,
                "required_bars": self.min_confirmation_bars,
            }

        return False, {"reason": f"未知的突破方向: {direction}"}

    def _analyze_volume_health(
        self,
        h4_structure: dict[str, Any],
        m15_data: pd.DataFrame,
        breakout_details: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """分析成交量健康度"""
        if len(m15_data) < 20:
            return False, {"reason": "数据不足进行成交量分析"}

        # 计算成交量平均值
        volumes = m15_data["volume"].values
        avg_volume = np.mean(volumes[-20:])  # 最近20根K线的平均成交量

        # 获取突破期间的成交量
        breakout_details.get("breakout_type", "")
        confirmation_bars = breakout_details.get("confirmation_bars", 0)

        if confirmation_bars == 0:
            return False, {"reason": "无确认K线"}

        # 突破K线（确认期之前的一根）
        if len(volumes) >= confirmation_bars + 1:
            breakout_volume = volumes[-(confirmation_bars + 1)]
            post_breakout_volumes = volumes[-confirmation_bars:]

            # 突破成交量应该放大
            volume_ratio_breakout = (
                breakout_volume / avg_volume if avg_volume > 0 else 1.0
            )

            # 确认期成交量应该收缩（健康调整）
            avg_post_volume = (
                np.mean(post_breakout_volumes) if len(post_breakout_volumes) > 0 else 0
            )
            volume_ratio_post = avg_post_volume / avg_volume if avg_volume > 0 else 1.0

            # 评估成交量健康度
            volume_healthy = True
            reasons = []

            if volume_ratio_breakout < self.volume_threshold:
                volume_healthy = False
                reasons.append(
                    f"突破成交量不足（{volume_ratio_breakout:.2f}倍，要求>{self.volume_threshold}倍）"
                )

            if volume_ratio_post > 1.2:
                # 确认期成交量仍然很大，可能是不健康的表现
                reasons.append(
                    f"确认期成交量偏大（{volume_ratio_post:.2f}倍），可能缺乏共识"
                )

            analysis = {
                "breakout_volume_ratio": volume_ratio_breakout,
                "post_breakout_volume_ratio": volume_ratio_post,
                "avg_volume": avg_volume,
                "breakout_volume": breakout_volume,
                "avg_post_volume": avg_post_volume,
                "volume_healthy": volume_healthy,
                "reasons": reasons,
            }

            if volume_healthy and not reasons:
                return True, analysis
            return False, {**analysis, "reason": "; ".join(reasons)}

        return False, {"reason": "成交量数据不足"}

    def _analyze_micro_wyckoff(
        self,
        h4_structure: dict[str, Any],
        m15_data: pd.DataFrame,
        m5_data: Optional[pd.DataFrame],
        macro_bias: str,
    ) -> tuple[bool, dict[str, Any]]:
        """分析微观威科夫结构"""
        # 简化实现：检查常见的微观威科夫形态
        if len(m15_data) < 10:
            return False, {"reason": "M15数据不足进行威科夫分析"}

        # 获取价格和成交量数据
        closes = m15_data["close"].values[-10:]
        highs = m15_data["high"].values[-10:]
        lows = m15_data["low"].values[-10:]
        m15_data["volume"].values[-10:]

        # 检查弹簧（Spring）或测试（Test）形态
        spring_detected = False
        test_detected = False
        lps_detected = False

        # 简化弹簧检测：价格快速跌破支撑后立即收回
        if len(closes) >= 5:
            # 检查最近5根K线
            recent_lows = lows[-5:]
            recent_closes = closes[-5:]

            # 寻找低点降低但收盘收回的形态
            for i in range(1, len(recent_lows)):
                if (
                    recent_lows[i] < recent_lows[i - 1] * 0.995
                    and recent_closes[i] > recent_lows[i - 1]
                ):
                    spring_detected = True
                    break

        # 检查LPS（最后支撑点）：在上升趋势中的回调低点
        if macro_bias == "BULLISH" and len(closes) >= 3:
            if closes[-1] > closes[-2] > closes[-3] and lows[-1] > lows[-2]:
                lps_detected = True

        # 综合评估
        wyckoff_score = 0.0
        if spring_detected:
            wyckoff_score += 0.4
        if test_detected:
            wyckoff_score += 0.3
        if lps_detected:
            wyckoff_score += 0.3

        analysis = {
            "spring_detected": spring_detected,
            "test_detected": test_detected,
            "lps_detected": lps_detected,
            "wyckoff_score": wyckoff_score,
            "price_action": {
                "recent_closes": closes.tolist(),
                "recent_highs": highs.tolist(),
                "recent_lows": lows.tolist(),
            },
        }

        # 如果M5数据可用，进行更精确的分析
        if m5_data is not None and len(m5_data) >= 20:
            m5_analysis = self._analyze_m5_wyckoff(m5_data)
            analysis["m5_analysis"] = m5_analysis
            wyckoff_score = max(wyckoff_score, m5_analysis.get("wyckoff_score", 0.0))

        valid = wyckoff_score >= 0.3
        analysis["wyckoff_score"] = wyckoff_score
        analysis["wyckoff_valid"] = valid

        return valid, analysis

    def _analyze_m5_wyckoff(self, m5_data: pd.DataFrame) -> dict[str, Any]:
        """分析M5级别的威科夫结构（更精确的入场点）"""
        if len(m5_data) < 20:
            return {"reason": "M5数据不足"}

        # 简化实现：检查价格行为和成交量
        closes = m5_data["close"].values[-10:]
        volumes = m5_data["volume"].values[-10:]

        # 检查成交量分布
        avg_volume = np.mean(volumes)
        volume_ratios = (
            volumes / avg_volume if avg_volume > 0 else np.ones_like(volumes)
        )

        # 检查价格上涨是否伴随成交量放大
        volume_confirmation = 0
        for i in range(1, len(closes)):
            if closes[i] > closes[i - 1] and volume_ratios[i] > 1.2:
                volume_confirmation += 1

        return {
            "volume_confirmation_count": volume_confirmation,
            "avg_volume_ratio": np.mean(volume_ratios),
            "price_trend": "UP" if closes[-1] > closes[0] else "DOWN",
            "wyckoff_score": min(volume_confirmation / 5, 1.0),  # 最多5次确认
        }


    def _validate_timeframe_alignment(
        self,
        macro_bias: str,
        h4_structure: dict[str, Any],
        m15_data: pd.DataFrame,
        market_context: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """验证多时间框架对齐"""
        # 检查H4结构与宏观偏向是否一致
        structure_direction = h4_structure.get("direction", "UNKNOWN")

        alignment_score = 0.0
        reasons = []

        if macro_bias == "BULLISH" and structure_direction == "RESISTANCE":
            # 看涨偏向 + 阻力突破 = 良好对齐
            alignment_score += 0.5
            reasons.append("看涨偏向与阻力突破对齐")
        elif macro_bias == "BEARISH" and structure_direction == "SUPPORT":
            # 看跌偏向 + 支撑突破 = 良好对齐
            alignment_score += 0.5
            reasons.append("看跌偏向与支撑突破对齐")
        else:
            reasons.append(
                f"宏观偏向{macro_bias}与结构方向{structure_direction}不完全对齐"
            )

        # 检查市场体制
        regime = market_context.get("regime", "UNKNOWN")
        if regime == "TRENDING" and macro_bias != "NEUTRAL":
            alignment_score += 0.3
            reasons.append(f"趋势市与{macro_bias}偏向对齐")
        elif regime == "RANGING":
            alignment_score += 0.2
            reasons.append("盘整市，对齐要求降低")

        # 检查价格是否在关键水平附近盘整（健康表现）
        if len(m15_data) >= 5:
            recent_closes = m15_data["close"].values[-5:]
            price_range = max(recent_closes) - min(recent_closes)
            avg_price = np.mean(recent_closes)
            range_pct = price_range / avg_price * 100 if avg_price > 0 else 0

            if range_pct < 1.0:  # 价格波动小于1%
                alignment_score += 0.2
                reasons.append("价格在关键水平附近窄幅盘整，健康表现")

        analysis = {
            "alignment_score": alignment_score,
            "reasons": reasons,
            "macro_bias": macro_bias,
            "structure_direction": structure_direction,
            "market_regime": regime,
        }

        # 对齐阈值
        aligned = alignment_score >= 0.5
        analysis["aligned"] = aligned

        return aligned, analysis

    def _calculate_overall_score(
        self,
        breakout_analysis: dict[str, Any],
        volume_analysis: dict[str, Any],
        wyckoff_analysis: dict[str, Any],
        alignment_valid: bool,
    ) -> float:
        """计算综合评分"""
        weights = {
            "breakout": 0.4,  # 突破确认权重
            "volume": 0.3,  # 成交量权重
            "wyckoff": 0.2,  # 威科夫结构权重
            "alignment": 0.1,  # 时间框架对齐权重
        }

        # 突破评分（基于确认K线数）
        confirmation_bars = breakout_analysis.get("confirmation_bars", 0)
        required_bars = self.min_confirmation_bars
        breakout_score = min(confirmation_bars / required_bars, 1.0)

        # 成交量评分
        volume_healthy = volume_analysis.get("volume_healthy", False)
        volume_score = 1.0 if volume_healthy else 0.3

        # 威科夫结构评分
        wyckoff_score = wyckoff_analysis.get("wyckoff_score", 0.0)

        # 对齐评分
        alignment_score = 1.0 if alignment_valid else 0.3

        # 加权平均
        return (
            breakout_score * weights["breakout"]
            + volume_score * weights["volume"]
            + wyckoff_score * weights["wyckoff"]
            + alignment_score * weights["alignment"]
        )


    def _generate_entry_parameters(
        self,
        h4_structure: dict[str, Any],
        m15_data: pd.DataFrame,
        m5_data: Optional[pd.DataFrame],
        overall_score: float,
        signal_type: EntrySignalType,
    ) -> dict[str, Any]:
        """生成入场参数"""
        structure_type = h4_structure.get("type", "UNKNOWN")
        price_level = h4_structure.get("price_level", 0.0)
        direction = h4_structure.get("direction", "UNKNOWN")

        # 确定入场方向
        if direction == "RESISTANCE":
            entry_direction = "LONG"
            entry_price = (
                m15_data["close"].iloc[-1] if len(m15_data) > 0 else price_level
            )
            stop_loss = price_level * 0.99  # 1% below resistance
            take_profit = entry_price * 1.03  # 3% profit target
        elif direction == "SUPPORT":
            entry_direction = "SHORT"
            entry_price = (
                m15_data["close"].iloc[-1] if len(m15_data) > 0 else price_level
            )
            stop_loss = price_level * 1.01  # 1% above support
            take_profit = entry_price * 0.97  # 3% profit target
        else:
            entry_direction = "NEUTRAL"
            entry_price = price_level
            stop_loss = price_level * 0.99
            take_profit = price_level * 1.01

        # 根据信号类型调整仓位大小
        if signal_type == EntrySignalType.CONFIRMED_ENTRY:
            position_size_multiplier = 1.0
            risk_multiplier = 1.0
        elif signal_type == EntrySignalType.AGGRESSIVE_ENTRY:
            position_size_multiplier = 0.5
            risk_multiplier = 0.7
        else:
            position_size_multiplier = 0.0
            risk_multiplier = 0.0

        # 根据综合评分微调
        position_size_multiplier *= min(overall_score * 1.2, 1.0)

        # 滑点调整
        slippage_adjustment = 1.0 + self.max_slippage_pct

        return {
            "entry_direction": entry_direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_size_multiplier": position_size_multiplier,
            "risk_multiplier": risk_multiplier,
            "slippage_adjustment": slippage_adjustment,
            "risk_reward_ratio": abs(take_profit - entry_price)
            / abs(stop_loss - entry_price)
            if abs(stop_loss - entry_price) > 0
            else 0,
            "structure_type": structure_type,
            "original_price_level": price_level,
        }

    def _create_rejected_result(
        self, base_result: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        """创建拒绝入场结果"""
        return {
            **base_result,
            "signal_type": EntrySignalType.REJECTED.value,
            "signal_reason": reason,
            "overall_score": 0.0,
            "entry_parameters": {
                "entry_direction": "NONE",
                "position_size_multiplier": 0.0,
                "risk_multiplier": 0.0,
            },
            "validation_timestamp": datetime.now(),
        }

    def _create_deferred_result(
        self, base_result: dict[str, Any], reason: str, analysis_details: dict[str, Any]
    ) -> dict[str, Any]:
        """创建延迟决策结果"""
        return {
            **base_result,
            "signal_type": EntrySignalType.DEFERRED.value,
            "signal_reason": reason,
            "overall_score": analysis_details.get("score", 0.3),
            "analysis_details": analysis_details,
            "entry_parameters": {
                "entry_direction": "NONE",
                "position_size_multiplier": 0.0,
                "risk_multiplier": 0.0,
            },
            "validation_timestamp": datetime.now(),
        }

    def get_validation_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取验证历史"""
        return self.validation_history[-limit:]

    def clear_history(self) -> None:
        """清空验证历史"""
        self.validation_history.clear()


# 使用示例
if __name__ == "__main__":
    # 创建验证器
    validator = MicroEntryValidator()

    # 模拟H4关键结构
    h4_structure = {
        "type": "CREEK",
        "price_level": 45000.0,
        "direction": "RESISTANCE",
        "confidence": 0.8,
        "timestamp": datetime.now().isoformat(),
    }

    # 模拟M15数据
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-20", periods=20, freq="15min")
    base_price = 44800.0
    prices = base_price + np.random.normal(0, 100, 20)
    volumes = np.random.randint(1000, 5000, 20)

    m15_data = pd.DataFrame(
        {
            "open": prices - 10,
            "high": prices + 20,
            "low": prices - 20,
            "close": prices,
            "volume": volumes,
        },
        index=dates,
    )

    # 手动调整最后几根K线以模拟突破
    m15_data.loc[m15_data.index[-1], "high"] = 45100.0
    m15_data.loc[m15_data.index[-1], "close"] = 45050.0
    m15_data.loc[m15_data.index[-1], "volume"] = 8000  # 突破放量

    # 模拟M5数据（可选）
    m5_dates = pd.date_range(start="2024-01-20", periods=40, freq="5min")
    m5_prices = 45000.0 + np.random.normal(0, 50, 40)
    m5_volumes = np.random.randint(500, 3000, 40)

    m5_data = pd.DataFrame(
        {
            "open": m5_prices - 5,
            "high": m5_prices + 10,
            "low": m5_prices - 10,
            "close": m5_prices,
            "volume": m5_volumes,
        },
        index=m5_dates,
    )

    # 市场上下文
    market_context = {
        "regime": "TRENDING",
        "timestamp": datetime.now().isoformat(),
        "volume_analysis": {},
        "price_action": {},
    }

    # 验证入场
    result = validator.validate_entry(
        h4_structure=h4_structure,
        m15_data=m15_data,
        m5_data=m5_data,
        macro_bias="BULLISH",
        market_context=market_context,
    )


    if result["signal_type"] in ["AGGRESSIVE_ENTRY", "CONFIRMED_ENTRY"]:
        params = result["entry_parameters"]

