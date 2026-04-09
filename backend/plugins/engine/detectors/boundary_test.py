"""模板1：边界测试型 — ST/Spring/UTAD/ST-B等"""

from __future__ import annotations

import uuid

from ..models import (
    Event,
    EventType,
    EventResult,
    RangeContext,
    EngineState,
    Phase,
    Direction,
)
from ..params import EventEngineParams
from .base_detector import BaseDetector


class BoundaryTestDetector(BaseDetector):
    """
    边界测试检测：价格接近/穿越区间边界后回收。
    初版极宽松：任何边界接近都标记。

    状态机：IDLE → APPROACHING → PENETRATING → RECOVERING → CONFIRMED/FAILED
    """

    def __init__(self):
        self._state = "IDLE"
        self._test_type: EventType | None = None
        self._start_bar: int = 0
        self._penetrate_price: float = 0.0

    def process_bar(
        self,
        candle: dict,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        if not range_ctx.has_active_range:
            return []

        active = range_ctx.active_range
        if active is None:
            return []

        close = candle.get("close", 0)
        low = candle.get("low", 0)
        high = candle.get("high", 0)

        lower = active.primary_anchor_1.extreme_price if active.primary_anchor_1 else 0
        upper = active.opposite_anchor.extreme_price if active.opposite_anchor else 0

        if lower <= 0 or upper <= 0 or upper <= lower:
            return []

        events = []

        # ─── 下边界测试（ST/Spring/SO） ───
        if range_ctx.distance_to_lower <= params.approach_distance:
            if low <= lower:  # 穿越下边界
                if close > lower:  # 收回 = 成功
                    test_type = self._classify_lower_test(active, engine_state)
                    events.append(
                        Event(
                            event_id=str(uuid.uuid4()),
                            event_type=test_type,
                            event_result=EventResult.SUCCESS,
                            sequence_start_bar=bar_index,
                            sequence_end_bar=bar_index,
                            sequence_length=1,
                            price_extreme=low,
                            price_body=close,
                            penetration_depth=abs(low - lower) / (upper - lower)
                            if upper > lower
                            else 0,
                            position_in_range=range_ctx.position_in_range,
                            range_id=active.range_id,
                            phase=active.current_phase,
                        )
                    )

        # ─── 上边界测试（UT/UTA/UTAD） ───
        if range_ctx.distance_to_upper <= params.approach_distance:
            if high >= upper:  # 穿穿上边界
                if close < upper:  # 收回 = 成功
                    test_type = self._classify_upper_test(active, engine_state)
                    events.append(
                        Event(
                            event_id=str(uuid.uuid4()),
                            event_type=test_type,
                            event_result=EventResult.SUCCESS,
                            sequence_start_bar=bar_index,
                            sequence_end_bar=bar_index,
                            sequence_length=1,
                            price_extreme=high,
                            price_body=close,
                            penetration_depth=abs(high - upper) / (upper - lower)
                            if upper > lower
                            else 0,
                            position_in_range=range_ctx.position_in_range,
                            range_id=active.range_id,
                            phase=active.current_phase,
                        )
                    )

        return events

    def _classify_lower_test(self, active, engine_state) -> EventType:
        """根据阶段分类下边界测试类型"""
        phase = active.current_phase
        if phase == Phase.A:
            return EventType.ST
        elif phase in (Phase.B, Phase.C):
            return EventType.SPRING
        elif phase == Phase.D:
            return EventType.LPS
        return EventType.ST_B

    def _classify_upper_test(self, active, engine_state) -> EventType:
        """根据阶段分类上边界测试类型"""
        phase = active.current_phase
        if phase in (Phase.B, Phase.C):
            return EventType.UTAD
        elif phase == Phase.D:
            return EventType.LPSY
        return EventType.UT
