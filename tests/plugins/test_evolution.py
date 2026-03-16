"""进化系统插件测试"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.plugins.evolution.plugin import EvolutionPlugin
from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginState


class TestEvolutionPluginInit:
    """测试插件初始化"""

    def test_init_default_name(self):
        """测试默认名称"""
        plugin = EvolutionPlugin()
        assert plugin.name == "evolution"

    def test_init_custom_name(self):
        """测试自定义名称"""
        plugin = EvolutionPlugin(name="my_evolution")
        assert plugin.name == "my_evolution"

    def test_init_inherits_base_plugin(self):
        """测试继承 BasePlugin"""
        plugin = EvolutionPlugin()
        assert isinstance(plugin, BasePlugin)

    def test_init_attributes(self):
        """测试初始属性"""
        plugin = EvolutionPlugin()
        assert plugin._archivist is None
        assert plugin._record_count == 0
        assert plugin._last_error is None
        assert plugin._is_evolving is False
        assert plugin._cycle_count == 0


class TestEvolutionPluginLoadUnload:
    """测试加载和卸载"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_on_load_default_config(self, mock_storage_cls, mock_cls):
        """测试默认配置加载"""
        mock_cls.return_value = MagicMock()
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()
        assert self.plugin._archivist is not None
        mock_cls.assert_called_once()

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_on_load_with_config(self, mock_storage_cls, mock_cls):
        """测试带配置加载"""
        mock_cls.return_value = MagicMock()
        mock_storage_cls.return_value = MagicMock()
        self.plugin._config = {
            "archivist": {
                "storage_path": "/tmp/test.jsonl",
                "max_queue_size": 500,
            }
        }
        self.plugin.on_load()
        mock_cls.assert_called_once_with(config={
            "storage_path": "/tmp/test.jsonl",
            "max_queue_size": 500,
        })

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_on_unload(self, mock_storage_cls, mock_cls):
        """测试卸载"""
        mock_archivist = MagicMock()
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()
        self.plugin._last_error = "some error"

        self.plugin.on_unload()
        assert self.plugin._archivist is None
        mock_archivist.stop.assert_called_once()

    def test_on_unload_when_not_loaded(self):
        """测试未加载时卸载"""
        self.plugin.on_unload()
        assert self.plugin._archivist is None


class TestEvolutionPluginConfigUpdate:
    """测试配置更新"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_config_update_when_not_loaded(self):
        """测试未加载时配置更新"""
        self.plugin.on_config_update({"key": "value"})
        assert self.plugin._config == {"key": "value"}


class TestEvolutionHealthCheck:
    """测试健康检查"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_health_check_not_active(self):
        """测试未激活时健康检查"""
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未激活" in result.message

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_health_check_active_healthy(self, mock_storage_cls, mock_cls):
        """测试激活且健康"""
        mock_archivist = MagicMock()
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()
        self.plugin._state = PluginState.ACTIVE

        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_health_check_with_error(self, mock_storage_cls, mock_cls):
        """测试有错误时健康检查"""
        mock_archivist = MagicMock()
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()
        self.plugin._state = PluginState.ACTIVE
        self.plugin._last_error = "测试错误"

        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED

    def test_health_check_archivist_none(self):
        """测试档案员为None"""
        self.plugin._state = PluginState.ACTIVE
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未初始化" in result.message


class TestEvolutionStartStop:
    """测试启动和停止"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_start_archivist_not_loaded(self):
        """测试未加载时启动档案员"""
        with pytest.raises(RuntimeError, match="档案员未初始化"):
            self.plugin.start_archivist()

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_start_archivist_success(self, mock_storage_cls, mock_cls):
        """测试成功启动档案员"""
        mock_archivist = MagicMock()
        mock_archivist.storage_path = "/tmp/test.jsonl"
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()

        self.plugin.start_archivist()
        mock_archivist.start.assert_called_once()

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_stop_archivist_success(self, mock_storage_cls, mock_cls):
        """测试成功停止档案员"""
        mock_archivist = MagicMock()
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()

        self.plugin.stop_archivist()
        mock_archivist.stop.assert_called_once()


class TestEvolutionRecordLog:
    """测试记录日志"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_record_log_not_loaded(self):
        """测试未加载时记录"""
        result = self.plugin.record_log(MagicMock())
        assert result is False

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_record_log_success(self, mock_storage_cls, mock_cls):
        """测试成功记录"""
        mock_archivist = MagicMock()
        mock_archivist.record_log.return_value = True
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()

        mock_log = MagicMock()
        mock_log.event_type.value = "weight_adjustment"
        mock_log.module = "test_module"
        mock_log.parameter = "test_param"

        result = self.plugin.record_log(mock_log)
        assert result is True
        assert self.plugin._record_count == 1

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_record_log_queue_full(self, mock_storage_cls, mock_cls):
        """测试队列满时记录"""
        mock_archivist = MagicMock()
        mock_archivist.record_log.return_value = False
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()

        result = self.plugin.record_log(MagicMock())
        assert result is False
        assert self.plugin._record_count == 0


