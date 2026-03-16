#!/usr/bin/env python3
"""
权重变异器综合测试脚本
全面测试权重变异器的核心功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.weight_variator import (
    WeightVariator,
    ThresholdMutationOperator,
    WeightMutationOperator,
    MutationType
)

# 使用实际的错题本枚举
from src.plugins.self_correction.mistake_book import ErrorPattern, ErrorSeverity

def test_mutation_operator_base_class():
    """测试变异算子基类"""
    print("=== 测试变异算子基类 ===")
    
    # 创建变异算子基类实例
    operator = ThresholdMutationOperator(
        target_module="test_module",
        parameters=["test_param"],
        max_change=0.05
    )
    
    # 测试变异方向计算
    direction_fp = operator.get_mutation_direction(ErrorPattern.FREQUENT_FALSE_POSITIVE)
    direction_fn = operator.get_mutation_direction(ErrorPattern.FREQUENT_FALSE_NEGATIVE)
    
    print(f"假阳性变异方向: {direction_fp} (应为正数)")
    print(f"假阴性变异方向: {direction_fn} (应为负数)")
    
    assert direction_fp > 0, "假阳性变异方向应为正数"
    assert direction_fn < 0, "假阴性变异方向应为负数"
    
    # 测试变异幅度计算
    magnitude = operator.calculate_mutation_magnitude(0.5, ErrorSeverity.MEDIUM)
    print(f"变异幅度: {magnitude:.3f} (频率0.5，中等严重度)")
    
    assert 0 <= magnitude <= 0.05, f"变异幅度应在0-0.05之间，实际为{magnitude}"
    
    print("变异算子基类测试通过")

def test_threshold_mutation_operator():
    """测试阈值变异算子"""
    print("\n=== 测试阈值变异算子 ===")
    
    operator = ThresholdMutationOperator(
        target_module="threshold_module",
        parameters=["confidence_threshold", "volume_threshold"],
        max_change=0.05
    )
    
    # 测试不同类型错误的变异
    test_cases = [
        (0.7, ErrorPattern.FREQUENT_FALSE_POSITIVE, 0.3, ErrorSeverity.MEDIUM, "假阳性"),
        (0.7, ErrorPattern.FREQUENT_FALSE_NEGATIVE, 0.3, ErrorSeverity.MEDIUM, "假阴性"),
        (0.7, ErrorPattern.TIMING_ERROR, 0.3, ErrorSeverity.MEDIUM, "时机错误"),
        (0.7, ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT, 0.3, ErrorSeverity.MEDIUM, "多周期错配"),
    ]
    
    for current_value, pattern, frequency, severity, description in test_cases:
        new_value = operator.mutate(current_value, pattern, frequency, severity)
        change_percent = abs(new_value - current_value) / current_value * 100
        
        print(f"{description}: {current_value:.3f} -> {new_value:.3f} (变化: {change_percent:.1f}%)")
        
        # 验证变化幅度不超过最大变化
        assert change_percent <= 5.0, f"{description}变化幅度超过5%: {change_percent:.1f}%"
        
        # 验证新值在合理范围内
        assert new_value >= 0.01, f"{description}新值小于最小值0.01: {new_value}"
    
    print("阈值变异算子测试通过")

def test_weight_mutation_operator():
    """测试权重变异算子"""
    print("\n=== 测试权重变异算子 ===")
    
    operator = WeightMutationOperator(
        target_module="period_weight_filter",
        parameters=["W", "D", "H4", "H1", "M15", "M5"],
        max_change=0.05,
        weight_sum_constraint=True
    )
    
    # 测试权重
    weights = {
        "W": 0.30,
        "D": 0.25,
        "H4": 0.20,
        "H1": 0.15,
        "M15": 0.07,
        "M5": 0.03
    }
    
    print(f"原始权重: {weights}")
    print(f"权重标准差: {calculate_std_dev(weights):.4f}")
    
    # 测试不同错误模式的变异
    test_patterns = [
        (ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT, "多周期错配"),
        (ErrorPattern.FREQUENT_FALSE_POSITIVE, "假阳性"),
        (ErrorPattern.FREQUENT_FALSE_NEGATIVE, "假阴性"),
    ]
    
    for pattern, description in test_patterns:
        new_weights = operator.mutate(
            value=weights,
            pattern=pattern,
            frequency=0.5,
            severity=ErrorSeverity.MEDIUM
        )
        
        print(f"\n{description}调整后:")
        total_change = 0
        for key in weights:
            if key in new_weights:
                change = abs(new_weights[key] - weights[key]) / weights[key] * 100
                total_change += abs(new_weights[key] - weights[key])
                print(f"  {key}: {weights[key]:.3f} -> {new_weights[key]:.3f} (变化: {change:.1f}%)")
        
        # 验证权重总和为1
        total = sum(new_weights.values())
        print(f"  权重总和: {total:.3f}")
        assert abs(total - 1.0) < 0.001, f"权重总和不为1: {total}"
        
        # 验证每个权重的变化幅度
        for key in weights:
            if key in new_weights:
                change = abs(new_weights[key] - weights[key]) / weights[key]
                assert change <= 0.055, f"权重 {key} 变化幅度超过5.5%: {change:.1%}"
    
    print("权重变异算子测试通过")

def calculate_std_dev(weights):
    """计算权重标准差"""
    import numpy as np
    weight_values = list(weights.values())
    return np.std(weight_values) if len(weight_values) > 1 else 0

def test_weight_variator_evolution():
    """测试权重变异器进化过程"""
    print("\n=== 测试权重变异器进化过程 ===")
    
    import random
    
    # 创建权重变异器
    variator = WeightVariator(
        {
            "mutation_rate": 0.3,
            "crossover_rate": 0.5,
            "max_mutation_percent": 0.05,
            "population_size": 10,
            "selection_pressure": 2.0,
            "enable_elitism": True,
        }
    )
    
    # 基础配置
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
        },
        "threshold_parameters": {
            "confidence_threshold": 0.7,
            "volume_threshold": 1.5,
            "breakout_threshold": 0.02,
        },
    }
    
    # 生成初始种群
    variator.generate_initial_population(base_config)
    
    print(f"初始种群大小: {len(variator.population)}")
    print(f"变异算子数量: {len(variator.mutation_operators)}")
    
    # 模拟多代进化
    generations = 5
    for gen in range(generations):
        # 模拟性能分数（在实际应用中来自WFA回测）
        performance_scores = {
            i: 0.5 + (i / len(variator.population)) * 0.4 + random.random() * 0.1
            for i in range(len(variator.population))
        }
        
        # 执行进化
        variator.evolve_population(performance_scores)
        
        # 获取性能报告
        report = variator.get_performance_report()
        
        print(f"\n第{gen+1}代:")
        print(f"  平均性能: {report['latest_avg_performance']:.3f}")
        print(f"  最佳性能: {report['best_performance']:.3f}")
        print(f"  种群大小: {report['population_size']}")
    
    # 获取最终最佳配置
    best_config = variator.get_best_configuration()
    if best_config:
        print("\n最终最佳配置:")
        
        # 显示周期权重
        if "period_weight_filter" in best_config:
            weights = best_config["period_weight_filter"].get("weights", {})
            print("周期权重:")
            for tf, w in weights.items():
                print(f"  {tf}: {w:.3f}")
        
        # 显示阈值参数
        if "threshold_parameters" in best_config:
            thresholds = best_config["threshold_parameters"]
            print("阈值参数:")
            for param, value in thresholds.items():
                print(f"  {param}: {value:.3f}")
    
    print("权重变异器进化测试通过")

def test_error_handling():
    """测试错误处理"""
    print("\n=== 测试错误处理 ===")
    
    operator = ThresholdMutationOperator(
        target_module="test_module",
        parameters=["test_param"],
        max_change=0.05
    )
    
    # 测试无效输入类型
    try:
        operator.mutate("invalid", ErrorPattern.FREQUENT_FALSE_POSITIVE, 0.5, ErrorSeverity.MEDIUM)
        assert False, "应抛出TypeError"
    except TypeError as e:
        print(f"类型错误处理正常: {e}")
    
    # 测试权重变异算子的无效输入
    weight_operator = WeightMutationOperator(
        target_module="test_module",
        parameters=["param1", "param2"],
        max_change=0.05
    )
    
    try:
        weight_operator.mutate("invalid", ErrorPattern.FREQUENT_FALSE_POSITIVE, 0.5, ErrorSeverity.MEDIUM)
        assert False, "应抛出TypeError"
    except TypeError as e:
        print(f"权重类型错误处理正常: {e}")
    
    print("错误处理测试通过")

def main():
    """主测试函数"""
    print("开始权重变异器综合测试...")
    
    import random
    random.seed(42)  # 设置随机种子以确保可重复性
    
    try:
        test_mutation_operator_base_class()
        test_threshold_mutation_operator()
        test_weight_mutation_operator()
        test_weight_variator_evolution()
        test_error_handling()
        
        print("\n所有综合测试通过！")
        return 0
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())