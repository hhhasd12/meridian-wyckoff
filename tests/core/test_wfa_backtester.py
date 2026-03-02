"""
WFA回测引擎单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from src.core.wfa_backtester import (
    WFABacktester,
    PerformanceMetric,
    ValidationResult,
)
from src.core.mistake_book import MistakeBook, MistakeType, ErrorSeverity, ErrorPattern


class TestWFABacktester:
    """测试WFA回测引擎"""

    def test_initialization(self):
        """测试初始化"""
        backtester = WFABacktester()
        assert backtester is not None
        assert backtester.train_days == 60
        assert backtester.test_days == 20
        assert backtester.step_days == 10
        assert backtester.min_performance_improvement == 0.01
        assert backtester.max_weight_change == 0.05
        assert backtester.smooth_factor == 0.3
        assert backtester.is_initialized is False

    def test_initialization_with_custom_config(self):
        """测试自定义配置初始化"""
        config = {
            "train_days": 30,
            "test_days": 10,
            "step_days": 5,
            "min_performance_improvement": 0.02,
            "max_weight_change": 0.1,
            "smooth_factor": 0.5,
        }
        backtester = WFABacktester(config)

        assert backtester.train_days == 30
        assert backtester.test_days == 10
        assert backtester.step_days == 5
        assert backtester.min_performance_improvement == 0.02
        assert backtester.max_weight_change == 0.1
        assert backtester.smooth_factor == 0.5

    def test_initialize_with_baseline(self):
        """测试基准配置初始化"""
        backtester = WFABacktester()

        baseline_config = {
            "period_weight_filter": {"weights": {"W": 0.25, "D": 0.20, "H4": 0.18}},
            "threshold_parameters": {"confidence_threshold": 0.7},
        }

        # 使用模拟性能评估器
        def mock_evaluator(config, data):
            return {
                PerformanceMetric.SHARPE_RATIO.value: 1.5,
                PerformanceMetric.MAX_DRAWDOWN.value: 0.1,
                PerformanceMetric.WIN_RATE.value: 0.6,
                PerformanceMetric.PROFIT_FACTOR.value: 1.8,
                PerformanceMetric.CALMAR_RATIO.value: 2.0,
                PerformanceMetric.STABILITY_SCORE.value: 0.8,
            }

        baseline_perf = backtester.initialize_with_baseline(
            baseline_config, performance_evaluator=mock_evaluator
        )

        assert backtester.is_initialized is True
        assert backtester.baseline_performance is not None
        assert backtester.accepted_configuration is not None
        assert backtester.accepted_performance is not None

        # 检查性能指标
        assert baseline_perf is not None
        assert PerformanceMetric.SHARPE_RATIO.value in baseline_perf
        assert baseline_perf[PerformanceMetric.SHARPE_RATIO.value] == 1.5

    def test_check_weight_changes_within_limit(self):
        """测试权重变化检查（在限制内）"""
        backtester = WFABacktester()
        backtester.accepted_configuration = {
            "weights": {"w1": 0.5, "w2": 0.5},
            "threshold": 0.7,
        }

        # 微小变化
        new_config = {
            "weights": {"w1": 0.51, "w2": 0.49},  # 平均变化0.01
            "threshold": 0.71,  # 变化0.01
        }

        result = backtester._check_weight_changes(new_config)
        assert result is True  # 平均变化0.01 < 0.05

    def test_check_weight_changes_exceed_limit(self):
        """测试权重变化检查（超出限制）"""
        backtester = WFABacktester()
        backtester.accepted_configuration = {
            "weights": {"w1": 0.5, "w2": 0.5},
            "threshold": 0.7,
        }

        # 大变化
        new_config = {
            "weights": {"w1": 0.8, "w2": 0.2},  # 平均变化0.3
            "threshold": 0.9,  # 变化0.2
        }

        result = backtester._check_weight_changes(new_config)
        assert result is False  # 平均变化 > 0.05

    def test_validate_mutations_empty(self):
        """测试验证空变异列表"""
        backtester = WFABacktester()
        baseline_config = {"weights": {"w1": 0.5}}
        backtester.initialize_with_baseline(baseline_config)

        accepted, rejected, report = backtester.validate_mutations([])

        assert accepted == []
        assert rejected == []
        assert report["status"] == "no_mutations"

    def test_validate_mutations_with_simulated_data(self):
        """测试使用模拟数据验证变异"""
        backtester = WFABacktester(
            {
                "train_days": 10,
                "test_days": 5,
                "step_days": 3,
            }
        )

        baseline_config = {"weights": {"w1": 0.5, "w2": 0.5}}

        # 创建模拟历史数据
        dates = pd.date_range(end=datetime.now(), periods=100, freq="D")
        historical_data = pd.DataFrame(
            {
                "open": np.random.randn(100).cumsum() + 100,
                "high": np.random.randn(100).cumsum() + 101,
                "low": np.random.randn(100).cumsum() + 99,
                "close": np.random.randn(100).cumsum() + 100,
                "volume": np.random.randint(1000, 10000, 100),
            },
            index=dates,
        )

        # 模拟性能评估器（总是返回相同性能）
        def mock_evaluator(config, data):
            return {
                PerformanceMetric.SHARPE_RATIO.value: 1.0
                + np.random.uniform(-0.1, 0.1),
                PerformanceMetric.MAX_DRAWDOWN.value: 0.05
                + np.random.uniform(-0.01, 0.01),
                PerformanceMetric.WIN_RATE.value: 0.5 + np.random.uniform(-0.05, 0.05),
                PerformanceMetric.PROFIT_FACTOR.value: 1.2
                + np.random.uniform(-0.1, 0.1),
                PerformanceMetric.CALMAR_RATIO.value: 1.5
                + np.random.uniform(-0.1, 0.1),
                PerformanceMetric.STABILITY_SCORE.value: 0.7
                + np.random.uniform(-0.05, 0.05),
            }

        backtester.initialize_with_baseline(
            baseline_config, historical_data, mock_evaluator
        )

        # 创建变异配置
        mutated_configs = [
            {"weights": {"w1": 0.55, "w2": 0.45}},  # 微小变化
            {"weights": {"w1": 0.6, "w2": 0.4}},  # 较大变化
        ]

        accepted, rejected, report = backtester.validate_mutations(
            mutated_configs, historical_data, mock_evaluator
        )

        assert report["total_mutations"] == 2
        assert "acceptance_rate" in report
        assert "average_improvement" in report

        # 由于性能评估随机，可能接受或拒绝
        # 至少检查报告结构
        assert "validation_details" in report
        assert len(report["validation_details"]) == 2

    def test_analyze_wfa_result_acceptance(self):
        """测试WFA结果分析（接受）"""
        backtester = WFABacktester({"overfitting_detection_enabled": False})
        backtester.baseline_performance = {PerformanceMetric.COMPOSITE_SCORE.value: 0.5}

        wfa_result = {
            "num_windows": 5,
            "improvement_vs_baseline": 0.02,  # 超过0.01
            "overall_stability": 0.8,  # 超过0.7
            "is_statistically_significant": True,
        }

        result = backtester._analyze_wfa_result(wfa_result)
        assert result == ValidationResult.ACCEPTED

    def test_analyze_wfa_result_rejected_insufficient_improvement(self):
        """测试WFA结果分析（改进不足拒绝）"""
        backtester = WFABacktester()
        backtester.baseline_performance = {PerformanceMetric.COMPOSITE_SCORE.value: 0.5}

        wfa_result = {
            "num_windows": 5,
            "improvement_vs_baseline": 0.005,  # 低于0.01
            "overall_stability": 0.8,
            "is_statistically_significant": True,
        }

        result = backtester._analyze_wfa_result(wfa_result)
        assert result == ValidationResult.REJECTED

    def test_analyze_wfa_result_rejected_insufficient_stability(self):
        """测试WFA结果分析（稳定性不足拒绝）"""
        backtester = WFABacktester()
        backtester.baseline_performance = {PerformanceMetric.COMPOSITE_SCORE.value: 0.5}

        wfa_result = {
            "num_windows": 5,
            "improvement_vs_baseline": 0.02,
            "overall_stability": 0.6,  # 低于0.7
            "is_statistically_significant": True,
        }

        result = backtester._analyze_wfa_result(wfa_result)
        assert result == ValidationResult.REJECTED

    def test_analyze_wfa_result_needs_more_data(self):
        """测试WFA结果分析（需要更多数据）"""
        backtester = WFABacktester()

        wfa_result = {
            "num_windows": 1,  # 不足2个窗口
            "improvement_vs_baseline": 0.02,
            "overall_stability": 0.8,
        }

        result = backtester._analyze_wfa_result(wfa_result)
        assert result == ValidationResult.NEEDS_MORE_DATA

    def test_calculate_composite_score(self):
        """测试综合评分计算"""
        backtester = WFABacktester()

        performance = {
            PerformanceMetric.SHARPE_RATIO.value: 1.5,
            PerformanceMetric.MAX_DRAWDOWN.value: 0.1,
            PerformanceMetric.WIN_RATE.value: 0.6,
            PerformanceMetric.PROFIT_FACTOR.value: 1.8,
            PerformanceMetric.CALMAR_RATIO.value: 2.0,
            PerformanceMetric.STABILITY_SCORE.value: 0.8,
        }

        stability_scores = {
            PerformanceMetric.SHARPE_RATIO.value: 0.9,
            PerformanceMetric.MAX_DRAWDOWN.value: 0.8,
            PerformanceMetric.WIN_RATE.value: 0.7,
            PerformanceMetric.PROFIT_FACTOR.value: 0.85,
            PerformanceMetric.CALMAR_RATIO.value: 0.75,
            PerformanceMetric.STABILITY_SCORE.value: 0.95,
        }

        score = backtester._calculate_composite_score(performance, stability_scores)
        assert score > 0
        assert score <= 2.0  # 综合评分应在合理范围（未归一化可能超过1）

    def test_smooth_transition(self):
        """测试平滑过渡"""
        backtester = WFABacktester({"smooth_factor": 0.5})
        backtester.accepted_configuration = {
            "threshold": 0.7,
            "weights": {"w1": 0.5, "w2": 0.5},
        }

        new_config = {
            "threshold": 0.8,
            "weights": {"w1": 0.6, "w2": 0.4},
        }

        backtester._apply_smooth_transition(new_config)

        # 检查平滑后的值
        assert backtester.accepted_configuration is not None
        assert (
            backtester.accepted_configuration["threshold"] == 0.75
        )  # 0.7*0.5 + 0.8*0.5
        assert (
            backtester.accepted_configuration["weights"]["w1"] == 0.55
        )  # 0.5*0.5 + 0.6*0.5
        assert (
            backtester.accepted_configuration["weights"]["w2"] == 0.45
        )  # 0.5*0.5 + 0.4*0.5

    def test_record_validation_failure(self):
        """测试记录验证失败到错题本"""
        backtester = WFABacktester()
        mistake_book = MistakeBook()

        config = {"weights": {"w1": 0.6, "w2": 0.4}}
        validation_detail = {
            "result": "REJECTED",
            "performance": {"sharpe_ratio": 1.0},
            "improvement": -0.01,
            "stability": 0.6,
        }

        # 应不抛出异常
        backtester._record_validation_failure(mistake_book, config, validation_detail)

        # 检查错误已记录
        stats = mistake_book.get_statistics()
        assert stats["total_errors"] == 1

    def test_get_performance_summary(self):
        """测试获取性能摘要"""
        backtester = WFABacktester()

        # 未初始化情况
        summary = backtester.get_performance_summary()
        assert summary["status"] == "no_validations"

        # 初始化后
        baseline_config = {"weights": {"w1": 0.5}}
        backtester.initialize_with_baseline(baseline_config)

        summary = backtester.get_performance_summary()
        assert summary["status"] == "active"
        assert "total_validations" in summary
        assert "acceptance_rate" in summary
        assert "current_composite_score" in summary
        assert "improvement_vs_baseline" in summary

    def test_get_validation_history(self):
        """测试获取验证历史"""
        backtester = WFABacktester()
        baseline_config = {"weights": {"w1": 0.5}}
        backtester.initialize_with_baseline(baseline_config)

        history = backtester.get_validation_history()
        assert isinstance(history, list)
        assert len(history) >= 1  # 至少包含初始化记录

    def test_reset(self):
        """测试重置"""
        backtester = WFABacktester()
        baseline_config = {"weights": {"w1": 0.5}}
        backtester.initialize_with_baseline(baseline_config)

        # 记录一些验证
        mutated_configs = [{"weights": {"w1": 0.55}}]
        backtester.validate_mutations(mutated_configs)

        assert backtester.total_validations > 0
        assert backtester.is_initialized is True
        assert backtester.baseline_performance is not None

        backtester.reset()

        assert backtester.total_validations == 0
        assert backtester.is_initialized is False
        assert backtester.baseline_performance is None
        assert backtester.accepted_configuration is None
        assert backtester.accepted_performance == {}

    def test_insufficient_data_result(self):
        """测试数据不足结果"""
        backtester = WFABacktester()
        result = backtester._create_insufficient_data_result()

        assert result["num_windows"] == 0
        assert result["insufficient_data"] is True
        assert result["composite_score"] == 0.0
        assert result["improvement_vs_baseline"] == 0.0

    def test_mock_historical_data_creation(self):
        """测试模拟历史数据创建"""
        backtester = WFABacktester()
        data = backtester._create_mock_historical_data()

        assert isinstance(data, pd.DataFrame)
        assert len(data) == 365  # 默认一年数据
        assert "open" in data.columns
        assert "high" in data.columns
        assert "low" in data.columns
        assert "close" in data.columns
        assert "volume" in data.columns

    def test_performance_metric_enum(self):
        """测试性能指标枚举"""
        assert PerformanceMetric.SHARPE_RATIO.value == "SHARPE_RATIO"
        assert PerformanceMetric.MAX_DRAWDOWN.value == "MAX_DRAWDOWN"
        assert PerformanceMetric.WIN_RATE.value == "WIN_RATE"
        assert PerformanceMetric.PROFIT_FACTOR.value == "PROFIT_FACTOR"
        assert PerformanceMetric.CALMAR_RATIO.value == "CALMAR_RATIO"
        assert PerformanceMetric.STABILITY_SCORE.value == "STABILITY_SCORE"
        assert PerformanceMetric.COMPOSITE_SCORE.value == "COMPOSITE_SCORE"

    def test_validation_result_enum(self):
        """测试验证结果枚举"""
        assert ValidationResult.ACCEPTED.value == "ACCEPTED"
        assert ValidationResult.REJECTED.value == "REJECTED"
        assert ValidationResult.NEEDS_MORE_DATA.value == "NEEDS_MORE_DATA"
        assert ValidationResult.INCONCLUSIVE.value == "INCONCLUSIVE"

    def test_configuration_complexity_estimation(self):
        """测试配置复杂度估计"""
        backtester = WFABacktester()

        # 简单配置
        simple_config = {"param1": 0.5, "param2": 0.3}
        complexity = backtester._estimate_configuration_complexity(simple_config)
        assert complexity == 2

        # 嵌套配置
        nested_config = {
            "module1": {"param1": 0.5, "param2": {"subparam": 0.3}},
            "module2": [0.1, 0.2, 0.3],
        }
        complexity = backtester._estimate_configuration_complexity(nested_config)
        assert complexity > 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
