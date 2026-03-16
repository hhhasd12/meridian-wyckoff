"""data_pipeline 插件测试

测试 DataPipelinePlugin 的生命周期、事件发布、
健康检查、配置热更新等功能。
使用 mock 替代真实的 DataPipeline 和外部依赖。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import (
    HealthCheckResult,
    HealthStatus,
    PluginState,
)
from src.plugins.data_pipeline.plugin import (
    DataPipelinePlugin,
)


# ---- 测试辅助 ----


def _make_ohlcv_df(rows: int = 100) -> pd.DataFrame:
    """生成模拟 OHLCV DataFrame"""
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(rows) * 0.5)
    return pd.DataFrame(
        {
            "open": close - np.random.rand(rows) * 0.3,
            "high": close + np.random.rand(rows) * 0.5,
            "low": close - np.random.rand(rows) * 0.5,
            "close": close,
            "volume": np.random.randint(
                1000, 10000, rows
            ),
        }
    )


class TestDataPipelinePluginInit:
    """测试插件初始化"""

    def test_inherits_base_plugin(self) -> None:
        """验证继承自 BasePlugin"""
        plugin = DataPipelinePlugin()
        assert isinstance(plugin, BasePlugin)

    def test_default_name(self) -> None:
        """验证默认名称"""
        plugin = DataPipelinePlugin()
        assert plugin.name == "data_pipeline"

    def test_custom_name(self) -> None:
        """验证自定义名称"""
        plugin = DataPipelinePlugin(
            name="custom_pipeline"
        )
        assert plugin.name == "custom_pipeline"

    def test_default_config(self) -> None:
        """验证默认配置"""
        plugin = DataPipelinePlugin()
        assert plugin.config == {}

    def test_custom_config(self) -> None:
        """验证自定义配置"""
        cfg = {"redis_host": "10.0.0.1", "cache_ttl": 7200}
        plugin = DataPipelinePlugin(config=cfg)
        assert plugin.config["redis_host"] == "10.0.0.1"
        assert plugin.config["cache_ttl"] == 7200

    def test_pipeline_none_before_load(self) -> None:
        """加载前 pipeline 应为 None"""
        plugin = DataPipelinePlugin()
        assert plugin.pipeline is None

    def test_initial_state_unloaded(self) -> None:
        """初始状态应为 UNLOADED"""
        plugin = DataPipelinePlugin()
        assert plugin.state == PluginState.UNLOADED


class TestDataPipelinePluginLifecycle:
    """测试插件生命周期"""

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_on_load_creates_pipeline(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """on_load 应创建 DataPipeline 实例"""
        mock_dp_cls.return_value = MagicMock()
        plugin = DataPipelinePlugin(
            config={"cache_ttl": 1800}
        )
        plugin.on_load()

        mock_dp_cls.assert_called_once_with(
            config={"cache_ttl": 1800}
        )
        assert plugin.pipeline is not None

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_on_load_resets_counters(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """on_load 应重置计数器"""
        mock_dp_cls.return_value = MagicMock()
        plugin = DataPipelinePlugin()
        plugin._fetch_count = 5
        plugin._last_error = "some error"
        plugin.on_load()

        assert plugin._fetch_count == 0
        assert plugin._last_error is None

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_on_unload_clears_pipeline(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """on_unload 应清理 pipeline"""
        mock_dp_cls.return_value = MagicMock()
        plugin = DataPipelinePlugin()
        plugin.on_load()
        assert plugin.pipeline is not None

        plugin.on_unload()
        assert plugin.pipeline is None
        assert plugin._fetch_count == 0
        assert plugin._last_error is None


class TestDataPipelinePluginHealthCheck:
    """测试健康检查"""

    def test_health_check_not_loaded(self) -> None:
        """未加载时健康检查应返回 UNKNOWN"""
        plugin = DataPipelinePlugin()
        result = plugin.health_check()
        # 基类 health_check 在非 ACTIVE 状态返回 UNKNOWN
        assert result.status in (
            HealthStatus.UNKNOWN,
            HealthStatus.UNHEALTHY,
        )

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_health_check_active_healthy(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """活跃且无错误时应返回 HEALTHY"""
        mock_dp_cls.return_value = MagicMock()
        plugin = DataPipelinePlugin()
        plugin.on_load()
        # 模拟 ACTIVE 状态
        plugin._state = PluginState.ACTIVE

        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_health_check_with_last_error(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """有最近错误时应返回 DEGRADED"""
        mock_dp_cls.return_value = MagicMock()
        plugin = DataPipelinePlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE
        plugin._last_error = "Connection timeout"

        result = plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "Connection timeout" in result.message

    def test_health_check_pipeline_none_active(
        self,
    ) -> None:
        """pipeline 为 None 但状态为 ACTIVE 时应返回 UNHEALTHY"""
        plugin = DataPipelinePlugin()
        plugin._state = PluginState.ACTIVE
        # pipeline 仍为 None

        result = plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY


class TestDataPipelinePluginConfigUpdate:
    """测试配置热更新"""

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_config_update_recreates_pipeline(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """配置更新应重新创建 DataPipeline"""
        mock_dp_cls.return_value = MagicMock()
        plugin = DataPipelinePlugin(
            config={"cache_ttl": 1800}
        )
        plugin.on_load()
        assert mock_dp_cls.call_count == 1

        new_config = {"cache_ttl": 3600, "max_retries": 5}
        plugin.on_config_update(new_config)

        assert mock_dp_cls.call_count == 2
        mock_dp_cls.assert_called_with(config=new_config)

    def test_config_update_before_load(self) -> None:
        """加载前配置更新不应崩溃"""
        plugin = DataPipelinePlugin()
        new_config = {"cache_ttl": 7200}
        # pipeline 为 None，不应创建新实例
        plugin.on_config_update(new_config)
        assert plugin._config == new_config
        assert plugin.pipeline is None


class TestDataPipelinePluginFetchData:
    """测试数据获取"""

    def test_fetch_data_not_loaded_raises(self) -> None:
        """未加载时获取数据应抛出 RuntimeError"""
        plugin = DataPipelinePlugin()
        with pytest.raises(RuntimeError, match="未加载"):
            plugin.fetch_data("BTC/USDT")

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_fetch_data_success(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """成功获取数据应返回 DataFrame 并发布事件"""
        mock_df = _make_ohlcv_df(50)
        mock_pipeline = MagicMock()
        mock_pipeline.fetch_data = AsyncMock(
            return_value=mock_df
        )
        mock_dp_cls.return_value = mock_pipeline

        plugin = DataPipelinePlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE

        # mock emit_event
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.fetch_data(
            "BTC/USDT", timeframe="1h", limit=50
        )

        assert result is not None
        assert len(result) == 50
        assert plugin._fetch_count == 1
        assert plugin._last_error is None

        # 验证事件发布
        plugin.emit_event.assert_called_once()
        call_args = plugin.emit_event.call_args
        assert (
            call_args[0][0]
            == "data_pipeline.ohlcv_ready"
        )
        assert call_args[0][1]["symbol"] == "BTC/USDT"
        assert call_args[0][1]["timeframe"] == "1h"
        assert call_args[0][1]["rows"] == 50

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_fetch_data_error_publishes_event(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """获取数据失败应发布错误事件"""
        mock_pipeline = MagicMock()
        mock_pipeline.fetch_data = AsyncMock(
            side_effect=ValueError("Exchange unavailable")
        )
        mock_dp_cls.return_value = mock_pipeline

        plugin = DataPipelinePlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.fetch_data("ETH/USDT")

        assert result is None
        assert plugin._last_error is not None
        assert "Exchange unavailable" in plugin._last_error

        # 验证错误事件
        plugin.emit_event.assert_called_once()
        call_args = plugin.emit_event.call_args
        assert (
            call_args[0][0]
            == "data_pipeline.source_error"
        )

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_fetch_count_increments(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """多次获取数据应递增计数"""
        mock_df = _make_ohlcv_df(10)
        mock_pipeline = MagicMock()
        mock_pipeline.fetch_data = AsyncMock(
            return_value=mock_df
        )
        mock_dp_cls.return_value = mock_pipeline

        plugin = DataPipelinePlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE
        plugin.emit_event = MagicMock(return_value=1)

        plugin.fetch_data("BTC/USDT")
        plugin.fetch_data("ETH/USDT")
        plugin.fetch_data("SOL/USDT")

        assert plugin._fetch_count == 3


class TestDataPipelinePluginValidateData:
    """测试数据验证"""

    def test_validate_not_loaded_raises(self) -> None:
        """未加载时验证应抛出 RuntimeError"""
        plugin = DataPipelinePlugin()
        df = _make_ohlcv_df(10)
        with pytest.raises(RuntimeError, match="未加载"):
            plugin.validate_data(df, "BTC/USDT")

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_validate_valid_data(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """验证有效数据不应发布告警"""
        mock_pipeline = MagicMock()
        mock_pipeline.validate_data_quality.return_value = {
            "is_valid": True,
            "quality_score": 0.95,
            "issues": [],
        }
        mock_dp_cls.return_value = mock_pipeline

        plugin = DataPipelinePlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE
        plugin.emit_event = MagicMock(return_value=0)

        df = _make_ohlcv_df(50)
        result = plugin.validate_data(df, "BTC/USDT")

        assert result["is_valid"] is True
        plugin.emit_event.assert_not_called()

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_validate_invalid_data_publishes_alert(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """验证无效数据应发布告警事件"""
        mock_pipeline = MagicMock()
        mock_pipeline.validate_data_quality.return_value = {
            "is_valid": False,
            "quality_score": 0.3,
            "issues": ["missing_data", "outlier"],
        }
        mock_dp_cls.return_value = mock_pipeline

        plugin = DataPipelinePlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE
        plugin.emit_event = MagicMock(return_value=1)

        df = _make_ohlcv_df(50)
        result = plugin.validate_data(df, "BTC/USDT")

        assert result["is_valid"] is False
        plugin.emit_event.assert_called_once()
        call_args = plugin.emit_event.call_args
        assert (
            call_args[0][0]
            == "data_pipeline.data_quality_alert"
        )
        assert "missing_data" in call_args[0][1]["issues"]


class TestDataPipelinePluginStatistics:
    """测试统计信息"""

    def test_statistics_not_loaded(self) -> None:
        """未加载时应返回基本统计"""
        plugin = DataPipelinePlugin()
        stats = plugin.get_statistics()
        assert stats["status"] == "not_loaded"
        assert stats["fetch_count"] == 0

    @patch(
        "src.plugins.data_pipeline.data_pipeline.DataPipeline"
    )
    def test_statistics_loaded(
        self, mock_dp_cls: MagicMock
    ) -> None:
        """加载后应包含 fetch_count"""
        mock_pipeline = MagicMock()
        mock_pipeline.get_statistics.return_value = {
            "cache_hits": 10,
            "cache_misses": 5,
        }
        mock_dp_cls.return_value = mock_pipeline

        plugin = DataPipelinePlugin()
        plugin.on_load()
        plugin._fetch_count = 15

        stats = plugin.get_statistics()
        assert stats["fetch_count"] == 15
        assert stats["cache_hits"] == 10
