"""交易所连接器插件 - 管理加密货币交易所连接

封装ccxt库，提供统一的交易所连接管理、OHLCV数据获取、
Ticker查询等功能。支持多交易所、速率限制、重试机制。
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class ExchangeConnectorPlugin(BasePlugin):
    """交易所连接器插件

    功能：
    1. 多交易所连接管理（ccxt）
    2. OHLCV数据获取
    3. Ticker数据查询
    4. 连接状态监控
    5. 自动重试与速率限制
    """

    def on_load(self) -> None:
        """加载插件，初始化交易所连接管理器"""
        config = self._config or {}

        # 配置参数
        self._default_exchange: str = config.get(
            "default_exchange", "binance"
        )
        self._request_timeout: int = config.get(
            "request_timeout", 30
        )
        self._enable_rate_limit: bool = config.get(
            "enable_rate_limit", True
        )
        self._max_retries: int = config.get("max_retries", 3)
        self._retry_delay: float = config.get("retry_delay", 1.0)
        self._api_key: str = config.get("api_key", "")
        self._api_secret: str = config.get("api_secret", "")
        self._proxy: str = config.get("proxy", "")
        self._supported_exchanges: List[str] = config.get(
            "supported_exchanges",
            ["binance", "bybit", "okx", "coinbase", "kraken"],
        )

        # 交易所实例缓存
        self._exchanges: Dict[str, Any] = {}

        # 连接状态
        self._connection_status: Dict[str, Dict[str, Any]] = {}

        # 统计信息
        self._fetch_count: int = 0
        self._error_count: int = 0
        self._last_error: Optional[str] = None
        self._last_fetch_time: Optional[datetime] = None

        logger.info(
            "交易所连接器插件已加载, 默认交易所: %s",
            self._default_exchange,
        )

    def on_unload(self) -> None:
        """卸载插件，关闭所有交易所连接"""
        exchange_count = len(self._exchanges)
        self._exchanges.clear()
        self._connection_status.clear()
        logger.info(
            "交易所连接器插件已卸载, 关闭 %d 个连接",
            exchange_count,
        )

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """处理配置更新

        Args:
            new_config: 新的配置字典
        """
        self._config.update(new_config)

        # 更新关键配置
        if "default_exchange" in new_config:
            self._default_exchange = new_config["default_exchange"]
        if "request_timeout" in new_config:
            self._request_timeout = new_config["request_timeout"]
        if "max_retries" in new_config:
            self._max_retries = new_config["max_retries"]
        if "proxy" in new_config:
            self._proxy = new_config["proxy"]
            # 代理变更时清除缓存的交易所实例
            self._exchanges.clear()
            self._connection_status.clear()

        logger.info("交易所连接器配置已更新")

    def health_check(self) -> HealthCheckResult:
        """健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        details: Dict[str, Any] = {
            "connected_exchanges": len(self._exchanges),
            "fetch_count": self._fetch_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

        if self._error_count > 10:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"错误过多: {self._error_count}",
                details=details,
            )

        if self._error_count > 5:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"存在错误: {self._error_count}",
                details=details,
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="交易所连接器运行正常",
            details=details,
        )

    def get_exchange(
        self, exchange_name: Optional[str] = None
    ) -> Any:
        """获取交易所实例（惰性初始化）

        Args:
            exchange_name: 交易所名称，默认使用配置的默认交易所

        Returns:
            ccxt.Exchange实例

        Raises:
            ValueError: 交易所不受支持
            ConnectionError: 无法创建交易所实例
        """
        import ccxt

        name = exchange_name or self._default_exchange

        if name not in self._supported_exchanges:
            raise ValueError(
                f"不支持的交易所: {name}, "
                f"支持: {self._supported_exchanges}"
            )

        if name not in self._exchanges:
            try:
                exchange_class = getattr(ccxt, name)
                config: Dict[str, Any] = {
                    "enableRateLimit": self._enable_rate_limit,
                    "timeout": self._request_timeout * 1000,
                }

                if self._api_key:
                    config["apiKey"] = self._api_key
                if self._api_secret:
                    config["secret"] = self._api_secret
                if self._proxy:
                    config["proxies"] = {
                        "http": self._proxy,
                        "https": self._proxy,
                    }

                exchange = exchange_class(config)
                self._exchanges[name] = exchange
                self._connection_status[name] = {
                    "status": "connected",
                    "connected_at": datetime.now(),
                    "error_count": 0,
                }

                self.emit_event(
                    "exchange.connected",
                    {"exchange": name},
                )
                logger.info("交易所 %s 连接成功", name)

            except AttributeError:
                raise ValueError(
                    f"ccxt不支持交易所: {name}"
                )
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                self.emit_event(
                    "exchange.error",
                    {
                        "exchange": name,
                        "error": str(e),
                        "operation": "connect",
                    },
                )
                raise ConnectionError(
                    f"无法连接交易所 {name}: {e}"
                ) from e

        return self._exchanges[name]

    def disconnect(
        self, exchange_name: Optional[str] = None
    ) -> None:
        """断开交易所连接

        Args:
            exchange_name: 交易所名称，None则断开所有
        """
        if exchange_name:
            if exchange_name in self._exchanges:
                del self._exchanges[exchange_name]
                del self._connection_status[exchange_name]
                self.emit_event(
                    "exchange.disconnected",
                    {"exchange": exchange_name},
                )
                logger.info(
                    "交易所 %s 已断开", exchange_name
                )
        else:
            names = list(self._exchanges.keys())
            self._exchanges.clear()
            self._connection_status.clear()
            for name in names:
                self.emit_event(
                    "exchange.disconnected",
                    {"exchange": name},
                )
            logger.info("所有交易所已断开")

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: int = 100,
        exchange_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """获取OHLCV数据

        Args:
            symbol: 交易对，如 "BTC/USDT"
            timeframe: 时间框架，如 "1h", "4h", "1d"
            since: 起始时间戳（毫秒）
            limit: 数据条数限制
            exchange_name: 交易所名称

        Returns:
            包含OHLCV数据的DataFrame

        Raises:
            ConnectionError: 交易所连接失败
            RuntimeError: 数据获取失败
        """
        exchange = self.get_exchange(exchange_name)
        name = exchange_name or self._default_exchange

        last_error = None
        for attempt in range(self._max_retries):
            try:
                ohlcv = exchange.fetch_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    since=since,
                    limit=limit,
                )

                df = pd.DataFrame(
                    ohlcv,
                    columns=[
                        "timestamp",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                    ],
                )

                df["timestamp"] = pd.to_datetime(
                    df["timestamp"], unit="ms"
                )
                df.set_index("timestamp", inplace=True)
                df.sort_index(inplace=True)

                self._fetch_count += 1
                self._last_fetch_time = datetime.now()

                self.emit_event(
                    "exchange.ohlcv_fetched",
                    {
                        "exchange": name,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "rows": len(df),
                    },
                )

                return df

            except Exception as e:
                last_error = e
                self._error_count += 1
                self._last_error = str(e)

                if attempt < self._max_retries - 1:
                    time.sleep(
                        self._retry_delay * (attempt + 1)
                    )
                    logger.warning(
                        "获取OHLCV重试 %d/%d: %s",
                        attempt + 1,
                        self._max_retries,
                        e,
                    )

        self.emit_event(
            "exchange.error",
            {
                "exchange": name,
                "error": str(last_error),
                "operation": "fetch_ohlcv",
                "symbol": symbol,
            },
        )
        raise RuntimeError(
            f"获取OHLCV失败 ({name}/{symbol}): {last_error}"
        ) from last_error

    def fetch_ticker(
        self,
        symbol: str,
        exchange_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取Ticker数据

        Args:
            symbol: 交易对，如 "BTC/USDT"
            exchange_name: 交易所名称

        Returns:
            Ticker数据字典

        Raises:
            ConnectionError: 交易所连接失败
            RuntimeError: 数据获取失败
        """
        exchange = self.get_exchange(exchange_name)
        name = exchange_name or self._default_exchange

        try:
            ticker = exchange.fetch_ticker(symbol)

            self._fetch_count += 1
            self._last_fetch_time = datetime.now()

            self.emit_event(
                "exchange.ticker_fetched",
                {
                    "exchange": name,
                    "symbol": symbol,
                    "price": ticker.get("last"),
                },
            )

            return ticker

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            self.emit_event(
                "exchange.error",
                {
                    "exchange": name,
                    "error": str(e),
                    "operation": "fetch_ticker",
                    "symbol": symbol,
                },
            )
            raise RuntimeError(
                f"获取Ticker失败 ({name}/{symbol}): {e}"
            ) from e

    async def fetch_ohlcv_async(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: int = 100,
        exchange_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """异步获取OHLCV数据

        Args:
            symbol: 交易对
            timeframe: 时间框架
            since: 起始时间戳（毫秒）
            limit: 数据条数限制
            exchange_name: 交易所名称

        Returns:
            包含OHLCV数据的DataFrame
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.fetch_ohlcv(
                symbol, timeframe, since, limit, exchange_name
            ),
        )

    def get_supported_exchanges(self) -> List[str]:
        """获取支持的交易所列表

        Returns:
            支持的交易所名称列表
        """
        return list(self._supported_exchanges)

    def get_connected_exchanges(self) -> List[str]:
        """获取已连接的交易所列表

        Returns:
            已连接的交易所名称列表
        """
        return list(self._exchanges.keys())

    def get_connection_status(self) -> Dict[str, Any]:
        """获取所有交易所的连接状态

        Returns:
            连接状态字典
        """
        result: Dict[str, Any] = {}
        for name, status in self._connection_status.items():
            result[name] = {
                "status": status["status"],
                "connected_at": (
                    status["connected_at"].isoformat()
                    if status.get("connected_at")
                    else None
                ),
                "error_count": status.get("error_count", 0),
            }
        return result

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "connected_exchanges": len(self._exchanges),
            "supported_exchanges": len(
                self._supported_exchanges
            ),
            "fetch_count": self._fetch_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "last_fetch_time": (
                self._last_fetch_time.isoformat()
                if self._last_fetch_time
                else None
            ),
            "default_exchange": self._default_exchange,
        }
