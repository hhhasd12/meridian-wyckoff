"""交易所连接器插件测试 - 第1批

测试内容：初始化、加载/卸载、配置更新、健康检查
"""

from unittest.mock import MagicMock, patch

import pytest

from src.kernel.types import HealthStatus, PluginState
from src.plugins.exchange_connector.plugin import (
    ExchangeConnectorPlugin,
)

import sys


class TestExchangeConnectorInit:
    """测试插件初始化"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )

    def test_init_basic(self) -> None:
        """测试基本初始化"""
        assert self.plugin.name == "exchange_connector"

    def test_init_state(self) -> None:
        """测试初始化状态"""
        assert self.plugin._state == PluginState.UNLOADED

    def test_init_with_config(self) -> None:
        """测试带配置的初始化"""
        config = {
            "default_exchange": "bybit",
            "request_timeout": 60,
        }
        plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
            config=config,
        )
        assert plugin._config == config


class TestExchangeConnectorLoad:
    """测试插件加载"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
            config={
                "default_exchange": "binance",
                "request_timeout": 30,
                "max_retries": 3,
            },
        )

    def test_load_success(self) -> None:
        """测试成功加载"""
        self.plugin.on_load()
        assert self.plugin._default_exchange == "binance"
        assert self.plugin._request_timeout == 30
        assert self.plugin._max_retries == 3
        assert self.plugin._exchanges == {}
        assert self.plugin._fetch_count == 0
        assert self.plugin._error_count == 0

    def test_load_default_config(self) -> None:
        """测试默认配置加载"""
        plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )
        plugin.on_load()
        assert plugin._default_exchange == "binance"
        assert plugin._request_timeout == 30
        assert plugin._enable_rate_limit is True
        assert plugin._max_retries == 3
        assert plugin._retry_delay == 1.0
        assert plugin._api_key == ""
        assert plugin._api_secret == ""
        assert plugin._proxy == ""

    def test_load_custom_config(self) -> None:
        """测试自定义配置加载"""
        plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
            config={
                "default_exchange": "okx",
                "request_timeout": 60,
                "enable_rate_limit": False,
                "max_retries": 5,
                "retry_delay": 2.0,
                "api_key": "test_key",
                "api_secret": "test_secret",
                "proxy": "http://proxy:8080",
                "supported_exchanges": ["binance", "okx"],
            },
        )
        plugin.on_load()
        assert plugin._default_exchange == "okx"
        assert plugin._request_timeout == 60
        assert plugin._enable_rate_limit is False
        assert plugin._max_retries == 5
        assert plugin._retry_delay == 2.0
        assert plugin._api_key == "test_key"
        assert plugin._api_secret == "test_secret"
        assert plugin._proxy == "http://proxy:8080"
        assert plugin._supported_exchanges == ["binance", "okx"]

    def test_load_initializes_empty_exchanges(self) -> None:
        """测试加载后交易所缓存为空"""
        self.plugin.on_load()
        assert len(self.plugin._exchanges) == 0
        assert len(self.plugin._connection_status) == 0


class TestExchangeConnectorUnload:
    """测试插件卸载"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )
        self.plugin.on_load()

    def test_unload_clears_exchanges(self) -> None:
        """测试卸载清除交易所缓存"""
        # 模拟已连接的交易所
        self.plugin._exchanges = {"binance": MagicMock()}
        self.plugin._connection_status = {
            "binance": {"status": "connected"}
        }

        self.plugin.on_unload()

        assert len(self.plugin._exchanges) == 0
        assert len(self.plugin._connection_status) == 0

    def test_unload_empty(self) -> None:
        """测试空状态卸载"""
        self.plugin.on_unload()
        assert len(self.plugin._exchanges) == 0


class TestExchangeConnectorConfig:
    """测试配置更新"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
            config=MagicMock(),
        )
        self.plugin.on_load()

    def test_config_update_default_exchange(self) -> None:
        """测试更新默认交易所"""
        self.plugin.on_config_update(
            {"default_exchange": "bybit"}
        )
        assert self.plugin._default_exchange == "bybit"

    def test_config_update_timeout(self) -> None:
        """测试更新超时时间"""
        self.plugin.on_config_update({"request_timeout": 60})
        assert self.plugin._request_timeout == 60

    def test_config_update_max_retries(self) -> None:
        """测试更新最大重试次数"""
        self.plugin.on_config_update({"max_retries": 5})
        assert self.plugin._max_retries == 5

    def test_config_update_proxy_clears_cache(self) -> None:
        """测试更新代理时清除交易所缓存"""
        self.plugin._exchanges = {"binance": MagicMock()}
        self.plugin._connection_status = {
            "binance": {"status": "connected"}
        }

        self.plugin.on_config_update(
            {"proxy": "http://new-proxy:8080"}
        )

        assert self.plugin._proxy == "http://new-proxy:8080"
        assert len(self.plugin._exchanges) == 0
        assert len(self.plugin._connection_status) == 0


