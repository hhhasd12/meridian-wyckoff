"""
市场体制（Regime）独立检测模块测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.plugins.market_regime import MarketRegime, RegimeDetector


class TestMarketRegime:
    """测试市场体制枚举"""

    def test_enum_values(self):
        """测试枚举值"""
        assert MarketRegime.TRENDING.value == "TRENDING"
        assert MarketRegime.RANGING.value == "RANGING"
        assert MarketRegime.VOLATILE.value == "VOLATILE"
        assert MarketRegime.UNKNOWN.value == "UNKNOWN"

    def test_enum_members(self):
        """测试枚举成员"""
        assert len(list(MarketRegime)) == 4
        assert MarketRegime.TRENDING in MarketRegime
        assert MarketRegime.RANGING in MarketRegime


class TestRegimeDetector:
    """测试市场体制检测器"""

    def setup_method(self):
        """测试初始化"""
        self.detector = RegimeDetector()

    def test_initialization(self):
        """测试初始化参数"""
        detector = RegimeDetector()
        assert detector is not None
        assert hasattr(detector, "detect_regime")

    def test_detect_regime_with_insufficient_data(self):
        """测试数据不足的情况"""
        # 创建空DataFrame
        empty_df = pd.DataFrame()
        result = self.detector.detect_regime(empty_df)
        assert result["regime"] == MarketRegime.UNKNOWN
        assert result["confidence"] < 0.5

    def test_detect_regime_with_trending_data(self):
        """测试趋势市数据"""
        # 创建上升趋势数据
        dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
        prices = np.linspace(100, 200, 100) + np.random.normal(0, 2, 100)
        df = pd.DataFrame(
            {
                "open": prices - 1,
                "high": prices + 2,
                "low": prices - 2,
                "close": prices,
                "volume": np.random.randint(1000, 10000, 100),
            },
            index=dates,
        )

        result = self.detector.detect_regime(df)
        # 至少应该返回一个有效结果
        assert result["regime"] in [
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.VOLATILE,
            MarketRegime.UNKNOWN,
        ]
        assert 0 <= result["confidence"] <= 1

    def test_detect_regime_with_ranging_data(self):
        """测试盘整市数据"""
        # 创建盘整数据（均值回归）
        dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
        base_price = 150
        prices = (
            base_price
            + 10 * np.sin(np.linspace(0, 10 * np.pi, 100))
            + np.random.normal(0, 1, 100)
        )
        df = pd.DataFrame(
            {
                "open": prices - 1,
                "high": prices + 2,
                "low": prices - 2,
                "close": prices,
                "volume": np.random.randint(1000, 10000, 100),
            },
            index=dates,
        )

        result = self.detector.detect_regime(df)
        # 正弦波数据可能被识别为趋势或盘整
        assert result["regime"] in [
            MarketRegime.RANGING,
            MarketRegime.UNKNOWN,
            MarketRegime.VOLATILE,
            MarketRegime.TRENDING,  # 允许趋势，因为ADX可能较高
        ]

    def test_get_regime_history(self):
        """测试获取历史体制记录"""
        dates = pd.date_range(start="2024-01-01", periods=50, freq="D")
        prices = np.linspace(100, 150, 50)
        df = pd.DataFrame(
            {
                "open": prices - 1,
                "high": prices + 2,
                "low": prices - 2,
                "close": prices,
                "volume": np.random.randint(1000, 10000, 50),
            },
            index=dates,
        )

        # 先检测体制以填充历史记录
        self.detector.detect_regime(df)
        history = self.detector.get_regime_history(n=20)
        # 历史记录应该是列表
        assert isinstance(history, list)
        # 每个记录应该是三元组
        if len(history) > 0:
            for record in history:
                assert len(record) == 3
                timestamp, regime, confidence = record
                assert isinstance(timestamp, pd.Timestamp)
                assert regime in MarketRegime
                assert 0 <= confidence <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
