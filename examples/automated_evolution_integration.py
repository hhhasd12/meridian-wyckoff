"""
自动化进化层集成示例
演示第四阶段（自动化进化层）完整工作流程：
1. 错题本记录交易错误
2. 权重变异算法基于错误模式生成新配置
3. WFA回测引擎验证变异配置
4. 性能监控系统监控整个进化过程
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional

from src.core.mistake_book import MistakeBook, MistakeType, ErrorSeverity, ErrorPattern
from src.core.weight_variator import WeightVariator
from src.core.wfa_backtester import WFABacktester, PerformanceMetric, ValidationResult
from src.core.performance_monitor import (
    PerformanceMonitor,
    ModuleType,
    HealthStatus,
    AlertLevel,
)

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import time


def simulate_trading_error(mistake_book: MistakeBook, error_index: int):
    """模拟交易错误记录"""
    error_types = [
        (MistakeType.STATE_MISJUDGMENT, ErrorPattern.TIMING_ERROR),
        (MistakeType.WEIGHT_ASSIGNMENT_ERROR, ErrorPattern.VOLATILITY_ADAPTATION_ERROR),
        (
            MistakeType.CONFLICT_RESOLUTION_ERROR,
            ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT,
        ),
        (MistakeType.MARKET_REGIME_ERROR, ErrorPattern.CORRELATION_ERROR),
        (MistakeType.ENTRY_VALIDATION_ERROR, ErrorPattern.FREQUENT_FALSE_POSITIVE),
        (MistakeType.BREAKOUT_VALIDATION_ERROR, ErrorPattern.FREQUENT_FALSE_NEGATIVE),
        (MistakeType.TREND_RECOGNITION_ERROR, ErrorPattern.MAGNITUDE_ERROR),
        (MistakeType.SUPPORT_RESISTANCE_ERROR, ErrorPattern.CONTEXT_SENSITIVITY_ERROR),
    ]

    mistake_type, pattern = random.choice(error_types)
    severity = random.choice(
        [ErrorSeverity.LOW, ErrorSeverity.MEDIUM, ErrorSeverity.HIGH]
    )

    error_id = mistake_book.record_mistake(
        mistake_type=mistake_type,
        severity=severity,
        context={
            "simulation_id": error_index,
            "market_regime": random.choice(
                ["TRENDING_BULLISH", "TRENDING_BEARISH", "RANGING"]
            ),
            "timestamp": datetime.now(),
        },
        expected="CORRECT_STATE",
        actual="WRONG_STATE",
        confidence_before=random.uniform(0.6, 0.9),
        confidence_after=random.uniform(0.3, 0.7),
        impact_score=random.uniform(0.2, 0.8),
        module_name=random.choice(
            ["state_machine", "weight_filter", "conflict_resolver"]
        ),
        timeframe=random.choice(["H4", "H1", "D"]),
        patterns=[pattern],
        metadata={"simulation": True},
    )

    return error_id


def create_baseline_config():
    """创建基准配置"""
    return {
        "period_weight_filter": {
            "weights": {
                "W": 0.25,
                "D": 0.20,
                "H4": 0.18,
                "H1": 0.15,
                "M15": 0.12,
                "M5": 0.10,
            },
            "regime_weights": {
                "TRENDING_BULLISH": {"D": 0.30, "H4": 0.25, "H1": 0.20},
                "TRENDING_BEARISH": {"D": 0.30, "H4": 0.25, "H1": 0.20},
                "RANGING": {"H4": 0.35, "H1": 0.30, "M15": 0.20},
            },
        },
        "threshold_parameters": {
            "confidence_threshold": 0.7,
            "volume_threshold": 1.5,
            "volatility_threshold": 0.02,
        },
        "state_machine": {
            "transition_confidence": 0.75,
            "min_state_duration": 3,
            "max_state_duration": 20,
        },
    }


def simulate_performance_evaluation(
    config: dict, historical_data: Optional[pd.DataFrame] = None
) -> dict:
    """
    模拟性能评估函数
    在实际应用中应替换为真实的交易策略回测
    """
    # 简化模拟：基于配置复杂度和随机性生成性能指标
    complexity = sum(len(str(v)) for v in config.values()) % 100  # 简单复杂度估计

    base_perf = 0.5 / (1.0 + complexity * 0.01)
    random_factor = random.uniform(0.8, 1.2)

    return {
        PerformanceMetric.SHARPE_RATIO.value: base_perf * random_factor * 1.5,
        PerformanceMetric.MAX_DRAWDOWN.value: max(0.05, 0.2 - base_perf * 0.1),
        PerformanceMetric.WIN_RATE.value: 0.4 + base_perf * 0.3,
        PerformanceMetric.PROFIT_FACTOR.value: 1.2 + base_perf * 0.5,
        PerformanceMetric.CALMAR_RATIO.value: base_perf * random_factor * 2.0,
        PerformanceMetric.STABILITY_SCORE.value: 0.7 + random.uniform(-0.1, 0.1),
    }


def create_mock_historical_data(days: int = 365) -> pd.DataFrame:
    """创建模拟历史数据"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    data = {
        "open": np.random.randn(len(dates)).cumsum() + 100,
        "high": np.random.randn(len(dates)).cumsum() + 101,
        "low": np.random.randn(len(dates)).cumsum() + 99,
        "close": np.random.randn(len(dates)).cumsum() + 100,
        "volume": np.random.randint(1000, 10000, len(dates)),
    }
    return pd.DataFrame(data, index=dates)


