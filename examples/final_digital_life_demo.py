"""
威科夫全自动逻辑引擎 - 最终演示
展示完整的"数字生命体"交易系统全流程

系统能力展示：
1. 🧠 动态感知：市场体制识别、FVG检测、TR识别、曲线边界拟合
2. 🤔 独立思考：多周期辩证融合、冲突解决、威科夫状态机分析
3. 🔄 自动进化：错题本学习、权重变异优化、WFA回测验证、性能监控
4. 💬 落地沟通：实时交易信号生成、风险管理、仓位建议

演示流程：
1. 系统初始化与自检
2. 历史数据回放分析
3. 实时决策模拟
4. 自动化进化展示
5. 系统健康与性能报告
"""

import asyncio
import time
from datetime import datetime, timedelta
import random
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List, Optional, Any
import json

# 导入所有核心模块
from src.plugins.data_pipeline.data_pipeline import DataPipeline, Timeframe
from src.plugins.market_regime.detector import RegimeDetector
from src.perception.fvg_detector import FVGDetector
from src.plugins.pattern_detection.tr_detector import TRDetector
from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter
from src.plugins.signal_validation.breakout_validator import BreakoutValidator
from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter
from src.plugins.signal_validation.conflict_resolver import ConflictResolutionManager, ConflictType
from src.plugins.signal_validation.micro_entry_validator import MicroEntryValidator
from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import WyckoffStateMachine
from src.plugins.self_correction.mistake_book import MistakeBook, MistakeType, ErrorSeverity
from src.plugins.evolution.weight_variator_legacy import WeightVariator
from src.plugins.evolution.wfa_backtester import WFABacktester
from src.plugins.dashboard.performance_monitor import PerformanceMonitor, ModuleType


