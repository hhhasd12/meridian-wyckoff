"""回测运行器 — 逐根K线驱动引擎"""

from __future__ import annotations

import logging

from backend.plugins.engine.models import (
    AnchorPoint,
    EngineState,
    EventType,
)
from backend.plugins.engine.range_engine import RangeEngine
from backend.plugins.engine.event_engine import EventEngine
from backend.plugins.engine.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class BacktestRunner:
    def __init__(
        self,
        engine_instance: dict,
        candles: list[dict],
        symbol: str = "UNKNOWN",
        timeframe: str = "1d",
    ):
        """
        Args:
            engine_instance: engine插件的create_isolated_instance() 返回值
            candles: 按时间排序的K线列表，每个 dict 至少包含 open/high/low/close/volume
        """
        self.range_engine: RangeEngine = engine_instance["range_engine"]
        self.event_engine: EventEngine = engine_instance["event_engine"]
        self.rule_engine: RuleEngine = engine_instance["rule_engine"]
        self.candles = candles
        self.symbol = symbol
        self.timeframe = timeframe

    def run(self) -> dict:
        """逐根K线运行引擎，收集所有产出。

        完全复刻 engine/plugin.py._on_candle() 的处理流程。

        Returns:
            dict:
                events: list[dict]       — 所有检测到的事件
                transitions: list[dict]  — 所有阶段转换
                timeline: list[dict]     — 每根K线的状态快照
                total_bars: int
        """
        # 创建全新的 EngineState
        engine_state = EngineState(symbol=self.symbol, timeframe=self.timeframe)

        events: list[dict] = []
        transitions: list[dict] = []
        timeline: list[dict] = []

        for bar_index, candle in enumerate(self.candles):
            engine_state.bar_count = bar_index

            # ── 完全复刻 engine/plugin.py._on_candle ──

            # 1. 区间引擎
            range_ctx = self.range_engine.process_bar(candle, bar_index, engine_state)

            # 2. 事件引擎（内部调用规则引擎）
            event_ctx = self.event_engine.process_bar(
                candle, range_ctx, bar_index, engine_state, self.rule_engine
            )

            # 3. 更新引擎状态
            engine_state.current_phase = event_ctx.current_phase
            engine_state.direction = event_ctx.current_direction
            engine_state.structure_type = event_ctx.structure_type
            engine_state.active_range = range_ctx.active_range
            engine_state.candidate_extreme = self.range_engine.candidate_extreme

            # 4. 处理事件
            if event_ctx.new_events:
                for ev in event_ctx.new_events:
                    engine_state.recent_events.append(ev)
                    if len(engine_state.recent_events) > 20:
                        engine_state.recent_events.pop(0)

                    # AR锚点
                    if ev.event_type == EventType.AR:
                        engine_state.ar_anchor = AnchorPoint(
                            bar_index=ev.sequence_end_bar,
                            extreme_price=ev.price_extreme,
                            body_price=ev.price_body,
                            volume=0,
                        )

                    events.append(
                        {
                            "event_type": ev.event_type.value,
                            "event_result": ev.event_result.value,
                            "bar_index": ev.sequence_end_bar,
                            "sequence_start_bar": ev.sequence_start_bar,
                            "sequence_length": ev.sequence_length,
                            "position_in_range": ev.position_in_range,
                            "volume_ratio": ev.volume_ratio,
                            "variant_tag": ev.variant_tag,
                        }
                    )

            # 阶段转换
            if event_ctx.phase_transition:
                pt = event_ctx.phase_transition
                transitions.append(
                    {
                        "from_phase": pt.from_phase.value,
                        "to_phase": pt.to_phase.value,
                        "trigger_rule": pt.trigger_rule,
                        "bar_index": pt.bar_index,
                    }
                )

            # 时间线快照
            timeline.append(
                {
                    "bar_index": bar_index,
                    "phase": engine_state.current_phase.value,
                    "direction": (
                        engine_state.direction.value if engine_state.direction else None
                    ),
                    "has_active_range": engine_state.active_range is not None,
                    "events_this_bar": len(event_ctx.new_events)
                    if event_ctx.new_events
                    else 0,
                }
            )

        logger.info(
            "回测完成: %d bars, %d events, %d transitions",
            len(self.candles),
            len(events),
            len(transitions),
        )

        return {
            "events": events,
            "transitions": transitions,
            "timeline": timeline,
            "total_bars": len(self.candles),
        }
