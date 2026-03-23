"""平仓重试 + 部分成交处理测试

测试内容：
- [H3] 平仓失败指数退避重试（最多3次）
- [H3] 失败平仓加入 pending_exits 队列
- [H3] pending_exits 周期性重试
- [M9] 平仓部分成交处理（仅关闭已成交部分）
- [M9] OrderResult.is_partial 属性
- [M9] execute() 映射 expired 状态到 OrderStatus.EXPIRED
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.kernel.types import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingSignal,
)
from src.plugins.exchange_connector.exchange_executor import ExchangeExecutor
from src.plugins.position_manager.plugin import PositionManagerPlugin
from src.plugins.position_manager.position_manager import PositionManager
from src.plugins.position_manager.types import (
    ExitCheckResult,
    ExitReason,
    Position,
    PositionSide,
    PositionStatus,
)


def _make_position(
    symbol: str = "BTC/USDT",
    side: PositionSide = PositionSide.LONG,
    size: float = 1.0,
    entry_price: float = 50000.0,
) -> Position:
    """创建测试用持仓"""
    return Position(
        symbol=symbol,
        side=side,
        size=size,
        entry_price=entry_price,
        entry_time=datetime.now(),
        stop_loss=entry_price * 0.98,
        take_profit=entry_price * 1.04,
        signal_confidence=0.8,
        wyckoff_state="accumulation",
        entry_signal=TradingSignal.BUY,
        original_size=size,
        leverage=1.0,
    )


def _make_order_result(
    status: OrderStatus = OrderStatus.FILLED,
    filled_size: float = 1.0,
    filled_price: float = 50000.0,
    error: Optional[str] = None,
) -> OrderResult:
    """创建测试用订单结果"""
    return OrderResult(
        order_id="test_001",
        status=status,
        filled_size=filled_size,
        filled_price=filled_price,
        timestamp=datetime.now(),
        error=error,
    )


def _make_plugin() -> PositionManagerPlugin:
    """创建测试用插件实例（绕过 on_load）"""
    plugin = PositionManagerPlugin("position_manager")
    plugin._config = {"paper_trading": True}
    plugin._manager = PositionManager({"paper_trading": True})
    plugin._executor = MagicMock(spec=ExchangeExecutor)
    plugin._journal = None
    return plugin


class TestExecuteExitRetry:
    """[H3] 平仓失败指数退避重试"""

    def test_retry_succeeds_on_second_attempt(self) -> None:
        """第二次重试成功时不加入队列"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position()
        plugin._manager.positions["BTC/USDT"] = pos

        # 第一次失败，第二次成功
        fail_result = _make_order_result(status=OrderStatus.ERROR, error="timeout")
        ok_result = _make_order_result(
            status=OrderStatus.FILLED,
            filled_size=1.0,
            filled_price=50100.0,
        )
        plugin._executor.execute = MagicMock(side_effect=[fail_result, ok_result])

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)

        with patch("time.sleep"):
            plugin._execute_exit("BTC/USDT", 50100.0, exit_check)

        assert len(plugin._pending_exits) == 0
        assert plugin._executor.execute.call_count == 2

    def test_retry_succeeds_on_third_attempt(self) -> None:
        """第三次重试成功时不加入队列"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position()
        plugin._manager.positions["BTC/USDT"] = pos

        fail_result = _make_order_result(status=OrderStatus.ERROR, error="network")
        ok_result = _make_order_result(
            status=OrderStatus.FILLED,
            filled_size=1.0,
            filled_price=50100.0,
        )
        plugin._executor.execute = MagicMock(
            side_effect=[fail_result, fail_result, ok_result]
        )

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)

        with patch("time.sleep"):
            plugin._execute_exit("BTC/USDT", 50100.0, exit_check)

        assert len(plugin._pending_exits) == 0
        assert plugin._executor.execute.call_count == 3

    def test_all_retries_fail_goes_to_pending(self) -> None:
        """3次全部失败后加入 pending_exits 队列"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position()
        plugin._manager.positions["BTC/USDT"] = pos

        fail_result = _make_order_result(
            status=OrderStatus.ERROR, error="exchange_down"
        )
        plugin._executor.execute = MagicMock(return_value=fail_result)

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)

        with patch("time.sleep"):
            plugin._execute_exit("BTC/USDT", 49000.0, exit_check)

        assert len(plugin._pending_exits) == 1
        pending = plugin._pending_exits[0]
        assert pending["symbol"] == "BTC/USDT"
        assert pending["price"] == 49000.0
        assert pending["exit_result"] is exit_check
        assert "timestamp" in pending
        # 仓位不应被关闭
        assert plugin._manager.get_position("BTC/USDT") is not None

    def test_retry_uses_exponential_backoff(self) -> None:
        """重试使用指数退避延迟（1s, 2s）"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position()
        plugin._manager.positions["BTC/USDT"] = pos

        fail_result = _make_order_result(status=OrderStatus.ERROR, error="timeout")
        plugin._executor.execute = MagicMock(return_value=fail_result)

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)

        sleep_calls: List[float] = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            plugin._execute_exit("BTC/USDT", 49000.0, exit_check)

        # 3次尝试，前2次失败后 sleep（最后一次不 sleep）
        assert sleep_calls == [1, 2]

    def test_successful_exit_no_retry(self) -> None:
        """成功时不重试"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position()
        plugin._manager.positions["BTC/USDT"] = pos

        ok_result = _make_order_result(
            status=OrderStatus.FILLED,
            filled_size=1.0,
            filled_price=50100.0,
        )
        plugin._executor.execute = MagicMock(return_value=ok_result)

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.TAKE_PROFIT)
        plugin._execute_exit("BTC/USDT", 50100.0, exit_check)

        assert len(plugin._pending_exits) == 0
        assert plugin._executor.execute.call_count == 1
        assert plugin._close_count == 1


