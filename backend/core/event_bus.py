from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subs: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subs[event_type].append(handler)
        logger.debug(f"订阅: {event_type} → {handler.__qualname__}")

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        try:
            self._subs[event_type].remove(handler)
        except ValueError:
            logger.warning(f"取消订阅失败，handler不存在: {event_type}")

    async def publish(self, event_type: str, data: Any = None) -> None:
        """串行执行所有handler，一个失败不影响其他"""
        for handler in self._subs.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"事件处理失败 [{event_type}]: {e}", exc_info=True)
