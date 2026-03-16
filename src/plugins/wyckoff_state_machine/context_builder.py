"""
威科夫Context构建器模块
为状态机提供完整的上下文信息，包括TR边界、趋势分析、关键价格等

设计原则：
1. TR检测：基于价格波动和成交量识别交易区间
2. 趋势分析：多周期趋势方向和强度
3. 关键价格追踪：记录SC低点、BC高点、Spring低点等
4. 成交量分析：主力行为识别
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TradingRange:
    """交易区间数据结构"""
    high: float
    low: float
    midpoint: float
    width: float
    width_pct: float
    start_idx: int
    end_idx: int
    bars: int
    volume_profile: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class TrendInfo:
    """趋势信息数据结构"""
    direction: str  # UP, DOWN, SIDEWAYS
    strength: float  # 0.0 - 1.0
    slope: float  # 价格斜率
    duration_bars: int  # 持续K线数
    price_change_pct: float  # 价格变化百分比
    higher_highs: int  # 更高高点数量
    lower_lows: int  # 更低低点数量


@dataclass
class KeyPriceLevels:
    """关键价格水平"""
    ps_high: Optional[float] = None
    ps_low: Optional[float] = None
    sc_high: Optional[float] = None
    sc_low: Optional[float] = None
    sc_volume: Optional[float] = None
    ar_high: Optional[float] = None
    ar_low: Optional[float] = None
    bc_high: Optional[float] = None
    bc_volume: Optional[float] = None
    spring_low: Optional[float] = None
    spring_volume: Optional[float] = None
    lps_high: Optional[float] = None
    sos_high: Optional[float] = None
    last_update: Dict[str, int] = field(default_factory=dict)


@dataclass
class VolumeProfile:
    """成交量分布"""
    total_volume: float = 0.0
    avg_volume: float = 0.0
    volume_trend: str = "NEUTRAL"  # INCREASING, DECREASING, NEUTRAL
    volume_ratio: float = 1.0  # 当前成交量/平均成交量
    accumulation_volume: float = 0.0  # 吸筹成交量
    distribution_volume: float = 0.0  # 派发成交量


class TRDetector:
    """交易区间检测器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.min_bars = self.config.get("min_bars", 20)
        self.max_bars = self.config.get("max_bars", 200)
        self.width_threshold = self.config.get("width_threshold", 0.15)
        self.lookback = self.config.get("lookback", 100)
        
        self.current_tr: Optional[TradingRange] = None
        self.tr_history: List[TradingRange] = []
    
    def detect(self, data: pd.DataFrame, idx: int) -> Optional[TradingRange]:
        """检测交易区间"""
        if idx < self.min_bars:
            return None
        
        lookback_start = max(0, idx - self.lookback)
        recent_data = data.iloc[lookback_start:idx + 1]
        
        if len(recent_data) < self.min_bars:
            return None
        
        highs = recent_data['high'].values
        lows = recent_data['low'].values
        closes = recent_data['close'].values
        volumes = recent_data['volume'].values if 'volume' in recent_data.columns else None
        
        rolling_high = pd.Series(highs).rolling(self.min_bars, min_periods=1).max().values
        rolling_low = pd.Series(lows).rolling(self.min_bars, min_periods=1).min().values
        
        for window in range(self.min_bars, min(len(highs), self.max_bars)):
            window_highs = highs[-window:]
            window_lows = lows[-window:]
            window_closes = closes[-window:]
            
            tr_high = np.max(window_highs)
            tr_low = np.min(window_lows)
            tr_width = tr_high - tr_low
            tr_midpoint = (tr_high + tr_low) / 2
            
            if tr_high <= 0:
                continue
            
            width_pct = tr_width / tr_high
            
            if width_pct > self.width_threshold:
                continue
            
            closes_in_range = np.sum((window_closes >= tr_low * 0.98) & (window_closes <= tr_high * 1.02))
            range_ratio = closes_in_range / window
            
            if range_ratio < 0.7:
                continue
            
            volume_profile = {}
            if volumes is not None:
                window_volumes = volumes[-window:]
                volume_profile = {
                    'total': float(np.sum(window_volumes)),
                    'avg': float(np.mean(window_volumes)),
                    'max': float(np.max(window_volumes)),
                    'min': float(np.min(window_volumes)),
                }
            
            tr = TradingRange(
                high=float(tr_high),
                low=float(tr_low),
                midpoint=float(tr_midpoint),
                width=float(tr_width),
                width_pct=float(width_pct),
                start_idx=idx - window + 1,
                end_idx=idx,
                bars=window,
                volume_profile=volume_profile,
                confidence=float(range_ratio * (1 - width_pct / self.width_threshold)),
            )
            
            self.current_tr = tr
            self.tr_history.append(tr)
            
            return tr
        
        return self.current_tr
    
    def get_tr_context(self, data: pd.DataFrame, idx: int) -> Dict[str, Any]:
        """获取TR上下文信息"""
        tr = self.detect(data, idx)
        
        if tr is None:
            return {
                "tr_high": None,
                "tr_low": None,
                "tr_midpoint": None,
                "tr_width": None,
                "tr_width_pct": None,
                "tr_bars": 0,
                "tr_confidence": 0.0,
                "in_tr": False,
            }
        
        current_close = data.iloc[idx]['close']
        in_tr = tr.low * 0.98 <= current_close <= tr.high * 1.02
        
        position_in_tr = 0.5
        if tr.width > 0:
            position_in_tr = (current_close - tr.low) / tr.width
        
        return {
            "tr_high": tr.high,
            "tr_low": tr.low,
            "tr_midpoint": tr.midpoint,
            "tr_width": tr.width,
            "tr_width_pct": tr.width_pct,
            "tr_bars": tr.bars,
            "tr_confidence": tr.confidence,
            "in_tr": in_tr,
            "position_in_tr": position_in_tr,
        }


