"""T1.1 — Hypothesis.bar_range + WyckoffStateResult.event_window 测试"""

import pytest
from src.plugins.wyckoff_state_machine.state_machine_v4 import (
    WyckoffStateMachineV4,
    Hypothesis,
    StateStatus,
)
from src.kernel.types import WyckoffStateResult


def _candle(open_=100.0, high=105.0, low=95.0, close=103.0, volume=1000.0):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _context(**kw):
    defaults = {
        "market_regime": "RANGING",
        "regime_confidence": 0.7,
        "tr_support": 90.0,
        "tr_resistance": 110.0,
    }
    defaults.update(kw)
    return defaults


class TestBarRange:
    """Hypothesis.bar_range 字段测试"""

    def test_hypothesis_bar_range_default_none(self):
        hyp = Hypothesis(
            event_name="PS",
            status=StateStatus.HYPOTHETICAL,
            confidence=0.3,
            proposed_at_bar=5,
        )
        assert hyp.bar_range is None

    def test_confirm_sets_bar_range(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.bars_processed = 10
        hyp = Hypothesis(
            event_name="PS",
            status=StateStatus.TESTING,
            confidence=0.6,
            proposed_at_bar=7,
            confirmation_quality=3.0,
        )
        sm.active_hypothesis = hyp
        sm._confirm_and_advance(hyp, _candle())
        # bar_range should be set before hypothesis was cleared
        assert hyp.bar_range == (7, 10)

    def test_event_window_in_result(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        sm.bars_processed = 10
        hyp = Hypothesis(
            event_name="PS",
            status=StateStatus.TESTING,
            confidence=0.6,
            proposed_at_bar=7,
            confirmation_quality=3.0,
        )
        sm.active_hypothesis = hyp
        sm._confirm_and_advance(hyp, _candle())
        result = sm._build_result(state_changed=True, previous_state="IDLE")
        assert result.event_window == (7, 10)

    def test_event_window_none_without_confirmation(self):
        sm = WyckoffStateMachineV4(timeframe="H4")
        result = sm._build_result(state_changed=False, previous_state="IDLE")
        assert result.event_window is None
