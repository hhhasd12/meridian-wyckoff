"""生产就绪集成测试 — 5个关键链路端到端验证

Test 1: 杠杆PnL全链路
Test 2: 风控链路（CapitalGuard 日亏损限制）
Test 3: 止损链路（ExchangeExecutor paper模式止损触发）
Test 4: 关闭链路（app.py system.shutdown 事件名匹配）
Test 5: Journal恢复链路（PositionJournal 写入→恢复）
"""

import os
import tempfile
from datetime import datetime

import pytest

from src.kernel.types import TradingSignal
from src.plugins.position_manager.types import (
    Position,
    PositionSide,
    PositionStatus,
)
from src.plugins.risk_management.capital_guard import CapitalGuard
from src.plugins.exchange_connector.exchange_executor import ExchangeExecutor
from src.plugins.position_manager.position_journal import PositionJournal


# ── Test 1: 杠杆PnL全链路 ────────────────────────────────


class TestLeveragePnL:
    """验证 Position.calculate_unrealized_pnl 杠杆放大逻辑"""

    def test_long_5x_leverage_1pct_move(self):
        """LONG 5x杠杆 + 价格上涨1% → PnL% ≈ 5%"""
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            size=1.0,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=95.0,
            take_profit=110.0,
            signal_confidence=0.8,
            wyckoff_state="accumulation",
            entry_signal=TradingSignal.BUY,
            leverage=5.0,
        )
        pnl, pnl_pct = pos.calculate_unrealized_pnl(101.0)
        # 价格变动 1%, 杠杆 5x → PnL% = 5%
        assert abs(pnl_pct - 0.05) < 1e-9, f"expected ~0.05, got {pnl_pct}"
        # 绝对PnL = (101 - 100) * 1.0 = 1.0
        assert abs(pnl - 1.0) < 1e-9, f"expected ~1.0, got {pnl}"

    def test_short_3x_leverage_2pct_drop(self):
        """SHORT 3x杠杆 + 价格下跌2% → PnL% ≈ 6%"""
        pos = Position(
            symbol="ETH/USDT",
            side=PositionSide.SHORT,
            size=2.0,
            entry_price=100.0,
            entry_time=datetime.now(),
            stop_loss=105.0,
            take_profit=90.0,
            signal_confidence=0.7,
            wyckoff_state="distribution",
            entry_signal=TradingSignal.SELL,
            leverage=3.0,
        )
        pnl, pnl_pct = pos.calculate_unrealized_pnl(98.0)
        assert abs(pnl_pct - 0.06) < 1e-9, f"expected ~0.06, got {pnl_pct}"
        assert abs(pnl - 4.0) < 1e-9, f"expected ~4.0, got {pnl}"


# ── Test 2: 风控链路 ─────────────────────────────────────


class TestCapitalGuardCircuitBreaker:
    """验证 CapitalGuard 日亏损超限 → 禁止交易"""

    def test_daily_loss_exceeds_limit_halts_trading(self):
        """累计日亏损 > 5% → is_trading_allowed() == False"""
        guard = CapitalGuard(
            {
                "capital_management": {"daily_loss_limit": 0.05},
            }
        )
        # 初始状态允许交易
        assert guard.is_trading_allowed() is True

        # 模拟亏损：账户 10000，亏 300 (3%) — 仍允许
        guard.record_trade_result(pnl=-300, balance=9700)
        assert guard.is_trading_allowed() is True

        # 再亏 250 (累计 5.5% of peak=10000) — 超限
        guard.record_trade_result(pnl=-250, balance=9450)
        assert guard.is_trading_allowed() is False

        status = guard.get_status()
        assert status["daily_loss_pct"] >= 0.05


# ── Test 3: 止损链路 ─────────────────────────────────────


