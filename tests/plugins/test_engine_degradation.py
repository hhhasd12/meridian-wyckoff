"""WyckoffEngine 优雅降级测试

验证引擎4个阶段各自独立的 try/except 降级行为：
1. _run_perception 失败 → PerceptionResult(regime=UNKNOWN)
2. _run_fusion 失败 → FusionResult(resolved_bias=NEUTRAL)
3. _run_state_machine 失败 → WyckoffStateResult(state=IDLE)
4. _generate_decision 失败 → NEUTRAL signal
"""

from unittest.mock import patch

import pytest

from src.kernel.types import (
    FusionResult,
    PerceptionResult,
    TradingDecision,
    TradingSignal,
    WyckoffStateResult,
)
from src.plugins.wyckoff_engine.engine import (
    EngineEvents,
    WyckoffEngine,
    _default_fusion,
    _default_perception,
    _default_state_result,
)
from tests.fixtures.ohlcv_generator import make_multi_tf_data


@pytest.fixture
def engine() -> WyckoffEngine:
    return WyckoffEngine()


@pytest.fixture
def market_data():
    return make_multi_tf_data(h4_bars=100, trend="flat")


# ================================================================
# 阶段1降级：_run_perception 失败
# ================================================================


class TestPerceptionDegradation:
    """感知层失败时的优雅降级"""

    def test_perception_failure_returns_neutral(
        self, engine: WyckoffEngine, market_data
    ) -> None:
        """_run_perception 抛异常 → 继续执行，返回有效决策"""
        with patch.object(
            engine,
            "_run_perception",
            side_effect=RuntimeError("模拟感知层崩溃"),
        ):
            decision, events = engine.process_market_data(
                symbol="BTC/USDT",
                timeframes=list(market_data.keys()),
                data_dict=market_data,
            )
        assert isinstance(decision, TradingDecision)
        assert isinstance(events, EngineEvents)

    def test_perception_failure_uses_default(
        self, engine: WyckoffEngine, market_data
    ) -> None:
        """感知层失败时使用 UNKNOWN regime 默认值"""
        default = _default_perception()
        assert default.market_regime == "UNKNOWN"
        assert default.regime_confidence == 0.0
        assert default.fvg_signals == []
        assert default.anomaly_events == []


# ================================================================
# 阶段2降级：_run_fusion 失败
# ================================================================


class TestFusionDegradation:
    """融合层失败时的优雅降级"""

    def test_fusion_failure_returns_valid_decision(
        self, engine: WyckoffEngine, market_data
    ) -> None:
        """_run_fusion 抛异常 → 继续执行"""
        with patch.object(
            engine,
            "_run_fusion",
            side_effect=ValueError("模拟融合层崩溃"),
        ):
            decision, events = engine.process_market_data(
                symbol="BTC/USDT",
                timeframes=list(market_data.keys()),
                data_dict=market_data,
            )
        assert isinstance(decision, TradingDecision)
        assert isinstance(events, EngineEvents)

    def test_fusion_failure_uses_neutral_bias(self) -> None:
        """融合层失败时偏向 NEUTRAL"""
        default = _default_fusion()
        assert default.resolved_bias == "NEUTRAL"
        assert default.conflicts == []
        assert default.entry_validation is None


# ================================================================
# 阶段3降级：_run_state_machine 失败
# ================================================================


class TestStateMachineDegradation:
    """状态机失败时的优雅降级"""

    def test_state_machine_failure_returns_valid_decision(
        self, engine: WyckoffEngine, market_data
    ) -> None:
        """_run_state_machine 抛异常 → 继续执行"""
        with patch.object(
            engine,
            "_run_state_machine",
            side_effect=KeyError("模拟状态机崩溃"),
        ):
            decision, events = engine.process_market_data(
                symbol="BTC/USDT",
                timeframes=list(market_data.keys()),
                data_dict=market_data,
            )
        assert isinstance(decision, TradingDecision)
        assert isinstance(events, EngineEvents)

    def test_state_machine_failure_uses_idle_default(self) -> None:
        """状态机失败时默认 IDLE 状态"""
        default = _default_state_result()
        assert default.current_state == "IDLE"
        assert default.phase == "IDLE"
        assert default.confidence == 0.0
        assert default.state_changed is False
        assert default.heritage_score == 0.0


# ================================================================
# 阶段4降级：_generate_decision 失败
# ================================================================


class TestDecisionDegradation:
    """决策生成失败时的优雅降级"""

    def test_decision_failure_returns_neutral(
        self, engine: WyckoffEngine, market_data
    ) -> None:
        """_generate_decision 抛异常 → 返回 NEUTRAL 信号"""
        with patch.object(
            engine,
            "_generate_decision",
            side_effect=TypeError("模拟决策层崩溃"),
        ):
            decision, events = engine.process_market_data(
                symbol="BTC/USDT",
                timeframes=list(market_data.keys()),
                data_dict=market_data,
            )
        assert decision.signal == TradingSignal.NEUTRAL
        assert decision.confidence == 0.0
        assert "graceful degradation" in decision.reasoning[0].lower()

    def test_decision_failure_has_context(
        self, engine: WyckoffEngine, market_data
    ) -> None:
        """降级决策仍有完整 context"""
        with patch.object(
            engine,
            "_generate_decision",
            side_effect=Exception("模拟决策崩溃"),
        ):
            decision, _ = engine.process_market_data(
                symbol="BTC/USDT",
                timeframes=list(market_data.keys()),
                data_dict=market_data,
            )
        assert decision.context is not None
        assert decision.context.market_regime == "UNKNOWN"


# ================================================================
# 多阶段同时失败
# ================================================================


class TestMultiPhaseDegradation:
    """多阶段同时失败时的级联降级"""

    def test_all_phases_fail_still_returns_neutral(
        self, engine: WyckoffEngine, market_data
    ) -> None:
        """所有阶段都失败 → 仍返回 NEUTRAL 而非崩溃"""
        with (
            patch.object(
                engine,
                "_run_perception",
                side_effect=RuntimeError("感知层崩溃"),
            ),
            patch.object(
                engine,
                "_run_fusion",
                side_effect=RuntimeError("融合层崩溃"),
            ),
            patch.object(
                engine,
                "_run_state_machine",
                side_effect=RuntimeError("状态机崩溃"),
            ),
            patch.object(
                engine,
                "_generate_decision",
                side_effect=RuntimeError("决策层崩溃"),
            ),
        ):
            decision, events = engine.process_market_data(
                symbol="BTC/USDT",
                timeframes=list(market_data.keys()),
                data_dict=market_data,
            )
        assert decision.signal == TradingSignal.NEUTRAL
        assert decision.confidence == 0.0
        assert isinstance(events, EngineEvents)