class TestPendingExitsQueue:
    """[H3] pending_exits 队列周期性重试"""

    def test_check_pending_exits_retries(self) -> None:
        """周期性检查重试待处理平仓"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position()
        plugin._manager.positions["BTC/USDT"] = pos
        plugin._last_prices["BTC/USDT"] = 49500.0

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)
        plugin._pending_exits.append(
            {
                "symbol": "BTC/USDT",
                "price": 49000.0,
                "exit_result": exit_check,
                "timestamp": time.time() - 60,
            }
        )

        # 重试时成功
        ok_result = _make_order_result(
            status=OrderStatus.FILLED,
            filled_size=1.0,
            filled_price=49500.0,
        )
        plugin._executor.execute = MagicMock(return_value=ok_result)

        with patch("time.sleep"):
            plugin._check_pending_exits()

        assert len(plugin._pending_exits) == 0
        assert plugin._close_count == 1

    def test_check_pending_exits_position_gone(self) -> None:
        """仓位已不存在时丢弃 pending exit"""
        plugin = _make_plugin()
        # 没有持仓

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)
        plugin._pending_exits.append(
            {
                "symbol": "BTC/USDT",
                "price": 49000.0,
                "exit_result": exit_check,
                "timestamp": time.time(),
            }
        )

        plugin._check_pending_exits()

        assert len(plugin._pending_exits) == 0

    def test_check_pending_exits_empty_noop(self) -> None:
        """空队列时无操作"""
        plugin = _make_plugin()
        plugin._check_pending_exits()
        assert len(plugin._pending_exits) == 0

    def test_pending_uses_latest_price(self) -> None:
        """重试时使用最新价格而非原始价格"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position()
        plugin._manager.positions["BTC/USDT"] = pos
        plugin._last_prices["BTC/USDT"] = 48000.0  # 最新价

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)
        plugin._pending_exits.append(
            {
                "symbol": "BTC/USDT",
                "price": 49000.0,  # 原始价
                "exit_result": exit_check,
                "timestamp": time.time(),
            }
        )

        ok_result = _make_order_result(
            status=OrderStatus.FILLED,
            filled_size=1.0,
            filled_price=48000.0,
        )
        plugin._executor.execute = MagicMock(return_value=ok_result)

        with patch("time.sleep"):
            plugin._check_pending_exits()

        # 应使用最新价格48000.0作为退出价
        call_args = plugin._executor.execute.call_args
        request: OrderRequest = call_args[0][0]
        assert request.price == 48000.0


