"""
BreakoutValidator单元测试
测试src/core/breakout_validator.py模块的所有功能

注意：此测试文件仅测试源代码中实际存在的方法。
2026-02-20 更新：根据源码同步测试接口
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

try:
    from src.plugins.signal_validation.breakout_validator import BreakoutValidator, BreakoutStatus
except ImportError:
    from core.breakout_validator import BreakoutValidator, BreakoutStatus


class TestBreakoutValidator(unittest.TestCase):
    """BreakoutValidator单元测试类"""

    def setUp(self):
        """测试前准备"""
        self.validator = BreakoutValidator()
        self.create_test_data()

    def create_test_data(self):
        """创建测试数据"""
        dates = pd.date_range(start="2025-01-01", periods=50, freq="h")
        np.random.seed(42)

        base_price = 105.0
        noise = np.random.randn(50) * 2.0

        self.df_normal = pd.DataFrame(
            {
                "open": base_price + noise,
                "high": base_price + noise + np.random.rand(50) * 3.0,
                "low": base_price + noise - np.random.rand(50) * 3.0,
                "close": base_price + noise + np.random.randn(50) * 1.0,
                "volume": np.random.rand(50) * 1000 + 500,
            },
            index=dates,
        )

        # 向上突破数据
        self.df_up_breakout = self.df_normal.copy()
        self.df_up_breakout.iloc[-5:, :] = pd.DataFrame(
            {
                "open": [110.5, 111.0, 110.8, 111.5, 112.0],
                "high": [111.5, 112.0, 111.8, 112.5, 113.0],
                "low": [110.0, 110.5, 110.3, 111.0, 111.5],
                "close": [111.0, 111.5, 111.2, 112.0, 112.5],
                "volume": [1500, 1800, 1200, 2000, 2200],
            },
            index=self.df_up_breakout.index[-5:],
        )

        # 向下跌破数据
        self.df_down_breakout = self.df_normal.copy()
        self.df_down_breakout.iloc[-5:, :] = pd.DataFrame(
            {
                "open": [99.5, 99.0, 98.8, 98.5, 98.0],
                "high": [100.5, 100.0, 99.8, 99.5, 99.0],
                "low": [99.0, 98.5, 98.3, 98.0, 97.5],
                "close": [99.5, 99.0, 98.8, 98.5, 98.0],
                "volume": [1500, 1800, 1200, 2000, 2200],
            },
            index=self.df_down_breakout.index[-5:],
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.validator)
        self.assertEqual(self.validator.atr_multiplier, 1.0)
        self.assertEqual(self.validator.retest_depth_pct, 30.0)
        self.assertEqual(self.validator.max_retest_bars, 20)
        self.assertEqual(self.validator.confirmation_bars, 3)

        config = {
            "atr_multiplier": 1.5,
            "retest_depth_pct": 40.0,
            "max_retest_bars": 15,
            "confirmation_bars": 5,
        }
        validator_custom = BreakoutValidator(config)
        self.assertEqual(validator_custom.atr_multiplier, 1.5)
        self.assertEqual(validator_custom.retest_depth_pct, 40.0)
        self.assertEqual(validator_custom.max_retest_bars, 15)
        self.assertEqual(validator_custom.confirmation_bars, 5)

    def test_detect_initial_breakout_up(self):
        """测试向上突破检测"""
        resistance_level = 110.0
        support_level = 100.0
        current_atr = 2.0

        result = self.validator.detect_initial_breakout(
            self.df_up_breakout.tail(10), resistance_level, support_level, current_atr
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], 1)
        self.assertEqual(result["status"], BreakoutStatus.INITIAL_BREAKOUT)
        self.assertGreater(result["breakout_price"], resistance_level)

    def test_detect_initial_breakout_down(self):
        """测试向下跌破检测"""
        resistance_level = 110.0
        support_level = 100.0
        current_atr = 2.0

        result = self.validator.detect_initial_breakout(
            self.df_down_breakout.tail(10), resistance_level, support_level, current_atr
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], -1)
        self.assertEqual(result["status"], BreakoutStatus.INITIAL_BREAKOUT)
        self.assertLess(result["breakout_price"], support_level)

    def test_detect_initial_breakout_no_breakout(self):
        """测试无突破情况"""
        resistance_level = 110.0
        support_level = 100.0
        current_atr = 2.0

        result = self.validator.detect_initial_breakout(
            self.df_normal.tail(10), resistance_level, support_level, current_atr
        )

        self.assertIsNone(result)

    def test_update_breakout_status(self):
        """测试更新突破状态"""
        resistance_level = 110.0
        support_level = 100.0
        current_atr = 2.0

        # 创建突破
        result = self.validator.detect_initial_breakout(
            self.df_up_breakout.tail(10), resistance_level, support_level, current_atr
        )
        self.assertIsNotNone(result)
        
        breakout_id = result["breakout_id"]
        
        # 更新突破状态
        update_result = self.validator.update_breakout_status(
            breakout_id=breakout_id,
            current_price=111.5,
            current_low=110.0,
            current_high=112.0,
            current_time=pd.Timestamp("2025-01-03 10:00:00"),
        )
        
        self.assertIsNotNone(update_result)

    def test_get_breakout_signal(self):
        """测试获取突破信号"""
        resistance_level = 110.0
        support_level = 100.0
        current_atr = 2.0

        # 创建突破
        result = self.validator.detect_initial_breakout(
            self.df_up_breakout.tail(10), resistance_level, support_level, current_atr
        )
        self.assertIsNotNone(result)
        
        breakout_id = result["breakout_id"]
        
        # 获取信号
        signal = self.validator.get_breakout_signal(breakout_id)
        self.assertIsNotNone(signal)
        self.assertIn("signal", signal)

    def test_get_statistics(self):
        """测试获取统计数据"""
        resistance_level = 110.0
        support_level = 100.0
        current_atr = 2.0

        # 创建一些突破
        for i in range(3):
            df = self.df_up_breakout if i % 2 == 0 else self.df_down_breakout
            result = self.validator.detect_initial_breakout(
                df.tail(10), resistance_level, support_level, current_atr
            )

        stats = self.validator.get_statistics()
        self.assertIsInstance(stats, dict)
        self.assertIn("total_breakouts", stats)

    def test_cleanup_old_breakouts(self):
        """测试清理旧突破"""
        resistance_level = 110.0
        support_level = 100.0
        current_atr = 2.0

        # 创建突破
        for i in range(3):
            df = self.df_up_breakout if i % 2 == 0 else self.df_down_breakout
            self.validator.detect_initial_breakout(
                df.tail(10), resistance_level, support_level, current_atr
            )

        # 清理旧突破
        self.validator.cleanup_old_breakouts(max_age_hours=0)
        
        # 验证清理结果
        stats = self.validator.get_statistics()
        self.assertIsInstance(stats, dict)

    def test_error_handling(self):
        """测试错误处理"""
        # 无效DataFrame
        with self.assertRaises((ValueError, TypeError)):
            self.validator.detect_initial_breakout(
                None, 110.0, 100.0, 2.0
            )

        # 空DataFrame
        empty_df = pd.DataFrame()
        result = self.validator.detect_initial_breakout(empty_df, 110.0, 100.0, 2.0)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