class TestExchangeConnectorHealth:
    """测试健康检查"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )
        self.plugin.on_load()

    def test_health_healthy(self) -> None:
        """测试健康状态"""
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert "正常" in result.message

    def test_health_degraded(self) -> None:
        """测试降级状态"""
        self.plugin._error_count = 6
        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "6" in result.message

    def test_health_unhealthy(self) -> None:
        """测试不健康状态"""
        self.plugin._error_count = 11
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "11" in result.message

    def test_health_details(self) -> None:
        """测试健康检查详情"""
        self.plugin._fetch_count = 10
        self.plugin._error_count = 2
        self.plugin._last_error = "timeout"
        self.plugin._exchanges = {"binance": MagicMock()}

        result = self.plugin.health_check()
        assert result.details["connected_exchanges"] == 1
        assert result.details["fetch_count"] == 10
        assert result.details["error_count"] == 2
        assert result.details["last_error"] == "timeout"


class TestExchangeConnectorGetExchange:
    """测试获取交易所实例"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
            config={
                "default_exchange": "binance",
                "api_key": "test_key",
                "api_secret": "test_secret",
                "proxy": "http://proxy:8080",
            },
        )
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_get_exchange_default(self) -> None:
        """测试获取默认交易所"""
        mock_ccxt = MagicMock()
        mock_exchange = MagicMock()
        mock_ccxt.binance = MagicMock(
            return_value=mock_exchange
        )

        with patch.dict(
            sys.modules, {"ccxt": mock_ccxt}
        ):
            result = self.plugin.get_exchange()

        assert result == mock_exchange
        assert "binance" in self.plugin._exchanges
        self.plugin.emit_event.assert_called_once()

    def test_get_exchange_named(self) -> None:
        """测试获取指定交易所"""
        mock_ccxt = MagicMock()
        mock_exchange = MagicMock()
        mock_ccxt.bybit = MagicMock(
            return_value=mock_exchange
        )

        with patch.dict(
            sys.modules, {"ccxt": mock_ccxt}
        ):
            result = self.plugin.get_exchange("bybit")

        assert result == mock_exchange
        assert "bybit" in self.plugin._exchanges

    def test_get_exchange_cached(self) -> None:
        """测试交易所实例缓存"""
        mock_exchange = MagicMock()
        self.plugin._exchanges["binance"] = mock_exchange

        mock_ccxt = MagicMock()
        with patch.dict(
            sys.modules, {"ccxt": mock_ccxt}
        ):
            result = self.plugin.get_exchange("binance")

        assert result == mock_exchange

    def test_get_exchange_unsupported(self) -> None:
        """测试不支持的交易所"""
        with pytest.raises(ValueError, match="不支持"):
            self.plugin.get_exchange("unknown_exchange")

    def test_get_exchange_ccxt_not_found(self) -> None:
        """测试ccxt不支持的交易所"""
        mock_ccxt = MagicMock(spec=[])

        with patch.dict(
            sys.modules, {"ccxt": mock_ccxt}
        ):
            with pytest.raises(
                ValueError, match="ccxt不支持"
            ):
                self.plugin.get_exchange("binance")

    def test_get_exchange_connection_error(self) -> None:
        """测试连接错误"""
        mock_ccxt = MagicMock()
        mock_ccxt.binance = MagicMock(
            side_effect=RuntimeError("network error")
        )

        with patch.dict(
            sys.modules, {"ccxt": mock_ccxt}
        ):
            with pytest.raises(
                ConnectionError, match="无法连接"
            ):
                self.plugin.get_exchange("binance")

        assert self.plugin._error_count == 1

    def test_get_exchange_with_api_keys(self) -> None:
        """测试带API密钥的连接"""
        mock_ccxt = MagicMock()
        mock_exchange = MagicMock()
        mock_ccxt.binance = MagicMock(
            return_value=mock_exchange
        )

        with patch.dict(
            sys.modules, {"ccxt": mock_ccxt}
        ):
            self.plugin.get_exchange("binance")

        call_args = mock_ccxt.binance.call_args[0][0]
        assert call_args["apiKey"] == "test_key"
        assert call_args["secret"] == "test_secret"
        assert "proxies" in call_args

    def test_get_exchange_connection_status(self) -> None:
        """测试连接状态记录"""
        mock_ccxt = MagicMock()
        mock_ccxt.binance = MagicMock(
            return_value=MagicMock()
        )

        with patch.dict(
            sys.modules, {"ccxt": mock_ccxt}
        ):
            self.plugin.get_exchange("binance")

        status = self.plugin._connection_status["binance"]
        assert status["status"] == "connected"
        assert status["error_count"] == 0

    def _plugin_exchanges(self):
        return self.plugin._exchanges


