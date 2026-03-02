"""
WFA（Walk-Forward Analysis）回测引擎模块
实现滚动窗口验证，防止自动化进化中的过拟合问题

设计原则：
1. 滚动窗口验证：训练60天/测试20天/步长10天，确保变异稳健性
2. 防过拟合机制：监控性能稳定性、权重稳定性、训练-测试差异
3. 权重调整限制：单次调整不超过5%，防止参数跳跃
4. 平滑过渡：新旧权重混合（平滑因子0.3），避免系统震荡
5. 多维度评估：夏普比率、最大回撤、胜率、盈亏比、稳定性评分

技术要点：
- 时间序列交叉验证：避免未来数据泄露
- 性能基准对比：与基准配置比较，确保进化有意义
- 统计显著性检验：确保性能提升不是随机波动
- 复杂度惩罚：防止过度复杂化模型
"""

import copy
import logging
import random
import warnings
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 导入相关模块
try:
    from .mistake_book import ErrorPattern, ErrorSeverity, MistakeBook, MistakeType
    from .weight_variator import WeightVariator
except ImportError:
    # 备用导入
    from mistake_book import ErrorPattern, ErrorSeverity, MistakeBook, MistakeType


class PerformanceMetric(Enum):
    """性能指标枚举"""

    SHARPE_RATIO = "SHARPE_RATIO"  # 夏普比率
    MAX_DRAWDOWN = "MAX_DRAWDOWN"  # 最大回撤
    WIN_RATE = "WIN_RATE"  # 胜率
    PROFIT_FACTOR = "PROFIT_FACTOR"  # 盈亏比
    CALMAR_RATIO = "CALMAR_RATIO"  # 卡玛比率
    STABILITY_SCORE = "STABILITY_SCORE"  # 稳定性评分
    COMPOSITE_SCORE = "COMPOSITE_SCORE"  # 综合评分
    SORTINO_RATIO = "SORTINO_RATIO"  # 索提诺比率（只考虑下行风险）
    ULCR = "ULCR"  # 上行捕获率（Upside Capture Ratio）
    DLCR = "DLCR"  # 下行捕获率（Downside Capture Ratio）
    INFORMATION_RATIO = "INFORMATION_RATIO"  # 信息比率
    ALPHA = "ALPHA"  # 阿尔法（超额收益）
    BETA = "BETA"  # 贝塔（市场风险暴露）
    TRACKING_ERROR = "TRACKING_ERROR"  # 跟踪误差
    VALUE_AT_RISK = "VALUE_AT_RISK"  # 风险价值（VaR）
    EXPECTED_SHORTFALL = "EXPECTED_SHORTFALL"  # 预期损失（ES）
    SKEWNESS = "SKEWNESS"  # 偏度
    KURTOSIS = "KURTOSIS"  # 峰度
    MAX_CONSECUTIVE_LOSSES = "MAX_CONSECUTIVE_LOSSES"  # 最大连续亏损次数
    AVG_WINNING_TRADE = "AVG_WINNING_TRADE"  # 平均盈利交易
    AVG_LOSING_TRADE = "AVG_LOSING_TRADE"  # 平均亏损交易
    PROFIT_LOSS_RATIO = "PROFIT_LOSS_RATIO"  # 盈亏比（每笔交易）
    RECOVERY_FACTOR = "RECOVERY_FACTOR"  # 恢复因子（净利润/最大回撤）
    RISK_ADJUSTED_RETURN = "RISK_ADJUSTED_RETURN"  # 风险调整后收益


class ValidationResult(Enum):
    """验证结果枚举"""

    ACCEPTED = "ACCEPTED"  # 接受变异
    REJECTED = "REJECTED"  # 拒绝变异
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"  # 需要更多数据
    INCONCLUSIVE = "INCONCLUSIVE"  # 不确定


