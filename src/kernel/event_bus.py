"""事件总线 - 插件间解耦通信机制

EventBus 替代硬编码的模块间 import，实现发布-订阅模式。
插件通过 EventBus 发布和订阅事件，无需知道对方的存在。

设计要点：
1. 同步事件分发（保证处理顺序）
2. 支持异步事件分发（asyncio 兼容）
3. 优先级排序（HIGH > NORMAL > LOW）
4. 错误隔离 — 单个订阅者异常不影响其他订阅者
5. 通配符订阅 — 支持 "plugin.*" 模式匹配

参考：VCP Plugin.js 中的事件机制
"""

import asyncio
import fnmatch
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from src.kernel.types import EventPriority

logger = logging.getLogger(__name__)

# 事件回调类型：接收 (event_name, event_data) 两个参数
EventHandler = Callable[[str, Dict[str, Any]], None]
AsyncEventHandler = Callable[[str, Dict[str, Any]], Any]


@dataclass
class Subscription:
    """事件订阅记录

    Attributes:
        event_pattern: 事件名称或通配符模式
        handler: 回调函数
        priority: 处理优先级
        subscriber_name: 订阅者名称（用于日志和调试）
        is_async: 是否为异步处理器
    """

    event_pattern: str
    handler: Any  # EventHandler 或 AsyncEventHandler
    priority: EventPriority = EventPriority.NORMAL
    subscriber_name: str = ""
    is_async: bool = False


@dataclass
class EventRecord:
    """事件记录（用于调试和监控）

    Attributes:
        event_name: 事件名称
        data: 事件数据
        timestamp: 发布时间戳
        publisher: 发布者名称
        handler_count: 处理器数量
        errors: 处理过程中的错误列表
    """

    event_name: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    publisher: str = ""
    handler_count: int = 0
    errors: List[str] = field(default_factory=list)


