"""交易所执行器测试 - 滑点、手续费、止损单、部分成交、超时

测试内容：
- [C6] 纸盘滑点 + 手续费模拟
- [H2] 交易所端止损单 (STOP_MARKET)
- [M9] 部分成交处理 + 订单超时
"""

import random
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.kernel.types import OrderStatus, OrderType
from src.plugins.exchange_connector.exchange_executor import (
    ExchangeExecutor,
)
from src.plugins.position_manager.types import PositionSide


class TestSlippageAndCommission:
    """[C6] 纸盘滑点 + 手续费"""

    def setup_method(self) -> None:
        self.executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "initial_balance": 10000.0,
                "slippage_rate": 0.0005,
                "commission_rate": 0.001,
            }
        )

    def test_default_slippage_rate(self) -> None:
        """测试默认滑点率"""
        executor = ExchangeExecutor({"paper_trading": True})
        assert executor.slippage_rate == 0.0005

    def test_default_commission_rate(self) -> None:
        """测试默认手续费率"""
        executor = ExchangeExecutor({"paper_trading": True})
        assert executor.commission_rate == 0.001

    def test_custom_rates(self) -> None:
        """测试自定义滑点和手续费"""
        assert self.executor.slippage_rate == 0.0005
        assert self.executor.commission_rate == 0.001

    def test_buy_market_slippage(self) -> None:
        """买入市价单滑点：价格应上升"""
        with patch("random.uniform", return_value=1.0):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "market", 0.1, 50000.0
            )
        expected = 50000.0 * (1 + 0.0005)
        assert order["price"] == pytest.approx(expected, rel=1e-6)

    def test_sell_market_slippage(self) -> None:
        """卖出市价单滑点：价格应下降"""
        with patch("random.uniform", return_value=1.0):
            order = self.executor._simulate_order(
                "BTC/USDT", "sell", "market", 0.1, 50000.0
            )
        expected = 50000.0 * (1 - 0.0005)
        assert order["price"] == pytest.approx(expected, rel=1e-6)

    def test_commission_deducted(self) -> None:
        """手续费从 paper_balance 扣除"""
        initial = self.executor._paper_balance
        with patch("random.uniform", return_value=1.0):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "market", 0.1, 50000.0
            )
        commission = order["commission"]
        assert commission > 0
        assert self.executor._paper_balance == pytest.approx(
            initial - commission, rel=1e-6
        )

    def test_commission_in_order_info(self) -> None:
        """手续费记录在订单 info 中"""
        with patch("random.uniform", return_value=1.0):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "market", 0.1, 50000.0
            )
        assert "commission" in order["info"]
        assert order["info"]["commission"] > 0

    def test_commission_calculation(self) -> None:
        """手续费 = price × size × commission_rate"""
        with patch("random.uniform", return_value=1.0):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "market", 0.1, 50000.0
            )
        price = order["price"]
        filled = order["filled"]
        expected_commission = price * filled * 0.001
        assert order["commission"] == pytest.approx(expected_commission, rel=1e-6)

    def test_limit_order_no_slippage(self) -> None:
        """限价单无滑点"""
        with patch("random.uniform", return_value=1.0):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "limit", 0.1, 49000.0
            )
        assert order["price"] == 49000.0

    def test_zero_slippage_config(self) -> None:
        """滑点率为0时无滑点"""
        executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "slippage_rate": 0.0,
            }
        )
        with patch("random.uniform", return_value=1.0):
            order = executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        assert order["price"] == 50000.0

    def test_multiple_orders_accumulate_commission(self) -> None:
        """多笔订单手续费累积扣除"""
        initial = self.executor._paper_balance
        with patch("random.uniform", return_value=1.0):
            o1 = self.executor._simulate_order(
                "BTC/USDT", "buy", "market", 0.1, 50000.0
            )
            o2 = self.executor._simulate_order("ETH/USDT", "buy", "market", 1.0, 3000.0)
        total_commission = o1["commission"] + o2["commission"]
        assert self.executor._paper_balance == pytest.approx(
            initial - total_commission, rel=1e-6
        )


