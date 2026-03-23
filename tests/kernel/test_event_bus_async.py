"""测试 EventBus 异步处理器支持

验证 sync emit() 能正确调用 async handler，包括：
1. 基本异步处理器执行
2. 混合同步/异步处理器
3. 异步处理器错误隔离
4. 异步处理器带正确参数
5. emit_async() 仍然正常工作
6. 通配符模式匹配的异步处理器
7. 优先级排序对异步处理器生效
"""

import asyncio

import pytest

from src.kernel.event_bus import EventBus
from src.kernel.types import EventPriority


class TestEventBusAsyncHandlers:
    """测试异步处理器在 sync emit() 中的行为"""

    def setup_method(self) -> None:
        self.bus = EventBus()

    def test_async_handler_called_via_sync_emit(self) -> None:
        """异步处理器通过 sync emit() 被正确调用"""
        received = []

        async def async_handler(event_name: str, data: dict) -> None:
            received.append({"event": event_name, "data": data})

        self.bus.subscribe_async("test.async", async_handler)
        count = self.bus.emit("test.async", {"key": "value"})

        assert count == 1
        assert len(received) == 1
        assert received[0]["event"] == "test.async"
        assert received[0]["data"]["key"] == "value"

    def test_async_handler_receives_correct_args(self) -> None:
        """异步处理器接收正确的 event_name 和 data"""
        captured_args = {}

        async def async_handler(event_name: str, data: dict) -> None:
            captured_args["event_name"] = event_name
            captured_args["data"] = data.copy()

        self.bus.subscribe_async("my.event", async_handler)
        test_data = {"symbol": "BTC/USDT", "price": 50000.0}
        self.bus.emit("my.event", test_data)

        assert captured_args["event_name"] == "my.event"
        assert captured_args["data"]["symbol"] == "BTC/USDT"
        assert captured_args["data"]["price"] == 50000.0

    def test_mixed_sync_and_async_handlers(self) -> None:
        """混合同步和异步处理器都被正确调用"""
        results = []

        def sync_handler(event_name: str, data: dict) -> None:
            results.append("sync")

        async def async_handler(event_name: str, data: dict) -> None:
            results.append("async")

        self.bus.subscribe("mixed.event", sync_handler)
        self.bus.subscribe_async("mixed.event", async_handler)
        count = self.bus.emit("mixed.event", {})

        assert count == 2
        assert "sync" in results
        assert "async" in results

    def test_multiple_async_handlers(self) -> None:
        """多个异步处理器都被调用"""
        results = []

        async def handler_a(event_name: str, data: dict) -> None:
            results.append("a")

        async def handler_b(event_name: str, data: dict) -> None:
            results.append("b")

        self.bus.subscribe_async("multi", handler_a)
        self.bus.subscribe_async("multi", handler_b)
        count = self.bus.emit("multi", {})

        assert count == 2
        assert "a" in results
        assert "b" in results

    def test_async_handler_error_isolation(self) -> None:
        """异步处理器异常不影响其他处理器（错误隔离）"""
        results = []

        async def bad_async(event_name: str, data: dict) -> None:
            raise ValueError("异步处理器故意抛出的错误")

        def good_sync(event_name: str, data: dict) -> None:
            results.append("sync_ok")

        async def good_async(event_name: str, data: dict) -> None:
            results.append("async_ok")

        # 注册：bad_async, good_sync, good_async
        self.bus.subscribe_async("error.test", bad_async, subscriber_name="bad")
        self.bus.subscribe("error.test", good_sync, subscriber_name="good_sync")
        self.bus.subscribe_async("error.test", good_async, subscriber_name="good_async")

        # sync emit 不应崩溃
        count = self.bus.emit("error.test", {})

        # bad_async 在 asyncio.run() 路径中会抛异常被 except 捕获
        # 所以 count 反映实际成功数
        assert "sync_ok" in results
        assert "async_ok" in results

    def test_async_handler_error_counted(self) -> None:
        """异步处理器的异常被正确计入 error_count"""

        async def bad_handler(event_name: str, data: dict) -> None:
            raise RuntimeError("测试错误")

        self.bus.subscribe_async("err.count", bad_handler, subscriber_name="bad")

        initial_errors = self.bus._error_count
        self.bus.emit("err.count", {})

        assert self.bus._error_count > initial_errors

    def test_sync_handlers_not_affected(self) -> None:
        """添加异步处理器支持不影响同步处理器行为"""
        results = []

        def handler_high(event_name: str, data: dict) -> None:
            results.append("high")

        def handler_low(event_name: str, data: dict) -> None:
            results.append("low")

        def handler_normal(event_name: str, data: dict) -> None:
            results.append("normal")

        self.bus.subscribe("sync.only", handler_low, priority=EventPriority.LOW)
        self.bus.subscribe("sync.only", handler_high, priority=EventPriority.HIGH)
        self.bus.subscribe("sync.only", handler_normal, priority=EventPriority.NORMAL)

        count = self.bus.emit("sync.only", {"val": 42})

        assert count == 3
        assert results == ["high", "normal", "low"]

    def test_async_handler_with_wildcard_pattern(self) -> None:
        """异步处理器支持通配符模式匹配"""
        received = []

        async def wildcard_handler(event_name: str, data: dict) -> None:
            received.append(event_name)

        self.bus.subscribe_async("trading.*", wildcard_handler)
        self.bus.emit("trading.signal", {"action": "BUY"})
        self.bus.emit("trading.close", {"reason": "stop_loss"})
        self.bus.emit("market.data", {})  # 不应匹配

        assert len(received) == 2
        assert "trading.signal" in received
        assert "trading.close" in received

    def test_async_handler_with_priority(self) -> None:
        """异步处理器的优先级排序正确"""
        order = []

        async def high_handler(event_name: str, data: dict) -> None:
            order.append("high")

        async def low_handler(event_name: str, data: dict) -> None:
            order.append("low")

        def sync_normal(event_name: str, data: dict) -> None:
            order.append("normal")

        self.bus.subscribe_async("prio", low_handler, priority=EventPriority.LOW)
        self.bus.subscribe_async("prio", high_handler, priority=EventPriority.HIGH)
        self.bus.subscribe("prio", sync_normal, priority=EventPriority.NORMAL)

        self.bus.emit("prio", {})

        assert order == ["high", "normal", "low"]

    def test_async_handler_emit_returns_correct_count(self) -> None:
        """sync emit() 返回正确的成功处理器计数（含异步处理器）"""

        async def handler(event_name: str, data: dict) -> None:
            pass

        def sync_handler(event_name: str, data: dict) -> None:
            pass

        self.bus.subscribe_async("count.test", handler)
        self.bus.subscribe("count.test", sync_handler)

        count = self.bus.emit("count.test", {})
        assert count == 2

    def test_async_handler_with_none_data(self) -> None:
        """async handler 能处理 data=None（自动转为空 dict）"""
        received_data = []

        async def handler(event_name: str, data: dict) -> None:
            received_data.append(data)

        self.bus.subscribe_async("null.data", handler)
        self.bus.emit("null.data")

        assert len(received_data) == 1
        assert received_data[0] == {}

    def test_unsubscribe_async_handler(self) -> None:
        """异步处理器可以被正确取消订阅"""
        received = []

        async def handler(event_name: str, data: dict) -> None:
            received.append(1)

        self.bus.subscribe_async("unsub.async", handler)
        self.bus.emit("unsub.async", {})
        assert len(received) == 1

        self.bus.unsubscribe("unsub.async", handler)  # type: ignore[arg-type]
        self.bus.emit("unsub.async", {})
        assert len(received) == 1  # 不再接收


