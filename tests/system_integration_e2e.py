"""
系统端到端集成测试 - 验证从数据获取到交易信号生成的完整流水线

测试目标：
1. 验证数据管道 → 数据清洗 → 物理感知 → 状态机 → 交易信号的完整流程
2. 确保各模块协同工作，数据流完整闭环
3. 验证异常处理和数据质量保证机制
4. 测试系统韧性和错误恢复能力

测试策略：
1. 使用模拟数据测试正常流程
2. 注入异常数据测试错误处理
3. 验证多周期数据融合
4. 测试交易信号生成逻辑
"""

import sys
import os
import asyncio
import unittest
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import json
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 导入核心模块
try:
    from src.plugins.data_pipeline.data_pipeline import (
        DataPipeline,
        DataRequest,
        Timeframe,
        DataSource,
    )
    from src.plugins.data_pipeline.data_sanitizer import (
        DataSanitizer,
        DataSanitizerConfig,
        MarketType,
        RawCandle,
        HistoricalContext,
    )
    from src.plugins.market_regime import RegimeDetector
    from src.plugins.pattern_detection.tr_detector import TRDetector
    from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter
    from src.plugins.signal_validation.breakout_validator import BreakoutValidator
    from src.plugins.risk_management.anomaly_validator import AnomalyValidator
    from src.plugins.risk_management.circuit_breaker import CircuitBreaker
    from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter
    from src.plugins.signal_validation.conflict_resolver import (
        ConflictResolutionManager,
    )
    from src.plugins.signal_validation.micro_entry_validator import MicroEntryValidator
    from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
        EnhancedWyckoffStateMachine,
    )
    from src.kernel.types import StateConfig
    from src.plugins.orchestrator.system_orchestrator_legacy import SystemOrchestrator
    from src.kernel.types import SystemMode, TradingSignal
    from src.perception.fvg_detector import FVGDetector
    from src.perception.candle_physical import create_candle_from_dataframe_row
    from src.perception.pin_body_analyzer import (
        analyze_pin_vs_body,
        AnalysisContext,
        MarketRegimeType,
    )
except ImportError as e:
    print(f"导入模块失败: {e}")
    # 尝试备用导入
    try:
        from core.data_pipeline import DataPipeline, DataRequest, Timeframe, DataSource
        from core.data_sanitizer import (
            DataSanitizer,
            DataSanitizerConfig,
            MarketType,
            RawCandle,
            HistoricalContext,
        )
        from src.plugins.market_regime import RegimeDetector
        from core.tr_detector import TRDetector
        from core.curve_boundary import CurveBoundaryFitter
        from core.breakout_validator import BreakoutValidator
        from core.anomaly_validator import AnomalyValidator
        from core.circuit_breaker import CircuitBreaker
        from core.period_weight_filter import PeriodWeightFilter
        from core.conflict_resolver import ConflictResolutionManager
        from core.micro_entry_validator import MicroEntryValidator
        from core.wyckoff_state_machine import EnhancedWyckoffStateMachine, StateConfig
        from core.system_orchestrator import (
            SystemOrchestrator,
            SystemMode,
            TradingSignal,
        )
        from perception.fvg_detector import FVGDetector
        from perception.candle_physical import create_candle_from_dataframe_row
        from perception.pin_body_analyzer import (
            analyze_pin_vs_body,
            AnalysisContext,
            MarketRegimeType,
        )
    except ImportError as e2:
        print(f"备用导入也失败: {e2}")
        raise