class TestStopOrders:
    """[H2] 交易所端止损单"""

    def setup_method(self) -> None:
        self.executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "initial_balance": 10000.0,
                "stop_loss_pct": 0.02,
            }
        )

    def test_stop_order_created_on_buy(self) -> None:
        """买入开仓后自动创建止损单"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        stops = self.executor._pending_stop_orders
        assert len(stops) >= 1
        stop = stops[-1]
        assert stop["symbol"] == "BTC/USDT"
        assert stop["side"] == "sell"
        assert stop["type"] == "STOP_MARKET"
        assert stop["status"] == "open"

    def test_stop_order_created_on_sell(self) -> None:
        """卖出开仓后自动创建止损单"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "sell", "market", 0.1, 50000.0)
        stops = self.executor._pending_stop_orders
        assert len(stops) >= 1
        stop = stops[-1]
        assert stop["side"] == "buy"
        assert stop["position_side"] == PositionSide.SHORT

    def test_long_stop_price_below_entry(self) -> None:
        """LONG 止损价应在入场价下方"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        stop = self.executor._pending_stop_orders[-1]
        assert stop["stop_price"] < 50000.0

    def test_short_stop_price_above_entry(self) -> None:
        """SHORT 止损价应在入场价上方"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "sell", "market", 0.1, 50000.0)
        stop = self.executor._pending_stop_orders[-1]
        assert stop["stop_price"] > 50000.0

    def test_stop_order_default_distance(self) -> None:
        """默认止损距离 2%"""
        entry = 50000.0
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, entry)
        stop = self.executor._pending_stop_orders[-1]
        exec_price = entry * (1 + 0.0005)  # 含滑点
        expected_stop = exec_price * (1 - 0.02)
        assert stop["stop_price"] == pytest.approx(expected_stop, rel=1e-4)


class TestCheckStopOrders:
    """[H2] 止损单触发检查"""

    def setup_method(self) -> None:
        self.executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "initial_balance": 10000.0,
                "stop_loss_pct": 0.02,
            }
        )

    def test_long_stop_triggered(self) -> None:
        """LONG 仓位价格下跌触发止损"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        stop = self.executor._pending_stop_orders[-1]
        trigger_price = stop["stop_price"] - 100

        triggered = self.executor.check_stop_orders({"BTC/USDT": trigger_price})
        assert len(triggered) >= 1
        assert triggered[0]["status"] == "triggered"
        assert "execution_order" in triggered[0]

    def test_long_stop_not_triggered(self) -> None:
        """LONG 仓位价格未跌到止损位"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        triggered = self.executor.check_stop_orders({"BTC/USDT": 50500.0})
        assert len(triggered) == 0

    def test_short_stop_triggered(self) -> None:
        """SHORT 仓位价格上涨触发止损"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "sell", "market", 0.1, 50000.0)
        stop = self.executor._pending_stop_orders[-1]
        trigger_price = stop["stop_price"] + 100

        triggered = self.executor.check_stop_orders({"BTC/USDT": trigger_price})
        assert len(triggered) >= 1

    def test_stop_removed_after_trigger(self) -> None:
        """触发的止损单从 pending 列表移除"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        # 找到为此仓位创建的止损单
        stop = next(
            s
            for s in self.executor._pending_stop_orders
            if s["position_side"] == PositionSide.LONG
        )
        stop_id = stop["id"]

        self.executor.check_stop_orders({"BTC/USDT": stop["stop_price"] - 100})
        # 原止损单应该不在 pending 列表中
        remaining_ids = [s["id"] for s in self.executor._pending_stop_orders]
        assert stop_id not in remaining_ids

    def test_no_price_symbol_skipped(self) -> None:
        """无对应价格的交易对跳过检查"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        triggered = self.executor.check_stop_orders({"ETH/USDT": 3000.0})
        assert len(triggered) == 0
        assert len(self.executor._pending_stop_orders) > 0

    def test_empty_prices(self) -> None:
        """空价格字典不触发"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "market", 0.1, 50000.0)
        triggered = self.executor.check_stop_orders({})
        assert len(triggered) == 0


class TestPartialFill:
    """[M9] 部分成交处理"""

    def setup_method(self) -> None:
        self.executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "initial_balance": 10000.0,
            }
        )

    def test_limit_order_partial_fill(self) -> None:
        """限价单可能部分成交"""
        with patch("random.uniform", return_value=0.7):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "limit", 1.0, 49000.0
            )
        assert order["filled"] == pytest.approx(0.7, rel=1e-6)
        assert order["remaining"] == pytest.approx(0.3, rel=1e-6)
        assert order["status"] == "partial"

    def test_limit_order_full_fill(self) -> None:
        """限价单完全成交"""
        with patch("random.uniform", return_value=1.0):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "limit", 1.0, 49000.0
            )
        assert order["filled"] == 1.0
        assert order["remaining"] == 0.0
        assert order["status"] == "closed"

    def test_market_order_always_full(self) -> None:
        """市价单总是全部成交"""
        with patch("random.uniform", return_value=0.5):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "market", 1.0, 50000.0
            )
        assert order["filled"] == 1.0
        assert order["status"] == "closed"

    def test_partial_fill_position_size(self) -> None:
        """部分成交时持仓按实际成交量"""
        with patch("random.uniform", return_value=0.6):
            self.executor._simulate_order("BTC/USDT", "buy", "limit", 1.0, 49000.0)
        pos = self.executor._paper_positions.get("BTC/USDT")
        assert pos is not None
        assert pos["size"] == pytest.approx(0.6, rel=1e-6)

    def test_partial_commission_on_filled_only(self) -> None:
        """手续费仅按已成交部分计算"""
        with patch("random.uniform", return_value=0.5):
            order = self.executor._simulate_order(
                "BTC/USDT", "buy", "limit", 1.0, 49000.0
            )
        expected = 49000.0 * 0.5 * 0.001
        assert order["commission"] == pytest.approx(expected, rel=1e-6)


