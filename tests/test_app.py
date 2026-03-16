"""WyckoffApp 单元测试"""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.app import WyckoffApp


class TestWyckoffAppInit:
    """测试 WyckoffApp 初始化"""

    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    def test_init_default_params(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试默认参数初始化"""
        mock_cs = MagicMock()
        mock_cs_cls.return_value = mock_cs

        app = WyckoffApp()

        assert app._config_path == "config.yaml"
        assert app._plugins_dir == "src/plugins"
        assert app.is_running is False
        mock_cs.load.assert_called_once_with("config.yaml")

    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    def test_init_custom_params(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试自定义参数初始化"""
        mock_cs = MagicMock()
        mock_cs_cls.return_value = mock_cs

        app = WyckoffApp(
            config_path="custom.yaml",
            plugins_dir="my_plugins",
        )

        assert app._config_path == "custom.yaml"
        assert app._plugins_dir == "my_plugins"
        mock_cs.load.assert_called_once_with("custom.yaml")
        mock_pm_cls.assert_called_once_with(
            plugins_dir="my_plugins",
            config_system=mock_cs,
            event_bus=mock_eb_cls.return_value,
        )


class TestDiscoverAndLoad:
    """测试插件发现和加载"""

    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    def test_discover_and_load_success(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试成功发现和加载插件"""
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.discover_plugins.return_value = [
            "market_regime",
            "orchestrator",
        ]
        mock_pm.load_all.return_value = {
            "market_regime": True,
            "orchestrator": True,
        }

        app = WyckoffApp()
        results = app.discover_and_load()

        assert results == {
            "market_regime": True,
            "orchestrator": True,
        }
        mock_pm.discover_plugins.assert_called_once()
        mock_pm.load_all.assert_called_once()

    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    def test_discover_and_load_partial_failure(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试部分插件加载失败"""
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.discover_plugins.return_value = [
            "market_regime",
            "broken_plugin",
        ]
        mock_pm.load_all.return_value = {
            "market_regime": True,
            "broken_plugin": False,
        }

        app = WyckoffApp()
        results = app.discover_and_load()

        assert results["market_regime"] is True
        assert results["broken_plugin"] is False


class TestStartStop:
    """测试启动和停止"""

    @pytest.mark.asyncio
    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    async def test_start_success(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试成功启动"""
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.discover_plugins.return_value = [
            "market_regime",
            "data_pipeline",
            "orchestrator",
        ]
        mock_pm.load_all.return_value = {
            "market_regime": True,
            "data_pipeline": True,
            "orchestrator": True,
        }

        app = WyckoffApp()
        await app.start()

        assert app.is_running is True

    @pytest.mark.asyncio
    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    async def test_start_missing_core_plugin(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试核心插件缺失时启动失败"""
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.discover_plugins.return_value = ["market_regime"]
        mock_pm.load_all.return_value = {
            "market_regime": True,
            "data_pipeline": False,
            "orchestrator": True,
        }

        app = WyckoffApp()
        with pytest.raises(RuntimeError, match="核心插件"):
            await app.start()

    @pytest.mark.asyncio
    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    async def test_stop(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试停止系统"""
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.discover_plugins.return_value = [
            "market_regime",
            "data_pipeline",
            "orchestrator",
        ]
        mock_pm.load_all.return_value = {
            "market_regime": True,
            "data_pipeline": True,
            "orchestrator": True,
        }
        mock_pm.get_plugin.return_value = None

        app = WyckoffApp()
        await app.start()
        assert app.is_running is True

        await app.stop()
        assert app.is_running is False
        mock_pm.unload_all.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    async def test_stop_when_not_running(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试未运行时停止"""
        app = WyckoffApp()
        await app.stop()  # 不应抛出异常
        assert app.is_running is False

    @pytest.mark.asyncio
    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    async def test_double_start(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试重复启动"""
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.discover_plugins.return_value = [
            "market_regime",
            "data_pipeline",
            "orchestrator",
        ]
        mock_pm.load_all.return_value = {
            "market_regime": True,
            "data_pipeline": True,
            "orchestrator": True,
        }

        app = WyckoffApp()
        await app.start()
        await app.start()  # 第二次调用不应出错

        # discover_plugins 只应被调用一次
        mock_pm.discover_plugins.assert_called_once()


class TestGetStatus:
    """测试状态获取"""

    @patch("src.app.ConfigSystem")
    @patch("src.app.EventBus")
    @patch("src.app.PluginManager")
    def test_get_status(
        self, mock_pm_cls, mock_eb_cls, mock_cs_cls
    ):
        """测试获取系统状态"""
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm._plugin_infos = {}

        app = WyckoffApp()
        status = app.get_status()

        assert status["is_running"] is False
        assert status["config_path"] == "config.yaml"
        assert status["plugins_dir"] == "src/plugins"
        assert status["plugin_count"] == 0
        assert status["plugins"] == {}