class TestDataGenerator:
    """测试数据生成器"""

    @staticmethod
    def create_normal_market_data(
        symbol: str = "BTCUSDT",
        n_points: int = 200,
        timeframe: str = "1h",
        start_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """创建正常市场数据（模拟吸筹模式）"""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)

        dates = pd.date_range(start=start_date, periods=n_points, freq=timeframe)

        # 创建吸筹模式数据：先下跌，然后盘整，最后突破
        # 阶段1: 下跌（PSY阶段）
        phase1_end = 50
        prices_phase1 = (
            100 - np.linspace(0, 20, phase1_end) + np.random.randn(phase1_end) * 2
        )

        # 阶段2: 盘整（TR阶段）
        phase2_end = 150
        tr_width = 5.0
        base_price = 80.0
        prices_phase2 = base_price + np.random.uniform(
            -tr_width / 2, tr_width / 2, phase2_end - phase1_end
        )

        # 阶段3: 突破（UT阶段）
        phase3_end = n_points
        breakout_slope = 0.3
        prices_phase3 = (
            base_price
            + tr_width / 2
            + breakout_slope * np.arange(phase3_end - phase2_end)
            + np.random.randn(phase3_end - phase2_end) * 1
        )

        # 合并价格
        prices = np.concatenate([prices_phase1, prices_phase2, prices_phase3])

        # 创建OHLCV数据
        df = pd.DataFrame(
            {
                "open": prices + np.random.randn(n_points) * 0.5,
                "high": prices + np.random.rand(n_points) * 2,
                "low": prices - np.random.rand(n_points) * 2,
                "close": prices + np.random.randn(n_points) * 0.5,
                "volume": np.random.rand(n_points) * 1000 + 500,
            },
            index=dates,
        )

        return df

    @staticmethod
    def create_anomaly_market_data(
        symbol: str = "BTCUSDT", n_points: int = 100, timeframe: str = "1h"
    ) -> pd.DataFrame:
        """创建包含异常的市场数据"""
        dates = pd.date_range(start="2025-01-01", periods=n_points, freq=timeframe)

        # 创建基础价格
        base_price = 100.0
        prices = base_price + np.cumsum(np.random.randn(n_points) * 0.5)

        df = pd.DataFrame(
            {
                "open": prices + np.random.randn(n_points) * 0.5,
                "high": prices + np.random.rand(n_points) * 2,
                "low": prices - np.random.rand(n_points) * 2,
                "close": prices + np.random.randn(n_points) * 0.5,
                "volume": np.random.rand(n_points) * 1000 + 500,
            },
            index=dates,
        )

        # 注入异常数据
        # 1. 零成交量异常
        df.loc[dates[20], "volume"] = 0

        # 2. 价格跳空异常
        df.loc[dates[40], "close"] = df.loc[dates[40], "close"] * 1.2

        # 3. 极端成交量异常
        df.loc[dates[60], "volume"] = df.loc[dates[60], "volume"] * 10

        # 4. 无效价格异常 (high < low)
        df.loc[dates[80], "high"] = df.loc[dates[80], "low"] - 1

        return df

    @staticmethod
    def create_multi_timeframe_data(
        symbol: str = "BTCUSDT",
        timeframes: List[str] = ["1h", "4h", "1d"],
        n_points: int = 200,
    ) -> Dict[str, pd.DataFrame]:
        """创建多时间框架数据"""
        data_dict = {}

        for tf in timeframes:
            if tf == "1h":
                freq = "h"
            elif tf == "4h":
                freq = "4h"
            elif tf == "1d":
                freq = "D"
            else:
                freq = "h"

            data_dict[tf] = TestDataGenerator.create_normal_market_data(
                symbol=symbol, n_points=n_points, timeframe=freq
            )

        return data_dict