class TestOrderTimeout:
    """[M9] 订单超时处理"""

    def setup_method(self) -> None:
        self.executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "initial_balance": 10000.0,
            }
        )

    def test_partial_order_expires(self) -> None:
        """部分成交订单超时后标记 expired"""
        with patch("random.uniform", return_value=0.5):
            self.executor._simulate_order("BTC/USDT", "buy", "limit", 1.0, 49000.0)
        # 手动将创建时间设置为31秒前
        for o in self.executor._paper_orders:
            if o["status"] == "partial":
                o["created_at"] = datetime.now() - timedelta(seconds=31)

        expired = self.executor.check_order_timeouts(timeout_seconds=30.0)
        assert len(expired) == 1
        assert expired[0]["status"] == "expired"

    def test_recent_order_not_expired(self) -> None:
        """未超时的订单不标记"""
        with patch("random.uniform", return_value=0.5):
            self.executor._simulate_order("BTC/USDT", "buy", "limit", 1.0, 49000.0)
        expired = self.executor.check_order_timeouts(timeout_seconds=30.0)
        assert len(expired) == 0

    def test_filled_order_not_expired(self) -> None:
        """已完全成交的订单不受超时影响"""
        with patch("random.uniform", return_value=1.0):
            self.executor._simulate_order("BTC/USDT", "buy", "limit", 1.0, 49000.0)
        for o in self.executor._paper_orders:
            o["created_at"] = datetime.now() - timedelta(seconds=60)

        expired = self.executor.check_order_timeouts(timeout_seconds=30.0)
        assert len(expired) == 0

    def test_custom_timeout(self) -> None:
        """自定义超时时间"""
        with patch("random.uniform", return_value=0.5):
            self.executor._simulate_order("BTC/USDT", "buy", "limit", 1.0, 49000.0)
        for o in self.executor._paper_orders:
            if o["status"] == "partial":
                o["created_at"] = datetime.now() - timedelta(seconds=11)

        expired = self.executor.check_order_timeouts(timeout_seconds=10.0)
        assert len(expired) == 1


class TestOrderTypeEnum:
    """OrderType 枚举测试"""

    def test_stop_market_exists(self) -> None:
        """STOP_MARKET 枚举值存在"""
        assert OrderType.STOP_MARKET.value == "STOP_MARKET"

    def test_market_unchanged(self) -> None:
        """MARKET 枚举值不变"""
        assert OrderType.MARKET.value == "market"

    def test_limit_unchanged(self) -> None:
        """LIMIT 枚举值不变"""
        assert OrderType.LIMIT.value == "limit"


class TestOrderStatusEnum:
    """OrderStatus 枚举测试"""

    def test_expired_exists(self) -> None:
        """EXPIRED 枚举值存在"""
        assert OrderStatus.EXPIRED.value == "expired"

    def test_partial_unchanged(self) -> None:
        """PARTIAL 枚举值不变"""
        assert OrderStatus.PARTIAL.value == "partial"

    def test_filled_unchanged(self) -> None:
        """FILLED 枚举值不变"""
        assert OrderStatus.FILLED.value == "filled"


class TestStatisticsEnhanced:
    """增强统计信息测试"""

    def setup_method(self) -> None:
        self.executor = ExchangeExecutor(
            {
                "paper_trading": True,
                "initial_balance": 10000.0,
            }
        )

    def test_stats_include_stop_orders(self) -> None:
        """统计信息包含止损单数量"""
        stats = self.executor.get_statistics()
        assert "pending_stop_orders" in stats
        assert stats["pending_stop_orders"] == 0

    def test_stats_include_balance(self) -> None:
        """统计信息包含余额"""
        stats = self.executor.get_statistics()
        assert stats["paper_balance"] == 10000.0

    def test_stats_include_rates(self) -> None:
        """统计信息包含滑点/手续费率"""
        stats = self.executor.get_statistics()
        assert "slippage_rate" in stats
        assert "commission_rate" in stats

    def test_pending_stop_orders_init(self) -> None:
        """初始化时 pending_stop_orders 为空列表"""
        assert self.executor._pending_stop_orders == []
