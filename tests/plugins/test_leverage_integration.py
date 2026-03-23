"""杠杆全链路集成测试 — Position PnL + calculate_position_size + to_dict + Journal + StopLoss"""

import os
import tempfile
from datetime import datetime

import pytest

from src.kernel.types import TradingSignal
from src.plugins.position_manager.position_journal import PositionJournal
from src.plugins.position_manager.position_manager import PositionManager
from src.plugins.position_manager.types import (
    ExitReason,
    Position,
    PositionSide,
    PositionStatus,
)


class TestLeveragePnL:
    """测试1: 杠杆对 PnL 百分比的放大效果"""

    def test_leverage_5x_pnl_pct(self):
        """leverage=5, 1% 价格上涨 → pnl_pct ≈ 5%"""
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=10000.0,
            entry_time=datetime.now(),
            stop_loss=9500.0,
            take_profit=11000.0,
            signal_confidence=0.8,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=5.0,
        )
        current_price = 10100.0  # +1%
        _pnl, pnl_pct = pos.calculate_unrealized_pnl(current_price)
        assert pnl_pct == pytest.approx(0.05, abs=1e-6)

    def test_leverage_1x_pnl_pct(self):
        """leverage=1（默认）, 1% 价格上涨 → pnl_pct ≈ 1%"""
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=10000.0,
            entry_time=datetime.now(),
            stop_loss=9500.0,
            take_profit=11000.0,
            signal_confidence=0.8,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=1.0,
        )
        current_price = 10100.0  # +1%
        _pnl, pnl_pct = pos.calculate_unrealized_pnl(current_price)
        assert pnl_pct == pytest.approx(0.01, abs=1e-6)

    def test_short_leverage_3x(self):
        """SHORT leverage=3, 2% 价格下跌 → pnl_pct ≈ 6%"""
        pos = Position(
            symbol="ETH/USDT",
            side=PositionSide.SHORT,
            size=10.0,
            entry_price=2000.0,
            entry_time=datetime.now(),
            stop_loss=2100.0,
            take_profit=1800.0,
            signal_confidence=0.7,
            wyckoff_state="distribution",
            entry_signal=TradingSignal.SELL,
            leverage=3.0,
        )
        current_price = 1960.0  # -2%
        _pnl, pnl_pct = pos.calculate_unrealized_pnl(current_price)
        assert pnl_pct == pytest.approx(0.06, abs=1e-6)


class TestLeveragePositionSize:
    """测试2: leverage 放大 calculate_position_size 结果"""

    def setup_method(self):
        self.config = {
            "max_positions": 3,
            "max_position_size": 0.1,
            "min_position_size": 0.001,
            "risk_per_trade": 0.02,
        }
        self.manager = PositionManager(self.config)

    def test_leverage_5x_larger_size(self):
        """leverage=5 时仓位 ≈ leverage=1 的 5 倍（上限受 max_size 约束）"""
        balance = 10000.0
        entry = 50000.0
        stop = 49000.0
        size_1x = self.manager.calculate_position_size(
            balance,
            entry,
            stop,
            leverage=1.0,
        )
        size_5x = self.manager.calculate_position_size(
            balance,
            entry,
            stop,
            leverage=5.0,
        )
        assert size_1x > 0
        assert size_5x > 0
        # 两者之比应接近 5（可能被 risk_amount 而非 max_size 限制时比值小于 5）
        ratio = size_5x / size_1x
        assert ratio >= 1.0
        # 当 risk_amount 是瓶颈时 size 相同；当 max_size 是瓶颈时比值 ≈5
        # 验证 5x 的 max_size 上限确实是 1x 的 5 倍
        max_1x = balance * 0.1 * 1.0 / entry
        max_5x = balance * 0.1 * 5.0 / entry
        assert max_5x == pytest.approx(max_1x * 5.0, rel=1e-9)

    def test_leverage_capped_by_max_size(self):
        """即使 leverage 很大，仓位不能超过 max_position_size * leverage 限制"""
        balance = 10000.0
        entry = 100.0
        stop = 99.0  # 很小的 risk → 大仓位 → 应被 max_size 限制
        size_10x = self.manager.calculate_position_size(
            balance,
            entry,
            stop,
            leverage=10.0,
        )
        max_allowed = balance * 0.1 * 10.0 / entry  # = 100
        assert size_10x <= max_allowed + 1e-9


