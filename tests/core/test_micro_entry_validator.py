"""
微观入场验证器单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.plugins.signal_validation.micro_entry_validator import (
    MicroEntryValidator,
    EntrySignalType,
    StructureType,
)


class TestMicroEntryValidator:
    """测试微观入场验证器"""

    def test_initialization(self):
        """测试初始化"""
        validator = MicroEntryValidator()
        assert validator is not None
        assert validator.min_confirmation_bars == 3
        assert validator.volume_threshold == 1.5
        assert validator.max_slippage_pct == 0.001
        assert validator.require_alignment is True
        assert len(validator.validation_history) == 0

    def test_create_sample_data(self):
        """创建测试数据"""
        # 创建模拟M15数据
        dates = pd.date_range(start="2024-01-20", periods=20, freq="15min")
        base_price = 45000.0
        np.random.seed(42)
        prices = base_price + np.random.normal(0, 100, 20)
        volumes = np.random.randint(1000, 5000, 20)

        m15_data = pd.DataFrame(
            {
                "open": prices - 10,
                "high": prices + 20,
                "low": prices - 20,
                "close": prices,
                "volume": volumes,
            },
            index=dates,
        )

        # 创建模拟H4结构
        h4_structure = {
            "type": "CREEK",
            "price_level": 45500.0,
            "direction": "RESISTANCE",
            "confidence": 0.8,
            "timestamp": datetime.now().isoformat(),
        }

        return h4_structure, m15_data

    def test_validate_h4_structure_valid(self):
        """测试有效的H4结构验证"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
            "confidence": 0.8,
            "timestamp": datetime.now().isoformat(),
        }

        valid, reason = validator._validate_h4_structure(h4_structure)
        assert valid is True
        assert reason == "H4结构有效"

    def test_validate_h4_structure_invalid_type(self):
        """测试无效结构类型"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "INVALID_TYPE",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
            "confidence": 0.8,
        }

        valid, reason = validator._validate_h4_structure(h4_structure)
        assert valid is False
        assert "不支持的结构类型" in reason

    def test_validate_h4_structure_low_confidence(self):
        """测试低置信度结构"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
            "confidence": 0.4,  # 低于0.6
        }

        valid, reason = validator._validate_h4_structure(h4_structure)
        assert valid is False
        assert "结构置信度不足" in reason

    def test_validate_breakout_confirmation_resistance(self):
        """测试阻力位突破确认"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
        }

        # 创建模拟数据：价格突破阻力位并站稳
        dates = pd.date_range(start="2024-01-20", periods=10, freq="15min")
        # 前7根K线在阻力位之下
        prices_before = 44900.0 + np.random.normal(0, 50, 7)
        # 第8根K线突破
        prices_breakout = np.array([45100.0, 45050.0, 45020.0])  # 突破后站稳
        prices = np.concatenate([prices_before, prices_breakout])

        m15_data = pd.DataFrame(
            {
                "open": prices - 10,
                "high": prices + 20,
                "low": prices - 20,
                "close": prices,
                "volume": np.random.randint(1000, 5000, 10),
            },
            index=dates,
        )

        valid, details = validator._validate_breakout_confirmation(
            h4_structure, m15_data
        )
        assert valid is True
        assert details["breakout_type"] == "RESISTANCE_BREAKOUT"
        assert details["confirmation_bars"] >= validator.min_confirmation_bars

    def test_validate_breakout_confirmation_support(self):
        """测试支撑位突破确认（做空）"""
        validator = MicroEntryValidator()

        h4_structure = {"type": "ICE", "price_level": 45000.0, "direction": "SUPPORT"}

        # 创建模拟数据：价格跌破支撑位并站稳
        dates = pd.date_range(start="2024-01-20", periods=10, freq="15min")
        # 前7根K线在支撑位之上
        prices_before = 45100.0 + np.random.normal(0, 50, 7)
        # 第8根K线跌破
        prices_breakout = np.array([44900.0, 44950.0, 44980.0])  # 跌破后站稳
        prices = np.concatenate([prices_before, prices_breakout])

        m15_data = pd.DataFrame(
            {
                "open": prices - 10,
                "high": prices + 20,
                "low": prices - 20,
                "close": prices,
                "volume": np.random.randint(1000, 5000, 10),
            },
            index=dates,
        )

        valid, details = validator._validate_breakout_confirmation(
            h4_structure, m15_data
        )
        assert valid is True
        assert details["breakout_type"] == "SUPPORT_BREAKOUT"
        assert details["confirmation_bars"] >= validator.min_confirmation_bars

    def test_validate_breakout_confirmation_insufficient_data(self):
        """测试数据不足"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
        }

        # 数据不足
        dates = pd.date_range(start="2024-01-20", periods=2, freq="15min")
        m15_data = pd.DataFrame(
            {
                "open": [44900, 44950],
                "high": [44920, 44970],
                "low": [44880, 44930],
                "close": [44900, 44950],
                "volume": [1000, 1200],
            },
            index=dates,
        )

        valid, details = validator._validate_breakout_confirmation(
            h4_structure, m15_data
        )
        assert valid is False
        assert "数据不足" in details["reason"]

    def test_analyze_volume_health(self):
        """测试成交量健康度分析"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
        }

        # 创建模拟数据
        dates = pd.date_range(start="2024-01-20", periods=25, freq="15min")
        # 正常成交量（21个）
        normal_volumes = np.random.randint(1000, 2000, 21)
        # 突破放量（1个）
        breakout_volume = 4000  # 2倍平均
        # 确认期缩量（3个）
        confirmation_volumes = np.random.randint(800, 1500, 3)

        volumes = np.concatenate(
            [normal_volumes, [breakout_volume], confirmation_volumes]
        )
        prices = 44900.0 + np.random.normal(0, 100, 25)

        m15_data = pd.DataFrame(
            {
                "open": prices - 10,
                "high": prices + 20,
                "low": prices - 20,
                "close": prices,
                "volume": volumes,
            },
            index=dates,
        )

        breakout_details = {
            "breakout_type": "RESISTANCE_BREAKOUT",
            "confirmation_bars": 3,
        }

        valid, analysis = validator._analyze_volume_health(
            h4_structure, m15_data, breakout_details
        )
        assert valid is True
        assert analysis["volume_healthy"] is True
        assert analysis["breakout_volume_ratio"] > 1.0

    def test_analyze_micro_wyckoff(self):
        """测试微观威科夫结构分析"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
        }

        # 创建模拟数据
        dates = pd.date_range(start="2024-01-20", periods=15, freq="15min")
        # 模拟弹簧形态：价格快速跌破后收回
        prices = 44900.0 + np.random.normal(0, 50, 15)
        # 手动创建弹簧形态
        prices[10] = 44800.0  # 低点
        prices[11] = 44950.0  # 快速收回

        m15_data = pd.DataFrame(
            {
                "open": prices - 10,
                "high": prices + 20,
                "low": prices - 20,
                "close": prices,
                "volume": np.random.randint(1000, 5000, 15),
            },
            index=dates,
        )

        valid, analysis = validator._analyze_micro_wyckoff(
            h4_structure, m15_data, None, "BULLISH"
        )

        assert "wyckoff_score" in analysis
        assert 0.0 <= analysis["wyckoff_score"] <= 1.0
        assert "spring_detected" in analysis
        assert "test_detected" in analysis
        assert "lps_detected" in analysis

    def test_validate_timeframe_alignment(self):
        """测试时间框架对齐验证"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
        }

        # 创建模拟数据
        dates = pd.date_range(start="2024-01-20", periods=10, freq="15min")
        m15_data = pd.DataFrame(
            {
                "open": np.ones(10) * 44900,
                "high": np.ones(10) * 44920,
                "low": np.ones(10) * 44880,
                "close": np.ones(10) * 44900,
                "volume": np.random.randint(1000, 2000, 10),
            },
            index=dates,
        )

        market_context = {"regime": "TRENDING"}

        aligned, analysis = validator._validate_timeframe_alignment(
            "BULLISH", h4_structure, m15_data, market_context
        )

        assert "alignment_score" in analysis
        assert "reasons" in analysis
        assert "aligned" in analysis
        assert analysis["aligned"] == aligned

    def test_calculate_overall_score(self):
        """测试综合评分计算"""
        validator = MicroEntryValidator()

        breakout_analysis = {"confirmation_bars": 3}

        volume_analysis = {"volume_healthy": True}

        wyckoff_analysis = {"wyckoff_score": 0.7}

        alignment_valid = True

        score = validator._calculate_overall_score(
            breakout_analysis, volume_analysis, wyckoff_analysis, alignment_valid
        )

        assert 0.0 <= score <= 1.0
        # 理想情况应得高分
        assert score > 0.6

    def test_generate_entry_parameters_long(self):
        """测试做多入场参数生成"""
        validator = MicroEntryValidator()

        h4_structure = {
            "type": "CREEK",
            "price_level": 45000.0,
            "direction": "RESISTANCE",
        }

        # 创建模拟数据
        dates = pd.date_range(start="2024-01-20", periods=10, freq="15min")
        m15_data = pd.DataFrame(
            {
                "open": np.ones(10) * 45050,
                "high": np.ones(10) * 45070,
                "low": np.ones(10) * 45030,
                "close": np.ones(10) * 45050,
                "volume": np.random.randint(1000, 2000, 10),
            },
            index=dates,
        )

        params = validator._generate_entry_parameters(
            h4_structure, m15_data, None, 0.8, EntrySignalType.CONFIRMED_ENTRY
        )

        assert params["entry_direction"] == "LONG"
        assert params["entry_price"] == 45050.0
        assert params["stop_loss"] < params["entry_price"]  # 做多止损低于入场价
        assert params["take_profit"] > params["entry_price"]  # 做多止盈高于入场价
        assert params["position_size_multiplier"] > 0
        assert params["risk_multiplier"] > 0
        assert params["risk_reward_ratio"] > 0

    def test_generate_entry_parameters_short(self):
        """测试做空入场参数生成"""
        validator = MicroEntryValidator()

        h4_structure = {"type": "ICE", "price_level": 45000.0, "direction": "SUPPORT"}

        # 创建模拟数据
        dates = pd.date_range(start="2024-01-20", periods=10, freq="15min")
        m15_data = pd.DataFrame(
            {
                "open": np.ones(10) * 44950,
                "high": np.ones(10) * 44970,
                "low": np.ones(10) * 44930,
                "close": np.ones(10) * 44950,
                "volume": np.random.randint(1000, 2000, 10),
            },
            index=dates,
        )

        params = validator._generate_entry_parameters(
            h4_structure, m15_data, None, 0.8, EntrySignalType.CONFIRMED_ENTRY
        )

        assert params["entry_direction"] == "SHORT"
        assert params["entry_price"] == 44950.0
        assert params["stop_loss"] > params["entry_price"]  # 做空止损高于入场价
        assert params["take_profit"] < params["entry_price"]  # 做空止盈低于入场价

    def test_full_validation_process(self):
        """测试完整验证流程"""
        validator = MicroEntryValidator()

        # 准备测试数据
        h4_structure, m15_data = self.test_create_sample_data()

        # 调整数据以模拟成功突破
        m15_data.loc[m15_data.index[-1], "high"] = 45600.0  # 突破阻力位
        m15_data.loc[m15_data.index[-1], "close"] = 45550.0
        m15_data.loc[m15_data.index[-1], "volume"] = 8000  # 放量

        # 前几根K线也调整以模拟站稳
        for i in range(1, 4):
            m15_data.loc[m15_data.index[-i], "close"] = 45500.0 + i * 10

        # 市场上下文
        market_context = {"regime": "TRENDING", "timestamp": datetime.now().isoformat()}

        # 执行验证
        result = validator.validate_entry(
            h4_structure=h4_structure,
            m15_data=m15_data,
            m5_data=None,
            macro_bias="BULLISH",
            market_context=market_context,
        )

        # 验证结果结构
        assert "signal_type" in result
        assert "signal_reason" in result
        assert "overall_score" in result
        assert "entry_parameters" in result
        assert "validation_timestamp" in result

        # 信号类型应为某种入场信号
        assert result["signal_type"] in [
            EntrySignalType.AGGRESSIVE_ENTRY.value,
            EntrySignalType.CONFIRMED_ENTRY.value,
            EntrySignalType.REJECTED.value,
            EntrySignalType.DEFERRED.value,
        ]

    def test_validation_history(self):
        """测试验证历史记录"""
        validator = MicroEntryValidator()

        # 执行几次验证
        h4_structure, m15_data = self.test_create_sample_data()
        market_context = {"regime": "TRENDING", "timestamp": datetime.now().isoformat()}

        # 第一次验证
        result1 = validator.validate_entry(
            h4_structure, m15_data, None, "BULLISH", market_context
        )

        # 修改数据，第二次验证
        m15_data2 = m15_data.copy()
        m15_data2.loc[m15_data2.index[-1], "close"] = 44000.0  # 未突破

        result2 = validator.validate_entry(
            h4_structure, m15_data2, None, "BULLISH", market_context
        )

        # 检查历史记录
        history = validator.get_validation_history()
        assert len(history) == 2
        assert history[0]["signal_type"] == result1["signal_type"]
        assert history[1]["signal_type"] == result2["signal_type"]

    def test_clear_history(self):
        """测试清空验证历史"""
        validator = MicroEntryValidator()

        # 添加一些历史记录
        h4_structure, m15_data = self.test_create_sample_data()
        market_context = {"regime": "TRENDING", "timestamp": datetime.now().isoformat()}

        validator.validate_entry(
            h4_structure, m15_data, None, "BULLISH", market_context
        )
        assert len(validator.validation_history) == 1

        # 清空历史
        validator.clear_history()
        assert len(validator.validation_history) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
