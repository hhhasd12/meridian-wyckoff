"""
周期权重过滤器单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import numpy as np
from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter, Timeframe


class TestPeriodWeightFilter:
    """测试周期权重过滤器"""

    def test_initialization(self):
        """测试初始化"""
        filter = PeriodWeightFilter()
        assert filter is not None
        assert len(filter.weights) == 7  # 7个时间框架（W/D/H8/H4/H1/M15/M5）
        assert filter.normalize is True
        assert filter.min_weight == 0.05

    def test_default_weights_sum_to_one(self):
        """测试默认权重总和为1"""
        filter = PeriodWeightFilter()
        weights = filter.get_weights("UNKNOWN")
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001

    def test_timeframe_enum(self):
        """测试时间框架枚举"""
        assert Timeframe.WEEKLY.value == "W"
        assert Timeframe.DAILY.value == "D"
        assert Timeframe.H8.value == "H8"
        assert Timeframe.H4.value == "H4"
        assert Timeframe.H1.value == "H1"
        assert Timeframe.M15.value == "M15"
        assert Timeframe.M5.value == "M5"

        all_tfs = Timeframe.get_all()
        assert len(all_tfs) == 7
        assert all_tfs[0] == Timeframe.WEEKLY
        assert all_tfs[-1] == Timeframe.M5

    def test_from_string(self):
        """测试字符串转换"""
        assert Timeframe.from_string("W") == Timeframe.WEEKLY
        assert Timeframe.from_string("D") == Timeframe.DAILY
        assert Timeframe.from_string("H8") == Timeframe.H8
        assert Timeframe.from_string("H4") == Timeframe.H4
        assert Timeframe.from_string("H1") == Timeframe.H1
        assert Timeframe.from_string("M15") == Timeframe.M15
        assert Timeframe.from_string("M5") == Timeframe.M5

        with pytest.raises(ValueError):
            Timeframe.from_string("INVALID")

    def test_get_weights_different_regimes(self):
        """测试不同市场体制下的权重"""
        filter = PeriodWeightFilter()

        # 趋势市：大周期权重增加
        trending_weights = filter.get_weights("TRENDING")
        assert (
            trending_weights[Timeframe.WEEKLY]
            > filter.DEFAULT_WEIGHTS[Timeframe.WEEKLY]
        )
        assert trending_weights[Timeframe.M5] < filter.DEFAULT_WEIGHTS[Timeframe.M5]

        # 盘整市：中短周期权重增加
        ranging_weights = filter.get_weights("RANGING")
        assert (
            ranging_weights[Timeframe.WEEKLY] < filter.DEFAULT_WEIGHTS[Timeframe.WEEKLY]
        )
        assert ranging_weights[Timeframe.H1] > filter.DEFAULT_WEIGHTS[Timeframe.H1]

        # 高波动市：短周期权重增加
        volatile_weights = filter.get_weights("VOLATILE")
        assert (
            volatile_weights[Timeframe.WEEKLY]
            < filter.DEFAULT_WEIGHTS[Timeframe.WEEKLY]
        )
        assert volatile_weights[Timeframe.M5] > filter.DEFAULT_WEIGHTS[Timeframe.M5]

    def test_calculate_weighted_score(self):
        """测试加权分数计算"""
        filter = PeriodWeightFilter()

        timeframe_scores = {
            "W": 0.8,
            "D": 0.6,
            "H8": 0.5,
            "H4": 0.4,
            "H1": 0.5,
            "M15": 0.7,
            "M5": 0.9,
        }

        # 趋势市加权分数
        trending_score = filter.calculate_weighted_score(timeframe_scores, "TRENDING")
        assert 0.0 <= trending_score <= 1.0

        # 盘整市加权分数
        ranging_score = filter.calculate_weighted_score(timeframe_scores, "RANGING")
        assert 0.0 <= ranging_score <= 1.0

        # 分数应因权重不同而不同
        assert trending_score != ranging_score

    def test_calculate_weighted_score_partial_data(self):
        """测试部分时间框架数据的加权分数计算"""
        filter = PeriodWeightFilter()

        # 只有部分时间框架数据
        partial_scores = {"W": 0.9, "D": 0.7, "H4": 0.8}

        score = filter.calculate_weighted_score(partial_scores, "UNKNOWN")
        assert 0.0 <= score <= 1.0

        # 单个时间框架
        single_score = {"W": 0.5}
        score_single = filter.calculate_weighted_score(single_score, "UNKNOWN")
        assert score_single == 0.5

    def test_calculate_weighted_score_invalid_timeframe(self):
        """测试无效时间框架的处理"""
        filter = PeriodWeightFilter()

        scores_with_invalid = {
            "W": 0.8,
            "INVALID": 0.9,  # 无效时间框架应被忽略
            "D": 0.6,
        }

        score = filter.calculate_weighted_score(scores_with_invalid, "UNKNOWN")
        assert 0.0 <= score <= 1.0

    def test_get_weighted_decision(self):
        """测试加权决策生成"""
        filter = PeriodWeightFilter()

        timeframe_decisions = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BULLISH", "confidence": 0.7},
            "H8": {"state": "BULLISH", "confidence": 0.6},
            "H4": {"state": "NEUTRAL", "confidence": 0.5},
            "H1": {"state": "BULLISH", "confidence": 0.6},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BULLISH", "confidence": 0.8},
        }

        decision = filter.get_weighted_decision(timeframe_decisions, "TRENDING")

        assert "primary_bias" in decision
        assert "confidence" in decision
        assert "timeframe_contributions" in decision
        assert "regime" in decision
        assert "weights_used" in decision

        assert decision["regime"] == "TRENDING"
        assert 0.0 <= decision["confidence"] <= 1.0
        assert len(decision["timeframe_contributions"]) == 7

    def test_get_weighted_decision_conflict(self):
        """测试冲突场景的加权决策"""
        filter = PeriodWeightFilter()

        # 多头空头混合
        conflicting_decisions = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BEARISH", "confidence": 0.7},
            "H8": {"state": "BULLISH", "confidence": 0.5},
            "H4": {"state": "BULLISH", "confidence": 0.6},
            "H1": {"state": "BEARISH", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BEARISH", "confidence": 0.8},
        }

        decision = filter.get_weighted_decision(conflicting_decisions, "RANGING")

        # 应有置信度计算
        assert "confidence" in decision
        assert 0.0 <= decision["confidence"] <= 1.0

        # 应有时框架贡献度
        contributions = decision["timeframe_contributions"]
        assert len(contributions) == 7
        for tf, contrib in contributions.items():
            assert "weight" in contrib
            assert "state" in contrib
            assert "confidence" in contrib
            assert "contribution" in contrib

    def test_recommend_timeframe_focus(self):
        """测试时间框架关注推荐"""
        filter = PeriodWeightFilter()

        # 趋势市看涨偏向
        recommendations = filter.recommend_timeframe_focus("TRENDING", "BULLISH")
        assert len(recommendations) == 7

        # 应按时框架权重降序排列
        weights = [w for _, w in recommendations]
        assert all(weights[i] >= weights[i + 1] for i in range(len(weights) - 1))

        # 趋势市大周期应权重更高
        trending_rec = dict(recommendations)
        assert trending_rec["W"] > trending_rec["M5"]

    def test_custom_config(self):
        """测试自定义配置"""
        custom_config = {
            "weights": {
                "W": 0.35,  # 修改为0.35，使总和不等于1
                "D": 0.25,
                "H8": 0.10,
                "H4": 0.2,
                "H1": 0.15,
                "M15": 0.07,
                "M5": 0.03,
            },
            "normalize": False,
            "min_weight": 0.01,
        }

        filter = PeriodWeightFilter(custom_config)
        weights = filter.get_weights("UNKNOWN")

        # 检查自定义权重
        assert abs(weights[Timeframe.WEEKLY] - 0.35) < 0.001
        assert abs(weights[Timeframe.DAILY] - 0.25) < 0.001

        # 检查不归一化（总和应为1.15，不是1.0）
        total = sum(weights.values())
        assert abs(total - 1.15) < 0.001  # 不应归一化，保持原总和

    def test_min_weight_enforcement(self):
        """测试最小权重强制"""
        custom_config = {
            "weights": {
                "W": 0.01,  # 低于最小权重
                "D": 0.99,
            },
            "min_weight": 0.05,
        }

        filter = PeriodWeightFilter(custom_config)
        weights = filter.get_weights("UNKNOWN")

        # 周线权重应被提升到最小权重
        assert weights[Timeframe.WEEKLY] >= 0.05

    def test_get_config_report(self):
        """测试配置报告"""
        filter = PeriodWeightFilter()
        report = filter.get_config_report()

        assert "base_weights" in report
        assert "regime_adjustments" in report
        assert "normalize" in report
        assert "min_weight" in report

        assert len(report["base_weights"]) == 7
        assert len(report["regime_adjustments"]) == 4  # 4种市场体制


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