class TestStopLossExecution:
    """验证 ExchangeExecutor paper模式止损单触发"""

    def test_stop_order_triggered_on_price_drop(self):
        """开多仓 entry=100 → 手动创建 stop=98 → 价格跌到97 → 止损触发"""
        executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "slippage_rate": 0.0,
                "commission_rate": 0.0,
                "stop_loss_pct": 0.02,
            }
        )
        # 清空自动创建的止损单，手动控制
        executor._pending_stop_orders.clear()

        # 手动添加止损单（模拟 entry=100, stop=98 的 LONG 仓位）
        executor._pending_stop_orders.append(
            {
                "id": "stop_manual_1",
                "symbol": "BTC/USDT",
                "type": "STOP_MARKET",
                "side": "sell",
                "amount": 1.0,
                "stop_price": 98.0,
                "status": "open",
                "created_at": datetime.now(),
                "position_side": PositionSide.LONG,
                "info": {"paper_trading": True},
            }
        )
        assert len(executor._pending_stop_orders) == 1

        # 价格还在止损价上方 → 不触发
        triggered = executor.check_stop_orders({"BTC/USDT": 99.0})
        assert len(triggered) == 0
        assert len(executor._pending_stop_orders) == 1

        # 价格跌破止损价 → 触发
        triggered = executor.check_stop_orders({"BTC/USDT": 97.0})
        assert len(triggered) == 1
        assert triggered[0]["status"] == "triggered"
        assert triggered[0]["id"] == "stop_manual_1"
        # 原始止损单已从 pending 移除；
        # _simulate_order 平仓时自动为反向持仓创建了新止损单，
        # 验证原始止损单不在 pending 中
        original_ids = [s["id"] for s in executor._pending_stop_orders]
        assert "stop_manual_1" not in original_ids


# ── Test 4: 关闭链路 ─────────────────────────────────────


class TestShutdownEventMatch:
    """验证 app.py 发布 system.shutdown 与 position_manager 订阅一致"""

    def test_shutdown_event_name_matches(self):
        """app.py stop() 发布 'system.shutdown'，
        position_manager 订阅 'system.shutdown' — 名称必须一致"""
        import ast

        # 解析 app.py 找到 stop() 中 emit 的事件名
        app_path = os.path.join("src", "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            app_source = f.read()
        app_tree = ast.parse(app_source)

        shutdown_events_published = []
        for node in ast.walk(app_tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "emit"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and "shutdown" in str(node.args[0].value)
            ):
                shutdown_events_published.append(node.args[0].value)

        assert "system.shutdown" in shutdown_events_published, (
            f"app.py should emit 'system.shutdown', found: {shutdown_events_published}"
        )

        # 解析 position_manager/plugin.py 找到订阅的事件名
        pm_path = os.path.join("src", "plugins", "position_manager", "plugin.py")
        with open(pm_path, "r", encoding="utf-8") as f:
            pm_source = f.read()
        pm_tree = ast.parse(pm_source)

        shutdown_events_subscribed = []
        for node in ast.walk(pm_tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "subscribe_event"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and "shutdown" in str(node.args[0].value)
            ):
                shutdown_events_subscribed.append(node.args[0].value)

        assert "system.shutdown" in shutdown_events_subscribed, (
            f"position_manager should subscribe 'system.shutdown', "
            f"found: {shutdown_events_subscribed}"
        )


# ── Test 5: Journal恢复链路 ──────────────────────────────


class TestJournalRecovery:
    """验证 PositionJournal 写入→关闭→重新打开→恢复"""

    def test_write_close_reopen_recover(self):
        """写入持仓 → 关闭journal → 新实例读取 → 恢复正确"""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "test_journal.jsonl")

            # 创建 Position
            pos = Position(
                symbol="BTC/USDT",
                side=PositionSide.LONG,
                size=0.5,
                entry_price=30000.0,
                entry_time=datetime(2026, 1, 15, 12, 0, 0),
                stop_loss=29000.0,
                take_profit=33000.0,
                signal_confidence=0.85,
                wyckoff_state="spring",
                entry_signal=TradingSignal.STRONG_BUY,
                leverage=3.0,
            )

            # 第一个 journal 实例：写入开仓
            journal1 = PositionJournal(journal_path=journal_path)
            journal1.record_open(pos)

            # "关闭" journal1（Python GC 会处理，模拟重启）
            del journal1

            # 第二个 journal 实例：恢复
            journal2 = PositionJournal(journal_path=journal_path)
            recovered = journal2.recover_positions()

            assert "BTC/USDT" in recovered
            rpos = recovered["BTC/USDT"]
            assert rpos.symbol == "BTC/USDT"
            assert rpos.side == PositionSide.LONG
            assert abs(rpos.size - 0.5) < 1e-9
            assert abs(rpos.entry_price - 30000.0) < 1e-9
            assert abs(rpos.stop_loss - 29000.0) < 1e-9
            assert abs(rpos.take_profit - 33000.0) < 1e-9
            assert rpos.wyckoff_state == "spring"
            assert rpos.entry_signal == TradingSignal.STRONG_BUY
            assert rpos.status == PositionStatus.OPEN
            assert abs(rpos.signal_confidence - 0.85) < 1e-9
