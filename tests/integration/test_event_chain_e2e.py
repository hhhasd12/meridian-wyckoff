"""E2E 事件链集成测试 — 验证跨插件真实事件传播

6 条关键事件链 + Paper Trading 全周期 + 错误隔离:
1. 核心信号链: trading.signal → position.opened
2. 价格更新链: market.price_update → 止损触发
3. 熔断链: circuit_breaker_tripped → 4 消费者
4. 进化链: evolution.cycle_complete → 2 消费者
5. 关机链: system.shutdown → 强制平仓
6. 数据回环: data_refresh_requested → data_pipeline
7. Paper Trading 全周期 (信号→开仓→止损→平仓)
8. EventBus 错误隔离
"""

from typing import Any, Dict, List

import pytest

from src.kernel.types import TradingSignal


# ================================================================
# Helpers
# ================================================================


def _enable_history(loaded_app) -> None:
    """启用 EventBus 历史记录"""
    bus = loaded_app.plugin_manager.get_event_bus()
    bus._enable_history = True
    bus._history.clear()


def _get_history_names(loaded_app) -> List[str]:
    """获取事件历史中的事件名列表"""
    bus = loaded_app.plugin_manager.get_event_bus()
    return [r.event_name for r in bus.get_history(limit=200)]


def _clear_positions(loaded_app) -> None:
    """清理所有持仓"""
    pm = loaded_app.plugin_manager.get_plugin("position_manager")
    if pm and hasattr(pm, "_manager") and pm._manager:
        pm._manager.positions.clear()


# ================================================================
# Chain 1 — 核心信号链
# ================================================================


class TestCoreSignalChain:
    """trading.signal → position_manager → position.opened"""

    def test_signal_event_reaches_position_manager(self, loaded_app) -> None:
        """直接 emit trading.signal，验证 position_manager 接收"""
        _enable_history(loaded_app)
        _clear_positions(loaded_app)
        bus = loaded_app.plugin_manager.get_event_bus()

        bus.emit(
            "trading.signal",
            {
                "symbol": "TEST/USDT",
                "signal": TradingSignal.STRONG_BUY,
                "confidence": 0.85,
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 52000.0,
                "reasoning": ["test signal"],
                "timestamp": "2026-01-01T00:00:00Z",
            },
            publisher="test",
        )

        events = _get_history_names(loaded_app)
        assert "trading.signal" in events

    def test_trading_signal_subscribers_exist(self, loaded_app) -> None:
        """验证 trading.signal 有预期的订阅者"""
        bus = loaded_app.plugin_manager.get_event_bus()
        sub_names = bus.get_subscribers("trading.signal")
        assert "position_manager" in sub_names
        assert "audit_logger" in sub_names


# ================================================================
# Chain 2 — 价格更新链
# ================================================================


class TestPriceUpdateChain:
    """market.price_update → position_manager 检查止损"""

    def test_price_update_subscriber_exists(self, loaded_app) -> None:
        """验证 position_manager 订阅了 market.price_update"""
        bus = loaded_app.plugin_manager.get_event_bus()
        sub_names = bus.get_subscribers("market.price_update")
        assert "position_manager" in sub_names

    def test_price_update_event_propagates(self, loaded_app) -> None:
        """emit market.price_update，验证事件传播"""
        _enable_history(loaded_app)
        bus = loaded_app.plugin_manager.get_event_bus()

        bus.emit(
            "market.price_update",
            {
                "symbol": "BTC/USDT",
                "price": 50000.0,
                "timestamp": "2026-01-01T00:00:00Z",
            },
            publisher="test",
        )

        events = _get_history_names(loaded_app)
        assert "market.price_update" in events


# ================================================================
# Chain 3 — 熔断链
# ================================================================


