"""回测评分 — 对比引擎输出与莱恩标注"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class BacktestScorer:
    def __init__(self, match_window: int = 3):
        """
        Args:
            match_window: 事件匹配的K线容差（±N根K线内算匹配）
        """
        self.match_window = match_window

    def score(self, result: dict, annotations: list[dict]) -> dict:
        """对比回测结果和标注。

        Args:
            result: BacktestRunner.run() 的返回值
            annotations: 标注事件列表，每个 dict 至少包含:
                - event_type: str (如 "sc", "ar", "st", "spring" 等)
                - bar_index: int (标注的K线位置)
                可选:
                - phase: str (标注时的阶段)

        Returns:
            dict: 评分结果
        """
        if not annotations:
            return {
                "detection_rate": 0,
                "false_positive_rate": 0,
                "phase_accuracy": 0,
                "avg_time_offset": 0,
                "matched_count": 0,
                "missed_count": 0,
                "false_positive_count": len(result.get("events", [])),
                "total_annotations": 0,
                "total_engine_events": len(result.get("events", [])),
                "matched": [],
                "missed": [],
                "false_positives": result.get("events", []),
                "note": "无标注数据，仅输出引擎原始结果",
            }

        engine_events = result.get("events", [])

        # 事件匹配
        matched, missed, false_positives = self._match_events(
            engine_events, annotations
        )

        # 各维度评分
        detection_rate = len(matched) / len(annotations) if annotations else 0
        false_positive_rate = (
            len(false_positives) / len(engine_events) if engine_events else 0
        )
        avg_offset = self._calc_avg_offset(matched)
        phase_accuracy = self._calc_phase_accuracy(
            result.get("timeline", []), annotations
        )

        return {
            "detection_rate": round(detection_rate, 4),
            "false_positive_rate": round(false_positive_rate, 4),
            "phase_accuracy": round(phase_accuracy, 4),
            "avg_time_offset": round(avg_offset, 2),
            "matched_count": len(matched),
            "missed_count": len(missed),
            "false_positive_count": len(false_positives),
            "total_annotations": len(annotations),
            "total_engine_events": len(engine_events),
            "matched": matched,
            "missed": missed,
            "false_positives": false_positives,
        }

    def _match_events(
        self,
        engine_events: list[dict],
        annotations: list[dict],
    ) -> tuple[list, list, list]:
        """匹配引擎事件和标注事件。

        匹配规则：
        - 事件类型相同
        - 时间窗口内（|ann.bar_index - eng.bar_index| <= match_window）
        - 一个标注最多匹配一个引擎事件（最近优先）
        - 一个引擎事件最多匹配一个标注
        """
        matched = []
        used_engine = set()
        used_annotation = set()

        for ai, ann in enumerate(annotations):
            best_ei = None
            best_offset = self.match_window + 1

            for ei, eng in enumerate(engine_events):
                if ei in used_engine:
                    continue
                if eng.get("event_type", "") != ann.get("event_type", ""):
                    continue
                offset = abs(eng.get("bar_index", 0) - ann.get("bar_index", 0))
                if offset <= self.match_window and offset < best_offset:
                    best_ei = ei
                    best_offset = offset

            if best_ei is not None:
                matched.append(
                    {
                        "annotation": ann,
                        "engine_event": engine_events[best_ei],
                        "offset": best_offset,
                    }
                )
                used_engine.add(best_ei)
                used_annotation.add(ai)

        missed = [
            ann for ai, ann in enumerate(annotations) if ai not in used_annotation
        ]
        false_positives = [
            eng for ei, eng in enumerate(engine_events) if ei not in used_engine
        ]

        return matched, missed, false_positives

    def _calc_avg_offset(self, matched: list) -> float:
        if not matched:
            return 0.0
        return sum(m["offset"] for m in matched) / len(matched)

    def _calc_phase_accuracy(
        self, timeline: list[dict], annotations: list[dict]
    ) -> float:
        """阶段准确率：标注中有phase字段的，对比引擎在该时间点的阶段。"""
        phase_anns = [a for a in annotations if "phase" in a]
        if not phase_anns:
            return 0.0

        correct = 0
        for ann in phase_anns:
            bar = ann.get("bar_index", 0)
            if 0 <= bar < len(timeline):
                if timeline[bar].get("phase", "") == ann.get("phase", ""):
                    correct += 1

        return correct / len(phase_anns)
