"""
威科夫阶段检测方法模块
实现完整的威科夫阶段识别逻辑

设计原则：
1. 使用完整的Context信息（TR边界、关键价格、趋势方向等）
2. 检查威科夫阶段序列和逻辑关系
3. 基于威科夫理论的特征识别
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class WyckoffPhaseDetector:
    """威科夫阶段检测器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        self.tr_confidence_threshold = self.config.get("tr_confidence_threshold", 0.5)
        self.volume_spike_threshold = self.config.get("volume_spike_threshold", 1.5)
        self.price_change_threshold = self.config.get("price_change_threshold", 0.02)
        
        self.detected_phases: List[Dict[str, Any]] = []
        self.key_levels: Dict[str, float] = {}
    
    def detect_ps(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测初步支撑
        
        PS特征：
        1. 下跌趋势后首次出现支撑迹象
        2. 价格接近或触及TR下边界
        3. 成交量放大（买盘进入）
        4. K线形态显示支撑（长下影线、锤子线等）
        """
        evidences = []
        confidence = 0.0
        
        trend_direction = context.get("trend_direction", "UNKNOWN")
        tr_low = context.get("tr_low")
        tr_high = context.get("tr_high")
        tr_confidence = context.get("tr_confidence", 0)
        volume_ratio = context.get("volume_ratio", 1.0)
        market_regime = context.get("market_regime", "UNKNOWN")
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        volume = float(candle["volume"])
        
        trend_score = 0.0
        if trend_direction in ["DOWN", "DOWNTREND"]:
            trend_score = 0.8
            evidences.append(f"下跌趋势中检测到PS候选")
        elif trend_direction == "SIDEWAYS":
            trend_score = 0.5
            evidences.append(f"横盘趋势中检测到PS候选")
        else:
            trend_score = 0.2
            evidences.append(f"非下跌趋势，PS可能性低")
        
        tr_score = 0.0
        if tr_low is not None and tr_high is not None:
            tr_range = tr_high - tr_low
            if tr_range > 0:
                price_position = (close - tr_low) / tr_range
                
                if price_position < 0.3:
                    tr_score = 0.7
                    evidences.append(f"价格接近TR下边界 (位置: {price_position:.2f})")
                elif price_position < 0.5:
                    tr_score = 0.5
                    evidences.append(f"价格在TR下半部分 (位置: {price_position:.2f})")
                else:
                    tr_score = 0.2
                    evidences.append(f"价格在TR上半部分，PS可能性低")
        else:
            tr_score = 0.3
            evidences.append(f"TR边界未确定")
        
        volume_score = 0.0
        if volume_ratio > self.volume_spike_threshold:
            volume_score = 0.8
            evidences.append(f"成交量放大 ({volume_ratio:.2f}x)")
        elif volume_ratio > 1.0:
            volume_score = 0.5
            evidences.append(f"成交量正常 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.3
            evidences.append(f"成交量萎缩 ({volume_ratio:.2f}x)")
        
        body_size = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)
        
        pattern_score = 0.0
        if body_size > 0:
            shadow_ratio = lower_shadow / body_size
            
            if shadow_ratio > 2.0 and upper_shadow < body_size * 0.3:
                pattern_score = 0.9
                evidences.append(f"锤子线形态 (下影线/实体: {shadow_ratio:.2f})")
            elif shadow_ratio > 1.0:
                pattern_score = 0.6
                evidences.append(f"支撑形态 (下影线/实体: {shadow_ratio:.2f})")
            elif close > open_price:
                pattern_score = 0.4
                evidences.append(f"阳线，显示买盘")
            else:
                pattern_score = 0.2
                evidences.append(f"阴线，支撑较弱")
        else:
            pattern_score = 0.3
            evidences.append(f"十字星，方向不明")
        
        confidence = (
            trend_score * 0.25 +
            tr_score * 0.25 +
            volume_score * 0.25 +
            pattern_score * 0.25
        )
        
        if current_state != "IDLE" and current_state not in ["PS", "TEST"]:
            confidence *= 0.5
            evidences.append(f"当前状态{current_state}，PS可能性降低")
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": volume_score * 0.5 + pattern_score * 0.5,
            "evidences": evidences,
        }
    
    def detect_sc(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测抛售高潮
        
        SC特征：
        1. 大幅下跌后的恐慌性抛售
        2. 成交量急剧放大（通常是最高的）
        3. 价格大幅下跌但收盘价回升（长下影线）
        4. 可能跌破之前的支撑位
        """
        evidences = []
        confidence = 0.0
        
        trend_direction = context.get("trend_direction", "UNKNOWN")
        tr_low = context.get("tr_low")
        tr_high = context.get("tr_high")
        volume_ratio = context.get("volume_ratio", 1.0)
        volume_trend = context.get("volume_trend", "NEUTRAL")
        ps_low = context.get("ps_low")
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        volume = float(candle["volume"])
        
        trend_score = 0.0
        if trend_direction in ["DOWN", "DOWNTREND"]:
            trend_score = 0.9
            evidences.append(f"下跌趋势中检测到SC候选")
        elif trend_direction == "SIDEWAYS":
            trend_score = 0.6
            evidences.append(f"横盘趋势中检测到SC候选")
        else:
            trend_score = 0.2
            evidences.append(f"上涨趋势，SC可能性低")
        
        volume_score = 0.0
        if volume_ratio > 2.0:
            volume_score = 0.9
            evidences.append(f"成交量急剧放大 ({volume_ratio:.2f}x)")
        elif volume_ratio > 1.5:
            volume_score = 0.7
            evidences.append(f"成交量明显放大 ({volume_ratio:.2f}x)")
        elif volume_ratio > 1.0:
            volume_score = 0.4
            evidences.append(f"成交量正常 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.2
            evidences.append(f"成交量萎缩，不符合SC特征")
        
        body_size = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)
        total_range = high - low
        
        pattern_score = 0.0
        if total_range > 0:
            lower_shadow_ratio = lower_shadow / total_range
            
            if lower_shadow_ratio > 0.5 and close > open_price:
                pattern_score = 0.9
                evidences.append(f"长下影线针形K线 (下影线占比: {lower_shadow_ratio:.2f})")
            elif lower_shadow_ratio > 0.3:
                pattern_score = 0.6
                evidences.append(f"下影线较长 (占比: {lower_shadow_ratio:.2f})")
            elif close < open_price and body_size / total_range > 0.6:
                pattern_score = 0.5
                evidences.append(f"长阴线，恐慌抛售")
            else:
                pattern_score = 0.3
                evidences.append(f"K线形态不典型")
        else:
            pattern_score = 0.2
        
        support_break_score = 0.0
        if ps_low is not None and low < ps_low:
            support_break_score = 0.8
            evidences.append(f"跌破PS低点 ({ps_low:.2f})，假突破可能")
        elif tr_low is not None and low < tr_low:
            support_break_score = 0.7
            evidences.append(f"跌破TR下边界 ({tr_low:.2f})，假突破可能")
        else:
            support_break_score = 0.3
            evidences.append(f"未跌破关键支撑")
        
        confidence = (
            trend_score * 0.25 +
            volume_score * 0.30 +
            pattern_score * 0.25 +
            support_break_score * 0.20
        )
        
        if current_state not in ["IDLE", "PS", "SC", "TEST"]:
            confidence *= 0.5
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": volume_score * 0.6 + pattern_score * 0.4,
            "evidences": evidences,
        }
    
    def detect_ar(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测自动反弹
        
        AR特征：
        1. SC之后的强劲反弹
        2. 成交量仍然较高
        3. 价格快速回升
        4. 确立TR的初步边界
        """
        evidences = []
        confidence = 0.0
        
        sc_low = context.get("sc_low")
        sc_volume = context.get("sc_volume")
        tr_low = context.get("tr_low")
        tr_high = context.get("tr_high")
        volume_ratio = context.get("volume_ratio", 1.0)
        trend_direction = context.get("trend_direction", "UNKNOWN")
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        sc_context_score = 0.0
        if sc_low is not None:
            sc_context_score = 0.8
            evidences.append(f"已检测到SC (低点: {sc_low:.2f})")
        else:
            sc_context_score = 0.3
            evidences.append(f"未检测到SC，AR可能性低")
        
        rebound_score = 0.0
        if sc_low is not None:
            price_change = (close - sc_low) / sc_low if sc_low > 0 else 0
            
            if price_change > 0.05:
                rebound_score = 0.9
                evidences.append(f"强劲反弹 ({price_change*100:.1f}%)")
            elif price_change > 0.02:
                rebound_score = 0.6
                evidences.append(f"明显反弹 ({price_change*100:.1f}%)")
            elif price_change > 0:
                rebound_score = 0.4
                evidences.append(f"小幅反弹 ({price_change*100:.1f}%)")
            else:
                rebound_score = 0.1
                evidences.append(f"未反弹")
        else:
            if close > open_price:
                rebound_score = 0.5
                evidences.append(f"阳线反弹")
            else:
                rebound_score = 0.2
        
        volume_score = 0.0
        if volume_ratio > 1.5:
            volume_score = 0.7
            evidences.append(f"成交量较高 ({volume_ratio:.2f}x)")
        elif volume_ratio > 1.0:
            volume_score = 0.5
            evidences.append(f"成交量正常 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.3
            evidences.append(f"成交量较低 ({volume_ratio:.2f}x)")
        
        tr_score = 0.0
        if tr_high is not None and tr_low is not None:
            tr_score = 0.7
            evidences.append(f"TR边界已确立 ({tr_low:.2f} - {tr_high:.2f})")
        elif high > 0:
            tr_score = 0.4
            evidences.append(f"可能确立AR高点")
        
        confidence = (
            sc_context_score * 0.30 +
            rebound_score * 0.30 +
            volume_score * 0.20 +
            tr_score * 0.20
        )
        
        if current_state not in ["IDLE", "PS", "SC", "AR", "TEST"]:
            confidence *= 0.5
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": rebound_score * 0.6 + volume_score * 0.4,
            "evidences": evidences,
        }
    
    def detect_st(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测二次测试
        
        ST特征：
        1. AR之后的回撤
        2. 成交量减少（供应枯竭）
        3. 价格接近SC低点但未跌破
        4. 确认支撑有效
        """
        evidences = []
        confidence = 0.0
        
        sc_low = context.get("sc_low")
        ar_high = context.get("ar_high")
        tr_low = context.get("tr_low")
        tr_high = context.get("tr_high")
        volume_ratio = context.get("volume_ratio", 1.0)
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        ar_context_score = 0.0
        if ar_high is not None:
            ar_context_score = 0.8
            evidences.append(f"已检测到AR (高点: {ar_high:.2f})")
        else:
            ar_context_score = 0.3
            evidences.append(f"未检测到AR，ST可能性低")
        
        pullback_score = 0.0
        if ar_high is not None and tr_low is not None:
            tr_range = ar_high - tr_low
            if tr_range > 0:
                price_position = (close - tr_low) / tr_range
                
                if price_position < 0.3:
                    pullback_score = 0.8
                    evidences.append(f"回撤至TR下边界 (位置: {price_position:.2f})")
                elif price_position < 0.5:
                    pullback_score = 0.6
                    evidences.append(f"回撤至TR下半部分 (位置: {price_position:.2f})")
                else:
                    pullback_score = 0.3
                    evidences.append(f"回撤不足")
        else:
            pullback_score = 0.4
        
        volume_score = 0.0
        if volume_ratio < 0.7:
            volume_score = 0.9
            evidences.append(f"成交量萎缩 ({volume_ratio:.2f}x)，供应枯竭")
        elif volume_ratio < 1.0:
            volume_score = 0.7
            evidences.append(f"成交量较低 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.4
            evidences.append(f"成交量较高 ({volume_ratio:.2f}x)，不符合ST特征")
        
        support_test_score = 0.0
        if sc_low is not None:
            if low <= sc_low * 1.02 and close >= sc_low * 0.98:
                support_test_score = 0.9
                evidences.append(f"测试SC低点成功 (低点: {low:.2f}, SC: {sc_low:.2f})")
            elif low > sc_low:
                support_test_score = 0.6
                evidences.append(f"未触及SC低点")
            else:
                support_test_score = 0.3
                evidences.append(f"跌破SC低点")
        else:
            support_test_score = 0.4
        
        confidence = (
            ar_context_score * 0.25 +
            pullback_score * 0.25 +
            volume_score * 0.25 +
            support_test_score * 0.25
        )
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": pullback_score * 0.5 + volume_score * 0.5,
            "evidences": evidences,
        }
    
    def detect_spring(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测弹簧
        
        Spring特征：
        1. 价格短暂跌破TR下边界或SC低点
        2. 快速收回（假突破）
        3. 成交量较低（最后的供应测试）
        4. 主力诱空行为
        """
        evidences = []
        confidence = 0.0
        
        sc_low = context.get("sc_low")
        tr_low = context.get("tr_low")
        tr_high = context.get("tr_high")
        volume_ratio = context.get("volume_ratio", 1.0)
        in_tr = context.get("in_tr", False)
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        support_level = tr_low if tr_low is not None else sc_low
        
        break_score = 0.0
        if support_level is not None:
            if low < support_level:
                break_score = 0.8
                evidences.append(f"跌破支撑 ({low:.2f} < {support_level:.2f})")
            else:
                break_score = 0.2
                evidences.append(f"未跌破支撑")
        else:
            break_score = 0.3
        
        recovery_score = 0.0
        if support_level is not None and low < support_level:
            if close >= support_level:
                recovery_score = 0.9
                evidences.append(f"快速收回支撑上方 (收盘: {close:.2f})")
            else:
                recovery_score = 0.3
                evidences.append(f"未收回支撑上方")
        else:
            recovery_score = 0.4
        
        volume_score = 0.0
        if volume_ratio < 0.8:
            volume_score = 0.9
            evidences.append(f"成交量低 ({volume_ratio:.2f}x)，主力诱空")
        elif volume_ratio < 1.0:
            volume_score = 0.6
            evidences.append(f"成交量较低 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.3
            evidences.append(f"成交量较高 ({volume_ratio:.2f}x)，可能不是Spring")
        
        tr_context_score = 0.0
        if in_tr and tr_high is not None:
            tr_context_score = 0.7
            evidences.append(f"在TR范围内")
        else:
            tr_context_score = 0.4
        
        confidence = (
            break_score * 0.25 +
            recovery_score * 0.35 +
            volume_score * 0.25 +
            tr_context_score * 0.15
        )
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": recovery_score * 0.6 + volume_score * 0.4,
            "evidences": evidences,
        }
    
    def detect_sos(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测强势信号
        
        SOS特征：
        1. 价格突破TR上边界或AR高点
        2. 成交量放大（需求主导）
        3. 确认吸筹完成
        4. 后续可能回踩确认
        """
        evidences = []
        confidence = 0.0
        
        ar_high = context.get("ar_high")
        tr_high = context.get("tr_high")
        tr_low = context.get("tr_low")
        volume_ratio = context.get("volume_ratio", 1.0)
        trend_direction = context.get("trend_direction", "UNKNOWN")
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        resistance_level = ar_high if ar_high is not None else tr_high
        
        breakout_score = 0.0
        if resistance_level is not None:
            if close > resistance_level:
                breakout_score = 0.9
                evidences.append(f"突破阻力位 (收盘: {close:.2f} > {resistance_level:.2f})")
            elif high > resistance_level:
                breakout_score = 0.6
                evidences.append(f"触及阻力位但未突破")
            else:
                breakout_score = 0.2
                evidences.append(f"未突破阻力位")
        else:
            breakout_score = 0.4
        
        volume_score = 0.0
        if volume_ratio > 1.5:
            volume_score = 0.9
            evidences.append(f"成交量放大 ({volume_ratio:.2f}x)，需求主导")
        elif volume_ratio > 1.0:
            volume_score = 0.6
            evidences.append(f"成交量正常 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.3
            evidences.append(f"成交量较低 ({volume_ratio:.2f}x)，突破可能无效")
        
        trend_score = 0.0
        if trend_direction in ["UP", "UPTREND"]:
            trend_score = 0.8
            evidences.append(f"上涨趋势中")
        elif trend_direction == "SIDEWAYS":
            trend_score = 0.5
            evidences.append(f"横盘趋势中")
        else:
            trend_score = 0.3
        
        pattern_score = 0.0
        body_size = abs(close - open_price)
        if close > open_price and body_size > 0:
            pattern_score = 0.7
            evidences.append(f"阳线突破")
        else:
            pattern_score = 0.4
        
        confidence = (
            breakout_score * 0.35 +
            volume_score * 0.30 +
            trend_score * 0.20 +
            pattern_score * 0.15
        )
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": breakout_score * 0.5 + volume_score * 0.5,
            "evidences": evidences,
        }
    
    def detect_lps(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测最后支撑点
        
        LPS特征：
        1. SOS之后的回撤
        2. 成交量萎缩（供应耗尽）
        3. 价格在较高位置获得支撑
        4. 吸筹阶段的最后买入机会
        """
        evidences = []
        confidence = 0.0
        
        sos_high = context.get("sos_high")
        ar_high = context.get("ar_high")
        tr_high = context.get("tr_high")
        tr_low = context.get("tr_low")
        volume_ratio = context.get("volume_ratio", 1.0)
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        sos_context_score = 0.0
        if sos_high is not None:
            sos_context_score = 0.8
            evidences.append(f"已检测到SOS (高点: {sos_high:.2f})")
        elif ar_high is not None:
            sos_context_score = 0.5
            evidences.append(f"有AR高点 (高点: {ar_high:.2f})")
        else:
            sos_context_score = 0.2
            evidences.append(f"未检测到SOS/AR，LPS可能性低")
        
        pullback_score = 0.0
        resistance_level = sos_high if sos_high is not None else ar_high
        support_level = tr_high if tr_high is not None else tr_low
        
        if resistance_level is not None and support_level is not None:
            range_mid = (resistance_level + support_level) / 2
            if close >= range_mid:
                pullback_score = 0.8
                evidences.append(f"回撤至高位支撑 (收盘: {close:.2f})")
            else:
                pullback_score = 0.4
                evidences.append(f"回撤较深")
        else:
            pullback_score = 0.4
        
        volume_score = 0.0
        if volume_ratio < 0.7:
            volume_score = 0.9
            evidences.append(f"成交量萎缩 ({volume_ratio:.2f}x)，供应耗尽")
        elif volume_ratio < 1.0:
            volume_score = 0.6
            evidences.append(f"成交量较低 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.3
            evidences.append(f"成交量较高 ({volume_ratio:.2f}x)")
        
        pattern_score = 0.0
        if close > open_price:
            pattern_score = 0.6
            evidences.append(f"阳线，显示支撑")
        elif close < open_price:
            body_size = abs(close - open_price)
            lower_shadow = min(open_price, close) - low
            if lower_shadow > body_size:
                pattern_score = 0.7
                evidences.append(f"下影线较长，支撑有效")
            else:
                pattern_score = 0.3
        else:
            pattern_score = 0.4
        
        confidence = (
            sos_context_score * 0.25 +
            pullback_score * 0.30 +
            volume_score * 0.25 +
            pattern_score * 0.20
        )
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": pullback_score * 0.5 + volume_score * 0.5,
            "evidences": evidences,
        }
    
    def detect_psy(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测初步供应
        
        PSY特征：
        1. 上涨趋势后首次出现供应
        2. 价格接近或触及TR上边界
        3. 成交量放大（卖盘进入）
        4. K线形态显示阻力（长上影线、流星线等）
        """
        evidences = []
        confidence = 0.0
        
        trend_direction = context.get("trend_direction", "UNKNOWN")
        tr_low = context.get("tr_low")
        tr_high = context.get("tr_high")
        volume_ratio = context.get("volume_ratio", 1.0)
        market_regime = context.get("market_regime", "UNKNOWN")
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        trend_score = 0.0
        if trend_direction in ["UP", "UPTREND"]:
            trend_score = 0.8
            evidences.append(f"上涨趋势中检测到PSY候选")
        elif trend_direction == "SIDEWAYS":
            trend_score = 0.5
            evidences.append(f"横盘趋势中检测到PSY候选")
        else:
            trend_score = 0.2
            evidences.append(f"下跌趋势，PSY可能性低")
        
        tr_score = 0.0
        if tr_low is not None and tr_high is not None:
            tr_range = tr_high - tr_low
            if tr_range > 0:
                price_position = (close - tr_low) / tr_range
                
                if price_position > 0.7:
                    tr_score = 0.7
                    evidences.append(f"价格接近TR上边界 (位置: {price_position:.2f})")
                elif price_position > 0.5:
                    tr_score = 0.5
                    evidences.append(f"价格在TR上半部分 (位置: {price_position:.2f})")
                else:
                    tr_score = 0.2
                    evidences.append(f"价格在TR下半部分，PSY可能性低")
        else:
            tr_score = 0.3
        
        volume_score = 0.0
        if volume_ratio > self.volume_spike_threshold:
            volume_score = 0.8
            evidences.append(f"成交量放大 ({volume_ratio:.2f}x)")
        elif volume_ratio > 1.0:
            volume_score = 0.5
            evidences.append(f"成交量正常 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.3
            evidences.append(f"成交量萎缩 ({volume_ratio:.2f}x)")
        
        body_size = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        
        pattern_score = 0.0
        if body_size > 0:
            shadow_ratio = upper_shadow / body_size
            
            if shadow_ratio > 2.0 and lower_shadow < body_size * 0.3:
                pattern_score = 0.9
                evidences.append(f"流星线形态 (上影线/实体: {shadow_ratio:.2f})")
            elif shadow_ratio > 1.0:
                pattern_score = 0.6
                evidences.append(f"阻力形态 (上影线/实体: {shadow_ratio:.2f})")
            elif close < open_price:
                pattern_score = 0.4
                evidences.append(f"阴线，显示卖盘")
            else:
                pattern_score = 0.2
                evidences.append(f"阳线，阻力较弱")
        else:
            pattern_score = 0.3
        
        confidence = (
            trend_score * 0.25 +
            tr_score * 0.25 +
            volume_score * 0.25 +
            pattern_score * 0.25
        )
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": volume_score * 0.5 + pattern_score * 0.5,
            "evidences": evidences,
        }
    
    def detect_bc(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测买入高潮
        
        BC特征：
        1. 大幅上涨后的恐慌性买入
        2. 成交量急剧放大（通常是最高的）
        3. 价格大幅上涨但收盘价回落（长上影线）
        4. 可能突破之前的阻力位
        """
        evidences = []
        confidence = 0.0
        
        trend_direction = context.get("trend_direction", "UNKNOWN")
        tr_low = context.get("tr_low")
        tr_high = context.get("tr_high")
        volume_ratio = context.get("volume_ratio", 1.0)
        volume_trend = context.get("volume_trend", "NEUTRAL")
        psy_high = context.get("psy_high")
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        trend_score = 0.0
        if trend_direction in ["UP", "UPTREND"]:
            trend_score = 0.9
            evidences.append(f"上涨趋势中检测到BC候选")
        elif trend_direction == "SIDEWAYS":
            trend_score = 0.6
            evidences.append(f"横盘趋势中检测到BC候选")
        else:
            trend_score = 0.2
            evidences.append(f"下跌趋势，BC可能性低")
        
        volume_score = 0.0
        if volume_ratio > 2.0:
            volume_score = 0.9
            evidences.append(f"成交量急剧放大 ({volume_ratio:.2f}x)")
        elif volume_ratio > 1.5:
            volume_score = 0.7
            evidences.append(f"成交量明显放大 ({volume_ratio:.2f}x)")
        elif volume_ratio > 1.0:
            volume_score = 0.4
            evidences.append(f"成交量正常 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.2
            evidences.append(f"成交量萎缩，不符合BC特征")
        
        body_size = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        total_range = high - low
        
        pattern_score = 0.0
        if total_range > 0:
            upper_shadow_ratio = upper_shadow / total_range
            
            if upper_shadow_ratio > 0.5 and close < open_price:
                pattern_score = 0.9
                evidences.append(f"长上影线针形K线 (上影线占比: {upper_shadow_ratio:.2f})")
            elif upper_shadow_ratio > 0.3:
                pattern_score = 0.6
                evidences.append(f"上影线较长 (占比: {upper_shadow_ratio:.2f})")
            elif close > open_price and body_size / total_range > 0.6:
                pattern_score = 0.5
                evidences.append(f"长阳线，恐慌买入")
            else:
                pattern_score = 0.3
                evidences.append(f"K线形态不典型")
        else:
            pattern_score = 0.2
        
        resistance_break_score = 0.0
        if psy_high is not None and high > psy_high:
            resistance_break_score = 0.8
            evidences.append(f"突破PSY高点 ({psy_high:.2f})，假突破可能")
        elif tr_high is not None and high > tr_high:
            resistance_break_score = 0.7
            evidences.append(f"突破TR上边界 ({tr_high:.2f})，假突破可能")
        else:
            resistance_break_score = 0.3
            evidences.append(f"未突破关键阻力")
        
        confidence = (
            trend_score * 0.25 +
            volume_score * 0.30 +
            pattern_score * 0.25 +
            resistance_break_score * 0.20
        )
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": volume_score * 0.6 + pattern_score * 0.4,
            "evidences": evidences,
        }
    
    def detect_utad(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Any]:
        """检测派发后上涨陷阱
        
        UTAD特征：
        1. 价格短暂突破TR上边界或BC高点
        2. 快速回落（假突破）
        3. 成交量可能较高但无法维持
        4. 主力诱多行为
        """
        evidences = []
        confidence = 0.0
        
        bc_high = context.get("bc_high")
        tr_high = context.get("tr_high")
        tr_low = context.get("tr_low")
        volume_ratio = context.get("volume_ratio", 1.0)
        in_tr = context.get("in_tr", False)
        
        close = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        
        resistance_level = bc_high if bc_high is not None else tr_high
        
        break_score = 0.0
        if resistance_level is not None:
            if high > resistance_level:
                break_score = 0.8
                evidences.append(f"突破阻力 ({high:.2f} > {resistance_level:.2f})")
            else:
                break_score = 0.2
                evidences.append(f"未突破阻力")
        else:
            break_score = 0.3
        
        reversal_score = 0.0
        if resistance_level is not None and high > resistance_level:
            if close < resistance_level:
                reversal_score = 0.9
                evidences.append(f"快速回落阻力下方 (收盘: {close:.2f})")
            elif close < high * 0.98:
                reversal_score = 0.6
                evidences.append(f"部分回落")
            else:
                reversal_score = 0.3
                evidences.append(f"维持高位")
        else:
            reversal_score = 0.4
        
        volume_score = 0.0
        if volume_ratio > 1.0:
            volume_score = 0.7
            evidences.append(f"成交量较高 ({volume_ratio:.2f}x)")
        elif volume_ratio > 0.7:
            volume_score = 0.5
            evidences.append(f"成交量正常 ({volume_ratio:.2f}x)")
        else:
            volume_score = 0.3
            evidences.append(f"成交量较低 ({volume_ratio:.2f}x)")
        
        tr_context_score = 0.0
        if in_tr and tr_low is not None:
            tr_context_score = 0.7
            evidences.append(f"在TR范围内")
        else:
            tr_context_score = 0.4
        
        confidence = (
            break_score * 0.25 +
            reversal_score * 0.35 +
            volume_score * 0.25 +
            tr_context_score * 0.15
        )
        
        return {
            "confidence": min(1.0, max(0.0, confidence)),
            "intensity": reversal_score * 0.6 + volume_score * 0.4,
            "evidences": evidences,
        }
    
    def detect(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE"
    ) -> Dict[str, Dict[str, Any]]:
        """检测所有威科夫阶段"""
        results = {}
        
        results["PS"] = self.detect_ps(candle, context, current_state)
        results["SC"] = self.detect_sc(candle, context, current_state)
        results["AR"] = self.detect_ar(candle, context, current_state)
        results["ST"] = self.detect_st(candle, context, current_state)
        results["SPRING"] = self.detect_spring(candle, context, current_state)
        results["SOS"] = self.detect_sos(candle, context, current_state)
        results["LPS"] = self.detect_lps(candle, context, current_state)
        results["PSY"] = self.detect_psy(candle, context, current_state)
        results["BC"] = self.detect_bc(candle, context, current_state)
        results["UTAD"] = self.detect_utad(candle, context, current_state)
        
        return results