class TestEventBusEmitAsync:
    """测试 emit_async() 方法（对比验证）"""

    def setup_method(self) -> None:
        self.bus = EventBus()

    def test_emit_async_with_async_handler(self) -> None:
        """emit_async() 正确调用异步处理器"""
        received = []

        async def handler(event_name: str, data: dict) -> None:
            received.append(data)

        self.bus.subscribe_async("async.evt", handler)

        asyncio.run(self.bus.emit_async("async.evt", {"ok": True}))

        assert len(received) == 1
        assert received[0]["ok"] is True

    def test_emit_async_mixed_handlers(self) -> None:
        """emit_async() 正确处理混合同步/异步处理器"""
        results = []

        def sync_handler(event_name: str, data: dict) -> None:
            results.append("sync")

        async def async_handler(event_name: str, data: dict) -> None:
            results.append("async")

        self.bus.subscribe("mixed", sync_handler)
        self.bus.subscribe_async("mixed", async_handler)

        count = asyncio.run(self.bus.emit_async("mixed", {}))

        assert count == 2
        assert "sync" in results
        assert "async" in results

    def test_emit_async_error_isolation(self) -> None:
        """emit_async() 中的错误隔离"""
        results = []

        async def bad_handler(event_name: str, data: dict) -> None:
            raise ValueError("故意的错误")

        async def good_handler(event_name: str, data: dict) -> None:
            results.append("ok")

        self.bus.subscribe_async("err", bad_handler)
        self.bus.subscribe_async("err", good_handler)

        count = asyncio.run(self.bus.emit_async("err", {}))

        assert "ok" in results
        assert count == 1  # bad_handler 失败不计入


