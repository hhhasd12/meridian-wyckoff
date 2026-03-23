"""滑动窗口限频器测试

测试内容：初始化、acquire限频行为、reset重置、滑动窗口过期、属性访问
"""

import asyncio
import time
from unittest.mock import patch

import pytest

from src.plugins.exchange_connector.rate_limiter import RateLimiter


class TestRateLimiterInit:
    """测试限频器初始化"""

    def test_default_params(self) -> None:
        """测试默认参数"""
        rl = RateLimiter()
        assert rl.max_requests == 1100
        assert rl.window_seconds == 60.0
        assert rl.current_usage == 0

    def test_custom_params(self) -> None:
        """测试自定义参数"""
        rl = RateLimiter(max_requests=10, window_seconds=5.0)
        assert rl.max_requests == 10
        assert rl.window_seconds == 5.0

    def test_repr(self) -> None:
        """测试repr输出"""
        rl = RateLimiter(max_requests=10, window_seconds=5.0)
        r = repr(rl)
        assert "max_requests=10" in r
        assert "window_seconds=5.0" in r
        assert "current_usage=0" in r


class TestRateLimiterAcquire:
    """测试acquire方法"""

    @pytest.mark.asyncio
    async def test_acquire_under_limit(self) -> None:
        """测试未达到限制时直接通过"""
        rl = RateLimiter(max_requests=5, window_seconds=60.0)
        await rl.acquire()
        assert rl.current_usage == 1

    @pytest.mark.asyncio
    async def test_acquire_multiple(self) -> None:
        """测试多次acquire累积计数"""
        rl = RateLimiter(max_requests=10, window_seconds=60.0)
        for _ in range(5):
            await rl.acquire()
        assert rl.current_usage == 5

    @pytest.mark.asyncio
    async def test_acquire_at_limit_waits(self) -> None:
        """测试达到限制时等待"""
        rl = RateLimiter(max_requests=3, window_seconds=0.1)

        # 填满窗口
        for _ in range(3):
            await rl.acquire()

        assert rl.current_usage == 3

        # 第4次应该等待窗口过期
        start = time.monotonic()
        await rl.acquire()
        elapsed = time.monotonic() - start

        # 应该等待了大约0.1秒（窗口大小）
        assert elapsed >= 0.05  # 宽松检查，避免CI环境时间抖动

    @pytest.mark.asyncio
    async def test_acquire_records_timestamp(self) -> None:
        """测试acquire记录时间戳"""
        rl = RateLimiter(max_requests=10, window_seconds=60.0)
        await rl.acquire()
        assert len(rl._timestamps) == 1


class TestRateLimiterSlidingWindow:
    """测试滑动窗口过期机制"""

    @pytest.mark.asyncio
    async def test_expired_timestamps_purged(self) -> None:
        """测试过期时间戳被清除"""
        rl = RateLimiter(max_requests=10, window_seconds=0.05)

        await rl.acquire()
        await rl.acquire()
        assert rl.current_usage == 2

        # 等待窗口过期
        await asyncio.sleep(0.1)
        assert rl.current_usage == 0

    @pytest.mark.asyncio
    async def test_partial_expiry(self) -> None:
        """测试部分过期（只有早期请求过期）"""
        rl = RateLimiter(max_requests=10, window_seconds=0.1)

        await rl.acquire()
        await asyncio.sleep(0.06)
        await rl.acquire()

        # 第一个快要过期但还没过期
        assert rl.current_usage >= 1

        # 等待第一个过期
        await asyncio.sleep(0.06)
        # 第一个应已过期，第二个还在
        assert rl.current_usage == 1

    def test_purge_expired_internal(self) -> None:
        """测试_purge_expired内部方法"""
        rl = RateLimiter(max_requests=10, window_seconds=60.0)

        # 手动插入过期时间戳
        now = time.monotonic()
        rl._timestamps.append(now - 120)  # 2分钟前
        rl._timestamps.append(now - 90)  # 1.5分钟前
        rl._timestamps.append(now - 30)  # 30秒前（未过期）

        rl._purge_expired(now)
        assert len(rl._timestamps) == 1


class TestRateLimiterReset:
    """测试reset方法"""

    @pytest.mark.asyncio
    async def test_reset_clears_all(self) -> None:
        """测试reset清除所有记录"""
        rl = RateLimiter(max_requests=10, window_seconds=60.0)

        for _ in range(5):
            await rl.acquire()
        assert rl.current_usage == 5

        rl.reset()
        assert rl.current_usage == 0
        assert len(rl._timestamps) == 0

    @pytest.mark.asyncio
    async def test_reset_allows_new_requests(self) -> None:
        """测试reset后可以继续请求"""
        rl = RateLimiter(max_requests=3, window_seconds=60.0)

        for _ in range(3):
            await rl.acquire()
        assert rl.current_usage == 3

        rl.reset()
        await rl.acquire()
        assert rl.current_usage == 1

    def test_reset_empty(self) -> None:
        """测试空状态reset"""
        rl = RateLimiter()
        rl.reset()  # 不应抛出异常
        assert rl.current_usage == 0


class TestRateLimiterProperties:
    """测试属性访问"""

    def test_max_requests_property(self) -> None:
        """测试max_requests属性"""
        rl = RateLimiter(max_requests=500)
        assert rl.max_requests == 500

    def test_window_seconds_property(self) -> None:
        """测试window_seconds属性"""
        rl = RateLimiter(window_seconds=30.0)
        assert rl.window_seconds == 30.0

    @pytest.mark.asyncio
    async def test_current_usage_reflects_state(self) -> None:
        """测试current_usage反映当前状态"""
        rl = RateLimiter(max_requests=10, window_seconds=60.0)
        assert rl.current_usage == 0

        await rl.acquire()
        assert rl.current_usage == 1

        await rl.acquire()
        assert rl.current_usage == 2

        rl.reset()
        assert rl.current_usage == 0


class TestRateLimiterConcurrency:
    """测试并发安全"""

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self) -> None:
        """测试并发acquire不超过限制"""
        rl = RateLimiter(max_requests=10, window_seconds=60.0)

        # 并发发送5个请求
        tasks = [rl.acquire() for _ in range(5)]
        await asyncio.gather(*tasks)

        assert rl.current_usage == 5
