"""检测器基类"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Event, RangeContext, EngineState
from ..params import EventEngineParams


class BaseDetector(ABC):
    @abstractmethod
    def process_bar(
        self,
        candle: dict,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        """返回本根K线检测到的事件列表（可为空）"""
        ...
