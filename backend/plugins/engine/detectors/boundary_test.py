"""模板1：边界测试型 — ST/Spring/UTAD/ST-B等

状态机：IDLE → APPROACHING → PENETRATING → RECOVERING → CONFIRMED/FAILED

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


class BoundaryTestDetector(BaseDetector):
    """
    边界测试检测：价格接近/穿越区间边界后回收。
    初版极宽松：任何边界接近都标记。

    状态机：IDLE → APPROACHING → PENETRATING → RECOVERING → CONFIRMED/FAILED
    """

    def __init__(self):
        self._state: str = "IDLE"

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

        # 核心检测逻辑已移除
        return []

    def reset(self) -> None:
        """重置状态机"""
        self._state = "IDLE"