class TestEventBusAsyncEdgeCases:
    """测试异步处理器的边缘情况"""

    def setup_method(self) -> None:
        self.bus = EventBus()

    def test_async_handler_with_paused_event(self) -> None:
        """暂停事件时异步处理器不被调用"""
        received = []

        async def handler(event_name: str, data: dict) -> None:
            received.append(1)

        self.bus.subscribe_async("pause.test", handler)
        self.bus.pause_event("pause.test")

        count = self.bus.emit("pause.test", {})
        assert count == 0
        assert len(received) == 0

        self.bus.resume_event("pause.test")
        count = self.bus.emit("pause.test", {})
        assert count == 1
        assert len(received) == 1

    def test_async_handler_event_history(self) -> None:
        """事件历史记录正确记录异步处理器的执行"""
        bus = EventBus(enable_history=True)

        async def handler(event_name: str, data: dict) -> None:
            pass

        bus.subscribe_async("hist.test", handler)
        bus.emit("hist.test", {"recorded": True}, publisher="test_pub")

        history = bus.get_history()
        assert len(history) == 1
        assert history[0].event_name == "hist.test"
        assert history[0].handler_count == 1
        assert history[0].publisher == "test_pub"

    def test_stats_include_async_subscriptions(self) -> None:
        """统计信息正确包含异步订阅"""

        async def handler(event_name: str, data: dict) -> None:
            pass

        self.bus.subscribe_async("stats.test", handler)
        stats = self.bus.get_stats()

        assert stats["total_subscriptions"] == 1
        assert stats["exact_subscriptions"] == 1

    def test_unsubscribe_all_removes_async(self) -> None:
        """unsubscribe_all() 正确移除异步订阅"""
        received = []

        async def handler(event_name: str, data: dict) -> None:
            received.append(1)

        self.bus.subscribe_async("unsub_all", handler, subscriber_name="plugin_x")
        removed = self.bus.unsubscribe_all("plugin_x")
        assert removed == 1

        self.bus.emit("unsub_all", {})
        assert len(received) == 0

    def test_clear_removes_async_subscriptions(self) -> None:
        """clear() 清除所有异步订阅"""

        async def handler(event_name: str, data: dict) -> None:
            pass

        self.bus.subscribe_async("clear.test", handler)
        self.bus.clear()

        stats = self.bus.get_stats()
        assert stats["total_subscriptions"] == 0
