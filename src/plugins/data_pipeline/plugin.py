"""数据管道插件

将 DataPipeline 包装为标准插件，提供：
1. 生命周期管理（on_load / on_unload）
2. 事件驱动：发布 data_pipeline.ohlcv_ready 事件
3. 配置热更新
4. 健康检查
5. 数据质量验证与告警

核心逻辑复用 src/plugins/data_pipeline/data_pipeline.py 中的 DataPipeline 类。
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class DataPipelinePlugin(BasePlugin):
    """数据管道插件

    封装 DataPipeline，通过事件总线与其他插件通信。
    获取到 OHLCV 数据后自动发布 data_pipeline.ohlcv_ready 事件，
    供 market_regime 等下游插件消费。

    Attributes:
        pipeline: DataPipeline 实例（惰性导入避免循环依赖）
        _fetch_count: 数据获取计数
    """

    def __init__(
        self,
        name: str = "data_pipeline",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name=name, config=config)
        self.pipeline: Any = None
        self._fetch_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件：初始化 DataPipeline 并订阅事件"""
        # 惰性导入，避免在插件发现阶段触发外部依赖
        from src.plugins.data_pipeline.data_pipeline import DataPipeline

        self.pipeline = DataPipeline(config=self._config)
        self._fetch_count = 0
        self._last_error = None

        # 订阅 orchestrator 的数据刷新请求事件
        self.subscribe_event(
            "orchestrator.data_refresh_requested",
            self._on_data_refresh_requested,
        )

        self._logger.info(
            "DataPipelinePlugin 已加载，缓存=%s，验证=%s",
            self._config.get("enable_cache", True),
            self._config.get("enable_validation", True),
        )

    def on_unload(self) -> None:
        """卸载插件：清理资源"""
        self.pipeline = None
        self._fetch_count = 0
        self._last_error = None
        self._logger.info("DataPipelinePlugin 已卸载")

    def on_config_update(
        self, new_config: Dict[str, Any]
    ) -> None:
        """配置热更新：重新创建 DataPipeline"""
        self._config = new_config
        if self.pipeline is not None:
            from src.plugins.data_pipeline.data_pipeline import DataPipeline

            self.pipeline = DataPipeline(config=new_config)
            self._logger.info(
                "DataPipelinePlugin 配置已热更新"
            )

    def health_check(self) -> HealthCheckResult:
        """健康检查：验证 pipeline 是否正常"""
        base_check = super().health_check()
        if base_check.status != HealthStatus.HEALTHY:
            return base_check

        if self.pipeline is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="DataPipeline 未初始化",
            )

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近错误: {self._last_error}",
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"运行正常，已获取 {self._fetch_count} 次数据",
        )

    # ---- 公共 API ----

    async def async_fetch_data(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 1000,
        **kwargs: Any,
    ) -> Optional[pd.DataFrame]:
        """异步获取 OHLCV 数据并发布事件

        Args:
            symbol: 交易对（如 "BTC/USDT"）
            timeframe: 时间框架（如 "1h", "4h", "1d"）
            limit: 数据条数限制
            **kwargs: 传递给 DataPipeline 的额外参数

        Returns:
            OHLCV DataFrame，失败时返回 None
        """
        if self.pipeline is None:
            raise RuntimeError(
                "DataPipelinePlugin 未加载，无法获取数据"
            )

        try:
            from src.plugins.data_pipeline.data_pipeline import (
                DataRequest,
                DataSource,
                Timeframe,
            )

            tf_map = {v.value: v for v in Timeframe}
            tf_enum = tf_map.get(timeframe, Timeframe.H1)

            request = DataRequest(
                symbol=symbol,
                timeframe=tf_enum,
                limit=limit,
                source=kwargs.get("source", DataSource.CCXT),
                exchange=kwargs.get("exchange", "binance"),
            )

            df = await self.pipeline.fetch_data(request)

            self._fetch_count += 1
            self._last_error = None

            self._publish_ohlcv_ready(df, symbol, timeframe)

            return df

        except Exception as e:
            self._last_error = str(e)
            self._logger.error(
                "数据获取失败 [%s %s]: %s",
                symbol,
                timeframe,
                e,
            )
            self.emit_event(
                "data_pipeline.source_error",
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "error": str(e),
                },
            )
            return None

    def fetch_data(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 1000,
        **kwargs: Any,
    ) -> Optional[pd.DataFrame]:
        """同步获取 OHLCV 数据并发布事件

        Args:
            symbol: 交易对（如 "BTC/USDT"）
            timeframe: 时间框架（如 "1h", "4h", "1d"）
            limit: 数据条数限制
            **kwargs: 传递给 DataPipeline 的额外参数

        Returns:
            OHLCV DataFrame，失败时返回 None

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self.pipeline is None:
            raise RuntimeError(
                "DataPipelinePlugin 未加载，无法获取数据"
            )

        try:
            from src.plugins.data_pipeline.data_pipeline import (
                DataRequest,
                DataSource,
                Timeframe,
            )

            # 构建请求
            tf_map = {v.value: v for v in Timeframe}
            tf_enum = tf_map.get(
                timeframe, Timeframe.H1
            )

            request = DataRequest(
                symbol=symbol,
                timeframe=tf_enum,
                limit=limit,
                source=kwargs.get(
                    "source", DataSource.CCXT
                ),
                exchange=kwargs.get(
                    "exchange", "binance"
                ),
            )

            # 使用 asyncio 运行异步方法
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 已有事件循环运行中，使用 nest_asyncio 或创建 Future
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    df = pool.submit(
                        asyncio.run,
                        self.pipeline.fetch_data(request),
                    ).result()
            else:
                # 无事件循环，安全创建新的
                df = asyncio.run(
                    self.pipeline.fetch_data(request)
                )

            self._fetch_count += 1
            self._last_error = None

            # 发布数据就绪事件
            self._publish_ohlcv_ready(
                df, symbol, timeframe
            )

            return df

        except Exception as e:
            self._last_error = str(e)
            self._logger.error(
                "数据获取失败 [%s %s]: %s",
                symbol,
                timeframe,
                e,
            )
            self.emit_event(
                "data_pipeline.source_error",
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "error": str(e),
                },
            )
            return None

    def validate_data(
        self, df: pd.DataFrame, symbol: str
    ) -> Dict[str, Any]:
        """验证数据质量

        Args:
            df: OHLCV DataFrame
            symbol: 交易对

        Returns:
            验证结果字典

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self.pipeline is None:
            raise RuntimeError(
                "DataPipelinePlugin 未加载"
            )

        result = self.pipeline.validate_data_quality(
            df, symbol
        )

        # 如果数据质量有问题，发布告警
        if not result.get("is_valid", True):
            self.emit_event(
                "data_pipeline.data_quality_alert",
                {
                    "symbol": symbol,
                    "issues": result.get("issues", []),
                    "quality_score": result.get(
                        "quality_score", 0
                    ),
                },
            )

        return result

    def get_statistics(self) -> Dict[str, Any]:
        """获取管道统计信息"""
        if self.pipeline is None:
            return {
                "status": "not_loaded",
                "fetch_count": 0,
            }
        stats = self.pipeline.get_statistics()
        stats["fetch_count"] = self._fetch_count
        return stats

    # ---- 内部方法 ----

    def _on_data_refresh_requested(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理 orchestrator 的数据刷新请求事件

        从事件数据中提取 symbol 和 timeframes，
        逐个获取数据并发布 ohlcv_ready 事件。

        Args:
            event_name: 事件名称
            data: 事件数据，包含 symbol 和 timeframes
        """
        symbol = data.get("symbol", "")
        timeframes = data.get("timeframes", ["1h"])

        if not symbol:
            self._logger.warning(
                "数据刷新请求缺少 symbol 参数"
            )
            return

        self._logger.debug(
            "收到数据刷新请求: %s, timeframes=%s",
            symbol,
            timeframes,
        )

        for tf in timeframes:
            try:
                df = self.fetch_data(
                    symbol=symbol,
                    timeframe=tf,
                )
                if df is not None:
                    self._logger.debug(
                        "数据获取成功: %s %s (%d 行)",
                        symbol,
                        tf,
                        len(df),
                    )
                else:
                    self._logger.warning(
                        "数据获取返回 None: %s %s",
                        symbol,
                        tf,
                    )
            except (RuntimeError, ValueError, KeyError) as e:
                self._logger.error(
                    "数据刷新失败 [%s %s]: %s",
                    symbol,
                    tf,
                    e,
                )
                self.emit_event(
                    "data_pipeline.fetch_error",
                    {
                        "symbol": symbol,
                        "timeframe": tf,
                        "error": str(e),
                    },
                )

    def _publish_ohlcv_ready(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> None:
        """发布 OHLCV 数据就绪事件"""
        self.emit_event(
            "data_pipeline.ohlcv_ready",
            {
                "df": df,
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": len(df),
            },
        )
