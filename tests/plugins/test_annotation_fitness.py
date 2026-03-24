"""标注匹配度接入 fitness 的测试

覆盖:
1. 无标注文件时 annotation_score = 0.0
2. 标注不足 min_annotations 时 = 0.0
3. 有足够标注时返回 0-1 分数
4. 有标注时 fitness (COMPOSITE_SCORE) 被标注权重混合
5. 无标注时 fitness 完全不变
6. _extract_transitions 从 bar_details 提取转换历史
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.kernel.types import BacktestResult, BacktestTrade, BarDetail
from src.plugins.evolution.evaluator import StandardEvaluator


# ================================================================
# 辅助工厂
# ================================================================


def _make_bar_detail(state: str = "IDLE", confidence: float = 0.5) -> BarDetail:
    return BarDetail(
        phase="A",
        state=state,
        confidence=confidence,
        state_changed=False,
    )


def _make_backtest_result(
    bar_details: Optional[List[BarDetail]] = None,
    total_trades: int = 10,
) -> BacktestResult:
    """创建最小 BacktestResult"""
    if bar_details is None:
        bar_details = [_make_bar_detail() for _ in range(20)]

    trades = [
        BacktestTrade(
            entry_bar=i * 5,
            exit_bar=i * 5 + 3,
            entry_price=100.0,
            exit_price=101.0 if i % 2 == 0 else 99.0,
            side="LONG",
            size=1.0,
            pnl=1.0 if i % 2 == 0 else -1.0,
            pnl_pct=0.01 if i % 2 == 0 else -0.01,
            exit_reason="TAKE_PROFIT" if i % 2 == 0 else "STOP_LOSS",
            hold_bars=3,
            entry_state="SC",
            max_favorable=2.0,
            max_adverse=1.0,
        )
        for i in range(total_trades)
    ]

    return BacktestResult(
        trades=trades,
        total_return=0.05,
        sharpe_ratio=1.5,
        max_drawdown=0.1,
        win_rate=0.5,
        profit_factor=1.2,
        total_trades=total_trades,
        avg_hold_bars=3.0,
        config_hash="test123",
        equity_curve=[10000.0 + i * 10 for i in range(20)],
        bar_phases=["A"] * 20,
        bar_states=["SC"] * 20,
        bar_details=bar_details,
    )


def _write_annotations(
    ann_dir: Path, annotations: List[Dict[str, Any]], filename: str = "ETHUSDT_H4.jsonl"
) -> None:
    """写标注文件到指定目录"""
    ann_dir.mkdir(parents=True, exist_ok=True)
    with open(ann_dir / filename, "w", encoding="utf-8") as f:
        for ann in annotations:
            f.write(json.dumps(ann) + "\n")


# ================================================================
# 测试
# ================================================================


class TestAnnotationScore:
    """_compute_annotation_score 单元测试"""

    def test_no_annotation_file(self, tmp_path: Path) -> None:
        """无标注文件时返回 0.0"""
        evaluator = StandardEvaluator(
            annotation_weight=0.3,
            annotation_dir=str(tmp_path / "nonexistent"),
        )
        result = _make_backtest_result()
        score = evaluator._compute_annotation_score(result)
        assert score == 0.0

    def test_empty_annotation_dir(self, tmp_path: Path) -> None:
        """标注目录存在但无 .jsonl 文件时返回 0.0"""
        ann_dir = tmp_path / "annotations"
        ann_dir.mkdir()
        evaluator = StandardEvaluator(
            annotation_weight=0.3,
            annotation_dir=str(ann_dir),
        )
        result = _make_backtest_result()
        score = evaluator._compute_annotation_score(result)
        assert score == 0.0

    def test_insufficient_annotations(self, tmp_path: Path) -> None:
        """标注不足 min_annotations(5) 时返回 0.0"""
        ann_dir = tmp_path / "annotations"
        # 只写3个 event 标注 (< 5)
        annotations = [
            {
                "type": "event",
                "event_type": "SC",
                "start_bar_index": i,
                "end_bar_index": i,
            }
            for i in range(3)
        ]
        _write_annotations(ann_dir, annotations)

        evaluator = StandardEvaluator(
            annotation_weight=0.3,
            annotation_dir=str(ann_dir),
            min_annotations=5,
        )
        result = _make_backtest_result()
        score = evaluator._compute_annotation_score(result)
        assert score == 0.0

    def test_annotation_score_calculation(self, tmp_path: Path) -> None:
        """有足够标注时返回 0-1 匹配度分数"""
        ann_dir = tmp_path / "annotations"
        # 写 6 个事件标注
        annotations = [
            {
                "type": "event",
                "event_type": "SC",
                "start_bar_index": 5,
                "end_bar_index": 5,
            },
            {
                "type": "event",
                "event_type": "AR",
                "start_bar_index": 10,
                "end_bar_index": 10,
            },
            {
                "type": "event",
                "event_type": "ST",
                "start_bar_index": 15,
                "end_bar_index": 15,
            },
            {
                "type": "event",
                "event_type": "SPRING",
                "start_bar_index": 20,
                "end_bar_index": 20,
            },
            {
                "type": "event",
                "event_type": "SOS",
                "start_bar_index": 25,
                "end_bar_index": 25,
            },
            {
                "type": "event",
                "event_type": "BU",
                "start_bar_index": 30,
                "end_bar_index": 30,
            },
        ]
        _write_annotations(ann_dir, annotations)

        # bar_details: 在对应位置触发状态变化
        details: List[BarDetail] = []
        states = ["IDLE"] * 40
        states[5] = "SC"
        states[10] = "AR"
        states[15] = "ST"
        states[20] = "SPRING"
        states[25] = "SOS"
        states[30] = "BU"
        for i, s in enumerate(states):
            details.append(_make_bar_detail(state=s))

        evaluator = StandardEvaluator(
            annotation_weight=0.3,
            annotation_dir=str(ann_dir),
            min_annotations=5,
        )
        result = _make_backtest_result(bar_details=details)
        score = evaluator._compute_annotation_score(result)
        # 6个标注都应该匹配上 → score > 0
        assert 0.0 < score <= 1.0

    def test_non_event_annotations_ignored(self, tmp_path: Path) -> None:
        """非 event 类型标注不参与匹配"""
        ann_dir = tmp_path / "annotations"
        # 10 个 level 标注 + 2 个 event 标注 → event 不足 5 个
        annotations = [
            {"type": "level", "level_label": "support", "price": 100.0}
            for _ in range(10)
        ]
        annotations.extend(
            [
                {
                    "type": "event",
                    "event_type": "SC",
                    "start_bar_index": 5,
                    "end_bar_index": 5,
                },
                {
                    "type": "event",
                    "event_type": "AR",
                    "start_bar_index": 10,
                    "end_bar_index": 10,
                },
            ]
        )
        _write_annotations(ann_dir, annotations)

        evaluator = StandardEvaluator(
            annotation_weight=0.3,
            annotation_dir=str(ann_dir),
            min_annotations=5,
        )
        result = _make_backtest_result()
        score = evaluator._compute_annotation_score(result)
        assert score == 0.0  # event 标注不足 5 个


class TestExtractTransitions:
    """_extract_transitions 静态方法测试"""

    def test_extract_state_changes(self) -> None:
        """从 bar_details 正确提取状态转换"""
        details = [
            _make_bar_detail("IDLE"),
            _make_bar_detail("IDLE"),
            _make_bar_detail("SC"),  # bar 2: IDLE → SC
            _make_bar_detail("SC"),
            _make_bar_detail("AR"),  # bar 4: SC → AR
            _make_bar_detail("AR"),
            _make_bar_detail("ST"),  # bar 6: AR → ST
        ]
        transitions = StandardEvaluator._extract_transitions(
            _make_backtest_result(bar_details=details)
        )
        assert len(transitions) == 3
        assert transitions[0] == {
            "from": "IDLE",
            "to": "SC",
            "bar": 2,
            "confidence": 0.5,
        }
        assert transitions[1] == {"from": "SC", "to": "AR", "bar": 4, "confidence": 0.5}
        assert transitions[2] == {"from": "AR", "to": "ST", "bar": 6, "confidence": 0.5}

    def test_no_state_changes(self) -> None:
        """无状态变化时返回空列表"""
        details = [_make_bar_detail("IDLE") for _ in range(10)]
        transitions = StandardEvaluator._extract_transitions(
            _make_backtest_result(bar_details=details)
        )
        assert transitions == []


class TestFitnessWithAnnotation:
    """fitness 合成（有/无标注）"""

    @patch("src.plugins.evolution.bar_by_bar_backtester.BarByBarBacktester")
    def test_fitness_with_annotation_weight(
        self, mock_backtester_cls: MagicMock, tmp_path: Path
    ) -> None:
        """有标注时 COMPOSITE_SCORE 被标注权重混合"""
        ann_dir = tmp_path / "annotations"
        # 准备标注 (6个event，类型匹配 bar_details 状态变化)
        annotations = [
            {
                "type": "event",
                "event_type": "SC",
                "start_bar_index": 5,
                "end_bar_index": 5,
            },
            {
                "type": "event",
                "event_type": "AR",
                "start_bar_index": 10,
                "end_bar_index": 10,
            },
            {
                "type": "event",
                "event_type": "ST",
                "start_bar_index": 15,
                "end_bar_index": 15,
            },
            {
                "type": "event",
                "event_type": "SPRING",
                "start_bar_index": 20,
                "end_bar_index": 20,
            },
            {
                "type": "event",
                "event_type": "SOS",
                "start_bar_index": 25,
                "end_bar_index": 25,
            },
            {
                "type": "event",
                "event_type": "BU",
                "start_bar_index": 30,
                "end_bar_index": 30,
            },
        ]
        _write_annotations(ann_dir, annotations)

        # Mock 回测结果 — bar_details 有状态变化，能提取 transitions
        states = ["IDLE"] * 50
        states[5] = "SC"
        states[10] = "AR"
        states[15] = "ST"
        states[20] = "SPRING"
        states[25] = "SOS"
        states[30] = "BU"
        details = [_make_bar_detail(state=s) for s in states]
        mock_result = _make_backtest_result(bar_details=details, total_trades=10)
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_result
        mock_backtester_cls.return_value = mock_instance

        evaluator = StandardEvaluator(
            annotation_weight=0.3,
            annotation_dir=str(ann_dir),
            min_annotations=5,
        )
        import numpy as np
        import pandas as pd

        h4 = pd.DataFrame(
            {
                "open": np.ones(100),
                "high": np.ones(100) * 1.01,
                "low": np.ones(100) * 0.99,
                "close": np.ones(100),
                "volume": np.ones(100),
            },
            index=pd.date_range("2025-01-01", periods=100, freq="4h"),
        )
        metrics = evaluator({"test": 1}, {"H4": h4})

        # 验证标注分数被记录且 > 0
        assert metrics["ANNOTATION_SCORE"] > 0.0
        assert metrics["ANNOTATION_SCORE"] <= 1.0

        # 对比无标注权重时的 base composite
        evaluator_base = StandardEvaluator(
            annotation_weight=0.0,
            annotation_dir=str(ann_dir),
        )
        metrics_base = evaluator_base({"test": 1}, {"H4": h4})
        base_composite = metrics_base["COMPOSITE_SCORE"]

        # 有标注时 composite 应被混合: base * 0.7 + ann_score * 0.3
        expected = base_composite * 0.7 + metrics["ANNOTATION_SCORE"] * 0.3
        assert abs(metrics["COMPOSITE_SCORE"] - expected) < 1e-9

    @patch("src.plugins.evolution.bar_by_bar_backtester.BarByBarBacktester")
    def test_fitness_without_annotation(
        self, mock_backtester_cls: MagicMock, tmp_path: Path
    ) -> None:
        """无标注时 COMPOSITE_SCORE 完全不受影响"""
        # 空的标注目录
        ann_dir = tmp_path / "annotations"

        mock_result = _make_backtest_result(total_trades=10)
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_result
        mock_backtester_cls.return_value = mock_instance

        # annotation_weight=0.3 但无标注文件
        evaluator_with_weight = StandardEvaluator(
            annotation_weight=0.3,
            annotation_dir=str(ann_dir),
            min_annotations=5,
        )
        # annotation_weight=0 (默认)
        evaluator_no_weight = StandardEvaluator(
            annotation_weight=0.0,
            annotation_dir=str(ann_dir),
        )

        import pandas as pd
        import numpy as np

        h4 = pd.DataFrame(
            {
                "open": np.ones(100),
                "high": np.ones(100) * 1.01,
                "low": np.ones(100) * 0.99,
                "close": np.ones(100),
                "volume": np.ones(100),
            },
            index=pd.date_range("2025-01-01", periods=100, freq="4h"),
        )

        metrics_with = evaluator_with_weight({"test": 1}, {"H4": h4})
        metrics_without = evaluator_no_weight({"test": 1}, {"H4": h4})

        # 无标注时，两者的 COMPOSITE_SCORE 应完全一致
        assert metrics_with["COMPOSITE_SCORE"] == metrics_without["COMPOSITE_SCORE"]
        # ANNOTATION_SCORE 应为 0 或不存在
        assert metrics_with.get("ANNOTATION_SCORE", 0.0) == 0.0


class TestPluginAnnotationWeight:
    """EvolutionPlugin 传递 annotation_weight 到 evaluator"""

    def test_plugin_passes_annotation_weight(self) -> None:
        """plugin._init_evolution_components 正确传递 annotation_weight"""
        from src.plugins.evolution.plugin import EvolutionPlugin

        plugin = EvolutionPlugin()
        plugin._init_evolution_components({"annotation_fitness_weight": 0.3})

        assert plugin._evaluator is not None
        assert plugin._evaluator.annotation_weight == 0.3

    def test_plugin_default_no_annotation_weight(self) -> None:
        """默认配置下 annotation_weight = 0.0"""
        from src.plugins.evolution.plugin import EvolutionPlugin

        plugin = EvolutionPlugin()
        plugin._init_evolution_components({})

        assert plugin._evaluator is not None
        assert plugin._evaluator.annotation_weight == 0.0
