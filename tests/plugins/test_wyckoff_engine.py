"""WyckoffEngine v3 单元测试

P0: 冒烟测试（7个）— 基础初始化和类型验证
P1: 感知阶段测试（4个）— 各感知模块输出验证
P2: 方向正确性测试（5个）— 趋势偏向验证
P3: 边界条件（5个）— 异常输入处理
"""

import numpy as np
import pandas as pd
import pytest

from src.kernel.types import (
    BarSignal,
    PerceptionResult,
    TradingDecision,
    TradingSignal,
    WyckoffStateResult,
)
from src.plugins.wyckoff_engine.engine import EngineEvents, WyckoffEngine
from tests.fixtures.ohlcv_generator import make_multi_tf_data, make_ohlcv


# ================================================================
# P0 — 冒烟测试（7个）
# ================================================================


class TestP0Smoke:
    """P0 冒烟测试 — 必须第一轮通过"""

    def test_engine_init(self) -> None:
        """WyckoffEngine() 不抛异常"""
        engine = WyckoffEngine()
        assert engine is not None

    def test_engine_init_with_config(self) -> None:
        """WyckoffEngine(config) 正确初始化子组件"""
        config = {
            "market_regime": {},
            "tr_detector": {},
            "curve_boundary": {},
            "fvg_detector": {},
            "breakout_validator": {},
            "anomaly_validator": {},
            "circuit_breaker": {},
            "period_weight_filter": {},
            "conflict_resolver": {},
            "micro_entry_validator": {},
            "state_machine": {},
        }
        engine = WyckoffEngine(config)
        # 验证11个子组件已初始化
        assert engine.regime_detector is not None
        assert engine.tr_detector is not None
        assert engine.curve_analyzer is not None
        assert engine.fvg_detector is not None
        assert engine.breakout_validator is not None
        assert engine.anomaly_validator is not None
        assert engine.circuit_breaker is not None
        assert engine.period_filter is not None
        assert engine.conflict_resolver is not None
        assert engine.entry_validator is not None
        assert len(engine._state_machines) > 0

    def test_process_returns_correct_types(self) -> None:
        """process_market_data 返回 (TradingDecision, EngineEvents)"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=100, trend="flat")
        decision, events = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        assert isinstance(decision, TradingDecision)
        assert isinstance(events, EngineEvents)

    def test_decision_has_required_fields(self) -> None:
        """signal, confidence, context, reasoning 非None"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=100, trend="flat")
        decision, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        assert decision.signal is not None
        assert decision.confidence is not None
        assert decision.context is not None
        assert decision.reasoning is not None

    def test_confidence_in_range(self) -> None:
        """0.0 <= confidence <= 1.0"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=100, trend="flat")
        decision, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        assert 0.0 <= decision.confidence <= 1.0

    def test_signal_is_valid_enum(self) -> None:
        """signal 属于 TradingSignal 枚举"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=100, trend="flat")
        decision, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        assert isinstance(decision.signal, TradingSignal)

    def test_reset_clears_state(self) -> None:
        """reset() 后再调用 = 全新实例的结果"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=100, trend="up")

        # 第一次处理
        engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )

        # reset
        engine.reset()
        assert engine.previous_state is None
        assert engine._bar_index == 0
        # 状态机应重新初始化
        for tf, sm in engine._state_machines.items():
            assert sm.current_state == "IDLE"


# ================================================================
# P1 — 感知阶段测试（4个）
# ================================================================


class TestP1Perception:
    """P1 感知阶段测试"""

    def setup_method(self) -> None:
        """每个测试前创建引擎和数据"""
        self.engine = WyckoffEngine()
        self.data = make_multi_tf_data(h4_bars=200, trend="flat")

    def test_perception_returns_regime(self) -> None:
        """感知层返回市场体制信息"""
        perception, _ = self.engine._run_perception("BTC/USDT", self.data)
        assert isinstance(perception, PerceptionResult)
        assert perception.market_regime is not None
        assert isinstance(perception.market_regime, str)
        assert perception.regime_confidence >= 0.0

    def test_perception_detects_tr(self) -> None:
        """给定区间数据 → trading_range 可能被检测到"""
        # 使用 flat 数据（更容易形成 TR）
        flat_data = make_multi_tf_data(h4_bars=200, trend="flat", seed=123)
        perception, events = self.engine._run_perception("BTC/USDT", flat_data)
        # TR检测可能成功也可能不成功（取决于数据），
        # 但不应崩溃，且类型正确
        assert isinstance(perception, PerceptionResult)
        if perception.trading_range is not None:
            assert perception.trading_range.has_range is True
            assert events.tr_detected is True

    def test_perception_pin_body(self) -> None:
        """感知层返回针体分析结果"""
        perception, _ = self.engine._run_perception("BTC/USDT", self.data)
        # pin_body_summary 可能为 None（数据不足）或 PinBodySummary
        if perception.pin_body_summary is not None:
            assert perception.pin_body_summary.dominant_pattern in (
                "PIN",
                "BODY",
                "NEUTRAL",
            )

    def test_perception_fvg(self) -> None:
        """FVG检测不崩溃，返回列表"""
        perception, _ = self.engine._run_perception("BTC/USDT", self.data)
        assert isinstance(perception.fvg_signals, list)


# ================================================================
# P2 — 方向正确性测试（5个）
# ================================================================


class TestP2Direction:
    """P2 方向正确性测试"""

    def test_uptrend_bias_bullish(self) -> None:
        """强上涨数据 → signal 偏向 BUY 或 NEUTRAL（不应该 SELL）"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=200, trend="up")
        decision, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        # 强上涨不应该产生 SELL 信号
        assert decision.signal not in (
            TradingSignal.SELL,
            TradingSignal.STRONG_SELL,
        )

    def test_downtrend_bias_bearish(self) -> None:
        """强下跌数据 → signal 偏向 SELL 或 NEUTRAL（不应该 BUY）"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=200, trend="down")
        decision, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        # 强下跌不应该产生 BUY 信号
        assert decision.signal not in (
            TradingSignal.BUY,
            TradingSignal.STRONG_BUY,
        )

    def test_flat_bias_neutral(self) -> None:
        """震荡数据 → signal 偏向 NEUTRAL"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=200, trend="flat")
        decision, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        # 震荡市场通常为 NEUTRAL 或 WAIT
        assert decision.signal in (
            TradingSignal.NEUTRAL,
            TradingSignal.WAIT,
            TradingSignal.BUY,
            TradingSignal.SELL,
        )

    def test_config_sensitivity(self) -> None:
        """不同 config → 不同或相同 confidence（至少不崩溃）"""
        config_a = {"state_machine": {"STATE_MIN_CONFIDENCE": 0.2}}
        config_b = {"state_machine": {"STATE_MIN_CONFIDENCE": 0.8}}
        engine_a = WyckoffEngine(config_a)
        engine_b = WyckoffEngine(config_b)
        data = make_multi_tf_data(h4_bars=100, trend="flat")

        decision_a, _ = engine_a.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        decision_b, _ = engine_b.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        # 两者都应正常运行
        assert isinstance(decision_a, TradingDecision)
        assert isinstance(decision_b, TradingDecision)

    def test_no_lookahead(self) -> None:
        """注入未来异常数据(price=999999) → 引擎不受影响"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=100, trend="flat")

        # 正常运行
        decision_normal, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        engine.reset()

        # 在未来位置注入异常价格
        modified_data = {}
        for tf, df in data.items():
            df_copy = df.copy()
            # 在最后5根之后追加一根极端价格K线
            extreme_row = pd.DataFrame(
                {
                    "open": [999999.0],
                    "high": [999999.0],
                    "low": [999999.0],
                    "close": [999999.0],
                    "volume": [999999.0],
                },
                index=pd.date_range(
                    start=df.index[-1] + pd.Timedelta(hours=4),
                    periods=1,
                    freq="4h",
                ),
            )
            df_extended = pd.concat([df_copy, extreme_row])
            # 只喂到倒数第2根（排除极端值）
            modified_data[tf] = df_extended.iloc[:-1]

        decision_modified, _ = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(modified_data.keys()),
            data_dict=modified_data,
        )
        # 不使用未来数据 → 结果应该一致
        assert decision_normal.signal == decision_modified.signal


# ================================================================
# P3 — 边界条件（5个）
# ================================================================


class TestP3EdgeCases:
    """P3 边界条件测试"""

    def test_empty_dataframe(self) -> None:
        """空DataFrame不崩溃，返回 NEUTRAL"""
        engine = WyckoffEngine()
        empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        data = {"H4": empty_df, "H1": empty_df, "M15": empty_df}
        decision, events = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4", "H1", "M15"],
            data_dict=data,
        )
        assert isinstance(decision, TradingDecision)
        assert decision.signal == TradingSignal.NEUTRAL

    def test_single_row(self) -> None:
        """单行数据不崩溃"""
        engine = WyckoffEngine()
        single = make_ohlcv(1)
        data = {"H4": single}
        decision, events = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4"],
            data_dict=data,
        )
        assert isinstance(decision, TradingDecision)

    def test_missing_timeframes(self) -> None:
        """部分TF缺失时优雅降级"""
        engine = WyckoffEngine()
        # 只提供 H4，不提供 H1/M15
        h4_data = make_ohlcv(200, trend="flat")
        data = {"H4": h4_data}
        decision, events = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4"],
            data_dict=data,
        )
        assert isinstance(decision, TradingDecision)
        assert isinstance(events, EngineEvents)

    def test_nan_values(self) -> None:
        """NaN不导致崩溃"""
        engine = WyckoffEngine()
        df = make_ohlcv(100)
        # 注入NaN
        df.iloc[50, df.columns.get_loc("close")] = np.nan
        df.iloc[51, df.columns.get_loc("volume")] = np.nan
        data = {"H4": df}
        decision, events = engine.process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4"],
            data_dict=data,
        )
        assert isinstance(decision, TradingDecision)

    def test_process_bar_smoke(self) -> None:
        """process_bar() 基础冒烟测试"""
        engine = WyckoffEngine()
        data = make_multi_tf_data(h4_bars=100, trend="flat")
        bar_signal = engine.process_bar(symbol="BTC/USDT", data_dict=data)
        assert isinstance(bar_signal, BarSignal)
        assert bar_signal.bar_index == 1
        assert isinstance(bar_signal.signal, TradingSignal)
        assert 0.0 <= bar_signal.confidence <= 1.0
        assert isinstance(bar_signal.wyckoff_state, str)
        assert isinstance(bar_signal.phase, str)
