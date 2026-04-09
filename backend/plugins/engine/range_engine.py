"""区间引擎 — 场域基础设施"""

from __future__ import annotations

import logging
import uuid

from .models import (
    RangeContext,
    Range,
    RangeStatus,
    Phase,
    Direction,
    RangeShape,
    CandidateExtreme,
    AnchorPoint,
    Event,
    EventType,
    EventResult,
    EngineState,
)
from .params import RangeEngineParams

logger = logging.getLogger(__name__)


class RangeEngine:
    def __init__(self, params: RangeEngineParams):
        self.params = params
        self.candidate_extreme: CandidateExtreme | None = None
        self.archived_ranges: list[Range] = []
        # 趋势均量追踪
        self._trend_volume_sum: float = 0.0
        self._trend_volume_count: int = 0

    def process_bar(
        self, candle: dict, bar_index: int, engine_state: EngineState
    ) -> RangeContext:
        """
        每根K线调用一次。

        核心逻辑：
        1. 没有活跃区间 → 寻找SC/BC候选 + 检测AR + 检测ST
        2. 有活跃区间 → 更新位置 + 更新形状 + 检测边界事件
        """
        ctx = RangeContext()
        active = engine_state.active_range

        if active is None:
            # ─── 趋势运行中：寻找新区间 ───
            self._update_trend_volume(candle)
            # 1. 先检查ST（如果候选+AR都就位）
            #    ST检查必须在_seek_candidate之前，否则刺破+收回会被错误识别为新SC（ED-9）
            if (
                self.candidate_extreme is not None
                and engine_state.ar_anchor is not None
            ):
                if self._check_st(candle, bar_index, engine_state, ctx):
                    return ctx  # 区间已创建，本轮结束
            # 2. 再检查新极值（可能创建/替换SC/BC候选）
            self._seek_candidate(candle, bar_index, engine_state, ctx)
        else:
            # ─── 有活跃区间：更新状态 ───
            ctx.has_active_range = True
            ctx.active_range = active
            active.duration_bars = bar_index - active.created_at_bar
            self._update_position(candle, active, ctx)
            if active.current_phase == Phase.B:
                self._update_range_shape(candle, bar_index, active)
                self._update_creek_ice(candle, bar_index, active)

        return ctx

    def _check_st(
        self, candle: dict, bar_index: int, engine_state: EngineState, ctx: RangeContext
    ) -> bool:
        """
        Phase.A的ST检测：价格回到SC/BC极值位附近（ED-8）。

        极宽松判断（ED-2/RD-55）：
        - SC情况：low接近或穿越SC极值 + close收回到SC上方 → ST成功
        - BC情况：high接近或穿越BC极值 + close收回到BC下方 → ST成功

        ST成功 → 创建ST Event + 调用create_range() + 设置ctx.active_range

        返回True表示区间已创建，False表示未触发ST。
        """
        candidate = self.candidate_extreme
        ar = engine_state.ar_anchor
        if candidate is None or ar is None:
            return False

        threshold = self.params.st_max_distance_pct  # 初版0.20
        close = candle.get("close", 0)
        low = candle.get("low", 0)
        high = candle.get("high", 0)
        volume = candle.get("volume", 0)

        is_sc = candidate.candidate_type == "SC"

        if is_sc:
            sc_level = candidate.extreme_price
            # 价格接近或穿越SC位
            if low <= sc_level * (1 + threshold):
                if close > sc_level:  # 收回 = ST成功
                    st_anchor = AnchorPoint(
                        bar_index=bar_index,
                        extreme_price=low,
                        body_price=close,
                        volume=volume,
                    )
                    st_event = Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.ST,
                        event_result=EventResult.SUCCESS,
                        sequence_start_bar=bar_index,
                        sequence_end_bar=bar_index,
                        sequence_length=1,
                        price_extreme=low,
                        price_body=close,
                    )
                    ctx.pending_events.append(st_event)

                    new_range = self.create_range(
                        candidate, ar, st_anchor, engine_state.direction
                    )
                    new_range.timeframe = engine_state.timeframe
                    ctx.has_active_range = True
                    ctx.active_range = new_range
                    ctx.range_just_created = True

                    # 清理区间形成状态
                    self.candidate_extreme = None
                    engine_state.ar_anchor = None
                    self._trend_volume_sum = 0.0
                    self._trend_volume_count = 0

                    logger.info(
                        "ST确认，区间创建: range_id=%s, entry=%s, phase=B",
                        new_range.range_id[:8],
                        new_range.entry_trend.value,
                    )
                    return True
                # close没收回 = 不是ST，是新低。让_seek_candidate处理
                return False
        else:
            bc_level = candidate.extreme_price
            if high >= bc_level * (1 - threshold):
                if close < bc_level:  # 收回 = ST成功
                    st_anchor = AnchorPoint(
                        bar_index=bar_index,
                        extreme_price=high,
                        body_price=close,
                        volume=volume,
                    )
                    st_event = Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.ST,
                        event_result=EventResult.SUCCESS,
                        sequence_start_bar=bar_index,
                        sequence_end_bar=bar_index,
                        sequence_length=1,
                        price_extreme=high,
                        price_body=close,
                    )
                    ctx.pending_events.append(st_event)

                    new_range = self.create_range(
                        candidate, ar, st_anchor, engine_state.direction
                    )
                    new_range.timeframe = engine_state.timeframe
                    ctx.has_active_range = True
                    ctx.active_range = new_range
                    ctx.range_just_created = True

                    self.candidate_extreme = None
                    engine_state.ar_anchor = None
                    self._trend_volume_sum = 0.0
                    self._trend_volume_count = 0

                    logger.info(
                        "ST确认，区间创建: range_id=%s, entry=%s, phase=B",
                        new_range.range_id[:8],
                        new_range.entry_trend.value,
                    )
                    return True
                return False

        return False

    def _seek_candidate(
        self, candle: dict, bar_index: int, engine_state: EngineState, ctx: RangeContext
    ) -> None:
        """趋势中寻找SC/BC候选"""
        direction = engine_state.direction
        is_sc = direction in (Direction.SHORT, Direction.NEUTRAL)

        extreme = candle.get("low", 0) if is_sc else candle.get("high", 0)

        # 每个新低/新高都是候选（ED-2：零门槛）
        is_new_extreme = False
        if self.candidate_extreme is None:
            is_new_extreme = True
        elif is_sc and extreme < self.candidate_extreme.extreme_price:
            is_new_extreme = True
        elif not is_sc and extreme > self.candidate_extreme.extreme_price:
            is_new_extreme = True

        if is_new_extreme:
            # ED-9：如果有AR锚点，检查是否可能是ST（刺破+收回）
            # 如果是ST情况，不替换候选，由_check_st在下一轮处理
            if (
                engine_state.ar_anchor is not None
                and self.candidate_extreme is not None
            ):
                close = candle.get("close", 0)
                old_is_sc = self.candidate_extreme.candidate_type == "SC"
                if old_is_sc and close > self.candidate_extreme.extreme_price:
                    return  # 刺破SC但收回 = 可能是ST，不替换
                elif not old_is_sc and close < self.candidate_extreme.extreme_price:
                    return  # 刺破BC但收回 = 可能是ST，不替换

            # 真正的新极值 → 替换候选 + 重置AR锚点
            engine_state.ar_anchor = None  # 新候选意味着新的区间形成序列

            trend_avg_vol = self._get_trend_avg_volume()
            vol_ratio = (
                candle.get("volume", 0) / trend_avg_vol if trend_avg_vol > 0 else 1.0
            )

            new_candidate = CandidateExtreme(
                candidate_type="SC" if is_sc else "BC",
                bar_index=bar_index,
                extreme_price=extreme,
                body_price=candle.get("close", extreme),
                volume=candle.get("volume", 0),
                volume_ratio=vol_ratio,
                confidence=0.0,  # 初版不评分
            )

            # 替换旧候选
            if self.candidate_extreme is not None:
                self.candidate_extreme.replaced_by = new_candidate.candidate_type
                # TODO: 旧候选存入记忆层

            self.candidate_extreme = new_candidate

            # 创建SC/BC事件传递给事件引擎
            event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.SC if is_sc else EventType.BC,
                event_result=EventResult.PENDING,
                sequence_start_bar=bar_index,
                sequence_end_bar=bar_index,
                sequence_length=1,
                price_extreme=extreme,
                price_body=candle.get("close", extreme),
                volume_ratio=vol_ratio,
            )
            ctx.pending_events.append(event)

    def _update_position(self, candle: dict, active: Range, ctx: RangeContext) -> None:
        """计算价格在区间中的位置"""
        if active.channel_width <= 0:
            return
        price = candle.get("close", 0)
        # 简化版：用锚点价格计算（完整版用趋势线）
        lower = active.primary_anchor_1.extreme_price if active.primary_anchor_1 else 0
        upper = active.opposite_anchor.extreme_price if active.opposite_anchor else 0
        if upper <= lower:
            return
        ctx.position_in_range = (price - lower) / (upper - lower)
        ctx.distance_to_lower = abs(price - lower) / lower if lower > 0 else 0
        ctx.distance_to_upper = abs(price - upper) / upper if upper > 0 else 0

    def _update_trend_volume(self, candle: dict) -> None:
        """更新趋势均量"""
        vol = candle.get("volume", 0)
        self._trend_volume_sum += vol
        self._trend_volume_count += 1

    def _get_trend_avg_volume(self) -> float:
        if self._trend_volume_count == 0:
            return 1.0
        return self._trend_volume_sum / self._trend_volume_count

    def _update_range_shape(self, candle: dict, bar_index: int, active: Range) -> None:
        """阶段B：更新区间形状（拟合趋势线）"""
        # TODO: 收集ST-B高低点 → 拟合趋势线 → 更新slope
        pass

    def _update_creek_ice(self, candle: dict, bar_index: int, active: Range) -> None:
        """阶段B：更新Creek/Ice"""
        # TODO: 收集反弹高点/回调低点 → 拟合趋势线
        pass

    def create_range(
        self,
        sc_bc: CandidateExtreme,
        ar: AnchorPoint,
        st: AnchorPoint,
        entry_trend: Direction,
    ) -> Range:
        """三点定区间：SC/BC + AR + ST → 创建Range"""
        is_sc = sc_bc.candidate_type == "SC"
        primary1 = AnchorPoint(
            bar_index=sc_bc.bar_index,
            extreme_price=sc_bc.extreme_price,
            body_price=sc_bc.body_price,
            volume=sc_bc.volume,
        )

        # 计算通道
        slope = (st.extreme_price - primary1.extreme_price) / max(
            1, st.bar_index - primary1.bar_index
        )
        width = abs(ar.extreme_price - primary1.extreme_price)

        # 判断形状
        if abs(slope) < 0.0001:
            shape = RangeShape.HORIZONTAL
        elif slope > 0:
            shape = RangeShape.ASCENDING
        else:
            shape = RangeShape.DESCENDING

        return Range(
            range_id=str(uuid.uuid4()),
            timeframe="",  # 由plugin设置
            channel_slope=slope,
            channel_width=width,
            primary_anchor_1=primary1,
            primary_anchor_2=st,
            opposite_anchor=ar,
            entry_trend=entry_trend,
            range_shape=shape,
            status=RangeStatus.CONFIRMED,
            created_at_bar=primary1.bar_index,
            confirmed_at_bar=st.bar_index,
            current_phase=Phase.B,
        )
