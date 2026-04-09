"""引擎插件入口"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from backend.core.types import BackendPlugin, PluginContext
from .models import (
    EngineState,
    Direction,
    Phase,
    StructureType,
    CandidateExtreme,
    AnchorPoint,
    RangeContext,
    EventContext,
    EventType,
)
from .params import EngineParams, load_params
from .range_engine import RangeEngine
from .event_engine import EventEngine
from .rule_engine import RuleEngine
from .routes import create_router

logger = logging.getLogger(__name__)


class EnginePlugin(BackendPlugin):
    id = "engine"
    name = "Wyckoff Engine"
    version = "0.1.0"
    dependencies = ("datasource",)

    def __init__(self):
        self.ctx: PluginContext | None = None
        self.params = EngineParams()
        self.range_engine = RangeEngine(self.params.range_engine)
        self.event_engine = EventEngine(self.params.event_engine)
        self.rule_engine = RuleEngine(self.params.rule_engine)
        self.state: dict[str, dict[str, EngineState]] = {}
        self.running = False

    async def on_init(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        # 加载进化参数
        params_path = ctx.storage.base_path / "evolution" / "params_latest.json"
        self.params = load_params(params_path)
        # 用加载的参数重新初始化三引擎
        self.range_engine = RangeEngine(self.params.range_engine)
        self.event_engine = EventEngine(self.params.event_engine)
        self.rule_engine = RuleEngine(self.params.rule_engine)
        logger.info("引擎插件初始化完成，参数版本: %s", self.params.version)

    async def on_start(self) -> None:
        self.running = True
        logger.info("引擎插件启动")

    async def on_stop(self) -> None:
        self.running = False
        logger.info("引擎插件停止")

    def get_router(self) -> APIRouter:
        return create_router(self)

    def get_subscriptions(self) -> dict:
        return {
            "candle.new": self._on_candle,
            "evolution.params_updated": self._on_params_updated,
            "annotation.created": self._on_annotation,
        }

    async def _on_candle(self, data: dict) -> None:
        """每根K线到达时触发"""
        if not self.running:
            return
        symbol = data.get("symbol", "")
        tf = data.get("timeframe", "")
        candle = data.get("candle", {})
        bar_index = data.get("bar_index", 0)

        # 确保state存在
        if symbol not in self.state:
            self.state[symbol] = {}
        if tf not in self.state[symbol]:
            self.state[symbol][tf] = EngineState(symbol=symbol, timeframe=tf)

        engine_state = self.state[symbol][tf]
        engine_state.bar_count = bar_index

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

        # 4. 发布事件 + AR锚点存储
        if event_ctx.new_events:
            for event in event_ctx.new_events:
                engine_state.recent_events.append(event)
                # 保留最近20个事件
                if len(engine_state.recent_events) > 20:
                    engine_state.recent_events.pop(0)

                # AR事件 → 存储锚点（ED-11）
                if event.event_type == EventType.AR:
                    engine_state.ar_anchor = AnchorPoint(
                        bar_index=event.sequence_end_bar,
                        extreme_price=event.price_extreme,
                        body_price=event.price_body,
                        volume=0,  # bounce.py当前不传volume，后续进化补充
                    )

                if self.ctx:
                    await self.ctx.event_bus.publish(
                        "engine.event_detected",
                        {"symbol": symbol, "timeframe": tf, "event": event},
                    )

        if event_ctx.phase_transition and self.ctx:
            await self.ctx.event_bus.publish(
                "engine.phase_changed",
                {
                    "symbol": symbol,
                    "timeframe": tf,
                    "phase": event_ctx.current_phase.value,
                    "direction": event_ctx.current_direction.value,
                },
            )

    async def _on_params_updated(self, data: dict) -> None:
        """进化参数更新时重新加载"""
        if not self.ctx:
            return
        params_path = self.ctx.storage.base_path / "evolution" / "params_latest.json"
        self.params = load_params(params_path)
        self.range_engine = RangeEngine(self.params.range_engine)
        self.event_engine = EventEngine(self.params.event_engine)
        self.rule_engine = RuleEngine(self.params.rule_engine)
        logger.info("引擎参数已更新: %s", self.params.version)

    async def _on_annotation(self, data: dict) -> None:
        """
        莱恩标注事件时，引擎接收并处理（ED-5）。

        两种标注方式创建区间：
        1. 莱恩分别标注SC/AR/ST → 三点就位时自动创建区间
        2. 莱恩直接画平行通道 → 从通道坐标直接创建区间

        annotation.created 事件的期望数据格式：
        {
            "drawing_id": "uuid",
            "drawing_type": "callout" | "parallel_channel" | ...,
            "symbol": "ETHUSDT",
            "timeframe": "1D",
            "label": "SC",
            "points": [
                {"time": 1234567890, "bar_index": 100, "price": 1500.0},
                ...
            ],
            "metadata": {}
        }
        """
        symbol = data.get("symbol", "")
        tf = data.get("timeframe", "")
        drawing_type = data.get("drawing_type", "")

        # 确保state存在
        if symbol not in self.state:
            self.state[symbol] = {}
        if tf not in self.state[symbol]:
            self.state[symbol][tf] = EngineState(symbol=symbol, timeframe=tf)
        engine_state = self.state[symbol][tf]

        if drawing_type == "parallel_channel":
            # 莱恩画了平行通道 = 直接创建区间
            points = data.get("points", [])
            if len(points) >= 4:
                pass  # TODO: 实现通道→区间的转换，等annotation插件数据结构确定

        elif drawing_type == "callout":
            label = data.get("label", "").upper().strip()
            points = data.get("points", [])
            if not points:
                return
            point = points[0]
            bar_idx = point.get("bar_index", 0)
            price = point.get("price", 0)

            if label in ("SC", "BC"):
                # 莱恩标注了SC/BC → 存为候选
                is_sc = label == "SC"
                self.range_engine.candidate_extreme = CandidateExtreme(
                    candidate_type=label,
                    bar_index=bar_idx,
                    extreme_price=price,
                    body_price=price,
                    volume=0,
                    volume_ratio=1.0,
                )
                engine_state.candidate_extreme = self.range_engine.candidate_extreme
                engine_state.direction = Direction.SHORT if is_sc else Direction.LONG
                engine_state.current_phase = Phase.A
                logger.info("标注→候选: %s at bar=%d price=%.2f", label, bar_idx, price)

            elif label == "AR":
                # 莱恩标注了AR → 存为AR锚点
                engine_state.ar_anchor = AnchorPoint(
                    bar_index=bar_idx,
                    extreme_price=price,
                    body_price=price,
                    volume=0,
                )
                logger.info("标注→AR锚点: bar=%d price=%.2f", bar_idx, price)

            elif label == "ST":
                # 莱恩标注了ST → 如果有候选+AR → 创建区间
                candidate = self.range_engine.candidate_extreme
                ar = engine_state.ar_anchor
                if candidate is None or ar is None:
                    logger.warning(
                        "ST标注忽略：缺少SC候选或AR锚点 (candidate=%s, ar=%s)",
                        candidate is not None,
                        ar is not None,
                    )
                    return
                st_anchor = AnchorPoint(
                    bar_index=bar_idx,
                    extreme_price=price,
                    body_price=price,
                    volume=0,
                )
                new_range = self.range_engine.create_range(
                    candidate, ar, st_anchor, engine_state.direction
                )
                new_range.timeframe = tf
                engine_state.active_range = new_range
                engine_state.current_phase = Phase.B
                # 清理
                self.range_engine.candidate_extreme = None
                engine_state.ar_anchor = None
                engine_state.candidate_extreme = None
                logger.info(
                    "标注→区间创建: range_id=%s, phase=B",
                    new_range.range_id[:8],
                )
                if self.ctx:
                    await self.ctx.event_bus.publish(
                        "engine.range_created",
                        {"symbol": symbol, "timeframe": tf, "range": new_range},
                    )

    def get_state(self, symbol: str, tf: str) -> EngineState:
        """获取指定标的和周期的引擎状态"""
        return self.state.get(symbol, {}).get(
            tf, EngineState(symbol=symbol, timeframe=tf)
        )

    def get_all_states(self, symbol: str) -> dict[str, EngineState]:
        """获取指定标的所有周期的状态"""
        return self.state.get(symbol, {})

    def create_isolated_instance(self, params: EngineParams | None = None) -> dict:
        """创建隔离的引擎实例，用于回测。不注册到 self.state。

        Args:
            params: 可选。如果不传，使用当前加载的参数。

        Returns:
            {
                "range_engine": RangeEngine,
                "event_engine": EventEngine,
                "rule_engine": RuleEngine,
                "params": EngineParams,
            }
        """
        p = params or self.params
        return {
            "range_engine": RangeEngine(p.range_engine),
            "event_engine": EventEngine(p.event_engine),
            "rule_engine": RuleEngine(p.rule_engine),
            "params": p,
        }