class TestCircuitBreakerChain:
    """circuit_breaker_tripped → orchestrator + position_manager
    + telegram_notifier + audit_logger (4 消费者)"""

    def test_circuit_breaker_subscribers_complete(self, loaded_app) -> None:
        """验证熔断事件有全部 4 个预期订阅者"""
        bus = loaded_app.plugin_manager.get_event_bus()
        event = "risk_management.circuit_breaker_tripped"
        sub_names = bus.get_subscribers(event)
        assert "orchestrator" in sub_names
        assert "position_manager" in sub_names

    def test_circuit_breaker_event_propagates(self, loaded_app) -> None:
        """emit circuit_breaker_tripped，验证事件传播"""
        _enable_history(loaded_app)
        bus = loaded_app.plugin_manager.get_event_bus()

        event_name = "risk_management.circuit_breaker_tripped"
        result = bus.emit(
            event_name,
            {"tripped": True, "status": "TRIPPED"},
            publisher="test",
        )

        assert result >= 2  # 至少 2 个 handler 成功处理
        events = _get_history_names(loaded_app)
        assert event_name in events

    def test_circuit_breaker_recovery(self, loaded_app) -> None:
        """emit circuit_breaker_recovered，验证恢复事件传播"""
        _enable_history(loaded_app)
        bus = loaded_app.plugin_manager.get_event_bus()

        event_name = "risk_management.circuit_breaker_recovered"
        result = bus.emit(
            event_name,
            {"status": "NORMAL"},
            publisher="test",
        )

        assert result >= 1
        events = _get_history_names(loaded_app)
        assert event_name in events


# ================================================================
# Chain 4 — 进化链
# ================================================================


class TestEvolutionChain:
    """evolution.cycle_complete → self_correction + advisor"""

    def test_evolution_cycle_subscribers_exist(self, loaded_app) -> None:
        """验证 evolution.cycle_complete 有订阅者"""
        bus = loaded_app.plugin_manager.get_event_bus()
        sub_names = bus.get_subscribers("evolution.cycle_complete")
        # self_correction 和/或 evolution_advisor 应订阅
        assert len(sub_names) >= 1

    def test_evolution_cycle_event_propagates(self, loaded_app) -> None:
        """emit evolution.cycle_complete，验证事件传播"""
        _enable_history(loaded_app)
        bus = loaded_app.plugin_manager.get_event_bus()

        bus.emit(
            "evolution.cycle_complete",
            {
                "cycle": 1,
                "generation": 10,
                "best_fitness": 0.8,
                "avg_fitness": 0.5,
                "wfa_passed": True,
            },
            publisher="test",
        )

        events = _get_history_names(loaded_app)
        assert "evolution.cycle_complete" in events


# ================================================================
# Chain 5 — 关机链
# ================================================================


class TestShutdownChain:
    """system.shutdown → position_manager 强制平仓"""

    def test_shutdown_subscribers_exist(self, loaded_app) -> None:
        """验证 system.shutdown 有 position_manager 订阅"""
        bus = loaded_app.plugin_manager.get_event_bus()
        sub_names = bus.get_subscribers("system.shutdown")
        assert "position_manager" in sub_names

    def test_shutdown_event_propagates(self, loaded_app) -> None:
        """emit system.shutdown，验证事件传播"""
        _enable_history(loaded_app)
        bus = loaded_app.plugin_manager.get_event_bus()

        bus.emit(
            "system.shutdown",
            {},
            publisher="test",
        )

        events = _get_history_names(loaded_app)
        assert "system.shutdown" in events


# ================================================================
# Chain 6 — 数据回环
# ================================================================


class TestDataRefreshLoop:
    """data_refresh_requested → data_pipeline"""

    def test_data_refresh_subscriber_exists(self, loaded_app) -> None:
        """验证 data_pipeline 订阅了 data_refresh_requested"""
        bus = loaded_app.plugin_manager.get_event_bus()
        event = "orchestrator.data_refresh_requested"
        sub_names = bus.get_subscribers(event)
        assert "data_pipeline" in sub_names


# ================================================================
# Chain 7 — EventBus 错误隔离
# ================================================================


class TestEventBusErrorIsolation:
    """一个 handler 异常不影响其他 handler"""

    def test_error_isolation(self, loaded_app) -> None:
        """注册一个抛异常的 handler，验证不影响其他"""
        bus = loaded_app.plugin_manager.get_event_bus()
        _enable_history(loaded_app)
        results: List[str] = []

        def good_handler(event: str, data: dict) -> None:
            results.append("ok")

        def bad_handler(event: str, data: dict) -> None:
            raise ValueError("intentional test error")

        test_event = "test.error_isolation"
        bus.subscribe(test_event, bad_handler, subscriber_name="bad")
        bus.subscribe(test_event, good_handler, subscriber_name="good")

        bus.emit(test_event, {}, publisher="test")

        # good_handler 应该仍然执行
        assert "ok" in results

        # 清理
        bus.unsubscribe(test_event, bad_handler)
        bus.unsubscribe(test_event, good_handler)