class TestEvolutionQueryHistory:
    """测试历史查询"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_query_not_loaded(self):
        """测试未加载时查询"""
        results = self.plugin.query_history("测试查询")
        assert results == []

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_query_success(self, mock_storage_cls, mock_cls):
        """测试成功查询"""
        mock_archivist = MagicMock()
        mock_log = MagicMock()
        mock_archivist.query_history.return_value = [
            (mock_log, 0.95),
        ]
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()

        results = self.plugin.query_history("为什么调整RSI阈值？")
        assert len(results) == 1
        assert results[0][1] == 0.95

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_query_empty_result(self, mock_storage_cls, mock_cls):
        """测试空结果查询"""
        mock_archivist = MagicMock()
        mock_archivist.query_history.return_value = []
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()

        results = self.plugin.query_history("不存在的查询")
        assert len(results) == 0


class TestEvolutionStatistics:
    """测试统计信息"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_plugin_statistics_initial(self):
        """测试初始统计"""
        stats = self.plugin.get_statistics()
        assert stats["record_count"] == 0
        assert stats["last_error"] is None
        assert stats["is_evolving"] is False
        assert stats["cycle_count"] == 0

    @patch("src.plugins.evolution.archivist.EvolutionArchivist")
    @patch("src.storage.evolution_storage.EvolutionStorage")
    def test_plugin_statistics_after_ops(self, mock_storage_cls, mock_cls):
        """测试操作后统计"""
        mock_archivist = MagicMock()
        mock_cls.return_value = mock_archivist
        mock_storage_cls.return_value = MagicMock()
        self.plugin.on_load()
        self.plugin._record_count = 10
        self.plugin._is_evolving = True
        self.plugin._cycle_count = 5

        stats = self.plugin.get_statistics()
        assert stats["record_count"] == 10
        assert stats["is_evolving"] is True
        assert stats["cycle_count"] == 5


class TestEvolutionStatus:
    """测试进化状态"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_get_evolution_status_initial(self):
        """测试初始进化状态"""
        status = self.plugin.get_evolution_status()
        assert status["status"] == "stopped"
        assert status["cycle_count"] == 0
        assert status["start_time"] is None

    def test_get_current_config_initial(self):
        """测试初始配置"""
        config = self.plugin.get_current_config()
        assert config == {}


class TestEvolutionPositions:
    """测试进化盘持仓"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    def test_get_positions_no_storage(self):
        """测试无存储时获取持仓"""
        positions = self.plugin.get_positions()
        assert positions == []

    def test_get_position_no_storage(self):
        """测试无存储时获取单个持仓"""
        position = self.plugin.get_position("test_id")
        assert position is None

    def test_add_position_no_storage(self):
        """测试无存储时添加持仓"""
        result = self.plugin.add_position({"symbol": "BTC/USDT"})
        assert result == {}

    def test_close_position_no_storage(self):
        """测试无存储时平仓"""
        result = self.plugin.close_position("test_id", 100.0)
        assert result is None

    def test_get_trades_no_storage(self):
        """测试无存储时获取交易"""
        trades = self.plugin.get_trades()
        assert trades == []

    def test_get_evolution_statistics_no_storage(self):
        """测试无存储时获取统计"""
        stats = self.plugin.get_evolution_statistics()
        assert stats == {}


class TestEvolutionStartStopEvolution:
    """测试进化系统启停"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = EvolutionPlugin()

    @pytest.mark.asyncio
    async def test_start_evolution_no_workflow(self):
        """测试无工作流时启动进化"""
        result = await self.plugin.start_evolution()
        assert result["status"] == "error"
        assert "工作流" in result["message"]

    @pytest.mark.asyncio
    async def test_stop_evolution_not_running(self):
        """测试未运行时停止进化"""
        result = await self.plugin.stop_evolution()
        assert result["status"] == "already_stopped"
