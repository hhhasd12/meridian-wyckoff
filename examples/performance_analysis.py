"""
性能分析与优化建议
分析威科夫全自动逻辑引擎的计算瓶颈，提供优化建议

分析内容：
1. 各模块执行时间测量
2. 内存使用分析
3. 并行计算潜力评估
4. 缓存策略建议
5. 优化建议汇总
"""

import time
import cProfile
import pstats
import io
import tracemalloc
from datetime import datetime
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.plugins.market_regime.detector import RegimeDetector
from src.plugins.perception.fvg_detector import FVGDetector
from src.plugins.pattern_detection.tr_detector import TRDetector
from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter
from src.plugins.signal_validation.breakout_validator import BreakoutValidator
from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter
from src.plugins.signal_validation.conflict_resolver import ConflictResolutionManager
from src.plugins.signal_validation.micro_entry_validator import MicroEntryValidator
from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
    WyckoffStateMachine,
)


class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(self):
        self.results = {}
        self.memory_snapshots = {}

    def generate_test_data(self, bars: int = 1000) -> pd.DataFrame:
        """生成测试数据"""
        dates = pd.date_range(end=datetime.now(), periods=bars, freq="1H")

        # 生成价格序列
        base_price = 50000
        returns = np.random.randn(bars) * 0.01
        prices = base_price * (1 + returns.cumsum())

        data = pd.DataFrame(
            {
                "open": prices * (1 + np.random.randn(bars) * 0.001),
                "high": prices * (1 + np.abs(np.random.randn(bars)) * 0.002),
                "low": prices * (1 - np.abs(np.random.randn(bars)) * 0.002),
                "close": prices,
                "volume": np.random.randint(1000, 10000, bars),
            },
            index=dates,
        )

        return data

    def measure_module_performance(self) -> Dict[str, Any]:
        """测量各模块性能"""
        print("📊 开始性能分析...")
        print("=" * 60)

        # 生成测试数据
        test_data = self.generate_test_data(500)  # 500根K线

        # 初始化模块
        modules = {
            "market_regime": RegimeDetector(),
            "fvg_detector": FVGDetector(),
            "tr_detector": TRDetector(),
            "curve_fitter": CurveBoundaryFitter(),
            "breakout_validator": BreakoutValidator(),
            "period_filter": PeriodWeightFilter(),
            "conflict_resolver": ConflictResolutionManager(),
            "entry_validator": MicroEntryValidator(),
            "state_machine": WyckoffStateMachine(),
        }

        performance_results = {}

        for module_name, module in modules.items():
            print(f"🔍 测试模块: {module_name}")

            try:
                # 测量执行时间
                start_time = time.perf_counter()

                if module_name == "market_regime":
                    result = module.detect(test_data)
                elif module_name == "fvg_detector":
                    result = module.detect(test_data)
                elif module_name == "tr_detector":
                    result = module.detect(test_data)
                elif module_name == "curve_fitter":
                    result = module.analyze(test_data)
                elif module_name == "breakout_validator":
                    # 需要突破方向参数
                    result = module.validate(
                        test_data, "bullish", test_data["close"].mean()
                    )
                elif module_name == "period_filter":
                    # 需要多时间框架数据
                    data_dict = {"H4": test_data, "H1": test_data}
                    result = module.calculate_weights(data_dict, "TRENDING")
                elif module_name == "conflict_resolver":
                    # 需要时间框架状态
                    timeframe_states = {
                        "H4": {"state": "ACCUMULATION", "confidence": 0.7},
                        "H1": {"state": "DISTRIBUTION", "confidence": 0.6},
                    }
                    result = module.detect_conflicts(
                        timeframe_states, {"H4": 0.6, "H1": 0.4}
                    )
                elif module_name == "entry_validator":
                    # 需要突破状态
                    result = module.validate(
                        {"H4": test_data}, {"breakout_direction": "bullish"}
                    )
                elif module_name == "state_machine":
                    # 需要状态机输入
                    state_input = {
                        "price_data": test_data,
                        "market_regime": "TRENDING",
                        "trading_range_info": {"has_trading_range": False},
                        "timeframe_weights": {"H4": 0.6, "H1": 0.4},
                    }
                    result = module.analyze(state_input)
                else:
                    result = None

                end_time = time.perf_counter()
                execution_time = end_time - start_time

                # 记录结果
                performance_results[module_name] = {
                    "execution_time_ms": execution_time * 1000,
                    "success": result is not None,
                    "result_size": len(str(result)) if result else 0,
                }

                print(f"   ⏱️  执行时间: {execution_time * 1000:.2f} ms")
                print(f"   ✅ 状态: {'成功' if result is not None else '失败'}")

            except Exception as e:
                print(f"   ❌ 错误: {e}")
                performance_results[module_name] = {
                    "execution_time_ms": 0,
                    "success": False,
                    "error": str(e),
                }

        print("=" * 60)
        print("✅ 性能分析完成")

        self.results = performance_results
        return performance_results

    def analyze_bottlenecks(self) -> Dict[str, Any]:
        """分析性能瓶颈"""
        if not self.results:
            self.measure_module_performance()

        print("\n🔎 性能瓶颈分析...")
        print("=" * 60)

        # 找出最慢的模块
        slow_modules = sorted(
            [
                (name, data["execution_time_ms"])
                for name, data in self.results.items()
                if data.get("success", False)
            ],
            key=lambda x: x[1],
            reverse=True,
        )

        bottlenecks = []

        for module_name, exec_time in slow_modules[:3]:  # 前3个最慢的模块
            bottlenecks.append(
                {
                    "module": module_name,
                    "execution_time_ms": exec_time,
                    "percentage_of_total": exec_time
                    / sum([d["execution_time_ms"] for d in self.results.values()])
                    * 100,
                }
            )

        # 分析总体性能
        total_time = sum([d["execution_time_ms"] for d in self.results.values()])
        avg_time = total_time / len(self.results)

        analysis = {
            "total_execution_time_ms": total_time,
            "average_module_time_ms": avg_time,
            "module_count": len(self.results),
            "bottlenecks": bottlenecks,
            "performance_rating": self._calculate_performance_rating(total_time),
        }

        # 显示结果
        print(f"📈 总体执行时间: {total_time:.2f} ms")
        print(f"📊 平均模块时间: {avg_time:.2f} ms")
        print(f"🔧 分析模块数量: {len(self.results)}")

        print("\n🚧 性能瓶颈 (前3名):")
        for i, bottleneck in enumerate(bottlenecks, 1):
            print(
                f"  {i}. {bottleneck['module']}: {bottleneck['execution_time_ms']:.2f} ms "
                f"({bottleneck['percentage_of_total']:.1f}%)"
            )

        print(f"\n🏆 性能评级: {analysis['performance_rating']}")

        return analysis

    def _calculate_performance_rating(self, total_time_ms: float) -> str:
        """计算性能评级"""
        if total_time_ms < 100:
            return "优秀 ⭐⭐⭐⭐⭐"
        elif total_time_ms < 500:
            return "良好 ⭐⭐⭐⭐"
        elif total_time_ms < 1000:
            return "一般 ⭐⭐⭐"
        elif total_time_ms < 2000:
            return "需改进 ⭐⭐"
        else:
            return "需优化 ⭐"

    def generate_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """生成优化建议"""
        print("\n💡 优化建议生成...")
        print("=" * 60)

        recommendations = []

        # 基于瓶颈分析的优化建议
        bottlenecks = self.analyze_bottlenecks().get("bottlenecks", [])

        for bottleneck in bottlenecks:
            module_name = bottleneck["module"]
            exec_time = bottleneck["execution_time_ms"]

            if exec_time > 100:  # 超过100ms的模块需要优化
                rec = {
                    "module": module_name,
                    "issue": f"执行时间过长 ({exec_time:.2f} ms)",
                    "recommendation": self._get_module_specific_recommendation(
                        module_name
                    ),
                    "priority": "高" if exec_time > 200 else "中",
                }
                recommendations.append(rec)

        # 通用优化建议
        general_recommendations = [
            {
                "module": "系统级",
                "issue": "模块间数据传递开销",
                "recommendation": "实现数据缓存机制，避免重复计算",
                "priority": "中",
            },
            {
                "module": "系统级",
                "issue": "单线程执行",
                "recommendation": "实现并行计算，特别是独立模块可并行执行",
                "priority": "高",
            },
            {
                "module": "数据管道",
                "issue": "数据加载延迟",
                "recommendation": "预加载和缓存历史数据，减少I/O等待",
                "priority": "中",
            },
            {
                "module": "状态机",
                "issue": "状态计算复杂度高",
                "recommendation": "实现状态缓存和增量更新，避免全量重新计算",
                "priority": "高",
            },
        ]

        recommendations.extend(general_recommendations)

        # 显示建议
        print("📋 优化建议汇总:")
        for i, rec in enumerate(recommendations, 1):
            print(f"\n  {i}. [{rec['priority']}优先级] {rec['module']}")
            print(f"     问题: {rec['issue']}")
            print(f"     建议: {rec['recommendation']}")

        return recommendations

    def _get_module_specific_recommendation(self, module_name: str) -> str:
        """获取模块特定的优化建议"""
        recommendations = {
            "market_regime": "优化技术指标计算，使用滑动窗口算法减少重复计算",
            "fvg_detector": "实现FVG检测缓存，相同K线范围的检测结果可复用",
            "tr_detector": "优化枢轴点检测算法，使用增量更新而非全量重新计算",
            "curve_fitter": "简化曲线拟合算法，或降低拟合精度以获得性能提升",
            "state_machine": "实现状态机快照和恢复机制，避免每次从头计算",
            "conflict_resolver": "缓存冲突检测结果，相同输入产生相同输出时可快速返回",
            "period_filter": "预计算周期权重表，避免实时动态计算",
        }

        return recommendations.get(module_name, "检查算法复杂度，考虑优化或替换算法")

    def profile_system(self, profile_seconds: int = 10):
        """使用cProfile进行系统性能分析"""
        print(f"\n🔬 开始系统级性能分析 ({profile_seconds}秒)...")
        print("=" * 60)

        # 开始性能分析
        pr = cProfile.Profile()
        pr.enable()

        # 运行测试任务
        self._run_profile_task(profile_seconds)

        pr.disable()

        # 分析结果
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats(20)  # 显示前20个最耗时的函数

        print("📈 性能分析结果 (前20个最耗时函数):")
        print(s.getvalue())

        # 保存结果到文件
        with open("performance_profile.txt", "w") as f:
            f.write(s.getvalue())

        print("✅ 性能分析结果已保存到 performance_profile.txt")

    def _run_profile_task(self, duration_seconds: int):
        """运行性能分析任务"""
        test_data = self.generate_test_data(1000)

        # 初始化模块
        regime = RegimeDetector()
        fvg = FVGDetector()
        tr = TRDetector()
        state_machine = WyckoffStateMachine()

        end_time = time.time() + duration_seconds
        iterations = 0

        while time.time() < end_time:
            # 执行一系列操作
            regime.detect(test_data)
            fvg.detect(test_data)
            tr.detect(test_data)

            # 状态机分析
            state_input = {
                "price_data": test_data,
                "market_regime": "TRENDING",
                "trading_range_info": {"has_trading_range": False},
                "timeframe_weights": {"H4": 0.6, "H1": 0.4},
            }
            state_machine.analyze(state_input)

            iterations += 1

        print(f"  完成 {iterations} 次迭代")

    def analyze_memory_usage(self):
        """分析内存使用"""
        print("\n🧠 内存使用分析...")
        print("=" * 60)

        tracemalloc.start()

        # 执行内存密集型操作
        test_data = self.generate_test_data(5000)  # 大量数据

        # 初始化多个模块
        modules = []
        for _ in range(10):
            modules.append(WyckoffStateMachine())

        # 获取内存快照
        snapshot = tracemalloc.take_snapshot()

        # 显示内存使用统计
        top_stats = snapshot.statistics("lineno")

        print("📊 内存使用统计 (前10名):")
        for stat in top_stats[:10]:
            print(f"  {stat}")

        tracemalloc.stop()

    def generate_optimization_plan(self) -> Dict[str, Any]:
        """生成完整的优化计划"""
        print("\n🎯 生成完整优化计划...")
        print("=" * 60)

        # 收集所有分析结果
        performance_results = self.measure_module_performance()
        bottleneck_analysis = self.analyze_bottlenecks()
        recommendations = self.generate_optimization_recommendations()

        # 创建优化计划
        optimization_plan = {
            "analysis_date": datetime.now().isoformat(),
            "performance_summary": {
                "total_execution_time_ms": bottleneck_analysis[
                    "total_execution_time_ms"
                ],
                "performance_rating": bottleneck_analysis["performance_rating"],
                "bottleneck_count": len(bottleneck_analysis["bottlenecks"]),
            },
            "critical_issues": [
                rec for rec in recommendations if rec["priority"] == "高"
            ],
            "optimization_phases": [
                {
                    "phase": 1,
                    "name": "快速优化",
                    "duration": "1-2周",
                    "tasks": [
                        "实现数据缓存机制",
                        "优化最慢的3个模块算法",
                        "添加性能监控指标",
                    ],
                    "expected_improvement": "30-50% 性能提升",
                },
                {
                    "phase": 2,
                    "name": "中级优化",
                    "duration": "2-4周",
                    "tasks": [
                        "实现并行计算框架",
                        "优化内存使用模式",
                        "添加懒加载机制",
                    ],
                    "expected_improvement": "50-70% 性能提升",
                },
                {
                    "phase": 3,
                    "name": "高级优化",
                    "duration": "4-8周",
                    "tasks": [
                        "重构高复杂度算法",
                        "实现分布式计算支持",
                        "添加实时性能调优",
                    ],
                    "expected_improvement": "70-90% 性能提升",
                },
            ],
            "immediate_actions": [
                "启用性能监控日志",
                "设置性能基准测试",
                "优先优化高优先级模块",
            ],
        }

        # 显示优化计划
        print("📋 优化计划概览:")
        print(f"\n📅 分析日期: {optimization_plan['analysis_date']}")
        print(
            f"📊 总体性能: {optimization_plan['performance_summary']['performance_rating']}"
        )
        print(
            f"⏱️  总执行时间: {optimization_plan['performance_summary']['total_execution_time_ms']:.2f} ms"
        )

        print(f"\n🚨 关键问题 ({len(optimization_plan['critical_issues'])}个):")
        for issue in optimization_plan["critical_issues"]:
            print(f"  • {issue['module']}: {issue['issue']}")

        print(f"\n📈 优化阶段:")
        for phase in optimization_plan["optimization_phases"]:
            print(f"\n  阶段 {phase['phase']}: {phase['name']}")
            print(f"     时长: {phase['duration']}")
            print(f"     任务: {', '.join(phase['tasks'])}")
            print(f"     预期提升: {phase['expected_improvement']}")

        print(f"\n🎯 立即行动:")
        for action in optimization_plan["immediate_actions"]:
            print(f"  • {action}")

        # 保存优化计划
        import json

        with open("optimization_plan.json", "w") as f:
            json.dump(optimization_plan, f, indent=2, default=str)

        print("\n✅ 优化计划已保存到 optimization_plan.json")

        return optimization_plan


