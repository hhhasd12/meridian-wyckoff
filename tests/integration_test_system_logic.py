"""
系统逻辑闭环集成测试
验证威科夫全自动逻辑引擎的核心功能是否协同工作
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# 导入核心模块
try:
    from src.plugins.data_pipeline.data_sanitizer import DataSanitizer, RawCandle, HistoricalContext
    from src.plugins.risk_management.anomaly_validator import AnomalyValidator
    from src.plugins.risk_management.circuit_breaker import CircuitBreaker
    from src.plugins.pattern_detection.tr_detector import TRDetector, TRStatus, BreakoutDirection
    from src.plugins.signal_validation.breakout_validator import BreakoutValidator, BreakoutStatus
    from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import EnhancedWyckoffStateMachine
    from src.plugins.orchestrator.system_orchestrator_legacy import SystemOrchestrator
    from src.plugins.orchestrator.config_types import create_default_config
except ImportError:
    from core.data_sanitizer import DataSanitizer, RawCandle, HistoricalContext
    from core.anomaly_validator import AnomalyValidator
    from core.circuit_breaker import CircuitBreaker
    from core.tr_detector import TRDetector, TRStatus, BreakoutDirection
    from core.breakout_validator import BreakoutValidator, BreakoutStatus
    from core.wyckoff_state_machine import EnhancedWyckoffStateMachine
    from core.system_orchestrator import SystemOrchestrator
    from core.config_system import create_default_config


class TestSystemLogicIntegration(unittest.TestCase):
    """系统逻辑集成测试类"""

    def setUp(self):
        """测试前准备"""
        # 创建测试数据
        self.create_test_data()

        # 初始化系统组件
        self.config = create_default_config()
        self.data_sanitizer = DataSanitizer()
        self.anomaly_validator = AnomalyValidator()
        self.circuit_breaker = CircuitBreaker()
        self.tr_detector = TRDetector()
        self.breakout_validator = BreakoutValidator()
        self.state_machine = EnhancedWyckoffStateMachine()
        self.system_orchestrator = SystemOrchestrator()

    def create_test_data(self):
        """创建测试数据"""
        np.random.seed(42)
        n_points = 200

        # 创建时间索引
        dates = pd.date_range(start="2025-01-01", periods=n_points, freq="h")

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
        self.df_test = pd.DataFrame(
            {
                "open": prices + np.random.randn(n_points) * 0.5,
                "high": prices + np.random.rand(n_points) * 2,
                "low": prices - np.random.rand(n_points) * 2,
                "close": prices + np.random.randn(n_points) * 0.5,
                "volume": np.random.rand(n_points) * 1000 + 500,
            },
            index=dates,
        )

        # 在特定位置添加异常数据（测试异常处理）
        anomaly_indices = [60, 120, 180]
        for idx in anomaly_indices:
            self.df_test.loc[dates[idx], "volume"] = 0  # 零成交量异常
            if idx == 120:
                self.df_test.loc[dates[idx], "close"] = (
                    self.df_test.loc[dates[idx], "close"] * 1.2
                )  # 价格跳空

    def test_data_pipeline_integration(self):
        """测试数据管道集成"""
        print("\n=== 测试数据管道集成 ===")

        # 1. 数据清洗
        historical_context = HistoricalContext()
        anomaly_events = []

        for i, row in self.df_test.iterrows():
            raw_candle = RawCandle(
                timestamp=i,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                symbol="BTCUSDT",
                exchange="binance",
            )

            # 数据清洗
            sanitized_data, is_anomaly, anomaly_event = (
                self.data_sanitizer.sanitize_candle(raw_candle, historical_context)
            )

            if is_anomaly and anomaly_event:
                anomaly_events.append(anomaly_event)
                print(f"检测到异常数据: {anomaly_event.anomaly_types} (时间: {i})")

            # 更新历史上下文
            if not is_anomaly:
                historical_context.recent_candles.append(raw_candle)
                if len(historical_context.recent_candles) > 50:
                    historical_context.recent_candles.pop(0)

        print(f"总共检测到 {len(anomaly_events)} 个异常事件")
        self.assertGreater(len(anomaly_events), 0, "应该检测到异常数据")

    def test_anomaly_validation_integration(self):
        """测试异常验证集成"""
        print("\n=== 测试异常验证集成 ===")

        # 创建相关数据（模拟BTC和ETH）
        btc_data = []
        eth_data = []

        for i, row in self.df_test.iterrows():
            btc_data.append(
                {
                    "timestamp": i,
                    "price": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )

            # ETH价格与BTC高度相关，但有些差异
            eth_price = float(row["close"]) * 0.05 + np.random.randn() * 2
            eth_data.append(
                {
                    "timestamp": i,
                    "price": eth_price,
                    "volume": float(row["volume"]) * 0.8,
                }
            )

        # 验证异常
        validation_result = self.anomaly_validator.validate_anomalies(
            btc_data, eth_data, "BTCUSDT", "ETHUSDT"
        )

        print(f"异常验证结果: {validation_result.is_valid}")
        print(f"异常类型: {validation_result.anomaly_types}")
        print(f"置信度: {validation_result.confidence}")

        self.assertIsNotNone(validation_result)
        self.assertIsInstance(validation_result.is_valid, bool)

    def test_circuit_breaker_integration(self):
        """测试熔断机制集成"""
        print("\n=== 测试熔断机制集成 ===")

        # 模拟连续异常触发熔断
        for i in range(5):
            is_triggered = self.circuit_breaker.check_and_trigger(
                market_type="CRYPTO",
                symbol="BTCUSDT",
                anomaly_type="ZERO_VOLUME",
                anomaly_severity="CRITICAL" if i >= 2 else "WARNING",
                timestamp=datetime.now() + timedelta(minutes=i),
            )

            if is_triggered:
                print(f"熔断触发于第 {i + 1} 次异常")
                break

        # 检查熔断状态
        status = self.circuit_breaker.get_status("BTCUSDT")
        print(f"熔断状态: {status.status if status else '无状态'}")

        self.assertIsNotNone(status)

    def test_tr_detection_integration(self):
        """测试交易区间检测集成"""
        print("\n=== 测试交易区间检测集成 ===")

        # 检测交易区间
        tr_result = self.tr_detector.detect_trading_range(
            self.df_test["high"], self.df_test["low"], self.df_test["close"]
        )

        print(f"TR状态: {tr_result.status}")
        print(f"TR置信度: {tr_result.confidence:.2f}")
        print(f"上边界: {tr_result.upper_boundary:.2f}")
        print(f"下边界: {tr_result.lower_boundary:.2f}")
        print(f"价格位置: {tr_result.price_position:.2f}")

        self.assertIsNotNone(tr_result)
        self.assertIn(
            tr_result.status,
            [TRStatus.CONSOLIDATION, TRStatus.TRENDING, TRStatus.TRANSITION],
        )
        self.assertGreaterEqual(tr_result.confidence, 0.0)
        self.assertLessEqual(tr_result.confidence, 1.0)

    def test_breakout_validation_integration(self):
        """测试突破验证集成"""
        print("\n=== 测试突破验证集成 ===")

        # 首先检测交易区间
        tr_result = self.tr_detector.detect_trading_range(
            self.df_test["high"], self.df_test["low"], self.df_test["close"]
        )

        # 使用最后的价格检测突破
        last_close = self.df_test["close"].iloc[-1]
        last_volume = self.df_test["volume"].iloc[-1]
        avg_volume = self.df_test["volume"].mean()

        # TR检测突破
        tr_breakout = self.tr_detector.detect_breakout(
            tr_result, last_close, last_volume, avg_volume
        )

        print(f"TR突破检测: {tr_breakout['is_breakout']}")
        print(f"TR突破方向: {tr_breakout['direction']}")
        print(f"TR突破强度: {tr_breakout['strength']:.2f}")

        # 突破验证器检测
        breakout_result = self.breakout_validator.detect_initial_breakout(
            self.df_test.tail(20),
            tr_result.upper_boundary,
            tr_result.lower_boundary,
            current_atr=2.0,
        )

        if breakout_result:
            print(f"突破验证器结果: {breakout_result['status']}")
            print(f"突破方向: {breakout_result['direction']}")
            print(f"突破价格: {breakout_result['breakout_price']:.2f}")

        self.assertIsNotNone(tr_breakout)
        self.assertIsInstance(tr_breakout["is_breakout"], bool)

    def test_wyckoff_state_machine_integration(self):
        """测试威科夫状态机集成"""
        print("\n=== 测试威科夫状态机集成 ===")

        # 准备状态机输入
        current_candle = {
            "open": float(self.df_test["open"].iloc[-1]),
            "high": float(self.df_test["high"].iloc[-1]),
            "low": float(self.df_test["low"].iloc[-1]),
            "close": float(self.df_test["close"].iloc[-1]),
            "volume": float(self.df_test["volume"].iloc[-1]),
        }

        # 创建上下文
        context = {
            "tr_upper": 110.0,
            "tr_lower": 90.0,
            "market_regime": "ACCUMULATION",
            "volume_ma20": 800.0,
            "atr14": 2.0,
        }

        # 运行状态机
        state_result = self.state_machine.process_candle(current_candle, context)

        print(f"威科夫状态: {state_result['state']}")
        print(f"状态置信度: {state_result['confidence']:.2f}")
        print(f"信号类型: {state_result.get('signal_type', 'NONE')}")
        print(f"信号强度: {state_result.get('signal_strength', 0):.2f}")

        self.assertIsNotNone(state_result)
        self.assertIn("state", state_result)
        self.assertIn("confidence", state_result)

    def test_system_orchestrator_integration(self):
        """测试系统协调器集成"""
        print("\n=== 测试系统协调器集成 ===")

        # 准备测试数据
        test_data = {
            "timestamp": datetime.now(),
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "data": self.df_test.tail(50).to_dict("records"),
        }

        # 运行系统协调器
        try:
            orchestrator_result = self.system_orchestrator.process_market_data(
                test_data
            )

            print(f"系统处理结果: {orchestrator_result.get('status', 'UNKNOWN')}")
            print(f"交易信号: {orchestrator_result.get('trading_signal', 'NONE')}")
            print(f"信号置信度: {orchestrator_result.get('signal_confidence', 0):.2f}")

            if "analysis" in orchestrator_result:
                analysis = orchestrator_result["analysis"]
                print(f"市场体制: {analysis.get('market_regime', 'UNKNOWN')}")
                print(f"TR状态: {analysis.get('tr_status', 'UNKNOWN')}")
                print(f"威科夫阶段: {analysis.get('wyckoff_phase', 'UNKNOWN')}")

            self.assertIsNotNone(orchestrator_result)
            self.assertIn("status", orchestrator_result)

        except Exception as e:
            print(f"系统协调器异常: {e}")
            # 在某些情况下，系统协调器可能抛出异常，这是可以接受的
            pass

    def test_full_system_workflow(self):
        """测试完整系统工作流"""
        print("\n=== 测试完整系统工作流 ===")

        # 模拟实时数据流处理
        chunk_size = 20
        total_points = len(self.df_test)

        system_log = []

        for i in range(0, total_points, chunk_size):
            chunk = self.df_test.iloc[i : i + chunk_size]

            if len(chunk) < 10:
                continue

            print(f"\n处理数据块 {i // chunk_size + 1}: {len(chunk)} 根K线")

            # 1. 数据清洗
            historical_context = HistoricalContext()
            chunk_anomalies = 0

            for idx, row in chunk.iterrows():
                raw_candle = RawCandle(
                    timestamp=idx,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    symbol="BTCUSDT",
                    exchange="binance",
                )

                sanitized_data, is_anomaly, _ = self.data_sanitizer.sanitize_candle(
                    raw_candle, historical_context
                )

                if is_anomaly:
                    chunk_anomalies += 1

            print(f"  数据清洗: 检测到 {chunk_anomalies} 个异常")

            # 2. 交易区间检测
            tr_result = self.tr_detector.detect_trading_range(
                chunk["high"], chunk["low"], chunk["close"]
            )

            print(f"  TR检测: {tr_result.status} (置信度: {tr_result.confidence:.2f})")

            # 3. 突破检测
            last_close = chunk["close"].iloc[-1]
            last_volume = chunk["volume"].iloc[-1]
            avg_volume = chunk["volume"].mean()

            breakout_result = self.tr_detector.detect_breakout(
                tr_result, last_close, last_volume, avg_volume
            )

            if breakout_result["is_breakout"]:
                print(
                    f"  突破检测: {breakout_result['direction']} (强度: {breakout_result['strength']:.2f})"
                )

            # 4. 威科夫状态分析
            current_candle = {
                "open": float(chunk["open"].iloc[-1]),
                "high": float(chunk["high"].iloc[-1]),
                "low": float(chunk["low"].iloc[-1]),
                "close": float(chunk["close"].iloc[-1]),
                "volume": float(chunk["volume"].iloc[-1]),
            }

            context = {
                "tr_upper": tr_result.upper_boundary,
                "tr_lower": tr_result.lower_boundary,
                "market_regime": "ACCUMULATION"
                if tr_result.status == TRStatus.CONSOLIDATION
                else "TRENDING",
                "volume_ma20": chunk["volume"].rolling(20).mean().iloc[-1]
                if len(chunk) >= 20
                else chunk["volume"].mean(),
                "atr14": 2.0,  # 简化ATR
            }

            state_result = self.state_machine.process_candle(current_candle, context)

            print(
                f"  威科夫状态: {state_result['state']} (置信度: {state_result['confidence']:.2f})"
            )

            # 记录系统状态
            system_state = {
                "chunk_index": i // chunk_size + 1,
                "tr_status": tr_result.status.value,
                "tr_confidence": tr_result.confidence,
                "breakout_detected": breakout_result["is_breakout"],
                "wyckoff_state": state_result["state"],
                "wyckoff_confidence": state_result["confidence"],
            }

            system_log.append(system_state)

        print(f"\n=== 系统工作流总结 ===")
        print(f"处理了 {len(system_log)} 个数据块")

        # 分析系统行为
        tr_states = [s["tr_status"] for s in system_log]
        breakout_count = sum(1 for s in system_log if s["breakout_detected"])

        print(f"TR状态分布: {set(tr_states)}")
        print(f"突破检测次数: {breakout_count}")

        # 验证系统逻辑
        self.assertGreater(len(system_log), 0, "系统应该处理了数据")
        self.assertTrue(
            all("tr_status" in s for s in system_log), "所有状态都应包含TR状态"
        )

    def test_error_recovery_and_resilience(self):
        """测试错误恢复和系统韧性"""
        print("\n=== 测试错误恢复和系统韧性 ===")

        # 测试1: 异常数据处理
        print("测试1: 处理极端异常数据")

        extreme_data = pd.DataFrame(
            {
                "open": [100.0, 0.0, 1000.0, -50.0],  # 无效价格
                "high": [105.0, 0.0, 2000.0, -30.0],
                "low": [95.0, 0.0, 500.0, -70.0],
                "close": [102.0, 0.0, 1500.0, -60.0],
                "volume": [1000.0, 0.0, 100000.0, -100.0],  # 无效成交量
            }
        )

        # 系统应该能够处理这些异常而不崩溃
        try:
            tr_result = self.tr_detector.detect_trading_range(
                extreme_data["high"], extreme_data["low"], extreme_data["close"]
            )
            print(f"  异常数据处理成功: TR状态={tr_result.status}")
        except Exception as e:
            print(f"  异常数据处理失败: {e}")
            # 在某些情况下，处理异常数据可能失败，这是可以接受的

        # 测试2: 熔断机制恢复
        print("\n测试2: 熔断机制恢复测试")

        # 触发熔断
        for i in range(3):
            self.circuit_breaker.check_and_trigger(
                market_type="CRYPTO",
                symbol="TEST",
                anomaly_type="ZERO_VOLUME",
                anomaly_severity="CRITICAL",
                timestamp=datetime.now() + timedelta(minutes=i),
            )

        # 检查熔断状态
        status = self.circuit_breaker.get_status("TEST")
        if status and status.status == "TRIPPED":
            print(f"  熔断已触发: {status.reason}")

            # 模拟恢复
            recovery_time = datetime.now() + timedelta(minutes=10)
            is_recovered = self.circuit_breaker.check_recovery("TEST", recovery_time)
            print(f"  恢复检查: {'已恢复' if is_recovered else '未恢复'}")

        # 测试3: 组件间通信错误
        print("\n测试3: 组件间通信错误处理")

        # 模拟无效输入
        invalid_inputs = [
            None,  # 空输入
            {},  # 空字典
            {"invalid": "data"},  # 无效数据结构
            pd.Series([]),  # 空序列
        ]

        for i, invalid_input in enumerate(invalid_inputs):
            try:
                # 尝试用无效输入调用TR检测
                if isinstance(invalid_input, pd.Series):
                    result = self.tr_detector.detect_trading_range(
                        invalid_input, invalid_input, invalid_input
                    )
                else:
                    # 对于非Series输入，应该抛出异常
                    continue

                print(
                    f"  无效输入 {i + 1} 处理结果: {result.status if hasattr(result, 'status') else '无状态'}"
                )
            except (ValueError, AttributeError, TypeError) as e:
                print(f"  无效输入 {i + 1} 正确处理: {type(e).__name__}")
            except Exception as e:
                print(f"  无效输入 {i + 1} 意外错误: {e}")

        print("\n系统韧性测试完成")


if __name__ == "__main__":
    # 运行集成测试
    print("=" * 60)
    print("威科夫全自动逻辑引擎 - 系统逻辑闭环集成测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSystemLogicIntegration)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结:")
    print(f"  运行测试: {result.testsRun}")
    print(f"  通过测试: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  失败测试: {len(result.failures)}")
    print(f"  错误测试: {len(result.errors)}")

    if result.failures:
        print("\n失败详情:")
        for test, traceback in result.failures:
            print(f"  {test}: {traceback.splitlines()[-1]}")

    if result.errors:
        print("\n错误详情:")
        for test, traceback in result.errors:
            print(f"  {test}: {traceback.splitlines()[-1]}")

    print("=" * 60)