class TestExchangeConnectorDisconnect:
    """测试断开连接"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_disconnect_single(self) -> None:
        """测试断开单个交易所"""
        self.plugin._exchanges["binance"] = MagicMock()
        self.plugin._connection_status["binance"] = {
            "status": "connected"
        }

        self.plugin.disconnect("binance")

        assert "binance" not in self.plugin._exchanges
        assert (
            "binance"
            not in self.plugin._connection_status
        )
        self.plugin.emit_event.assert_called_once_with(
            "exchange.disconnected",
            {"exchange": "binance"},
        )

    def test_disconnect_all(self) -> None:
        """测试断开所有交易所"""
        self.plugin._exchanges["binance"] = MagicMock()
        self.plugin._exchanges["bybit"] = MagicMock()
        self.plugin._connection_status["binance"] = {
            "status": "connected"
        }
        self.plugin._connection_status["bybit"] = {
            "status": "connected"
        }

        self.plugin.disconnect()

        assert len(self.plugin._exchanges) == 0
        assert len(self.plugin._connection_status) == 0
        assert self.plugin.emit_event.call_count == 2

    def test_disconnect_nonexistent(self) -> None:
        """测试断开不存在的交易所"""
        self.plugin.disconnect("nonexistent")
        self.plugin.emit_event.assert_not_called()

    def test_disconnect_empty(self) -> None:
        """测试空状态断开所有"""
        self.plugin.disconnect()
        assert len(self.plugin._exchanges) == 0


class TestExchangeConnectorFetchOhlcv:
    """测试OHLCV数据获取"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
            config={"max_retries": 3, "retry_delay": 0.01},
        )
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)
        # mock get_exchange 避免 ccxt 导入
        self.mock_exchange = MagicMock()
        self.plugin.get_exchange = MagicMock(
            return_value=self.mock_exchange
        )

    def test_fetch_ohlcv_success(self) -> None:
        """测试成功获取OHLCV"""
        self.mock_exchange.fetch_ohlcv.return_value = [
            [1700000000000, 100, 110, 90, 105, 1000],
            [1700003600000, 105, 115, 95, 110, 1200],
        ]

        df = self.plugin.fetch_ohlcv("BTC/USDT")

        assert len(df) == 2
        assert list(df.columns) == [
            "open", "high", "low", "close", "volume"
        ]
        assert df.index.name == "timestamp"
        assert self.plugin._fetch_count == 1

    def test_fetch_ohlcv_params(self) -> None:
        """测试OHLCV参数传递"""
        self.mock_exchange.fetch_ohlcv.return_value = [
            [1700000000000, 100, 110, 90, 105, 1000],
        ]

        self.plugin.fetch_ohlcv(
            "ETH/USDT",
            timeframe="4h",
            since=1700000000000,
            limit=50,
            exchange_name="bybit",
        )

        self.mock_exchange.fetch_ohlcv.assert_called_once_with(
            "ETH/USDT",
            timeframe="4h",
            since=1700000000000,
            limit=50,
        )

    def test_fetch_ohlcv_emits_event(self) -> None:
        """测试OHLCV获取后发送事件"""
        self.mock_exchange.fetch_ohlcv.return_value = [
            [1700000000000, 100, 110, 90, 105, 1000],
        ]

        self.plugin.fetch_ohlcv("BTC/USDT")

        self.plugin.emit_event.assert_called_once()
        call_args = self.plugin.emit_event.call_args
        assert call_args[0][0] == "exchange.ohlcv_fetched"
        assert call_args[0][1]["symbol"] == "BTC/USDT"

    @patch(
        "src.plugins.exchange_connector.plugin.time.sleep"
    )
    def test_fetch_ohlcv_retry(self, mock_sleep) -> None:
        """测试OHLCV获取重试"""
        self.mock_exchange.fetch_ohlcv.side_effect = [
            RuntimeError("timeout"),
            [[1700000000000, 100, 110, 90, 105, 1000]],
        ]

        df = self.plugin.fetch_ohlcv("BTC/USDT")

        assert len(df) == 1
        assert mock_sleep.call_count == 1
        assert self.plugin._error_count == 1

    @patch(
        "src.plugins.exchange_connector.plugin.time.sleep"
    )
    def test_fetch_ohlcv_all_retries_fail(
        self, mock_sleep
    ) -> None:
        """测试OHLCV所有重试都失败"""
        self.mock_exchange.fetch_ohlcv.side_effect = (
            RuntimeError("timeout")
        )

        with pytest.raises(
            RuntimeError, match="获取OHLCV失败"
        ):
            self.plugin.fetch_ohlcv("BTC/USDT")

        assert self.plugin._error_count == 3
        # 最后一次重试不 sleep
        assert mock_sleep.call_count == 2

    def test_fetch_ohlcv_sorted_index(self) -> None:
        """测试OHLCV结果按时间排序"""
        self.mock_exchange.fetch_ohlcv.return_value = [
            [1700007200000, 110, 120, 100, 115, 800],
            [1700000000000, 100, 110, 90, 105, 1000],
            [1700003600000, 105, 115, 95, 110, 1200],
        ]

        df = self.plugin.fetch_ohlcv("BTC/USDT")

        assert df.index.is_monotonic_increasing


