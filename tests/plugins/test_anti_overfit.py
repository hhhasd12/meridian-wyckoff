"""AntiOverfitGuard 单元测试"""

import pytest

from src.kernel.types import BacktestResult, BacktestTrade
from src.plugins.evolution.anti_overfit import (
    AntiOverfitConfig,
    AntiOverfitGuard,
)


def _make_trade(
    pnl_pct: float, entry_bar: int = 0, exit_bar: int = 10
) -> BacktestTrade:
    return BacktestTrade(
        entry_bar=entry_bar,
        exit_bar=exit_bar,
        entry_price=100.0,
        exit_price=100.0 * (1 + pnl_pct),
        side="LONG",
        size=1.0,
        pnl=100.0 * pnl_pct,
        pnl_pct=pnl_pct,
        exit_reason="TEST",
        hold_bars=exit_bar - entry_bar,
        entry_state="IDLE",
        max_favorable=abs(pnl_pct) * 100,
        max_adverse=abs(pnl_pct) * 50,
    )


def _make_result(pnl_pcts: list, sharpe: float = 1.0) -> BacktestResult:
    trades = []
    for i, pct in enumerate(pnl_pcts):
        trades.append(_make_trade(pct, entry_bar=i * 50, exit_bar=i * 50 + 10))
    return BacktestResult(
        trades=trades,
        total_return=sum(pnl_pcts),
        sharpe_ratio=sharpe,
        max_drawdown=0.1,
        win_rate=sum(1 for p in pnl_pcts if p > 0) / max(len(pnl_pcts), 1),
        profit_factor=2.0,
        total_trades=len(trades),
        avg_hold_bars=10.0,
        config_hash="test123",
    )


class TestMBL:
    def test_sufficient_data_passes(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(min_backtest_bars=100))
        result = _make_result([0.01] * 20, sharpe=1.5)
        verdict = guard.check(result)
        assert verdict.checks["MBL"] is True

    def test_insufficient_data_fails(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(min_backtest_bars=9999))
        result = _make_result([0.01] * 5, sharpe=1.0)
        verdict = guard.check(result)
        assert verdict.checks["MBL"] is False

    def test_no_trades_fails(self):
        guard = AntiOverfitGuard()
        result = _make_result([], sharpe=0.0)
        verdict = guard.check(result)
        assert verdict.checks["MBL"] is False


class TestOOSDR:
    def test_good_oos_passes(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(oos_dr_threshold=0.5))
        verdict = guard.check(
            _make_result([0.01] * 20),
            train_sharpes=[1.0, 1.0],
            test_sharpes=[0.8, 0.9],
        )
        assert verdict.checks["OOS_DR"] is True

    def test_bad_oos_fails(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(oos_dr_threshold=0.2))
        verdict = guard.check(
            _make_result([0.01] * 20),
            train_sharpes=[2.0, 2.0],
            test_sharpes=[0.1, 0.2],
        )
        assert verdict.checks["OOS_DR"] is False

    def test_no_wfa_data_passes(self):
        guard = AntiOverfitGuard()
        verdict = guard.check(_make_result([0.01] * 20))
        assert verdict.checks["OOS_DR"] is True


class TestDSR:
    def test_single_trial_uses_raw_sharpe(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(dsr_threshold=0.5))
        result = _make_result([0.01] * 20, sharpe=1.0)
        verdict = guard.check(result, n_trials=1)
        assert verdict.checks["DSR"] is True
        assert verdict.details["DSR"]["dsr"] == pytest.approx(1.0)

    def test_many_trials_deflates(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(dsr_threshold=0.5))
        result = _make_result([0.01] * 20, sharpe=1.0)
        verdict = guard.check(result, n_trials=100)
        assert verdict.details["DSR"]["dsr"] < 1.0


class TestMonteCarlo:
    def test_all_positive_returns_high_pvalue(self):
        # When all returns are positive, shuffling doesn't change Sharpe
        # so p_value should be ~1.0 (not significant) — this is CORRECT behavior
        guard = AntiOverfitGuard(AntiOverfitConfig(mc_n_permutations=50))
        result = _make_result([0.05, 0.03, 0.04, 0.02, 0.06])
        verdict = guard.check(result)
        # MC p-value is ~1.0 because shuffling returns with same stats gives same Sharpe
        assert verdict.details["MONTE_CARLO"]["p_value"] >= 0.5

    def test_few_trades_skips(self):
        guard = AntiOverfitGuard()
        result = _make_result([0.01, 0.02])
        verdict = guard.check(result)
        assert verdict.checks["MONTE_CARLO"] is True


class TestCPCV:
    def test_consistent_segments_pass(self):
        guard = AntiOverfitGuard(
            AntiOverfitConfig(cpcv_n_splits=3, cpcv_min_pass_ratio=0.6)
        )
        pnls = [0.01, 0.02, 0.03, 0.01, 0.02, 0.01, 0.03, 0.01, 0.02]
        result = _make_result(pnls)
        verdict = guard.check(result)
        assert verdict.checks["CPCV"] is True

    def test_too_few_trades_skips(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(cpcv_n_splits=5))
        result = _make_result([0.01, 0.02])
        verdict = guard.check(result)
        assert verdict.checks["CPCV"] is True


class TestOverallVerdict:
    def test_all_pass(self):
        guard = AntiOverfitGuard(
            AntiOverfitConfig(
                min_backtest_bars=10,
                mc_p_value_threshold=1.0,  # Disable MC filter for this test
            )
        )
        pnls = [0.05, 0.03, 0.04, 0.02, 0.06, 0.01, 0.03, 0.02, 0.04, 0.03]
        result = _make_result(pnls, sharpe=1.5)
        verdict = guard.check(
            result,
            train_sharpes=[1.5, 1.5],
            test_sharpes=[1.2, 1.3],
        )
        assert verdict.passed is True
        assert verdict.rejection_reason is None

    def test_failure_gives_reason(self):
        guard = AntiOverfitGuard(AntiOverfitConfig(min_backtest_bars=99999))
        result = _make_result([0.01] * 5)
        verdict = guard.check(result)
        assert verdict.passed is False
        assert verdict.rejection_reason is not None
        assert "MBL" in verdict.rejection_reason