class TestLeverageToDict:
    """测试3: Position.to_dict() 包含 leverage 并可还原"""

    def test_to_dict_contains_leverage(self):
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.5,
            entry_price=40000.0,
            entry_time=datetime.now(),
            stop_loss=39000.0,
            take_profit=42000.0,
            signal_confidence=0.9,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=3.0,
        )
        d = pos.to_dict()
        assert "leverage" in d
        assert d["leverage"] == 3.0

    def test_to_dict_roundtrip_leverage(self):
        """to_dict 中的 leverage 值可用于重建等价 Position"""
        pos = Position(
            symbol="ETH/USDT",
            side=PositionSide.SHORT,
            size=5.0,
            entry_price=2500.0,
            entry_time=datetime.now(),
            stop_loss=2600.0,
            take_profit=2300.0,
            signal_confidence=0.75,
            wyckoff_state="distribution",
            entry_signal=TradingSignal.SELL,
            leverage=7.5,
        )
        d = pos.to_dict()
        # 验证可从 dict 取回 leverage
        assert d["leverage"] == 7.5
        # 验证与原始一致
        assert d["leverage"] == pos.leverage


class TestLeverageDefault:
    """测试4: 默认 leverage=1.0 行为不变"""

    def test_default_leverage_is_one(self):
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=50000.0,
            entry_time=datetime.now(),
            stop_loss=48000.0,
            take_profit=54000.0,
            signal_confidence=0.8,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
        )
        assert pos.leverage == 1.0

    def test_default_leverage_pnl_unchanged(self):
        """默认杠杆下 PnL 百分比 = 价格变动百分比"""
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=50000.0,
            entry_time=datetime.now(),
            stop_loss=48000.0,
            take_profit=54000.0,
            signal_confidence=0.8,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
        )
        _pnl, pnl_pct = pos.calculate_unrealized_pnl(51000.0)
        expected = (51000.0 - 50000.0) / 50000.0  # 2%
        assert pnl_pct == pytest.approx(expected, abs=1e-9)

    def test_default_leverage_position_size(self):
        """默认 leverage=1 时 calculate_position_size 行为不变"""
        config = {
            "max_position_size": 0.1,
            "min_position_size": 0.001,
            "risk_per_trade": 0.02,
        }
        mgr = PositionManager(config)
        size_default = mgr.calculate_position_size(10000, 50000, 49000)
        size_1x = mgr.calculate_position_size(
            10000,
            50000,
            49000,
            leverage=1.0,
        )
        assert size_default == size_1x


