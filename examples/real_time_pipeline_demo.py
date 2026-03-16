"""
实时交易决策流水线演示
展示完整的"数字生命体"交易系统从数据输入到信号输出的全流程

流程：
1. 模拟实时数据流 (WebSocket/API 数据模拟)
2. 物理感知层处理 (市场体制、FVG、TR识别)
3. 多周期融合 (周期权重、冲突解决、微观入场)
4. 状态机决策 (威科夫状态分析)
5. 交易信号生成
6. 自动化进化 (错题本记录、性能监控)
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
from src.plugins.data_pipeline.data_pipeline import DataPipeline, Timeframe
from src.plugins.market_regime.detector import RegimeDetector
from src.perception.fvg_detector import FVGDetector
from src.plugins.pattern_detection.tr_detector import TRDetector
from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter
from src.plugins.signal_validation.breakout_validator import BreakoutValidator
from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter
from src.plugins.signal_validation.conflict_resolver import ConflictResolutionManager, ConflictType
from src.plugins.signal_validation.micro_entry_validator import MicroEntryValidator
from src.core.wyckoff_state_machine import WyckoffStateMachine
from src.plugins.self_correction.mistake_book import MistakeBook, MistakeType, ErrorSeverity
from src.plugins.dashboard.performance_monitor import PerformanceMonitor, ModuleType


class RealTimePipeline:
    """实时交易决策流水线"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.is_running = False

        # 初始化模块
        self._init_modules()

        # 状态跟踪
        self.decision_history = []
        self.data_buffer = {}
        self.last_processing_time = None

        print("✅ 实时交易决策流水线初始化完成")

    def _init_modules(self):
        """初始化所有模块"""
        print("🔄 初始化交易系统模块...")

        # 数据管道
        self.data_pipeline = DataPipeline(
            {
                "redis_host": "localhost",
                "redis_port": 6379,
            }
        )

        # 物理感知层
        self.regime_detector = RegimeDetector()
        self.fvg_detector = FVGDetector()
        self.tr_detector = TRDetector()
        self.curve_fitter = CurveBoundaryFitter()
        self.breakout_validator = BreakoutValidator()

        # 多周期融合层
        self.period_filter = PeriodWeightFilter()
        self.conflict_resolver = ConflictResolutionManager()
        self.entry_validator = MicroEntryValidator()

        # 状态机决策层
        self.state_machine = WyckoffStateMachine()

        # 自动化进化层
        self.mistake_book = MistakeBook()
        self.performance_monitor = PerformanceMonitor()

        # 注册模块到性能监控
        self._register_modules()

        print("✅ 所有模块初始化完成")

    def _register_modules(self):
        """注册模块到性能监控系统"""
        modules = [
            ("regime_detector", ModuleType.PERCEPTION),
            ("fvg_detector", ModuleType.PERCEPTION),
            ("tr_detector", ModuleType.PERCEPTION),
            ("state_machine", ModuleType.STATEMACHINE),
            ("period_filter", ModuleType.MULTITIMEFRAME),
            ("conflict_resolver", ModuleType.MULTITIMEFRAME),
        ]

        for module_name, module_type in modules:
            module_instance = getattr(self, module_name, None)
            if module_instance:
                self.performance_monitor.register_module(
                    module_name, module_type, module_instance
                )

    async def start(self):
        """启动流水线"""
        if self.is_running:
            print("⚠️  流水线已在运行中")
            return

        print("🚀 启动实时交易决策流水线...")
        self.is_running = True
        self.performance_monitor.start_monitoring()

        # 启动数据流模拟
        asyncio.create_task(self._simulate_data_stream())

        print("✅ 流水线已启动")

    async def stop(self):
        """停止流水线"""
        if not self.is_running:
            print("⚠️  流水线未运行")
            return

        print("🛑 停止实时交易决策流水线...")
        self.is_running = False
        self.performance_monitor.stop_monitoring()

        # 保存状态
        self._save_pipeline_state()

        print("✅ 流水线已停止")

    async def _simulate_data_stream(self):
        """模拟实时数据流"""
        print("📡 开始模拟实时数据流...")

        timeframes = ["M15", "H1", "H4", "D1"]

        while self.is_running:
            try:
                # 生成模拟数据
                new_data = await self._generate_market_data(timeframes)

                # 处理新数据
                await self._process_new_data(new_data)

                # 等待下一个周期
                await asyncio.sleep(60)  # 每分钟处理一次

            except Exception as e:
                print(f"❌ 数据流错误: {e}")
                await asyncio.sleep(5)

    async def _generate_market_data(
        self, timeframes: List[str]
    ) -> Dict[str, pd.DataFrame]:
        """生成模拟市场数据"""
        data_dict = {}

        for tf in timeframes:
            # 生成100根K线数据
            periods = 100
            base_price = 50000 + random.randint(-1000, 1000)

            dates = pd.date_range(end=datetime.now(), periods=periods, freq=tf)

            # 生成价格序列（带趋势和噪声）
            trend = random.uniform(-0.001, 0.001)
            noise = np.random.randn(periods) * 0.005

            prices = base_price * (1 + np.arange(periods) * trend + noise.cumsum())

            data = pd.DataFrame(
                {
                    "open": prices * (1 + np.random.randn(periods) * 0.001),
                    "high": prices * (1 + np.abs(np.random.randn(periods)) * 0.002),
                    "low": prices * (1 - np.abs(np.random.randn(periods)) * 0.002),
                    "close": prices,
                    "volume": np.random.randint(1000, 10000, periods),
                },
                index=dates,
            )

            data_dict[tf] = data

        return data_dict

    async def _process_new_data(self, data_dict: Dict[str, pd.DataFrame]):
        """处理新数据并生成交易决策"""
        try:
            print(f"\n{'=' * 60}")
            print(f"📊 处理新数据批次: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'=' * 60}")

            # 1. 物理感知层分析
            perception_results = await self._run_perception_layer(data_dict)

            # 2. 多周期融合分析
            fusion_results = await self._run_fusion_layer(data_dict, perception_results)

            # 3. 状态机决策
            state_results = await self._run_state_machine(
                data_dict, perception_results, fusion_results
            )

            # 4. 生成交易信号
            signal = await self._generate_trading_signal(
                perception_results, fusion_results, state_results
            )

            # 5. 记录决策
            decision = {
                "timestamp": datetime.now(),
                "signal": signal,
                "perception": perception_results,
                "fusion": fusion_results,
                "state": state_results,
            }

            self.decision_history.append(decision)

            # 6. 显示结果
            self._display_decision_results(
                signal, perception_results, fusion_results, state_results
            )

            # 7. 更新性能监控
            self.performance_monitor.record_success("real_time_pipeline")

        except Exception as e:
            print(f"❌ 数据处理错误: {e}")
            self.performance_monitor.record_error("real_time_pipeline", str(e))

            # 记录错误到错题本
            self.mistake_book.record_mistake(
                mistake_type=MistakeType.SYSTEM_ERROR,
                error_description=str(e),
                context={"timestamp": datetime.now()},
                severity=ErrorSeverity.MEDIUM,
            )

    async def _run_perception_layer(
        self, data_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """运行物理感知层分析"""
        print("🔍 运行物理感知层分析...")

        # 使用主要时间框架（H4）
        primary_tf = "H4"
        if primary_tf not in data_dict:
            primary_tf = list(data_dict.keys())[0]

        data = data_dict[primary_tf]

        # 市场体制检测
        regime_result = self.regime_detector.detect(data)

        # TR识别
        tr_result = self.tr_detector.detect(data)

        # FVG检测
        fvg_result = self.fvg_detector.detect(data)

        # 曲线边界拟合
        curve_result = self.curve_fitter.analyze(data)

        # 突破验证
        breakout_result = None
        if tr_result["has_trading_range"] and tr_result["breakout_direction"]:
            breakout_result = self.breakout_validator.validate(
                data, tr_result["breakout_direction"], tr_result["breakout_level"]
            )

        return {
            "market_regime": regime_result["regime"],
            "regime_confidence": regime_result["confidence"],
            "trading_range": tr_result["has_trading_range"],
            "breakout_direction": tr_result.get("breakout_direction"),
            "fvg_signals": len(fvg_result["bullish_fvgs"])
            + len(fvg_result["bearish_fvgs"]),
            "curve_boundary": curve_result["boundary_type"] if curve_result else None,
            "breakout_status": breakout_result["is_valid"]
            if breakout_result
            else False,
            "primary_timeframe": primary_tf,
        }

    async def _run_fusion_layer(
        self, data_dict: Dict[str, pd.DataFrame], perception_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """运行多周期融合分析"""
        print("🔄 运行多周期融合分析...")

        # 计算周期权重
        weights = self.period_filter.calculate_weights(
            data_dict, perception_results["market_regime"]
        )

        # 检测冲突
        conflicts = self.conflict_resolver.detect_conflicts(data_dict, weights)

        # 解决冲突
        resolved_decisions = []
        if conflicts:
            for conflict in conflicts:
                resolution = self.conflict_resolver.resolve_conflict(
                    {"timeframe_states": data_dict},
                    {"regime": perception_results["market_regime"]},
                )
                resolved_decisions.append(resolution)

        # 微观入场验证
        entry_validation = None
        if perception_results.get("breakout_status"):
            entry_validation = self.entry_validator.validate(
                data_dict,
                {"breakout_direction": perception_results["breakout_direction"]},
            )

        return {
            "timeframe_weights": weights,
            "conflict_count": len(conflicts),
            "resolved_decisions": resolved_decisions,
            "entry_validation": entry_validation,
        }

    async def _run_state_machine(
        self,
        data_dict: Dict[str, pd.DataFrame],
        perception_results: Dict[str, Any],
        fusion_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """运行状态机决策分析"""
        print("🤖 运行威科夫状态机分析...")

        primary_tf = perception_results["primary_timeframe"]
        data = data_dict[primary_tf]

        # 准备状态机输入
        state_input = {
            "price_data": data,
            "market_regime": perception_results["market_regime"],
            "trading_range_info": {
                "has_trading_range": perception_results["trading_range"],
                "breakout_direction": perception_results["breakout_direction"],
            },
            "timeframe_weights": fusion_results["timeframe_weights"],
        }

        # 运行状态机
        state_result = self.state_machine.analyze(state_input)

        return {
            "current_state": state_result.get("current_state", {}).get(
                "state_name", "UNKNOWN"
            ),
            "confidence": state_result.get("confidence", 0),
            "signals": state_result.get("signals", []),
            "evidence_count": len(state_result.get("evidence_chain", [])),
        }

    async def _generate_trading_signal(
        self,
        perception_results: Dict[str, Any],
        fusion_results: Dict[str, Any],
        state_results: Dict[str, Any],
    ) -> str:
        """生成交易信号"""
        print("📈 生成交易信号...")

        # 基于状态机信号
        state_signals = state_results.get("signals", [])
        state_confidence = state_results.get("confidence", 0)

        if state_signals:
            # 提取最强的信号
            strongest_signal = max(state_signals, key=lambda x: x.get("confidence", 0))

            signal_type = strongest_signal.get("type", "")
            signal_confidence = strongest_signal.get("confidence", 0)

            if "BUY" in signal_type and signal_confidence > 0.6:
                return "BUY"
            elif "SELL" in signal_type and signal_confidence > 0.6:
                return "SELL"

        # 基于突破状态
        if perception_results.get("breakout_status"):
            direction = perception_results.get("breakout_direction")
            if direction == "bullish":
                return "BUY"
            elif direction == "bearish":
                return "SELL"

        # 默认中性
        return "NEUTRAL"

    def _display_decision_results(
        self,
        signal: str,
        perception_results: Dict[str, Any],
        fusion_results: Dict[str, Any],
        state_results: Dict[str, Any],
    ):
        """显示决策结果"""
        print(f"\n📋 决策结果摘要:")
        print(f"   📡 信号: {signal}")
        print(
            f"   🏛️  市场体制: {perception_results['market_regime']} "
            f"(置信度: {perception_results['regime_confidence']:.2f})"
        )
        print(f"   📊 TR状态: {'有' if perception_results['trading_range'] else '无'}")

        if perception_results["breakout_direction"]:
            print(f"   🚀 突破方向: {perception_results['breakout_direction']}")

        print(f"   🔍 FVG信号: {perception_results['fvg_signals']}个")
        print(f"   ⚖️  周期权重: {len(fusion_results['timeframe_weights'])}个时间框架")
        print(f"   ⚔️  冲突数量: {fusion_results['conflict_count']}")
        print(
            f"   🤖 威科夫状态: {state_results['current_state']} "
            f"(置信度: {state_results['confidence']:.2f})"
        )
        print(f"   🧩 证据数量: {state_results['evidence_count']}")

        # 显示性能监控状态
        dashboard = self.performance_monitor.get_dashboard()
        health_status = dashboard.get("system_health", {}).get("status", "UNKNOWN")
        health_score = dashboard.get("system_health", {}).get("score", 0)

        print(f"\n📊 系统健康状态: {health_status} (分数: {health_score:.1f}/100)")

        if signal != "NEUTRAL":
            print(f"\n🎯 交易建议: {signal} 信号生成，建议关注!")
        else:
            print(f"\n⏸️  交易建议: 中性信号，建议观望")

    def _save_pipeline_state(self):
        """保存流水线状态"""
        try:
            state_file = "pipeline_state.json"
            import json

            state_data = {
                "timestamp": datetime.now().isoformat(),
                "decision_count": len(self.decision_history),
                "last_decisions": self.decision_history[-3:]
                if self.decision_history
                else [],
                "performance_dashboard": self.performance_monitor.get_dashboard(),
            }

            with open(state_file, "w") as f:
                json.dump(state_data, f, indent=2, default=str)

            print(f"✅ 流水线状态已保存到 {state_file}")

        except Exception as e:
            print(f"❌ 保存状态失败: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取流水线统计信息"""
        return {
            "is_running": self.is_running,
            "decision_count": len(self.decision_history),
            "last_signal": self.decision_history[-1]["signal"]
            if self.decision_history
            else "NONE",
            "performance_dashboard": self.performance_monitor.get_dashboard(),
        }


async def main_demo():
    """主演示函数"""
    print("=" * 80)
    print("威科夫全自动逻辑引擎 - 实时交易决策流水线演示")
    print("=" * 80)
    print()
    print("本演示展示完整的'数字生命体'交易系统工作流程：")
    print("1. 📡 模拟实时数据流")
    print("2. 🔍 物理感知层分析 (市场体制、FVG、TR识别)")
    print("3. 🔄 多周期融合 (周期权重、冲突解决)")
    print("4. 🤖 状态机决策 (威科夫状态分析)")
    print("5. 📈 交易信号生成")
    print("6. 📊 性能监控与自动化进化")
    print()
    print("=" * 80)

    # 创建流水线
    pipeline = RealTimePipeline()

    # 启动流水线
    await pipeline.start()

    # 运行演示（5个决策周期）
    print("\n⏳ 运行5个决策周期演示...")
    for i in range(5):
        if not pipeline.is_running:
            break

        print(f"\n📅 决策周期 {i + 1}/5")
        print("-" * 40)

        # 等待处理完成
        await asyncio.sleep(10)  # 每个周期10秒

        # 显示统计信息
        stats = pipeline.get_statistics()
        print(
            f"📊 统计: {stats['decision_count']}个决策，"
            f"最后信号: {stats['last_signal']}"
        )

    # 停止流水线
    await pipeline.stop()

    # 显示最终结果
    print("\n" + "=" * 80)
    print("演示完成 - 系统摘要:")
    print("=" * 80)

    stats = pipeline.get_statistics()
    dashboard = stats["performance_dashboard"]

    print(f"📈 总决策数量: {stats['decision_count']}")
    print(f"🎯 最后信号: {stats['last_signal']}")

    if dashboard:
        health = dashboard.get("system_health", {})
        print(
            f"🏥 系统健康: {health.get('status', 'UNKNOWN')} "
            f"(分数: {health.get('score', 0):.1f}/100)"
        )

        modules = dashboard.get("modules", {})
        print(f"🔧 监控模块: {len(modules)}个")

        alerts = dashboard.get("alerts", [])
        print(f"⚠️  报警数量: {len(alerts)}")

    print("\n✅ 实时交易决策流水线演示成功完成!")
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
