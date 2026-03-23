"""滑动窗口限频器 - 防止超过交易所API速率限制

使用 collections.deque 存储请求时间戳，实现滑动窗口算法。
当窗口内请求数达到上限时，异步等待直到最早的请求过期。
"""

import asyncio
import logging
import time
from collections import deque
from typing import Deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """滑动窗口限频器

    通过维护一个时间戳队列，跟踪窗口期内的请求数量。
    当请求数达到 max_requests 时，计算需等待的时间并异步休眠。

    Args:
        max_requests: 窗口期内允许的最大请求数（默认1100，Binance限制1200/min）
        window_seconds: 滑动窗口大小（秒，默认60.0）
    """

    def __init__(
        self,
        max_requests: int = 1100,
        window_seconds: float = 60.0,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """异步等待直到可以发送请求

        清除过期时间戳后检查是否超限。
        超限时计算需等待的时间（最早时间戳到期时间），然后 asyncio.sleep。
        """
        async with self._lock:
            now = time.monotonic()
            self._purge_expired(now)

            if len(self._timestamps) >= self._max_requests:
                # 最早的请求时间戳 + 窗口大小 = 该请求过期时间
                earliest = self._timestamps[0]
                wait_time = earliest + self._window_seconds - now
                if wait_time > 0:
                    logger.warning(
                        "限频器: 达到上限 %d/%d，等待 %.2fs",
                        len(self._timestamps),
                        self._max_requests,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    # 等待后重新清除过期时间戳
                    now = time.monotonic()
                    self._purge_expired(now)

            self._timestamps.append(now)

    def _purge_expired(self, now: float) -> None:
        """清除窗口外的过期时间戳

        Args:
            now: 当前单调时钟时间
        """
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    @property
    def current_usage(self) -> int:
        """当前窗口内的请求数量"""
        self._purge_expired(time.monotonic())
        return len(self._timestamps)

    @property
    def max_requests(self) -> int:
        """最大请求数"""
        return self._max_requests

    @property
    def window_seconds(self) -> float:
        """窗口大小（秒）"""
        return self._window_seconds

    def reset(self) -> None:
        """重置限频器，清除所有请求记录

        用于测试或需要手动重置限频状态时。
        """
        self._timestamps.clear()

    def __repr__(self) -> str:
        return (
            f"RateLimiter(max_requests={self._max_requests}, "
            f"window_seconds={self._window_seconds}, "
            f"current_usage={self.current_usage})"
        )
