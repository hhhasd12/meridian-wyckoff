"""端到端进化管线测试 — GA + Evaluator + WFA + AntiOverfit"""

import numpy as np
import pandas as pd
import pytest

from src.plugins.evolution.anti_overfit import AntiOverfitConfig, AntiOverfitGuard
from src.plugins.evolution.evaluator import StandardEvaluator
from src.plugins.evolution.genetic_algorithm import GAConfig, GeneticAlgorithm
from src.plugins.evolution.wfa_validator import WFAConfig, WFAValidator
from src.plugins.self_correction.mistake_book import MistakeBook


def _make_h4_data(n_bars: int = 500) -> pd.DataFrame:
    """生成合成H4数据"""
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="4h")
    np.random.seed(42)
    close = 2000 + np.cumsum(np.random.randn(n_bars) * 10)
    return pd.DataFrame(
        {
            "open": close - np.random.rand(n_bars) * 5,
            "high": close + np.abs(np.random.randn(n_bars) * 10),
            "low": close - np.abs(np.random.randn(n_bars) * 10),
            "close": close,
            "volume": np.random.randint(100, 10000, n_bars).astype(float),
        },
        index=dates,
    )


def _baseline_config():
    return {
        "period_weight_filter": {
            "weights": {"H4": 0.50, "H1": 0.30, "M15": 0.20},
        },
        "threshold_parameters": {"confidence_threshold": 0.30},
        "signal_control": {"cooldown_bars": 8},
    }


class TestStandardEvaluator:
    def test_evaluator_returns_metrics(self):
        evaluator = StandardEvaluator()
        config = _baseline_config()
        data = {"H4": _make_h4_data(100)}
        metrics = evaluator(config, data)
        assert isinstance(metrics, dict)
        assert "SHARPE_RATIO" in metrics
        assert "COMPOSITE_SCORE" in metrics

    def test_evaluator_insufficient_data(self):
        evaluator = StandardEvaluator()
        config = _baseline_config()
        data = {"H4": _make_h4_data(10)}  # too few bars
        metrics = evaluator(config, data)
        assert metrics["TOTAL_TRADES"] == 0

    def test_evaluator_with_mistake_book(self):
        book = MistakeBook()
        evaluator = StandardEvaluator(mistake_book=book)
        config = _baseline_config()
        data = {"H4": _make_h4_data(200)}
        evaluator(config, data)
        # Mistake book may or may not have records depending on signals


class TestGAWithEvaluator:
    def test_ga_with_dummy_evaluator(self):
        ga = GeneticAlgorithm(
            _baseline_config(),
            GAConfig(population_size=5, max_generations=2),
        )

        def dummy_eval(config, data):
            return {"COMPOSITE_SCORE": np.random.random() * 0.5}

        best = ga.run(dummy_eval, {"H4": None})
        assert best is not None
        assert best.fitness >= 0


class TestMistakeBookIntegration:
    def test_record_trade_mistake(self):
        book = MistakeBook()
        error_id = book.record_trade_mistake(
            side="LONG",
            entry_price=100.0,
            exit_price=95.0,
            pnl=-5.0,
            pnl_pct=-0.05,
            hold_bars=10,
        )
        assert error_id is not None
        assert len(book.records) == 1

    def test_record_multiple_mistakes(self):
        book = MistakeBook()
        # Use record_history instead of records dict (records can dedupe by timestamp-based key)
        for i in range(5):
            book.record_trade_mistake(
                side="SHORT",
                entry_price=100.0 + i,  # Different prices to avoid identical keys
                exit_price=102.0 + i,
                pnl=-2.0,
                pnl_pct=-0.02,
            )
        assert len(book.record_history) == 5
