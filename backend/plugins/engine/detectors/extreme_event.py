"""模板3：极端事件型 — SC/BC候选检测"""

from __future__ import annotations

from ..models import Event, RangeContext, EngineState
from ..params import EventEngineParams
from .base_detector import BaseDetector


class ExtremeEventDetector(BaseDetector):
    """
    SC/BC候选由区间引擎直接处理（range_engine._seek_candidate）。
    本检测器作为扩展点保留，初版不额外处理。
    """

    def process_bar(
        self,
        candle: dict,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        # SC/BC候选已由区间引擎通过pending_events传递
        return []
