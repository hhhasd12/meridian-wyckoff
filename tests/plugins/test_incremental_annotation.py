"""T5.3: 增量标注自动对比测试

验证:
- 标注<5个时不触发自动对比
- 标注≥5个时触发自动对比
- 无缓存时 get_auto_compare_result 返回 None
- 有缓存时返回对比数据
- create_annotation 触发自动对比链路
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.plugins.annotation.plugin import AnnotationPlugin


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """临时标注数据目录"""
    d = tmp_path / "annotations"
    d.mkdir()
    return d


@pytest.fixture
def plugin(tmp_data_dir: Path) -> AnnotationPlugin:
    """已初始化的标注插件"""
    p = AnnotationPlugin(name="annotation")
    p._config = {"data_dir": str(tmp_data_dir)}
    p.on_load()
    # Stub emit_event to avoid needing event bus
    p.emit_event = MagicMock()  # type: ignore[assignment]
    return p


def _make_event_annotation(
    symbol: str = "ETH/USDT",
    timeframe: str = "H4",
    event_type: str = "SC",
    start_bar: int = 10,
    end_bar: int = 12,
) -> Dict[str, Any]:
    """构造一个 event 类型标注数据"""
    return {
        "type": "event",
        "symbol": symbol,
        "timeframe": timeframe,
        "event_type": event_type,
        "start_bar_index": start_bar,
        "end_bar_index": end_bar,
    }


class TestAutoCompareNotTriggered:
    """标注<5个时不触发自动对比"""

    def test_auto_compare_not_triggered_few_annotations(
        self, plugin: AnnotationPlugin
    ) -> None:
        """不足5个 event 标注时 _auto_compare_result 应保持 None"""
        # 创建3个 event 标注
        for i in range(3):
            plugin.create_annotation(
                _make_event_annotation(event_type=f"SC_{i}", start_bar=i * 10)
            )

        assert plugin.get_auto_compare_result() is None

    def test_level_annotations_not_counted(self, plugin: AnnotationPlugin) -> None:
        """level 类型标注不计入事件计数"""
        # 5个 level 标注
        for i in range(5):
            plugin.create_annotation(
                {
                    "type": "level",
                    "symbol": "ETH/USDT",
                    "timeframe": "H4",
                    "price": 2000.0 + i,
                    "level_label": f"LEVEL_{i}",
                }
            )
        # 不应触发
        assert plugin.get_auto_compare_result() is None


class TestAutoCompareTriggered:
    """标注≥5个时触发自动对比"""

    def test_auto_compare_triggered(self, plugin: AnnotationPlugin) -> None:
        """≥5个 event 标注 + 有 transition_history → 自动对比触发"""
        # Mock _get_transition_history 返回检测数据
        fake_history = [
            {"from": "IDLE", "to": "SC", "bar": 10, "confidence": 0.8},
            {"from": "SC", "to": "AR", "bar": 30, "confidence": 0.7},
            {"from": "AR", "to": "ST", "bar": 50, "confidence": 0.6},
        ]
        with patch.object(plugin, "_get_transition_history", return_value=fake_history):
            events = ["SC", "AR", "ST", "SPRING", "LPS"]
            for i, evt in enumerate(events):
                plugin.create_annotation(
                    _make_event_annotation(
                        event_type=evt, start_bar=i * 20, end_bar=i * 20 + 2
                    )
                )

        result = plugin.get_auto_compare_result()
        assert result is not None
        assert result["symbol"] == "ETH/USDT"
        assert result["timeframe"] == "H4"
        assert result["total_annotations"] == 5
        assert "match_score" in result
        assert "timestamp" in result

    def test_auto_compare_no_history(self, plugin: AnnotationPlugin) -> None:
        """≥5个标注但无 transition_history → 不触发对比"""
        with patch.object(plugin, "_get_transition_history", return_value=[]):
            for i in range(6):
                plugin.create_annotation(
                    _make_event_annotation(event_type=f"EVT_{i}", start_bar=i * 10)
                )

        assert plugin.get_auto_compare_result() is None


class TestGetAutoCompareResult:
    """get_auto_compare_result 返回值测试"""

    def test_get_auto_compare_empty(self, plugin: AnnotationPlugin) -> None:
        """无缓存时返回 None"""
        assert plugin.get_auto_compare_result() is None

    def test_get_auto_compare_with_cache(self, plugin: AnnotationPlugin) -> None:
        """手动设置缓存后返回数据"""
        expected = {
            "symbol": "BTC/USDT",
            "timeframe": "H1",
            "total_annotations": 7,
            "total_detections": 5,
            "matched": 3,
            "missed": 4,
            "false_positives": 2,
            "type_mismatches": 0,
            "match_score": 0.545,
            "timestamp": "2026-03-23T12:00:00+00:00",
        }
        plugin._auto_compare_result = expected

        result = plugin.get_auto_compare_result()
        assert result == expected
        assert result["match_score"] == 0.545


class TestAutoCompareOnCreate:
    """create_annotation 端到端触发"""

    def test_auto_compare_on_create(self, plugin: AnnotationPlugin) -> None:
        """通过 create_annotation 逐条添加，第5条触发自动对比"""
        fake_history = [
            {"from": "IDLE", "to": "SC", "bar": 11, "confidence": 0.9},
            {"from": "SC", "to": "AR", "bar": 31, "confidence": 0.8},
        ]
        with patch.object(plugin, "_get_transition_history", return_value=fake_history):
            # 前4条不触发 — 使用与检测匹配的事件类型
            events_pre = [
                ("SC", 10, 12),
                ("AR", 30, 32),
                ("ST", 50, 52),
                ("SPRING", 70, 72),
            ]
            for evt, sb, eb in events_pre:
                plugin.create_annotation(
                    _make_event_annotation(event_type=evt, start_bar=sb, end_bar=eb)
                )
            assert plugin.get_auto_compare_result() is None

            # 第5条触发
            ann = plugin.create_annotation(
                _make_event_annotation(event_type="LPS", start_bar=90, end_bar=92)
            )
            assert ann is not None
            result = plugin.get_auto_compare_result()
            assert result is not None
            assert result["total_annotations"] == 5
            assert result["total_detections"] == 2
            # SC at bar 11 matches annotation SC at 10-12
            assert result["matched"] >= 1

    def test_auto_compare_failure_no_side_effect(
        self, plugin: AnnotationPlugin
    ) -> None:
        """自动对比异常不影响标注创建"""
        with patch.object(
            plugin,
            "_get_transition_history",
            side_effect=RuntimeError("boom"),
        ):
            for i in range(6):
                ann = plugin.create_annotation(
                    _make_event_annotation(event_type=f"EVT_{i}", start_bar=i * 10)
                )
                # 标注创建不受影响
                assert ann is not None
                assert ann.type == "event"

        # 自动对比结果仍为 None（异常被捕获）
        assert plugin.get_auto_compare_result() is None
