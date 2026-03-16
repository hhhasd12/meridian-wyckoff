"""测试 src/kernel/event_bus.py 中的事件总线"""

import asyncio

import pytest

from src.kernel.event_bus import EventBus
from src.kernel.types import EventPriority


class TestEventBus:
    """测试 EventBus 核心功能"""

    def setup_method(self) -> None:
        self.bus = EventBus()

    def test_subscribe_and_emit(self) -> None:
        """测试基本的订阅和发布"""
        received = []

        def handler(event_name: str, data: dict) -> None:
            received.append(data)

        self.bus.subscribe("test.event", handler)
        self.bus.emit("test.event", {"key": "value"})

        assert len(received) == 1
        assert received[0]["key"] == "value"

    def test_multiple_subscribers(self) -> None:
        """测试多个订阅者"""
        results = []

        def handler_a(event_name: str, data: dict) -> None:
            results.append("a")

        def handler_b(event_name: str, data: dict) -> None:
            results.append("b")

        self.bus.subscribe("evt", handler_a)
        self.bus.subscribe("evt", handler_b)
        self.bus.emit("evt", {})

        assert len(results) == 2
        assert "a" in results
        assert "b" in results

    def test_unsubscribe(self) -> None:
        """测试取消订阅"""
        received = []

        def handler(event_name: str, data: dict) -> None:
            received.append(1)

        self.bus.subscribe("evt", handler)
        self.bus.emit("evt", {})
        assert len(received) == 1

        self.bus.unsubscribe("evt", handler)
        self.bus.emit("evt", {})
        assert len(received) == 1  # 不再接收

    def test_unsubscribe_all(self) -> None:
        """测试按 subscriber_name 取消所有订阅"""
        received = []

        def handler(event_name: str, data: dict) -> None:
            received.append(1)

        self.bus.subscribe(
            "a", handler, subscriber_name="p1"
        )
        self.bus.subscribe(
            "b", handler, subscriber_name="p1"
        )
        self.bus.unsubscribe_all("p1")

        self.bus.emit("a", {})
        self.bus.emit("b", {})
        assert len(received) == 0

    def test_wildcard_pattern(self) -> None:
        """测试通配符模式匹配"""
        received = []

        def handler(event_name: str, data: dict) -> None:
            received.append(event_name)

        self.bus.subscribe("plugin.*", handler)
        self.bus.emit("plugin.loaded", {"name": "test"})
        self.bus.emit("plugin.unloaded", {"name": "test"})
        self.bus.emit("kernel.started", {})

        assert len(received) == 2

    def test_priority_ordering(self) -> None:
        """测试优先级排序"""
        order = []

        def high_handler(event_name: str, data: dict) -> None:
            order.append("high")

        def low_handler(event_name: str, data: dict) -> None:
            order.append("low")

        def normal_handler(event_name: str, data: dict) -> None:
            order.append("normal")

        self.bus.subscribe(
            "evt", low_handler, priority=EventPriority.LOW
        )
        self.bus.subscribe(
            "evt", high_handler, priority=EventPriority.HIGH
        )
        self.bus.subscribe(
            "evt", normal_handler, priority=EventPriority.NORMAL
        )

        self.bus.emit("evt", {})
        assert order == ["high", "normal", "low"]

    def test_error_isolation(self) -> None:
        """测试错误隔离：一个处理器异常不影响其他"""
        results = []

        def bad_handler(event_name: str, data: dict) -> None:
            raise ValueError("故意的错误")

        def good_handler(event_name: str, data: dict) -> None:
            results.append("ok")

        self.bus.subscribe("evt", bad_handler)
        self.bus.subscribe("evt", good_handler)
        self.bus.emit("evt", {})

        assert len(results) == 1
        assert results[0] == "ok"

    def test_pause_and_resume(self) -> None:
        """测试暂停和恢复事件"""
        received = []

        def handler(event_name: str, data: dict) -> None:
            received.append(1)

        self.bus.subscribe("evt", handler)

        self.bus.pause_event("evt")
        self.bus.emit("evt", {})
        assert len(received) == 0

        self.bus.resume_event("evt")
        self.bus.emit("evt", {})
        assert len(received) == 1

    def test_event_history(self) -> None:
        """测试事件历史记录"""
        bus = EventBus(max_history=5, enable_history=True)
        for i in range(3):
            bus.emit("evt", {"i": i})

        history = bus.get_history()
        assert len(history) == 3

    def test_stats(self) -> None:
        """测试统计信息"""
        self.bus.subscribe(
            "a", lambda en, d: None
        )
        self.bus.subscribe(
            "b", lambda en, d: None
        )
        self.bus.emit("a", {})
        self.bus.emit("a", {})

        stats = self.bus.get_stats()
        assert stats["total_subscriptions"] == 2
        assert stats["emit_count"] >= 2

    def test_emit_async(self) -> None:
        """测试异步发布"""
        received = []

        async def async_handler(
            event_name: str, data: dict
        ) -> None:
            received.append(data)

        self.bus.subscribe_async("evt", async_handler)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                self.bus.emit_async(
                    "evt", {"async": True}
                )
            )
        finally:
            loop.close()

        assert len(received) == 1