class TrendAnalyzer:
    """趋势分析器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.short_period = self.config.get("short_period", 20)
        self.long_period = self.config.get("long_period", 50)
        self.trend_threshold = self.config.get("trend_threshold", 0.05)
        
        self.current_trend: Optional[TrendInfo] = None
        self.trend_history: List[TrendInfo] = []
    
    def analyze(self, data: pd.DataFrame, idx: int) -> TrendInfo:
        """分析趋势"""
        if idx < self.short_period:
            return TrendInfo(
                direction="UNKNOWN",
                strength=0.0,
                slope=0.0,
                duration_bars=0,
                price_change_pct=0.0,
                higher_highs=0,
                lower_lows=0,
            )
        
        short_data = data.iloc[max(0, idx - self.short_period):idx + 1]
        long_data = data.iloc[max(0, idx - self.long_period):idx + 1]
        
        closes = short_data['close'].values
        highs = short_data['high'].values
        lows = short_data['low'].values
        
        short_ma = np.mean(closes)
        long_ma = np.mean(long_data['close'].values) if len(long_data) > 0 else short_ma
        
        x = np.arange(len(closes))
        if len(closes) > 1:
            slope = np.polyfit(x, closes, 1)[0]
        else:
            slope = 0.0
        
        price_change_pct = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0.0
        
        higher_highs = 0
        lower_lows = 0
        for i in range(1, len(highs)):
            if highs[i] > highs[i-1]:
                higher_highs += 1
            if lows[i] < lows[i-1]:
                lower_lows += 1
        
        if price_change_pct > self.trend_threshold:
            direction = "UP"
            strength = min(1.0, abs(price_change_pct) / 0.2)
        elif price_change_pct < -self.trend_threshold:
            direction = "DOWN"
            strength = min(1.0, abs(price_change_pct) / 0.2)
        else:
            direction = "SIDEWAYS"
            strength = 0.3
        
        ma_diff = (short_ma - long_ma) / long_ma if long_ma > 0 else 0.0
        if abs(ma_diff) > 0.02:
            if ma_diff > 0 and direction != "DOWN":
                direction = "UP"
                strength = min(1.0, strength + 0.2)
            elif ma_diff < 0 and direction != "UP":
                direction = "DOWN"
                strength = min(1.0, strength + 0.2)
        
        trend = TrendInfo(
            direction=direction,
            strength=strength,
            slope=slope,
            duration_bars=len(short_data),
            price_change_pct=price_change_pct,
            higher_highs=higher_highs,
            lower_lows=lower_lows,
        )
        
        self.current_trend = trend
        self.trend_history.append(trend)
        
        return trend
    
    def get_trend_context(self, data: pd.DataFrame, idx: int) -> Dict[str, Any]:
        """获取趋势上下文信息"""
        trend = self.analyze(data, idx)
        
        return {
            "trend_direction": trend.direction,
            "trend_strength": trend.strength,
            "trend_slope": trend.slope,
            "trend_duration": trend.duration_bars,
            "price_change_pct": trend.price_change_pct,
            "higher_highs": trend.higher_highs,
            "lower_lows": trend.lower_lows,
            "is_uptrend": trend.direction == "UP",
            "is_downtrend": trend.direction == "DOWN",
            "is_sideways": trend.direction == "SIDEWAYS",
        }


class KeyPriceTracker:
    """关键价格追踪器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.decay_bars = self.config.get("decay_bars", 100)
        
        self.key_levels = KeyPriceLevels()
        self.price_history: List[Dict[str, Any]] = []
    
    def update(
        self,
        candle: pd.Series,
        state: str,
        idx: int,
        volume: Optional[float] = None,
    ) -> None:
        """更新关键价格水平"""
        high = float(candle['high'])
        low = float(candle['low'])
        vol = volume or float(candle.get('volume', 0))
        
        state_upper = state.upper()
        
        if 'PS' in state_upper:
            if self.key_levels.ps_high is None or high > self.key_levels.ps_high:
                self.key_levels.ps_high = high
            if self.key_levels.ps_low is None or low < self.key_levels.ps_low:
                self.key_levels.ps_low = low
            self.key_levels.last_update['PS'] = idx
        
        elif 'SC' in state_upper:
            if self.key_levels.sc_high is None or high > self.key_levels.sc_high:
                self.key_levels.sc_high = high
            if self.key_levels.sc_low is None or low < self.key_levels.sc_low:
                self.key_levels.sc_low = low
            if self.key_levels.sc_volume is None or vol > self.key_levels.sc_volume:
                self.key_levels.sc_volume = vol
            self.key_levels.last_update['SC'] = idx
        
        elif 'AR' in state_upper and 'DIST' not in state_upper:
            if self.key_levels.ar_high is None or high > self.key_levels.ar_high:
                self.key_levels.ar_high = high
            if self.key_levels.ar_low is None or low < self.key_levels.ar_low:
                self.key_levels.ar_low = low
            self.key_levels.last_update['AR'] = idx
        
        elif 'BC' in state_upper:
            if self.key_levels.bc_high is None or high > self.key_levels.bc_high:
                self.key_levels.bc_high = high
            if self.key_levels.bc_volume is None or vol > self.key_levels.bc_volume:
                self.key_levels.bc_volume = vol
            self.key_levels.last_update['BC'] = idx
        
        elif 'SPRING' in state_upper:
            if self.key_levels.spring_low is None or low < self.key_levels.spring_low:
                self.key_levels.spring_low = low
            if self.key_levels.spring_volume is None or vol > self.key_levels.spring_volume:
                self.key_levels.spring_volume = vol
            self.key_levels.last_update['SPRING'] = idx
        
        elif 'LPS' in state_upper:
            if self.key_levels.lps_high is None or high > self.key_levels.lps_high:
                self.key_levels.lps_high = high
            self.key_levels.last_update['LPS'] = idx
        
        elif 'SOS' in state_upper or 'JOC' in state_upper:
            if self.key_levels.sos_high is None or high > self.key_levels.sos_high:
                self.key_levels.sos_high = high
            self.key_levels.last_update['SOS'] = idx
        
        self.price_history.append({
            'idx': idx,
            'state': state,
            'high': high,
            'low': low,
            'volume': vol,
        })
    
    def get_key_levels_context(self, idx: int) -> Dict[str, Any]:
        """获取关键价格水平上下文"""
        context = {
            "ps_high": self.key_levels.ps_high,
            "ps_low": self.key_levels.ps_low,
            "sc_high": self.key_levels.sc_high,
            "sc_low": self.key_levels.sc_low,
            "sc_volume": self.key_levels.sc_volume,
            "ar_high": self.key_levels.ar_high,
            "ar_low": self.key_levels.ar_low,
            "bc_high": self.key_levels.bc_high,
            "bc_volume": self.key_levels.bc_volume,
            "spring_low": self.key_levels.spring_low,
            "spring_volume": self.key_levels.spring_volume,
            "lps_high": self.key_levels.lps_high,
            "sos_high": self.key_levels.sos_high,
        }
        
        for key, update_idx in self.key_levels.last_update.items():
            bars_since = idx - update_idx
            context[f"bars_since_{key.lower()}"] = bars_since
        
        return context


