"""模板4：反弹回落型 — AR检测"""

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


class BounceDetector(BaseDetector):
    """
    AR检测：SC/BC之后的反弹。
    初版极宽松：任何方向相反的价格运动都可能是AR。
    """

    def __init__(self):
        self._tracking = False
        self._bounce_start_bar: int = 0
        self._bounce_start_price: float = 0.0
        self._bounce_peak: float = 0.0
        self._bounce_bars: int = 0

    def process_bar(
        self,
        candle: dict,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        # 只在有候选SC/BC且无活跃区间时检测AR
        if range_ctx.has_active_range:
            return []

        candidate = engine_state.candidate_extreme
        if candidate is None:
            return []

        # 已经有AR了就不重复检测
        if engine_state.current_phase != Phase.A:
            return []

        is_sc = candidate.candidate_type == "SC"
        close = candle.get("close", 0)
        high = candle.get("high", 0)
        low = candle.get("low", 0)

        if not self._tracking:
            # 开始追踪反弹
            if is_sc and close > candidate.extreme_price:
                self._tracking = True
                self._bounce_start_bar = bar_index
                self._bounce_start_price = candidate.extreme_price
                self._bounce_peak = high
                self._bounce_bars = 1
            elif not is_sc and close < candidate.extreme_price:
                self._tracking = True
                self._bounce_start_bar = bar_index
                self._bounce_start_price = candidate.extreme_price
                self._bounce_peak = low
                self._bounce_bars = 1
            return []

        # 追踪中
        self._bounce_bars += 1

        if is_sc:
            if high > self._bounce_peak:
                self._bounce_peak = high
            # 反弹结束检测：价格开始回落
            if close < self._bounce_peak * 0.98:  # 从峰值回落2%视为AR结束
                bounce_pct = (
                    abs(self._bounce_peak - self._bounce_start_price)
                    / self._bounce_start_price
                )
                if (
                    bounce_pct >= 0.01  # ar_min_bounce_pct default
                    and self._bounce_bars >= 1  # ar_min_bars default
                ):
                    self._tracking = False
                    return [
                        Event(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.AR,
                            event_result=EventResult.SUCCESS,
                            sequence_start_bar=self._bounce_start_bar,
                            sequence_end_bar=bar_index,
                            sequence_length=self._bounce_bars,
                            price_extreme=self._bounce_peak,
                            price_body=close,
                        )
                    ]
        else:
            if low < self._bounce_peak:
                self._bounce_peak = low
            if close > self._bounce_peak * 1.02:
                bounce_pct = (
                    abs(self._bounce_peak - self._bounce_start_price)
                    / self._bounce_start_price
                )
                if (
                    bounce_pct >= 0.01  # ar_min_bounce_pct default
                    and self._bounce_bars >= 1  # ar_min_bars default
                ):
                    self._tracking = False
                    return [
                        Event(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.AR,
                            event_result=EventResult.SUCCESS,
                            sequence_start_bar=self._bounce_start_bar,
                            sequence_end_bar=bar_index,
                            sequence_length=self._bounce_bars,
                            price_extreme=self._bounce_peak,
                            price_body=close,
                        )
                    ]

        return []
