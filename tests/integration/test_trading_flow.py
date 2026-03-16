"""集成测试 - 完整交易流程测试

测试从信号生成到平仓的完整链路：
1. 信号 → 开仓
2. 止损触发
3. 止盈触发
4. 信号反转出场
5. 完整交易周期
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.kernel.types import TradingSignal
from src.plugins.position_manager import (
    PositionManager,
    StopLossExecutor,
    SignalExitLogic,
    Position,
    PositionSide,
    ExitReason,
)
from src.plugins.exchange_connector.exchange_executor import ExchangeExecutor


class TestSignalToOpenPosition:
    """测试信号 → 开仓流程"""

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
                "trailing_activation_pct": 0.015,
                "trailing_distance_pct": 0.01,
            },
            "signal_exit": {
                "signal_reversal_enabled": True,
                "min_reversal_confidence": 0.6,
            },
        }
        self.manager = PositionManager(self.config)
        
        self.df = pd.DataFrame({
            "open": [100, 101, 102, 103, 104] * 20,
            "high": [105, 106, 107, 108, 109] * 20,
            "low": [95, 96, 97, 98, 99] * 20,
            "close": [100, 101, 102, 103, 104] * 20,
            "volume": [1000] * 100,
        })

    def test_buy_signal_opens_long_position(self):
        """买入信号应该开多仓"""
        assert self.manager.can_open_position("BTC/USDT")
        
        position = self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=50000.0,
            signal_confidence=0.75,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )
        
        assert position is not None
        assert position.symbol == "BTC/USDT"
        assert position.side == PositionSide.LONG
        assert position.entry_price == 50000.0
        assert position.signal_confidence == 0.75
        assert position.stop_loss < position.entry_price
        assert position.take_profit > position.entry_price

    def test_sell_signal_opens_short_position(self):
        """卖出信号应该开空仓"""
        position = self.manager.open_position(
            symbol="ETH/USDT",
            side=PositionSide.SHORT,
            size=0.5,
            entry_price=3000.0,
            signal_confidence=0.8,
            wyckoff_state="LPSY",
            entry_signal=TradingSignal.SELL,
            df=self.df,
        )
        
        assert position is not None
        assert position.side == PositionSide.SHORT
        assert position.stop_loss > position.entry_price
        assert position.take_profit < position.entry_price

    def test_max_positions_limit(self):
        """测试最大持仓限制"""
        for i, symbol in enumerate(["BTC/USDT", "ETH/USDT", "SOL/USDT"]):
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
        
        assert not self.manager.can_open_position("DOGE/USDT")
        assert self.manager.get_open_position_count() == 3

    def test_cannot_open_duplicate_position(self):
        """不能对同一品种重复开仓"""
        self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=50000.0,
            signal_confidence=0.7,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )
        
        assert not self.manager.can_open_position("BTC/USDT")


class TestStopLossTrigger:
    """测试止损触发流程"""

    def setup_method(self):
        self.config = {
            "stop_loss": {
                "method": "fixed",
                "fixed_percentage": 0.02,
                "trailing_enabled": False,
            },
        }
        self.manager = PositionManager(self.config)
        self.executor = StopLossExecutor(self.config["stop_loss"])

    def test_long_stop_loss_triggered(self):
        """多头止损触发"""
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

    def test_short_stop_loss_triggered(self):
        """空头止损触发"""
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
        
        result = self.executor.check_exit_conditions(position, 103.0)
        
        assert result.should_exit
        assert result.reason == ExitReason.STOP_LOSS

    def test_stop_loss_not_triggered_when_profit(self):
        """盈利时不应触发止损"""
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
        
        result = self.executor.check_exit_conditions(position, 102.0)
        
        assert not result.should_exit


class TestTakeProfitTrigger:
    """测试止盈触发流程"""

    def setup_method(self):
        self.config = {
            "stop_loss": {
                "method": "fixed",
                "fixed_percentage": 0.02,
            },
        }
        self.executor = StopLossExecutor(self.config["stop_loss"])

    def test_long_take_profit_triggered(self):
        """多头止盈触发"""
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

    def test_short_take_profit_triggered(self):
        """空头止盈触发"""
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
        
        result = self.executor.check_exit_conditions(position, 95.0)
        
        assert result.should_exit
        assert result.reason == ExitReason.TAKE_PROFIT


class TestSignalReversalExit:
    """测试信号反转出场流程"""

    def setup_method(self):
        self.config = {
            "signal_reversal_enabled": True,
            "min_reversal_confidence": 0.6,
            "wyckoff_exit_enabled": True,
        }
        self.logic = SignalExitLogic(self.config)

    def test_long_position_exit_on_sell_signal(self):
        """多头持仓遇到卖出信号应该出场"""
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
            new_wyckoff_state="UNKNOWN",
            confidence=0.7,
        )
        
        assert result.should_exit
        assert result.reason == ExitReason.SIGNAL_REVERSAL

    def test_short_position_exit_on_buy_signal(self):
        """空头持仓遇到买入信号应该出场"""
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
            new_wyckoff_state="UNKNOWN",
            confidence=0.7,
        )
        
        assert result.should_exit

    def test_no_exit_on_low_confidence_signal(self):
        """低置信度信号不应触发出场"""
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
            new_wyckoff_state="UNKNOWN",
            confidence=0.4,
        )
        
        assert not result.should_exit

    def test_exit_on_wyckoff_distribution(self):
        """威科夫派发状态应该触发多头出场"""
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


class TestFullTradingCycle:
    """测试完整交易周期"""

    def setup_method(self):
        self.config = {
            "max_positions": 3,
            "max_position_size": 0.1,
            "min_position_size": 0.01,
            "risk_per_trade": 0.02,
            "stop_loss": {
                "method": "fixed",
                "fixed_percentage": 0.02,
                "trailing_enabled": True,
                "trailing_activation_pct": 0.015,
                "trailing_distance_pct": 0.01,
            },
            "signal_exit": {
                "signal_reversal_enabled": True,
                "min_reversal_confidence": 0.6,
            },
        }
        self.manager = PositionManager(self.config)
        
        self.df = pd.DataFrame({
            "open": [100] * 20,
            "high": [105] * 20,
            "low": [95] * 20,
            "close": [100] * 20,
            "volume": [1000] * 20,
        })

    def test_full_cycle_with_stop_loss(self):
        """完整周期：开仓 → 止损出场"""
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
        assert self.manager.get_position("BTC/USDT") is not None
        
        exit_result = self.manager.update_position(
            symbol="BTC/USDT",
            current_price=position.stop_loss - 1,
        )
        
        assert exit_result.should_exit
        assert exit_result.reason == ExitReason.STOP_LOSS
        
        trade_result = self.manager.close_position(
            symbol="BTC/USDT",
            exit_price=position.stop_loss,
            reason=ExitReason.STOP_LOSS,
        )
        
        assert trade_result is not None
        assert trade_result.pnl < 0
        assert self.manager.get_position("BTC/USDT") is None

    def test_full_cycle_with_take_profit(self):
        """完整周期：开仓 → 止盈出场"""
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
        
        exit_result = self.manager.update_position(
            symbol="BTC/USDT",
            current_price=position.take_profit + 1,
        )
        
        assert exit_result.should_exit
        assert exit_result.reason == ExitReason.TAKE_PROFIT
        
        trade_result = self.manager.close_position(
            symbol="BTC/USDT",
            exit_price=position.take_profit,
            reason=ExitReason.TAKE_PROFIT,
        )
        
        assert trade_result.pnl > 0
        assert trade_result.is_profitable

    def test_full_cycle_with_signal_reversal(self):
        """完整周期：开仓 → 信号反转出场"""
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
        
        exit_result = self.manager.update_position(
            symbol="BTC/USDT",
            current_price=101.0,
            new_signal=TradingSignal.SELL,
            new_wyckoff_state="LPSY",
            signal_confidence=0.75,
        )
        
        assert exit_result.should_exit
        assert exit_result.reason == ExitReason.SIGNAL_REVERSAL

    def test_multiple_trades_statistics(self):
        """多次交易后的统计信息"""
        for i in range(3):
            position = self.manager.open_position(
                symbol=f"COIN{i}/USDT",
                side=PositionSide.LONG,
                size=0.1,
                entry_price=100.0,
                signal_confidence=0.7,
                wyckoff_state="SOS",
                entry_signal=TradingSignal.BUY,
                df=self.df,
            )
            
            exit_price = 102.0 if i % 2 == 0 else 98.0
            reason = ExitReason.TAKE_PROFIT if i % 2 == 0 else ExitReason.STOP_LOSS
            
            self.manager.close_position(
                symbol=f"COIN{i}/USDT",
                exit_price=exit_price,
                reason=reason,
            )
        
        stats = self.manager.get_statistics()
        
        assert stats["total_trades"] == 3
        assert stats["winning_trades"] == 2
        assert stats["win_rate"] == 2/3


class TestExchangeExecutor:
    """测试交易所执行器"""

    def setup_method(self):
        self.config = {
            "paper_trading": True,
            "initial_balance": 10000.0,
            "leverage": 5,
        }
        self.executor = ExchangeExecutor(self.config)

    def test_paper_trading_mode(self):
        """模拟交易模式"""
        assert self.executor.paper_trading

    def test_simulate_order(self):
        """模拟下单"""
        order = self.executor.place_order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            size=0.1,
            price=50000.0,
        )
        
        assert order["id"].startswith("paper_")
        assert order["symbol"] == "BTC/USDT"
        assert order["side"] == "buy"
        assert order["status"] == "closed"

    def test_get_paper_position(self):
        """获取模拟持仓"""
        self.executor.place_order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            size=0.1,
            price=50000.0,
        )
        
        position = self.executor.get_position("BTC/USDT")
        
        assert position is not None
        assert position["side"] == PositionSide.LONG

    def test_get_balance(self):
        """获取余额"""
        balance = self.executor.get_balance()
        
        assert balance["total"] == 10000.0

    def test_close_position(self):
        """平仓"""
        self.executor.place_order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            size=0.1,
            price=50000.0,
        )
        
        close_order = self.executor.close_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
        )
        
        assert close_order["side"] == "sell"
        assert self.executor.get_position("BTC/USDT") is None


class TestPositionManagerWithExecutor:
    """测试 PositionManager 与 ExchangeExecutor 集成"""

    def setup_method(self):
        self.config = {
            "max_positions": 3,
            "risk_per_trade": 0.02,
            "stop_loss": {
                "method": "fixed",
                "fixed_percentage": 0.02,
            },
            "signal_exit": {
                "signal_reversal_enabled": True,
                "min_reversal_confidence": 0.6,
            },
        }
        self.manager = PositionManager(self.config)
        self.executor = ExchangeExecutor({"paper_trading": True})
        
        self.df = pd.DataFrame({
            "open": [100] * 20,
            "high": [105] * 20,
            "low": [95] * 20,
            "close": [100] * 20,
            "volume": [1000] * 20,
        })

    def test_open_position_via_executor(self):
        """通过执行器开仓"""
        position = self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=50000.0,
            signal_confidence=0.75,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )
        
        order = self.executor.place_order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            size=position.size,
            price=position.entry_price,
        )
        
        assert order["status"] == "closed"
        
        exec_position = self.executor.get_position("BTC/USDT")
        assert exec_position is not None

    def test_close_position_via_executor(self):
        """通过执行器平仓"""
        position = self.manager.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=50000.0,
            signal_confidence=0.75,
            wyckoff_state="SOS",
            entry_signal=TradingSignal.BUY,
            df=self.df,
        )
        
        self.executor.place_order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            size=position.size,
            price=position.entry_price,
        )
        
        exit_price = 51000.0
        trade_result = self.manager.close_position(
            symbol="BTC/USDT",
            exit_price=exit_price,
            reason=ExitReason.MANUAL,
        )
        
        self.executor.close_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=position.size,
        )
        
        assert trade_result.pnl > 0
        assert self.executor.get_position("BTC/USDT") is None
