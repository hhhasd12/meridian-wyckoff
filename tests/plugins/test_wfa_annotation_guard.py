"""T5.2: WFA 标注回归守护（Pareto改进）测试

验证:
1. WFA 验证中标注匹配度不能比旧配置降低超过5%
2. 无标注/无基准时完全不影响现有 WFA 逻辑
3. 边界条件处理正确
"""

import numpy as np
import pandas as pd
import pytest

from src.plugins.evolution.wfa_validator import WFAConfig, WFAReport, WFAValidator


def _make_h4(n: int = 700) -> pd.DataFrame:
    """生成 n 根 H4 假数据"""
    idx = pd.date_range("2025-01-01", periods=n, freq="4h")
    rng = np.random.RandomState(42)
    close = 100.0 + rng.randn(n).cumsum() * 0.5
    return pd.DataFrame(
        {
            "open": close - rng.rand(n) * 0.3,
            "high": close + rng.rand(n) * 0.5,
            "low": close - rng.rand(n) * 0.5,
            "close": close,
            "volume": rng.rand(n) * 1000 + 500,
        },
        index=idx,
    )


def _make_evaluator(sharpe: float = 1.0, trades: int = 10, ann_score: float = 0.0):
    """返回一个假评估函数，固定输出指定指标"""

    def evaluator_fn(config, data_dict):
        return {
            "SHARPE_RATIO": sharpe,
            "TOTAL_TRADES": trades,
            "TOTAL_RETURN": 0.05,
            "MAX_DRAWDOWN": 0.1,
            "WIN_RATE": 0.6,
            "PROFIT_FACTOR": 1.5,
            "ANNOTATION_SCORE": ann_score,
        }

    return evaluator_fn


class TestAnnotationRegressionGuard:
    """T5.2: 标注回归守护测试"""

    def test_no_regression(self):
        """新分数 >= 旧分数 → 通过"""
        cfg = WFAConfig(train_bars=200, test_bars=200, step_bars=200, min_windows=1)
        validator = WFAValidator(
            config=cfg,
            evaluator_fn=_make_evaluator(sharpe=1.5, trades=10, ann_score=0.85),
            baseline_annotation_score=0.80,
        )
        h4 = _make_h4(700)
        report = validator.validate({}, {"H4": h4})
        assert report.passed is True
        assert report.annotation_regression_passed is True
        assert report.annotation_score >= 0.80

    def test_slight_drop_ok(self):
        """新分数 = 旧 * 0.96 → 在5%容忍范围内，通过"""
        baseline = 0.80
        new_score = baseline * 0.96  # 0.768, > 0.80 * 0.95 = 0.76

        cfg = WFAConfig(train_bars=200, test_bars=200, step_bars=200, min_windows=1)
        validator = WFAValidator(
            config=cfg,
            evaluator_fn=_make_evaluator(sharpe=1.5, trades=10, ann_score=new_score),
            baseline_annotation_score=baseline,
        )
        h4 = _make_h4(700)
        report = validator.validate({}, {"H4": h4})
        assert report.passed is True
        assert report.annotation_regression_passed is True

    def test_regression_detected(self):
        """新分数 = 旧 * 0.80 → 降低20%，超出容忍范围，回归"""
        baseline = 0.80
        new_score = baseline * 0.80  # 0.64 < 0.80 * 0.95 = 0.76

        cfg = WFAConfig(train_bars=200, test_bars=200, step_bars=200, min_windows=1)
        validator = WFAValidator(
            config=cfg,
            evaluator_fn=_make_evaluator(sharpe=1.5, trades=10, ann_score=new_score),
            baseline_annotation_score=baseline,
        )
        h4 = _make_h4(700)
        report = validator.validate({}, {"H4": h4})
        assert report.passed is False
        assert report.annotation_regression_passed is False

    def test_no_old_score(self):
        """旧分数 = 0 → 跳过检查，不影响原有 WFA 结果"""
        cfg = WFAConfig(train_bars=200, test_bars=200, step_bars=200, min_windows=1)
        validator = WFAValidator(
            config=cfg,
            evaluator_fn=_make_evaluator(sharpe=1.5, trades=10, ann_score=0.0),
            baseline_annotation_score=0.0,
        )
        h4 = _make_h4(700)
        report = validator.validate({}, {"H4": h4})
        # WFA 本身通过（sharpe > 0, trades >= min）
        assert report.passed is True
        assert report.annotation_regression_passed is True
        assert report.annotation_score == 0.0

    def test_zero_scores(self):
        """新旧都是0 → 通过（baseline=0跳过检查）"""
        cfg = WFAConfig(train_bars=200, test_bars=200, step_bars=200, min_windows=1)
        validator = WFAValidator(
            config=cfg,
            evaluator_fn=_make_evaluator(sharpe=1.0, trades=10, ann_score=0.0),
            baseline_annotation_score=0.0,
        )
        h4 = _make_h4(700)
        report = validator.validate({}, {"H4": h4})
        assert report.passed is True
        assert report.annotation_regression_passed is True

    def test_set_baseline_annotation_score(self):
        """验证 set_baseline_annotation_score 方法"""
        validator = WFAValidator()
        assert validator.baseline_annotation_score == 0.0
        validator.set_baseline_annotation_score(0.75)
        assert validator.baseline_annotation_score == 0.75

    def test_config_regression_ratio_customizable(self):
        """验证 annotation_regression_ratio 可自定义"""
        cfg = WFAConfig(
            train_bars=200,
            test_bars=200,
            step_bars=200,
            min_windows=1,
            annotation_regression_ratio=0.90,  # 更严格: 不能降超过10%
        )
        baseline = 0.80
        # 新分数 = 0.73, threshold = 0.80 * 0.90 = 0.72 → 通过
        validator = WFAValidator(
            config=cfg,
            evaluator_fn=_make_evaluator(sharpe=1.5, trades=10, ann_score=0.73),
            baseline_annotation_score=baseline,
        )
        h4 = _make_h4(700)
        report = validator.validate({}, {"H4": h4})
        assert report.passed is True
        assert report.annotation_regression_passed is True