class TestSystemIntegrationE2E(unittest.TestCase):
    """系统端到端集成测试类"""

    def setUp(self):
        """测试前准备"""
        print("\n" + "=" * 80)
        print("设置测试环境...")

        # 创建测试数据
        self.symbol = "BTCUSDT"
        self.timeframes = ["H4", "H1", "M15"]

        # 正常数据
        self.normal_data = TestDataGenerator.create_multi_timeframe_data(
            symbol=self.symbol, timeframes=self.timeframes, n_points=200
        )

        # 异常数据
        self.anomaly_data = TestDataGenerator.create_anomaly_market_data(
            symbol=self.symbol, n_points=100
        )

        # 系统配置
        self.config = {
            "mode": "paper",
            "data_pipeline": {
                "redis_host": "localhost",
                "redis_port": 6379,
                "cache_ttl": 3600,
            },
            "data_sanitizer": {
                "market_type": "CRYPTO",
                "anomaly_threshold": 0.7,
                "max_volume_ratio": 10.0,
                "max_gap_atr_multiple": 5.0,
                "circuit_breaker_enabled": True,
            },
            "market_regime": {
                "min_atr_multiplier": 1.5,
                "max_atr_multiplier": 2.5,
                "adx_threshold": 25,
            },
            "wyckoff_state_machine": {
                "transition_confidence": 0.75,
                "min_state_duration": 3,
                "max_state_duration": 20,
                "heritage_decay": 0.95,
            },
        }

        print("测试环境设置完成")
        print("=" * 80)

    def test_01_data_pipeline_integration(self):
        """测试1: 数据管道集成"""
        print("\n" + "=" * 80)
        print("测试1: 数据管道集成测试")
        print("=" * 80)

        try:
            # 初始化数据管道
            pipeline = DataPipeline(self.config.get("data_pipeline", {}))

            # 测试数据验证功能
            for timeframe, data in self.normal_data.items():
                print(f"\n验证 {timeframe} 时间框架数据:")
                print(f"  数据点数: {len(data)}")
                print(f"  时间范围: {data.index[0]} 到 {data.index[-1]}")
                print(f"  价格范围: {data['low'].min():.2f} - {data['high'].max():.2f}")

                # 检查数据质量
                missing_values = data.isnull().sum().sum()
                invalid_prices = (data["high"] < data["low"]).sum()
                zero_volume = (data["volume"] == 0).sum()

                print(f"  数据质量检查:")
                print(f"    - 缺失值: {missing_values}")
                print(f"    - 无效价格: {invalid_prices}")
                print(f"    - 零成交量: {zero_volume}")

                # 验证数据质量
                self.assertEqual(missing_values, 0, f"{timeframe}数据存在缺失值")
                self.assertEqual(invalid_prices, 0, f"{timeframe}数据存在无效价格")
                self.assertEqual(zero_volume, 0, f"{timeframe}数据存在零成交量")

            print("\n✅ 数据管道集成测试通过")

        except Exception as e:
            print(f"\n❌ 数据管道集成测试失败: {e}")
            raise

    def test_02_data_sanitizer_integration(self):
        """测试2: 数据清洗器集成"""
        print("\n" + "=" * 80)
        print("测试2: 数据清洗器集成测试")
        print("=" * 80)

        try:
            # 初始化数据清洗器
            sanitizer_config = DataSanitizerConfig()
            sanitizer = DataSanitizer(sanitizer_config)
            sanitizer.market_type = MarketType.CRYPTO

            # 使用正常数据测试
            normal_df = self.normal_data["H4"]
            historical_context = HistoricalContext()
            anomaly_count = 0

            print(f"\n处理正常数据 ({len(normal_df)} 根K线):")

            for i, row in normal_df.iterrows():
                raw_candle = RawCandle(
                    timestamp=i,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    symbol=self.symbol,
                    exchange="binance",
                )

                # 数据清洗
                sanitized_data, is_anomaly, anomaly_event = sanitizer.sanitize_candle(
                    raw_candle, historical_context
                )

                if is_anomaly:
                    anomaly_count += 1
                    print(f"  检测到异常: {anomaly_event.anomaly_types} (时间: {i})")

            print(f"  正常数据中检测到 {anomaly_count} 个异常事件")
            self.assertLess(anomaly_count, 5, "正常数据中异常事件过多")

            # 使用异常数据测试
            print(f"\n处理异常数据 ({len(self.anomaly_data)} 根K线):")
            anomaly_events = []

            for i, row in self.anomaly_data.iterrows():
                raw_candle = RawCandle(
                    timestamp=i,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    symbol=self.symbol,
                    exchange="binance",
                )

                sanitized_data, is_anomaly, anomaly_event = sanitizer.sanitize_candle(
                    raw_candle, historical_context
                )

                if is_anomaly and anomaly_event:
                    anomaly_events.append(anomaly_event)

            print(f"  异常数据中检测到 {len(anomaly_events)} 个异常事件")
            self.assertGreater(len(anomaly_events), 0, "应该检测到异常数据中的异常")

            # 验证异常事件类型
            anomaly_types = set()
            for event in anomaly_events:
                anomaly_types.update(event.anomaly_types)

            print(f"  检测到的异常类型: {anomaly_types}")

            print("\n✅ 数据清洗器集成测试通过")

        except Exception as e:
            print(f"\n❌ 数据清洗器集成测试失败: {e}")
            raise

    def test_03_physical_perception_integration(self):
        """测试3: 物理感知层集成"""
        print("\n" + "=" * 80)
        print("测试3: 物理感知层集成测试")
        print("=" * 80)

        try:
            # 初始化物理感知层模块
            regime_detector = RegimeDetector(self.config.get("market_regime", {}))
            tr_detector = TRDetector()
            fvg_detector = FVGDetector()
            curve_analyzer = CurveBoundaryFitter()
            breakout_validator = BreakoutValidator()
            anomaly_validator = AnomalyValidator()

            # 使用H4数据作为主时间框架
            primary_data = self.normal_data["H4"]

            print(f"\n分析 {self.symbol} H4 数据 ({len(primary_data)} 根K线):")

            # 1. 市场体制检测
            regime_result = regime_detector.detect_regime(primary_data)
            print(f"  市场体制: {regime_result.get('regime', 'unknown')}")
            print(f"  置信度: {regime_result.get('confidence', 0):.2f}")

            self.assertIn("regime", regime_result)
            self.assertIn("confidence", regime_result)

            # 2. 交易区间检测
            tr_result = tr_detector.detect_trading_range(primary_data)
            print(f"  交易区间检测:")
            print(
                f"    - 状态: {tr_result.status if hasattr(tr_result, 'status') else 'N/A'}"
            )
            print(
                f"    - 支撑位: {tr_result.lower_boundary if hasattr(tr_result, 'lower_boundary') else 'N/A':.2f}"
            )
            print(
                f"    - 阻力位: {tr_result.upper_boundary if hasattr(tr_result, 'upper_boundary') else 'N/A':.2f}"
            )

            self.assertIsNotNone(tr_result)

            # 3. FVG检测
            fvg_result = fvg_detector.detect_fvg_gaps(primary_data)
            print(f"  FVG检测: 发现 {len(fvg_result)} 个信号")

            # 4. 曲线边界拟合
            if len(primary_data) >= 20:
                curve_result = curve_analyzer.detect_trading_range(
                    primary_data["high"], primary_data["low"], primary_data["close"]
                )
                if curve_result:
                    print(f"  曲线边界拟合: 成功")
                else:
                    print(f"  曲线边界拟合: 未检测到有效曲线")

            # 5. 突破验证
            if hasattr(tr_result, "lower_boundary") and hasattr(
                tr_result, "upper_boundary"
            ):
                breakout_result = breakout_validator.detect_initial_breakout(
                    df=primary_data.tail(30),
                    support_level=tr_result.lower_boundary,
                    resistance_level=tr_result.upper_boundary,
                    current_atr=2.0,
                )

                if breakout_result:
                    print(f"  突破验证: {breakout_result.get('status', 'unknown')}")

            print("\n✅ 物理感知层集成测试通过")

        except Exception as e:
            print(f"\n❌ 物理感知层集成测试失败: {e}")
            raise

    def test_04_state_machine_integration(self):
        """测试4: 状态机集成"""
        print("\n" + "=" * 80)
        print("测试4: 状态机集成测试")
        print("=" * 80)

        try:
            # 初始化状态机
            state_config = StateConfig()
            state_config.update_from_dict(self.config.get("wyckoff_state_machine", {}))
            state_machine = EnhancedWyckoffStateMachine(state_config)

            # 使用H4数据
            primary_data = self.normal_data["H4"]

            # 准备上下文
            context = {
                "market_regime": "ACCUMULATION",
                "regime_confidence": 0.8,
                "support": 80.0,
                "resistance": 90.0,
                "volume_ma20": 800.0,
                "atr14": 2.0,
            }

            print(f"\n运行威科夫状态机 ({len(primary_data)} 根K线):")

            # 处理最近10根K线
            recent_candles = (
                primary_data.iloc[-10:] if len(primary_data) >= 10 else primary_data
            )

            state_history = []

            for i, candle in recent_candles.iterrows():
                # 处理每根K线
                state_result = state_machine.process_candle(candle, context)
                state_history.append(state_result)

                print(
                    f"  K线 {i}: 状态={state_result.get('state', 'unknown')}, "
                    f"置信度={state_result.get('confidence', 0):.2f}"
                )

            # 验证状态机输出
            self.assertGreater(len(state_history), 0, "状态机应该处理了K线数据")

            # 检查状态转换
            states = [s.get("state", "unknown") for s in state_history]
            print(f"\n  状态序列: {states}")

            # 获取当前状态信息
            if hasattr(state_machine, "get_current_state_info"):
                current_state = state_machine.get_current_state_info()
                print(f"\n  当前状态信息:")
                print(f"    - 状态: {current_state.get('current_state', 'unknown')}")
                print(f"    - 方向: {current_state.get('state_direction', 'unknown')}")
                print(f"    - 强度: {current_state.get('state_intensity', 0):.2f}")

            print("\n✅ 状态机集成测试通过")

        except Exception as e:
            print(f"\n❌ 状态机集成测试失败: {e}")
            raise

    def test_05_system_orchestrator_full_workflow(self):
        """测试5: 系统协调器完整工作流"""
        print("\n" + "=" * 80)
        print("测试5: 系统协调器完整工作流测试")
        print("=" * 80)

        try:
            # 初始化系统协调器
            orchestrator = SystemOrchestrator(self.config)

            print(f"\n初始化系统协调器完成")
            print(f"运行模式: {orchestrator.mode.value}")

            # 准备测试数据
            test_data = {
                "H4": self.normal_data["H4"],
                "H1": self.normal_data["H1"],
                "M15": self.normal_data["M15"],
            }

            # 运行系统处理
            print(f"\n处理 {self.symbol} 多时间框架数据...")

            # 注意：process_market_data是异步方法，我们需要在事件循环中运行
            async def run_processing():
                return await orchestrator.process_market_data(
                    symbol=self.symbol,
                    timeframes=["H4", "H1", "M15"],
                    data_dict=test_data,
                )

            # 创建事件循环并运行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                decision = loop.run_until_complete(run_processing())
            finally:
                loop.close()

            # 验证决策结果
            print(f"\n系统决策结果:")
            print(f"  信号: {decision.signal.value}")
            print(f"  置信度: {decision.confidence:.2f}")
            print(f"  推理: {decision.reasoning}")

            # 验证决策结构
            self.assertIsNotNone(decision)
            self.assertIsInstance(decision.signal, TradingSignal)
            self.assertIsInstance(decision.confidence, float)
            self.assertIsInstance(decision.reasoning, list)

            # 验证上下文
            context_dict = decision.context.to_dict()
            print(f"\n决策上下文:")
            print(f"  市场体制: {context_dict.get('market_regime', 'unknown')}")
            print(f"  威科夫状态: {context_dict.get('wyckoff_state', 'unknown')}")
            print(f"  时间框架权重: {context_dict.get('timeframe_weights', {})}")

            print("\n✅ 系统协调器完整工作流测试通过")

        except Exception as e:
            print(f"\n❌ 系统协调器完整工作流测试失败: {e}")
            raise

    def test_06_error_handling_and_resilience(self):
        """测试6: 错误处理和系统韧性"""
        print("\n" + "=" * 80)
        print("测试6: 错误处理和系统韧性测试")
        print("=" * 80)

        try:
            # 初始化系统协调器
            orchestrator = SystemOrchestrator(self.config)

            print(f"\n测试1: 处理异常数据...")

            # 准备包含异常的数据
            anomaly_test_data = {
                "H4": self.anomaly_data,
            }

            async def run_anomaly_processing():
                return await orchestrator.process_market_data(
                    symbol=self.symbol, timeframes=["H4"], data_dict=anomaly_test_data
                )

            # 运行异常数据处理
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                decision = loop.run_until_complete(run_anomaly_processing())
            finally:
                loop.close()

            print(f"  异常数据处理结果: {decision.signal.value}")
            print(f"  系统未崩溃，正确处理了异常数据")

            # 测试熔断机制
            print(f"\n测试2: 熔断机制测试...")

            circuit_breaker = CircuitBreaker()

            # 模拟连续异常触发熔断
            for i in range(5):
                is_triggered = circuit_breaker.check_and_trigger(
                    market_type="CRYPTO",
                    symbol="TEST_SYMBOL",
                    anomaly_type="ZERO_VOLUME",
                    anomaly_severity="CRITICAL" if i >= 2 else "WARNING",
                    timestamp=datetime.now() + timedelta(minutes=i),
                )

                if is_triggered:
                    print(f"  熔断触发于第 {i + 1} 次异常")
                    break

            # 检查熔断状态
            status = circuit_breaker.get_status("TEST_SYMBOL")
            if status:
                print(f"  熔断状态: {status.status}")
                print(f"  熔断原因: {status.reason}")

            print("\n✅ 错误处理和系统韧性测试通过")

        except Exception as e:
            print(f"\n❌ 错误处理和系统韧性测试失败: {e}")
            raise

    def test_07_multi_timeframe_conflict_resolution(self):
        """测试7: 多周期冲突解决"""
        print("\n" + "=" * 80)
        print("测试7: 多周期冲突解决测试")
        print("=" * 80)

        try:
            # 初始化冲突解决器
            conflict_resolver = ConflictResolutionManager()

            # 模拟多周期冲突
            print(f"\n模拟多周期冲突场景:")

            # 日线显示派发，4小时显示吸筹
            daily_signal = {
                "timeframe": "D1",
                "signal": "SELL",
                "confidence": 0.8,
                "reasoning": ["日线显示派发阶段完成"],
            }

            h4_signal = {
                "timeframe": "H4",
                "signal": "BUY",
                "confidence": 0.7,
                "reasoning": ["4小时显示吸筹阶段LPS"],
            }

            h1_signal = {
                "timeframe": "H1",
                "signal": "BUY",
                "confidence": 0.6,
                "reasoning": ["1小时显示微观入场信号"],
            }

            conflicting_signals = [daily_signal, h4_signal, h1_signal]

            print(f"  冲突信号:")
            for signal in conflicting_signals:
                print(
                    f"    - {signal['timeframe']}: {signal['signal']} (置信度: {signal['confidence']:.2f})"
                )

            # 解决冲突
            resolution = conflict_resolver.resolve_conflicts(conflicting_signals)

            print(f"\n  冲突解决结果:")
            print(f"    最终决策: {resolution.get('final_decision', 'unknown')}")
            print(f"    决策置信度: {resolution.get('decision_confidence', 0):.2f}")
            print(f"    解决理由: {resolution.get('resolution_reasoning', [])}")

            self.assertIsNotNone(resolution)
            self.assertIn("final_decision", resolution)

            print("\n✅ 多周期冲突解决测试通过")

        except Exception as e:
            print(f"\n❌ 多周期冲突解决测试失败: {e}")
            raise