class WFABacktester:
    """
    WFA回测引擎

    功能：
    1. 执行Walk-Forward Analysis验证权重变异
    2. 计算多维度性能指标
    3. 防止过拟合和随机波动
    4. 管理权重平滑过渡
    5. 提供进化决策建议
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化WFA回测引擎

        Args:
            config: 配置字典，包含以下参数：
                - train_days: 训练天数（默认60）
                - test_days: 测试天数（默认20）
                - step_days: 步长天数（默认10）
                - min_performance_improvement: 最小性能提升（默认0.01，即1%）
                - max_weight_change: 最大权重变化（默认0.05，即5%）
                - smooth_factor: 平滑因子（默认0.3）
                - stability_threshold: 稳定性阈值（默认0.7）
                - require_statistical_significance: 是否需要统计显著性（默认True）
                - significance_level: 显著性水平（默认0.05）
                - composite_weights: 综合评分权重字典
                - enable_complexity_penalty: 是否启用复杂度惩罚（默认True）
        """
        self.config = config or {}

        # WFA参数
        self.train_days = self.config.get("train_days", 60)
        self.test_days = self.config.get("test_days", 20)
        self.step_days = self.config.get("step_days", 10)

        # 性能要求
        self.min_performance_improvement = self.config.get(
            "min_performance_improvement", 0.01
        )
        self.max_weight_change = self.config.get("max_weight_change", 0.05)
        self.smooth_factor = self.config.get("smooth_factor", 0.3)
        self.stability_threshold = self.config.get("stability_threshold", 0.7)

        # 统计检验
        self.require_statistical_significance = self.config.get(
            "require_statistical_significance", True
        )
        self.significance_level = self.config.get("significance_level", 0.05)

        # 综合评分权重
        self.composite_weights = self.config.get(
            "composite_weights",
            {
                PerformanceMetric.SHARPE_RATIO: 0.15,
                PerformanceMetric.MAX_DRAWDOWN: 0.15,
                PerformanceMetric.WIN_RATE: 0.10,
                PerformanceMetric.PROFIT_FACTOR: 0.10,
                PerformanceMetric.CALMAR_RATIO: 0.08,
                PerformanceMetric.STABILITY_SCORE: 0.08,
                PerformanceMetric.SORTINO_RATIO: 0.07,
                PerformanceMetric.INFORMATION_RATIO: 0.06,
                PerformanceMetric.RECOVERY_FACTOR: 0.05,
                PerformanceMetric.RISK_ADJUSTED_RETURN: 0.05,
                PerformanceMetric.ULCR: 0.03,
                PerformanceMetric.DLCR: 0.03,
                PerformanceMetric.ALPHA: 0.02,
                PerformanceMetric.BETA: 0.02,
                PerformanceMetric.TRACKING_ERROR: 0.01,
            },
        )

        # 复杂度惩罚
        self.enable_complexity_penalty = self.config.get(
            "enable_complexity_penalty", True
        )
        self.complexity_penalty_factor = self.config.get(
            "complexity_penalty_factor", 0.01
        )

        # 防过拟合参数
        self.overfitting_detection_enabled = self.config.get(
            "overfitting_detection_enabled", True
        )
        self.train_test_gap_threshold = self.config.get(
            "train_test_gap_threshold", 0.15
        )
        self.performance_decay_threshold = self.config.get(
            "performance_decay_threshold", 0.10
        )
        self.min_window_count = self.config.get("min_window_count", 5)
        self.max_variance_ratio = self.config.get("max_variance_ratio", 2.0)
        self.correlation_threshold = self.config.get("correlation_threshold", 0.7)
        self.out_of_sample_weight = self.config.get("out_of_sample_weight", 0.7)

        # 统计检验参数
        self.min_observations_for_test = self.config.get(
            "min_observations_for_test", 30
        )
        self.bootstrap_iterations = self.config.get("bootstrap_iterations", 1000)
        self.cross_validation_folds = self.config.get("cross_validation_folds", 5)

        # 数据存储
        self.validation_history: list[dict[str, Any]] = []
        self.performance_cache: dict[str, dict[str, float]] = {}

        # 基准配置性能（用于比较）
        self.baseline_performance: Optional[dict[str, float]] = None

        # 当前接受的最佳配置
        self.accepted_configuration: Optional[dict[str, Any]] = None
        self.accepted_performance: Optional[dict[str, float]] = None

        # 回测引擎状态
        self.is_initialized = False
        self.total_validations = 0
        self.accepted_validations = 0
        self.rejected_validations = 0

    def initialize_with_baseline(
        self,
        baseline_config: dict[str, Any],
        historical_data: Optional[pd.DataFrame] = None,
        performance_evaluator: Optional[Callable] = None,
    ) -> Optional[dict[str, float]]:
        """
        使用基准配置初始化WFA引擎

        Args:
            baseline_config: 基准配置
            historical_data: 历史数据（DataFrame格式）
            performance_evaluator: 性能评估函数（如未提供，使用模拟评估）

        Returns:
            基准配置的性能指标
        """
        # 设置基准配置
        self.baseline_config = copy.deepcopy(baseline_config)

        # 评估基准性能
        if performance_evaluator is not None:
            self.baseline_performance = performance_evaluator(
                baseline_config, historical_data
            )
        else:
            # 模拟性能评估（实际应用中应替换为真实评估）
            self.baseline_performance = self._simulate_performance(
                baseline_config, historical_data
            )

        # 设置当前接受配置为基准
        self.accepted_configuration = copy.deepcopy(baseline_config)
        self.accepted_performance = copy.deepcopy(self.baseline_performance)

        self.is_initialized = True

        # 记录初始化
        self.validation_history.append(
            {
                "timestamp": datetime.now(),
                "type": "INITIALIZATION",
                "configuration": "BASELINE",
                "performance": self.baseline_performance,
                "result": ValidationResult.ACCEPTED.value,
                "notes": "Baseline configuration initialized",
            }
        )

        return self.baseline_performance

    def validate_mutations(
        self,
        mutated_configs: list[dict[str, Any]],
        historical_data: Optional[pd.DataFrame] = None,
        performance_evaluator: Optional[Callable] = None,
        mistake_book: Optional[MistakeBook] = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        """
        验证一组变异配置

        Args:
            mutated_configs: 变异配置列表
            historical_data: 历史数据
            performance_evaluator: 性能评估函数
            mistake_book: 错题本引用（用于记录验证结果）

        Returns:
            (接受的配置列表, 拒绝的配置列表, 验证报告)
        """
        if not self.is_initialized:
            raise RuntimeError("WFA引擎未初始化，请先调用initialize_with_baseline")

        if not mutated_configs:
            return [], [], {"status": "no_mutations"}

        accepted_configs = []
        rejected_configs = []
        validation_details = []

        for i, config in enumerate(mutated_configs):
            config_id = f"mutation_{self.total_validations + i + 1}"

            # 检查权重变化是否超过限制
            weight_change_ok = self._check_weight_changes(config)
            if not weight_change_ok:
                # 权重变化过大，直接拒绝
                result = ValidationResult.REJECTED
                reason = "Weight changes exceed maximum allowed limit"
                validation_details.append(
                    {
                        "config_id": config_id,
                        "result": result.value,
                        "reason": reason,
                        "performance": None,
                    }
                )
                rejected_configs.append(config)
                continue

            # 执行Walk-Forward Analysis
            wfa_result = self._run_walk_forward_analysis(
                config, historical_data, performance_evaluator
            )

            # 分析WFA结果
            validation_decision = self._analyze_wfa_result(wfa_result)

            # 记录验证结果
            validation_detail = {
                "config_id": config_id,
                "result": validation_decision.value,
                "wfa_result": wfa_result,
                "performance": wfa_result.get("test_performance", {}),
                "improvement": wfa_result.get("improvement_vs_baseline", 0.0),
                "stability": wfa_result.get("stability_score", 0.0),
            }
            validation_details.append(validation_detail)

            # 根据决策分类
            if validation_decision == ValidationResult.ACCEPTED:
                accepted_configs.append(config)

                # 更新接受配置（如果性能更好）
                improvement = wfa_result.get("improvement_vs_baseline", 0.0)
                if improvement > self.min_performance_improvement:
                    # 平滑过渡到新配置
                    self._apply_smooth_transition(config)
                    self.accepted_performance = wfa_result["test_performance"]
            else:
                rejected_configs.append(config)

            # 记录到错题本（如果提供）
            if (
                mistake_book is not None
                and validation_decision == ValidationResult.REJECTED
            ):
                self._record_validation_failure(mistake_book, config, validation_detail)

        # 更新统计信息
        self.total_validations += len(mutated_configs)
        self.accepted_validations += len(accepted_configs)
        self.rejected_validations += len(rejected_configs)

        # 创建验证报告
        report = {
            "timestamp": datetime.now(),
            "total_mutations": len(mutated_configs),
            "accepted": len(accepted_configs),
            "rejected": len(rejected_configs),
            "acceptance_rate": len(accepted_configs) / max(len(mutated_configs), 1),
            "average_improvement": np.mean(
                [detail.get("improvement", 0.0) for detail in validation_details]
            ),
            "average_stability": np.mean(
                [detail.get("stability", 0.0) for detail in validation_details]
            ),
            "validation_details": validation_details,
            "current_baseline_performance": self.baseline_performance,
            "current_accepted_performance": self.accepted_performance,
        }

        # 保存到历史记录
        self.validation_history.append(report)

        return accepted_configs, rejected_configs, report

    def _check_weight_changes(self, config: dict[str, Any]) -> bool:
        """检查权重变化是否超过最大限制"""
        if self.accepted_configuration is None:
            return True

        # 计算配置间的权重变化（简化实现）
        # 实际实现需要比较相同参数的变化
        total_change = 0.0
        compared_params = 0

        # 比较共同参数
        for key in set(config.keys()) & set(self.accepted_configuration.keys()):
            if isinstance(config[key], dict) and isinstance(
                self.accepted_configuration[key], dict
            ):
                # 比较嵌套字典
                for subkey in set(config[key].keys()) & set(
                    self.accepted_configuration[key].keys()
                ):
                    if isinstance(config[key][subkey], (int, float)) and isinstance(
                        self.accepted_configuration[key][subkey], (int, float)
                    ):
                        change = abs(
                            config[key][subkey]
                            - self.accepted_configuration[key][subkey]
                        )
                        total_change += change
                        compared_params += 1
            elif isinstance(config[key], (int, float)) and isinstance(
                self.accepted_configuration[key], (int, float)
            ):
                change = abs(config[key] - self.accepted_configuration[key])
                total_change += change
                compared_params += 1

        if compared_params == 0:
            return True

        avg_change = total_change / compared_params
        return avg_change <= self.max_weight_change

    def _run_walk_forward_analysis(
        self,
        config: dict[str, Any],
        historical_data: Optional[pd.DataFrame] = None,
        performance_evaluator: Optional[Callable] = None,
    ) -> dict[str, Any]:
        """
        执行Walk-Forward Analysis

        Args:
            config: 待验证配置
            historical_data: 历史数据
            performance_evaluator: 性能评估函数

        Returns:
            WFA分析结果字典
        """
        # 如果没有历史数据，使用模拟数据
        if historical_data is None:
            # 创建模拟历史数据（实际应用中应使用真实数据）
            historical_data = self._create_mock_historical_data()

        # 如果没有性能评估函数，使用模拟评估
        if performance_evaluator is None:
            performance_evaluator = self._simulate_performance

        # 提取时间序列
        dates = (
            historical_data.index
            if hasattr(historical_data, "index")
            else range(len(historical_data))
        )
        total_days = len(dates)

        # 检查数据是否足够
        if total_days < self.train_days + self.test_days:
            warnings.warn(
                f"Insufficient data for WFA: {total_days} days available, "
                f"need at least {self.train_days + self.test_days} days"
            )
            return self._create_insufficient_data_result()

        # 执行滚动窗口验证（最多20个窗口，防止数据量大时爆炸）
        windows = []
        start_idx = 0
        max_windows = self.config.get("max_windows", 20)

        while (
            start_idx + self.train_days + self.test_days <= total_days
            and len(windows) < max_windows
        ):
            # 划分训练集和测试集
            train_end_idx = start_idx + self.train_days
            test_end_idx = train_end_idx + self.test_days

            (
                historical_data.iloc[start_idx:train_end_idx]
                if hasattr(historical_data, "iloc")
                else historical_data[start_idx:train_end_idx]
            )
            test_data = (
                historical_data.iloc[train_end_idx:test_end_idx]
                if hasattr(historical_data, "iloc")
                else historical_data[train_end_idx:test_end_idx]
            )

            # 在训练集上评估配置（可选微调）
            # 这里我们直接使用给定配置，实际应用中可以在训练集上进一步优化

            # 在测试集上评估性能
            # 注意：必须传入 train+test 完整窗口，否则行数不足 slow_window 导致 MA 全为 NaN
            full_window_data = (
                historical_data.iloc[start_idx:test_end_idx]
                if hasattr(historical_data, "iloc")
                else historical_data[start_idx:test_end_idx]
            )
            test_performance = performance_evaluator(config, full_window_data)

            # 记录窗口结果
            windows.append(
                {
                    "window_index": len(windows),
                    "train_start": start_idx,
                    "train_end": train_end_idx - 1,
                    "test_start": train_end_idx,
                    "test_end": test_end_idx - 1,
                    "test_performance": test_performance,
                }
            )

            # 移动到下一个窗口
            start_idx += self.step_days

        if not windows:
            return self._create_insufficient_data_result()

        # 分析窗口结果
        return self._analyze_windows(windows)

    def _analyze_windows(self, windows: list[dict[str, Any]]) -> dict[str, Any]:
        """分析WFA窗口结果"""
        # 收集所有窗口的性能指标
        all_performance = [w["test_performance"] for w in windows]

        # 计算平均性能
        avg_performance = {}
        for metric in PerformanceMetric:
            metric_values = [p.get(metric.value, 0.0) for p in all_performance]
            if metric_values:
                avg_performance[metric.value] = np.mean(metric_values)

        # 计算性能稳定性（跨窗口的一致性）
        stability_scores = {}
        for metric in PerformanceMetric:
            metric_values = [p.get(metric.value, 0.0) for p in all_performance]
            if len(metric_values) > 1:
                # 使用变异系数（标准差/均值）的倒数作为稳定性分数
                mean_val = np.mean(metric_values)
                std_val = np.std(metric_values)
                if mean_val != 0:
                    cv = std_val / abs(mean_val)
                    stability_scores[metric.value] = 1.0 / (1.0 + cv)
                else:
                    stability_scores[metric.value] = 0.0
            else:
                stability_scores[metric.value] = 1.0 if metric_values else 0.0

        # 计算综合稳定性分数
        overall_stability = np.mean(list(stability_scores.values()))

        # 计算综合性能评分
        composite_score = self._calculate_composite_score(
            avg_performance, stability_scores
        )

        # 与基准比较
        improvement_vs_baseline = 0.0
        if self.baseline_performance:
            baseline_composite = self._calculate_composite_score(
                self.baseline_performance, stability_scores
            )
            improvement_vs_baseline = composite_score - baseline_composite

        # 检查统计显著性（简化实现）
        is_statistically_significant = False
        if self.require_statistical_significance and len(windows) >= 3:
            # 使用配对t检验（简化：比较综合评分）
            [
                self._calculate_composite_score(p, stability_scores)
                for p in all_performance
            ]
            # 这里简化处理，实际需要更严谨的统计检验
            if (
                improvement_vs_baseline > 0
                and overall_stability > self.stability_threshold
            ):
                is_statistically_significant = True

        return {
            "num_windows": len(windows),
            "test_performance": avg_performance,
            "stability_scores": stability_scores,
            "overall_stability": overall_stability,
            "composite_score": composite_score,
            "improvement_vs_baseline": improvement_vs_baseline,
            "is_statistically_significant": is_statistically_significant,
            "window_details": windows,
        }

    def _calculate_composite_score(
        self, performance: dict[str, float], stability_scores: dict[str, float]
    ) -> float:
        """计算综合性能评分"""
        total_score = 0.0
        total_weight = 0.0

        for metric, weight in self.composite_weights.items():
            metric_name = (
                metric.value if isinstance(metric, PerformanceMetric) else metric
            )
            perf_value = performance.get(metric_name, 0.0)
            stability = stability_scores.get(metric_name, 1.0)

            # 调整性能值（考虑稳定性）
            adjusted_perf = perf_value * stability

            # 应用指标特定调整
            if metric == PerformanceMetric.MAX_DRAWDOWN:
                # 最大回撤越小越好，取倒数
                adjusted_perf = 1.0 / (1.0 + perf_value) if perf_value > 0 else 1.0
            elif metric == PerformanceMetric.STABILITY_SCORE:
                # 稳定性分数直接使用
                adjusted_perf = stability

            total_score += adjusted_perf * weight
            total_weight += weight

        composite_score = total_score / total_weight if total_weight > 0 else 0.0

        # 应用复杂度惩罚（如果启用）
        if self.enable_complexity_penalty:
            # 简化复杂度估计：配置中参数数量
            # 实际应用中可能需要更复杂的复杂度度量
            param_count = self._estimate_configuration_complexity(performance)
            complexity_penalty = param_count * self.complexity_penalty_factor
            composite_score *= 1.0 - complexity_penalty

        return max(composite_score, 0.0)

    def _check_for_overfitting(self, wfa_result: dict[str, Any]) -> dict[str, Any]:
        """检查是否存在过拟合迹象"""
        window_details = wfa_result.get("window_details", [])
        if len(window_details) < self.min_window_count:
            return {"is_valid": False, "reason": "窗口数量不足"}

        # 提取训练集和测试集性能（如果有）
        train_performances = []
        test_performances = []

        for window in window_details:
            if "train_performance" in window:
                train_performances.append(window["train_performance"])
            if "test_performance" in window:
                test_performances.append(window["test_performance"])

        # 检查训练-测试性能差距
        if train_performances and test_performances:
            train_scores = [
                self._calculate_composite_score(p, {}) for p in train_performances
            ]
            test_scores = [
                self._calculate_composite_score(p, {}) for p in test_performances
            ]

            if train_scores and test_scores:
                avg_train_score = np.mean(train_scores)
                avg_test_score = np.mean(test_scores)

                if avg_train_score > 0:
                    gap_ratio = (avg_train_score - avg_test_score) / avg_train_score
                    if gap_ratio > self.train_test_gap_threshold:
                        return {
                            "is_valid": False,
                            "reason": f"训练-测试性能差距过大: {gap_ratio:.2%} > {self.train_test_gap_threshold:.2%}",
                        }

        # 检查性能衰减（后期窗口性能下降）
        test_scores = [
            self._calculate_composite_score(w["test_performance"], {})
            for w in window_details
        ]
        if len(test_scores) >= 3:
            # 将窗口分为前半部分和后半部分
            split_idx = len(test_scores) // 2
            first_half = test_scores[:split_idx]
            second_half = test_scores[split_idx:]

            if first_half and second_half:
                avg_first = np.mean(first_half)
                avg_second = np.mean(second_half)

                if avg_first > 0:
                    decay_ratio = (avg_first - avg_second) / avg_first
                    if decay_ratio > self.performance_decay_threshold:
                        return {
                            "is_valid": False,
                            "reason": f"性能衰减过大: {decay_ratio:.2%} > {self.performance_decay_threshold:.2%}",
                        }

        # 检查性能方差（过拟合通常导致高方差）
        if test_scores:
            variance = np.var(test_scores)
            mean_score = np.mean(test_scores)

            if mean_score > 0:
                variance_ratio = variance / mean_score
                if variance_ratio > self.max_variance_ratio:
                    return {
                        "is_valid": False,
                        "reason": f"性能方差过大: {variance_ratio:.2f} > {self.max_variance_ratio:.2f}",
                    }

        # 检查窗口间相关性（过拟合可能导致窗口间低相关性）
        if len(window_details) >= 3:
            # 提取每个窗口的关键指标
            metrics_to_check = [
                PerformanceMetric.SHARPE_RATIO.value,
                PerformanceMetric.WIN_RATE.value,
                PerformanceMetric.MAX_DRAWDOWN.value,
            ]

            for metric in metrics_to_check:
                metric_values = []
                for window in window_details:
                    if metric in window["test_performance"]:
                        metric_values.append(window["test_performance"][metric])

                if len(metric_values) >= 3:
                    # 计算自相关性（简化：计算相邻窗口的相关性）
                    correlations = []
                    for i in range(len(metric_values) - 1):
                        corr = np.corrcoef([metric_values[i]], [metric_values[i + 1]])[
                            0, 1
                        ]
                        if not np.isnan(corr):
                            correlations.append(corr)

                    if correlations:
                        avg_correlation = np.mean(correlations)
                        if avg_correlation < self.correlation_threshold:
                            return {
                                "is_valid": False,
                                "reason": f"窗口间相关性过低: {avg_correlation:.3f} < {self.correlation_threshold:.3f}",
                            }

        return {"is_valid": True, "reason": "通过所有过拟合检查"}

    def _estimate_configuration_complexity(self, config: Any) -> int:
        """估计配置复杂度（参数数量）"""
        if isinstance(config, dict):
            return sum(
                self._estimate_configuration_complexity(v) for v in config.values()
            )
        if isinstance(config, (list, tuple)):
            return sum(self._estimate_configuration_complexity(v) for v in config)
        return 1

    def _analyze_wfa_result(self, wfa_result: dict[str, Any]) -> ValidationResult:
        """分析WFA结果并做出决策"""
        # 检查是否有足够数据
        if wfa_result.get("num_windows", 0) < self.min_window_count:
            return ValidationResult.NEEDS_MORE_DATA

        # 检查综合性能提升
        improvement = wfa_result.get("improvement_vs_baseline", 0.0)
        if improvement < self.min_performance_improvement:
            return ValidationResult.REJECTED

        # 检查稳定性
        stability = wfa_result.get("overall_stability", 0.0)
        if stability < self.stability_threshold:
            return ValidationResult.REJECTED

        # 检查统计显著性（如果要求）
        if self.require_statistical_significance:
            if not wfa_result.get("is_statistically_significant", False):
                return ValidationResult.REJECTED

        # 防过拟合检查
        if self.overfitting_detection_enabled:
            overfitting_check = self._check_for_overfitting(wfa_result)
            if not overfitting_check["is_valid"]:
                logger.warning(f"过拟合检测失败: {overfitting_check['reason']}")
                return ValidationResult.REJECTED

        # 所有检查通过
        return ValidationResult.ACCEPTED

    def _apply_smooth_transition(self, new_config: dict[str, Any]):
        """应用平滑过渡到新配置"""
        if self.accepted_configuration is None:
            self.accepted_configuration = copy.deepcopy(new_config)
            return

        # 递归合并配置，应用平滑因子
        def smooth_merge(old: Any, new: Any, factor: float) -> Any:
            if isinstance(old, dict) and isinstance(new, dict):
                result = {}
                all_keys = set(old.keys()) | set(new.keys())
                for key in all_keys:
                    if key in old and key in new:
                        result[key] = smooth_merge(old[key], new[key], factor)
                    elif key in old:
                        result[key] = old[key]
                    else:
                        result[key] = new[key]
                return result
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                # 线性插值
                return old * (1.0 - factor) + new * factor
            # 类型不匹配，使用新值
            return new

        self.accepted_configuration = smooth_merge(
            self.accepted_configuration, new_config, self.smooth_factor
        )

    def _record_validation_failure(
        self,
        mistake_book: MistakeBook,
        config: dict[str, Any],
        validation_detail: dict[str, Any],
    ):
        """记录验证失败到错题本"""
        try:
            mistake_book.record_mistake(
                mistake_type=MistakeType.WEIGHT_ASSIGNMENT_ERROR,
                severity=ErrorSeverity.MEDIUM,
                context={
                    "config_summary": str(config)[:500],  # 限制长度
                    "validation_result": validation_detail["result"],
                    "performance": validation_detail.get("performance", {}),
                    "improvement": validation_detail.get("improvement", 0.0),
                    "stability": validation_detail.get("stability", 0.0),
                },
                expected="ACCEPTED",
                actual=validation_detail["result"],
                confidence_before=0.7,  # 假设对变异有信心
                confidence_after=0.3,  # 验证后信心下降
                impact_score=0.5,
                module_name="wfa_backtester",
                timeframe="N/A",
                patterns=[ErrorPattern.VOLATILITY_ADAPTATION_ERROR],
                metadata={"validation_detail": validation_detail},
            )
        except Exception as e:
            # 记录失败但不影响主流程
            warnings.warn(f"Failed to record validation failure to mistake book: {e}")

    def _simulate_performance(
        self, config: dict[str, Any], data: Optional[pd.DataFrame] = None
    ) -> dict[str, float]:
        """
        模拟性能评估（实际应用中应替换为真实评估）

        Args:
            config: 配置字典
            data: 历史数据

        Returns:
            模拟性能指标字典
        """
        # -----------------------------------------------------------
        # 关键修复：评分必须对 config 的实际参数值敏感，否则不同 config
        # 得到相同分数，选择压力为零，进化无法发生。
        #
        # 策略：提取 config 中所有叶子数值作为"指纹"，用其哈希/统计
        # 特征计算一个与 config 内容强相关的确定性基准分，再叠加
        # 较小的随机噪声（模拟市场噪声），保证不同 config 得分不同。
        # -----------------------------------------------------------

        def _extract_leaf_values(obj, acc=None):
            """递归提取所有叶子浮点/整数值"""
            if acc is None:
                acc = []
            if isinstance(obj, dict):
                for v in obj.values():
                    _extract_leaf_values(v, acc)
            elif isinstance(obj, (list, tuple)):
                for v in obj:
                    _extract_leaf_values(v, acc)
            elif isinstance(obj, (int, float)):
                acc.append(float(obj))
            return acc

        leaf_values = _extract_leaf_values(config)

        if leaf_values:
            # 用所有参数值的加权和构造与 config 唯一绑定的基准性能
            arr = np.array(leaf_values)
            # 归一化到 [0,1]，避免量纲差异
            arr_norm = arr / (np.abs(arr).max() + 1e-9)
            # 用 sin/cos 混合映射，使相近参数也能产生可区分的分数
            config_signal = float(np.mean(np.sin(arr_norm * np.pi) * 0.5 + 0.5))
        else:
            config_signal = 0.5  # 无参数时回退到中间值

        # 基础性能：0.3 ~ 0.7 范围内，与 config 内容强绑定
        base_perf = 0.3 + config_signal * 0.4

        # 小幅随机扰动（模拟市场噪声），幅度远小于 config 间差异
        noise = random.uniform(-0.05, 0.05)
        base_perf = max(0.1, min(0.9, base_perf + noise))

        # 生成各项指标
        return {
            PerformanceMetric.SHARPE_RATIO.value: base_perf * 1.5,
            PerformanceMetric.MAX_DRAWDOWN.value: max(0.03, 0.25 - base_perf * 0.2),
            PerformanceMetric.WIN_RATE.value: 0.35 + base_perf * 0.35,
            PerformanceMetric.PROFIT_FACTOR.value: 1.0 + base_perf * 0.8,
            PerformanceMetric.CALMAR_RATIO.value: base_perf * 2.0,
            PerformanceMetric.STABILITY_SCORE.value: 0.6 + base_perf * 0.3 + random.uniform(-0.05, 0.05),
            PerformanceMetric.SORTINO_RATIO.value: base_perf * 1.8,
            PerformanceMetric.INFORMATION_RATIO.value: base_perf * 0.8,
        }

    def _create_mock_historical_data(self) -> pd.DataFrame:
        """创建模拟历史数据"""
        dates = pd.date_range(end=datetime.now(), periods=365, freq="D")
        data = {
            "open": np.random.randn(len(dates)).cumsum() + 100,
            "high": np.random.randn(len(dates)).cumsum() + 101,
            "low": np.random.randn(len(dates)).cumsum() + 99,
            "close": np.random.randn(len(dates)).cumsum() + 100,
            "volume": np.random.randint(1000, 10000, len(dates)),
        }
        return pd.DataFrame(data, index=dates)

    def _create_insufficient_data_result(self) -> dict[str, Any]:
        """创建数据不足的结果"""
        return {
            "num_windows": 0,
            "test_performance": {},
            "stability_scores": {},
            "overall_stability": 0.0,
            "composite_score": 0.0,
            "improvement_vs_baseline": 0.0,
            "is_statistically_significant": False,
            "window_details": [],
            "insufficient_data": True,
        }

    def get_validation_history(self) -> list[dict[str, Any]]:
        """获取验证历史"""
        return self.validation_history

    def get_performance_summary(self) -> dict[str, Any]:
        """获取性能摘要"""
        if not self.validation_history:
            return {"status": "no_validations"}

        latest = self.validation_history[-1]

        # 安全获取当前综合评分
        current_composite = 0.0
        if self.accepted_performance is not None:
            current_composite = self.accepted_performance.get(
                PerformanceMetric.COMPOSITE_SCORE.value, 0.0
            )

        # 安全获取基准综合评分
        baseline_composite = 0.0
        if self.baseline_performance is not None:
            baseline_composite = self.baseline_performance.get(
                PerformanceMetric.COMPOSITE_SCORE.value, 0.0
            )

        return {
            "status": "active",
            "total_validations": self.total_validations,
            "acceptance_rate": self.accepted_validations
            / max(self.total_validations, 1),
            "current_composite_score": current_composite,
            "improvement_vs_baseline": current_composite - baseline_composite,
            "latest_validation": {
                "timestamp": latest.get("timestamp"),
                "accepted": latest.get("accepted", 0),
                "rejected": latest.get("rejected", 0),
            },
            "configuration_status": {
                "is_initialized": self.is_initialized,
                "has_baseline": self.baseline_performance is not None,
                "has_accepted_config": self.accepted_configuration is not None,
            },
        }

    def reset(self) -> None:
        """重置WFA引擎状态"""
        self.validation_history.clear()
        self.performance_cache.clear()
        self.baseline_performance = None
        self.accepted_configuration = None
        self.accepted_performance = {}
        self.is_initialized = False
        self.total_validations = 0
        self.accepted_validations = 0
        self.rejected_validations = 0


# 使用示例
if __name__ == "__main__":
    # 创建WFA回测引擎
    backtester = WFABacktester(
        {
            "train_days": 60,
            "test_days": 20,
            "step_days": 10,
            "min_performance_improvement": 0.01,
            "max_weight_change": 0.05,
            "smooth_factor": 0.3,
        }
    )

    # 基准配置
    baseline_config = {
        "period_weight_filter": {
            "weights": {
                "W": 0.25,
                "D": 0.20,
                "H4": 0.18,
                "H1": 0.15,
                "M15": 0.12,
                "M5": 0.10,
            },
        },
        "threshold_parameters": {
            "confidence_threshold": 0.7,
            "volume_threshold": 1.5,
        },
    }

    # 初始化
    baseline_perf = backtester.initialize_with_baseline(baseline_config)

    # 创建变异配置
    mutated_configs = [
        {
            "period_weight_filter": {
                "weights": {
                    "W": 0.28,
                    "D": 0.18,
                    "H4": 0.20,
                    "H1": 0.14,
                    "M15": 0.11,
                    "M5": 0.09,
                },
            },
            "threshold_parameters": {
                "confidence_threshold": 0.72,
                "volume_threshold": 1.6,
            },
        },
        {
            "period_weight_filter": {
                "weights": {
                    "W": 0.22,
                    "D": 0.22,
                    "H4": 0.16,
                    "H1": 0.16,
                    "M15": 0.13,
                    "M5": 0.11,
                },
            },
            "threshold_parameters": {
                "confidence_threshold": 0.68,
                "volume_threshold": 1.4,
            },
        },
    ]

    # 验证变异配置
    accepted, rejected, report = backtester.validate_mutations(mutated_configs)


    if accepted:
        perf_summary = backtester.get_performance_summary()

    # 获取性能摘要
    summary = backtester.get_performance_summary()
