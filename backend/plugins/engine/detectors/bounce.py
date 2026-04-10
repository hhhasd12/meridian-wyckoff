"""模板4：反弹回落型 — AR检测

> ⚠️ 核心算法已移除。此文件为接口占位，保留类结构和方法签名。
> 完整实现仅在本机开发环境可用。
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
    Phase,
)
from ..params import EventEngineParams
from .base_detector import BaseDetector

logger = logging.getLogger(__name__)


class BounceDetector(BaseDetector):
    """
    AR检测：SC/BC之后的反弹。
    初版极宽松：任何方向相反的价格运动都可能是AR。
    """

    def __init__(self):
        self._tracking: bool = False
        self._bounce_start_bar: int = 0
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
        """每根K线调用一次，返回事件或空列表"""
        if range_ctx.has_active_range:
            return []

        candidate = engine_state.candidate_extreme
        if candidate is None:
            return []
        if engine_state.current_phase != Phase.A:
            return []

        # 核心检测逻辑已移除
        return []

    def reset(self) -> None:
        """重置状态机"""
        self._tracking = False
        self._bounce_start_bar = 0
        self._bounce_peak = 0.0
        self._bounce_bars = 0
