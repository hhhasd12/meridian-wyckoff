"""仓位管理插件测试"""

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
        
        self.df = pd.DataFrame({
            "open": [100, 101, 102, 103, 104],
            "high": [105, 106, 107, 108, 109],
            "low": [95, 96, 97, 98, 99],
            "close": [100, 101, 102, 103, 104],
            "volume": [1000, 1000, 1000, 1000, 1000],
        })

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
        assert position.trailing_stop_activated or result.new_stop_loss is not None or result.partial_close_ratio is not None


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
        
        self.df = pd.DataFrame({
            "open": [100, 101, 102, 103, 104],
            "high": [105, 106, 107, 108, 109],
            "low": [95, 96, 97, 98, 99],
            "close": [100, 101, 102, 103, 104],
            "volume": [1000, 1000, 1000, 1000, 1000],
        })

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
        
        results = self.manager.force_close_all({
            "BTC/USDT": 101.0,
            "ETH/USDT": 99.0,
        })
        
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