def main():
    """主函数"""
    print("=" * 80)
    print("威科夫全自动逻辑引擎 - 性能分析与优化建议")
    print("=" * 80)
    print()
    print("本工具将分析系统性能，识别瓶颈，并提供优化建议。")
    print()

    analyzer = PerformanceAnalyzer()

    try:
        # 1. 测量模块性能
        analyzer.measure_module_performance()

        # 2. 分析瓶颈
        analyzer.analyze_bottlenecks()

        # 3. 生成优化建议
        analyzer.generate_optimization_recommendations()

        # 4. 系统级性能分析 (可选，耗时)
        print("\n" + "=" * 60)
        run_profiling = input("是否运行系统级性能分析? (y/n): ").lower().strip()
        if run_profiling == "y":
            analyzer.profile_system(5)  # 5秒分析

        # 5. 内存分析 (可选)
        print("\n" + "=" * 60)
        run_memory = input("是否运行内存使用分析? (y/n): ").lower().strip()
        if run_memory == "y":
            analyzer.analyze_memory_usage()

        # 6. 生成完整优化计划
        print("\n" + "=" * 60)
        generate_plan = input("是否生成完整优化计划? (y/n): ").lower().strip()
        if generate_plan == "y":
            analyzer.generate_optimization_plan()

        print("\n" + "=" * 80)
        print("✅ 性能分析完成!")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n\n🛑 分析被用户中断")
    except Exception as e:
        print(f"\n❌ 分析过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
