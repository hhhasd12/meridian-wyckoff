"""模板2：区间突破型 — Breakout检测器

检测价格是否离开了区间。
状态机：IDLE → APPROACHING → CANDIDATE → CONFIRMED/FAILED
边界三级退回：莱恩标注的Creek/Ice → 引擎拟合的 → 区间通道边界
不硬编码量价要求：缩量突破和放量突破都合法。
"""

from __future__ import annotations

import logging
import uuid

from ..models import (
    Event,
    EventType,
    EventResult,
    RangeContext,
    EngineState,
    Range,
    TrendLine,
    Phase,
    AnchorPoint,
)
from ..params import EventEngineParams
from .base_detector import BaseDetector

logger = logging.getLogger(__name__)

# 状态机常量
_IDLE = "IDLE"
_APPROACHING = "APPROACHING"
_CANDIDATE = "CANDIDATE"

# 边界类型
_CREEK = "CREEK"
_ICE = "ICE"
_CHANNEL = "CHANNEL"


class BreakoutDetector(BaseDetector):
    """
    区间突破检测器 — 检测价格是否离开区间。

    只做一件事：检测价格是否离开了区间。
    不判断阶段、不判断方向、不做交易决策、不硬编码量价要求。
    """

    def __init__(self):
        self._state: str = _IDLE
        self._candidate_bar: int = 0
        self._candidate_price: float = 0.0
        self._boundary_value: float = 0.0
        self._boundary_type: str = _CHANNEL
        self._direction: str = ""  # "UP" / "DOWN"
        self._penetration_depth: float = 0.0
        self._approach_start_bar: int = 0
        self._max_departure: float = 0.0
        self._recent_volumes: list[float] = []
        self._bars_since_candidate: int = 0
        self._has_pullback: bool = False
        self._pullback_depth: float = 0.0
        self._pullback_volume: float = 0.0

    def process_bar(
        self,
        candle: dict,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        """每根K线调用一次，返回事件或空列表"""
        if not range_ctx.has_active_range:
            return []
        active = range_ctx.active_range
        if active is None:
            return []

        close = candle.get("close", 0)
        high = candle.get("high", 0)
        low = candle.get("low", 0)
        volume = candle.get("volume", 0)

        bp = params.breakout

        # 更新量价历史窗口
        self._recent_volumes.append(float(volume))
        if len(self._recent_volumes) > bp.volume_context_window:
            self._recent_volumes.pop(0)

        # 区间宽度（用于归一化）
        channel_width = self._get_channel_width(active)
        if channel_width <= 0:
            return []

        events: list[Event] = []

        if self._state == _IDLE:
            events = self._handle_idle(
                candle, active, range_ctx, bar_index, bp, channel_width, engine_state
            )
        elif self._state == _APPROACHING:
            events = self._handle_approaching(
                candle, active, range_ctx, bar_index, bp, channel_width, engine_state
            )
        elif self._state == _CANDIDATE:
            events = self._handle_candidate(
                candle, active, range_ctx, bar_index, bp, channel_width, engine_state
            )

        return events

    # ═══ 状态处理 ═══

    def _handle_idle(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        bp,
        channel_width: float,
        engine_state: EngineState,
    ) -> list[Event]:
        """IDLE状态：检查价格是否接近或穿越边界"""
        high = candle.get("high", 0)
        low = candle.get("low", 0)
        close = candle.get("close", 0)

        approach_zone_abs = bp.approach_zone * channel_width
        breakout_depth_abs = bp.breakout_depth * channel_width

        # 检查上边界
        upper_boundary, upper_type = self._get_boundary(active, bar_index, "upper")
        if upper_boundary > 0:
            dist_inside = (
                upper_boundary - low
            )  # 价格低点到上边界的距离（正=还在区间内）
            penetration = high - upper_boundary  # 穿越深度（正=已穿越）

            # 情况1：大幅穿越（加密市场常见）→ 直接跳到 CANDIDATE
            if penetration >= breakout_depth_abs and close > upper_boundary:
                self._state = _CANDIDATE
                self._approach_start_bar = bar_index
                self._candidate_bar = bar_index
                self._candidate_price = close
                self._direction = "UP"
                self._boundary_value = upper_boundary
                self._boundary_type = upper_type
                self._penetration_depth = penetration / channel_width
                self._bars_since_candidate = 0
                self._max_departure = penetration
                self._has_pullback = False
                self._pullback_depth = 0.0
                self._pullback_volume = 0.0

                features = self._extract_features(
                    candle, active, range_ctx, bar_index, channel_width, engine_state
                )
                event = self._make_event(
                    EventType.BREAKOUT_CANDIDATE,
                    EventResult.PENDING,
                    bar_index,
                    candle,
                    active,
                    features,
                )
                return [event]

            # 情况2：接近边界（从区间内部逼近或小幅穿越）→ APPROACHING
            if dist_inside < approach_zone_abs:
                self._state = _APPROACHING
                self._approach_start_bar = bar_index
                self._direction = "UP"
                self._boundary_value = upper_boundary
                self._boundary_type = upper_type
                return []

        # 检查下边界
        lower_boundary, lower_type = self._get_boundary(active, bar_index, "lower")
        if lower_boundary > 0:
            dist_inside = (
                high - lower_boundary
            )  # 价格高点到下边界的距离（正=还在区间内）
            penetration = lower_boundary - low  # 穿越深度（正=已穿越）

            # 情况1：大幅穿越 → 直接跳到 CANDIDATE
            if penetration >= breakout_depth_abs and close < lower_boundary:
                self._state = _CANDIDATE
                self._approach_start_bar = bar_index
                self._candidate_bar = bar_index
                self._candidate_price = close
                self._direction = "DOWN"
                self._boundary_value = lower_boundary
                self._boundary_type = lower_type
                self._penetration_depth = penetration / channel_width
                self._bars_since_candidate = 0
                self._max_departure = penetration
                self._has_pullback = False
                self._pullback_depth = 0.0
                self._pullback_volume = 0.0

                features = self._extract_features(
                    candle, active, range_ctx, bar_index, channel_width, engine_state
                )
                event = self._make_event(
                    EventType.BREAKOUT_CANDIDATE,
                    EventResult.PENDING,
                    bar_index,
                    candle,
                    active,
                    features,
                )
                return [event]

            # 情况2：接近边界 → APPROACHING
            if dist_inside < approach_zone_abs:
                self._state = _APPROACHING
                self._approach_start_bar = bar_index
                self._direction = "DOWN"
                self._boundary_value = lower_boundary
                self._boundary_type = lower_type
                return []

        return []

    def _handle_approaching(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        bp,
        channel_width: float,
        engine_state: EngineState,
    ) -> list[Event]:
        """APPROACHING状态：检查收盘价是否越过边界"""
        close = candle.get("close", 0)

        # 重新计算当前K线的边界价格（斜线支持）
        boundary, _ = self._get_boundary(
            active, bar_index, "upper" if self._direction == "UP" else "lower"
        )
        self._boundary_value = boundary

        if boundary <= 0:
            self._state = _IDLE
            return []

        breakout_depth_abs = bp.breakout_depth * channel_width

        if self._direction == "UP":
            penetration = close - boundary
        else:
            penetration = boundary - close

        if penetration >= breakout_depth_abs:
            # 收盘越过边界 → CANDIDATE
            self._state = _CANDIDATE
            self._candidate_bar = bar_index
            self._candidate_price = close
            self._penetration_depth = penetration / channel_width
            self._bars_since_candidate = 0
            self._max_departure = penetration
            self._has_pullback = False
            self._pullback_depth = 0.0
            self._pullback_volume = 0.0

            features = self._extract_features(
                candle, active, range_ctx, bar_index, channel_width, engine_state
            )

            event = self._make_event(
                EventType.BREAKOUT_CANDIDATE,
                EventResult.PENDING,
                bar_index,
                candle,
                active,
                features,
            )
            return [event]

        # 没越过 → 超时或远离则回到IDLE
        bars_in_approach = bar_index - self._approach_start_bar
        if bars_in_approach > bp.confirm_bars * 3:
            self._state = _IDLE

        return []

    def _handle_candidate(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        bp,
        channel_width: float,
        engine_state: EngineState,
    ) -> list[Event]:
        """CANDIDATE状态：等待确认或失败"""
        close = candle.get("close", 0)
        low = candle.get("low", 0)
        high = candle.get("high", 0)
        volume = candle.get("volume", 0)

        self._bars_since_candidate += 1

        # 重新计算边界价格（斜线支持）
        boundary, _ = self._get_boundary(
            active, bar_index, "upper" if self._direction == "UP" else "lower"
        )
        self._boundary_value = boundary

        if boundary <= 0:
            # 无法计算边界 → 重置
            self._state = _IDLE
            return []

        confirm_dist_abs = bp.confirm_distance * channel_width

        if self._direction == "UP":
            departure = close - boundary
        else:
            departure = boundary - close

        # 追踪最大远离距离
        if departure > self._max_departure:
            self._max_departure = departure

        # ── 确认方式1：距离确认 — 远离超过阈值 ──
        if departure >= confirm_dist_abs:
            self._state = _IDLE
            features = self._extract_features(
                candle, active, range_ctx, bar_index, channel_width, engine_state
            )
            features["confirmation_method"] = "distance"
            features["departure_distance"] = departure / channel_width
            event = self._make_event(
                EventType.BREAKOUT_CONFIRMED,
                EventResult.SUCCESS,
                bar_index,
                candle,
                active,
                features,
            )
            return [event]

        # ── 确认方式2：事件确认 — 回踩边界不破 ──
        # 检测回踩：价格曾回到边界附近但收盘价仍在边界外
        if not self._has_pullback and self._bars_since_candidate >= 2:
            if self._direction == "UP":
                pullback = boundary - low  # 低点距离边界多近
                close_holds = close > boundary  # W4: 收盘价仍在边界上方
            else:
                pullback = high - boundary
                close_holds = close < boundary  # W4: 收盘价仍在边界下方

            # W4修复：影线刺穿但收盘不破 + 刺穿深度在阈值内 → 回踩确认
            if (
                pullback > 0
                and close_holds
                and pullback < bp.approach_zone * channel_width
            ):
                # 回踩到边界附近但没突破 → 这是回踩
                self._has_pullback = True
                self._pullback_depth = pullback / channel_width
                self._pullback_volume = float(volume)
                # 回踩不破 = 确认
                self._state = _IDLE
                features = self._extract_features(
                    candle, active, range_ctx, bar_index, channel_width, engine_state
                )
                features["confirmation_method"] = "pullback_hold"
                features["has_pullback"] = True
                features["pullback_depth"] = self._pullback_depth
                features["pullback_volume_ratio"] = self._volume_ratio()
                event = self._make_event(
                    EventType.BREAKOUT_CONFIRMED,
                    EventResult.SUCCESS,
                    bar_index,
                    candle,
                    active,
                    features,
                )
                return [event]

        # ── 失败：回到区间内（假突破） ──
        # 回来超过穿越深度的 return_threshold 比例
        if self._penetration_depth > 0 and self._candidate_price > 0:
            penetration_abs = self._penetration_depth * channel_width
            return_threshold_abs = penetration_abs * bp.return_threshold

            if self._direction == "UP":
                # 向上突破但价格回到突破价以下
                returned = self._candidate_price - close
            else:
                # 向下突破但价格回到突破价以上
                returned = close - self._candidate_price

            if returned >= return_threshold_abs:
                self._state = _IDLE
                features = self._extract_features(
                    candle, active, range_ctx, bar_index, channel_width, engine_state
                )
                features["has_pullback"] = self._has_pullback
                event = self._make_event(
                    EventType.BREAKOUT_FAILED,
                    EventResult.FAILED,
                    bar_index,
                    candle,
                    active,
                    features,
                )
                return [event]

        # 超时安全阀：candidate持续太久未确认也未失败
        if self._bars_since_candidate > bp.confirm_bars * 10:
            logger.debug(
                "Breakout candidate 超时: direction=%s, bars=%d",
                self._direction,
                self._bars_since_candidate,
            )
            self._state = _IDLE

        return []

    # ═══ 边界获取：三级退回 ═══

    def _get_boundary(
        self, active: Range, bar_index: int, side: str
    ) -> tuple[float, str]:
        """
        三级退回获取边界价格。

        优先级：
        1. 莱恩标注的Creek/Ice（标注数据中的线段）
        2. 引擎拟合的Creek/Ice（区间引擎自动拟合的趋势线）
        3. 区间通道边界（三点定区间的上下轨，永远存在）

        W2修复：根据 entry_trend 和锚点价格判断真正的上下边界。
        - 吸筹（SC进入）：primary_anchor_1(SC)=底部, opposite_anchor(AR)=顶部
        - 派发（BC进入）：primary_anchor_1(BC)=顶部, opposite_anchor(AR)=底部
        因此需要比较两个锚点的价格来确定哪个是上边界、哪个是下边界。

        返回 (boundary_price, boundary_type)
        """
        if side == "upper":
            # 上边界 = Creek（吸筹）或价格更高的锚点
            creek = active.creek
            if creek is not None:
                return creek.price_at(bar_index), _CREEK
            # 兜底：取两个锚点中价格更高的作为上边界
            upper = self._get_upper_anchor(active)
            if upper is not None:
                # 支持斜线通道
                if active.channel_slope != 0 and active.primary_anchor_1 is not None:
                    slope_offset = active.channel_slope * (
                        bar_index - active.primary_anchor_1.bar_index
                    )
                    return upper.extreme_price + slope_offset, _CHANNEL
                return upper.extreme_price, _CHANNEL
        else:
            # 下边界 = Ice（派发）或价格更低的锚点
            ice = active.ice
            if ice is not None:
                return ice.price_at(bar_index), _ICE
            # 兜底：取两个锚点中价格更低的作为下边界
            lower = self._get_lower_anchor(active)
            if lower is not None:
                if active.channel_slope != 0 and active.primary_anchor_1 is not None:
                    slope_offset = active.channel_slope * (
                        bar_index - active.primary_anchor_1.bar_index
                    )
                    return lower.extreme_price + slope_offset, _CHANNEL
                return lower.extreme_price, _CHANNEL

        return 0.0, _CHANNEL

    def _get_upper_anchor(self, active: Range) -> AnchorPoint | None:
        """获取上下边界锚点中价格更高的那个"""
        p1 = active.primary_anchor_1
        opp = active.opposite_anchor
        if p1 is not None and opp is not None:
            return opp if opp.extreme_price >= p1.extreme_price else p1
        return opp or p1

    def _get_lower_anchor(self, active: Range) -> AnchorPoint | None:
        """获取上下边界锚点中价格更低的那个"""
        p1 = active.primary_anchor_1
        opp = active.opposite_anchor
        if p1 is not None and opp is not None:
            return p1 if p1.extreme_price <= opp.extreme_price else opp
        return p1 or opp

    def _get_channel_width(self, active: Range) -> float:
        """获取区间宽度"""
        if active.channel_width > 0:
            return active.channel_width
        # 兜底：从锚点计算
        lower = active.primary_anchor_1
        upper = active.opposite_anchor
        if lower is not None and upper is not None:
            return abs(upper.extreme_price - lower.extreme_price)
        return 0.0

    # ═══ 特征提取 ═══

    def _extract_features(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        channel_width: float,
        engine_state: EngineState,
    ) -> dict:
        """
        提取特征给进化系统（BREAKOUT_DESIGN.md §5）。

        四大类：
        1. 突破时刻
        2. 突破前背景
        3. 突破后行为
        4. 事件链上下文（EVD-10）
        """
        close = candle.get("close", 0)
        open_ = candle.get("open", 0)
        high = candle.get("high", 0)
        low = candle.get("low", 0)
        volume = candle.get("volume", 0)

        features: dict = {}

        # ─── 5.1 突破时刻 ───
        features["penetration_depth"] = self._penetration_depth
        features["breakout_bar_volume_ratio"] = self._volume_ratio()
        # K线实体占比
        total_range = high - low
        features["bar_body_ratio"] = (
            abs(close - open_) / total_range if total_range > 0 else 0.0
        )
        # K线方向
        features["bar_direction"] = "up" if close >= open_ else "down"

        # ─── 5.2 突破前背景 ───
        features["range_duration"] = bar_index - active.created_at_bar
        features["volume_trend"] = self._volume_trend()
        features["boundary_test_count"] = active.test_count
        features["last_test_distance"] = (
            bar_index - active.last_test_bar if active.last_test_bar is not None else 0
        )

        # ─── 5.3 突破后行为 ───
        features["has_pullback"] = self._has_pullback
        features["pullback_depth"] = self._pullback_depth
        features["pullback_volume_ratio"] = (
            self._pullback_volume / self._avg_volume()
            if self._avg_volume() > 0 and self._pullback_volume > 0
            else 0.0
        )
        # 远离速度
        if self._bars_since_candidate > 0 and self._candidate_price > 0:
            features["departure_speed"] = abs(close - self._candidate_price) / (
                self._candidate_price * self._bars_since_candidate
            )
        else:
            features["departure_speed"] = 0.0

        # ─── 5.4 事件链上下文（EVD-10） ───
        features["prior_events"] = self._get_prior_events(engine_state)
        features["current_phase"] = (
            active.current_phase.value if active.current_phase else ""
        )
        features["range_shape"] = active.range_shape.value if active.range_shape else ""

        # 方向和边界类型（给下游消费者）
        features["direction"] = self._direction
        features["boundary_type"] = self._boundary_type

        return features

    def _get_prior_events(self, engine_state: EngineState) -> list[str]:
        """
        EVD-10: 从当前区间的事件历史中提取已发生事件的类型列表。
        去重，保持时间顺序。
        """
        seen: set[str] = set()
        result: list[str] = []
        for event in engine_state.recent_events:
            et = event.event_type.value
            if et not in seen:
                seen.add(et)
                result.append(et)
        return result

    # ═══ 辅助计算 ═══

    def _avg_volume(self) -> float:
        """近期平均成交量"""
        if not self._recent_volumes:
            return 1.0
        return sum(self._recent_volumes) / len(self._recent_volumes)

    def _volume_ratio(self) -> float:
        """当前K线成交量 / 近期均量"""
        if not self._recent_volumes:
            return 1.0
        current = self._recent_volumes[-1] if self._recent_volumes else 0
        avg = self._avg_volume()
        return current / avg if avg > 0 else 1.0

    def _volume_trend(self) -> str:
        """
        末期成交量趋势判断。
        不硬编码"缩量才算突破" — 缩量/放量/平稳都合法。
        """
        n = len(self._recent_volumes)
        if n < 5:
            return "insufficient_data"

        first_half = self._recent_volumes[: n // 2]
        second_half = self._recent_volumes[n // 2 :]

        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0

        if avg_first <= 0:
            return "insufficient_data"

        ratio = avg_second / avg_first
        if ratio < 0.7:
            return "drying"  # 缩量
        elif ratio > 1.3:
            return "expanding"  # 放量
        else:
            return "stable"  # 平稳

    # ═══ 事件构造 ═══

    def _make_event(
        self,
        event_type: EventType,
        result: EventResult,
        bar_index: int,
        candle: dict,
        active: Range,
        features: dict,
    ) -> Event:
        """构造Breakout事件"""
        # W3修复：position_in_range = (price - lower) / (upper - lower)
        # 不使用 penetration_depth，它语义完全不同
        close = candle.get("close", 0)
        pos_in_range = self._calc_position_in_range(close, active)

        return Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            event_result=result,
            sequence_start_bar=self._candidate_bar
            if self._candidate_bar
            else bar_index,
            sequence_end_bar=bar_index,
            sequence_length=bar_index - self._candidate_bar + 1
            if self._candidate_bar
            else 1,
            price_extreme=candle.get("high" if self._direction == "UP" else "low", 0),
            price_body=candle.get("close", 0),
            penetration_depth=features.get("penetration_depth", 0.0),
            position_in_range=pos_in_range,
            range_id=active.range_id,
            phase=active.current_phase,
            variant_tag=f"{self._direction}_{self._boundary_type}",
            variant_features=features,
        )

    def _calc_position_in_range(self, price: float, active: Range) -> float:
        """计算价格在区间中的相对位置：0=下沿, 1=上沿"""
        lower = self._get_lower_anchor(active)
        upper = self._get_upper_anchor(active)
        if lower is None or upper is None:
            return 0.0
        range_height = upper.extreme_price - lower.extreme_price
        if range_height <= 0:
            return 0.0
        return (price - lower.extreme_price) / range_height

    def reset(self) -> None:
        """重置状态机"""
        self._state = _IDLE
        self._candidate_bar = 0
        self._candidate_price = 0.0
        self._boundary_value = 0.0
        self._boundary_type = _CHANNEL
        self._direction = ""
        self._penetration_depth = 0.0
        self._approach_start_bar = 0
        self._max_departure = 0.0
        self._bars_since_candidate = 0
        self._has_pullback = False
        self._pullback_depth = 0.0
        self._pullback_volume = 0.0
        self._recent_volumes = []  # I1: 重置量价历史，避免跨区间污染
