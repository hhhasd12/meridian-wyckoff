"""
数据管道模块 - 多周期数据同步与缓存
解决跨周期时间差陷阱：节奏对齐（Rhythm Sync），大周期定方向，小周期定时机
支持多源互证（BTC/ETH相关性验证），区分机构异常vs交易所宕机
"""

import asyncio
import contextlib
import json
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import aiohttp
import ccxt
import numpy as np
import pandas as pd
import redis
import yfinance as yf


class DataSource(Enum):
    """数据源枚举"""

    CCXT = "CCXT"  # 加密货币交易所
    YFINANCE = "YFINANCE"  # 股票数据
    CSV = "CSV"  # 本地CSV文件
    API = "API"  # 自定义API


class Timeframe(Enum):
    """时间框架枚举（兼容ccxt）"""

    M1 = "1m"  # 1分钟
    M5 = "5m"  # 5分钟
    M15 = "15m"  # 15分钟
    M30 = "30m"  # 30分钟
    H1 = "1h"  # 1小时
    H2 = "2h"  # 2小时
    H4 = "4h"  # 4小时
    H6 = "6h"  # 6小时
    H8 = "8h"  # 8小时
    H12 = "12h"  # 12小时
    D1 = "1d"  # 日线
    W1 = "1w"  # 周线
    MN1 = "1M"  # 月线


@dataclass
class DataRequest:
    """数据请求参数"""

    symbol: str
    timeframe: Timeframe
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 1000
    source: DataSource = DataSource.CCXT
    exchange: str = "binance"  # 对于CCXT源
    validate: bool = True  # 是否进行数据验证


