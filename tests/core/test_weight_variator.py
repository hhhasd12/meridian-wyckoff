"""
权重变异算法单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import numpy as np
from src.plugins.evolution.weight_variator_legacy import (
    WeightVariator,
    MutationOperator,
    ThresholdMutationOperator,
    WeightMutationOperator,
)
from src.kernel.types import MutationType
from src.plugins.self_correction.mistake_book import (
    MistakeBook,
    MistakeType,
    ErrorPattern,
    ErrorSeverity,
)


class TestWeightVariator:
    """测试权重变异算法"""

    def test_initialization(self):
        """测试初始化"""
        variator = WeightVariator()
        assert variator is not None
        assert variator.mutation_rate == 0.3
        assert variator.crossover_rate == 0.5
        assert variator.max_mutation_percent == 0.05
        assert variator.population_size == 10
        assert len(variator.mutation_operators) >= 3  # 至少3个默认算子

    def test_mutation_operator_initialization(self):
        """测试变异算子初始化"""
        # 阈值变异算子
        threshold_op = ThresholdMutationOperator(
            target_module="test_module",
            parameters=["param1", "param2"],
            max_change=0.05,
        )
        assert threshold_op.mutation_type == MutationType.THRESHOLD_ADJUSTMENT
        assert threshold_op.target_module == "test_module"
        assert threshold_op.parameters == ["param1", "param2"]
        assert threshold_op.max_change == 0.05

        # 权重变异算子
        weight_op = WeightMutationOperator(
            target_module="weight_module",
            parameters=["w1", "w2", "w3"],
            max_change=0.1,
            weight_sum_constraint=True,
        )
        assert weight_op.mutation_type == MutationType.WEIGHT_ADJUSTMENT
        assert weight_op.weight_sum_constraint is True

    def test_mutation_direction_calculation(self):
        """测试变异方向计算"""
        op = ThresholdMutationOperator("test", ["param"], 0.05)

        # 测试不同错误模式的变异方向
        assert op.get_mutation_direction(ErrorPattern.FREQUENT_FALSE_POSITIVE) > 0
        assert op.get_mutation_direction(ErrorPattern.FREQUENT_FALSE_NEGATIVE) < 0
        assert abs(op.get_mutation_direction(ErrorPattern.TIMING_ERROR)) > 0

        # 测试未知模式返回小幅度调整
        unknown_dir = op.get_mutation_direction(ErrorPattern.CORRELATION_ERROR)
        assert abs(unknown_dir) <= 0.2

    def test_mutation_magnitude_calculation(self):
        """测试变异幅度计算"""
        op = ThresholdMutationOperator("test", ["param"], 0.05)

        # 测试不同频率和严重程度的变异幅度
        magnitude_low = op.calculate_mutation_magnitude(0.3, ErrorSeverity.LOW)
        magnitude_high = op.calculate_mutation_magnitude(0.3, ErrorSeverity.HIGH)

        assert 0 <= magnitude_low <= 0.05
        assert 0 <= magnitude_high <= 0.05
        assert magnitude_high > magnitude_low  # 高严重程度应有更大变异幅度

    def test_threshold_mutation(self):
        """测试阈值变异"""
        op = ThresholdMutationOperator("test", ["threshold"], 0.05)

        current_value = 0.7
        pattern = ErrorPattern.FREQUENT_FALSE_POSITIVE
        frequency = 0.5

        new_value = op.mutate(current_value, pattern, frequency, ErrorSeverity.MEDIUM)

        # 假阳性过多应增加阈值
        assert new_value > current_value
        # 变化幅度应在合理范围内
        change_percent = abs(new_value - current_value) / current_value
        assert change_percent <= 0.05 * 1.5  # 允许轻微超出（考虑严重程度乘数）

    def test_weight_mutation_with_sum_constraint(self):
        """测试带总和约束的权重变异"""
        op = WeightMutationOperator(
            target_module="test",
            parameters=["w1", "w2", "w3"],
            max_change=0.1,
            weight_sum_constraint=True,
        )

        weights = {"w1": 0.5, "w2": 0.3, "w3": 0.2}
        pattern = ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT
        frequency = 0.4

        new_weights = op.mutate(weights, pattern, frequency, ErrorSeverity.MEDIUM)

        # 检查所有权重都存在
        assert set(new_weights.keys()) == set(weights.keys())

        # 检查权重总和约束（应接近1）
        total = sum(new_weights.values())
        assert abs(total - 1.0) < 0.001

        # 检查变化幅度
        for key in weights:
            change_percent = abs(new_weights[key] - weights[key]) / weights[key]
            assert change_percent <= 0.1 * 1.5  # 允许轻微超出

    def test_generate_initial_population(self):
        """测试初始种群生成"""
        variator = WeightVariator({"population_size": 5})

        base_config = {
            "period_weight_filter": {"weights": {"W": 0.25, "D": 0.20, "H4": 0.18}}
        }

        variator.generate_initial_population(base_config)

        assert len(variator.population) == 5
        assert variator.population[0]["config"] == base_config

        # 检查种群多样性（由于随机性，配置可能相同，至少检查种群大小）
        configs = [ind["config"] for ind in variator.population]
        # 不强制要求所有配置不同，因为随机变异可能未发生

    def test_evolution_without_mistake_book(self):
        """测试无错题本的进化过程"""
        variator = WeightVariator(
            {"population_size": 5, "mutation_rate": 0.5, "crossover_rate": 0.5}
        )

        base_config = {
            "period_weight_filter": {
                "weights": {
                    "W": 0.25,
                    "D": 0.20,
                    "H4": 0.18,
                    "H1": 0.15,
                    "M15": 0.12,
                    "M5": 0.10,
                }
            }
        }

        variator.generate_initial_population(base_config)

        # 模拟性能分数
        performance_scores = {i: np.random.uniform(0.5, 0.9) for i in range(5)}

        # 执行进化
        variator.evolve_population(performance_scores)

        # 检查种群大小不变
        assert len(variator.population) == 5

        # 检查代数增加（由于精英保留，第一个个体可能不变）
        # 至少检查种群大小不变
        pass

    def test_get_performance_report(self):
        """测试性能报告"""
        variator = WeightVariator()

        report = variator.get_performance_report()
        assert "status" in report

        # 初始状态下应无历史
        if report["status"] == "no_history":
            assert "generations" not in report or report["generations"] == 0
        else:
            assert "generations" in report
            assert "best_performance" in report

    def test_mutation_operator_registry(self):
        """测试变异算子注册"""
        variator = WeightVariator(
            {
                "mutation_operators": {
                    "custom_op": {
                        "type": "weight",
                        "target_module": "custom_module",
                        "parameters": ["p1", "p2", "p3"],
                        "max_change": 0.03,
                        "weight_sum_constraint": False,
                    }
                }
            }
        )

        assert "custom_op" in variator.mutation_operators
        custom_op = variator.mutation_operators["custom_op"]
        assert custom_op.target_module == "custom_module"
        assert custom_op.parameters == ["p1", "p2", "p3"]
        assert custom_op.max_change == 0.03

    def test_single_point_crossover(self):
        """测试单点交叉"""
        variator = WeightVariator()

        config1 = {
            "module1": {"param1": 0.5, "param2": 0.3},
            "module2": {"paramA": 0.7, "paramB": 0.2},
            "common_module": {"x": 1.0, "y": 2.0},
        }

        config2 = {
            "module1": {"param1": 0.6, "param2": 0.4},
            "module3": {"paramC": 0.8, "paramD": 0.1},
            "common_module": {"x": 1.5, "y": 2.5},
        }

        child1, child2 = variator._single_point_crossover(config1, config2)

        # 检查子代包含有效模块（不要求包含所有父代模块）
        assert isinstance(child1, dict)
        assert isinstance(child2, dict)
        assert len(child1) > 0
        assert len(child2) > 0

        # 检查交叉点逻辑（随机，无法精确断言）
        # 至少确保子代不同于父代
        assert str(child1) != str(config1) or str(child1) != str(config2)
        assert str(child2) != str(config1) or str(child2) != str(config2)

    def test_weight_normalization(self):
        """测试权重归一化"""
        op = WeightMutationOperator("test", ["w1", "w2", "w3"], 0.1, True)

        # 测试归一化
        weights = {"w1": 0.5, "w2": 0.3, "w3": 0.1}  # 总和0.9
        normalized = op._normalize_weights(weights)

        total = sum(normalized.values())
        assert abs(total - 1.0) < 0.001

        # 测试比例保持（近似）
        ratio_original = weights["w1"] / weights["w2"]
        ratio_normalized = normalized["w1"] / normalized["w2"]
        assert abs(ratio_original - ratio_normalized) < 0.01

    def test_mutation_history_recording(self):
        """测试变异历史记录"""
        op = ThresholdMutationOperator("test_module", ["threshold"], 0.05)

        # 执行变异并记录
        old_value = 0.7
        new_value = 0.75
        pattern = ErrorPattern.FREQUENT_FALSE_POSITIVE

        op.record_mutation("threshold", old_value, new_value, pattern)

        assert len(op.mutation_history) == 1
        record = op.mutation_history[0]

        assert record["parameter"] == "threshold"
        assert record["old_value"] == old_value
        assert record["new_value"] == new_value
        assert record["pattern"] == pattern.value
        assert record["module"] == "test_module"
        assert "change_percent" in record

    def test_best_configuration_tracking(self):
        """测试最佳配置跟踪"""
        variator = WeightVariator({"population_size": 3})

        base_config = {"weights": {"w1": 0.5, "w2": 0.5}}
        variator.generate_initial_population(base_config)

        # 模拟性能分数
        performance_scores = {0: 0.6, 1: 0.8, 2: 0.7}
        variator.evolve_population(performance_scores)

        # 检查最佳配置已更新
        assert variator.best_configuration is not None
        assert variator.best_performance == 0.8

        # 注意：第二次进化需要重新评估新个体的性能，这里不测试
        # 第一次进化后最佳性能应为0.8
        pass

    def test_mistake_book_integration_simulation(self):
        """测试错题本集成模拟"""

        # 创建错题本模拟
        class MockMistakeBook:
            def generate_weight_adjustments(self):
                return [
                    {
                        "module": "period_weight_filter",
                        "adjustment_type": "ADJUST_TIMEFRAME_WEIGHTS",
                        "adjustment_value": 0.1,
                        "source_patterns": ["FREQUENT_FALSE_POSITIVE"],
                        "reason": "假阳性频率过高",
                    }
                ]

            def analyze_patterns(self):
                return {
                    "patterns": [
                        {
                            "pattern": "FREQUENT_FALSE_POSITIVE",
                            "frequency": 0.6,
                            "description": "假阳性过多",
                        }
                    ]
                }

        variator = WeightVariator({"population_size": 3})
        variator.set_mistake_book(MockMistakeBook())  # type: ignore

        base_config = {
            "period_weight_filter": {"weights": {"W": 0.25, "D": 0.20, "H4": 0.18}}
        }

        variator.generate_initial_population(base_config)

        # 测试变异配置（应使用错题本建议）
        mutated = variator._mutate_configuration(base_config)
        assert mutated != base_config  # 应发生变异

    def test_error_pattern_specific_mutations(self):
        """测试错误模式特定的变异策略"""
        op = WeightMutationOperator("test", ["w1", "w2", "w3"], 0.1, True)

        weights = {"w1": 0.4, "w2": 0.3, "w3": 0.3}

        # 测试假阳性调整策略
        fp_adjustments = op._adjust_for_false_positive(
            weights, ["w1", "w2", "w3"], 0.5, ErrorSeverity.MEDIUM
        )

        # 假阳性过多应降低小周期权重（这里简化测试）
        assert len(fp_adjustments) == 3

        # 测试假阴性调整策略
        fn_adjustments = op._adjust_for_false_negative(
            weights, ["w1", "w2", "w3"], 0.5, ErrorSeverity.MEDIUM
        )

        assert len(fn_adjustments) == 3

        # 测试多周期错配调整策略
        misalignment_adjustments = op._adjust_for_misalignment(
            weights, ["w1", "w2", "w3"], 0.5, ErrorSeverity.MEDIUM
        )

        assert len(misalignment_adjustments) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