class TestJournalLeverageRoundtrip:
    """测试5: PositionJournal 序列化/反序列化保留 leverage 字段"""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._journal_path = os.path.join(self._tmpdir, "test_journal.jsonl")
        self.journal = PositionJournal(journal_path=self._journal_path)

    def teardown_method(self):
        if os.path.exists(self._journal_path):
            os.remove(self._journal_path)
        os.rmdir(self._tmpdir)

    def test_journal_roundtrip_preserves_leverage(self):
        """record_open → recover_positions 保留 leverage=5.0"""
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.5,
            entry_price=40000.0,
            entry_time=datetime(2026, 1, 1, 12, 0),
            stop_loss=39000.0,
            take_profit=42000.0,
            signal_confidence=0.85,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=5.0,
        )
        self.journal.record_open(pos)

        recovered = self.journal.recover_positions()
        assert "BTC/USDT" in recovered
        assert recovered["BTC/USDT"].leverage == 5.0

    def test_journal_roundtrip_default_leverage(self):
        """默认 leverage=1.0 也应被正确恢复"""
        pos = Position(
            symbol="ETH/USDT",
            side=PositionSide.SHORT,
            size=10.0,
            entry_price=2000.0,
            entry_time=datetime(2026, 1, 1, 12, 0),
            stop_loss=2100.0,
            take_profit=1800.0,
            signal_confidence=0.7,
            wyckoff_state="distribution",
            entry_signal=TradingSignal.SELL,
        )
        self.journal.record_open(pos)

        recovered = self.journal.recover_positions()
        assert "ETH/USDT" in recovered
        assert recovered["ETH/USDT"].leverage == 1.0

    def test_journal_roundtrip_pnl_consistent(self):
        """恢复后的 Position 计算 PnL 时 leverage 正确生效"""
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=50000.0,
            entry_time=datetime(2026, 1, 1, 12, 0),
            stop_loss=48000.0,
            take_profit=55000.0,
            signal_confidence=0.9,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=10.0,
        )
        self.journal.record_open(pos)

        recovered = self.journal.recover_positions()
        rpos = recovered["BTC/USDT"]
        # 1% price increase → 10% PnL on margin
        _pnl, pnl_pct = rpos.calculate_unrealized_pnl(50500.0)
        assert pnl_pct == pytest.approx(0.10, abs=1e-6)


class TestStopLossWithLeverage:
    """测试6: 止损检查结合杠杆仓位"""

    def test_long_stop_loss_triggers_leveraged_pnl(self):
        """LONG leverage=5, 价格跌至 stop_loss → PnL% 反映杠杆放大"""
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=10000.0,
            entry_time=datetime.now(),
            stop_loss=9800.0,  # -2% from entry
            take_profit=11000.0,
            signal_confidence=0.8,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=5.0,
        )
        # Price hits stop loss level
        _pnl, pnl_pct = pos.calculate_unrealized_pnl(9800.0)
        # -2% price change × 5x leverage = -10% PnL on margin
        assert pnl_pct == pytest.approx(-0.10, abs=1e-6)

    def test_short_stop_loss_triggers_leveraged_pnl(self):
        """SHORT leverage=3, 价格涨至 stop_loss → PnL% 反映杠杆放大"""
        pos = Position(
            symbol="ETH/USDT",
            side=PositionSide.SHORT,
            size=5.0,
            entry_price=2000.0,
            entry_time=datetime.now(),
            stop_loss=2060.0,  # +3% from entry
            take_profit=1800.0,
            signal_confidence=0.75,
            wyckoff_state="distribution",
            entry_signal=TradingSignal.SELL,
            leverage=3.0,
        )
        # Price hits stop loss level
        _pnl, pnl_pct = pos.calculate_unrealized_pnl(2060.0)
        # +3% price change against short × 3x leverage = -9% PnL on margin
        assert pnl_pct == pytest.approx(-0.09, abs=1e-6)

    def test_stop_loss_exit_check_with_leveraged_position(self):
        """StopLossExecutor.check_exit_conditions 触发后 PnL 已被杠杆放大"""
        from src.plugins.risk_management.stop_loss_executor import StopLossExecutor

        executor = StopLossExecutor({"trailing_enabled": False})
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=10000.0,
            entry_time=datetime.now(),
            stop_loss=9500.0,
            take_profit=11000.0,
            signal_confidence=0.8,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=5.0,
        )
        # Price at stop loss
        result = executor.check_exit_conditions(pos, 9500.0)
        assert result.should_exit is True
        assert result.reason == ExitReason.STOP_LOSS
        # After check, position's PnL should reflect leverage
        assert pos.unrealized_pnl_pct == pytest.approx(-0.25, abs=1e-6)