class VolumeAnalyzer:
    """成交量分析器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.lookback = self.config.get("lookback", 20)
        
        self.volume_history: List[float] = []
        self.current_profile: Optional[VolumeProfile] = None
    
    def analyze(self, candle: pd.Series, idx: int) -> VolumeProfile:
        """分析成交量"""
        volume = float(candle.get('volume', 0))
        
        self.volume_history.append(volume)
        if len(self.volume_history) > self.lookback * 2:
            self.volume_history = self.volume_history[-self.lookback * 2:]
        
        avg_volume = np.mean(self.volume_history[-self.lookback:]) if len(self.volume_history) >= self.lookback else volume
        
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        
        if len(self.volume_history) >= self.lookback:
            recent_avg = np.mean(self.volume_history[-5:])
            older_avg = np.mean(self.volume_history[-self.lookback:-5])
            
            if recent_avg > older_avg * 1.2:
                volume_trend = "INCREASING"
            elif recent_avg < older_avg * 0.8:
                volume_trend = "DECREASING"
            else:
                volume_trend = "NEUTRAL"
        else:
            volume_trend = "NEUTRAL"
        
        profile = VolumeProfile(
            total_volume=float(np.sum(self.volume_history)),
            avg_volume=float(avg_volume),
            volume_trend=volume_trend,
            volume_ratio=float(volume_ratio),
            accumulation_volume=volume if volume_ratio > 1.5 else 0.0,
            distribution_volume=volume if volume_ratio > 2.0 else 0.0,
        )
        
        self.current_profile = profile
        return profile
    
    def get_volume_context(self, candle: pd.Series, idx: int) -> Dict[str, Any]:
        """获取成交量上下文"""
        profile = self.analyze(candle, idx)
        
        return {
            "volume": float(candle.get('volume', 0)),
            "avg_volume": profile.avg_volume,
            "volume_ratio": profile.volume_ratio,
            "volume_trend": profile.volume_trend,
            "is_high_volume": profile.volume_ratio > 1.5,
            "is_low_volume": profile.volume_ratio < 0.7,
            "accumulation_volume": profile.accumulation_volume,
            "distribution_volume": profile.distribution_volume,
        }


class WyckoffContextBuilder:
    """威科夫Context构建器 - 整合所有信息"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        self.tr_detector = TRDetector(self.config.get("tr_detector", {}))
        self.trend_analyzer = TrendAnalyzer(self.config.get("trend_analyzer", {}))
        self.key_price_tracker = KeyPriceTracker(self.config.get("key_price_tracker", {}))
        self.volume_analyzer = VolumeAnalyzer(self.config.get("volume_analyzer", {}))
        
        self.context_history: List[Dict[str, Any]] = []
    
    def build_context(
        self,
        data: pd.DataFrame,
        candle: pd.Series,
        idx: int,
        current_state: str = "IDLE",
    ) -> Dict[str, Any]:
        """构建完整的上下文信息"""
        tr_context = self.tr_detector.get_tr_context(data, idx)
        trend_context = self.trend_analyzer.get_trend_context(data, idx)
        volume_context = self.volume_analyzer.get_volume_context(candle, idx)
        
        self.key_price_tracker.update(candle, current_state, idx)
        key_levels_context = self.key_price_tracker.get_key_levels_context(idx)
        
        market_regime = self._determine_market_regime(trend_context, tr_context)
        
        context = {
            **tr_context,
            **trend_context,
            **volume_context,
            **key_levels_context,
            "market_regime": market_regime,
            "bar_index": idx,
            "current_state": current_state,
            "timestamp": candle.name if hasattr(candle, 'name') else None,
        }
        
        self.context_history.append(context)
        
        return context
    
    def _determine_market_regime(
        self,
        trend_context: Dict[str, Any],
        tr_context: Dict[str, Any],
    ) -> str:
        """确定市场体制"""
        if tr_context.get("in_tr", False) and tr_context.get("tr_confidence", 0) > 0.5:
            return "RANGING"
        
        trend_direction = trend_context.get("trend_direction", "UNKNOWN")
        trend_strength = trend_context.get("trend_strength", 0)
        
        if trend_direction == "UP" and trend_strength > 0.5:
            return "UPTREND"
        elif trend_direction == "DOWN" and trend_strength > 0.5:
            return "DOWNTREND"
        else:
            return "SIDEWAYS"
    
    def reset(self) -> None:
        """重置所有追踪器"""
        self.tr_detector = TRDetector(self.config.get("tr_detector", {}))
        self.trend_analyzer = TrendAnalyzer(self.config.get("trend_analyzer", {}))
        self.key_price_tracker = KeyPriceTracker(self.config.get("key_price_tracker", {}))
        self.volume_analyzer = VolumeAnalyzer(self.config.get("volume_analyzer", {}))
        self.context_history = []
