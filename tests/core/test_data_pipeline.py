"""
DataPipeline单元测试
测试src/core/data_pipeline.py模块的所有功能
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import numpy as np
import pandas as pd
import pickle

try:
    from src.plugins.data_pipeline.data_pipeline import (
        DataPipeline,
        DataRequest,
        DataSource,
        Timeframe,
    )
except ImportError:
    from core.data_pipeline import (
        DataPipeline,
        DataRequest,
        DataSource,
        Timeframe,
    )


class TestDataPipeline(unittest.TestCase):
    """DataPipeline单元测试类"""

    def setUp(self):
        """测试前准备"""
        # 创建测试配置
        self.config = {
            "redis_host": "localhost",
            "redis_port": 6379,
            "cache_ttl": 3600,
            "max_retries": 2,
            "request_timeout": 10,
            "correlation_threshold": 0.7,
            "max_gap_seconds": 300,
            "enable_validation": True,
            "enable_cache": True,
        }

        # 创建数据管道实例
        self.pipeline = DataPipeline(self.config)

        # 创建测试数据
        self.test_timestamps = pd.date_range(
            start="2025-01-01 00:00:00", periods=10, freq="1h"
        )
        self.test_df = pd.DataFrame(
            {
                "open": np.random.uniform(100, 110, 10),
                "high": np.random.uniform(110, 120, 10),
                "low": np.random.uniform(90, 100, 10),
                "close": np.random.uniform(105, 115, 10),
                "volume": np.random.uniform(1000, 5000, 10),
            },
            index=self.test_timestamps,
        )

        # 创建测试请求
        self.test_request = DataRequest(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            source=DataSource.CCXT,
            exchange="binance",
            limit=100,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
            validate=True,
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.pipeline)
        self.assertEqual(self.pipeline.redis_host, "localhost")
        self.assertEqual(self.pipeline.redis_port, 6379)
        self.assertEqual(self.pipeline.cache_ttl, 3600)
        self.assertEqual(self.pipeline.max_retries, 2)
        self.assertEqual(self.pipeline.request_timeout, 10)
        self.assertEqual(self.pipeline.correlation_threshold, 0.7)
        self.assertEqual(self.pipeline.max_gap_seconds, 300)
        self.assertTrue(self.pipeline.enable_validation)
        self.assertTrue(self.pipeline.enable_cache)

    def test_get_cache_key(self):
        """测试缓存键生成"""
        cache_key = self.pipeline.get_cache_key(self.test_request)
        expected_key = "data:CCXT:BTC_USDT:1h:20250101:20250102:100"
        self.assertEqual(cache_key, expected_key)

        # 测试无日期的情况
        request_no_date = DataRequest(
            symbol="ETH/USDT",
            timeframe=Timeframe.D1,
            source=DataSource.YFINANCE,
            limit=50,
        )
        cache_key_no_date = self.pipeline.get_cache_key(request_no_date)
        self.assertIn("data:YFINANCE:ETH_USDT:1d:all:now:50", cache_key_no_date)

    @patch("redis.Redis")
    def test_get_redis_client(self, mock_redis):
        """测试Redis客户端获取"""
        # 模拟Redis连接成功
        mock_instance = Mock()
        mock_instance.ping.return_value = True
        mock_redis.return_value = mock_instance

        client = self.pipeline.get_redis_client()
        self.assertIsNotNone(client)
        self.assertEqual(client, mock_instance)

        # 测试连接失败的情况
        mock_redis.side_effect = Exception("Connection failed")
        self.pipeline._redis_client = None
        client = self.pipeline.get_redis_client()
        self.assertIsNone(client)
        self.assertFalse(self.pipeline.enable_cache)

    @patch("redis.Redis")
    def test_get_cached_data(self, mock_redis):
        """测试缓存数据获取"""
        # 模拟Redis客户端
        mock_client = Mock()
        mock_client.get.return_value = pickle.dumps(self.test_df)
        self.pipeline._redis_client = mock_client

        cache_key = "test_key"
        cached_data = self.pipeline.get_cached_data(cache_key)

        self.assertIsNotNone(cached_data)
        self.assertTrue(isinstance(cached_data, pd.DataFrame))
        self.assertEqual(len(cached_data), 10)
        mock_client.get.assert_called_once_with(cache_key)

        # 测试缓存未命中
        mock_client.get.return_value = None
        cached_data = self.pipeline.get_cached_data(cache_key)
        self.assertIsNone(cached_data)

        # 测试缓存禁用
        self.pipeline.enable_cache = False
        cached_data = self.pipeline.get_cached_data(cache_key)
        self.assertIsNone(cached_data)

    @patch("redis.Redis")
    def test_set_cached_data(self, mock_redis):
        """测试缓存数据设置"""
        # 模拟Redis客户端
        mock_client = Mock()
        self.pipeline._redis_client = mock_client

        cache_key = "test_key"
        self.pipeline.set_cached_data(cache_key, self.test_df)

        mock_client.setex.assert_called_once()
        args, kwargs = mock_client.setex.call_args
        self.assertEqual(args[0], cache_key)
        self.assertEqual(args[1], self.pipeline.cache_ttl)

        # 测试空数据不缓存
        mock_client.reset_mock()
        self.pipeline.set_cached_data(cache_key, pd.DataFrame())
        mock_client.setex.assert_not_called()

        # 测试缓存禁用
        self.pipeline.enable_cache = False
        mock_client.reset_mock()
        self.pipeline.set_cached_data(cache_key, self.test_df)
        mock_client.setex.assert_not_called()

    def test_validate_data_quality(self):
        """测试数据质量验证"""
        # 创建符合时间间隔要求的数据
        test_timestamps = pd.date_range(
            start="2025-01-01 00:00:00",
            periods=10,
            freq="4min",  # 4分钟间隔，小于300秒
        )
        # 创建确保价格合理性的测试数据
        np.random.seed(42)  # 固定随机种子以确保可重复性
        opens = np.random.uniform(100, 110, 10)
        highs = opens + np.random.uniform(1, 10, 10)  # high > open
        lows = opens - np.random.uniform(1, 10, 10)  # low < open
        closes = np.random.uniform(lows, highs)  # close在low和high之间

        test_df = pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": np.random.uniform(1000, 5000, 10),
            },
            index=test_timestamps,
        )

        # 测试正常数据
        validation_result = self.pipeline.validate_data_quality(test_df, "BTC/USDT")
        print(f"验证结果: {validation_result}")  # 调试信息
        if not validation_result["is_valid"]:
            print(f"发现问题: {validation_result['issues']}")
        self.assertTrue(validation_result["is_valid"])
        self.assertEqual(len(validation_result["issues"]), 0)
        self.assertIn("data_points", validation_result)
        self.assertIn("date_range", validation_result)

        # 测试空数据
        empty_df = pd.DataFrame()
        validation_result = self.pipeline.validate_data_quality(empty_df, "BTC/USDT")
        self.assertFalse(validation_result["is_valid"])
        self.assertIn("数据为空", validation_result["issues"][0])

        # 测试缺失值
        df_with_nan = test_df.copy()
        df_with_nan.loc[df_with_nan.index[0], "open"] = np.nan
        validation_result = self.pipeline.validate_data_quality(df_with_nan, "BTC/USDT")
        self.assertFalse(validation_result["is_valid"])
        self.assertIn("缺失值", validation_result["issues"][0])

        # 测试零值或负值
        df_with_zero = test_df.copy()
        df_with_zero.loc[df_with_zero.index[0], "close"] = 0
        validation_result = self.pipeline.validate_data_quality(
            df_with_zero, "BTC/USDT"
        )
        self.assertFalse(validation_result["is_valid"])
        self.assertIn("close列有1个零值或负值", validation_result["issues"][0])

        # 测试价格合理性
        df_invalid_range = test_df.copy()
        df_invalid_range.loc[df_invalid_range.index[0], "high"] = 90
        df_invalid_range.loc[df_invalid_range.index[0], "low"] = 100
        validation_result = self.pipeline.validate_data_quality(
            df_invalid_range, "BTC/USDT"
        )
        self.assertFalse(validation_result["is_valid"])
        self.assertIn("high < low的行数: 1", validation_result["issues"][0])

        # 测试时间间隔
        irregular_timestamps = pd.date_range(
            start="2025-01-01 00:00:00", periods=3, freq="2h"
        )
        irregular_timestamps = irregular_timestamps.append(
            pd.DatetimeIndex([pd.Timestamp("2025-01-01 07:00:00")])
        )
        df_irregular = pd.DataFrame(
            {
                "open": [100, 101, 102, 103],
                "high": [105, 106, 107, 108],
                "low": [95, 96, 97, 98],
                "close": [102, 103, 104, 105],
                "volume": [1000, 1100, 1200, 1300],
            },
            index=irregular_timestamps,
        )
        validation_result = self.pipeline.validate_data_quality(
            df_irregular, "BTC/USDT"
        )
        self.assertFalse(validation_result["is_valid"])
        self.assertIn("最大时间间隔过长", validation_result["issues"][0])

    def test_validate_correlation(self):
        """测试相关性验证"""
        # 创建两个相关的数据序列
        np.random.seed(42)
        base_returns = np.random.normal(0, 0.01, 100)
        correlated_returns = base_returns * 0.8 + np.random.normal(0, 0.005, 100)

        timestamps = pd.date_range(start="2025-01-01", periods=100, freq="1h")
        df1 = pd.DataFrame(
            {
                "close": 100 * (1 + np.cumsum(base_returns)),
            },
            index=timestamps,
        )
        df2 = pd.DataFrame(
            {
                "close": 50 * (1 + np.cumsum(correlated_returns)),
            },
            index=timestamps,
        )

        # 测试高相关性
        correlation_result = self.pipeline.validate_correlation(
            df1, df2, "BTC/USDT", "ETH/USDT"
        )
        self.assertTrue(correlation_result["is_correlated"])
        self.assertGreater(correlation_result["correlation"], 0.7)
        self.assertEqual(correlation_result["common_points"], 100)

        # 测试低相关性
        uncorrelated_returns = np.random.normal(0, 0.01, 100)
        df3 = pd.DataFrame(
            {
                "close": 100 * (1 + np.cumsum(uncorrelated_returns)),
            },
            index=timestamps,
        )
        correlation_result = self.pipeline.validate_correlation(
            df1, df3, "BTC/USDT", "XRP/USDT"
        )
        self.assertFalse(correlation_result["is_correlated"])
        self.assertLess(abs(correlation_result["correlation"]), 0.7)

        # 测试空数据
        empty_df = pd.DataFrame()
        correlation_result = self.pipeline.validate_correlation(
            empty_df, df1, "BTC/USDT", "ETH/USDT"
        )
        self.assertFalse(correlation_result["is_correlated"])
        self.assertEqual(correlation_result["correlation"], 0.0)
        self.assertIn("数据为空", correlation_result["issues"][0])

        # 测试数据点不足
        df_small = df1.head(5)
        correlation_result = self.pipeline.validate_correlation(
            df_small, df2.head(5), "BTC/USDT", "ETH/USDT"
        )
        self.assertFalse(correlation_result["is_correlated"])
        self.assertIn("共同数据点不足", correlation_result["issues"][0])

    @patch.object(DataPipeline, "fetch_ccxt_data")
    async def test_fetch_data_with_cache(self, mock_fetch_ccxt):
        """测试带缓存的数据获取"""
        # 模拟缓存命中
        mock_fetch_ccxt.return_value = self.test_df

        # 模拟缓存数据
        with patch.object(self.pipeline, "get_cached_data") as mock_get_cache:
            with patch.object(self.pipeline, "set_cached_data") as mock_set_cache:
                # 测试缓存命中
                mock_get_cache.return_value = self.test_df
                result = await self.pipeline.fetch_data(self.test_request)

                self.assertTrue(isinstance(result, pd.DataFrame))
                self.assertEqual(len(result), 10)
                mock_fetch_ccxt.assert_not_called()  # 不应调用实际获取
                mock_set_cache.assert_not_called()  # 不应设置缓存

                # 测试缓存未命中
                mock_get_cache.return_value = None
                result = await self.pipeline.fetch_data(self.test_request)

                mock_fetch_ccxt.assert_called_once_with(self.test_request)
                mock_set_cache.assert_called_once()
                self.assertTrue(isinstance(result, pd.DataFrame))

    @patch.object(DataPipeline, "fetch_ccxt_data")
    async def test_fetch_data_validation(self, mock_fetch_ccxt):
        """测试数据获取时的验证"""
        # 创建有问题的测试数据
        problematic_df = self.test_df.copy()
        problematic_df.loc[problematic_df.index[0], "high"] = 80
        problematic_df.loc[problematic_df.index[0], "low"] = 90

        mock_fetch_ccxt.return_value = problematic_df

        # 禁用缓存以测试验证逻辑
        self.pipeline.enable_cache = False

        with patch.object(self.pipeline, "validate_data_quality") as mock_validate:
            # 测试验证通过
            mock_validate.return_value = {"is_valid": True, "issues": []}
            result = await self.pipeline.fetch_data(self.test_request)

            self.assertFalse(result.empty)
            mock_validate.assert_called_once_with(problematic_df, "BTC/USDT")

            # 测试验证失败但问题不严重
            mock_validate.return_value = {
                "is_valid": False,
                "issues": ["minor issue 1", "minor issue 2"],
            }
            result = await self.pipeline.fetch_data(self.test_request)

            self.assertFalse(result.empty)  # 应返回数据但记录警告

            # 测试验证失败且问题严重
            mock_validate.return_value = {
                "is_valid": False,
                "issues": [
                    "serious issue 1",
                    "serious issue 2",
                    "serious issue 3",
                    "serious issue 4",
                ],
            }
            result = await self.pipeline.fetch_data(self.test_request)

            self.assertTrue(result.empty)  # 应返回空DataFrame

    @patch("ccxt.binance")
    async def test_fetch_ccxt_data(self, mock_binance_class):
        """测试CCXT数据获取"""
        # 模拟CCXT交易所和数据
        mock_exchange = Mock()
        mock_binance_class.return_value = mock_exchange

        # 模拟OHLCV数据
        mock_ohlcv = [
            [1704067200000, 100.0, 105.0, 95.0, 102.0, 1000.0],
            [1704070800000, 102.0, 107.0, 100.0, 105.0, 1200.0],
            [1704074400000, 105.0, 110.0, 103.0, 108.0, 1500.0],
        ]
        mock_exchange.fetch_ohlcv.return_value = mock_ohlcv

        # 调用方法
        df = await self.pipeline.fetch_ccxt_data(self.test_request)

        # 验证结果
        self.assertTrue(isinstance(df, pd.DataFrame))
        self.assertEqual(len(df), 3)
        self.assertListEqual(
            list(df.columns), ["open", "high", "low", "close", "volume"]
        )
        self.assertTrue(isinstance(df.index, pd.DatetimeIndex))

        # 验证调用参数
        mock_exchange.fetch_ohlcv.assert_called_once_with(
            "BTC/USDT",
            timeframe="1h",
            since=int(datetime(2025, 1, 1).timestamp() * 1000),
            limit=100,
        )

    @patch("yfinance.Ticker")
    async def test_fetch_yfinance_data(self, mock_ticker_class):
        """测试YFinance数据获取"""
        # 模拟YFinance Ticker和数据
        mock_ticker = Mock()
        mock_ticker_class.return_value = mock_ticker

        # 模拟历史数据
        mock_history = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [105.0, 106.0, 107.0],
                "Low": [95.0, 96.0, 97.0],
                "Close": [102.0, 103.0, 104.0],
                "Volume": [1000.0, 1100.0, 1200.0],
            },
            index=pd.date_range(start="2025-01-01", periods=3, freq="1h"),
        )
        mock_ticker.history.return_value = mock_history

        # 创建YFinance请求
        yfinance_request = DataRequest(
            symbol="AAPL",
            timeframe=Timeframe.H1,
            source=DataSource.YFINANCE,
            limit=100,
        )

        # 调用方法
        df = await self.pipeline.fetch_yfinance_data(yfinance_request)

        # 验证结果
        self.assertTrue(isinstance(df, pd.DataFrame))
        self.assertEqual(len(df), 3)
        self.assertListEqual(
            list(df.columns), ["open", "high", "low", "close", "volume"]
        )

        # 验证调用参数
        mock_ticker.history.assert_called_once()

    async def test_fetch_csv_data(self):
        """测试CSV数据获取"""
        import tempfile
        import os

        # 创建临时CSV文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2025-01-01 00:00:00,100.0,105.0,95.0,102.0,1000.0\n")
            f.write("2025-01-01 01:00:00,102.0,107.0,100.0,105.0,1200.0\n")
            f.write("2025-01-01 02:00:00,105.0,110.0,103.0,108.0,1500.0\n")
            temp_file = f.name

        try:
            # 创建CSV请求
            csv_request = DataRequest(
                symbol=temp_file,
                timeframe=Timeframe.H1,
                source=DataSource.CSV,
                limit=100,
            )

            # 调用方法
            df = await self.pipeline.fetch_csv_data(csv_request)

            # 验证结果
            self.assertTrue(isinstance(df, pd.DataFrame))
            self.assertEqual(len(df), 3)
            self.assertListEqual(
                list(df.columns), ["open", "high", "low", "close", "volume"]
            )
            self.assertTrue(isinstance(df.index, pd.DatetimeIndex))

        finally:
            # 清理临时文件
            os.unlink(temp_file)

    @patch("aiohttp.ClientSession")
    async def test_fetch_custom_api_data(self, mock_session_class):
        """测试自定义API数据获取"""
        # 配置自定义API URL
        self.pipeline.custom_api_url = "https://api.example.com/data"

        # 模拟API响应
        mock_response = AsyncMock()
        mock_response.headers.get.return_value = "application/json"
        mock_response.raise_for_status = Mock()
        mock_response.json = AsyncMock(
            return_value={
                "data": [
                    {
                        "timestamp": 1704067200000,
                        "open": 100.0,
                        "high": 105.0,
                        "low": 95.0,
                        "close": 102.0,
                        "volume": 1000.0,
                    },
                    {
                        "timestamp": 1704070800000,
                        "open": 102.0,
                        "high": 107.0,
                        "low": 100.0,
                        "close": 105.0,
                        "volume": 1200.0,
                    },
                ]
            }
        )

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value = mock_session

        # 创建API请求
        api_request = DataRequest(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            source=DataSource.API,
            limit=100,
        )

        # 调用方法
        df = await self.pipeline.fetch_custom_api_data(api_request)

        # 验证结果
        self.assertTrue(isinstance(df, pd.DataFrame))
        self.assertEqual(len(df), 2)
        self.assertListEqual(
            list(df.columns), ["open", "high", "low", "close", "volume"]
        )

    async def test_fetch_multiple_timeframes(self):
        """测试多时间框架数据获取"""
        # 模拟fetch_data方法
        with patch.object(self.pipeline, "fetch_data") as mock_fetch_data:
            # 设置模拟返回值
            mock_fetch_data.side_effect = [
                self.test_df,
                self.test_df.iloc[:5],  # 模拟不同长度的数据
                pd.DataFrame(),  # 模拟空数据
            ]

            # 调用方法
            timeframes = [Timeframe.M15, Timeframe.H1, Timeframe.H4]
            result = await self.pipeline.fetch_multiple_timeframes(
                symbol="BTC/USDT",
                source=DataSource.CCXT,
                timeframes=timeframes,
                limit=100,
            )

            # 验证结果
            self.assertIsInstance(result, dict)
            self.assertEqual(len(result), 3)
            self.assertIn(Timeframe.M15, result)
            self.assertIn(Timeframe.H1, result)
            self.assertIn(Timeframe.H4, result)

            # 验证数据
            self.assertEqual(len(result[Timeframe.M15]), 10)
            self.assertEqual(len(result[Timeframe.H1]), 5)
            self.assertTrue(result[Timeframe.H4].empty)

            # 验证调用次数
            self.assertEqual(mock_fetch_data.call_count, 3)

    async def test_perform_correlation_validation(self):
        """测试相关性验证执行"""
        # 模拟fetch_data方法
        with patch.object(self.pipeline, "fetch_data") as mock_fetch_data:
            with patch.object(self.pipeline, "validate_correlation") as mock_validate:
                # 设置模拟返回值
                mock_fetch_data.side_effect = [self.test_df, self.test_df]
                mock_validate.return_value = {
                    "correlation": 0.85,
                    "is_correlated": True,
                    "common_points": 10,
                    "issues": [],
                }

                # 调用方法
                symbol_pairs = [("BTC/USDT", "ETH/USDT")]
                result = await self.pipeline.perform_correlation_validation(
                    symbol_pairs=symbol_pairs,
                    timeframe=Timeframe.H1,
                    limit=100,
                )

                # 验证结果
                self.assertIsInstance(result, dict)
                self.assertIn("BTC/USDT_ETH/USDT", result)
                self.assertTrue(result["BTC/USDT_ETH/USDT"]["is_correlated"])
                self.assertEqual(result["BTC/USDT_ETH/USDT"]["correlation"], 0.85)

                # 验证调用
                self.assertEqual(mock_fetch_data.call_count, 2)
                mock_validate.assert_called_once()

    def test_align_timeframes(self):
        """测试多时间框架数据对齐"""
        # 创建多时间框架测试数据
        data_dict = {
            Timeframe.M15: pd.DataFrame(
                {
                    "open": [100, 101, 102, 103],
                    "high": [105, 106, 107, 108],
                    "low": [95, 96, 97, 98],
                    "close": [102, 103, 104, 105],
                    "volume": [1000, 1100, 1200, 1300],
                },
                index=pd.date_range(start="2025-01-01 00:00:00", periods=4, freq="15min"),
            ),
            Timeframe.H1: pd.DataFrame(
                {
                    "open": [100, 101],
                    "high": [108, 109],
                    "low": [95, 96],
                    "close": [105, 106],
                    "volume": [4600, 4700],
                },
                index=pd.date_range(start="2025-01-01 00:00:00", periods=2, freq="1h"),
            ),
        }

        # 调用方法
        aligned_data = self.pipeline.align_timeframes(data_dict, Timeframe.H1)

        # 验证结果
        self.assertFalse(aligned_data.empty)
        self.assertEqual(len(aligned_data), 2)

        # 检查是否添加了M15时间框架的特征列
        expected_columns = ["open", "high", "low", "close", "volume"]
        for col in expected_columns:
            self.assertIn(f"{col}_15m", aligned_data.columns)

        # 测试空数据情况
        empty_result = self.pipeline.align_timeframes({}, Timeframe.H1)
        self.assertTrue(empty_result.empty)

        # 测试目标时间框架数据为空的情况
        data_dict_no_target = {
            Timeframe.M15: data_dict[Timeframe.M15],
            Timeframe.H1: pd.DataFrame(),  # 空DataFrame
        }
        result_fallback = self.pipeline.align_timeframes(
            data_dict_no_target, Timeframe.H1
        )
        self.assertFalse(result_fallback.empty)

    def test_get_statistics(self):
        """测试统计信息获取"""
        # 设置一些缓存统计
        self.pipeline.cache_stats = {
            "hits": 10,
            "misses": 5,
            "writes": 8,
            "invalidations": 2,
        }

        # 设置数据源状态
        self.pipeline.source_status = {
            "ccxt": {
                "status": "connected",
                "last_check": datetime.now(),
                "error_count": 0,
            },
            "yfinance": {"status": "unknown", "last_check": None, "error_count": 3},
        }

        # 调用方法
        stats = self.pipeline.get_statistics()

        # 验证结果
        self.assertIsInstance(stats, dict)
        self.assertIn("cache_stats", stats)
        self.assertIn("cache_hit_rate", stats)
        self.assertIn("source_status", stats)
        self.assertIn("enable_cache", stats)
        self.assertIn("enable_validation", stats)

        # 验证缓存命中率计算
        expected_hit_rate = 10 / (10 + 5)  # 10 hits / 15 total
        self.assertAlmostEqual(stats["cache_hit_rate"], expected_hit_rate)

        # 验证数据源状态
        self.assertEqual(stats["source_status"]["ccxt"]["status"], "connected")
        self.assertEqual(stats["source_status"]["yfinance"]["error_count"], 3)

    def test_error_handling_in_fetch_data(self):
        """测试数据获取中的错误处理"""
        # 测试fetch_data方法中的异常处理
        with patch.object(self.pipeline, "get_cached_data", return_value=None):
            with patch.object(self.pipeline, "fetch_ccxt_data") as mock_fetch:
                # 模拟数据获取时抛出异常
                mock_fetch.side_effect = Exception("模拟的API错误")

                # 创建测试请求
                request = DataRequest(
                    symbol="BTC/USDT",
                    timeframe=Timeframe.H1,
                    source=DataSource.CCXT,
                    limit=100,
                )

                # 运行异步测试
                async def run_test():
                    return await self.pipeline.fetch_data(request)

                import asyncio

                result = asyncio.run(run_test())

                # 验证错误处理：应返回空DataFrame而不是抛出异常
                self.assertTrue(isinstance(result, pd.DataFrame))
                self.assertTrue(result.empty)

    def test_data_pipeline_configuration_variations(self):
        """测试不同配置的数据管道"""
        # 测试禁用缓存
        config_no_cache = self.config.copy()
        config_no_cache["enable_cache"] = False
        pipeline_no_cache = DataPipeline(config_no_cache)
        self.assertFalse(pipeline_no_cache.enable_cache)

        # 测试禁用验证
        config_no_validation = self.config.copy()
        config_no_validation["enable_validation"] = False
        pipeline_no_validation = DataPipeline(config_no_validation)
        self.assertFalse(pipeline_no_validation.enable_validation)

        # 测试自定义相关阈值
        config_custom_threshold = self.config.copy()
        config_custom_threshold["correlation_threshold"] = 0.5
        pipeline_custom_threshold = DataPipeline(config_custom_threshold)
        self.assertEqual(pipeline_custom_threshold.correlation_threshold, 0.5)

        # 测试自定义最大间隔
        config_custom_gap = self.config.copy()
        config_custom_gap["max_gap_seconds"] = 600
        pipeline_custom_gap = DataPipeline(config_custom_gap)
        self.assertEqual(pipeline_custom_gap.max_gap_seconds, 600)


# 异步测试运行器
class AsyncTestRunner:
    """异步测试运行器"""

    @staticmethod
    def run_tests():
        """运行所有测试"""
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(TestDataPipeline)

        # 运行同步测试
        print("运行同步测试...")
        sync_runner = unittest.TextTestRunner(verbosity=2)
        sync_result = sync_runner.run(suite)

        # 运行异步测试
        print("\n运行异步测试...")
        async_tests = [
            "test_fetch_data_with_cache",
            "test_fetch_data_validation",
            "test_fetch_ccxt_data",
            "test_fetch_yfinance_data",
            "test_fetch_csv_data",
            "test_fetch_custom_api_data",
            "test_fetch_multiple_timeframes",
            "test_perform_correlation_validation",
        ]

        async_success = True
        for test_name in async_tests:
            print(f"\n运行异步测试: {test_name}")
            try:
                test_method = getattr(TestDataPipeline(test_name), test_name)
                asyncio.run(test_method())
                print(f"  ✓ {test_name} 通过")
            except Exception as e:
                print(f"  ✗ {test_name} 失败: {e}")
                async_success = False

        return sync_result.wasSuccessful() and async_success


if __name__ == "__main__":
    # 运行测试
    success = AsyncTestRunner.run_tests()

    if success:
        print("\n" + "=" * 50)
        print("所有测试通过！")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("部分测试失败")
        print("=" * 50)
        sys.exit(1)
