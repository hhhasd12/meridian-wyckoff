"""标注对比引擎 — 比较用户标注和状态机检测结果

核心匹配逻辑：
- 系统确认事件的 bar 序号落在标注 [start_bar_index, end_bar_index] ± tolerance 内 = 位置匹配
- 位置匹配且事件类型一致 = matched
- 位置匹配但事件类型不同 = type_mismatch
- 标注了但无检测 = missed
- 检测到但无标注 = false_positive
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MatchResult:
    """单条匹配结果"""

    type: str  # 'matched' | 'missed' | 'false_positive' | 'type_mismatch'
    annotation: Optional[Dict[str, Any]] = (
        None  # 用户标注（matched/missed/type_mismatch）
    )
    detection: Optional[Dict[str, Any]] = (
        None  # 系统检测（matched/false_positive/type_mismatch）
    )
    details: str = ""  # 匹配详情


@dataclass
class MatchReport:
    """完整匹配报告"""

    total_annotations: int = 0
    total_detections: int = 0
    matched: int = 0
    missed: int = 0  # 标注了但系统没检测到
    false_positives: int = 0  # 系统检测到但没标注
    type_mismatches: int = 0  # 位置匹配但事件类型不同
    match_score: float = 0.0  # 总体匹配度 F1 [0, 1]
    results: List[MatchResult] = field(default_factory=list)


class AnnotationMatcher:
    """标注对比引擎

    将用户标注（WyckoffAnnotation as dict）与状态机转换历史
    （_transition_history）进行匹配分析，输出匹配报告。
    """

    def __init__(self, tolerance_bars: int = 3) -> None:
        """
        Args:
            tolerance_bars: 时间窗口容差（标注和检测的bar序号差异允许范围）
        """
        self.tolerance_bars = tolerance_bars

    def match(
        self,
        annotations: List[Dict[str, Any]],
        transition_history: List[Dict[str, Any]],
    ) -> MatchReport:
        """执行匹配分析

        Args:
            annotations: 用户标注列表 (WyckoffAnnotation as dict)
            transition_history: 状态机转换历史 (from _transition_history)
                每条记录: {"from": str, "to": str, "bar": int, "confidence": float}

        Returns:
            MatchReport 匹配报告
        """
        # 只处理 event 类型的标注
        event_annotations = [a for a in annotations if a.get("type") == "event"]

        report = MatchReport(
            total_annotations=len(event_annotations),
            total_detections=len(transition_history),
        )

        # 标记哪些检测已被匹配
        matched_detections: set[int] = set()

        for ann in event_annotations:
            ann_start = ann.get("start_bar_index", 0)
            ann_end = ann.get("end_bar_index", ann_start)
            ann_event = ann.get("event_type", "")

            best_match: Optional[tuple[int, Dict[str, Any]]] = None
            best_distance = float("inf")

            for i, det in enumerate(transition_history):
                if i in matched_detections:
                    continue
                det_bar = det.get("bar", 0)

                # 检测的bar是否落在标注范围 ± tolerance 内
                if (
                    ann_start - self.tolerance_bars
                    <= det_bar
                    <= ann_end + self.tolerance_bars
                ):
                    distance = abs(det_bar - (ann_start + ann_end) / 2)
                    if distance < best_distance:
                        best_distance = distance
                        best_match = (i, det)

            if best_match is not None:
                idx, det = best_match
                matched_detections.add(idx)
                det_event = det.get("to", "")

                if det_event.upper() == ann_event.upper():
                    # 完全匹配
                    report.matched += 1
                    report.results.append(
                        MatchResult(
                            type="matched",
                            annotation=ann,
                            detection=det,
                            details=f"事件 {ann_event} 在 bar {det.get('bar')} 匹配",
                        )
                    )
                else:
                    # 位置匹配但类型不同
                    report.type_mismatches += 1
                    report.results.append(
                        MatchResult(
                            type="type_mismatch",
                            annotation=ann,
                            detection=det,
                            details=(
                                f"标注 {ann_event} vs 检测 {det_event}"
                                f" 在 bar {det.get('bar')}"
                            ),
                        )
                    )
            else:
                # 标注了但系统没检测到
                report.missed += 1
                report.results.append(
                    MatchResult(
                        type="missed",
                        annotation=ann,
                        details=f"事件 {ann_event} 在 bar {ann_start}-{ann_end} 未被检测",
                    )
                )

        # 未被匹配的检测 = false positives
        for i, det in enumerate(transition_history):
            if i not in matched_detections:
                report.false_positives += 1
                report.results.append(
                    MatchResult(
                        type="false_positive",
                        detection=det,
                        details=(
                            f"检测 {det.get('to', '?')}"
                            f" 在 bar {det.get('bar')} 无对应标注"
                        ),
                    )
                )

        # 计算匹配度得分 (F1-like: 平衡精确率和召回率)
        if report.total_annotations > 0:
            precision = report.matched / max(
                1, report.matched + report.false_positives + report.type_mismatches
            )
            recall = report.matched / max(1, report.total_annotations)
            if precision + recall > 0:
                report.match_score = 2 * precision * recall / (precision + recall)

        return report