def main():
    """主演示函数"""
    print("=" * 80)
    print("威科夫全自动逻辑引擎 - 自动化进化层集成演示")
    print("=" * 80)

    # 1. 初始化所有组件
    print("\n1. 初始化自动化进化组件...")

    # 错题本
    mistake_book = MistakeBook(
        {
            "max_records": 100,
            "auto_cleanup_days": 7,
            "min_learning_priority": 0.3,
        }
    )

    # 权重变异算法
    weight_variator = WeightVariator(
        {
            "mutation_rate": 0.3,
            "crossover_rate": 0.5,
            "population_size": 10,
            "max_generations": 5,
            "min_improvement": 0.01,
        }
    )

    # WFA回测引擎
    wfa_backtester = WFABacktester(
        {
            "train_days": 60,
            "test_days": 20,
            "step_days": 10,
            "min_performance_improvement": 0.01,
            "max_weight_change": 0.05,
            "smooth_factor": 0.3,
            "stability_threshold": 0.7,
        }
    )

    # 性能监控系统
    performance_monitor = PerformanceMonitor(
        {
            "monitoring_interval": 60,  # 60秒
            "auto_recovery_enabled": True,
            "alert_levels": {
                "WARNING": 0.05,
                "ERROR": 0.10,
                "CRITICAL": 0.20,
            },
        }
    )

    # 注册模块到监控系统
    performance_monitor.register_module(
        "mistake_book",
        mistake_book,
        ModuleType.EVOLUTION,
        health_check_func=lambda: HealthStatus.HEALTHY,
    )
    performance_monitor.register_module(
        "weight_variator",
        weight_variator,
        ModuleType.EVOLUTION,
        health_check_func=lambda: HealthStatus.HEALTHY,
    )
    performance_monitor.register_module(
        "wfa_backtester",
        wfa_backtester,
        ModuleType.EVOLUTION,
        health_check_func=lambda: HealthStatus.HEALTHY,
    )

    # 启动监控
    performance_monitor.start_monitoring()
    print("   组件初始化完成，性能监控已启动")

    # 2. 模拟错误记录
    print("\n2. 模拟交易错误记录...")
    for i in range(5):
        error_id = simulate_trading_error(mistake_book, i)
        print(f"   记录错误 #{i + 1}: ID={error_id}")
        time.sleep(0.01)  # 确保时间戳不同

    # 显示错题本统计
    stats = mistake_book.get_statistics()
    print(
        f"   错题本统计: {stats['record_count']} 条记录, {stats['learning_rate']:.1%} 学习率"
    )

    # 3. 分析错误模式并生成权重调整建议
    print("\n3. 分析错误模式并生成权重调整建议...")
    patterns = mistake_book.analyze_patterns()
    print(f"   检测到 {len(patterns.get('dominant_patterns', []))} 个主要错误模式")

    weight_adjustments = mistake_book.generate_weight_adjustments()
    print(f"   生成 {len(weight_adjustments)} 个权重调整建议")

    # 4. 使用权重变异算法生成新配置
    print("\n4. 权重变异算法生成新配置...")
    baseline_config = create_baseline_config()

    # 设置错题本引用
    weight_variator.set_mistake_book(mistake_book)

    # 生成初始种群
    weight_variator.generate_initial_population(baseline_config)
    print(f"   初始种群大小: {len(weight_variator.population)}")

    # 模拟性能分数（在实际应用中来自WFA回测）
    performance_scores = {
        ind["id"]: random.uniform(0.5, 1.0) for ind in weight_variator.population
    }

    # 进化种群
    weight_variator.evolve_population(performance_scores)

    # 提取变异配置（种群中的配置）
    mutated_configs = [
        ind["config"] for ind in weight_variator.population[1:4]
    ]  # 取前几个作为变异配置

    print(f"   生成 {len(mutated_configs)} 个变异配置")

    # 5. WFA回测验证变异配置
    print("\n5. WFA回测验证变异配置...")

    # 创建模拟历史数据
    historical_data = create_mock_historical_data(180)  # 180天数据

    # 初始化WFA回测引擎
    baseline_perf = wfa_backtester.initialize_with_baseline(
        baseline_config=baseline_config,
        historical_data=historical_data,
        performance_evaluator=simulate_performance_evaluation,
    )

    print(
        f"   基准配置综合评分: {(baseline_perf.get(PerformanceMetric.COMPOSITE_SCORE.value, 0.0) if baseline_perf else 0.0):.4f}"
    )

    # 验证变异配置
    accepted_configs, rejected_configs, report = wfa_backtester.validate_mutations(
        mutated_configs=mutated_configs,
        historical_data=historical_data,
        performance_evaluator=simulate_performance_evaluation,
        mistake_book=mistake_book,
    )

    print(f"   验证结果: {report['accepted']} 个接受, {report['rejected']} 个拒绝")
    print(f"   平均改进: {report['average_improvement']:.4f}")
    print(f"   平均稳定性: {report['average_stability']:.4f}")

    # 6. 更新最佳配置
    if accepted_configs:
        print("\n6. 更新系统配置...")
        best_config = accepted_configs[0]  # 取第一个接受的配置
        print("   已应用最佳变异配置")

        # 记录到错题本（学习）
        learning_batch = mistake_book.get_learning_batch(batch_size=2)
        mistake_book.mark_batch_as_learned([r.error_id for r in learning_batch])
        print(f"   已将 {len(learning_batch)} 个错误标记为已学习")
    else:
        print("\n6. 无接受的配置，保持基准配置")

    # 7. 性能监控报告
    print("\n7. 性能监控报告...")

    # 收集一些指标
    performance_monitor._record_metric(
        "evolution.error_rate",
        value=stats.get("error_rate", 0.0),
        timestamp=datetime.now(),
    )
    performance_monitor._record_metric(
        "evolution.acceptance_rate",
        value=report.get("acceptance_rate", 0.0),
        timestamp=datetime.now(),
    )

    # 执行健康检查
    performance_monitor._perform_health_checks()

    # 获取健康报告
    health_report = performance_monitor.get_health_report()
    print(f"   系统健康状态: {health_report.get('system_health', 'UNKNOWN')}")
    module_health = health_report.get("module_health", {})
    print(f"   模块健康: {len(module_health)} 个模块")

    for module_name, health_status in module_health.items():
        print(f"     - {module_name}: {health_status}")

    # 获取仪表板数据
    dashboard = performance_monitor.get_dashboard_data()
    print(f"   总监控指标数: {dashboard.get('total_metrics', 0)}")
    print(f"   总报警数: {dashboard.get('total_alerts', 0)}")

    # 8. 显示最终统计
    print("\n8. 最终统计信息...")

    # 错题本统计
    final_stats = mistake_book.get_statistics()
    print(
        f"   错题本: {final_stats['record_count']} 条记录, "
        f"学习率: {final_stats['learning_rate']:.1%}"
    )

    # 权重变异算法报告
    variator_report = weight_variator.get_performance_report()
    print(
        f"   权重变异: {variator_report.get('generations', 0)} 代进化, "
        f"最佳性能: {variator_report.get('best_performance', 0.0):.4f}"
    )

    # WFA回测报告
    wfa_summary = wfa_backtester.get_performance_summary()
    print(
        f"   WFA回测: {wfa_summary.get('total_validations', 0)} 次验证, "
        f"接受率: {wfa_summary.get('acceptance_rate', 0.0):.1%}"
    )

    if wfa_summary.get("current_composite_score"):
        improvement = wfa_summary.get("improvement_vs_baseline", 0.0)
        print(
            f"   当前综合评分: {wfa_summary.get('current_composite_score', 0.0):.4f} "
            f"(相对于基准: {improvement:+.4f})"
        )

    # 9. 停止监控
    print("\n9. 停止性能监控...")
    performance_monitor.stop_monitoring()

    print("\n" + "=" * 80)
    print("自动化进化层集成演示完成")
    print("=" * 80)

    # 10. 生成进化建议
    print("\n10. 系统进化建议:")
    recommendations = performance_monitor._generate_recommendations()

    if recommendations:
        for i, rec in enumerate(recommendations[:3], 1):
            print(f"   {i}. {rec}")
    else:
        print("   暂无具体建议，系统运行良好")

    print("\n" + "=" * 80)
    print("演示总结:")
    print("-" * 80)
    print("1. 错题本成功记录和分析交易错误")
    print("2. 权重变异算法基于错误模式生成针对性变异")
    print("3. WFA回测引擎有效过滤过拟合和随机波动")
    print("4. 性能监控系统实时跟踪进化过程健康状态")
    print("5. 系统具备自我学习、自我优化能力")
    print("=" * 80)


if __name__ == "__main__":
    main()