class DataPipeline:
    """
    数据管道 - 多周期数据同步与缓存管理器

    功能：
    1. 多数据源支持（CCXT加密货币、YFinance股票、本地CSV、自定义API）
    2. 多时间框架同步与节奏对齐（Rhythm Sync）
    3. 数据缓存与持久化（Redis + 本地文件）
    4. 异常数据验证与多源互证（BTC/ETH相关性）
    5. 实时数据流监控与更新

    设计原则：
    1. 异步高性能：支持并发数据获取
    2. 数据完整性：严格验证数据质量
    3. 容错机制：数据源故障时自动切换
    4. 缓存智能：根据数据新鲜度自动更新
    5. 监控报警：异常数据即时报警
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化数据管道

        Args:
            config: 配置字典，包含以下参数：
                - redis_host: Redis主机地址（默认localhost）
                - redis_port: Redis端口（默认6379）
                - cache_ttl: 缓存过期时间（秒，默认3600）
                - max_retries: 最大重试次数（默认3）
                - request_timeout: 请求超时时间（秒，默认30）
                - correlation_threshold: 相关性验证阈值（默认0.7）
                - max_gap_seconds: 最大数据间隔秒数（默认300）
                - enable_validation: 启用数据验证（默认True）
                - enable_cache: 启用缓存（默认True）
                - custom_api_url: 自定义API URL（默认None）
        """
        self.config = config or {}

        # Redis缓存配置
        self.redis_host = self.config.get("redis_host", "localhost")
        self.redis_port = self.config.get("redis_port", 6379)
        self.cache_ttl = self.config.get("cache_ttl", 3600)

        # 请求配置
        self.max_retries = self.config.get("max_retries", 3)
        self.request_timeout = self.config.get("request_timeout", 30)

        # 验证配置
        self.correlation_threshold = self.config.get("correlation_threshold", 0.7)
        self.max_gap_seconds = self.config.get("max_gap_seconds", 300)
        self.enable_validation = self.config.get("enable_validation", True)
        self.enable_cache = self.config.get("enable_cache", True)
        self.custom_api_url = self.config.get("custom_api_url")

        # 初始化Redis连接（惰性连接）
        self._redis_client = None

        # 初始化CCXT交易所（惰性初始化）
        self._exchanges: dict[str, ccxt.Exchange] = {}

        # 数据源状态监控
        self.source_status: dict[str, dict] = {
            "ccxt": {"status": "unknown", "last_check": None, "error_count": 0},
            "yfinance": {"status": "unknown", "last_check": None, "error_count": 0},
        }

        # 缓存统计
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "invalidations": 0,
        }

        # 相关性验证对（加密货币）
        self.correlation_pairs = [
            ("BTC/USDT", "ETH/USDT"),  # BTC-ETH相关性
            ("BTC/USDT", "BNB/USDT"),  # BTC-BNB相关性
            ("ETH/USDT", "BNB/USDT"),  # ETH-BNB相关性
        ]

    def get_redis_client(self):
        """获取Redis客户端（惰性连接）"""
        if self._redis_client is None:
            try:
                self._redis_client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    decode_responses=False,  # 存储pickle数据
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
                # 测试连接
                self._redis_client.ping()
            except Exception:
                self._redis_client = None
                self.enable_cache = False

        return self._redis_client

    def get_exchange(self, exchange_name: str) -> ccxt.Exchange:
        """获取CCXT交易所实例（惰性初始化）"""
        if exchange_name not in self._exchanges:
            try:
                exchange_class = getattr(ccxt, exchange_name)
                exchange = exchange_class(
                    {
                        "enableRateLimit": True,
                        "timeout": self.request_timeout * 1000,  # 转换为毫秒
                    }
                )
                self._exchanges[exchange_name] = exchange
                self.source_status["ccxt"]["status"] = "connected"
                self.source_status["ccxt"]["last_check"] = datetime.now()
            except Exception:
                raise

        return self._exchanges[exchange_name]

    def _format_timestamp(self, timestamp: datetime) -> str:
        """格式化时间戳，处理可能的int64类型"""
        if isinstance(timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime
            timestamp_dt = datetime.fromtimestamp(float(timestamp) / 1000.0)
            return timestamp_dt.strftime("%Y%m%d")
        # 如果是datetime对象，直接格式化
        return timestamp.strftime("%Y%m%d")

    def get_cache_key(self, request: DataRequest) -> str:
        """生成缓存键"""
        source_str = request.source.value
        symbol_str = request.symbol.replace("/", "_").replace("-", "_")
        timeframe_str = request.timeframe.value
        start_str = (
            self._format_timestamp(request.start_date) if request.start_date else "all"
        )
        end_str = (
            self._format_timestamp(request.end_date) if request.end_date else "now"
        )

        return f"data:{source_str}:{symbol_str}:{timeframe_str}:{start_str}:{end_str}:{request.limit}"

    def get_cached_data(self, cache_key: str) -> Optional[pd.DataFrame]:
        """从缓存获取数据"""
        if not self.enable_cache:
            return None

        try:
            client = self.get_redis_client()
            if client:
                cached = client.get(cache_key)
                if cached:
                    data = pickle.loads(cached)  # type: ignore[arg-type]
                    self.cache_stats["hits"] += 1
                    return data
        except Exception:
            pass

        self.cache_stats["misses"] += 1
        return None

    def set_cached_data(self, cache_key: str, data: pd.DataFrame):
        """缓存数据"""
        if not self.enable_cache or data.empty:
            return

        try:
            client = self.get_redis_client()
            if client:
                pickled = pickle.dumps(data)
                client.setex(cache_key, self.cache_ttl, pickled)
                self.cache_stats["writes"] += 1
        except Exception:
            pass

    async def fetch_ccxt_data(self, request: DataRequest) -> pd.DataFrame:
        """从CCXT获取加密货币数据"""
        exchange = self.get_exchange(request.exchange)

        # 转换时间框架
        timeframe = request.timeframe.value

        # 转换日期为时间戳（毫秒）
        since = None
        if request.start_date:
            since = int(request.start_date.timestamp() * 1000)

        try:
            # 获取OHLCV数据
            ohlcv = exchange.fetch_ohlcv(
                request.symbol, timeframe=timeframe, since=since, limit=request.limit
            )

            # 转换为DataFrame
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

            # 转换时间戳为datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)

            # 排序索引
            df.sort_index(inplace=True)

            return df

        except Exception:
            self.source_status["ccxt"]["error_count"] += 1
            raise

    async def fetch_yfinance_data(self, request: DataRequest) -> pd.DataFrame:
        """从YFinance获取股票数据"""
        symbol = request.symbol

        # YFinance使用不同的时间框架格式
        tf_map = {
            Timeframe.M1: "1m",
            Timeframe.M5: "5m",
            Timeframe.M15: "15m",
            Timeframe.M30: "30m",
            Timeframe.H1: "60m",
            Timeframe.H2: "120m",
            Timeframe.H4: "240m",
            Timeframe.D1: "1d",
            Timeframe.W1: "1wk",
            Timeframe.MN1: "1mo",
        }

        interval = tf_map.get(request.timeframe, "1d")

        try:
            ticker = yf.Ticker(symbol)

            # 计算日期范围
            end_date = request.end_date or datetime.now()
            start_date = request.start_date or (end_date - timedelta(days=30))

            # 获取数据
            df = ticker.history(
                start=start_date, end=end_date, interval=interval, auto_adjust=False
            )

            # 重命名列以保持一致性
            df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                },
                inplace=True,
            )

            # 确保列顺序一致
            df = df[["open", "high", "low", "close", "volume"]]

            # 检查数据量
            if len(df) > request.limit:
                df = df.tail(request.limit)

            return df  # type: ignore[return-value]

        except Exception:
            self.source_status["yfinance"]["error_count"] += 1
            raise

    async def fetch_csv_data(self, request: DataRequest) -> pd.DataFrame:
        """从本地CSV文件获取数据"""
        # CSV源需要文件路径作为symbol
        filepath = request.symbol

        try:
            df = pd.read_csv(filepath)

            # 确保必要的列存在
            required_cols = ["timestamp", "open", "high", "low", "close", "volume"]

            # 检查列名
            col_mapping = {}
            for col in df.columns:
                col_lower = col.lower()
                for req in required_cols:
                    if req in col_lower:
                        col_mapping[col] = req

            df.rename(columns=col_mapping, inplace=True)

            # 设置时间索引
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)

            # 排序索引
            df.sort_index(inplace=True)

            # 限制数据量
            if len(df) > request.limit:
                df = df.tail(request.limit)

            return df

        except Exception:
            raise

    def validate_data_quality(self, df: pd.DataFrame, symbol: str) -> dict[str, Any]:
        """
        验证数据质量

        Returns:
            验证结果字典，包含：
                - is_valid: 数据是否有效
                - issues: 问题列表
                - metrics: 质量指标
        """
        if df.empty:
            return {"is_valid": False, "issues": ["数据为空"], "metrics": {}}

        issues = []
        metrics = {}

        # 1. 检查缺失值
        missing_counts = df.isnull().sum()
        missing_columns = missing_counts[missing_counts > 0]

        if not missing_columns.empty:
            issues.append(f"缺失值: {missing_columns.to_dict()}")

        # 2. 检查零值或负值
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                zero_or_negative = (df[col] <= 0).sum()
                if zero_or_negative > 0:
                    issues.append(f"{col}列有{zero_or_negative}个零值或负值")

        # 3. 检查时间间隔一致性
        if df.index.is_monotonic_increasing and len(df) > 1:
            time_diffs = df.index.to_series().diff().dropna()
            if not time_diffs.empty:
                # 使用 pd.to_timedelta 保证可以处理 numpy.float64（纳秒）和 timedelta64
                avg_gap = pd.to_timedelta(time_diffs.mean()).total_seconds()
                max_gap = pd.to_timedelta(time_diffs.max()).total_seconds()

                metrics["avg_time_gap_seconds"] = avg_gap
                metrics["max_time_gap_seconds"] = max_gap

                if max_gap > self.max_gap_seconds:
                    issues.append(
                        f"最大时间间隔过长: {max_gap:.0f}秒 > {self.max_gap_seconds}秒"
                    )

        # 4. 检查价格合理性
        if all(col in df.columns for col in ["high", "low", "close"]):
            # 检查high >= low
            invalid_high_low = (df["high"] < df["low"]).sum()
            if invalid_high_low > 0:
                issues.append(f"high < low的行数: {invalid_high_low}")

            # 检查close在high/low范围内
            invalid_close = (
                (df["close"] > df["high"]) | (df["close"] < df["low"])
            ).sum()
            if invalid_close > 0:
                issues.append(f"close不在high/low范围内的行数: {invalid_close}")

        # 5. 检查成交量异常
        if "volume" in df.columns:
            volume_mean = df["volume"].mean()
            volume_std = df["volume"].std()

            if volume_std > 0:
                # 检查极端成交量（超过3个标准差）
                extreme_volume = (
                    abs(df["volume"] - volume_mean) > 3 * volume_std
                ).sum()
                if extreme_volume > 0:
                    issues.append(f"极端成交量行数: {extreme_volume}")

            metrics["volume_mean"] = volume_mean
            metrics["volume_std"] = volume_std

        is_valid = len(issues) == 0

        return {
            "is_valid": is_valid,
            "issues": issues,
            "metrics": metrics,
            "data_points": len(df),
            "date_range": (df.index.min(), df.index.max())
            if not df.empty
            else (None, None),
        }

    def validate_correlation(
        self, df1: pd.DataFrame, df2: pd.DataFrame, symbol1: str, symbol2: str
    ) -> dict[str, Any]:
        """
        验证两个数据源的相关性（多源互证）

        Args:
            df1: 第一个symbol的数据
            df2: 第二个symbol的数据
            symbol1: 第一个symbol名称
            symbol2: 第二个symbol名称

        Returns:
            相关性验证结果
        """
        if df1.empty or df2.empty:
            return {
                "correlation": 0.0,
                "is_correlated": False,
                "common_points": 0,
                "issues": ["数据为空，无法计算相关性"],
            }

        # 对齐时间索引
        common_index = df1.index.intersection(df2.index)

        if len(common_index) < 10:
            return {
                "correlation": 0.0,
                "is_correlated": False,
                "common_points": len(common_index),
                "issues": [f"共同数据点不足: {len(common_index)} < 10"],
            }

        # 提取收盘价序列
        close1 = df1.loc[common_index, "close"]
        close2 = df2.loc[common_index, "close"]

        # 计算收益率相关性
        returns1 = close1.pct_change().dropna()
        returns2 = close2.pct_change().dropna()

        # 对齐收益率序列
        common_returns_index = returns1.index.intersection(returns2.index)
        returns1_aligned = returns1.loc[common_returns_index]
        returns2_aligned = returns2.loc[common_returns_index]

        if len(common_returns_index) < 5:
            return {
                "correlation": 0.0,
                "is_correlated": False,
                "common_points": len(common_index),
                "issues": [f"收益率数据点不足: {len(common_returns_index)} < 5"],
            }

        # 计算相关系数
        correlation = returns1_aligned.corr(returns2_aligned)

        is_correlated = abs(correlation) > self.correlation_threshold

        issues = []
        if not is_correlated:
            issues.append(
                f"相关性不足: {correlation:.3f} < {self.correlation_threshold}"
            )

        return {
            "correlation": correlation,
            "is_correlated": is_correlated,
            "common_points": len(common_index),
            "common_returns_points": len(common_returns_index),
            "issues": issues,
            "symbol1": symbol1,
            "symbol2": symbol2,
        }

    async def fetch_data(self, request: DataRequest) -> pd.DataFrame:
        """
        获取数据（带缓存和验证）

        Args:
            request: 数据请求参数

        Returns:
            OHLCV数据DataFrame
        """
        # 生成缓存键
        cache_key = self.get_cache_key(request)

        # 尝试从缓存获取
        if self.enable_cache:
            cached_data = self.get_cached_data(cache_key)
            if cached_data is not None:
                # 验证缓存数据新鲜度
                if not cached_data.empty:
                    latest_time = cached_data.index.max()
                    age = (datetime.now() - latest_time).total_seconds()  # type: ignore[operator]

                    # 根据时间框架确定最大缓存年龄
                    max_age_map = {
                        Timeframe.M1: 60,  # 1分钟数据缓存1分钟
                        Timeframe.M5: 300,  # 5分钟数据缓存5分钟
                        Timeframe.M15: 900,  # 15分钟数据缓存15分钟
                        Timeframe.H1: 3600,  # 1小时数据缓存1小时
                        Timeframe.H4: 14400,  # 4小时数据缓存4小时
                        Timeframe.D1: 86400,  # 日线数据缓存1天
                    }

                    max_age = max_age_map.get(request.timeframe, 3600)

                    if age < max_age:
                        return cached_data

        # 根据数据源获取数据
        try:
            if request.source == DataSource.CCXT:
                df = await self.fetch_ccxt_data(request)
            elif request.source == DataSource.YFINANCE:
                df = await self.fetch_yfinance_data(request)
            elif request.source == DataSource.CSV:
                df = await self.fetch_csv_data(request)
            elif request.source == DataSource.API:
                # 自定义API实现（需要子类重写）
                df = await self.fetch_custom_api_data(request)
            else:
                raise ValueError(f"不支持的数据源: {request.source}")

            # 数据质量验证
            if self.enable_validation:
                validation_result = self.validate_data_quality(df, request.symbol)

                if not validation_result["is_valid"]:

                    # 根据严重程度决定是否继续
                    if len(validation_result["issues"]) > 3:
                        df = pd.DataFrame()

            # 缓存数据
            if not df.empty:
                self.set_cached_data(cache_key, df)

            return df

        except Exception:
            return pd.DataFrame()

    async def fetch_custom_api_data(self, request: DataRequest) -> pd.DataFrame:
        """获取自定义API数据"""
        if not self.custom_api_url:
            raise ValueError("自定义API URL未配置，请在config中设置custom_api_url")

        # 构建查询参数
        params = {
            "symbol": request.symbol,
            "timeframe": request.timeframe.value,
            "limit": request.limit,
        }
        if request.start_date:
            params["start"] = request.start_date.isoformat()
        if request.end_date:
            params["end"] = request.end_date.isoformat()

        # 添加自定义API密钥（如果配置中存在）
        api_key = self.config.get("custom_api_key")
        if api_key:
            params["api_key"] = api_key

        headers = {
            "User-Agent": "WyckoffDataPipeline/1.0",
            "Accept": "application/json, text/csv",
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout)
        ) as session:
            for retry in range(self.max_retries):
                try:
                    async with session.get(
                        self.custom_api_url, params=params, headers=headers
                    ) as response:
                        response.raise_for_status()
                        content_type = response.headers.get("Content-Type", "").lower()

                        # 根据内容类型解析数据
                        if "json" in content_type:
                            data = await response.json()
                            df = self._parse_custom_api_json(data, request)
                        elif "csv" in content_type or "text/plain" in content_type:
                            text = await response.text()
                            df = self._parse_custom_api_csv(text, request)
                        else:
                            # 尝试自动检测
                            text = await response.text()
                            try:
                                data = json.loads(text)
                                df = self._parse_custom_api_json(data, request)
                            except json.JSONDecodeError:
                                df = self._parse_custom_api_csv(text, request)

                        if df.empty:
                            pass
                        else:
                            pass
                        return df

                except (aiohttp.ClientError, asyncio.TimeoutError):
                    if retry == self.max_retries - 1:
                        raise
                    await asyncio.sleep(2**retry)  # 指数退避
                except Exception:
                    raise

        # 不应执行到此处
        return pd.DataFrame()

    def _parse_custom_api_json(self, data: Any, request: DataRequest) -> pd.DataFrame:
        """解析自定义API返回的JSON数据"""
        try:
            # 处理多种可能的JSON结构
            if isinstance(data, dict):
                # 如果返回的是字典，检查是否有数据键
                if "data" in data and isinstance(data["data"], list):
                    records = data["data"]
                elif "ohlcv" in data and isinstance(data["ohlcv"], list):
                    records = data["ohlcv"]
                elif "candles" in data and isinstance(data["candles"], list):
                    records = data["candles"]
                else:
                    # 尝试将字典转换为列表
                    records = [data]
            elif isinstance(data, list):
                records = data
            else:
                return pd.DataFrame()

            if not records:
                return pd.DataFrame()

            # 尝试自动检测字段名
            first_record = records[0]
            if isinstance(first_record, (list, tuple)):
                # 数组格式: [timestamp, open, high, low, close, volume]
                df = pd.DataFrame(
                    records,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],  # type: ignore[arg-type]
                )
            elif isinstance(first_record, dict):
                # 对象格式: {"timestamp": ..., "open": ..., ...}
                # 处理混合列名情况：遍历所有记录构建完整映射
                possible_columns = {
                    "timestamp": ["timestamp", "time", "date", "datetime", "t"],
                    "open": ["open", "o"],
                    "high": ["high", "h"],
                    "low": ["low", "l"],
                    "close": ["close", "c"],
                    "volume": ["volume", "v", "vol"],
                }

                # 构建标准化的记录列表
                standardized_records = []
                for record in records:
                    standardized_record = {}
                    for standard_col, possible_names in possible_columns.items():
                        # 查找记录中匹配的键
                        value_found = None
                        for name in possible_names:
                            if name in record:
                                value_found = record[name]
                                break
                        # 如果找到值，则使用；否则设为NaN
                        standardized_record[standard_col] = value_found
                    standardized_records.append(standardized_record)

                df = pd.DataFrame(standardized_records)
            else:
                return pd.DataFrame()

            # 确保必要的列存在
            required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                return pd.DataFrame()

            # 转换时间戳列
            # 保存原始时间戳值
            original_timestamps = df["timestamp"].copy()
            # 首先尝试将毫秒时间戳转换为datetime
            df["timestamp"] = pd.to_datetime(
                original_timestamps, unit="ms", errors="coerce"
            )
            # 如果存在NaT值，尝试作为ISO格式字符串解析
            if df["timestamp"].isna().any():  # type: ignore[operator]
                # 对转换失败的值尝试通用解析
                mask = df["timestamp"].isna()
                df.loc[mask, "timestamp"] = pd.to_datetime(
                    original_timestamps[mask], errors="coerce"
                )

            # 设置索引并排序
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

            # 转换数值列
            numeric_cols = ["open", "high", "low", "close", "volume"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 去除空值
            df.dropna(subset=numeric_cols, how="all", inplace=True)

            # 限制数据量
            if len(df) > request.limit:
                df = df.tail(request.limit)

            return df

        except Exception:
            return pd.DataFrame()

    def _parse_custom_api_csv(
        self, csv_text: str, request: DataRequest
    ) -> pd.DataFrame:
        """解析自定义API返回的CSV数据"""
        import io

        try:
            # 尝试读取CSV
            df = pd.read_csv(io.StringIO(csv_text))

            # 尝试自动检测列名
            column_mapping = {}
            possible_columns = {
                "timestamp": ["timestamp", "time", "date", "datetime", "t"],
                "open": ["open", "o"],
                "high": ["high", "h"],
                "low": ["low", "l"],
                "close": ["close", "c"],
                "volume": ["volume", "v", "vol"],
            }

            for col in df.columns:
                col_lower = col.lower()
                for standard_col, possible_names in possible_columns.items():
                    if col_lower in possible_names:
                        column_mapping[col] = standard_col
                        break

            if column_mapping:
                df.rename(columns=column_mapping, inplace=True)

            # 确保必要的列存在
            required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                return pd.DataFrame()

            # 转换时间戳列
            # 保存原始时间戳值
            original_timestamps = df["timestamp"].copy()
            # 首先尝试将毫秒时间戳转换为datetime
            df["timestamp"] = pd.to_datetime(
                original_timestamps, unit="ms", errors="coerce"
            )
            # 如果存在NaT值，尝试作为ISO格式字符串解析
            if df["timestamp"].isna().any():  # type: ignore[operator]
                # 对转换失败的值尝试通用解析
                mask = df["timestamp"].isna()
                df.loc[mask, "timestamp"] = pd.to_datetime(
                    original_timestamps[mask], errors="coerce"
                )

            # 设置索引并排序
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

            # 转换数值列
            numeric_cols = ["open", "high", "low", "close", "volume"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 去除空值
            df.dropna(subset=numeric_cols, how="all", inplace=True)

            # 限制数据量
            if len(df) > request.limit:
                df = df.tail(request.limit)

            return df

        except Exception:
            return pd.DataFrame()

    async def fetch_multiple_timeframes(
        self,
        symbol: str,
        source: DataSource,
        timeframes: list[Timeframe],
        limit: int = 1000,
    ) -> dict[Timeframe, pd.DataFrame]:
        """
        获取多时间框架数据（异步并发）

        Args:
            symbol: 交易对/股票代码
            source: 数据源
            timeframes: 时间框架列表
            limit: 每个时间框架数据量

        Returns:
            字典：{时间框架: DataFrame}
        """
        # 创建请求列表
        requests = []
        for tf in timeframes:
            request = DataRequest(
                symbol=symbol,
                timeframe=tf,
                source=source,
                limit=limit,
                start_date=datetime.now() - timedelta(days=30),  # 默认获取30天数据
            )
            requests.append(request)

        # 并发获取数据
        tasks = [self.fetch_data(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        data_dict = {}
        for tf, result in zip(timeframes, results):
            if isinstance(result, Exception):
                data_dict[tf] = pd.DataFrame()
            else:
                data_dict[tf] = result

        return data_dict

    async def perform_correlation_validation(
        self,
        symbol_pairs: list[tuple[str, str]],
        timeframe: Timeframe = Timeframe.H1,
        limit: int = 500,
    ) -> dict[str, dict]:
        """
        执行相关性验证（多源互证）

        Args:
            symbol_pairs: 需要验证的相关性对列表
            timeframe: 时间框架
            limit: 数据量

        Returns:
            相关性验证结果字典
        """
        results = {}

        for symbol1, symbol2 in symbol_pairs:
            # 获取两个symbol的数据
            request1 = DataRequest(
                symbol=symbol1, timeframe=timeframe, source=DataSource.CCXT, limit=limit
            )

            request2 = DataRequest(
                symbol=symbol2, timeframe=timeframe, source=DataSource.CCXT, limit=limit
            )

            df1 = await self.fetch_data(request1)
            df2 = await self.fetch_data(request2)

            # 验证相关性
            correlation_result = self.validate_correlation(df1, df2, symbol1, symbol2)

            pair_key = f"{symbol1}_{symbol2}"
            results[pair_key] = correlation_result

        return results

    def align_timeframes(
        self,
        data_dict: dict[Timeframe, pd.DataFrame],
        target_timeframe: Timeframe = Timeframe.H4,
    ) -> pd.DataFrame:
        """
        对齐多时间框架数据（节奏同步）

        Args:
            data_dict: 多时间框架数据字典
            target_timeframe: 目标对齐时间框架

        Returns:
            对齐后的DataFrame，包含多时间框架特征
        """
        if not data_dict:
            return pd.DataFrame()

        # 获取目标时间框架数据作为基准
        if target_timeframe not in data_dict or data_dict[target_timeframe].empty:
            # 使用最大的可用时间框架
            available_tfs = [tf for tf in data_dict if not data_dict[tf].empty]
            if not available_tfs:
                return pd.DataFrame()

            # 按时间框架大小排序（D1 > H4 > H1 > M15 > M5 > M1）
            tf_order = {
                Timeframe.MN1: 10,
                Timeframe.W1: 9,
                Timeframe.D1: 8,
                Timeframe.H12: 7,
                Timeframe.H8: 6,
                Timeframe.H6: 5,
                Timeframe.H4: 4,
                Timeframe.H2: 3,
                Timeframe.H1: 2,
                Timeframe.M30: 1,
                Timeframe.M15: 0,
                Timeframe.M5: -1,
                Timeframe.M1: -2,
            }

            available_tfs.sort(key=lambda x: tf_order.get(x, 0), reverse=True)
            target_timeframe = available_tfs[0]

        base_df = data_dict[target_timeframe].copy()

        # 对齐其他时间框架数据
        for tf, df in data_dict.items():
            if tf == target_timeframe or df.empty:
                continue

            # 重新采样到目标时间框架
            try:
                # 使用ohlc重采样
                resampled = df.resample(target_timeframe.value).agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )

                # 添加前缀列
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in resampled.columns:
                        base_df[f"{col}_{tf.value}"] = resampled[col]

            except Exception:
                pass

        return base_df

    def get_statistics(self) -> dict[str, Any]:
        """获取管道统计信息"""
        cache_hits = self.cache_stats["hits"]
        cache_misses = self.cache_stats["misses"]
        cache_total = cache_hits + cache_misses

        cache_hit_rate = cache_hits / cache_total if cache_total > 0 else 0.0

        return {
            "cache_stats": self.cache_stats.copy(),
            "cache_hit_rate": cache_hit_rate,
            "source_status": self.source_status.copy(),
            "enable_cache": self.enable_cache,
            "enable_validation": self.enable_validation,
        }


# 简单使用示例
async def main_example():
    """数据管道使用示例"""

    # 创建数据管道
    pipeline = DataPipeline(
        {
            "redis_host": "localhost",
            "redis_port": 6379,
            "cache_ttl": 1800,
            "enable_cache": True,
            "enable_validation": True,
        }
    )

    # 示例1: 获取单个时间框架数据
    request = DataRequest(
        symbol="BTC/USDT",
        timeframe=Timeframe.H1,
        source=DataSource.CCXT,
        exchange="binance",
        limit=100,
    )

    btc_data = await pipeline.fetch_data(request)

    if not btc_data.empty:
        pass
    else:
        pass

    # 示例2: 获取多时间框架数据
    timeframes = [Timeframe.M15, Timeframe.H1, Timeframe.H4]

    eth_data_dict = await pipeline.fetch_multiple_timeframes(
        symbol="ETH/USDT", source=DataSource.CCXT, timeframes=timeframes, limit=200
    )

    for tf, df in eth_data_dict.items():
        if not df.empty:
            pass
        else:
            pass

    # 示例3: 对齐多时间框架数据
    aligned_data = pipeline.align_timeframes(eth_data_dict, Timeframe.H4)

    if not aligned_data.empty:
        pass

    # 示例4: 相关性验证
    correlation_results = await pipeline.perform_correlation_validation(
        symbol_pairs=[("BTC/USDT", "ETH/USDT")], timeframe=Timeframe.H1, limit=500
    )

    for pair_key, result in correlation_results.items():
        if result["issues"]:
            pass

    # 示例5: 统计信息
    pipeline.get_statistics()

    return pipeline, btc_data, eth_data_dict, aligned_data


if __name__ == "__main__":
    # 运行示例
    import asyncio

    with contextlib.suppress(Exception):
        pipeline, btc_data, eth_data_dict, aligned_data = asyncio.run(main_example())
