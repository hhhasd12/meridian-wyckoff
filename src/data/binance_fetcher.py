"""
Binance 数据获取模块
从 Binance 公共 API 获取加密货币历史数据，支持多时间周期

功能：
1. 获取 ETH/USDT 合约历史数据（支持现货和永续合约）
2. 支持多时间周期（1m, 5m, 15m, 30m, 1h, 4h, 1d 等）
3. 数据清洗和格式化
4. 错误处理和重试机制
5. 数据缓存支持

设计原则：
1. 轻量级：不依赖 CCXT，直接调用 Binance REST API
2. 异步高性能：使用 aiohttp 并发请求
3. 数据完整性：验证数据质量，处理缺失值
4. 容错性：网络故障时自动重试，降级处理
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import aiohttp
import pandas as pd

logger = logging.getLogger(__name__)


class BinanceInterval(Enum):
    """Binance K线时间间隔枚举"""

    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_8 = "8h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    DAY_3 = "3d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


class BinanceSymbol(Enum):
    """Binance 交易对枚举"""

    BTC_USDT = "BTCUSDT"
    ETH_USDT = "ETHUSDT"
    BNB_USDT = "BNBUSDT"
    SOL_USDT = "SOLUSDT"
    XRP_USDT = "XRPUSDT"


class BinanceFetcher:
    """
    Binance 数据获取器

    支持功能：
    1. 获取历史 K线数据
    2. 多时间周期数据同步
    3. 数据质量验证
    4. 自动重试和错误处理
    5. 简单的内存缓存
    """

    BASE_URL = "https://api.binance.com"

    def __init__(self, max_retries: int = 3, request_timeout: int = 30, proxy: Optional[str] = None):
        """
        初始化 Binance 数据获取器

        Args:
            max_retries: 最大重试次数
            request_timeout: 请求超时时间（秒）
            proxy: HTTP/HTTPS 代理地址，例如 "http://127.0.0.1:7890"
        """
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self.proxy = proxy or self._detect_proxy()
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: dict[str, pd.DataFrame] = {}
        self.cache_ttl: dict[str, float] = {}
        self.default_cache_ttl = 300  # 5分钟

    @staticmethod
    def _detect_proxy() -> Optional[str]:
        """从环境变量自动检测代理配置"""
        import os
        return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or \
               os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    async def connect(self):
        """创建 aiohttp 会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
            if self.proxy:
                logger.info(f"BinanceFetcher 会话已创建（代理: {self.proxy}）")
            else:
                logger.info("BinanceFetcher 会话已创建")

    async def close(self):
        """关闭 aiohttp 会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("BinanceFetcher 会话已关闭")

    def _get_cache_key(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> str:
        """生成缓存键"""
        start_str = str(start_time) if start_time else "none"
        end_str = str(end_time) if end_time else "none"
        return f"{symbol}_{interval}_{start_str}_{end_str}_{limit}"

    def _get_cached_data(self, cache_key: str) -> Optional[pd.DataFrame]:
        """从缓存获取数据"""
        if cache_key in self.cache:
            cached_time = self.cache_ttl.get(cache_key, 0)
            if time.time() - cached_time < self.default_cache_ttl:
                logger.debug(f"使用缓存数据: {cache_key}")
                return self.cache[cache_key]
            # 缓存过期，清理
            del self.cache[cache_key]
            del self.cache_ttl[cache_key]
        return None

    def _set_cached_data(self, cache_key: str, data: pd.DataFrame):
        """缓存数据"""
        self.cache[cache_key] = data.copy()
        self.cache_ttl[cache_key] = time.time()
        logger.debug(f"数据已缓存: {cache_key}")

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        获取 Binance K线数据

        Args:
            symbol: 交易对，如 "ETHUSDT"
            interval: 时间间隔，如 "1h"
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            limit: 最大数据条数（默认1000，最大1000）

        Returns:
            DataFrame 包含以下列：
            - timestamp: 时间戳（datetime）
            - open: 开盘价
            - high: 最高价
            - low: 最低价
            - close: 收盘价
            - volume: 成交量
            - quote_asset_volume: 成交额
            - number_of_trades: 成交笔数
            - taker_buy_base_volume: 主动买入成交量
            - taker_buy_quote_volume: 主动买入成交额
        """
        # 生成缓存键
        start_ts = int(start_time.timestamp() * 1000) if start_time else None
        end_ts = int(end_time.timestamp() * 1000) if end_time else None
        cache_key = self._get_cache_key(symbol, interval, start_ts, end_ts, limit)

        # 检查缓存
        cached_data = self._get_cached_data(cache_key)
        if cached_data is not None:
            return cached_data

        # 确保会话已连接
        await self.connect()

        # 构建请求参数
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),  # Binance 最大限制1000
        }

        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)

        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                url = f"{self.BASE_URL}/api/v3/klines"
                async with self.session.get(url, params=params, proxy=self.proxy) as response:
                    if response.status == 200:
                        data = await response.json()

                        if not data:
                            logger.warning(f"无数据返回: {symbol} {interval}")
                            return pd.DataFrame()

                        # 解析数据
                        df = self._parse_klines_data(data, symbol, interval)

                        # 缓存数据
                        self._set_cached_data(cache_key, df)

                        logger.info(
                            f"获取数据成功: {symbol} {interval}, 数据量: {len(df)}"
                        )
                        return df

                    if response.status == 429:
                        # 速率限制，等待后重试
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"速率限制，等待 {retry_after} 秒后重试")
                        await asyncio.sleep(retry_after)
                        continue

                    error_text = await response.text()
                    logger.error(f"请求失败: {response.status}, 错误: {error_text}")
                    if attempt < self.max_retries - 1:
                        wait_time = 2**attempt  # 指数退避
                        logger.info(f"等待 {wait_time} 秒后重试")
                        await asyncio.sleep(wait_time)
                    else:
                        raise Exception(
                            f"API请求失败: {response.status} - {error_text}"
                        )

            except asyncio.TimeoutError:
                logger.warning(f"请求超时，尝试 {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise Exception("请求超时，已达最大重试次数")

            except Exception:
                logger.exception("获取数据异常")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise

        # 所有重试都失败，返回空DataFrame
        logger.error(f"所有重试都失败: {symbol} {interval}")
        return pd.DataFrame()

    def _parse_klines_data(
        self, data: list[list[Any]], symbol: str, interval: str
    ) -> pd.DataFrame:
        """
        解析 Binance K线数据

        Binance K线数据格式:
        [
            [
                1499040000000,      # 开盘时间
                "0.01634790",       # 开盘价
                "0.80000000",       # 最高价
                "0.01575800",       # 最低价
                "0.01577100",       # 收盘价
                "148976.11427815",  # 成交量
                1499644799999,      # 收盘时间
                "2434.19055334",    # 成交额
                308,                # 成交笔数
                "1756.87402397",    # 主动买入成交量
                "28.46694368",      # 主动买入成交额
                "17928899.62484339" # 忽略
            ]
        ]
        """
        columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "ignore",
        ]

        df = pd.DataFrame(data, columns=columns)

        # 转换数据类型
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")

        numeric_cols = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]

        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["number_of_trades"] = pd.to_numeric(df["number_of_trades"], errors="coerce")

        # 设置时间索引
        df.set_index("timestamp", inplace=True)

        # 排序索引
        df.sort_index(inplace=True)

        # 添加元数据
        df.attrs["symbol"] = symbol
        df.attrs["interval"] = interval
        df.attrs["data_source"] = "binance"
        df.attrs["fetch_time"] = datetime.now()

        return df

    async def fetch_multiple_intervals(
        self,
        symbol: str,
        intervals: list[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> dict[str, pd.DataFrame]:
        """
        并发获取多时间周期数据

        Args:
            symbol: 交易对
            intervals: 时间间隔列表
            start_time: 开始时间
            end_time: 结束时间
            limit: 每个时间周期数据量

        Returns:
            字典: {interval: DataFrame}
        """
        tasks = []
        for interval in intervals:
            task = self.fetch_klines(symbol, interval, start_time, end_time, limit)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        data_dict = {}
        for interval, result in zip(intervals, results):
            if isinstance(result, Exception):
                logger.error(f"获取 {symbol} {interval} 数据失败: {result}")
                data_dict[interval] = pd.DataFrame()
            else:
                data_dict[interval] = result

        return data_dict

    async def fetch_eth_data(
        self,
        intervals: Optional[list[str]] = None,
        days_back: int = 30,
        limit_per_interval: int = 1000,
    ) -> dict[str, pd.DataFrame]:
        """
        获取 ETH/USDT 数据（便捷方法）

        Args:
            intervals: 时间间隔列表，默认 ["1h", "4h", "1d"]
            days_back: 回溯天数
            limit_per_interval: 每个间隔数据量

        Returns:
            字典: {interval: DataFrame}
        """
        if intervals is None:
            intervals = ["1h", "4h", "1d", "15m", "5m"]

        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_back)

        logger.info(f"获取 ETH/USDT 数据: {days_back}天, 时间周期: {intervals}")

        return await self.fetch_multiple_intervals(
            symbol="ETHUSDT",
            intervals=intervals,
            start_time=start_time,
            end_time=end_time,
            limit=limit_per_interval,
        )

    def validate_data_quality(
        self, df: pd.DataFrame, symbol: str, interval: str
    ) -> dict[str, Any]:
        """
        验证数据质量

        Returns:
            包含验证结果的字典
        """
        if df.empty:
            return {
                "is_valid": False,
                "issues": ["数据为空"],
                "metrics": {},
                "symbol": symbol,
                "interval": interval,
            }

        issues = []
        metrics = {
            "data_points": len(df),
            "date_range": (df.index.min(), df.index.max()),
            "missing_values": df.isnull().sum().to_dict(),
        }

        # 检查缺失值
        missing_counts = df.isnull().sum()
        missing_columns = missing_counts[missing_counts > 0]
        if not missing_columns.empty:
            issues.append(f"缺失值列: {missing_columns.to_dict()}")

        # 检查零值或负值
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if col in df.columns:
                zero_or_negative = (df[col] <= 0).sum()
                if zero_or_negative > 0:
                    issues.append(f"{col} 有 {zero_or_negative} 个零值或负值")

        # 检查价格合理性
        if all(col in df.columns for col in ["high", "low"]):
            invalid_high_low = (df["high"] < df["low"]).sum()
            if invalid_high_low > 0:
                issues.append(f"high < low 的行数: {invalid_high_low}")

        # 检查时间间隔一致性
        if len(df) > 1:
            time_diffs = df.index.to_series().diff().dropna()
            if not time_diffs.empty:
                avg_gap = time_diffs.mean().total_seconds()
                max_gap = time_diffs.max().total_seconds()
                metrics["avg_time_gap_seconds"] = avg_gap
                metrics["max_time_gap_seconds"] = max_gap

                # 根据间隔检查最大间隔
                interval_seconds = self._get_interval_seconds(interval)
                if interval_seconds and max_gap > interval_seconds * 3:
                    issues.append(
                        f"最大时间间隔异常: {max_gap:.0f}秒 > {interval_seconds * 3}秒"
                    )

        is_valid = len(issues) == 0

        return {
            "is_valid": is_valid,
            "issues": issues,
            "metrics": metrics,
            "symbol": symbol,
            "interval": interval,
        }

    def _get_interval_seconds(self, interval: str) -> Optional[int]:
        """获取时间间隔秒数"""
        interval_map = {
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "2h": 7200,
            "4h": 14400,
            "6h": 21600,
            "8h": 28800,
            "12h": 43200,
            "1d": 86400,
            "3d": 259200,
            "1w": 604800,
            "1M": 2592000,  # 近似值
        }
        return interval_map.get(interval)

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.cache_ttl.clear()
        logger.info("缓存已清空")


async def main_example():
    """使用示例"""


    async with BinanceFetcher(max_retries=2, request_timeout=10) as fetcher:
        # 示例1: 获取单时间周期数据
        eth_1h = await fetcher.fetch_klines(symbol="ETHUSDT", interval="1h", limit=100)

        if not eth_1h.empty:

            # 验证数据质量
            validation = fetcher.validate_data_quality(eth_1h, "ETHUSDT", "1h")
            if validation["issues"]:
                pass
        else:
            pass

        # 示例2: 获取多时间周期数据
        intervals = ["15m", "1h", "4h"]
        eth_multi = await fetcher.fetch_multiple_intervals(
            symbol="ETHUSDT", intervals=intervals, limit=200
        )

        for interval, df in eth_multi.items():
            if not df.empty:
                pass
            else:
                pass

        # 示例3: 使用便捷方法获取ETH数据
        eth_data = await fetcher.fetch_eth_data(
            intervals=["5m", "15m", "1h", "4h"], days_back=7, limit_per_interval=500
        )

        for interval, df in eth_data.items():
            if not df.empty:
                pass



if __name__ == "__main__":
    # Windows 事件循环修复
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 运行示例
    try:
        asyncio.run(main_example())
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
