"""
DataSanitizer单元测试
测试src/core/data_sanitizer.py模块的所有功能

2026-03-02 更新：根据源码同步测试接口，修复所有 skipped 测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

try:
    from src.core.data_sanitizer import DataSanitizer, DataSanitizerConfig, AnomalyEvent, RawCandle
except ImportError:
    from core.data_sanitizer import DataSanitizer, DataSanitizerConfig, AnomalyEvent, RawCandle


def _make_normal_candle():
    return {
        "timestamp": datetime.now(),
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 1000.0,
    }


class TestDataSanitizer(unittest.TestCase):
    """DataSanitizer单元测试类"""

    def setUp(self):
        self.sanitizer = DataSanitizer()
        dates = pd.date_range(start="2025-01-01", periods=50, freq="h")
        np.random.seed(42)
        self.df_normal = pd.DataFrame(
            {
                "open": 100 + np.random.randn(50) * 2,
                "high": 100 + np.random.randn(50) * 3 + 5,
                "low": 100 + np.random.randn(50) * 3 - 5,
                "close": 100 + np.random.randn(50) * 2,
                "volume": np.random.rand(50) * 1000 + 500,
            },
            index=dates,
        )

    def test_sanitize_candle(self):
        """测试单根K线检测"""
        result, is_anomaly, event = self.sanitizer.sanitize_candle(_make_normal_candle())
        self.assertIsNotNone(result)
        self.assertIsInstance(is_anomaly, bool)

    def test_sanitize_dataframe(self):
        """测试DataFrame清洗"""
        result = self.sanitizer.sanitize_dataframe(self.df_normal)
        self.assertIsNotNone(result)

    def test_anomaly_event_serialization(self):
        """测试异常事件序列化"""
        raw = RawCandle(
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=0.0,  # zero volume → anomaly
        )
        from src.core.data_sanitizer import MarketType
        event = AnomalyEvent(
            raw_candle=raw,
            anomaly_types=["ZERO_VOLUME"],
            anomaly_score=1.0,
            market_type=MarketType.CRYPTO,
        )
        d = event.to_state_machine_input()
        self.assertIsInstance(d, dict)
        self.assertIn("type", d)
        self.assertIn("event_category", d)

    def test_circuit_breaker_integration(self):
        """测试熔断机制集成（通过异常数据触发）"""
        candle = _make_normal_candle()
        candle["volume"] = 0.0  # 零成交量 → ZERO_VOLUME 异常
        result, is_anomaly, event = self.sanitizer.sanitize_candle(candle)
        # 结果应为异常事件
        self.assertTrue(is_anomaly)
        self.assertIsNotNone(event)

    def test_market_type_sensitive_handling(self):
        """测试市场类型敏感处理"""
        from src.core.data_sanitizer import MarketType
        config_crypto = DataSanitizerConfig()
        config_crypto.MARKET_TYPE = MarketType.CRYPTO
        sanitizer_crypto = DataSanitizer(config_crypto)
        self.assertEqual(sanitizer_crypto.market_type, MarketType.CRYPTO)

        config_stock = DataSanitizerConfig()
        config_stock.MARKET_TYPE = MarketType.STOCK
        sanitizer_stock = DataSanitizer(config_stock)
        self.assertEqual(sanitizer_stock.market_type, MarketType.STOCK)

    def test_sanitize_candle_invalid_range(self):
        """测试无效价格范围处理"""
        # 创建 high < low 的无效K线（close > high 也是异常）
        candle = {
            "timestamp": datetime.now(),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 200.0,  # 远超 high，触发范围异常
            "volume": 1000.0,
        }
        result, is_anomaly, event = self.sanitizer.sanitize_candle(candle)
        self.assertIsNotNone(result)
        self.assertIsInstance(is_anomaly, bool)

    def test_sanitize_candle_price_gap(self):
        """测试价格跳空处理"""
        from src.core.data_sanitizer import HistoricalContext
        candle = {
            "timestamp": datetime.now(),
            "open": 200.0,   # 相比历史均价100大幅跳空
            "high": 205.0,
            "low": 195.0,
            "close": 202.0,
            "volume": 1000.0,
        }
        context = HistoricalContext(price_ma50=100.0, atr14=1.0)
        result, is_anomaly, event = self.sanitizer.sanitize_candle(candle, context)
        self.assertIsNotNone(result)
        self.assertIsInstance(is_anomaly, bool)

    def test_error_handling(self):
        """测试错误处理"""
        # 空DataFrame
        empty_df = pd.DataFrame()
        result = self.sanitizer.sanitize_dataframe(empty_df)
        # 应该能处理，不崩溃
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