class EventBus:
    """事件总线 — 插件间解耦通信的核心组件

    提供发布-订阅模式的事件系统，支持：
    - 精确匹配和通配符匹配
    - 优先级排序
    - 同步和异步事件分发
    - 错误隔离
    - 事件历史记录（可选）

    Example:
        >>> bus = EventBus()
        >>> bus.subscribe("market.regime_changed", handler, priority=EventPriority.HIGH)
        >>> bus.emit("market.regime_changed", {"regime": "TRENDING"})
    """

    def __init__(
        self,
        max_history: int = 1000,
        enable_history: bool = False,
    ) -> None:
        """初始化事件总线

        Args:
            max_history: 事件历史记录最大条数
            enable_history: 是否启用事件历史记录
        """
        # 精确匹配的订阅：event_name -> [Subscription]
        self._exact_subscriptions: Dict[str, List[Subscription]] = {}
        # 通配符模式的订阅：pattern -> [Subscription]
        self._pattern_subscriptions: List[Subscription] = []
        # 事件历史记录
        self._history: List[EventRecord] = []
        self._max_history = max_history
        self._enable_history = enable_history
        # 统计信息
        self._emit_count: int = 0
        self._error_count: int = 0
        # 已暂停的事件名称集合
        self._paused_events: Set[str] = set()

    def subscribe(
        self,
        event_pattern: str,
        handler: EventHandler,
        priority: EventPriority = EventPriority.NORMAL,
        subscriber_name: str = "",
    ) -> None:
        """订阅事件

        Args:
            event_pattern: 事件名称或通配符模式（如 "plugin.*"）
            handler: 事件处理回调函数
            priority: 处理优先级
            subscriber_name: 订阅者名称（用于日志）

        Example:
            >>> bus.subscribe("market.regime_changed", on_regime_change)
            >>> bus.subscribe("plugin.*", on_any_plugin_event)
        """
        sub = Subscription(
            event_pattern=event_pattern,
            handler=handler,
            priority=priority,
            subscriber_name=subscriber_name,
            is_async=False,
        )

        if self._is_pattern(event_pattern):
            self._pattern_subscriptions.append(sub)
            self._sort_pattern_subscriptions()
            logger.debug(
                "通配符订阅: pattern=%s, subscriber=%s",
                event_pattern,
                subscriber_name,
            )
        else:
            if event_pattern not in self._exact_subscriptions:
                self._exact_subscriptions[event_pattern] = []
            self._exact_subscriptions[event_pattern].append(sub)
            self._sort_exact_subscriptions(event_pattern)
            logger.debug(
                "精确订阅: event=%s, subscriber=%s",
                event_pattern,
                subscriber_name,
            )

    def subscribe_async(
        self,
        event_pattern: str,
        handler: AsyncEventHandler,
        priority: EventPriority = EventPriority.NORMAL,
        subscriber_name: str = "",
    ) -> None:
        """订阅事件（异步处理器）

        Args:
            event_pattern: 事件名称或通配符模式
            handler: 异步事件处理回调函数
            priority: 处理优先级
            subscriber_name: 订阅者名称
        """
        sub = Subscription(
            event_pattern=event_pattern,
            handler=handler,
            priority=priority,
            subscriber_name=subscriber_name,
            is_async=True,
        )

        if self._is_pattern(event_pattern):
            self._pattern_subscriptions.append(sub)
            self._sort_pattern_subscriptions()
        else:
            if event_pattern not in self._exact_subscriptions:
                self._exact_subscriptions[event_pattern] = []
            self._exact_subscriptions[event_pattern].append(sub)
            self._sort_exact_subscriptions(event_pattern)

    def unsubscribe(
        self,
        event_pattern: str,
        handler: EventHandler,
    ) -> bool:
        """取消订阅

        Args:
            event_pattern: 事件名称或通配符模式
            handler: 要取消的回调函数

        Returns:
            是否成功取消订阅
        """
        removed = False

        if self._is_pattern(event_pattern):
            before = len(self._pattern_subscriptions)
            self._pattern_subscriptions = [
                s
                for s in self._pattern_subscriptions
                if not (s.event_pattern == event_pattern and s.handler is handler)
            ]
            removed = len(self._pattern_subscriptions) < before
        else:
            if event_pattern in self._exact_subscriptions:
                before = len(self._exact_subscriptions[event_pattern])
                self._exact_subscriptions[event_pattern] = [
                    s
                    for s in self._exact_subscriptions[event_pattern]
                    if s.handler is not handler
                ]
                removed = len(self._exact_subscriptions[event_pattern]) < before
                # 清理空列表
                if not self._exact_subscriptions[event_pattern]:
                    del self._exact_subscriptions[event_pattern]

        if removed:
            logger.debug("取消订阅: pattern=%s", event_pattern)
        return removed

    def unsubscribe_all(self, subscriber_name: str) -> int:
        """取消指定订阅者的所有订阅

        Args:
            subscriber_name: 订阅者名称

        Returns:
            取消的订阅数量
        """
        count = 0

        # 清理精确匹配订阅
        for event_name in list(self._exact_subscriptions.keys()):
            before = len(self._exact_subscriptions[event_name])
            self._exact_subscriptions[event_name] = [
                s
                for s in self._exact_subscriptions[event_name]
                if s.subscriber_name != subscriber_name
            ]
            count += before - len(self._exact_subscriptions[event_name])
            if not self._exact_subscriptions[event_name]:
                del self._exact_subscriptions[event_name]

        # 清理通配符订阅
        before = len(self._pattern_subscriptions)
        self._pattern_subscriptions = [
            s
            for s in self._pattern_subscriptions
            if s.subscriber_name != subscriber_name
        ]
        count += before - len(self._pattern_subscriptions)

        if count > 0:
            logger.debug(
                "批量取消订阅: subscriber=%s, count=%d",
                subscriber_name,
                count,
            )
        return count

    def emit(
        self,
        event_name: str,
        data: Optional[Dict[str, Any]] = None,
        publisher: str = "",
    ) -> int:
        """同步发布事件

        按优先级顺序调用所有匹配的处理器。
        单个处理器异常不会阻止其他处理器执行。

        Args:
            event_name: 事件名称
            data: 事件数据
            publisher: 发布者名称

        Returns:
            成功处理的处理器数量
        """
        if event_name in self._paused_events:
            logger.debug("事件已暂停，跳过: %s", event_name)
            return 0

        if data is None:
            data = {}

        self._emit_count += 1
        handlers = self._get_matching_handlers(event_name)
        success_count = 0
        errors: List[str] = []

        for sub in handlers:
            try:
                if sub.is_async:
                    # 异步处理器：从同步上下文中执行
                    try:
                        loop = asyncio.get_running_loop()
                        # 有运行中的 loop，创建 task 调度执行
                        # 注意：task 中的异常通过 done_callback 捕获记录
                        task = loop.create_task(sub.handler(event_name, data))
                        task.add_done_callback(
                            lambda t, s=sub: self._handle_async_task_result(
                                t, event_name, s.subscriber_name, errors
                            )
                        )
                    except RuntimeError:
                        # 没有运行中的 loop，新建 loop 同步执行
                        asyncio.run(sub.handler(event_name, data))
                    success_count += 1
                    continue
                sub.handler(event_name, data)
                success_count += 1
            except Exception as e:
                self._error_count += 1
                error_msg = (
                    f"事件处理器异常: event={event_name}, "
                    f"subscriber={sub.subscriber_name}, "
                    f"error={type(e).__name__}: {e}"
                )
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)

        # 记录事件历史
        if self._enable_history:
            self._record_event(event_name, data, publisher, len(handlers), errors)

        return success_count

    async def emit_async(
        self,
        event_name: str,
        data: Optional[Dict[str, Any]] = None,
        publisher: str = "",
    ) -> int:
        """异步发布事件

        支持同步和异步处理器混合调用。

        Args:
            event_name: 事件名称
            data: 事件数据
            publisher: 发布者名称

        Returns:
            成功处理的处理器数量
        """
        if event_name in self._paused_events:
            return 0

        if data is None:
            data = {}

        self._emit_count += 1
        handlers = self._get_matching_handlers(event_name)
        success_count = 0
        errors: List[str] = []

        for sub in handlers:
            try:
                if sub.is_async:
                    await sub.handler(event_name, data)
                else:
                    sub.handler(event_name, data)
                success_count += 1
            except Exception as e:
                self._error_count += 1
                error_msg = (
                    f"事件处理器异常: event={event_name}, "
                    f"subscriber={sub.subscriber_name}, "
                    f"error={type(e).__name__}: {e}"
                )
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)

        if self._enable_history:
            self._record_event(event_name, data, publisher, len(handlers), errors)

        return success_count

    def pause_event(self, event_name: str) -> None:
        """暂停指定事件的分发

        Args:
            event_name: 要暂停的事件名称
        """
        self._paused_events.add(event_name)
        logger.info("事件已暂停: %s", event_name)

    def resume_event(self, event_name: str) -> None:
        """恢复指定事件的分发

        Args:
            event_name: 要恢复的事件名称
        """
        self._paused_events.discard(event_name)
        logger.info("事件已恢复: %s", event_name)

    def get_subscribers(self, event_name: str) -> List[str]:
        """获取指定事件的所有订阅者名称

        Args:
            event_name: 事件名称

        Returns:
            订阅者名称列表
        """
        handlers = self._get_matching_handlers(event_name)
        return [s.subscriber_name for s in handlers]

    def get_stats(self) -> Dict[str, Any]:
        """获取事件总线统计信息

        Returns:
            包含订阅数、发布数、错误数等统计信息的字典
        """
        exact_count = sum(len(subs) for subs in self._exact_subscriptions.values())
        return {
            "exact_subscriptions": exact_count,
            "pattern_subscriptions": len(self._pattern_subscriptions),
            "total_subscriptions": (exact_count + len(self._pattern_subscriptions)),
            "emit_count": self._emit_count,
            "error_count": self._error_count,
            "paused_events": list(self._paused_events),
            "registered_events": list(self._exact_subscriptions.keys()),
            "history_size": len(self._history),
        }

    def get_history(self, limit: int = 100) -> List[EventRecord]:
        """获取事件历史记录

        Args:
            limit: 返回的最大记录数

        Returns:
            事件记录列表（最新的在前）
        """
        return list(reversed(self._history[-limit:]))

    def clear(self) -> None:
        """清除所有订阅和历史记录"""
        self._exact_subscriptions.clear()
        self._pattern_subscriptions.clear()
        self._history.clear()
        self._paused_events.clear()
        self._emit_count = 0
        self._error_count = 0
        logger.info("事件总线已清空")

    # ---- 内部方法 ----

    def _handle_async_task_result(
        self,
        task: "asyncio.Task[Any]",
        event_name: str,
        subscriber_name: str,
        errors: List[str],
    ) -> None:
        """处理异步任务的结果，捕获并记录异常

        当 create_task() 调度的异步处理器完成时调用。
        如果任务抛出异常，记录错误但不影响其他处理器。

        Args:
            task: 已完成的异步任务
            event_name: 事件名称
            subscriber_name: 订阅者名称
            errors: 错误列表（用于历史记录）
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._error_count += 1
            error_msg = (
                f"异步事件处理器异常: event={event_name}, "
                f"subscriber={subscriber_name}, "
                f"error={type(exc).__name__}: {exc}"
            )
            errors.append(error_msg)
            logger.error(error_msg)

    def _is_pattern(self, event_pattern: str) -> bool:
        """判断是否为通配符模式

        Args:
            event_pattern: 事件名称或模式

        Returns:
            是否包含通配符字符
        """
        return "*" in event_pattern or "?" in event_pattern

    def _get_matching_handlers(self, event_name: str) -> List[Subscription]:
        """获取匹配指定事件名的所有处理器（已按优先级排序）

        使用 heapq.merge 合并已排序的精确匹配和通配符匹配列表，
        避免每次调用都对合并后的列表重新排序。

        Args:
            event_name: 事件名称

        Returns:
            匹配的订阅列表，按优先级排序
        """
        # 精确匹配（已按优先级排序）
        exact = self._exact_subscriptions.get(event_name, [])

        # 通配符匹配（_pattern_subscriptions 已按优先级排序）
        pattern_matches = [
            sub
            for sub in self._pattern_subscriptions
            if fnmatch.fnmatch(event_name, sub.event_pattern)
        ]

        # 使用 heapq.merge 合并两个已排序列表，避免重新排序
        if not exact:
            return pattern_matches
        if not pattern_matches:
            return list(exact)

        return list(
            heapq.merge(
                exact,
                pattern_matches,
                key=lambda s: s.priority.value,
            )
        )

    def _sort_exact_subscriptions(self, event_name: str) -> None:
        """对指定事件的精确匹配订阅按优先级排序"""
        if event_name in self._exact_subscriptions:
            self._exact_subscriptions[event_name].sort(key=lambda s: s.priority.value)

    def _sort_pattern_subscriptions(self) -> None:
        """对通配符订阅按优先级排序"""
        self._pattern_subscriptions.sort(key=lambda s: s.priority.value)

    def _record_event(
        self,
        event_name: str,
        data: Dict[str, Any],
        publisher: str,
        handler_count: int,
        errors: List[str],
    ) -> None:
        """记录事件到历史

        Args:
            event_name: 事件名称
            data: 事件数据
            publisher: 发布者名称
            handler_count: 处理器数量
            errors: 错误列表
        """
        record = EventRecord(
            event_name=event_name,
            data=data,
            publisher=publisher,
            handler_count=handler_count,
            errors=errors,
        )
        self._history.append(record)

        # 限制历史记录大小
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
