"""进化系统插件测试

注意: archivist 已在 v3.0 Phase 0 删除。
archivist 相关测试已移除，Phase 4 重建进化系统时会新增完整测试。
"""

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

    def test_on_load(self):
        """测试加载（archivist已移除，on_load应为pass）"""
        self.plugin.on_load()
        # archivist 已移除，on_load 不再初始化它
        assert self.plugin._archivist is None

    def test_on_unload(self):
        """测试卸载"""
        self.plugin.on_unload()
        assert self.plugin._archivist is None
        assert self.plugin.is_running is False

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
        assert status["is_running"] is False

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
