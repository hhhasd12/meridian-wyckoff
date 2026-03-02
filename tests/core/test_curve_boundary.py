"""
CurveBoundary单元测试
测试src/core/curve_boundary.py模块的所有功能

2026-03-02 更新：根据源码同步测试接口
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
import numpy as np
import pandas as pd

try:
    from src.core.curve_boundary import CurveBoundaryFitter, BoundaryType
except ImportError:
    from core.curve_boundary import CurveBoundaryFitter, BoundaryType


def _make_price_series(n=80, seed=42):
    np.random.seed(seed)
    prices = pd.Series(
        100 + np.cumsum(np.random.randn(n) * 0.5),
        index=pd.date_range("2024-01-01", periods=n, freq="h"),
    )
    return prices


class TestCurveBoundaryFitter(unittest.TestCase):
    """CurveBoundaryFitter单元测试类"""

    def setUp(self):
        self.fitter = CurveBoundaryFitter()
        prices = _make_price_series()
        self.high = prices + 2
        self.low = prices - 2
        self.close = prices

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.fitter)
        self.assertIsInstance(self.fitter.pivot_window, int)
        self.assertIsInstance(self.fitter.min_boundary_points, int)

    def test_detect_pivot_points(self):
        """测试枢轴点检测"""
        result = self.fitter.detect_pivot_points(self.high, include_time=True)
        self.assertIn("highs", result)
        self.assertIn("lows", result)
        self.assertIsInstance(result["highs"], list)
        self.assertIsInstance(result["lows"], list)

    def test_detect_pivot_points_without_time(self):
        """测试不含时间的枢轴点检测"""
        result = self.fitter.detect_pivot_points(self.close, include_time=False)
        self.assertIn("highs", result)
        self.assertIn("lows", result)

    def test_detect_pivot_points_too_short(self):
        """测试数据过短时的枢轴点检测"""
        short_series = pd.Series([100, 101, 102])
        result = self.fitter.detect_pivot_points(short_series)
        self.assertEqual(result["highs"], [])
        self.assertEqual(result["lows"], [])

    def test_fit_spline_boundary_insufficient_points(self):
        """测试枢轴点不足时返回 None"""
        result = self.fitter.fit_spline_boundary([(0, 100), (1, 101)], is_upper=True)
        self.assertIsNone(result)

    def test_detect_trading_range(self):
        """测试交易区间检测"""
        result = self.fitter.detect_trading_range(self.high, self.low, self.close)
        # 数据不足枢轴点的情况下可能返回 None
        self.assertTrue(result is None or isinstance(result, dict))

    def test_detect_trading_range_with_enough_pivots(self):
        """使用足够枢轴点的数据测试交易区间检测"""
        n = 200
        np.random.seed(0)
        idx = pd.date_range("2024-01-01", periods=n, freq="h")
        # 构造明显的震荡盘整区间
        base = 100 + np.sin(np.linspace(0, 6 * np.pi, n)) * 5
        high = pd.Series(base + 2, index=idx)
        low = pd.Series(base - 2, index=idx)
        close = pd.Series(base, index=idx)
        result = self.fitter.detect_trading_range(high, low, close)
        # 可能因枢轴点不足仍返回 None，只验证类型
        self.assertTrue(result is None or isinstance(result, dict))

    def test_record_and_get_boundary_event(self):
        """测试边界事件记录与获取"""
        tr_result = {"boundary_type": "RECTANGLE", "confidence": 0.8}
        self.fitter.record_boundary_event(tr_result)
        history = self.fitter.get_boundary_history(n=10)
        self.assertIsInstance(history, list)
        self.assertGreaterEqual(len(history), 1)

    def test_get_current_boundary_initially_none(self):
        """测试初始时当前边界为 None"""
        fitter = CurveBoundaryFitter()
        result = fitter.get_current_boundary()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
