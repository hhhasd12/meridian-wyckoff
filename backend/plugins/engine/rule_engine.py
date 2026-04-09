"""规则引擎 — 阶段转换路径图 + 方向管理"""

from __future__ import annotations

import logging

from .models import (
    Event,
    EventType,
    EventResult,
    Phase,
    Direction,
    StructureType,
    PhaseTransition,
    RangeContext,
    EngineState,
)
from .params import RuleEngineParams

logger = logging.getLogger(__name__)


class RuleEngine:
    def __init__(self, params: RuleEngineParams):
        self.params = params
        self.rule_log: list[dict] = []

    def evaluate(
        self,
        event: Event,
        range_ctx: RangeContext,
        engine_state: EngineState,
    ) -> PhaseTransition | None:
        """评估事件是否触发阶段转换"""
        phase = engine_state.current_phase
        direction = engine_state.direction
        etype = event.event_type

        transition = None

        # ─── SC/BC → 设置初始方向 ───
        if etype == EventType.SC:
            new_dir = Direction.SHORT
            transition = PhaseTransition(
                from_phase=phase,
                to_phase=Phase.A,
                trigger_event_id=event.event_id,
                trigger_rule="SC_sets_direction",
                bar_index=event.sequence_end_bar,
                direction_before=direction,
                direction_after=new_dir,
            )
            self._log("SC_sets_direction", event, phase, Phase.A)

        elif etype == EventType.BC:
            new_dir = Direction.LONG
            transition = PhaseTransition(
                from_phase=phase,
                to_phase=Phase.A,
                trigger_event_id=event.event_id,
                trigger_rule="BC_sets_direction",
                bar_index=event.sequence_end_bar,
                direction_before=direction,
                direction_after=new_dir,
            )
            self._log("BC_sets_direction", event, phase, Phase.A)

        # ─── ST确认 → A到B ───
        elif etype == EventType.ST and phase == Phase.A:
            if event.event_result == EventResult.SUCCESS:
                transition = PhaseTransition(
                    from_phase=Phase.A,
                    to_phase=Phase.B,
                    trigger_event_id=event.event_id,
                    trigger_rule="ST_confirms_range",
                    bar_index=event.sequence_end_bar,
                    direction_before=direction,
                    direction_after=direction,
                )
                self._log("ST_confirms_range", event, Phase.A, Phase.B)

        # ─── Spring/SO成功 → C确认 → 进入D ───
        elif etype in (EventType.SPRING, EventType.SO) and phase in (Phase.B, Phase.C):
            if event.event_result == EventResult.SUCCESS:
                new_dir = self._apply_direction_switch(engine_state, "spring")
                transition = PhaseTransition(
                    from_phase=phase,
                    to_phase=Phase.D,
                    trigger_event_id=event.event_id,
                    trigger_rule="Spring_confirms_direction",
                    bar_index=event.sequence_end_bar,
                    direction_before=direction,
                    direction_after=new_dir,
                )
                engine_state.direction_confirmed = True
                self._log("Spring_confirms", event, phase, Phase.D)

        # ─── UTAD成功 → C确认 → 进入D ───
        elif etype == EventType.UTAD and phase in (Phase.B, Phase.C):
            if event.event_result == EventResult.SUCCESS:
                new_dir = self._apply_direction_switch(engine_state, "utad")
                transition = PhaseTransition(
                    from_phase=phase,
                    to_phase=Phase.D,
                    trigger_event_id=event.event_id,
                    trigger_rule="UTAD_confirms_direction",
                    bar_index=event.sequence_end_bar,
                    direction_before=direction,
                    direction_after=new_dir,
                )
                engine_state.direction_confirmed = True
                self._log("UTAD_confirms", event, phase, Phase.D)

        # ─── JOC/跌破冰线/BREAKOUT_CONFIRMED → D到E ───
        elif (
            etype in (EventType.JOC, EventType.BREAK_ICE, EventType.BREAKOUT_CONFIRMED)
            and phase == Phase.D
        ):
            transition = PhaseTransition(
                from_phase=Phase.D,
                to_phase=Phase.E,
                trigger_event_id=event.event_id,
                trigger_rule="JOC_starts_trend",
                bar_index=event.sequence_end_bar,
                direction_before=direction,
                direction_after=direction,
            )
            self._log("JOC_starts_trend", event, Phase.D, Phase.E)

        # ─── 假突破回归 → E退回B ───
        elif etype == EventType.FALSE_BREAKOUT_RETURN and phase == Phase.E:
            transition = PhaseTransition(
                from_phase=Phase.E,
                to_phase=Phase.B,
                trigger_event_id=event.event_id,
                trigger_rule="false_breakout_recovery",
                bar_index=event.sequence_end_bar,
                direction_before=direction,
                direction_after=direction,
                notes="JOC标记FAILED，方向不变",
            )
            self._log("false_breakout", event, Phase.E, Phase.B)

        # ─── 供需信号 → 命名为具体事件类型 ───
        elif etype == EventType.SUPPLY_DEMAND_SIGNAL:
            named_type = self.classify_supply_demand_signal(event, phase, range_ctx)
            # 将命名结果记录到 variant_features
            if event.variant_features is not None:
                event.variant_features["named_event_type"] = named_type
            self._log(
                f"supply_demand→{named_type}",
                event,
                phase,
                phase,
            )

        return transition

    def _apply_direction_switch(self, state: EngineState, event_kind: str) -> Direction:
        """阶段C方向开关 — V3§2.3"""
        entry = (
            state.active_range.entry_trend if state.active_range else state.direction
        )

        if event_kind == "spring":
            if entry == Direction.SHORT:
                state.structure_type = StructureType.ACCUMULATION
                return Direction.LONG
            else:
                state.structure_type = StructureType.RE_ACCUMULATION
                return Direction.LONG

        elif event_kind == "utad":
            if entry == Direction.LONG:
                state.structure_type = StructureType.DISTRIBUTION
                return Direction.SHORT
            else:
                state.structure_type = StructureType.RE_DISTRIBUTION
                return Direction.SHORT

        return state.direction

    def _log(self, rule: str, event: Event, from_p: Phase, to_p: Phase) -> None:
        self.rule_log.append(
            {
                "rule": rule,
                "event_type": event.event_type.value,
                "from_phase": from_p.value,
                "to_phase": to_p.value,
                "bar_index": event.sequence_end_bar,
            }
        )

    # ═══ 供需信号命名 ═══

    def classify_supply_demand_signal(
        self,
        event: Event,
        current_phase: Phase,
        range_ctx: RangeContext,
    ) -> str:
        """
        将通用供需信号命名为具体事件类型。

        命名规则（设计文档 §9）：
        - E阶段 → MSOS/MSOW（趋势确认）
        - D阶段 + 靠近下边界 → LPS（支撑确认）
        - D阶段 + 靠近上边界 → LPSY（阻力确认）
        - D阶段 + 区间内 → SOS/SOW
        - B/C阶段 → mSOS/mSOW（渐进暗示）

        W4修复：boundary_proximity 从 variant_features 读取（检测器写入的进化参数）。
        W5修复：LPS 只在靠近下边界（支撑），LPSY 只在靠近上边界（阻力）。

        Args:
            event: SUPPLY_DEMAND_SIGNAL 事件
            current_phase: 当前阶段
            range_ctx: 区间上下文

        Returns:
            命名后的事件类型字符串
        """
        direction = event.variant_tag or ""
        position = event.position_in_range

        # W4修复：从 variant_features 读取检测器传入的 boundary_proximity
        features = event.variant_features or {}
        boundary_proximity = features.get("boundary_proximity", 0.15)

        is_bullish = direction == "BULLISH"
        is_near_lower = position < boundary_proximity
        is_near_upper = position > (1 - boundary_proximity)
        is_near_boundary = is_near_lower or is_near_upper

        if current_phase == Phase.E:
            return "MSOS" if is_bullish else "MSOW"

        if current_phase == Phase.D:
            if is_near_boundary:
                # W5修复：LPS 在靠近下边界（支撑），LPSY 在靠近上边界（阻力）
                # 不区分方向，只区分位置语义
                if is_near_lower:
                    return "LPS"  # 靠近支撑位
                else:
                    return "LPSY"  # 靠近阻力位
            else:
                return "SOS" if is_bullish else "SOW"

        # B/C 阶段
        return "mSOS" if is_bullish else "mSOW"
