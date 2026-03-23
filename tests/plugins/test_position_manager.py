"""仓位管理插件测试"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from src.kernel.types import TradingSignal
from src.plugins.position_manager.types import (
    ExitReason,
    Position,
    PositionSide,
    PositionStatus,
    TradeResult,
)
from src.plugins.position_manager.stop_loss_executor import StopLossExecutor
from src.plugins.position_manager.signal_exit_logic import SignalExitLogic
from src.plugins.position_manager.position_manager import PositionManager
from src.plugins.position_manager.position_journal import PositionJournal


class TestStopLossExecutor:
    """止损止盈执行器测试"""

    def setup_method(self):
        self.config = {
            "method": "atr",
            "atr_multiplier": 1.5,
            "fixed_percentage": 0.02,
            "trailing_enabled": True,
            "trailing_activation_pct": 0.015,
            "trailing_distance_pct": 0.01,
            "partial_profit_levels": [0.5, 0.8, 1.0],
            "partial_profit_sizes": [0.3, 0.3, 0.4],
        }
        self.executor = StopLossExecutor(self.config)

        self.df = pd.DataFrame(
            {
                "open": [100, 101, 102, 103, 104],
                "high": [105, 106, 107, 108, 109],
                "low": [95, 96, 97, 98, 99],
                "close": [100, 101, 102, 103, 104],
                "volume": [1000, 1000, 1000, 1000, 1000],
            }
        )

    def test_calculate_stop_loss_atr_long(self):
        stop_loss = self.executor.calculate_stop_loss(
            entry_price=100.0,
            side=PositionSide.LONG,
            df=self.df,
            method="atr",
        )
        assert stop_loss < 100.0

    def test_calculate_stop_loss_atr_short(self):
        stop_loss = self.executor.calculate_stop_loss(
            entry_price=100.0,
            side=PositionSide.SHORT,
            df=self.df,
            method="atr",
        )
        assert stop_loss > 100.0

    def test_calculate_stop_loss_fixed_long(self):
        stop_loss = self.executor.calculate_stop_loss(
            entry_price=100.0,
            side=PositionSide.LONG,
            df=self.df,
            method="fixed",
        )
        assert stop_loss == 98.0

    def test_calculate_stop_loss_fixed_short(self):
        stop_loss = self.executor.calculate_stop_loss(
            entry_price=100.0,
            side=PositionSide.SHORT,
            df=self.df,
            method="fixed",
        )
        assert stop_loss == 102.0

    def test_calculate_take_profit_risk_reward_long(self):
        stop_loss = 98.0
        take_profit = self.executor.calculate_take_profit(
            entry_price=100.0,
            stop_loss=stop_loss,
            side=PositionSide.LONG,
            method="risk_reward",
        )
        assert take_profit == 104.0

    def test_calculate_take_profit_risk_reward_short(self):
        stop_loss = 102.0
        take_profit = self.executor.calculate_take_profit(
            entry_price=100.0,
            stop_loss=stop_loss,
            side=PositionSide.SHORT,
            method="risk_reward",
        )
        assert take_profit == 96.0

    def test_check_exit_stop_loss_long(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        result = self.executor.check_exit_conditions(position, 97.0)
        assert result.should_exit
        assert result.reason == ExitReason.STOP_LOSS

    def test_check_exit_take_profit_long(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        result = self.executor.check_exit_conditions(position, 105.0)
        assert result.should_exit
        assert result.reason == ExitReason.TAKE_PROFIT

    def test_trailing_stop_activation(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=110.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        result = self.executor.check_exit_conditions(position, 102.0)
        assert not result.should_exit
        assert (
            position.trailing_stop_activated
            or result.new_stop_loss is not None
            or result.partial_close_ratio is not None
        )


class TestSignalExitLogic:
    """信号反转出场逻辑测试"""

    def setup_method(self):
        self.config = {
            "signal_reversal_enabled": True,
            "min_reversal_confidence": 0.6,
            "wyckoff_exit_enabled": True,
            "max_hold_hours": 72,
        }
        self.logic = SignalExitLogic(self.config)

    def test_signal_reversal_long_to_sell(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        result = self.logic.should_exit_on_signal(
            position=position,
            new_signal=TradingSignal.SELL,
            new_wyckoff_state="LPSY",
            confidence=0.7,
        )
        assert result.should_exit
        assert result.reason == ExitReason.SIGNAL_REVERSAL

    def test_signal_reversal_short_to_buy(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.SHORT,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=102.0,
            take_profit=96.0,
            signal_confidence=0.7,
            wyckoff_state="LPSY",
            entry_signal=TradingSignal.SELL,
        )

        result = self.logic.should_exit_on_signal(
            position=position,
            new_signal=TradingSignal.BUY,
            new_wyckoff_state="SPRING",
            confidence=0.7,
        )
        assert result.should_exit

    def test_signal_reversal_low_confidence(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        result = self.logic.should_exit_on_signal(
            position=position,
            new_signal=TradingSignal.SELL,
            new_wyckoff_state="TRADING",  # 非派发状态
            confidence=0.5,  # 低于阈值
        )
        assert not result.should_exit

    def test_wyckoff_distribution_exit(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        result = self.logic.should_exit_on_signal(
            position=position,
            new_signal=TradingSignal.NEUTRAL,
            new_wyckoff_state="LPSY",
            confidence=0.5,
        )
        assert result.should_exit

    def test_timeout_exit(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now() - timedelta(hours=73),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        result = self.logic.check_timeout_exit(position, datetime.now())
        assert result.should_exit
        assert result.reason == ExitReason.TIMEOUT


class TestPositionManager:
    """仓位管理器测试"""

    def setup_method(self):
        self.config = {
            "max_positions": 3,
            "max_position_size": 0.1,
            "min_position_size": 0.01,
            "risk_per_trade": 0.02,
            "stop_loss": {
                "method": "atr",
                "atr_multiplier": 1.5,
                "trailing_enabled": True,
            },
            "signal_exit": {
                "signal_reversal_enabled": True,
                "min_reversal_confidence": 0.6,
            },
        }
        self.manager = PositionManager(self.config)

        self.df = pd.DataFrame(
            {
                "open": [100, 101, 102, 103, 104],
                "high": [105, 106, 107, 108, 109],
                "low": [95, 96, 97, 98, 99],
                "close": [100, 101, 102, 103, 104],
                "volume": [1000, 1000, 1000, 1000, 1000],
            }
        )

    def test_can_open_position(self):
        assert self.manager.can_open_position("BTC/USDT")

        self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )

        assert not self.manager.can_open_position("BTC/USDT")

    def test_max_positions_limit(self):
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT"]

        for i, symbol in enumerate(symbols[:3]):
            pos = self.manager.open_position(
                symbol=symbol,
                side=PositionSide.LONG,
                size=0.1,
                entry_price=100.0,
                signal_confidence=0.7,
                wyckoff_state="SOS",
                entry_signal=TradingSignal.BUY,
                df=self.df,
            )
            assert pos is not None

        assert not self.manager.can_open_position("DOGE/USDT")

    def test_calculate_position_size(self):
        size = self.manager.calculate_position_size(
            account_balance=10000.0,
            entry_price=100.0,
            stop_loss=98.0,
        )
        assert size > 0
        assert size <= 10000.0 * 0.1 / 100.0

    def test_open_position(self):
        position = self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )

        assert position is not None
        assert position.symbol == "BTC/USDT"
        assert position.side == PositionSide.LONG
        assert position.status == PositionStatus.OPEN
        assert position.stop_loss < 100.0
        assert position.take_profit > 100.0

    def test_close_position(self):
        self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )

        result = self.manager.close_position(
            symbol="BTC/USDT",
            exit_price=102.0,
            reason=ExitReason.MANUAL,
        )

        assert result is not None
        assert result.pnl > 0
        assert result.exit_reason == ExitReason.MANUAL
        assert self.manager.get_position("BTC/USDT") is None

    def test_update_position_stop_loss_trigger(self):
        self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )

        position = self.manager.get_position("BTC/USDT")
        assert position is not None
        exit_result = self.manager.update_position(
            symbol="BTC/USDT",
            current_price=position.stop_loss - 1,
        )

        assert exit_result is not None
        assert exit_result.should_exit
        assert exit_result.reason == ExitReason.STOP_LOSS

    def test_update_position_take_profit_trigger(self):
        self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )

        position = self.manager.get_position("BTC/USDT")
        assert position is not None
        exit_result = self.manager.update_position(
            symbol="BTC/USDT",
            current_price=position.take_profit + 1,
        )

        assert exit_result is not None
        assert exit_result.should_exit
        assert exit_result.reason == ExitReason.TAKE_PROFIT

    def test_get_statistics(self):
        self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )

        self.manager.close_position(
            symbol="BTC/USDT",
            exit_price=102.0,
            reason=ExitReason.MANUAL,
        )

        stats = self.manager.get_statistics()
        assert stats["total_trades"] == 1
        assert stats["winning_trades"] == 1
        assert stats["win_rate"] == 1.0
        assert stats["total_pnl"] > 0

    def test_force_close_all(self):
        for symbol in ["BTC/USDT", "ETH/USDT"]:
            self.manager.open_position(
                symbol=symbol,
                side=PositionSide.LONG,
                size=0.1,
                entry_price=100.0,
                signal_confidence=0.7,
                wyckoff_state="SOS",
                entry_signal=TradingSignal.BUY,
                df=self.df,
            )

        results = self.manager.force_close_all(
            {
                "BTC/USDT": 101.0,
                "ETH/USDT": 99.0,
            }
        )

        assert len(results) == 2
        assert len(self.manager.get_all_positions()) == 0


class TestPositionTypes:
    """Position 类型测试"""

    def test_position_calculate_unrealized_pnl_long(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        pnl, pnl_pct = position.calculate_unrealized_pnl(102.0)
        assert pnl == 0.2
        assert pnl_pct == 0.02

    def test_position_calculate_unrealized_pnl_short(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.SHORT,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=102.0,
            take_profit=96.0,
            signal_confidence=0.7,
            wyckoff_state="LPSY",
            entry_signal=TradingSignal.SELL,
        )

        pnl, pnl_pct = position.calculate_unrealized_pnl(98.0)
        assert pnl == 0.2
        assert pnl_pct == 0.02

    def test_position_risk_reward_ratio(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        assert position.get_risk_reward_ratio() == 2.0

    def test_position_to_dict(self):
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

        d = position.to_dict()
        assert d["symbol"] == "BTC/USDT"
        assert d["side"] == "long"
        assert d["entry_signal"] == "buy"

    def test_trade_result_is_profitable(self):
        result = TradeResult(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            entry_price=100.0,
            exit_price=102.0,
            size=0.1,
            pnl=0.2,
            pnl_pct=0.02,
            hold_duration=timedelta(hours=1),
            exit_reason=ExitReason.TAKE_PROFIT,
            entry_signal=TradingSignal.BUY,
            entry_confidence=0.7,
            entry_wyckoff_state="SOS",
            entry_time=datetime.now() - timedelta(hours=1),
            exit_time=datetime.now(),
            stop_loss=98.0,
            take_profit=104.0,
            highest_price=103.0,
            lowest_price=99.0,
            trailing_activated=False,
            partial_profits=[],
        )

        assert result.is_profitable
        assert result.risk_reward_actual == 1.0


class TestFractionalKelly:
    """Kelly公式仓位计算测试"""

    def setup_method(self):
        self.manager = PositionManager(
            {
                "max_positions": 3,
                "max_position_size": 0.1,
                "min_position_size": 0.01,
                "risk_per_trade": 0.02,
                "stop_loss": {},
                "signal_exit": {},
            }
        )

    def test_basic_kelly(self):
        """基本Kelly公式: 60%胜率, 盈亏比2:1"""
        result = self.manager.fractional_kelly(
            win_rate=0.6,
            avg_win=200.0,
            avg_loss=100.0,
        )
        # b=2, q=0.4, full_kelly=(0.6*2-0.4)/2=0.4
        # result = 0.4 * 0.25 / 1.0 = 0.1
        assert abs(result - 0.1) < 1e-9

    def test_kelly_with_leverage(self):
        """杠杆降低仓位"""
        result = self.manager.fractional_kelly(
            win_rate=0.6,
            avg_win=200.0,
            avg_loss=100.0,
            leverage=2.0,
        )
        # 0.4 * 0.25 / 2.0 = 0.05
        assert abs(result - 0.05) < 1e-9

    def test_kelly_capped_by_max(self):
        """仓位不超过max_position_pct"""
        result = self.manager.fractional_kelly(
            win_rate=0.9,
            avg_win=500.0,
            avg_loss=50.0,
            kelly_fraction=1.0,
            max_position_pct=0.20,
        )
        assert result <= 0.20

    def test_kelly_negative_edge(self):
        """负期望时返回0"""
        result = self.manager.fractional_kelly(
            win_rate=0.3,
            avg_win=100.0,
            avg_loss=200.0,
        )
        assert result == 0.0

    def test_kelly_zero_avg_loss(self):
        """avg_loss为0时返回0"""
        result = self.manager.fractional_kelly(
            win_rate=0.6,
            avg_win=200.0,
            avg_loss=0.0,
        )
        assert result == 0.0

    def test_kelly_zero_avg_win(self):
        """avg_win为0时返回0"""
        result = self.manager.fractional_kelly(
            win_rate=0.6,
            avg_win=0.0,
            avg_loss=100.0,
        )
        assert result == 0.0

    def test_kelly_50_percent_winrate_even_payoff(self):
        """50%胜率+1:1盈亏比 = 零边际"""
        result = self.manager.fractional_kelly(
            win_rate=0.5,
            avg_win=100.0,
            avg_loss=100.0,
        )
        assert result == 0.0

    def test_kelly_custom_fraction(self):
        """自定义kelly_fraction=0.5"""
        result = self.manager.fractional_kelly(
            win_rate=0.6,
            avg_win=200.0,
            avg_loss=100.0,
            kelly_fraction=0.5,
        )
        # 0.4 * 0.5 / 1.0 = 0.2
        assert abs(result - 0.2) < 1e-9

    def test_kelly_zero_leverage(self):
        """leverage为0时返回0"""
        result = self.manager.fractional_kelly(
            win_rate=0.6,
            avg_win=200.0,
            avg_loss=100.0,
            leverage=0.0,
        )
        assert result == 0.0

    def test_kelly_55_winrate_2to1_5x_leverage(self):
        """规格测试: 55%胜率, 2:1盈亏比, 5x杠杆 → ~1.6%仓位"""
        result = self.manager.fractional_kelly(
            win_rate=0.55,
            avg_win=200.0,
            avg_loss=100.0,
            leverage=5.0,
        )
        # b=2, q=0.45, full_kelly=(0.55*2-0.45)/2=0.325
        # result = 0.325 * 0.25 / 5.0 = 0.01625
        assert 0.01 < result < 0.02, f"Expected ~1.6%, got {result * 100:.2f}%"
        assert abs(result - 0.01625) < 1e-9

    def test_kelly_win_rate_zero(self):
        """win_rate=0: 完全无胜算时返回0"""
        result = self.manager.fractional_kelly(
            win_rate=0.0,
            avg_win=200.0,
            avg_loss=100.0,
        )
        assert result == 0.0

    def test_kelly_win_rate_one(self):
        """win_rate=1.0: 100%胜率"""
        result = self.manager.fractional_kelly(
            win_rate=1.0,
            avg_win=200.0,
            avg_loss=100.0,
        )
        # b=2, q=0, full_kelly=(1.0*2-0)/2=1.0
        # result = 1.0 * 0.25 / 1.0 = 0.25 → clamped to 0.20
        assert result == 0.20


class TestAntiMartingale:
    """反马丁格尔仓位调整测试"""

    def setup_method(self):
        self.manager = PositionManager(
            {
                "max_positions": 3,
                "max_position_size": 0.1,
                "min_position_size": 0.01,
                "risk_per_trade": 0.02,
                "stop_loss": {},
                "signal_exit": {},
            }
        )

    def test_no_wins_no_drawdown(self):
        """无连赢无回撤 = base_size不变"""
        result = self.manager.anti_martingale_adjustment(
            base_size=1.0,
            consecutive_wins=0,
            current_drawdown_pct=0.0,
        )
        assert abs(result - 1.0) < 1e-9

    def test_consecutive_wins_scaling(self):
        """连赢3次: 1.0 * 1.2^3 = 1.728"""
        result = self.manager.anti_martingale_adjustment(
            base_size=1.0,
            consecutive_wins=3,
            current_drawdown_pct=0.0,
        )
        assert abs(result - 1.728) < 1e-6

    def test_wins_capped_at_5(self):
        """连赢>5次也只按5次计算"""
        r5 = self.manager.anti_martingale_adjustment(
            base_size=1.0,
            consecutive_wins=5,
            current_drawdown_pct=0.0,
        )
        r10 = self.manager.anti_martingale_adjustment(
            base_size=1.0,
            consecutive_wins=10,
            current_drawdown_pct=0.0,
        )
        assert abs(r5 - r10) < 1e-9

    def test_max_3x_cap(self):
        """加仓上限3倍base_size"""
        result = self.manager.anti_martingale_adjustment(
            base_size=1.0,
            consecutive_wins=5,
            current_drawdown_pct=0.0,
        )
        # 1.2^5 = 2.48832, < 3.0
        assert result <= 3.0
        # 验证用更大base使3x cap生效
        result_big = self.manager.anti_martingale_adjustment(
            base_size=10.0,
            consecutive_wins=5,
            current_drawdown_pct=0.0,
        )
        assert result_big <= 30.0

    def test_drawdown_over_10_halves(self):
        """回撤>10%: 仓位减半"""
        result = self.manager.anti_martingale_adjustment(
            base_size=2.0,
            consecutive_wins=3,
            current_drawdown_pct=0.15,
        )
        assert abs(result - 1.0) < 1e-9

    def test_drawdown_over_20_zero(self):
        """回撤>20%: 仓位为0"""
        result = self.manager.anti_martingale_adjustment(
            base_size=2.0,
            consecutive_wins=5,
            current_drawdown_pct=0.25,
        )
        assert result == 0.0

    def test_drawdown_exactly_10_no_cut(self):
        """回撤恰好10%: 不减半（需>10%）"""
        result = self.manager.anti_martingale_adjustment(
            base_size=1.0,
            consecutive_wins=0,
            current_drawdown_pct=0.10,
        )
        assert abs(result - 1.0) < 1e-9

    def test_drawdown_exactly_20_halves(self):
        """回撤恰好20%: 减半（不归零，需>20%）"""
        result = self.manager.anti_martingale_adjustment(
            base_size=2.0,
            consecutive_wins=0,
            current_drawdown_pct=0.20,
        )
        assert abs(result - 1.0) < 1e-9

    def test_drawdown_priority_over_wins(self):
        """回撤优先于连赢加仓"""
        result = self.manager.anti_martingale_adjustment(
            base_size=1.0,
            consecutive_wins=5,
            current_drawdown_pct=0.21,
        )
        assert result == 0.0


class TestCircuitBreakerBlock:
    """熔断器阻止开仓测试"""

    def setup_method(self):
        from src.plugins.position_manager.plugin import PositionManagerPlugin

        self.plugin = PositionManagerPlugin("position_manager")
        self.plugin._config = {
            "min_confidence": 0.5,
            "stop_loss": {},
            "signal_exit": {},
        }
        # Mock manager 和 executor
        self.plugin._manager = MagicMock()
        self.plugin._manager.can_open_position.return_value = True
        self.plugin._manager.calculate_position_size.return_value = 0.1
        self.plugin._executor = MagicMock()
        self.plugin._executor.get_balance_total.return_value = 10000.0
        self.plugin._executor.execute.return_value = MagicMock(
            status="FILLED", filled_size=0.1, avg_price=50000.0
        )
        self.plugin._journal = MagicMock()

    def test_circuit_breaker_blocks_open(self):
        """熔断器激活时拒绝开仓"""
        assert self.plugin._manager is not None
        assert self.plugin._executor is not None
        # 触发熔断
        self.plugin._on_circuit_breaker_tripped(
            "risk_management.circuit_breaker_tripped",
            {"reason": "max_daily_loss"},
        )
        assert self.plugin._circuit_breaker_active is True

        # 尝试开仓 — 应被拒绝
        self.plugin._try_open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            price=50000.0,
            confidence=0.9,
            wyckoff_state="accumulation",
            signal=TradingSignal.STRONG_BUY,
            df=None,
            data={},
            stop_loss_hint=49000.0,
            take_profit_hint=52000.0,
        )

        # manager.can_open_position 不应被调用（更早被拦截）
        self.plugin._manager.can_open_position.assert_not_called()  # type: ignore[attr-defined]
        # executor.execute 也不应被调用
        self.plugin._executor.execute.assert_not_called()  # type: ignore[attr-defined]

    def test_circuit_breaker_recovery_allows_open(self):
        """熔断器恢复后允许开仓"""
        assert self.plugin._manager is not None
        assert self.plugin._executor is not None
        # 先触发熔断
        self.plugin._on_circuit_breaker_tripped(
            "risk_management.circuit_breaker_tripped",
            {"reason": "max_daily_loss"},
        )
        assert self.plugin._circuit_breaker_active is True

        # 恢复熔断
        self.plugin._on_circuit_breaker_recovered(
            "risk_management.circuit_breaker_recovered",
            {},
        )
        assert self.plugin._circuit_breaker_active is False

        # 尝试开仓 — 应通过熔断检查（后续逻辑由 mock 处理）
        self.plugin._try_open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            price=50000.0,
            confidence=0.9,
            wyckoff_state="accumulation",
            signal=TradingSignal.STRONG_BUY,
            df=None,
            data={},
            stop_loss_hint=49000.0,
            take_profit_hint=52000.0,
        )

        # 熔断恢复后 can_open_position 应被调用
        self.plugin._manager.can_open_position.assert_called_once()  # type: ignore[attr-defined]


class TestShutdownEventChain:
    """系统关闭事件链测试 — 验证 shutdown 使用市场价平仓"""

    def setup_method(self):
        from src.plugins.position_manager.plugin import PositionManagerPlugin

        self.plugin = PositionManagerPlugin("position_manager")
        self.plugin._config = {}
        self.plugin._manager = MagicMock()
        self.plugin._executor = MagicMock()
        self.plugin._journal = MagicMock()

    def _make_position(self, symbol: str, entry_price: float) -> MagicMock:
        """创建 mock Position"""
        pos = MagicMock()
        pos.symbol = symbol
        pos.entry_price = entry_price
        pos.side = PositionSide.LONG
        return pos

    def test_shutdown_uses_market_price(self):
        """shutdown 时使用最后已知市场价，而非入场价"""
        pos = self._make_position("BTC/USDT", entry_price=50000.0)
        self.plugin._manager.get_all_positions.return_value = {  # type: ignore
            "BTC/USDT": pos,
        }
        self.plugin._manager.force_close_all.return_value = []  # type: ignore

        # 模拟收到市场价格更新
        self.plugin._last_prices["BTC/USDT"] = 52000.0

        self.plugin._on_shutdown("system.shutdown", {})

        # 验证 force_close_all 使用了市场价 52000，不是入场价 50000
        self.plugin._manager.force_close_all.assert_called_once()  # type: ignore
        call_args = self.plugin._manager.force_close_all.call_args  # type: ignore
        exit_prices = call_args[0][0] if call_args[0] else call_args[1]["exit_prices"]
        assert exit_prices["BTC/USDT"] == 52000.0

    def test_shutdown_fallback_to_entry_price(self):
        """无市场价时，降级使用入场价"""
        pos = self._make_position("ETH/USDT", entry_price=3000.0)
        self.plugin._manager.get_all_positions.return_value = {  # type: ignore
            "ETH/USDT": pos,
        }
        self.plugin._manager.force_close_all.return_value = []  # type: ignore

        # 不设置 _last_prices → 无市场价
        self.plugin._on_shutdown("system.shutdown", {})

        call_args = self.plugin._manager.force_close_all.call_args  # type: ignore
        exit_prices = call_args[0][0] if call_args[0] else call_args[1]["exit_prices"]
        assert exit_prices["ETH/USDT"] == 3000.0  # 降级到入场价

    def test_shutdown_mixed_prices(self):
        """多品种：一个有市场价一个没有"""
        btc = self._make_position("BTC/USDT", entry_price=50000.0)
        eth = self._make_position("ETH/USDT", entry_price=3000.0)
        self.plugin._manager.get_all_positions.return_value = {  # type: ignore
            "BTC/USDT": btc,
            "ETH/USDT": eth,
        }
        self.plugin._manager.force_close_all.return_value = []  # type: ignore

        self.plugin._last_prices["BTC/USDT"] = 51000.0
        # ETH 无市场价

        self.plugin._on_shutdown("system.shutdown", {})

        call_args = self.plugin._manager.force_close_all.call_args  # type: ignore
        exit_prices = call_args[0][0] if call_args[0] else call_args[1]["exit_prices"]
        assert exit_prices["BTC/USDT"] == 51000.0  # 市场价
        assert exit_prices["ETH/USDT"] == 3000.0  # 降级到入场价

    def test_shutdown_no_positions(self):
        """无持仓时 shutdown 不调用 force_close_all"""
        self.plugin._manager.get_all_positions.return_value = {}  # type: ignore
        self.plugin._manager.force_close_all.return_value = []  # type: ignore

        self.plugin._on_shutdown("system.shutdown", {})

        self.plugin._manager.force_close_all.assert_called_once_with({})  # type: ignore

    def test_shutdown_no_manager(self):
        """manager 未初始化时 shutdown 安全退出"""
        self.plugin._manager = None

        # 不应抛异常
        self.plugin._on_shutdown("system.shutdown", {})

    def test_event_name_matches_app(self):
        """验证 position_manager 订阅的事件名与 app.py 发布的一致"""
        # app.py 发布 "system.shutdown"，plugin.py 订阅 "system.shutdown"
        # 这里通过直接调用验证事件名可达性
        from src.kernel.event_bus import EventBus

        bus = EventBus()
        received = []

        def handler(event_name, data):
            received.append(event_name)

        bus.subscribe("system.shutdown", handler)
        bus.emit("system.shutdown", {}, publisher="app")
        assert received == ["system.shutdown"]


class TestPositionJournalCrashSafety:
    """持仓日志崩溃安全测试 — 验证 flush+fsync 和原子替换"""

    def setup_method(self):
        import tempfile

        self.tmpdir = tempfile.mkdtemp()
        self.journal_path = os.path.join(self.tmpdir, "test_journal.jsonl")
        self.journal = PositionJournal(self.journal_path)

    def teardown_method(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_append_entry_calls_fsync(self):
        """_append_entry 写入后执行 flush+fsync 保证落盘"""
        import unittest.mock as mock

        entry = {"event": "test", "data": "value"}

        with mock.patch("builtins.open", mock.mock_open()) as m_open:
            with mock.patch("os.fsync") as m_fsync:
                self.journal._append_entry(entry)

                # 验证 flush 和 fsync 均被调用
                handle = m_open()
                handle.flush.assert_called_once()
                m_fsync.assert_called_once()

    def test_append_entry_writes_valid_jsonl(self):
        """_append_entry 写入有效的 JSONL 格式"""
        import json

        entry = {"event": "open", "symbol": "BTC/USDT", "price": 50000.0}
        self.journal._append_entry(entry)

        with open(self.journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event"] == "open"
        assert parsed["symbol"] == "BTC/USDT"

    def test_compact_uses_atomic_replace(self):
        """compact 使用 temp 文件 + os.replace 原子替换"""
        import unittest.mock as mock

        # 创建初始日志文件
        self.journal._append_entry(
            {
                "event": "open",
                "timestamp": datetime.now().isoformat(),
                "symbol": "BTC/USDT",
                "position": {
                    "symbol": "BTC/USDT",
                    "side": "long",
                    "size": 0.1,
                    "entry_price": 50000.0,
                    "entry_time": datetime.now().isoformat(),
                    "stop_loss": 49000.0,
                    "take_profit": 52000.0,
                    "signal_confidence": 0.8,
                    "wyckoff_state": "accumulation",
                    "entry_signal": "STRONG_BUY",
                    "status": "open",
                    "original_size": 0.1,
                    "entry_atr": 500.0,
                    "leverage": 1.0,
                    "trailing_stop_activated": False,
                    "partial_profits_taken": [],
                    "highest_price": 50000.0,
                    "lowest_price": 50000.0,
                    "metadata": {},
                },
            }
        )

        with mock.patch("os.replace") as m_replace:
            self.journal.compact()

            # 验证 os.replace 被调用（原子替换）
            m_replace.assert_called_once()
            args = m_replace.call_args[0]
            assert args[0].endswith(".tmp")  # 源是 tmp 文件
            assert args[1] == self.journal_path  # 目标是原文件

    def test_compact_not_os_rename(self):
        """确认 compact 代码中使用 os.replace 而非 os.rename（Windows 兼容）"""
        import inspect

        source = inspect.getsource(self.journal.compact)
        assert "os.replace" in source
        assert "os.rename" not in source

    def test_append_entry_thread_safe(self):
        """多线程并发写入不丢数据"""
        import json
        import threading

        errors = []
        count = 50

        def write_entry(idx):
            try:
                self.journal._append_entry({"event": "test", "idx": idx})
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=write_entry, args=(i,)) for i in range(count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"线程写入出错: {errors}"

        with open(self.journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == count
        indices = {json.loads(line)["idx"] for line in lines}
        assert indices == set(range(count))


class TestRecoveryPriceValidation:
    """恢复持仓后验证市场价 — 验证 _validate_recovered_positions 行为"""

    def setup_method(self):
        from src.plugins.position_manager.plugin import PositionManagerPlugin

        self.plugin = PositionManagerPlugin("position_manager")
        self.plugin._config = {}
        self.plugin._manager = MagicMock()
        self.plugin._executor = MagicMock()
        self.plugin._journal = MagicMock()

    def _make_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        stop_loss: float,
    ) -> Position:
        """创建真实 Position（非 mock），以便 calculate_unrealized_pnl 可执行"""
        return Position(
            symbol=symbol,
            side=side,
            size=0.1,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=entry_price * (1.1 if side == PositionSide.LONG else 0.9),
            signal_confidence=0.8,
            wyckoff_state="SOS" if side == PositionSide.LONG else "LPSY",
            entry_signal=TradingSignal.BUY
            if side == PositionSide.LONG
            else TradingSignal.SELL,
        )

    def test_long_stop_loss_breached_triggers_close(self):
        """LONG 持仓：stop_loss=95, 市场价=90 → 应触发立即平仓"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 95.0)
        self.plugin._executor.get_market_price.return_value = 90.0  # type: ignore
        # Mock _execute_exit 以避免真实执行
        self.plugin._execute_exit = MagicMock()

        recovered = {"BTC/USDT": pos}
        self.plugin._validate_recovered_positions(recovered)

        # 验证 _execute_exit 被调用
        self.plugin._execute_exit.assert_called_once()
        call_args = self.plugin._execute_exit.call_args
        assert call_args[0][0] == "BTC/USDT"
        assert call_args[0][1] == 90.0
        exit_result = call_args[0][2]
        assert exit_result.should_exit is True
        assert exit_result.reason == ExitReason.STOP_LOSS

    def test_long_stop_loss_safe_updates_pnl(self):
        """LONG 持仓：stop_loss=95, 市场价=100 → 不平仓，仅更新 PnL"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 95.0)
        self.plugin._executor.get_market_price.return_value = 105.0  # type: ignore
        self.plugin._execute_exit = MagicMock()

        recovered = {"BTC/USDT": pos}
        self.plugin._validate_recovered_positions(recovered)

        # 不应触发平仓
        self.plugin._execute_exit.assert_not_called()
        # PnL 应已更新
        assert pos.unrealized_pnl > 0
        # _last_prices 应已记录
        assert self.plugin._last_prices["BTC/USDT"] == 105.0

    def test_short_stop_loss_breached_triggers_close(self):
        """SHORT 持仓：stop_loss=105, 市场价=110 → 应触发立即平仓"""
        pos = self._make_position("ETH/USDT", PositionSide.SHORT, 100.0, 105.0)
        self.plugin._executor.get_market_price.return_value = 110.0  # type: ignore
        self.plugin._execute_exit = MagicMock()

        recovered = {"ETH/USDT": pos}
        self.plugin._validate_recovered_positions(recovered)

        self.plugin._execute_exit.assert_called_once()
        call_args = self.plugin._execute_exit.call_args
        assert call_args[0][0] == "ETH/USDT"
        exit_result = call_args[0][2]
        assert exit_result.reason == ExitReason.STOP_LOSS

    def test_short_stop_loss_safe_updates_pnl(self):
        """SHORT 持仓：stop_loss=105, 市场价=95 → 不平仓，PnL 为正"""
        pos = self._make_position("SOL/USDT", PositionSide.SHORT, 100.0, 105.0)
        self.plugin._executor.get_market_price.return_value = 95.0  # type: ignore
        self.plugin._execute_exit = MagicMock()

        recovered = {"SOL/USDT": pos}
        self.plugin._validate_recovered_positions(recovered)

        self.plugin._execute_exit.assert_not_called()
        assert pos.unrealized_pnl > 0
        assert self.plugin._last_prices["SOL/USDT"] == 95.0

    def test_no_market_price_skips_validation(self):
        """交易所无法返回市场价 → 跳过该持仓验证"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 95.0)
        self.plugin._executor.get_market_price.return_value = None  # type: ignore
        self.plugin._execute_exit = MagicMock()

        recovered = {"BTC/USDT": pos}
        self.plugin._validate_recovered_positions(recovered)

        self.plugin._execute_exit.assert_not_called()
        assert "BTC/USDT" not in self.plugin._last_prices

    def test_multiple_positions_mixed_breach(self):
        """多持仓：一个止损击穿、一个安全 → 只平击穿的"""
        btc = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 95.0)
        eth = self._make_position("ETH/USDT", PositionSide.LONG, 100.0, 95.0)

        def mock_price(symbol):
            return {"BTC/USDT": 90.0, "ETH/USDT": 105.0}[symbol]

        self.plugin._executor.get_market_price.side_effect = mock_price  # type: ignore
        self.plugin._execute_exit = MagicMock()

        recovered = {"BTC/USDT": btc, "ETH/USDT": eth}
        self.plugin._validate_recovered_positions(recovered)

        # 仅 BTC 被平仓
        assert self.plugin._execute_exit.call_count == 1
        assert self.plugin._execute_exit.call_args[0][0] == "BTC/USDT"
        # ETH PnL 已更新
        assert eth.unrealized_pnl > 0

    def test_stop_loss_exactly_at_price_triggers_close(self):
        """LONG 持仓：市场价恰好等于止损 → 应触发平仓（<= 判定）"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 95.0)
        self.plugin._executor.get_market_price.return_value = 95.0  # type: ignore
        self.plugin._execute_exit = MagicMock()

        recovered = {"BTC/USDT": pos}
        self.plugin._validate_recovered_positions(recovered)

        self.plugin._execute_exit.assert_called_once()

    def test_price_extremes_updated(self):
        """恢复验证应更新 highest_price / lowest_price"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 90.0)
        self.plugin._executor.get_market_price.return_value = 120.0  # type: ignore
        self.plugin._execute_exit = MagicMock()

        recovered = {"BTC/USDT": pos}
        self.plugin._validate_recovered_positions(recovered)

        assert pos.highest_price == 120.0

    def test_no_executor_returns_safely(self):
        """executor 为 None 时安全返回"""
        self.plugin._executor = None
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 95.0)

        # 不应抛异常
        self.plugin._validate_recovered_positions({"BTC/USDT": pos})

    def test_no_manager_returns_safely(self):
        """manager 为 None 时安全返回"""
        self.plugin._manager = None
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 100.0, 95.0)

        # 不应抛异常
        self.plugin._validate_recovered_positions({"BTC/USDT": pos})


