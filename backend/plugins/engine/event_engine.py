"""事件引擎 — 检测器调度 + 规则引擎调用"""

from __future__ import annotations

import logging

from .models import (
    RangeContext,
    EventContext,
    Event,
    EventResult,
    Phase,
    Direction,
    StructureType,
    EngineState,
)
from .params import EventEngineParams
from .rule_engine import RuleEngine
from .detectors.base_detector import BaseDetector
from .detectors.extreme_event import ExtremeEventDetector
from .detectors.bounce import BounceDetector
from .detectors.boundary_test import BoundaryTestDetector
from .detectors.breakout import BreakoutDetector
from .detectors.supply_demand import SupplyDemandDetector

logger = logging.getLogger(__name__)


class EventEngine:
    def __init__(self, params: EventEngineParams):
        self.params = params
        self.detectors: list[BaseDetector] = [
            ExtremeEventDetector(),
            BounceDetector(),
            BoundaryTestDetector(),
            BreakoutDetector(),
            SupplyDemandDetector(),
        ]

    def process_bar(
        self,
        candle: dict,
        range_ctx: RangeContext,
        bar_index: int,
        engine_state: EngineState,
        rule_engine: RuleEngine,
    ) -> EventContext:
        """每根K线调用一次"""
        ctx = EventContext(
            current_phase=engine_state.current_phase,
            current_direction=engine_state.direction,
            structure_type=engine_state.structure_type,
        )

        # 收集所有事件（区间引擎传递的 + 检测器发现的）
        all_events = list(range_ctx.pending_events)

        # 区间刚创建的K线跳过检测器（避免ST创建区间的同时再触发Spring等边界事件）
        if not range_ctx.range_just_created:
            for detector in self.detectors:
                detected = detector.process_bar(
                    candle, range_ctx, bar_index, self.params, engine_state
                )
                if detected:
                    all_events.extend(detected)
        else:
            logger.debug("区间刚创建，跳过检测器")

        # 每个事件送规则引擎评估
        for event in all_events:
            transition = rule_engine.evaluate(event, range_ctx, engine_state)
            if transition:
                ctx.phase_transition = transition
                ctx.current_phase = transition.to_phase
                ctx.current_direction = transition.direction_after
                engine_state.current_phase = transition.to_phase
                engine_state.direction = transition.direction_after

            ctx.new_events.append(event)

        return ctx