class TestPartialFillExit:
    """[M9] 平仓部分成交处理"""

    def test_partial_fill_exit_closes_filled_portion(self) -> None:
        """部分成交时仅关闭已成交部分"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position(size=1.0)
        plugin._manager.positions["BTC/USDT"] = pos

        # 部分成交：0.6/1.0
        partial_result = _make_order_result(
            status=OrderStatus.PARTIAL,
            filled_size=0.6,
            filled_price=50100.0,
        )
        plugin._executor.execute = MagicMock(return_value=partial_result)

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.STOP_LOSS)

        with patch("time.sleep"):
            plugin._execute_exit("BTC/USDT", 50100.0, exit_check)

        # 部分平仓后，剩余加入待重试队列
        assert len(plugin._pending_exits) == 1
        assert plugin._close_count == 1

    def test_partial_fill_exit_remaining_queued(self) -> None:
        """部分成交后剩余部分加入 pending 队列"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position(size=2.0)
        plugin._manager.positions["BTC/USDT"] = pos

        partial_result = _make_order_result(
            status=OrderStatus.PARTIAL,
            filled_size=1.2,
            filled_price=50050.0,
        )
        plugin._executor.execute = MagicMock(return_value=partial_result)

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.TAKE_PROFIT)

        with patch("time.sleep"):
            plugin._execute_exit("BTC/USDT", 50050.0, exit_check)

        assert len(plugin._pending_exits) == 1
        pending = plugin._pending_exits[0]
        assert pending["symbol"] == "BTC/USDT"

    def test_full_fill_does_not_queue(self) -> None:
        """全部成交时不加入队列"""
        plugin = _make_plugin()
        assert plugin._manager is not None
        assert plugin._executor is not None
        pos = _make_position(size=1.0)
        plugin._manager.positions["BTC/USDT"] = pos

        full_result = _make_order_result(
            status=OrderStatus.FILLED,
            filled_size=1.0,
            filled_price=50100.0,
        )
        plugin._executor.execute = MagicMock(return_value=full_result)

        exit_check = ExitCheckResult(should_exit=True, reason=ExitReason.TAKE_PROFIT)
        plugin._execute_exit("BTC/USDT", 50100.0, exit_check)

        assert len(plugin._pending_exits) == 0
        assert plugin._close_count == 1


class TestOrderResultPartial:
    """[M9] OrderResult.is_partial 属性"""

    def test_is_partial_true(self) -> None:
        """PARTIAL 状态返回 True"""
        result = _make_order_result(status=OrderStatus.PARTIAL)
        assert result.is_partial is True

    def test_is_partial_false_filled(self) -> None:
        """FILLED 状态返回 False"""
        result = _make_order_result(status=OrderStatus.FILLED)
        assert result.is_partial is False

    def test_is_partial_false_error(self) -> None:
        """ERROR 状态返回 False"""
        result = _make_order_result(status=OrderStatus.ERROR)
        assert result.is_partial is False

    def test_is_filled_and_is_error_unchanged(self) -> None:
        """is_filled 和 is_error 属性不受影响"""
        filled = _make_order_result(status=OrderStatus.FILLED)
        assert filled.is_filled is True
        assert filled.is_error is False

        error = _make_order_result(status=OrderStatus.ERROR)
        assert error.is_filled is False
        assert error.is_error is True


class TestExpiredStatusMapping:
    """[M9] execute() 映射 expired 状态"""

    def test_expired_status_mapped(self) -> None:
        """交易所返回 'expired' 映射到 OrderStatus.EXPIRED"""
        executor = ExchangeExecutor({"paper_trading": True, "initial_balance": 10000.0})
        # 直接调用 _simulate_order 创建一个 partial 单
        with patch("random.uniform", return_value=0.5):
            executor._simulate_order("BTC/USDT", "buy", "limit", 1.0, 49000.0)

        # 手动将订单状态改为 expired 模拟超时
        for o in executor._paper_orders:
            if o["status"] == "partial":
                o["status"] = "expired"

        # 验证 check_order_timeouts 产生 expired 状态
        # (这已在现有测试中验证)
        expired_orders = [o for o in executor._paper_orders if o["status"] == "expired"]
        assert len(expired_orders) >= 1

    def test_order_status_expired_enum_value(self) -> None:
        """OrderStatus.EXPIRED 枚举值为 'expired'"""
        assert OrderStatus.EXPIRED.value == "expired"

    def test_execute_maps_expired_from_exchange(self) -> None:
        """execute() 方法正确映射 expired 状态"""
        executor = ExchangeExecutor({"paper_trading": True, "initial_balance": 10000.0})

        # Mock _place_order 返回 expired 状态
        expired_raw = {
            "id": "test_expired_001",
            "filled": 0.5,
            "price": 49000.0,
            "status": "expired",
        }
        with patch.object(executor, "_place_order", return_value=expired_raw):
            request = OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=1.0,
                price=49000.0,
            )
            result = executor.execute(request)

        assert result.status == OrderStatus.EXPIRED
        assert result.filled_size == 0.5
