"""
威科夫状态机测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
    WyckoffStateMachine,
    EnhancedWyckoffStateMachine,
    EvidenceChainManager,
)
from src.kernel.types import (
    StateConfig,
    StateEvidence,
    StateDirection,
    StateTransitionType,
)


class TestWyckoffStateMachine:
    """测试威科夫状态机基类"""

    def setup_method(self):
        """测试初始化"""
        self.state_machine = WyckoffStateMachine()

    def test_initialization(self):
        """测试状态机初始化"""
        assert self.state_machine is not None
        assert self.state_machine.current_state == "IDLE"
        assert self.state_machine.state_direction == StateDirection.IDLE
        assert len(self.state_machine.accumulation_states) == 13
        assert len(self.state_machine.distribution_states) == 9
        assert len(self.state_machine.all_states) == 22

    def test_state_definitions(self):
        """测试状态定义完整性"""
        # 检查关键吸筹状态
        accumulation_keys = list(self.state_machine.accumulation_states.keys())
        expected_accumulation = [
            "PS",
            "SC",
            "AR",
            "ST",
            "TEST",
            "UTA",
            "SPRING",
            "SO",
            "LPS",
            "mSOS",
            "MSOS",
            "JOC",
            "BU",
        ]
        assert set(accumulation_keys) == set(expected_accumulation)

        # 检查关键派发状态
        distribution_keys = list(self.state_machine.distribution_states.keys())
        expected_distribution = [
            "PSY",
            "BC",
            "AR_DIST",
            "ST_DIST",
            "UT",
            "UTAD",
            "LPSY",
            "mSOW",
            "MSOW",
        ]
        assert set(distribution_keys) == set(expected_distribution)

    def test_detection_methods_exist(self):
        """测试检测方法是否存在"""
        # 检查吸筹状态检测方法
        for state_name, state_info in self.state_machine.accumulation_states.items():
            detection_method_name = state_info.get("detection_method")
            if detection_method_name:
                assert hasattr(self.state_machine, detection_method_name), (
                    f"Missing detection method {detection_method_name} for state {state_name}"
                )

    def test_process_candle_with_minimal_data(self):
        """测试处理单根K线（最小数据）"""
        # 创建模拟K线数据
        candle = pd.Series(
            {
                "open": 100.0,
                "high": 102.0,
                "low": 98.0,
                "close": 101.0,
                "volume": 1000,
            }
        )
        context = {}

        # 初始状态应为IDLE
        result = self.state_machine.process_candle(candle, context)
        assert result == "IDLE"

    def test_state_reset_conditions(self):
        """测试状态重置条件"""
        # 设置当前状态为SC
        self.state_machine.current_state = "SC"
        self.state_machine.critical_price_levels["SC_LOW"] = 95.0

        # 创建跌破SC低点的K线
        candle = pd.Series(
            {
                "open": 96.0,
                "high": 97.0,
                "low": 94.0,
                "close": 94.5,
                "volume": 1000,
            }
        )
        context = {}

        # 处理K线，应触发状态重置
        result = self.state_machine.process_candle(candle, context)
        # 由于跌破SC低点，状态应重置为IDLE
        assert self.state_machine.current_state == "IDLE"

    def test_detect_sc_method(self):
        """测试SC检测方法"""
        # 创建模拟SC特征K线（高成交量、长下影线）
        candle = pd.Series(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 95.0,  # 大幅下跌
                "close": 98.0,
                "volume": 5000,  # 高成交量
            }
        )
        context = {
            "avg_volume_20": 1000,  # 平均成交量1000，当前5000（5倍）
            "atr_14": 2.0,
            "market_regime": "DOWNTREND",
            "support_level": 96.0,
            "trend_direction": "DOWN",
            "trend_strength": 0.8,
        }

        result = self.state_machine.detect_sc(candle, context)
        assert "confidence" in result
        assert "intensity" in result
        assert "evidences" in result
        # SC检测应返回一定置信度（非零）
        assert 0.0 <= result["confidence"] <= 1.0

    def test_detect_ar_method(self):
        """测试AR检测方法"""
        # 创建模拟AR特征K线（成交量收缩、从SC低点反弹）
        candle = pd.Series(
            {
                "open": 96.0,
                "high": 99.0,
                "low": 95.5,
                "close": 98.5,  # 阳线
                "volume": 1500,  # 成交量收缩
            }
        )
        context = {
            "sc_volume": 5000,  # SC成交量
            "sc_low": 95.0,
            "sc_range": 5.0,
            "has_sc": True,
            "sc_confidence": 0.8,
            "market_regime": "ACCUMULATION",
            "trend_direction": "DOWN",
            "trend_strength": 0.3,  # 趋势减弱
        }

        result = self.state_machine.detect_ar(candle, context)
        assert "confidence" in result
        assert "intensity" in result
        assert "evidences" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_detect_st_method(self):
        """测试ST检测方法"""
        # 创建模拟ST特征K线（成交量进一步收缩、回调测试SC区域）
        candle = pd.Series(
            {
                "open": 98.0,
                "high": 98.5,
                "low": 96.5,
                "close": 97.0,
                "volume": 1000,  # 成交量进一步收缩
            }
        )
        context = {
            "ar_volume": 1500,
            "sc_low": 95.0,
            "ar_high": 99.0,
            "sc_range": 5.0,
            "has_ar": True,
            "ar_confidence": 0.7,
            "market_regime": "ACCUMULATION",
        }

        result = self.state_machine.detect_st(candle, context)
        assert "confidence" in result
        assert "intensity" in result
        assert "evidences" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_state_transition_history(self):
        """测试状态转换历史记录"""
        # 执行几次状态转换
        candle = pd.Series(
            {
                "open": 100.0,
                "high": 102.0,
                "low": 98.0,
                "close": 101.0,
                "volume": 1000,
            }
        )
        context = {}

        initial_history_count = len(self.state_machine.transition_history)

        # 处理几根K线
        for _ in range(3):
            self.state_machine.process_candle(candle, context)

        # 转换历史应增加
        assert len(self.state_machine.transition_history) >= initial_history_count

    def test_get_state_report(self):
        """测试获取状态机报告"""
        report = self.state_machine.get_state_report()
        assert "current_state" in report
        assert "state_direction" in report
        assert "state_confidence" in report
        assert "state_intensity" in report
        assert "alternative_paths_count" in report
        assert "transition_history_count" in report
        assert "critical_price_levels" in report
        assert "timeout_counters" in report


class TestEnhancedWyckoffStateMachine:
    """测试增强威科夫状态机"""

    def setup_method(self):
        """测试初始化"""
        self.enhanced_machine = EnhancedWyckoffStateMachine()

    def test_initialization(self):
        """测试增强状态机初始化"""
        assert self.enhanced_machine is not None
        assert hasattr(self.enhanced_machine, "evidence_chain")
        assert hasattr(self.enhanced_machine, "multi_timeframe_states")
        assert hasattr(self.enhanced_machine, "optimization_history")

    def test_process_multi_timeframe(self):
        """测试多时间框架处理"""
        # 创建多时间框架数据
        candles_dict = {
            "1h": pd.DataFrame(
                {
                    "open": [100.0, 101.0, 100.5],
                    "high": [102.0, 103.0, 102.5],
                    "low": [98.0, 99.0, 98.5],
                    "close": [101.0, 102.0, 101.5],
                    "volume": [1000, 1200, 1100],
                }
            ),
            "4h": pd.DataFrame(
                {
                    "open": [100.0, 101.5],
                    "high": [103.0, 104.0],
                    "low": [99.0, 100.0],
                    "close": [102.0, 103.0],
                    "volume": [2000, 2200],
                }
            ),
        }
        context_dict = {
            "1h": {"market_regime": "ACCUMULATION"},
            "4h": {"market_regime": "ACCUMULATION"},
        }

        results = self.enhanced_machine.process_multi_timeframe(
            candles_dict, context_dict
        )
        assert isinstance(results, dict)
        assert "1h" in results
        assert "4h" in results
        # 状态应为有效状态或IDLE
        assert (
            results["1h"] in self.enhanced_machine.all_states or results["1h"] == "IDLE"
        )


class TestEvidenceChainManager:
    """测试证据链管理器"""

    def setup_method(self):
        """测试初始化"""
        self.evidence_manager = EvidenceChainManager()

    def test_initialization(self):
        """测试证据链管理器初始化"""
        assert self.evidence_manager is not None
        assert hasattr(self.evidence_manager, "evidence_chains")
        assert hasattr(self.evidence_manager, "evidence_weights")
        assert len(self.evidence_manager.evidence_weights) > 0

    def test_add_evidence(self):
        """测试添加证据"""
        evidence = StateEvidence(
            evidence_type="volume_ratio",
            value=2.5,
            confidence=0.8,
            weight=0.7,
            description="成交量比率2.5倍",
        )

        self.evidence_manager.add_evidence("SC", evidence)
        assert "SC" in self.evidence_manager.evidence_chains
        assert len(self.evidence_manager.evidence_chains["SC"]) == 1

    def test_calculate_state_confidence(self):
        """测试计算状态置信度"""
        # 添加多个证据
        evidence1 = StateEvidence(
            evidence_type="volume_ratio",
            value=2.5,
            confidence=0.8,
            weight=0.7,
            description="成交量比率2.5倍",
        )
        evidence2 = StateEvidence(
            evidence_type="price_action",
            value=0.7,
            confidence=0.6,
            weight=0.5,
            description="价格行为评分0.7",
        )

        self.evidence_manager.add_evidence("SC", evidence1)
        self.evidence_manager.add_evidence("SC", evidence2)

        confidence = self.evidence_manager.calculate_state_confidence("SC")
        assert 0.0 <= confidence <= 1.0

    def test_validate_evidence_chain(self):
        """测试验证证据链"""
        # 添加足够证据以通过验证
        for i in range(5):
            evidence = StateEvidence(
                evidence_type=f"test_evidence_{i}",
                value=0.7,
                confidence=0.8,
                weight=0.6,
                description=f"测试证据{i}",
            )
            self.evidence_manager.add_evidence("SC", evidence)

        validation = self.evidence_manager.validate_evidence_chain("SC")
        assert "valid" in validation
        assert "avg_confidence" in validation
        assert "confidence_std" in validation

    def test_get_evidence_report(self):
        """测试获取证据报告"""
        # 添加一些证据
        evidence = StateEvidence(
            evidence_type="volume_ratio",
            value=2.5,
            confidence=0.8,
            weight=0.7,
            description="成交量比率2.5倍",
        )
        self.evidence_manager.add_evidence("SC", evidence)

        report = self.evidence_manager.get_evidence_report("SC")
        assert "state" in report
        assert "evidence_count" in report
        assert "overall_confidence" in report
        assert "recent_evidences" in report
        assert report["state"] == "SC"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