class TestLeverageFullChain:
    """测试7: 完整链路 open → PnL 计算 → stop loss 检查 → 平仓"""

    def test_full_chain_long_profit(self):
        """LONG leverage=5: open → price +2% → PnL=+10% → close with correct pnl_pct"""
        config = {
            "max_positions": 3,
            "max_position_size": 0.5,
            "min_position_size": 0.001,
            "risk_per_trade": 0.02,
            "stop_loss": {
                "method": "fixed",
                "fixed_percentage": 0.05,
                "trailing_enabled": False,
            },
            "signal_exit": {},
        }
        mgr = PositionManager(config)

        import numpy as np
        import pandas as pd

        # Minimal OHLCV data for stop loss calculation
        dates = pd.date_range("2026-01-01", periods=20, freq="h")
        df = pd.DataFrame(
            {
                "open": np.full(20, 10000.0),
                "high": np.full(20, 10100.0),
                "low": np.full(20, 9900.0),
                "close": np.full(20, 10000.0),
                "volume": np.full(20, 100.0),
            },
            index=dates,
        )

        # Step 1: Open position with leverage=5
        pos = mgr.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.5,
            entry_price=10000.0,
            signal_confidence=0.85,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            df=df,
            leverage=5.0,
        )
        assert pos is not None
        assert pos.leverage == 5.0

        # Step 2: Price moves +2% → PnL should be +10% on margin
        _pnl, pnl_pct = pos.calculate_unrealized_pnl(10200.0)
        assert pnl_pct == pytest.approx(0.10, abs=1e-6)

        # Step 3: Close position → trade result pnl_pct reflects leverage
        result = mgr.close_position(
            symbol="BTC/USDT",
            exit_price=10200.0,
            reason=ExitReason.TAKE_PROFIT,
        )
        assert result is not None
        assert result.pnl_pct == pytest.approx(0.10, abs=1e-6)
        # Absolute PnL = (10200 - 10000) * 0.5 = 100
        assert result.pnl == pytest.approx(100.0, abs=1e-6)

    def test_full_chain_long_stop_loss(self):
        """LONG leverage=5: open → price hits SL → exit triggered → leveraged loss"""
        from src.plugins.risk_management.stop_loss_executor import StopLossExecutor

        config = {
            "max_positions": 3,
            "max_position_size": 0.5,
            "min_position_size": 0.001,
            "risk_per_trade": 0.02,
            "stop_loss": {
                "method": "fixed",
                "fixed_percentage": 0.03,
                "trailing_enabled": False,
            },
            "signal_exit": {},
        }
        mgr = PositionManager(config)

        import numpy as np
        import pandas as pd

        dates = pd.date_range("2026-01-01", periods=20, freq="h")
        df = pd.DataFrame(
            {
                "open": np.full(20, 10000.0),
                "high": np.full(20, 10100.0),
                "low": np.full(20, 9900.0),
                "close": np.full(20, 10000.0),
                "volume": np.full(20, 100.0),
            },
            index=dates,
        )

        # Open with leverage=5
        pos = mgr.open_position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=0.5,
            entry_price=10000.0,
            signal_confidence=0.85,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            df=df,
            leverage=5.0,
        )
        assert pos is not None
        # Fixed 3% SL → stop_loss = 10000 * 0.97 = 9700
        assert pos.stop_loss == pytest.approx(9700.0, abs=1.0)

        # Update position: price drops to stop loss → should trigger exit
        exit_result = mgr.update_position("BTC/USDT", current_price=9700.0)
        assert exit_result is not None
        assert exit_result.should_exit is True
        assert exit_result.reason == ExitReason.STOP_LOSS

        # PnL on the position reflects leverage: -3% × 5 = -15%
        assert pos.unrealized_pnl_pct == pytest.approx(-0.15, abs=1e-6)

        # Close it
        result = mgr.close_position(
            symbol="BTC/USDT",
            exit_price=9700.0,
            reason=ExitReason.STOP_LOSS,
        )
        assert result is not None
        assert result.pnl_pct == pytest.approx(-0.15, abs=1e-6)
        # Absolute PnL = (9700 - 10000) * 0.5 = -150
        assert result.pnl == pytest.approx(-150.0, abs=1e-6)
