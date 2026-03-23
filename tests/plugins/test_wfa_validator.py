"""WFA 验证器测试"""

import numpy as np
import pandas as pd
import pytest

from src.plugins.evolution.wfa_validator import WFAConfig, WFAReport, WFAValidator


def _make_h4_data(n_bars: int = 1000) -> pd.DataFrame:
    """生成合成H4数据"""
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="4h")
    np.random.seed(42)
    close = 2000 + np.cumsum(np.random.randn(n_bars) * 10)
    opens = close - np.random.rand(n_bars) * 5
    highs = close + np.abs(np.random.randn(n_bars) * 10)
    lows = close - np.abs(np.random.randn(n_bars) * 10)
    # 确保 OHLC 有效性: high >= max(open, close), low <= min(open, close)
    highs = np.maximum(highs, np.maximum(opens, close))
    lows = np.minimum(lows, np.minimum(opens, close))
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": close,
            "volume": np.random.randint(100, 10000, n_bars).astype(float),
        },
        index=dates,
    )


@pytest.fixture
def data_dict():
    h4 = _make_h4_data(1200)
    return {"H4": h4}


@pytest.fixture
def dummy_evaluator():
    def evaluator(config, data):
        return {
            "SHARPE_RATIO": 0.8,
            "MAX_DRAWDOWN": 0.1,
            "WIN_RATE": 0.55,
            "PROFIT_FACTOR": 1.5,
            "TOTAL_TRADES": 10,
            "TOTAL_RETURN": 0.05,
        }

    return evaluator


class TestWFAWindows:
    def test_create_windows(self):
        cfg = WFAConfig(
            train_bars=200, test_bars=100, step_bars=100, min_windows=2, max_windows=5
        )
        wfa = WFAValidator(config=cfg)
        windows = wfa.create_windows(1000)
        assert len(windows) >= cfg.min_windows
        assert len(windows) <= cfg.max_windows

    def test_insufficient_data_returns_empty(self):
        cfg = WFAConfig(train_bars=500, test_bars=500, warmup_bars=100)
        wfa = WFAValidator(config=cfg)
        windows = wfa.create_windows(200)
        assert len(windows) == 0

    def test_windows_non_overlapping(self):
        cfg = WFAConfig(train_bars=200, test_bars=100, step_bars=100, min_windows=2)
        wfa = WFAValidator(config=cfg)
        windows = wfa.create_windows(1000)
        for w in windows:
            assert w.test_start > w.train_end


class TestWFAValidation:
    def test_validate_returns_report(self, data_dict, dummy_evaluator):
        cfg = WFAConfig(train_bars=200, test_bars=100, step_bars=100, min_windows=2)
        wfa = WFAValidator(config=cfg, evaluator_fn=dummy_evaluator)
        report = wfa.validate({"test": True}, data_dict)
        assert isinstance(report, WFAReport)

    def test_validate_no_evaluator_raises(self, data_dict):
        wfa = WFAValidator()
        with pytest.raises(ValueError):
            wfa.validate({"test": True}, data_dict)

    def test_validate_missing_h4(self, dummy_evaluator):
        wfa = WFAValidator(evaluator_fn=dummy_evaluator)
        report = wfa.validate({}, {"M15": _make_h4_data(100)})
        assert report.passed is False

    def test_validate_population(self, data_dict, dummy_evaluator):
        cfg = WFAConfig(train_bars=200, test_bars=100, step_bars=100, min_windows=2)
        wfa = WFAValidator(config=cfg, evaluator_fn=dummy_evaluator)
        reports = wfa.validate_population([{"a": 1}, {"b": 2}], data_dict)
        assert len(reports) == 2


class TestOOSDegradation:
    def test_compute_oos_degradation(self):
        dr = WFAValidator._compute_oos_degradation(
            train_sharpes=[1.0, 1.0, 1.0],
            test_sharpes=[0.8, 0.9, 0.7],
        )
        assert 0.0 < dr < 1.0

    def test_zero_train_sharpe(self):
        dr = WFAValidator._compute_oos_degradation(
            train_sharpes=[0.0, 0.0],
            test_sharpes=[0.5, 0.5],
        )
        assert dr == 1.0  # All pairs skipped → returns 1.0
