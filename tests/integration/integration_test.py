"""
集成测试 - 测试所有核心模块的导入和基本功能
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime


def test_module_imports():
    """测试所有核心模块能否正确导入"""
    # 1. 市场体制模块
    from src.plugins.market_regime import MarketRegime, RegimeDetector

    assert MarketRegime is not None
    assert RegimeDetector is not None

    # 2. 曲线边界拟合模块
    from src.plugins.pattern_detection.curve_boundary import (
        CurveBoundaryFitter,
        BoundaryType,
    )

    assert CurveBoundaryFitter is not None
    assert BoundaryType is not None

    # 3. 突破验证器模块
    from src.plugins.signal_validation.breakout_validator import (
        BreakoutValidator,
        BreakoutStatus,
    )

    assert BreakoutValidator is not None
    assert BreakoutStatus is not None

    # 4. 数据管道模块
    from src.plugins.data_pipeline.data_pipeline import (
        DataPipeline,
        DataSource,
        Timeframe,
    )

    assert DataPipeline is not None
    assert DataSource is not None
    assert Timeframe is not None

    # 5. TR识别器模块
    from src.plugins.pattern_detection.tr_detector import (
        TRDetector,
        TRStatus,
        TradingRange,
    )

    assert TRDetector is not None
    assert TRStatus is not None
    assert TradingRange is not None

    # 6. 异常数据验证模块
    from src.plugins.risk_management.anomaly_validator import (
        AnomalyValidator,
        AnomalyType,
        ValidationResult,
    )

    assert AnomalyValidator is not None
    assert AnomalyType is not None
    assert ValidationResult is not None

    # 7. 熔断机制模块
    from src.plugins.risk_management.circuit_breaker import (
        CircuitBreaker,
        CircuitBreakerStatus,
        TripReason,
    )

    assert CircuitBreaker is not None
    assert CircuitBreakerStatus is not None
    assert TripReason is not None

    # 8. FVG检测引擎
    from src.perception.fvg_detector import FVGDetector, FVGStatus, FVGDirection

    assert FVGDetector is not None
    assert FVGStatus is not None
    assert FVGDirection is not None

    # 9. 可视化调试面板
    from src.plugins.agent_teams.visualization.heritage_panel import HeritageVisualizer

    assert HeritageVisualizer is not None

    print("[OK] 所有模块导入成功")


def test_basic_instantiation():
    """测试所有类的实例化"""
    # 创建测试数据
    dates = pd.date_range(start="2024-01-01", periods=50, freq="D")
    prices = np.linspace(100, 150, 50)
    test_df = pd.DataFrame(
        {
            "open": prices - 1,
            "high": prices + 2,
            "low": prices - 2,
            "close": prices,
            "volume": np.random.randint(1000, 10000, 50),
        },
        index=dates,
    )

    # 1. 市场体制检测器
    from src.plugins.market_regime import RegimeDetector

    detector = RegimeDetector()
    assert detector is not None

    # 2. 曲线边界拟合器
    from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter

    fitter = CurveBoundaryFitter()
    assert fitter is not None

    # 3. 突破验证器
    from src.plugins.signal_validation.breakout_validator import BreakoutValidator

    validator = BreakoutValidator()
    assert validator is not None

    # 4. TR识别器
    from src.plugins.pattern_detection.tr_detector import TRDetector

    tr_detector = TRDetector()
    assert tr_detector is not None

    # 5. 异常数据验证器
    from src.plugins.risk_management.anomaly_validator import AnomalyValidator

    anomaly_validator = AnomalyValidator()
    assert anomaly_validator is not None

    # 6. 熔断器
    from src.plugins.risk_management.circuit_breaker import CircuitBreaker

    circuit_breaker = CircuitBreaker()
    assert circuit_breaker is not None

    # 7. FVG检测器
    from src.perception.fvg_detector import FVGDetector

    fvg_detector = FVGDetector()
    assert fvg_detector is not None

    # 8. 可视化面板（不依赖数据）
    from src.plugins.agent_teams.visualization.heritage_panel import HeritageVisualizer

    panel = HeritageVisualizer()
    assert panel is not None

    print("[OK] 所有类实例化成功")


def test_basic_functionality():
    """测试基本功能（不涉及复杂计算）"""
    # 测试市场体制检测器的基本方法
    from src.plugins.market_regime import RegimeDetector

    detector = RegimeDetector()

    # 创建最小测试数据
    dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
    prices = np.array([100, 101, 102, 101, 102, 103, 104, 103, 104, 105])
    test_df = pd.DataFrame(
        {
            "open": prices - 0.5,
            "high": prices + 0.5,
            "low": prices - 0.5,
            "close": prices,
            "volume": np.ones(10) * 1000,
        },
        index=dates,
    )

    # 测试检测方法
    result = detector.detect_regime(test_df)
    assert "regime" in result
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1

    # 测试异常验证器的基本方法
    from src.plugins.risk_management.anomaly_validator import (
        AnomalyValidator,
        AnomalyEvent,
    )
    from datetime import datetime

    anomaly_validator = AnomalyValidator()
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

    validated = anomaly_validator.validate_anomaly(anomaly)
    assert hasattr(validated, "validation_result")
    assert hasattr(validated, "confidence")

    print("[OK] 基本功能测试通过")


if __name__ == "__main__":
    # 运行测试
    test_module_imports()
    test_basic_instantiation()
    test_basic_functionality()
    print("\n[SUCCESS] 集成测试全部通过！")
