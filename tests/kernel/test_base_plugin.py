"""测试 src/kernel/base_plugin.py 中的插件基类"""

import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.event_bus import EventBus
from src.kernel.types import (
    HealthCheckResult,
    HealthStatus,
    PluginError,
    PluginInfo,
    PluginState,
    PluginType,
)


class SimplePlugin(BasePlugin):
    """用于测试的简单插件实现"""

    def __init__(self, name: str = "simple") -> None:
        super().__init__(name)
        self.loaded = False
        self.unloaded = False

    def on_load(self) -> None:
        self.loaded = True

    def on_unload(self) -> None:
        self.unloaded = True


class FailingPlugin(BasePlugin):
    """加载时会失败的插件"""

    def on_load(self) -> None:
        raise RuntimeError("故意的加载错误")

    def on_unload(self) -> None:
        pass


class TestBasePlugin:
    """测试 BasePlugin 核心功能"""

    def test_initial_state(self) -> None:
        """测试初始状态"""
        plugin = SimplePlugin("test")
        assert plugin.name == "test"
        assert plugin.state == PluginState.UNLOADED
        assert not plugin.is_active
        assert not plugin.is_error

    def test_load_lifecycle(self) -> None:
        """测试加载生命周期"""
        plugin = SimplePlugin("test")
        bus = EventBus()
        plugin._set_event_bus(bus)

        plugin._do_load()
        assert plugin.loaded is True
        assert plugin.state == PluginState.ACTIVE
        assert plugin.is_active
        assert plugin._load_time is not None
        assert plugin._load_time >= 0

    def test_unload_lifecycle(self) -> None:
        """测试卸载生命周期"""
        plugin = SimplePlugin("test")
        bus = EventBus()
        plugin._set_event_bus(bus)

        plugin._do_load()
        plugin._do_unload()
        assert plugin.unloaded is True
        assert plugin.state == PluginState.UNLOADED

    def test_load_failure(self) -> None:
        """测试加载失败"""
        plugin = FailingPlugin("fail")
        bus = EventBus()
        plugin._set_event_bus(bus)

        with pytest.raises(PluginError):
            plugin._do_load()

        assert plugin.state == PluginState.ERROR
        assert plugin.is_error
        assert plugin._error_message is not None

    def test_emit_event(self) -> None:
        """测试插件发布事件"""
        plugin = SimplePlugin("emitter")
        bus = EventBus()
        plugin._set_event_bus(bus)

        received = []
        bus.subscribe(
            "test_event",
            lambda event_name, d: received.append(d),
        )

        plugin._do_load()
        plugin.emit_event("test_event", {"key": "val"})

        assert len(received) == 1
        assert received[0]["key"] == "val"

    def test_subscribe_event(self) -> None:
        """测试插件订阅事件"""
        plugin = SimplePlugin("subscriber")
        bus = EventBus()
        plugin._set_event_bus(bus)

        received = []
        plugin._do_load()
        plugin.subscribe_event(
            "external.event",
            lambda event_name, d: received.append(d),
        )

        bus.emit("external.event", {"from": "outside"})
        assert len(received) == 1

    def test_unload_cleans_subscriptions(self) -> None:
        """测试卸载时清理订阅"""
        plugin = SimplePlugin("cleaner")
        bus = EventBus()
        plugin._set_event_bus(bus)

        received = []
        plugin._do_load()
        plugin.subscribe_event(
            "some.event",
            lambda event_name, d: received.append(d),
        )

        bus.emit("some.event", {})
        assert len(received) == 1

        plugin._do_unload()
        bus.emit("some.event", {})
        assert len(received) == 1  # 不再接收

    def test_health_check_default(self) -> None:
        """测试默认健康检查"""
        plugin = SimplePlugin("healthy")
        bus = EventBus()
        plugin._set_event_bus(bus)
        plugin._do_load()

        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    def test_config_access(self) -> None:
        """测试配置访问"""
        plugin = SimplePlugin("configured")
        plugin._config = {"threshold": 0.8, "window": 20}

        assert plugin.config["threshold"] == 0.8
        assert plugin.get_config_value("window") == 20
        assert plugin.get_config_value("missing", 42) == 42

    def test_plugin_info(self) -> None:
        """测试插件信息"""
        plugin = SimplePlugin("info_test")
        info = PluginInfo(
            name="info_test",
            display_name="Info Test",
            version="1.0.0",
            plugin_type=PluginType.CORE,
        )
        plugin._set_plugin_info(info)

        assert plugin.plugin_info is not None
        assert plugin.plugin_info.name == "info_test"