class TestExchangeConnectorFetchTicker:
    """测试Ticker数据获取"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)
        self.mock_exchange = MagicMock()
        self.plugin.get_exchange = MagicMock(
            return_value=self.mock_exchange
        )

    def test_fetch_ticker_success(self) -> None:
        """测试成功获取Ticker"""
        self.mock_exchange.fetch_ticker.return_value = {
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
        }

        result = self.plugin.fetch_ticker("BTC/USDT")

        assert result["last"] == 50000.0
        assert self.plugin._fetch_count == 1

    def test_fetch_ticker_emits_event(self) -> None:
        """测试Ticker获取后发送事件"""
        self.mock_exchange.fetch_ticker.return_value = {
            "last": 50000.0,
        }

        self.plugin.fetch_ticker("BTC/USDT")

        self.plugin.emit_event.assert_called_once()
        call_args = self.plugin.emit_event.call_args
        assert call_args[0][0] == "exchange.ticker_fetched"
        assert call_args[0][1]["price"] == 50000.0

    def test_fetch_ticker_error(self) -> None:
        """测试Ticker获取失败"""
        self.mock_exchange.fetch_ticker.side_effect = (
            RuntimeError("API error")
        )

        with pytest.raises(
            RuntimeError, match="获取Ticker失败"
        ):
            self.plugin.fetch_ticker("BTC/USDT")

        assert self.plugin._error_count == 1

    def test_fetch_ticker_error_emits_event(self) -> None:
        """测试Ticker错误发送事件"""
        self.mock_exchange.fetch_ticker.side_effect = (
            RuntimeError("API error")
        )

        with pytest.raises(RuntimeError):
            self.plugin.fetch_ticker("BTC/USDT")

        # 应该发送 exchange.error 事件
        call_args = self.plugin.emit_event.call_args
        assert call_args[0][0] == "exchange.error"
        assert call_args[0][1]["operation"] == "fetch_ticker"


class TestExchangeConnectorAsync:
    """测试异步OHLCV获取"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)
        self.mock_exchange = MagicMock()
        self.plugin.get_exchange = MagicMock(
            return_value=self.mock_exchange
        )

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_async_success(self) -> None:
        """测试异步获取OHLCV"""
        import pandas as pd

        self.mock_exchange.fetch_ohlcv.return_value = [
            [1700000000000, 100, 110, 90, 105, 1000],
        ]

        df = await self.plugin.fetch_ohlcv_async("BTC/USDT")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_async_params(self) -> None:
        """测试异步获取OHLCV参数传递"""
        self.mock_exchange.fetch_ohlcv.return_value = [
            [1700000000000, 100, 110, 90, 105, 1000],
        ]

        await self.plugin.fetch_ohlcv_async(
            "ETH/USDT",
            timeframe="1h",
            limit=100,
        )

        self.mock_exchange.fetch_ohlcv.assert_called_once()


