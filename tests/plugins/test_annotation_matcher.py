"""AnnotationMatcher 对比引擎测试

覆盖场景:
- 完全匹配 (matched)
- 标注漏检 (missed)
- 误检 (false_positive)
- 类型不匹配 (type_mismatch)
- 容差窗口 (tolerance)
- F1 分数计算
- 空输入处理
- plugin 集成方法
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.plugins.annotation.matcher import AnnotationMatcher, MatchReport, MatchResult


def _ann(
    event_type: str,
    start: int,
    end: int,
    ann_type: str = "event",
) -> Dict[str, Any]:
    """辅助函数：构造标注字典"""
    return {
        "id": f"ann-{event_type}-{start}",
        "type": ann_type,
        "symbol": "ETH/USDT",
        "timeframe": "H4",
        "event_type": event_type,
        "start_bar_index": start,
        "end_bar_index": end,
    }


def _det(to_event: str, bar: int, confidence: float = 0.8) -> Dict[str, Any]:
    """辅助函数：构造检测字典（模拟 _transition_history 条目）"""
    return {
        "from": "IDLE",
        "to": to_event,
        "bar": bar,
        "confidence": confidence,
    }


class TestAnnotationMatcher:
    """AnnotationMatcher 核心测试"""

    def setup_method(self) -> None:
        self.matcher = AnnotationMatcher(tolerance_bars=3)

    def test_perfect_match(self) -> None:
        """标注和检测完全匹配"""
        annotations = [
            _ann("SC", 10, 12),
            _ann("AR", 20, 22),
        ]
        detections = [
            _det("SC", 11),
            _det("AR", 21),
        ]
        report = self.matcher.match(annotations, detections)

        assert report.total_annotations == 2
        assert report.total_detections == 2
        assert report.matched == 2
        assert report.missed == 0
        assert report.false_positives == 0
        assert report.type_mismatches == 0
        assert report.match_score == pytest.approx(1.0)
        assert len(report.results) == 2
        assert all(r.type == "matched" for r in report.results)

    def test_missed_annotation(self) -> None:
        """标注了但系统没检测到"""
        annotations = [
            _ann("SC", 10, 12),
            _ann("SPRING", 50, 55),
        ]
        detections = [
            _det("SC", 11),
        ]
        report = self.matcher.match(annotations, detections)

        assert report.matched == 1
        assert report.missed == 1
        assert report.false_positives == 0
        missed = [r for r in report.results if r.type == "missed"]
        assert len(missed) == 1
        assert missed[0].annotation is not None
        assert missed[0].annotation["event_type"] == "SPRING"

    def test_false_positive(self) -> None:
        """系统检测到但没标注"""
        annotations = [
            _ann("SC", 10, 12),
        ]
        detections = [
            _det("SC", 11),
            _det("AR", 30),
            _det("ST", 45),
        ]
        report = self.matcher.match(annotations, detections)

        assert report.matched == 1
        assert report.false_positives == 2
        fps = [r for r in report.results if r.type == "false_positive"]
        assert len(fps) == 2
        fp_events = {fp.detection["to"] for fp in fps}
        assert fp_events == {"AR", "ST"}

    def test_type_mismatch(self) -> None:
        """位置匹配但事件类型不同"""
        annotations = [
            _ann("SC", 10, 12),
        ]
        detections = [
            _det("PS", 11),  # 位置在范围内但类型是 PS 不是 SC
        ]
        report = self.matcher.match(annotations, detections)

        assert report.matched == 0
        assert report.type_mismatches == 1
        assert report.missed == 0
        assert report.false_positives == 0
        mismatch = report.results[0]
        assert mismatch.type == "type_mismatch"
        assert "SC" in mismatch.details
        assert "PS" in mismatch.details

    def test_tolerance_window(self) -> None:
        """验证容差范围：tolerance_bars=3 时 bar ±3 应匹配"""
        annotations = [_ann("SC", 10, 10)]

        # 刚好在容差边界内 (10 - 3 = 7)
        det_inside = [_det("SC", 7)]
        report = self.matcher.match(annotations, det_inside)
        assert report.matched == 1

        # 超出容差 (10 - 4 = 6)
        det_outside = [_det("SC", 6)]
        report2 = self.matcher.match(annotations, det_outside)
        assert report2.matched == 0
        assert report2.missed == 1
        assert report2.false_positives == 1

        # 右侧容差边界 (10 + 3 = 13)
        det_right = [_det("SC", 13)]
        report3 = self.matcher.match(annotations, det_right)
        assert report3.matched == 1

        # 右侧超出 (10 + 4 = 14)
        det_right_out = [_det("SC", 14)]
        report4 = self.matcher.match(annotations, det_right_out)
        assert report4.matched == 0

    def test_match_score_calculation(self) -> None:
        """F1 分数计算验证"""
        # 完美匹配 → F1 = 1.0
        report_perfect = self.matcher.match(
            [_ann("SC", 10, 12)],
            [_det("SC", 11)],
        )
        assert report_perfect.match_score == pytest.approx(1.0)

        # 1 matched + 1 false_positive → precision=0.5, recall=1.0 → F1=2/3
        report_fp = self.matcher.match(
            [_ann("SC", 10, 12)],
            [_det("SC", 11), _det("AR", 50)],
        )
        assert report_fp.match_score == pytest.approx(2.0 / 3.0, abs=0.01)

        # 1 matched + 1 missed → precision=1.0, recall=0.5 → F1=2/3
        report_miss = self.matcher.match(
            [_ann("SC", 10, 12), _ann("SPRING", 80, 85)],
            [_det("SC", 11)],
        )
        assert report_miss.match_score == pytest.approx(2.0 / 3.0, abs=0.01)

        # 0 matched → F1 = 0.0
        report_zero = self.matcher.match(
            [_ann("SC", 10, 12)],
            [_det("AR", 50)],
        )
        assert report_zero.match_score == 0.0

    def test_empty_inputs(self) -> None:
        """空输入处理"""
        # 两个都空
        report = self.matcher.match([], [])
        assert report.total_annotations == 0
        assert report.total_detections == 0
        assert report.matched == 0
        assert report.match_score == 0.0
        assert len(report.results) == 0

        # 只有标注无检测
        report2 = self.matcher.match([_ann("SC", 10, 12)], [])
        assert report2.missed == 1
        assert report2.false_positives == 0

        # 只有检测无标注
        report3 = self.matcher.match([], [_det("SC", 11)])
        assert report3.missed == 0
        assert report3.false_positives == 1

    def test_non_event_annotations_filtered(self) -> None:
        """非 event 类型标注应被过滤"""
        annotations = [
            _ann("SC", 10, 12, ann_type="event"),
            _ann("SC_LOW", 10, 10, ann_type="level"),  # level 类型，应被忽略
        ]
        detections = [_det("SC", 11)]
        report = self.matcher.match(annotations, detections)

        assert report.total_annotations == 1  # 只有 event 类型
        assert report.matched == 1

    def test_case_insensitive_match(self) -> None:
        """事件类型匹配大小写不敏感"""
        annotations = [_ann("sc", 10, 12)]  # 小写
        detections = [_det("SC", 11)]  # 大写
        report = self.matcher.match(annotations, detections)
        assert report.matched == 1


class TestCompareWithDetections:
    """plugin.compare_with_detections 集成测试"""

    def test_compare_with_detections(self, tmp_path: Path) -> None:
        """集成方法返回正确格式"""
        from src.plugins.annotation.plugin import AnnotationPlugin

        plugin = AnnotationPlugin()
        plugin._config = {"data_dir": str(tmp_path)}
        plugin.on_load()

        # 创建标注
        plugin.create_annotation(
            {
                "type": "event",
                "symbol": "ETH/USDT",
                "timeframe": "H4",
                "event_type": "SC",
                "start_bar_index": 10,
                "end_bar_index": 12,
            }
        )

        transition_history = [
            {"from": "IDLE", "to": "SC", "bar": 11, "confidence": 0.8},
            {"from": "SC", "to": "AR", "bar": 25, "confidence": 0.7},
        ]

        result = plugin.compare_with_detections("ETH/USDT", "H4", transition_history)

        assert result["total_annotations"] == 1
        assert result["total_detections"] == 2
        assert result["matched"] == 1
        assert result["false_positives"] == 1
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 2