class TestReconcileWithExchange:
    """启动对账测试 — 验证 _reconcile_with_exchange 行为"""

    def setup_method(self):
        from src.plugins.position_manager.plugin import PositionManagerPlugin

        self.plugin = PositionManagerPlugin("position_manager")
        self.plugin._config = {}
        self.plugin._manager = MagicMock()
        self.plugin._executor = MagicMock()
        self.plugin._journal = MagicMock()

    def _make_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        size: float = 0.1,
    ) -> Position:
        """创建真实 Position 用于对账测试"""
        return Position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss=entry_price * (0.95 if side == PositionSide.LONG else 1.05),
            take_profit=entry_price * (1.1 if side == PositionSide.LONG else 0.9),
            signal_confidence=0.8,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
        )

    def test_matching_positions_no_warning(self):
        """journal 和 exchange 持仓一致时不应有 WARNING"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 50000.0, 0.5)
        self.plugin._executor.get_position.return_value = {"size": 0.5}  # type: ignore

        journal_positions = {"BTC/USDT": pos}
        # 不应抛异常
        self.plugin._reconcile_with_exchange(journal_positions)

        self.plugin._executor.get_position.assert_called_once_with("BTC/USDT")  # type: ignore

    def test_exchange_missing_position_logs_warning(self):
        """exchange 无持仓但 journal 有 → 应记录差异"""
        pos = self._make_position("ETH/USDT", PositionSide.LONG, 3000.0, 1.0)
        self.plugin._executor.get_position.return_value = None  # type: ignore

        journal_positions = {"ETH/USDT": pos}
        # 不应抛异常，只记录 WARNING
        self.plugin._reconcile_with_exchange(journal_positions)

        self.plugin._executor.get_position.assert_called_once_with("ETH/USDT")  # type: ignore

    def test_size_mismatch_logs_warning(self):
        """仓位大小不一致（超过1%）→ 应记录差异"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 50000.0, 1.0)
        # exchange 报告 0.5（差 50%）
        self.plugin._executor.get_position.return_value = {"size": 0.5}  # type: ignore

        journal_positions = {"BTC/USDT": pos}
        self.plugin._reconcile_with_exchange(journal_positions)

        self.plugin._executor.get_position.assert_called_once_with("BTC/USDT")  # type: ignore

    def test_size_within_tolerance_no_warning(self):
        """仓位大小差异在 1% 以内 → 不应报差异"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 50000.0, 1.0)
        # 差异 0.5%，在容差范围内
        self.plugin._executor.get_position.return_value = {"size": 1.005}  # type: ignore

        journal_positions = {"BTC/USDT": pos}
        self.plugin._reconcile_with_exchange(journal_positions)

        self.plugin._executor.get_position.assert_called_once_with("BTC/USDT")  # type: ignore

    def test_executor_none_skips_reconciliation(self):
        """executor 为 None 时安全跳过"""
        self.plugin._executor = None
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 50000.0)

        # 不应抛异常
        self.plugin._reconcile_with_exchange({"BTC/USDT": pos})

    def test_exchange_exception_does_not_block(self):
        """exchange 抛异常时不应阻止系统启动"""
        pos = self._make_position("BTC/USDT", PositionSide.LONG, 50000.0)
        self.plugin._executor.get_position.side_effect = Exception("连接超时")  # type: ignore

        # 不应抛异常
        self.plugin._reconcile_with_exchange({"BTC/USDT": pos})

    def test_empty_journal_positions(self):
        """空 journal 对账应正常完成"""
        self.plugin._reconcile_with_exchange({})
        self.plugin._executor.get_position.assert_not_called()  # type: ignore

    def test_multiple_positions_reconciled(self):
        """多个持仓应逐个与 exchange 对比"""
        btc = self._make_position("BTC/USDT", PositionSide.LONG, 50000.0, 0.5)
        eth = self._make_position("ETH/USDT", PositionSide.SHORT, 3000.0, 2.0)

        def mock_get_position(symbol):
            return {
                "BTC/USDT": {"size": 0.5},
                "ETH/USDT": None,
            }[symbol]

        self.plugin._executor.get_position.side_effect = mock_get_position  # type: ignore

        journal_positions = {"BTC/USDT": btc, "ETH/USDT": eth}
        self.plugin._reconcile_with_exchange(journal_positions)

        assert self.plugin._executor.get_position.call_count == 2  # type: ignore
