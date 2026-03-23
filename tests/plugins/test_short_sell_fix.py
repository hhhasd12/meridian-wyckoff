"""做空条件正确性测试

验证合约做空逻辑的条件守卫链：
1. allow_shorting=True AND trading_mode="futures"
2. state.direction == DISTRIBUTION
3. state.current_state in {UT, UTAD, ST_DIST, LPSY}
4. market_regime 包含 BEARISH 或 DOWN

关键测试：
- DISTRIBUTION + NEUTRAL regime → 不触发做空信号
- DISTRIBUTION + BEARISH regime → 触发做空信号
"""

import pytest

from src.kernel.types import (
    BreakoutInfo,
    EntryValidation,
    FusionResult,
    PerceptionResult,
    StateDirection,
    StateEvidence,
    TradingSignal,
    WyckoffSignal,
    WyckoffStateResult,
)
from src.plugins.wyckoff_engine.engine import WyckoffEngine


def _make_perception(market_regime: str = "NEUTRAL") -> PerceptionResult:
    """构造最小感知结果"""
    return PerceptionResult(
        market_regime=market_regime,
        regime_confidence=0.7,
        trading_range=None,
        fvg_signals=[],
        breakout_status=BreakoutInfo(
            is_valid=False,
            direction=0,
            breakout_level=0.0,
            breakout_strength=0.0,
            volume_confirmation=False,
        ),
        pin_body_summary=None,
        candle_physical=None,
        anomaly_events=[],
    )


def _make_fusion() -> FusionResult:
    """构造最小融合结果"""
    return FusionResult(
        timeframe_weights={"H4": 0.5, "H1": 0.3, "M15": 0.2},
        conflicts=[],
        resolved_bias="NEUTRAL",
        entry_validation=None,
    )


def _make_state(
    current_state: str = "UT",
    direction: StateDirection = StateDirection.DISTRIBUTION,
    signal: WyckoffSignal = WyckoffSignal.NO_SIGNAL,
    confidence: float = 0.85,
) -> WyckoffStateResult:
    """构造最小状态机结果"""
    return WyckoffStateResult(
        current_state=current_state,
        phase="C",
        direction=direction,
        confidence=confidence,
        intensity=0.7,
        evidences=[],
        signal=signal,
        signal_strength="none",
        state_changed=False,
        previous_state=None,
        heritage_score=0.5,
    )


class TestShortSellCondition:
    """做空条件守卫链测试"""

    def setup_method(self) -> None:
        """配置允许做空的合约引擎"""
        self.engine = WyckoffEngine(
            {
                "trading_mode": "futures",
                "allow_shorting": True,
                "leverage": 3,
            }
        )

    def test_distribution_neutral_regime_no_short(self) -> None:
        """DISTRIBUTION + UT状态 + NEUTRAL regime → 不触发做空信号

        做空需要 BEARISH/DOWN regime 确认，NEUTRAL 不应触发。
        """
        perception = _make_perception(market_regime="NEUTRAL")
        fusion = _make_fusion()
        state = _make_state(
            current_state="UT",
            direction=StateDirection.DISTRIBUTION,
            signal=WyckoffSignal.NO_SIGNAL,
            confidence=0.85,
        )

        decision = self.engine._generate_decision(perception, fusion, state)

        # 没有 BEARISH/DOWN regime，不应产生 SELL 信号
        assert decision.signal not in [
            TradingSignal.SELL,
            TradingSignal.STRONG_SELL,
        ], f"NEUTRAL regime should not trigger short signal, got {decision.signal}"

    def test_distribution_bearish_regime_triggers_short(self) -> None:
        """DISTRIBUTION + UT状态 + BEARISH regime → 触发做空信号

        所有4层守卫都满足，应产生 SELL 或 STRONG_SELL。
        """
        perception = _make_perception(market_regime="BEARISH_TRENDING")
        fusion = _make_fusion()
        state = _make_state(
            current_state="UT",
            direction=StateDirection.DISTRIBUTION,
            signal=WyckoffSignal.NO_SIGNAL,
            confidence=0.85,
        )

        decision = self.engine._generate_decision(perception, fusion, state)

        # BEARISH regime + DISTRIBUTION + UT → 应触发做空
        assert decision.signal in [
            TradingSignal.SELL,
            TradingSignal.STRONG_SELL,
        ], (
            f"BEARISH regime with DISTRIBUTION/UT should trigger short, "
            f"got {decision.signal}"
        )

    def test_distribution_down_regime_triggers_short(self) -> None:
        """DISTRIBUTION + UTAD状态 + DOWN regime → 触发做空信号"""
        perception = _make_perception(market_regime="DOWNTREND")
        fusion = _make_fusion()
        state = _make_state(
            current_state="UTAD",
            direction=StateDirection.DISTRIBUTION,
            signal=WyckoffSignal.NO_SIGNAL,
            confidence=0.85,
        )

        decision = self.engine._generate_decision(perception, fusion, state)

        assert decision.signal in [
            TradingSignal.SELL,
            TradingSignal.STRONG_SELL,
        ], (
            f"DOWN regime with DISTRIBUTION/UTAD should trigger short, "
            f"got {decision.signal}"
        )

    def test_accumulation_bearish_regime_no_short(self) -> None:
        """ACCUMULATION方向 + BEARISH regime → 不触发做空

        即使regime是BEARISH，direction不是DISTRIBUTION也不应做空。
        """
        perception = _make_perception(market_regime="BEARISH_TRENDING")
        fusion = _make_fusion()
        state = _make_state(
            current_state="PS",
            direction=StateDirection.ACCUMULATION,
            signal=WyckoffSignal.NO_SIGNAL,
            confidence=0.85,
        )

        decision = self.engine._generate_decision(perception, fusion, state)

        assert decision.signal not in [
            TradingSignal.SELL,
            TradingSignal.STRONG_SELL,
        ], f"ACCUMULATION direction should not trigger short, got {decision.signal}"

    def test_spot_mode_no_short(self) -> None:
        """现货模式 → 即使条件全满足也不做空"""
        engine = WyckoffEngine(
            {
                "trading_mode": "spot",
                "allow_shorting": True,
            }
        )
        perception = _make_perception(market_regime="BEARISH_TRENDING")
        fusion = _make_fusion()
        state = _make_state(
            current_state="UT",
            direction=StateDirection.DISTRIBUTION,
            signal=WyckoffSignal.NO_SIGNAL,
            confidence=0.85,
        )

        decision = engine._generate_decision(perception, fusion, state)

        # 现货模式不能做空
        assert decision.signal not in [
            TradingSignal.SELL,
            TradingSignal.STRONG_SELL,
        ], f"Spot mode should not trigger short, got {decision.signal}"

    def test_non_distribution_structure_no_short(self) -> None:
        """DISTRIBUTION方向但非派发结构状态 → 不触发做空

        current_state 不在 {UT, UTAD, ST_DIST, LPSY} 中。
        """
        perception = _make_perception(market_regime="BEARISH_TRENDING")
        fusion = _make_fusion()
        state = _make_state(
            current_state="BC",  # BC 不在派发结构集合中
            direction=StateDirection.DISTRIBUTION,
            signal=WyckoffSignal.NO_SIGNAL,
            confidence=0.85,
        )

        decision = self.engine._generate_decision(perception, fusion, state)

        assert decision.signal not in [
            TradingSignal.SELL,
            TradingSignal.STRONG_SELL,
        ], (
            f"Non-distribution structure (BC) should not trigger short, "
            f"got {decision.signal}"
        )