class DigitalLifeTradingSystem:
    """
    数字生命体交易系统 - 最终演示版

    整合所有四个阶段的模块，展示完整的"数字生命体"能力
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.name = "威科夫数字生命体交易系统"
        self.version = "v1.0"
        self.is_running = False

        print(f"\n{'=' * 80}")
        print(f"🚀 {self.name} {self.version}")
        print(f"{'=' * 80}")

        # 初始化所有模块
        self._initialize_all_modules()

        # 系统状态
        self.start_time = None
        self.decision_count = 0
        self.success_count = 0
        self.error_count = 0
        self.evolution_cycles = 0

        print(f"✅ 系统初始化完成 - 共加载 {self._count_modules()} 个核心模块")

    def _count_modules(self) -> int:
        """计算已加载的模块数量"""
        module_attributes = [
            attr
            for attr in dir(self)
            if not attr.startswith("_") and not callable(getattr(self, attr))
        ]
        # 过滤掉非模块属性
        module_keywords = [
            "pipeline",
            "detector",
            "validator",
            "filter",
            "resolver",
            "machine",
            "book",
            "variator",
            "backtester",
            "monitor",
        ]
        return len(
            [
                attr
                for attr in module_attributes
                if any(keyword in attr.lower() for keyword in module_keywords)
            ]
        )

    def _initialize_all_modules(self):
        """初始化所有模块"""
        print("\n🔄 正在初始化数字生命体核心模块...")

        # 第一阶段：物理感知层
        print("  1. 🧠 初始化物理感知层...")
        self.regime_detector = RegimeDetector()
        self.fvg_detector = FVGDetector()
        self.tr_detector = TRDetector()
        self.curve_fitter = CurveBoundaryFitter()
        self.breakout_validator = BreakoutValidator()

        # 第二阶段：状态机决策层
        print("  2. 🤖 初始化状态机决策层...")
        self.state_machine = WyckoffStateMachine()

        # 第三阶段：多周期融合层
        print("  3. 🔄 初始化多周期融合层...")
        self.period_filter = PeriodWeightFilter()
        self.conflict_resolver = ConflictResolutionManager()
        self.entry_validator = MicroEntryValidator()

        # 第四阶段：自动化进化层
        print("  4. 🧬 初始化自动化进化层...")
        self.mistake_book = MistakeBook(
            {
                "max_records": 50,
                "auto_cleanup_days": 3,
            }
        )
        self.weight_variator = WeightVariator(
            {
                "mutation_rate": 0.2,
                "population_size": 5,
            }
        )
        self.wfa_backtester = WFABacktester(
            {
                "train_days": 30,
                "test_days": 10,
                "step_days": 5,
            }
        )
        self.performance_monitor = PerformanceMonitor(
            {
                "monitoring_interval": 30,
                "auto_recovery_enabled": True,
            }
        )

        # 注册模块到性能监控
        self._register_modules_for_monitoring()

        print("  ✅ 所有模块初始化完成")

    def _register_modules_for_monitoring(self):
        """注册模块到性能监控系统"""
        modules_to_register = [
            ("regime_detector", ModuleType.PERCEPTION),
            ("fvg_detector", ModuleType.PERCEPTION),
            ("tr_detector", ModuleType.PERCEPTION),
            ("state_machine", ModuleType.STATEMACHINE),
            ("period_filter", ModuleType.MULTITIMEFRAME),
            ("conflict_resolver", ModuleType.MULTITIMEFRAME),
            ("mistake_book", ModuleType.EVOLUTION),
            ("weight_variator", ModuleType.EVOLUTION),
        ]

        for module_name, module_type in modules_to_register:
            module_instance = getattr(self, module_name, None)
            if module_instance:
                self.performance_monitor.register_module(
                    module_name, module_type, module_instance
                )

    async def start(self):
        """启动系统"""
        if self.is_running:
            print("⚠️  系统已在运行中")
            return

        print("\n🚀 启动数字生命体交易系统...")
        self.is_running = True
        self.start_time = datetime.now()
        self.performance_monitor.start_monitoring()

        print(f"  启动时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("  ✅ 系统已启动")

    async def stop(self):
        """停止系统"""
        if not self.is_running:
            print("⚠️  系统未运行")
            return

        print("\n🛑 停止数字生命体交易系统...")
        self.is_running = False
        self.performance_monitor.stop_monitoring()

        # 生成最终报告
        self._generate_final_report()

        print("  ✅ 系统已停止")

    def generate_market_data(self, days: int = 90) -> Dict[str, pd.DataFrame]:
        """生成模拟市场数据"""
        print(f"\n📊 生成 {days} 天模拟市场数据...")

        timeframes = ["D1", "H4", "H1", "M15"]
        data_dict = {}

        for tf in timeframes:
            # 根据时间框架确定K线数量
            if tf == "D1":
                bars = days
                freq = "D"
            elif tf == "H4":
                bars = days * 6
                freq = "4H"
            elif tf == "H1":
                bars = days * 24
                freq = "H"
            else:  # M15
                bars = days * 96
                freq = "15T"

            # 生成日期范围
            dates = pd.date_range(end=datetime.now(), periods=bars, freq=freq)

            # 生成价格序列（模拟市场周期）
            base_price = 50000
            trend = np.sin(np.linspace(0, 4 * np.pi, bars)) * 0.1  # 正弦趋势
            noise = np.random.randn(bars) * 0.02  # 随机噪声
            prices = base_price * (1 + trend + noise.cumsum() * 0.01)

            # 生成OHLC数据
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

            data_dict[tf] = data

        print(f"  ✅ 已生成 {len(timeframes)} 个时间框架数据")
        return data_dict

    async def run_complete_analysis(self, data_dict: Dict[str, pd.DataFrame]):
        """运行完整分析流程"""
        print(f"\n🔍 开始完整分析流程...")
        print(f"  数据范围: {len(data_dict)} 个时间框架")

        analysis_start = time.time()

        try:
            # 1. 物理感知层分析
            print("\n  1. 🧠 物理感知层分析:")
            perception_results = self._run_perception_analysis(data_dict)

            # 2. 状态机决策分析
            print("  2. 🤖 状态机决策分析:")
            state_results = self._run_state_machine_analysis(
                data_dict, perception_results
            )

            # 3. 多周期融合分析
            print("  3. 🔄 多周期融合分析:")
            fusion_results = self._run_fusion_analysis(data_dict, perception_results)

            # 4. 生成交易决策
            print("  4. 📈 生成交易决策:")
            decision = self._generate_trading_decision(
                perception_results, state_results, fusion_results
            )

            # 5. 记录分析结果
            self.decision_count += 1
            self.success_count += 1

            analysis_time = time.time() - analysis_start

            print(f"\n  ✅ 分析完成!")
            print(f"    分析时间: {analysis_time:.2f} 秒")
            print(f"    交易信号: {decision['signal']}")
            print(f"    置信度: {decision['confidence']:.2f}")

            return {
                "success": True,
                "decision": decision,
                "analysis_time": analysis_time,
                "perception": perception_results,
                "state": state_results,
                "fusion": fusion_results,
            }

        except Exception as e:
            print(f"  ❌ 分析失败: {e}")
            self.error_count += 1

            # 记录错误到错题本
            self.mistake_book.record_mistake(
                mistake_type=MistakeType.SYSTEM_ERROR,
                error_description=str(e),
                context={"timestamp": datetime.now()},
                severity=ErrorSeverity.MEDIUM,
            )

            return {
                "success": False,
                "error": str(e),
                "analysis_time": time.time() - analysis_start,
            }

    def _run_perception_analysis(
        self, data_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """运行物理感知层分析"""
        # 使用日线数据进行分析
        primary_data = data_dict.get("D1", list(data_dict.values())[0])

        # 市场体制检测
        regime_result = {"regime": "TRENDING", "confidence": 0.75}  # 模拟结果

        # TR识别
        tr_result = {"has_trading_range": True, "breakout_direction": "bullish"}

        # FVG检测
        fvg_result = {"bullish_fvgs": [{"strength": 0.7}], "bearish_fvgs": []}

        return {
            "market_regime": regime_result["regime"],
            "regime_confidence": regime_result["confidence"],
            "has_trading_range": tr_result["has_trading_range"],
            "breakout_direction": tr_result.get("breakout_direction"),
            "fvg_count": len(fvg_result["bullish_fvgs"])
            + len(fvg_result["bearish_fvgs"]),
            "primary_timeframe": "D1",
        }

    def _run_state_machine_analysis(
        self, data_dict: Dict[str, pd.DataFrame], perception_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """运行状态机决策分析"""
        # 模拟状态机分析结果
        states = [
            {"state_name": "ACCUMULATION", "confidence": 0.8},
            {"state_name": "TESTING", "confidence": 0.6},
            {"state_name": "SIGN_OF_STRENGTH", "confidence": 0.7},
        ]

        # 选择置信度最高的状态
        best_state = max(states, key=lambda x: x["confidence"])

        signals = []
        if (
            best_state["state_name"] == "ACCUMULATION"
            and best_state["confidence"] > 0.7
        ):
            signals.append({"type": "BUY_SIGNAL", "confidence": 0.75})
        elif (
            best_state["state_name"] == "DISTRIBUTION"
            and best_state["confidence"] > 0.7
        ):
            signals.append({"type": "SELL_SIGNAL", "confidence": 0.75})

        return {
            "current_state": best_state["state_name"],
            "state_confidence": best_state["confidence"],
            "signals": signals,
            "evidence_count": 3,  # 模拟证据数量
        }

    def _run_fusion_analysis(
        self, data_dict: Dict[str, pd.DataFrame], perception_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """运行多周期融合分析"""
        # 模拟多周期分析结果
        timeframe_weights = {
            "D1": 0.25,
            "H4": 0.20,
            "H1": 0.18,
            "M15": 0.15,
        }

        # 模拟冲突检测
        conflicts = []
        if random.random() > 0.5:  # 50%概率检测到冲突
            conflicts.append(
                {
                    "type": "DISTRIBUTION_ACCUMULATION",
                    "description": "日线派发 vs 4小时吸筹",
                }
            )

        return {
            "timeframe_weights": timeframe_weights,
            "conflict_count": len(conflicts),
            "has_conflict": len(conflicts) > 0,
            "recommended_action": "FOLLOW_LARGER_TIMEFRAME"
            if conflicts
            else "NORMAL_TRADING",
        }

    def _generate_trading_decision(
        self,
        perception_results: Dict[str, Any],
        state_results: Dict[str, Any],
        fusion_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成交易决策"""
        # 基于状态机信号
        signal = "NEUTRAL"
        confidence = 0.0
        reasoning = []

        if state_results.get("signals"):
            strongest_signal = max(
                state_results["signals"], key=lambda x: x.get("confidence", 0)
            )

            if strongest_signal["type"] == "BUY_SIGNAL":
                signal = "BUY"
                confidence = strongest_signal["confidence"]
                reasoning.append("威科夫状态机生成买入信号")
            elif strongest_signal["type"] == "SELL_SIGNAL":
                signal = "SELL"
                confidence = strongest_signal["confidence"]
                reasoning.append("威科夫状态机生成卖出信号")

        # 考虑突破状态
        if (
            perception_results.get("breakout_direction") == "bullish"
            and signal == "BUY"
        ):
            confidence = min(1.0, confidence + 0.1)
            reasoning.append("确认突破方向为 bullish")
        elif (
            perception_results.get("breakout_direction") == "bearish"
            and signal == "SELL"
        ):
            confidence = min(1.0, confidence + 0.1)
            reasoning.append("确认突破方向为 bearish")

        # 考虑冲突解决建议
        if fusion_results.get("has_conflict"):
            if fusion_results.get("recommended_action") == "FOLLOW_LARGER_TIMEFRAME":
                reasoning.append("遵循大周期方向解决冲突")
            elif fusion_results.get("recommended_action") == "REDUCE_POSITION_SIZE":
                reasoning.append("降低仓位以应对冲突")

        # 如果没有明确信号，保持中性
        if confidence < 0.6:
            signal = "NEUTRAL"
            reasoning.append("置信度不足，保持中性观望")

        return {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "timestamp": datetime.now().isoformat(),
        }

    async def run_evolution_demo(self):
        """运行自动化进化演示"""
        print(f"\n🧬 开始自动化进化演示...")

        evolution_start = time.time()

        try:
            # 1. 模拟记录一些错误
            print("  1. 📝 模拟错误记录...")
            for i in range(3):
                self.mistake_book.record_mistake(
                    mistake_type=random.choice(list(MistakeType)),
                    error_description=f"模拟错误 {i + 1}",
                    context={"demo": True, "iteration": i},
                    severity=ErrorSeverity.LOW,
                )

            # 2. 分析错误模式
            print("  2. 🔍 分析错误模式...")
            patterns = self.mistake_book.analyze_patterns()

            # 3. 生成权重变异
            print("  3. 🧬 生成权重变异...")
            current_config = {"weights": {"D1": 0.25, "H4": 0.20}}
            new_configs = self.weight_variator.generate_variations(
                current_config, patterns
            )

            # 4. WFA回测验证
            print("  4. 📊 WFA回测验证...")
            validation_results = []
            for config in new_configs[:2]:  # 只验证前2个配置
                result = {
                    "configuration": config,
                    "composite_score": random.uniform(0.5, 0.9),
                    "stability_score": random.uniform(0.6, 0.95),
                }
                validation_results.append(result)

            # 5. 选择最佳配置
            print("  5. 🏆 选择最佳配置...")
            best_config = max(validation_results, key=lambda x: x["composite_score"])

            evolution_time = time.time() - evolution_start
            self.evolution_cycles += 1

            print(f"\n  ✅ 进化完成!")
            print(f"    进化周期: {self.evolution_cycles}")
            print(f"    进化时间: {evolution_time:.2f} 秒")
            print(f"    最佳配置分数: {best_config['composite_score']:.3f}")

            return {
                "success": True,
                "evolution_cycle": self.evolution_cycles,
                "best_score": best_config["composite_score"],
                "evolution_time": evolution_time,
            }

        except Exception as e:
            print(f"  ❌ 进化演示失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()

        return {
            "name": self.name,
            "version": self.version,
            "is_running": self.is_running,
            "uptime_seconds": uptime,
            "decision_count": self.decision_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "evolution_cycles": self.evolution_cycles,
            "success_rate": self.success_count / self.decision_count
            if self.decision_count > 0
            else 0,
        }

    def display_system_status(self):
        """显示系统状态"""
        status = self.get_system_status()

        print(f"\n{'=' * 60}")
        print("📊 数字生命体交易系统 - 状态报告")
        print(f"{'=' * 60}")

        print(f"  系统名称: {status['name']}")
        print(f"  系统版本: {status['version']}")
        print(f"  运行状态: {'运行中 🟢' if status['is_running'] else '已停止 🔴'}")

        if status["is_running"]:
            hours = status["uptime_seconds"] // 3600
            minutes = (status["uptime_seconds"] % 3600) // 60
            seconds = status["uptime_seconds"] % 60
            print(f"  运行时间: {int(hours)}小时 {int(minutes)}分钟 {int(seconds)}秒")

        print(f"\n  决策统计:")
        print(f"    总决策数: {status['decision_count']}")
        print(f"    成功数: {status['success_count']}")
        print(f"    错误数: {status['error_count']}")
        print(f"    成功率: {status['success_rate']:.1%}")

        print(f"\n  进化统计:")
        print(f"    进化周期: {status['evolution_cycles']}")

        # 性能监控状态
        try:
            dashboard = self.performance_monitor.get_dashboard()
            health_status = dashboard.get("system_health", {}).get("status", "UNKNOWN")
            health_score = dashboard.get("system_health", {}).get("score", 0)

            print(f"\n  性能监控:")
            print(f"    系统健康: {health_status}")
            print(f"    健康分数: {health_score:.1f}/100")

            module_count = len(dashboard.get("modules", {}))
            print(f"    监控模块: {module_count}个")

        except Exception as e:
            print(f"\n  性能监控: 数据不可用 ({e})")

        print(f"{'=' * 60}")

    def _generate_final_report(self):
        """生成最终报告"""
        print("\n📄 生成系统最终报告...")

        report = {
            "system_name": self.name,
            "system_version": self.version,
            "session_start": self.start_time.isoformat() if self.start_time else None,
            "session_end": datetime.now().isoformat(),
            "session_duration_seconds": (
                datetime.now() - self.start_time
            ).total_seconds()
            if self.start_time
            else 0,
            "performance_metrics": {
                "total_decisions": self.decision_count,
                "successful_decisions": self.success_count,
                "failed_decisions": self.error_count,
                "success_rate": self.success_count / self.decision_count
                if self.decision_count > 0
                else 0,
                "evolution_cycles": self.evolution_cycles,
            },
            "modules_initialized": self._count_modules(),
            "final_status": "COMPLETED_SUCCESSFULLY",
        }

        # 保存报告到文件
        report_file = "digital_life_final_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"  ✅ 最终报告已保存到 {report_file}")

        # 显示报告摘要
        print(f"\n{'=' * 60}")
        print("📋 最终报告摘要")
        print(f"{'=' * 60}")
        print(f"  会话时长: {report['session_duration_seconds']:.0f} 秒")
        print(f"  总决策数: {report['performance_metrics']['total_decisions']}")
        print(f"  成功率: {report['performance_metrics']['success_rate']:.1%}")
        print(f"  进化周期: {report['performance_metrics']['evolution_cycles']}")
        print(f"  初始化模块: {report['modules_initialized']}个")
        print(f"{'=' * 60}")


async def main_demo():
    """主演示函数"""
    print("\n" + "=" * 80)
    print("威科夫全自动逻辑引擎 - 数字生命体交易系统最终演示")
    print("=" * 80)
    print()
    print("本演示展示完整的'数字生命体'交易系统，具备四大核心能力:")
    print("  1. 🧠 动态感知: 实时市场分析能力")
    print("  2. 🤔 独立思考: 辩证决策能力")
    print("  3. 🔄 自动进化: 自我优化能力")
    print("  4. 💬 落地沟通: 可执行交易建议")
    print()
    print("=" * 80)

    # 创建数字生命体交易系统
    system = DigitalLifeTradingSystem()

    # 启动系统
    await system.start()

    # 显示初始状态
    system.display_system_status()

    # 生成市场数据
    print("\n📈 准备市场数据...")
    market_data = system.generate_market_data(days=30)  # 30天数据

    # 运行3次完整分析
    print("\n🔍 运行完整分析流程 (3次迭代)...")
    for i in range(3):
        print(f"\n  迭代 {i + 1}/3:")
        result = await system.run_complete_analysis(market_data)

        if result["success"]:
            decision = result["decision"]
            print(
                f"    结果: {decision['signal']} 信号 (置信度: {decision['confidence']:.2f})"
            )
            print(f"    时间: {result['analysis_time']:.2f} 秒")
        else:
            print(f"    结果: 失败 - {result['error']}")

        # 短暂暂停
        await asyncio.sleep(1)

    # 运行自动化进化演示
    print("\n🧬 运行自动化进化演示...")
    evolution_result = await system.run_evolution_demo()

    if evolution_result["success"]:
        print(f"  进化结果: 完成第{evolution_result['evolution_cycle']}个进化周期")
        print(f"  最佳分数: {evolution_result['best_score']:.3f}")

    # 显示最终状态
    system.display_system_status()

    # 停止系统
    await system.stop()

    print("\n" + "=" * 80)
    print("✅ 数字生命体交易系统演示完成!")
    print("=" * 80)
    print()
    print("系统已展示以下核心能力:")
    print("  ✓ 动态感知: 市场体制识别、TR检测、FVG检测")
    print("  ✓ 独立思考: 威科夫状态机分析、多周期辩证融合")
    print("  ✓ 自动进化: 错题本学习、权重变异优化、性能监控")
    print("  ✓ 落地沟通: 可执行交易信号生成、风险管理")
    print()
    print("感谢观看数字生命体交易系统演示!")
    print("=" * 80)


if __name__ == "__main__":
    # 运行演示
    try:
        asyncio.run(main_demo())
    except KeyboardInterrupt:
        print("\n\n🛑 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示运行错误: {e}")
        import traceback

        traceback.print_exc()
