"""测试 src/kernel/plugin_manager.py 中的插件管理器"""

import os
import tempfile

import pytest
import yaml

from src.kernel.config_system import ConfigSystem
from src.kernel.event_bus import EventBus
from src.kernel.plugin_manager import PluginManager
from src.kernel.plugin_manifest import MANIFEST_FILENAME
from src.kernel.types import (
    PluginDependencyError,
    PluginLoadError,
    PluginState,
)


def _make_plugin_dir(
    base: str,
    name: str,
    manifest_extra: dict | None = None,
    code: str | None = None,
) -> str:
    """在 base 目录下创建一个插件子目录，包含清单和入口文件"""
    plugin_dir = os.path.join(base, name)
    os.makedirs(plugin_dir, exist_ok=True)

    # 写清单
    manifest = {
        "manifest_version": "1.0",
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "version": "1.0.0",
        "plugin_type": "core",
        "entry_point": "main",
    }
    if manifest_extra:
        manifest.update(manifest_extra)

    with open(
        os.path.join(plugin_dir, MANIFEST_FILENAME),
        "w",
        encoding="utf-8",
    ) as f:
        yaml.dump(manifest, f)

    # 写入口文件
    if code is None:
        code = f'''
from src.kernel.base_plugin import BasePlugin

class {name.title().replace("_", "")}Plugin(BasePlugin):
    """测试插件: {name}"""
    def on_load(self) -> None:
        pass
    def on_unload(self) -> None:
        pass
'''
    with open(
        os.path.join(plugin_dir, "main.py"),
        "w",
        encoding="utf-8",
    ) as f:
        f.write(code)

    # __init__.py
    with open(
        os.path.join(plugin_dir, "__init__.py"),
        "w",
        encoding="utf-8",
    ) as f:
        f.write("")

    return plugin_dir


class TestPluginManager:
    """测试 PluginManager 核心功能"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.tmpdir = tempfile.mkdtemp()
        self.bus = EventBus()
        self.config = ConfigSystem()
        self.manager = PluginManager(
            plugins_dir=self.tmpdir,
            event_bus=self.bus,
            config_system=self.config,
        )

    def test_discover_plugins(self) -> None:
        """测试发现插件"""
        _make_plugin_dir(self.tmpdir, "alpha_plugin")
        _make_plugin_dir(self.tmpdir, "beta_plugin")

        discovered = self.manager.discover_plugins()
        assert len(discovered) == 2
        assert "alpha_plugin" in discovered
        assert "beta_plugin" in discovered

    def test_load_single_plugin(self) -> None:
        """测试加载单个插件"""
        _make_plugin_dir(self.tmpdir, "loader_test")
        self.manager.discover_plugins()

        self.manager.load_plugin("loader_test")
        plugin = self.manager.get_plugin("loader_test")
        assert plugin is not None
        assert plugin.state == PluginState.ACTIVE

    def test_unload_plugin(self) -> None:
        """测试卸载插件"""
        _make_plugin_dir(self.tmpdir, "unload_test")
        self.manager.discover_plugins()
        self.manager.load_plugin("unload_test")

        self.manager.unload_plugin("unload_test")
        plugin = self.manager.get_plugin("unload_test")
        assert plugin is None or plugin.state == PluginState.UNLOADED

    def test_load_with_dependency(self) -> None:
        """测试带依赖的加载（自动加载依赖）"""
        _make_plugin_dir(self.tmpdir, "dep_base")
        _make_plugin_dir(
            self.tmpdir,
            "dep_child",
            manifest_extra={
                "plugin_type": "optional",
                "dependencies": ["dep_base"],
            },
        )
        self.manager.discover_plugins()

        self.manager.load_plugin("dep_child")
        # dep_base 应该被自动加载
        base = self.manager.get_plugin("dep_base")
        child = self.manager.get_plugin("dep_child")
        assert base is not None
        assert base.state == PluginState.ACTIVE
        assert child is not None
        assert child.state == PluginState.ACTIVE

    def test_load_missing_dependency(self) -> None:
        """测试缺失依赖时报错"""
        _make_plugin_dir(
            self.tmpdir,
            "orphan_plugin",
            manifest_extra={
                "dependencies": ["nonexistent"],
            },
        )
        self.manager.discover_plugins()

        with pytest.raises(PluginDependencyError):
            self.manager.load_plugin("orphan_plugin")

    def test_list_plugins(self) -> None:
        """测试列出所有插件"""
        _make_plugin_dir(self.tmpdir, "list_a")
        _make_plugin_dir(self.tmpdir, "list_b")
        self.manager.discover_plugins()

        plugins = self.manager.list_plugins()
        assert len(plugins) == 2

    def test_load_all(self) -> None:
        """测试加载所有插件"""
        _make_plugin_dir(self.tmpdir, "all_a")
        _make_plugin_dir(
            self.tmpdir,
            "all_b",
            manifest_extra={
                "plugin_type": "optional",
                "dependencies": ["all_a"],
            },
        )
        self.manager.discover_plugins()

        results = self.manager.load_all()
        assert results["all_a"] is True
        assert results["all_b"] is True

    def test_unload_all(self) -> None:
        """测试卸载所有插件"""
        _make_plugin_dir(self.tmpdir, "ua")
        _make_plugin_dir(self.tmpdir, "ub")
        self.manager.discover_plugins()
        self.manager.load_all()

        self.manager.unload_all()
        for info in self.manager.list_plugins():
            assert info.state != PluginState.ACTIVE

    def test_health_check_all(self) -> None:
        """测试全局健康检查"""
        _make_plugin_dir(self.tmpdir, "hc_plugin")
        self.manager.discover_plugins()
        self.manager.load_all()

        results = self.manager.health_check_all()
        assert "hc_plugin" in results

    def test_get_nonexistent_plugin(self) -> None:
        """测试获取不存在的插件"""
        result = self.manager.get_plugin("ghost")
        assert result is None

    def test_load_failing_plugin(self) -> None:
        """测试加载失败的插件"""
        fail_code = '''
from src.kernel.base_plugin import BasePlugin

class FailPlugin(BasePlugin):
    def on_load(self) -> None:
        raise RuntimeError("boom")
    def on_unload(self) -> None:
        pass
'''
        _make_plugin_dir(
            self.tmpdir,
            "fail_plugin",
            code=fail_code,
        )
        self.manager.discover_plugins()

        with pytest.raises(PluginLoadError):
            self.manager.load_plugin("fail_plugin")
