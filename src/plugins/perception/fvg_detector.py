"""
FVG（公允价值缺口）检测模块
基于LuxAlgo算法实现，支持自动阈值计算和缺口缓解检测
解决FVG与威科夫冲突：TR内部FVG需回补，突破后FVG作为支撑阻力
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd


class FVGDirection(Enum):
    """FVG方向枚举"""

    BULLISH = "BULLISH"  # 看涨FVG（买方主导）
    BEARISH = "BEARISH"  # 看跌FVG（卖方主导）


class FVGStatus(Enum):
    """FVG状态枚举"""

    ACTIVE = "ACTIVE"  # 活跃缺口（未缓解）
    MITIGATED = "MITIGATED"  # 已缓解（价格回补）
    PARTIAL = "PARTIAL"  # 部分缓解
    EXPIRED = "EXPIRED"  # 过期（超过最大生命周期）


@dataclass
class FVGGap:
    """FVG缺口数据结构"""

    gap_id: str
    direction: FVGDirection
    max_price: float  # 缺口上边界
    min_price: float  # 缺口下边界
    timestamp: datetime  # 检测时间
    confidence: float  # 置信度 [0, 1]
    threshold_used: float  # 使用的阈值
    status: FVGStatus = FVGStatus.ACTIVE
    mitigated_time: Optional[datetime] = None  # 缓解时间
    mitigation_price: Optional[float] = None  # 缓解价格
    volume: Optional[float] = None  # 检测时的成交量
    market_regime: Optional[str] = None  # 检测时的市场体制
    strength: float = 1.0  # 缺口强度（基于大小和成交量）
    creation_bar_index: int = 0  # 创建时的K线索引（用于年龄计算）

    # 上下文信息
    in_trading_range: bool = False  # 是否在交易区间内
    is_breakout: bool = False  # 是否伴随突破
    related_resistance: Optional[float] = None  # 相关阻力位
    related_support: Optional[float] = None  # 相关支撑位


class FVGDetector:
    """
    FVG检测器 - 基于LuxAlgo算法

    功能：
    1. 检测看涨/看跌FVG缺口
    2. 自动/手动阈值计算
    3. 缺口缓解检测（价格回补）
    4. FVG上下文分析（TR内部 vs 突破后）
    5. 多时间框架FVG检测
    6. 统计跟踪与性能评估

    核心算法（LuxAlgo）：
    - 看涨FVG: low > high[2] and close[1] > high[2] and (low - high[2]) / high[2] > threshold
    - 看跌FVG: high < low[2] and close[1] < low[2] and (low[2] - high) / high > threshold

    设计原则：
    1. 上下文敏感：TR内部FVG需回补，突破后FVG作为支撑阻力
    2. 动态阈值：根据市场波动率自动调整
    3. 多时间框架验证：结合高低时间框架确认FVG重要性
    4. 实时监控：持续跟踪缺口状态变化
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化FVG检测器

        Args:
            config: 配置字典，包含以下参数：
                - threshold_percent: 手动阈值百分比（默认0.5%）
                - auto_threshold: 是否自动计算阈值（默认True）
                - threshold_lookback: 自动阈值计算回看周期（默认50）
                - min_gap_size_pct: 最小缺口大小百分比（默认0.1%）
                - max_gap_age_bars: 最大缺口年龄（K线数，默认100）
                - require_volume_confirmation: 是否需要成交量确认（默认False）
                - volume_threshold: 成交量阈值倍数（默认1.2）
                - enable_context_analysis: 启用上下文分析（默认True）
                - enable_multi_tf_validation: 启用多时间框架验证（默认True）
        """
        self.config = config or {}
        self.threshold_percent = self.config.get("threshold_percent", 0.5)
        self.auto_threshold = self.config.get("auto_threshold", True)
        self.threshold_lookback = self.config.get("threshold_lookback", 50)
        self.min_gap_size_pct = self.config.get("min_gap_size_pct", 0.1)
        self.max_gap_age_bars = self.config.get("max_gap_age_bars", 100)
        self.require_volume_confirmation = self.config.get(
            "require_volume_confirmation", False
        )
        self.volume_threshold = self.config.get("volume_threshold", 1.2)
        self.enable_context_analysis = self.config.get("enable_context_analysis", True)
        self.enable_multi_tf_validation = self.config.get(
            "enable_multi_tf_validation", True
        )

        # FVG记录
        self.fvg_history: list[FVGGap] = []
        self.active_fvgs: list[FVGGap] = []
        self.mitigated_fvgs: list[FVGGap] = []

        # 统计信息
        self.stats = {
            "total_detected": 0,
            "bullish_detected": 0,
            "bearish_detected": 0,
            "total_mitigated": 0,
            "bullish_mitigated": 0,
            "bearish_mitigated": 0,
            "avg_gap_size_pct": 0.0,
            "avg_gap_lifetime_bars": 0.0,
            "mitigation_rate": 0.0,
        }

        # 上下文状态
        self.current_context = {
            "in_trading_range": False,
            "tr_resistance": None,
            "tr_support": None,
            "market_regime": None,
            "volatility_index": 1.0,
        }

        # 下一个FVG ID
        self.next_fvg_id = 1

    def calculate_threshold(self, df: pd.DataFrame) -> float:
        """
        计算FVG检测阈值

        Args:
            df: OHLCV数据

        Returns:
            阈值（小数形式，如0.005表示0.5%）
        """
        if not self.auto_threshold or len(df) < self.threshold_lookback:
            return self.threshold_percent / 100.0

        # LuxAlgo自动阈值计算方法：平均波动率
        try:
            # 计算每个K线的波动率（(high - low) / low）
            volatility = (df["high"] - df["low"]) / df["low"]

            # 取最近N个周期的平均波动率
            recent_volatility = volatility.iloc[-self.threshold_lookback :]
            avg_volatility = recent_volatility.mean()

            # 确保阈值在合理范围内（0.1% - 2%）
            return max(self.min_gap_size_pct / 100.0, min(avg_volatility, 0.02))


        except Exception:
            return self.threshold_percent / 100.0

    def detect_fvg_gaps(
        self, df: pd.DataFrame, context: Optional[dict] = None, bar_index: int = 0
    ) -> list[FVGGap]:
        """
        检测FVG缺口

        Args:
            df: OHLCV数据，必须包含以下列：
                - 'open', 'high', 'low', 'close', 'volume'
            context: 上下文信息（可选），包含：
                - in_trading_range: 是否在交易区间内
                - tr_resistance: 交易区间阻力位
                - tr_support: 交易区间支撑位
                - market_regime: 市场体制
                - volatility_index: 波动率指数
            bar_index: 当前K线索引（用于记录FVG创建时间点）

        Returns:
            检测到的FVG缺口列表
        """
        if len(df) < 3:
            return []

        # 更新上下文
        if context:
            self.current_context.update(context)

        # 计算阈值
        threshold = self.calculate_threshold(df)

        # 获取最近3根K线的数据
        current_low = df["low"].iloc[-1]
        current_high = df["high"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        prev2_high = df["high"].iloc[-3]
        prev2_low = df["low"].iloc[-3]

        # 获取成交量数据（如果可用）
        current_volume = df["volume"].iloc[-1] if "volume" in df.columns else None
        avg_volume = None
        if current_volume is not None and len(df) >= 10:
            avg_volume = df["volume"].iloc[-10:-1].mean()

        detected_gaps = []

        # 检测看涨FVG
        bull_fvg = False
        bull_gap_size = 0.0

        if current_low > prev2_high and prev_close > prev2_high:
            bull_gap_size = (current_low - prev2_high) / prev2_high
            bull_fvg = bull_gap_size > threshold

        # 检测看跌FVG
        bear_fvg = False
        bear_gap_size = 0.0

        if current_high < prev2_low and prev_close < prev2_low:
            bear_gap_size = (prev2_low - current_high) / current_high
            bear_fvg = bear_gap_size > threshold

        # 成交量确认（可选）
        volume_confirmation = True
        if (
            self.require_volume_confirmation
            and current_volume is not None
            and avg_volume is not None
        ):
            volume_ratio = current_volume / avg_volume
            volume_confirmation = volume_ratio > self.volume_threshold

        # 创建FVG记录
        timestamp = df.index[-1]

        # 修复：时间戳可能是int64类型，需要转换为datetime对象
        if isinstance(timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime（使用UTC）
            timestamp_dt = datetime.fromtimestamp(float(timestamp) / 1000.0, tz=timezone.utc)
            time_str = timestamp_dt.strftime("%Y%m%d_%H%M")
        else:
            # 如果是datetime对象，直接格式化
            time_str = timestamp.strftime("%Y%m%d_%H%M")

        if bull_fvg and volume_confirmation:
            fvg_id = f"fvg_{self.next_fvg_id}_{time_str}"
            self.next_fvg_id += 1

            # 计算置信度
            confidence = self._calculate_confidence(
                gap_size=bull_gap_size,
                volume_ratio=current_volume / avg_volume
                if current_volume and avg_volume
                else 1.0,
                market_regime=self.current_context.get("market_regime"),
                in_tr=self.current_context.get("in_trading_range", False),
            )

            # 计算缺口强度
            strength = self._calculate_gap_strength(
                gap_size=bull_gap_size,
                volume=current_volume,
                avg_volume=avg_volume,
                direction=FVGDirection.BULLISH,
            )

            # 上下文分析
            in_trading_range = self.current_context.get("in_trading_range", False)
            is_breakout = False
            related_resistance = None
            related_support = None

            if self.enable_context_analysis:
                # 判断是否伴随突破
                tr_resistance = self.current_context.get("tr_resistance")
                if tr_resistance and current_high > tr_resistance:
                    is_breakout = True
                    related_support = tr_resistance  # 原阻力变支撑

                # 记录相关支撑阻力（仅在非突破时使用通用值）
                if not is_breakout:
                    related_resistance = self.current_context.get("tr_resistance")
                    related_support = self.current_context.get("tr_support")
                else:
                    related_resistance = self.current_context.get("tr_resistance")

            gap = FVGGap(
                gap_id=fvg_id,
                direction=FVGDirection.BULLISH,
                max_price=current_low,  # 看涨FVG：下边界是当前low
                min_price=prev2_high,  # 上边界是前2根high
                timestamp=timestamp,
                confidence=confidence,
                threshold_used=threshold,
                status=FVGStatus.ACTIVE,
                volume=current_volume,
                market_regime=self.current_context.get("market_regime"),
                strength=strength,
                creation_bar_index=bar_index,
                in_trading_range=in_trading_range,
                is_breakout=is_breakout,
                related_resistance=related_resistance,
                related_support=related_support,
            )

            detected_gaps.append(gap)

            # 更新统计信息
            self.stats["total_detected"] += 1
            self.stats["bullish_detected"] += 1

        if bear_fvg and volume_confirmation:
            fvg_id = f"fvg_{self.next_fvg_id}_{time_str}"
            self.next_fvg_id += 1

            # 计算置信度
            confidence = self._calculate_confidence(
                gap_size=bear_gap_size,
                volume_ratio=current_volume / avg_volume
                if current_volume and avg_volume
                else 1.0,
                market_regime=self.current_context.get("market_regime"),
                in_tr=self.current_context.get("in_trading_range", False),
            )

            # 计算缺口强度
            strength = self._calculate_gap_strength(
                gap_size=bear_gap_size,
                volume=current_volume,
                avg_volume=avg_volume,
                direction=FVGDirection.BEARISH,
            )

            # 上下文分析
            in_trading_range = self.current_context.get("in_trading_range", False)
            is_breakout = False
            related_resistance = None
            related_support = None

            if self.enable_context_analysis:
                # 判断是否伴随突破
                tr_support = self.current_context.get("tr_support")
                if tr_support and current_low < tr_support:
                    is_breakout = True
                    related_resistance = tr_support  # 原支撑变阻力

                # 记录相关支撑阻力（仅在非突破时使用通用值）
                if not is_breakout:
                    related_resistance = self.current_context.get("tr_resistance")
                    related_support = self.current_context.get("tr_support")
                else:
                    related_support = self.current_context.get("tr_support")

            gap = FVGGap(
                gap_id=fvg_id,
                direction=FVGDirection.BEARISH,
                max_price=prev2_low,  # 看跌FVG：上边界是前2根low
                min_price=current_high,  # 下边界是当前high
                timestamp=timestamp,
                confidence=confidence,
                threshold_used=threshold,
                status=FVGStatus.ACTIVE,
                volume=current_volume,
                market_regime=self.current_context.get("market_regime"),
                strength=strength,
                creation_bar_index=bar_index,
                in_trading_range=in_trading_range,
                is_breakout=is_breakout,
                related_resistance=related_resistance,
                related_support=related_support,
            )

            detected_gaps.append(gap)

            # 更新统计信息
            self.stats["total_detected"] += 1
            self.stats["bearish_detected"] += 1

        # 添加到历史记录和活跃列表
        for gap in detected_gaps:
            self.fvg_history.append(gap)
            self.active_fvgs.append(gap)

            # 限制历史记录长度
            if len(self.fvg_history) > 1000:
                self.fvg_history = self.fvg_history[-1000:]

        return detected_gaps

    def _calculate_confidence(
        self,
        gap_size: float,
        volume_ratio: float,
        market_regime: Optional[str],
        in_tr: bool,
    ) -> float:
        """计算FVG置信度"""
        confidence = 0.0

        # 1. 缺口大小因子（越大越可信）
        size_factor = min(gap_size * 100 / 2.0, 1.0)  # 2%缺口达到最大置信度

        # 2. 成交量因子（成交量越大越可信）
        volume_factor = min(volume_ratio / 2.0, 1.0)  # 2倍成交量达到最大置信度

        # 3. 市场体制因子
        regime_factor = 1.0
        if market_regime == "TRENDING":
            regime_factor = 0.9  # 趋势市中FVG更可信
        elif market_regime == "RANGING":
            regime_factor = 0.7  # 盘整市中FVG可信度较低

        # 4. 交易区间因子
        tr_factor = 0.8 if in_tr else 1.0  # TR内部FVG可信度较低

        # 综合置信度
        confidence = (
            size_factor * 0.4
            + volume_factor * 0.3
            + regime_factor * 0.2
            + tr_factor * 0.1
        )

        return max(0.0, min(1.0, confidence))

    def _calculate_gap_strength(
        self,
        gap_size: float,
        volume: Optional[float],
        avg_volume: Optional[float],
        direction: FVGDirection,
    ) -> float:
        """计算缺口强度"""
        strength = 1.0

        # 1. 缺口大小强度
        size_strength = min(gap_size * 100 / 1.0, 2.0)  # 1%缺口强度为1.0，最大2.0

        # 2. 成交量强度
        volume_strength = 1.0
        if volume is not None and avg_volume is not None and avg_volume > 0:
            volume_ratio = volume / avg_volume
            volume_strength = min(volume_ratio / 1.5, 2.0)  # 1.5倍成交量强度为1.0

        # 3. 方向强度调整（看涨缺口在上涨趋势中更强，看跌缺口在下跌趋势中更强）
        direction_factor = 1.0
        market_regime = self.current_context.get("market_regime")
        if market_regime == "TRENDING":
            # 简化处理，实际应根据趋势方向调整
            direction_factor = 1.1

        strength = size_strength * 0.6 + volume_strength * 0.4
        strength *= direction_factor

        return max(0.5, min(3.0, strength))  # 限制在0.5-3.0范围内

    def update_fvg_status(
        self, current_price: float, current_time: datetime, bar_index: int = 0
    ) -> list[FVGGap]:
        """
        更新FVG状态（每根新K线调用）

        Args:
            current_price: 当前价格（通常用收盘价）
            current_time: 当前时间
            bar_index: 当前K线索引（用于计算年龄）

        Returns:
            状态发生变化的FVG列表
        """
        updated_fvgs = []
        mitigated_indices = []

        for i, fvg in enumerate(self.active_fvgs):
            # 检查是否过期（超过最大年龄）— 使用创建时记录的bar_index
            age_bars = bar_index - fvg.creation_bar_index
            if age_bars > self.max_gap_age_bars:
                fvg.status = FVGStatus.EXPIRED
                updated_fvgs.append(fvg)
                mitigated_indices.append(i)
                continue

            # 检查缓解条件
            is_mitigated = False

            if fvg.direction == FVGDirection.BULLISH:
                # 看涨FVG缓解：价格跌破缺口下边界（min_price）
                if current_price < fvg.min_price:
                    is_mitigated = True
            # 看跌FVG缓解：价格突破缺口上边界（max_price）
            elif current_price > fvg.max_price:
                is_mitigated = True

            if is_mitigated and fvg.status == FVGStatus.ACTIVE:
                fvg.status = FVGStatus.MITIGATED
                fvg.mitigated_time = current_time
                fvg.mitigation_price = current_price

                updated_fvgs.append(fvg)
                mitigated_indices.append(i)

                # 更新统计信息
                self.stats["total_mitigated"] += 1
                if fvg.direction == FVGDirection.BULLISH:
                    self.stats["bullish_mitigated"] += 1
                else:
                    self.stats["bearish_mitigated"] += 1

        # 从活跃列表中移除已缓解的FVG
        for index in sorted(mitigated_indices, reverse=True):
            mitigated_fvg = self.active_fvgs.pop(index)
            self.mitigated_fvgs.append(mitigated_fvg)

        # 更新统计信息
        self._update_stats()

        return updated_fvgs

    def _update_stats(self):
        """更新统计信息"""
        total_detected = self.stats["total_detected"]
        total_mitigated = self.stats["total_mitigated"]

        if total_detected > 0:
            self.stats["mitigation_rate"] = total_mitigated / total_detected

        # 计算平均缺口大小
        if self.fvg_history:
            gap_sizes = []
            for fvg in self.fvg_history:
                gap_size_pct = (fvg.max_price - fvg.min_price) / fvg.min_price * 100
                gap_sizes.append(gap_size_pct)

            self.stats["avg_gap_size_pct"] = np.mean(gap_sizes) if gap_sizes else 0.0

        # 计算平均生命周期（简化）
        if self.mitigated_fvgs:
            lifetimes = []
            for fvg in self.mitigated_fvgs:
                if fvg.mitigated_time and fvg.timestamp:
                    lifetime = (
                        fvg.mitigated_time - fvg.timestamp
                    ).total_seconds() / 3600  # 小时
                    lifetimes.append(lifetime)

            if lifetimes:
                self.stats["avg_gap_lifetime_bars"] = np.mean(lifetimes)

    def get_active_fvgs(
        self, min_confidence: float = 0.0, min_strength: float = 0.0
    ) -> list[FVGGap]:
        """获取活跃的FVG（可过滤置信度和强度）"""
        if min_confidence <= 0 and min_strength <= 0:
            return self.active_fvgs.copy()

        filtered = []
        for fvg in self.active_fvgs:
            if fvg.confidence >= min_confidence and fvg.strength >= min_strength:
                filtered.append(fvg)

        return filtered

    def get_fvg_signals(
        self, current_price: float, current_regime: Optional[str] = None
    ) -> dict[str, Any]:
        """
        获取FVG交易信号

        Args:
            current_price: 当前价格
            current_regime: 当前市场体制

        Returns:
            交易信号字典
        """
        signals = {
            "buy_signals": [],
            "sell_signals": [],
            "support_levels": [],
            "resistance_levels": [],
            "active_fvg_count": len(self.active_fvgs),
            "recent_mitigations": len(self.mitigated_fvgs[-5:])
            if self.mitigated_fvgs
            else 0,
        }

        # 分析活跃FVG生成信号
        for fvg in self.active_fvgs:
            # 根据上下文生成不同信号
            if self.enable_context_analysis:
                # TR内部的FVG：回补信号
                if fvg.in_trading_range:
                    if fvg.direction == FVGDirection.BULLISH:
                        # 看涨FVG在TR内部：价格可能回落回补
                        if (
                            current_price > fvg.min_price
                            and current_price < fvg.max_price
                        ):
                            signals["sell_signals"].append(
                                {
                                    "type": "FVG_RETRACEMENT",
                                    "fvg_id": fvg.gap_id,
                                    "entry_price": current_price,
                                    "target_price": fvg.min_price,
                                    "stop_loss": fvg.max_price * 1.01,
                                    "confidence": fvg.confidence * 0.7,
                                    "reason": "TR内部看涨FVG回补",
                                }
                            )
                    # 看跌FVG在TR内部：价格可能反弹回补
                    elif (
                        current_price > fvg.min_price
                        and current_price < fvg.max_price
                    ):
                        signals["buy_signals"].append(
                            {
                                "type": "FVG_RETRACEMENT",
                                "fvg_id": fvg.gap_id,
                                "entry_price": current_price,
                                "target_price": fvg.max_price,
                                "stop_loss": fvg.min_price * 0.99,
                                "confidence": fvg.confidence * 0.7,
                                "reason": "TR内部看跌FVG回补",
                            }
                        )

                # 突破后的FVG：支撑阻力信号
                if fvg.is_breakout:
                    if fvg.direction == FVGDirection.BULLISH:
                        # 突破后的看涨FVG：作为支撑
                        signals["support_levels"].append(
                            {
                                "level": fvg.min_price,
                                "strength": fvg.strength,
                                "fvg_id": fvg.gap_id,
                                "type": "BREAKOUT_FVG_SUPPORT",
                            }
                        )
                    else:  # BEARISH
                        # 突破后的看跌FVG：作为阻力
                        signals["resistance_levels"].append(
                            {
                                "level": fvg.max_price,
                                "strength": fvg.strength,
                                "fvg_id": fvg.gap_id,
                                "type": "BREAKOUT_FVG_RESISTANCE",
                            }
                        )

            # 通用FVG信号（不考虑上下文）
            elif fvg.direction == FVGDirection.BULLISH:
                # 看涨FVG：价格在缺口上方时，缺口下边界作为支撑
                if current_price > fvg.max_price:
                    signals["support_levels"].append(
                        {
                            "level": fvg.min_price,
                            "strength": fvg.strength,
                            "fvg_id": fvg.gap_id,
                            "type": "BULLISH_FVG_SUPPORT",
                        }
                    )
            # 看跌FVG：价格在缺口下方时，缺口上边界作为阻力
            elif current_price < fvg.min_price:
                signals["resistance_levels"].append(
                    {
                        "level": fvg.max_price,
                        "strength": fvg.strength,
                        "fvg_id": fvg.gap_id,
                        "type": "BEARISH_FVG_RESISTANCE",
                    }
                )

        # 排序和过滤信号
        signals["buy_signals"].sort(key=lambda x: x["confidence"], reverse=True)
        signals["sell_signals"].sort(key=lambda x: x["confidence"], reverse=True)
        signals["support_levels"].sort(key=lambda x: x["strength"], reverse=True)
        signals["resistance_levels"].sort(key=lambda x: x["strength"], reverse=True)

        # 限制信号数量
        signals["buy_signals"] = signals["buy_signals"][:3]
        signals["sell_signals"] = signals["sell_signals"][:3]
        signals["support_levels"] = signals["support_levels"][:5]
        signals["resistance_levels"] = signals["resistance_levels"][:5]

        return signals

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()

        # 添加当前状态信息
        stats["active_fvg_count"] = len(self.active_fvgs)
        stats["mitigated_fvg_count"] = len(self.mitigated_fvgs)
        stats["total_fvg_count"] = len(self.fvg_history)

        # 计算最近表现
        recent_fvgs = (
            self.fvg_history[-20:] if len(self.fvg_history) >= 20 else self.fvg_history
        )
        if recent_fvgs:
            recent_bullish = sum(
                1 for fvg in recent_fvgs if fvg.direction == FVGDirection.BULLISH
            )
            recent_bearish = len(recent_fvgs) - recent_bullish
            stats["recent_bullish_ratio"] = (
                recent_bullish / len(recent_fvgs) if recent_fvgs else 0.0
            )
            stats["recent_bearish_ratio"] = (
                recent_bearish / len(recent_fvgs) if recent_fvgs else 0.0
            )

        return stats


# 简单使用示例
if __name__ == "__main__":
    # 创建模拟数据
    np.random.seed(42)
    n_bars = 200

    # 生成价格序列（包含一些FVG）
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="H")

    prices = []
    highs = []
    lows = []
    volumes = []

    base_price = 100.0

    for i in range(n_bars):
        # 随机生成一些FVG
        if i % 30 == 5 and i > 10:
            # 生成看涨FVG：当前low > 前2根high
            price = base_price + 5.0
            high = price + 1.0
            low = price - 0.5
        elif i % 35 == 10 and i > 10:
            # 生成看跌FVG：当前high < 前2根low
            price = base_price - 5.0
            high = price + 0.5
            low = price - 1.0
        else:
            # 正常价格波动
            price = base_price + np.random.randn() * 2
            high = price + abs(np.random.randn() * 1.5)
            low = price - abs(np.random.randn() * 1.5)

        volume = 1000 + np.random.rand() * 500

        prices.append(price)
        highs.append(high)
        lows.append(low)
        volumes.append(volume)

        # 更新基础价格
        base_price = price + np.random.randn() * 0.5

    df = pd.DataFrame(
        {
            "open": prices,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": volumes,
        },
        index=dates,
    )


    # 创建FVG检测器
    detector = FVGDetector(
        {
            "auto_threshold": True,
            "threshold_lookback": 20,
            "min_gap_size_pct": 0.1,
            "enable_context_analysis": True,
        }
    )

    # 模拟实时检测

    all_detected_gaps = []

    for i in range(10, len(df)):
        current_df = df.iloc[: i + 1]

        # 设置上下文（模拟）
        context = {
            "in_trading_range": i % 50 > 25,  # 模拟TR状态
            "market_regime": "TRENDING" if i % 100 > 50 else "RANGING",
            "volatility_index": 1.0 + np.random.rand() * 0.5,
        }

        # 检测FVG
        detected_gaps = detector.detect_fvg_gaps(current_df.tail(5), context, bar_index=i)

        if detected_gaps:
            for gap in detected_gaps:
                all_detected_gaps.append(gap)

        # 更新FVG状态（模拟价格变化）
        if i > 20 and all_detected_gaps:
            current_price = df["close"].iloc[i]
            current_time = df.index[i]

            updated_fvgs = detector.update_fvg_status(current_price, current_time, i)

            for fvg in updated_fvgs:
                if fvg.status == FVGStatus.MITIGATED:
                    pass

    # 获取统计信息
    stats = detector.get_statistics()


    # 获取交易信号
    current_price = df["close"].iloc[-1]
    signals = detector.get_fvg_signals(current_price)


    if signals["buy_signals"]:
        for signal in signals["buy_signals"][:3]:
            pass

    if signals["support_levels"]:
        for support in signals["support_levels"][:3]:
            pass
