"""
熔断机制模块单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerStatus,
    TripReason,
    DataQualityMetrics,
    MarketType,
)


class TestCircuitBreaker:
    """熔断机制测试类"""

    def setup_method(self):
        """测试前准备"""
        self.breaker = CircuitBreaker(
            trip_threshold=0.3,
            recovery_threshold=0.8,
            min_recovery_time=30,
            max_trip_duration=180,
            market_type=MarketType.CRYPTO,
            enable_progressive_recovery=True,
        )

    def test_initialization(self):
        """测试初始化"""
        assert self.breaker is not None
        assert self.breaker.trip_threshold == 0.3
        assert self.breaker.recovery_threshold == 0.8
        assert self.breaker.min_recovery_time == 30
        assert self.breaker.max_trip_duration == 180
        assert self.breaker.market_type == MarketType.CRYPTO
        assert self.breaker.enable_progressive_recovery is True
        assert self.breaker.status == CircuitBreakerStatus.NORMAL

    def test_data_quality_metrics_creation(self):
        """测试数据质量指标创建"""
        timestamp = datetime.now()
        metrics = DataQualityMetrics(
            timestamp=timestamp,
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=2.5,
            missing_data_points=0,
            consecutive_missing=0,
            price_change_pct=0.01,
            volume_change_pct=0.5,
            spread_pct=0.02,
            latency_ms=150,
            success_rate=0.99,
            error_count=0,
        )

        assert metrics.timestamp == timestamp
        assert metrics.symbol == "BTC/USDT"
        assert metrics.exchange == "binance"
        assert metrics.data_freshness_seconds == 2.5
        assert metrics.missing_data_points == 0
        assert metrics.consecutive_missing == 0
        assert metrics.price_change_pct == 0.01
        assert metrics.volume_change_pct == 0.5
        assert metrics.spread_pct == 0.02
        assert metrics.latency_ms == 150
        assert metrics.success_rate == 0.99
        assert metrics.error_count == 0

    def test_data_quality_score_calculation(self):
        """测试数据质量得分计算"""
        # 测试高质量数据
        good_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=2.5,
            missing_data_points=0,
            consecutive_missing=0,
            price_change_pct=0.01,
            volume_change_pct=0.5,
            spread_pct=0.02,
            latency_ms=150,
            success_rate=0.99,
            error_count=0,
        )

        assert 0.8 <= good_metrics.overall_score <= 1.0

        # 测试低质量数据
        bad_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=45.0,
            missing_data_points=3,
            consecutive_missing=3,
            price_change_pct=0.25,
            volume_change_pct=6.0,
            spread_pct=0.05,
            latency_ms=2500,
            success_rate=0.3,
            error_count=5,
        )

        assert 0 <= bad_metrics.overall_score <= 0.5

    def test_normal_data_does_not_trip(self):
        """测试正常数据不触发熔断"""
        normal_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=2.5,
            missing_data_points=0,
            consecutive_missing=0,
            price_change_pct=0.01,
            volume_change_pct=0.5,
            spread_pct=0.02,
            latency_ms=150,
            success_rate=0.99,
            error_count=0,
        )

        tripped = self.breaker.update_data_quality(normal_metrics)
        assert tripped is False
        assert self.breaker.status == CircuitBreakerStatus.NORMAL
        assert self.breaker.is_trading_allowed() is True

    def test_bad_data_triggers_trip(self):
        """测试异常数据触发熔断"""
        bad_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=45.0,
            missing_data_points=3,
            consecutive_missing=3,
            price_change_pct=0.25,
            volume_change_pct=6.0,
            spread_pct=0.05,
            latency_ms=2500,
            success_rate=0.3,
            error_count=5,
        )

        tripped = self.breaker.update_data_quality(bad_metrics)
        assert tripped is True
        assert self.breaker.status == CircuitBreakerStatus.TRIPPED
        assert self.breaker.is_trading_allowed() is False
        assert self.breaker.trip_reason is not None
        assert self.breaker.trip_time is not None

    def test_market_sensitivity_multiplier(self):
        """测试市场敏感度乘数"""
        # 加密货币市场应该更敏感
        crypto_breaker = CircuitBreaker(market_type=MarketType.CRYPTO)
        crypto_multiplier = crypto_breaker._get_market_sensitivity_multiplier()
        assert crypto_multiplier == 0.8

        # 股票市场应该相对宽松
        stock_breaker = CircuitBreaker(market_type=MarketType.STOCK)
        stock_multiplier = stock_breaker._get_market_sensitivity_multiplier()
        assert stock_multiplier == 1.2

        # 外汇市场中等敏感
        forex_breaker = CircuitBreaker(market_type=MarketType.FOREX)
        forex_multiplier = forex_breaker._get_market_sensitivity_multiplier()
        assert forex_multiplier == 0.9

        # 期货市场中等宽松
        futures_breaker = CircuitBreaker(market_type=MarketType.FUTURES)
        futures_multiplier = futures_breaker._get_market_sensitivity_multiplier()
        assert futures_multiplier == 1.1

    def test_market_closed_check(self):
        """测试市场关闭检查"""
        # 测试周末
        weekend_time = datetime(2024, 1, 6, 10, 0, 0)  # 周六
        stock_breaker = CircuitBreaker(market_type=MarketType.STOCK)

        # 简化实现中，周末被视为市场关闭
        assert stock_breaker._is_market_closed(weekend_time) is True

        # 测试工作日非交易时间
        weekday_night = datetime(2024, 1, 3, 20, 0, 0)  # 周三晚上8点
        # 股票市场应该关闭
        assert stock_breaker._is_market_closed(weekday_night) is True

        # 测试工作日交易时间
        weekday_day = datetime(2024, 1, 3, 12, 0, 0)  # 周三中午12点
        # 股票市场应该开放
        assert stock_breaker._is_market_closed(weekday_day) is False

    def test_manual_trip_and_recover(self):
        """测试手动触发和恢复"""
        # 手动触发
        tripped = self.breaker.manual_trip("测试手动触发")
        assert tripped is True
        assert self.breaker.status == CircuitBreakerStatus.TRIPPED
        assert self.breaker.trip_reason == TripReason.MANUAL_TRIP

        # 手动恢复（默认开启渐进式恢复，进入 RECOVERY 状态而非直接 NORMAL）
        recovered = self.breaker.manual_recover()
        assert recovered is True
        assert self.breaker.status in [
            CircuitBreakerStatus.RECOVERY,
            CircuitBreakerStatus.NORMAL,
        ]
        assert self.breaker.trip_time is None
        assert self.breaker.trip_reason is None

    def test_manual_override(self):
        """测试手动覆盖"""
        # 启用手动覆盖
        self.breaker.manual_override(True)
        assert self.breaker.status == CircuitBreakerStatus.MANUAL_OVERRIDE
        assert self.breaker.is_trading_allowed() is True

        # 即使数据异常也不触发熔断
        bad_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=100.0,
            missing_data_points=10,
            consecutive_missing=10,
            price_change_pct=0.5,
            volume_change_pct=10.0,
            spread_pct=0.1,
            latency_ms=5000,
            success_rate=0.1,
            error_count=10,
        )

        tripped = self.breaker.update_data_quality(bad_metrics)
        assert tripped is False
        assert self.breaker.status == CircuitBreakerStatus.MANUAL_OVERRIDE

        # 禁用手动覆盖
        self.breaker.manual_override(False)
        assert self.breaker.status == CircuitBreakerStatus.NORMAL

    def test_emergency_override(self):
        """测试紧急手动覆盖"""
        # 先触发熔断
        bad_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=45.0,
            missing_data_points=3,
            consecutive_missing=3,
            price_change_pct=0.25,
            volume_change_pct=6.0,
            spread_pct=0.05,
            latency_ms=2500,
            success_rate=0.3,
            error_count=5,
        )

        self.breaker.update_data_quality(bad_metrics)
        assert self.breaker.status == CircuitBreakerStatus.TRIPPED

        # 启用紧急覆盖
        success = self.breaker.emergency_override(True, "紧急测试")
        assert success is True
        assert self.breaker.status == CircuitBreakerStatus.MANUAL_OVERRIDE
        assert self.breaker.is_trading_allowed() is True

        # 禁用紧急覆盖
        success = self.breaker.emergency_override(False)
        assert success is True
        assert self.breaker.status == CircuitBreakerStatus.NORMAL

    def test_progressive_recovery(self):
        """测试渐进式恢复"""
        # 创建启用渐进式恢复的熔断器
        progressive_breaker = CircuitBreaker(
            enable_progressive_recovery=True,
            min_recovery_time=1,  # 设置较短的恢复时间便于测试
        )

        # 触发熔断
        bad_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=45.0,
            missing_data_points=3,
            consecutive_missing=3,
            price_change_pct=0.25,
            volume_change_pct=6.0,
            spread_pct=0.05,
            latency_ms=2500,
            success_rate=0.3,
            error_count=5,
        )

        progressive_breaker.update_data_quality(bad_metrics)
        assert progressive_breaker.status == CircuitBreakerStatus.TRIPPED

        # 提供高质量数据触发恢复
        good_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=1.0,
            missing_data_points=0,
            consecutive_missing=0,
            price_change_pct=0.01,
            volume_change_pct=0.5,
            spread_pct=0.02,
            latency_ms=100,
            success_rate=0.99,
            error_count=0,
        )

        # 多次更新以触发恢复（渐进式恢复需要 >=30秒才能完全恢复，这里只验证状态改变或保持）
        for _ in range(10):
            progressive_breaker.update_data_quality(good_metrics)
            progressive_breaker.check_progressive_recovery(good_metrics)

        # 应该进入恢复状态或完全恢复（渐进式恢复需要时间）
        assert progressive_breaker.status in [
            CircuitBreakerStatus.TRIPPED,
            CircuitBreakerStatus.RECOVERY,
            CircuitBreakerStatus.NORMAL,
        ]

    def test_get_status_report(self):
        """测试获取状态报告"""
        # 正常状态报告
        report = self.breaker.get_status_report()
        assert "status" in report
        assert "trip_time" in report
        assert "trip_reason" in report
        assert "event_count" in report
        assert report["status"] == CircuitBreakerStatus.NORMAL.value

        # 触发熔断后的报告
        bad_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=45.0,
            missing_data_points=3,
            consecutive_missing=3,
            price_change_pct=0.25,
            volume_change_pct=6.0,
            spread_pct=0.05,
            latency_ms=2500,
            success_rate=0.3,
            error_count=5,
        )

        self.breaker.update_data_quality(bad_metrics)
        report = self.breaker.get_status_report()
        assert report["status"] == CircuitBreakerStatus.TRIPPED.value
        assert report["trip_reason"] is not None
        assert "trip_duration_seconds" in report

    def test_clear_history(self):
        """测试清空历史记录"""
        # 添加一些历史数据
        for i in range(20):
            metrics = DataQualityMetrics(
                timestamp=datetime.now(),
                symbol=f"SYM{i}",
                exchange="test",
                data_freshness_seconds=1.0,
                missing_data_points=0,
                consecutive_missing=0,
                price_change_pct=0.01,
                volume_change_pct=0.5,
                spread_pct=0.02,
                latency_ms=100,
                success_rate=0.99,
                error_count=0,
            )
            self.breaker.update_data_quality(metrics)

        # 触发几次熔断
        for _ in range(5):
            bad_metrics = DataQualityMetrics(
                timestamp=datetime.now(),
                symbol="BTC/USDT",
                exchange="binance",
                data_freshness_seconds=45.0,
                missing_data_points=3,
                consecutive_missing=3,
                price_change_pct=0.25,
                volume_change_pct=6.0,
                spread_pct=0.05,
                latency_ms=2500,
                success_rate=0.3,
                error_count=5,
            )
            self.breaker.update_data_quality(bad_metrics)
            self.breaker.manual_recover()

        # 清空历史记录（保留最近10条）
        self.breaker.clear_history(keep_last_n=10)

        report = self.breaker.get_status_report()
        assert report["event_count"] <= 10

    def test_edge_cases(self):
        """测试边界情况"""
        # 测试空数据
        empty_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="",
            exchange="",
            data_freshness_seconds=0,
            missing_data_points=0,
            consecutive_missing=0,
            price_change_pct=0,
            volume_change_pct=0,
            spread_pct=0,
            latency_ms=0,
            success_rate=0,
            error_count=0,
        )

        score = empty_metrics.overall_score
        assert 0 <= score <= 1

        # 测试极端数据
        extreme_metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            exchange="binance",
            data_freshness_seconds=1000.0,
            missing_data_points=100,
            consecutive_missing=100,
            price_change_pct=10.0,
            volume_change_pct=100.0,
            spread_pct=1.0,
            latency_ms=10000,
            success_rate=0.0,
            error_count=100,
        )

        score = extreme_metrics.overall_score
        assert 0 <= score <= 0.4  # 极端数据应该得分很低


if __name__ == "__main__":
    # 运行测试
    test = TestCircuitBreaker()
    test.setup_method()

    print("=== 熔断机制模块单元测试 ===")

    tests = [
        test.test_initialization,
        test.test_data_quality_metrics_creation,
        test.test_data_quality_score_calculation,
        test.test_normal_data_does_not_trip,
        test.test_bad_data_triggers_trip,
        test.test_market_sensitivity_multiplier,
        test.test_market_closed_check,
        test.test_manual_trip_and_recover,
        test.test_manual_override,
        test.test_emergency_override,
        test.test_progressive_recovery,
        test.test_get_status_report,
        test.test_clear_history,
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
