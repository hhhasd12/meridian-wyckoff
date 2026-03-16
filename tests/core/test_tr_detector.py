"""
TRDetector单元测试
测试src/core/tr_detector.py模块的所有功能

2026-03-02 更新：根据源码同步测试接口
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
from datetime import datetime
import numpy as np
import pandas as pd

try:
    from src.plugins.pattern_detection.tr_detector import TRDetector, TradingRange, TRStatus, BreakoutDirection
except ImportError:
    from core.tr_detector import TRDetector, TradingRange, TRStatus, BreakoutDirection


def _make_ohlcv(n=60, seed=42):
    np.random.seed(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="h")
    base = 100 + np.random.randn(n) * 2
    return pd.DataFrame(
        {
            "open": base,
            "high": base + abs(np.random.randn(n)) * 2 + 1,
            "low": base - abs(np.random.randn(n)) * 2 - 1,
            "close": base + np.random.randn(n) * 0.5,
            "volume": np.random.rand(n) * 1000 + 500,
        },
        index=dates,
    )


class TestTRDetector(unittest.TestCase):
    """TRDetector单元测试类"""

    def setUp(self):
        self.detector = TRDetector()
        self.df = _make_ohlcv()
        # 趋势数据
        df_trend = self.df.copy()
        df_trend["close"] = np.linspace(80, 120, len(df_trend))
        df_trend["high"] = df_trend["close"] + 3
        df_trend["low"] = df_trend["close"] - 3
        self.df_trend = df_trend

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.detector)
        self.assertEqual(self.detector.min_tr_width_pct, 1.0)
        self.assertEqual(self.detector.min_tr_bars, 10)
        self.assertEqual(self.detector.stability_lock_bars, 5)
        self.assertEqual(self.detector.breakout_confirmation_bars, 3)
        self.assertEqual(self.detector.breakout_threshold_pct, 1.0)

    def test_initialization_with_custom_config(self):
        """测试自定义配置初始化"""
        config = {
            "min_tr_width_pct": 2.0,
            "min_tr_bars": 15,
            "stability_lock_bars": 7,
            "breakout_confirmation_bars": 5,
            "breakout_threshold_pct": 1.5,
        }
        detector_custom = TRDetector(config)
        self.assertEqual(detector_custom.min_tr_width_pct, 2.0)
        self.assertEqual(detector_custom.min_tr_bars, 15)

    def test_detect_trading_range_rectangle(self):
        """测试矩形交易区间检测"""
        tr_result = self.detector.detect_trading_range(self.df)
        self.assertTrue(tr_result is None or isinstance(tr_result, TradingRange))

    def test_detect_trading_range_trend(self):
        """测试趋势市场检测"""
        tr_result = self.detector.detect_trading_range(self.df_trend)
        self.assertTrue(tr_result is None or isinstance(tr_result, TradingRange))

    def test_detect_trading_range_triangle(self):
        """测试三角形交易区间检测"""
        # 构造三角形数据（收敛型）
        n = 60
        dates = pd.date_range("2025-01-01", periods=n, freq="h")
        np.random.seed(1)
        spread = np.linspace(5, 1, n)  # 收敛
        mid = 100
        df = pd.DataFrame(
            {
                "open": mid + np.random.randn(n) * 0.5,
                "high": mid + spread,
                "low": mid - spread,
                "close": mid + np.random.randn(n) * 0.5,
                "volume": np.random.rand(n) * 1000 + 500,
            },
            index=dates,
        )
        result = self.detector.detect_trading_range(df)
        self.assertTrue(result is None or isinstance(result, TradingRange))

    def test_detect_breakout_internal(self):
        """测试内部突破检测方法"""
        # 构造有突破迹象的TR结果
        tr_result = {
            "breakout_direction": 1,
            "breakout_strength": 0.8,
            "upper_price": 110,
            "lower_price": 90,
            "upper_boundary": {"curvature": 0.1, "confidence": 0.8},
            "lower_boundary": {"curvature": 0.1, "confidence": 0.8},
        }
        direction, strength = self.detector._detect_breakout(tr_result, self.df)
        self.assertIsInstance(direction, BreakoutDirection)
        self.assertIsInstance(float(strength), float)

    def test_calculate_tr_confidence(self):
        """测试TR置信度计算"""
        from src.plugins.pattern_detection.curve_boundary import BoundaryType
        tr_result = {
            "tr_confidence": 0.75,
            "boundary_distance": 5.0,
            "breakout_strength": 0.0,
            "price_position": 0.5,
            "upper_price": 110.0,
            "lower_price": 90.0,
            "upper_boundary": {
                "confidence": 0.8,
                "boundary_type": BoundaryType.RECTANGLE,
            },
            "lower_boundary": {
                "confidence": 0.7,
                "boundary_type": BoundaryType.RECTANGLE,
            },
        }
        validation_result = {"is_valid": True, "score": 0.8}
        confidence = self.detector._calculate_tr_confidence(
            tr_result, validation_result, self.df
        )
        self.assertIsInstance(float(confidence), float)
        self.assertGreaterEqual(confidence, 0)
        self.assertLessEqual(confidence, 1)

    def test_calculate_stability_score(self):
        """测试TR稳定性评分计算"""
        tr_result = {
            "price_position": 0.5,
            "upper_price": 110.0,
            "lower_price": 90.0,
            "upper_boundary": {"slope": 0.01},
            "lower_boundary": {"slope": -0.01},
        }
        stability = self.detector._calculate_stability_score(tr_result, self.df)
        self.assertIsInstance(float(stability), float)
        self.assertGreaterEqual(stability, 0)
        self.assertLessEqual(stability, 1)

    def test_update_tr_stability(self):
        """测试TR稳定性更新（通过_update_stability_lock）"""
        # 先检测一个TR以建立active_tr
        tr_result = self.detector.detect_trading_range(self.df)
        if tr_result is not None:
            self.detector._update_stability_lock(tr_result, self.df)

    def test_validate_breakout(self):
        """测试突破验证（通过_confirm_breakout）"""
        tr_result = {
            "upper_price": 110.0,
            "lower_price": 90.0,
        }
        result = self.detector._confirm_breakout(
            BreakoutDirection.UP, tr_result, self.df
        )
        self.assertIsInstance(result, bool)

    def test_get_tr_statistics(self):
        """测试获取统计数据"""
        self.detector.detect_trading_range(self.df)
        stats = self.detector.get_statistics()
        self.assertIsInstance(stats, dict)

    def test_get_tr_signals(self):
        """测试获取TR信号"""
        # 无 TR 时
        signals = self.detector.get_tr_signals(current_price=100.0)
        self.assertIsInstance(signals, dict)
        self.assertIn("tr_status", signals)

    def test_real_time_processing(self):
        """测试实时逐条处理"""
        results = []
        df = _make_ohlcv(n=30, seed=7)
        for i in range(10, len(df)):
            result = self.detector.detect_trading_range(df.iloc[:i])
            results.append(result)
        # 结果要么 None 要么 TradingRange
        for r in results:
            self.assertTrue(r is None or isinstance(r, TradingRange))

    def test_error_handling(self):
        """测试错误处理"""
        empty_df = pd.DataFrame()
        result = self.detector.detect_trading_range(empty_df)
        self.assertIsNone(result)

        # 数据过短
        short_df = _make_ohlcv(n=5, seed=0)
        result2 = self.detector.detect_trading_range(short_df)
        self.assertIsNone(result2)


if __name__ == "__main__":
    unittest.main()