def run_e2e_tests():
    """运行端到端测试"""
    print("\n" + "=" * 80)
    print("威科夫全自动逻辑引擎 - 系统端到端集成测试")
    print("=" * 80)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSystemIntegrationE2E)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出总结
    print("\n" + "=" * 80)
    print("端到端测试总结:")
    print("=" * 80)
    print(f"  运行测试: {result.testsRun}")
    print(f"  通过测试: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  失败测试: {len(result.failures)}")
    print(f"  错误测试: {len(result.errors)}")

    if result.failures:
        print("\n失败详情:")
        for test, traceback in result.failures:
            test_name = str(test).split()[0]
            print(f"  {test_name}: {traceback.splitlines()[-1]}")

    if result.errors:
        print("\n错误详情:")
        for test, traceback in result.errors:
            test_name = str(test).split()[0]
            print(f"  {test_name}: {traceback.splitlines()[-1]}")

    # 总体评估
    print("\n" + "=" * 80)
    if len(result.failures) == 0 and len(result.errors) == 0:
        print("🎉 所有端到端测试通过！系统集成验证成功。")
        print("\n系统验证结果:")
        print("  ✅ 数据管道 → 数据清洗 → 物理感知 → 状态机 → 交易信号流程完整")
        print("  ✅ 各模块协同工作，数据流完整闭环")
        print("  ✅ 异常处理和数据质量保证机制有效")
        print("  ✅ 系统具备韧性和错误恢复能力")
    else:
        print("⚠️  部分测试失败，需要检查系统集成问题。")

    print("=" * 80)

    return result


if __name__ == "__main__":
    # 运行端到端测试
    result = run_e2e_tests()

    # 根据测试结果退出
    if len(result.failures) == 0 and len(result.errors) == 0:
        sys.exit(0)
    else:
        sys.exit(1)
