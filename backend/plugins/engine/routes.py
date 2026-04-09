"""引擎API路由"""

from __future__ import annotations

from fastapi import APIRouter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin import EnginePlugin


def create_router(engine: EnginePlugin) -> APIRouter:
    router = APIRouter()

    @router.get("/state/{symbol}/all")
    async def get_all_states(symbol: str):
        states = engine.get_all_states(symbol)
        return {tf: _serialize_state(s) for tf, s in states.items()}

    @router.get("/state/{symbol}/{tf}")
    async def get_state(symbol: str, tf: str):
        state = engine.get_state(symbol, tf)
        return _serialize_state(state)

    @router.get("/ranges/{symbol}")
    async def get_ranges(symbol: str):
        # TODO: 从记忆层读取
        return []

    @router.get("/events/{symbol}")
    async def get_events(symbol: str):
        states = engine.get_all_states(symbol)
        all_events = []
        for s in states.values():
            all_events.extend(s.recent_events)
        return [_serialize_event(e) for e in all_events]

    return router


def _serialize_state(state) -> dict:
    return {
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "current_phase": state.current_phase.value,
        "structure_type": state.structure_type.value,
        "direction": state.direction.value,
        "confidence": state.confidence,
        "active_range": None,  # TODO: 序列化Range
        "bar_count": state.bar_count,
        "params_version": state.params_version,
        "recent_events": [_serialize_event(e) for e in state.recent_events[-10:]],
    }


def _serialize_event(event) -> dict:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "event_result": event.event_result.value,
        "start_bar": event.sequence_start_bar,
        "end_bar": event.sequence_end_bar,
        "price_extreme": event.price_extreme,
        "confidence": event.confidence,
    }