class TestExchangeConnectorQueries:
    """测试查询方法"""

    def setup_method(self) -> None:
        """测试初始化"""
        self.plugin = ExchangeConnectorPlugin(
            name="exchange_connector",
        )
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_get_supported_exchanges(self) -> None:
        """测试获取支持的交易所列表"""
        result = self.plugin.get_supported_exchanges()

        assert isinstance(result, list)
        assert "binance" in result
        assert "bybit" in result

    def test_get_connected_exchanges_empty(self) -> None:
        """测试无连接时获取已连接交易所"""
        result = self.plugin.get_connected_exchanges()

        assert result == []

    def test_get_connected_exchanges_with_data(
        self,
    ) -> None:
        """测试有连接时获取已连接交易所"""
        self.plugin._exchanges["binance"] = MagicMock()
        self.plugin._exchanges["bybit"] = MagicMock()

        result = self.plugin.get_connected_exchanges()

        assert len(result) == 2
        assert "binance" in result
        assert "bybit" in result

    def test_get_connection_status_empty(self) -> None:
        """测试无连接时获取连接状态"""
        result = self.plugin.get_connection_status()

        assert result == {}

    def test_get_connection_status_with_data(
        self,
    ) -> None:
        """测试有连接时获取连接状态"""
        from datetime import datetime

        self.plugin._exchanges["binance"] = MagicMock()
        self.plugin._connection_status["binance"] = {
            "status": "connected",
            "connected_at": datetime(2026, 1, 1),
            "error_count": 2,
        }

        result = self.plugin.get_connection_status()

        assert "binance" in result
        assert result["binance"]["status"] == "connected"
        assert result["binance"]["error_count"] == 2

    def test_get_statistics(self) -> None:
        """测试获取统计信息"""
        self.plugin._fetch_count = 42
        self.plugin._error_count = 3
        self.plugin._last_error = "timeout"

        result = self.plugin.get_statistics()

        assert result["fetch_count"] == 42
        assert result["error_count"] == 3
        assert result["last_error"] == "timeout"
        assert result["connected_exchanges"] == 0

    def test_get_statistics_with_connections(
        self,
    ) -> None:
        """测试有连接时的统计信息"""
        self.plugin._exchanges["binance"] = MagicMock()

        result = self.plugin.get_statistics()

        assert result["connected_exchanges"] == 1
        assert result["default_exchange"] == "binance"
