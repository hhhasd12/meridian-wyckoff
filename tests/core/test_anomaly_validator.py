"""
异常数据验证模块单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.core.anomaly_validator import (
    AnomalyValidator,
    AnomalyEvent,
    AnomalyType,
    ValidationResult,
    CorrelationData,
)


class TestAnomalyValidator:
    """异常数据验证器测试类"""

    def setup_method(self):
        """测试前准备"""
        self.validator = AnomalyValidator(
            correlation_threshold=2.0,
            price_deviation_threshold=0.02,
            min_confidence=0.7,
        )

    def test_initialization(self):
        """测试初始化"""
        assert self.validator is not None
        assert self.validator.correlation_threshold == 2.0
        assert self.validator.price_deviation_threshold == 0.02
        assert self.validator.min_confidence == 0.7
        assert len(self.validator.correlation_pairs) > 0
        assert len(self.validator.major_exchanges) > 0

    def test_anomaly_event_creation(self):
        """测试异常事件创建"""
        anomaly = AnomalyEvent(
            anomaly_id="test_001",
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            price_change=0.05,
            volume_change=2.0,
            price=50000.0,
            volume=1000.0,
        )

        assert anomaly.anomaly_id == "test_001"
        assert anomaly.symbol == "BTC/USDT"
        assert anomaly.exchange == "binance"
        assert anomaly.price_change == 0.05
        assert anomaly.volume_change == 2.0
        assert anomaly.price == 50000.0
        assert anomaly.volume == 1000.0
        assert anomaly.anomaly_type == AnomalyType.UNKNOWN
        assert anomaly.validation_result == ValidationResult.INCONCLUSIVE
        assert anomaly.confidence == 0.0

    def test_correlation_data_creation(self):
        """测试相关性数据创建"""
        timestamp = datetime.now()
        corr_data = CorrelationData(
            symbol_pair="BTC/USDT-ETH/USDT",
            correlation_30d=0.85,
            correlation_7d=0.82,
            correlation_1d=0.78,
            current_deviation=1.2,
            is_breaking=False,
            timestamp=timestamp,
        )

        assert corr_data.symbol_pair == "BTC/USDT-ETH/USDT"
        assert corr_data.correlation_30d == 0.85
        assert corr_data.correlation_7d == 0.82
        assert corr_data.correlation_1d == 0.78
        assert corr_data.current_deviation == 1.2
        assert corr_data.is_breaking is False
        assert corr_data.timestamp == timestamp

    def test_validate_anomaly_without_data(self):
        """测试无数据验证"""
        anomaly = AnomalyEvent(
            anomaly_id="test_002",
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
        )

        validated = self.validator.validate_anomaly(anomaly)
        assert validated.validation_result == ValidationResult.NEED_MANUAL_REVIEW
        assert "缺乏验证数据" in str(validated.validation_details.get("reason", ""))

    def test_multi_exchange_consistency_check(self):
        """测试多交易所一致性检查"""
        anomaly = AnomalyEvent(
            anomaly_id="test_003",
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            price=50000.0,
        )

        # 创建模拟的多交易所数据
        multi_exchange_data = {
            "binance": pd.DataFrame(
                {"close": [49800, 49900, 50000]},
                index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
            ),
            "coinbase": pd.DataFrame(
                {"close": [49750, 49850, 49950]},
                index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
            ),
            "kraken": pd.DataFrame(
                {"close": [49820, 49920, 50020]},
                index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
            ),
        }

        score, evidence = self.validator._check_multi_exchange_consistency(
            anomaly, multi_exchange_data
        )

        assert 0 <= score <= 1
        assert len(evidence) > 0
        assert any("价格一致性" in e for e in evidence)

    def test_correlation_consistency_check(self):
        """测试相关性一致性检查"""
        anomaly = AnomalyEvent(
            anomaly_id="test_004",
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
        )

        # 创建模拟的相关性数据
        correlation_data = {
            "BTC/USDT-ETH/USDT": CorrelationData(
                symbol_pair="BTC/USDT-ETH/USDT",
                correlation_30d=0.85,
                correlation_7d=0.82,
                correlation_1d=0.78,
                current_deviation=1.2,
                is_breaking=False,
                timestamp=datetime.now(),
            )
        }

        score, evidence = self.validator._check_correlation_consistency(
            anomaly, correlation_data
        )

        assert 0 <= score <= 1
        assert len(evidence) > 0
        assert any("相关性" in e for e in evidence)

    def test_analyze_anomaly_features(self):
        """测试异常特征分析"""
        anomaly = AnomalyEvent(
            anomaly_id="test_005",
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            price_change=0.08,
            volume_change=4.2,
            order_book_imbalance=0.25,
        )

        score, evidence = self.validator._analyze_anomaly_features(anomaly)

        assert 0 <= score <= 1
        assert len(evidence) > 0
        assert any("价格波动" in e for e in evidence) or any(
            "成交量" in e for e in evidence
        )

    def test_calculate_correlation(self):
        """测试相关性计算"""
        # 创建测试数据
        dates = pd.date_range(start="2024-01-01", periods=50, freq="D")

        # 创建两个高度相关的资产
        base_prices = np.linspace(100, 150, 50)
        symbol1_prices = base_prices + np.random.normal(0, 2, 50)
        symbol2_prices = base_prices + np.random.normal(0, 2, 50)

        symbol1_df = pd.DataFrame(
            {"close": symbol1_prices},
            index=dates,
        )
        symbol1_df.name = "BTC/USDT"

        symbol2_df = pd.DataFrame(
            {"close": symbol2_prices},
            index=dates,
        )
        symbol2_df.name = "ETH/USDT"

        # 计算相关性
        corr_data = self.validator.calculate_correlation(symbol1_df, symbol2_df)

        assert corr_data.symbol_pair == "BTC/USDT-ETH/USDT"
        assert -1 <= corr_data.correlation_30d <= 1
        assert -1 <= corr_data.correlation_7d <= 1
        # correlation_1d 只有1个数据点时为 NaN，允许
        assert np.isnan(corr_data.correlation_1d) or -1 <= corr_data.correlation_1d <= 1
        assert isinstance(float(corr_data.current_deviation), float)
        assert isinstance(bool(corr_data.is_breaking), bool)
        assert isinstance(corr_data.timestamp, datetime)

    def test_full_validation_workflow(self):
        """测试完整验证流程"""
        # 创建异常事件
        anomaly = AnomalyEvent(
            anomaly_id="test_006",
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            price_change=0.08,
            volume_change=4.2,
            price=45000.0,
            volume=1200.0,
        )

        # 创建模拟的多交易所数据
        multi_exchange_data = {
            "binance": pd.DataFrame(
                {"close": [44800, 44900, 45000]},
                index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
            ),
            "coinbase": pd.DataFrame(
                {"close": [44750, 44850, 44950]},
                index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
            ),
            "kraken": pd.DataFrame(
                {"close": [44820, 44920, 45020]},
                index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
            ),
        }

        # 创建模拟的相关性数据
        correlation_data = {
            "BTC/USDT-ETH/USDT": CorrelationData(
                symbol_pair="BTC/USDT-ETH/USDT",
                correlation_30d=0.85,
                correlation_7d=0.82,
                correlation_1d=0.78,
                current_deviation=1.2,
                is_breaking=False,
                timestamp=datetime.now(),
            )
        }

        # 执行验证
        validated_anomaly = self.validator.validate_anomaly(
            anomaly, multi_exchange_data, correlation_data
        )

        # 验证结果
        assert validated_anomaly.anomaly_id == "test_006"
        assert validated_anomaly.validation_result in [
            ValidationResult.CONFIRMED,
            ValidationResult.REJECTED,
            ValidationResult.INCONCLUSIVE,
            ValidationResult.NEED_MANUAL_REVIEW,
        ]
        assert 0 <= validated_anomaly.confidence <= 1
        assert validated_anomaly.validation_details is not None
        assert "scores" in validated_anomaly.validation_details
        assert "evidence" in validated_anomaly.validation_details

    def test_time_alignment_in_correlation_check(self):
        """测试相关性检查中的时间对齐"""
        current_time = datetime.now()
        old_time = current_time - timedelta(days=2)  # 2天前

        anomaly = AnomalyEvent(
            anomaly_id="test_007",
            timestamp=current_time,
            symbol="BTC/USDT",
            exchange="binance",
        )

        # 创建过时的相关性数据
        correlation_data = {
            "BTC/USDT-ETH/USDT": CorrelationData(
                symbol_pair="BTC/USDT-ETH/USDT",
                correlation_30d=0.85,
                correlation_7d=0.82,
                correlation_1d=0.78,
                current_deviation=1.2,
                is_breaking=False,
                timestamp=old_time,
            )
        }

        score, evidence = self.validator._check_correlation_consistency(
            anomaly, correlation_data
        )

        assert 0 <= score <= 1
        # 应该包含时间过时的警告
        assert any("过时" in e for e in evidence) or any(
            "时间差" in e for e in evidence
        )

    def test_edge_cases(self):
        """测试边界情况"""
        # 测试无价格数据
        anomaly = AnomalyEvent(
            anomaly_id="test_008",
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            price=None,
        )

        multi_exchange_data = {
            "binance": pd.DataFrame(
                {"close": [50000]},
                index=pd.date_range(end=datetime.now(), periods=1, freq="1h"),
            ),
        }

        score, evidence = self.validator._check_multi_exchange_consistency(
            anomaly, multi_exchange_data
        )
        assert score == 0.5
        assert any("价格缺失" in e for e in evidence)

        # 测试无相关资产数据
        anomaly = AnomalyEvent(
            anomaly_id="test_009",
            timestamp=datetime.now(),
            symbol="UNKNOWN/USDT",  # 不在相关资产对中
            exchange="binance",
        )

        correlation_data = {}
        score, evidence = self.validator._check_correlation_consistency(
            anomaly, correlation_data
        )
        assert score == 0.5
        assert any("无相关资产数据" in e for e in evidence)


if __name__ == "__main__":
    # 运行测试
    test = TestAnomalyValidator()
    test.setup_method()

    print("=== 异常数据验证模块单元测试 ===")

    tests = [
        test.test_initialization,
        test.test_anomaly_event_creation,
        test.test_correlation_data_creation,
        test.test_validate_anomaly_without_data,
        test.test_multi_exchange_consistency_check,
        test.test_correlation_consistency_check,
        test.test_analyze_anomaly_features,
        test.test_calculate_correlation,
        test.test_full_validation_workflow,
        test.test_time_alignment_in_correlation_check,
        test.test_edge_cases,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            print(f"✅ {test_func.__name__}: 通过")
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__}: 失败 - {str(e)}")
            failed += 1

    print(f"\n=== 测试结果 ===")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"总计: {passed + failed}")

    if failed == 0:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  有测试失败，请检查代码")
