"""测试 src/kernel/config_system.py 中的配置系统"""

import os
import tempfile

import pytest
import yaml

from src.kernel.config_system import ConfigSystem
from src.kernel.plugin_manifest import (
    ConfigSchemaField,
    PluginManifest,
)
from src.kernel.types import PluginConfigError, PluginType


class TestConfigSystem:
    """测试 ConfigSystem 核心功能"""

    def setup_method(self) -> None:
        self.config = ConfigSystem()

    def test_empty_config(self) -> None:
        """测试空配置"""
        self.config.load()
        assert self.config.is_loaded
        assert self.config.get("nonexistent") is None
        assert self.config.get("key", "default") == "default"

    def test_load_yaml_config(self) -> None:
        """测试加载 YAML 配置文件"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(
                {"database": {"host": "localhost", "port": 5432}},
                f,
            )
            f.flush()
            path = f.name

        try:
            config = ConfigSystem(path)
            config.load()
            assert config.get("database.host") == "localhost"
            assert config.get("database.port") == 5432
        finally:
            os.unlink(path)

    def test_set_and_get(self) -> None:
        """测试设置和获取配置"""
        self.config.load()
        self.config.set("app.name", "wyckoff")
        assert self.config.get("app.name") == "wyckoff"

    def test_nested_set(self) -> None:
        """测试嵌套设置"""
        self.config.load()
        self.config.set("a.b.c", 42)
        assert self.config.get("a.b.c") == 42

    def test_plugin_config(self) -> None:
        """测试插件级配置"""
        self.config.load()
        self.config.set_plugin_config(
            "test_plugin", {"threshold": 0.8, "enabled": True}
        )
        cfg = self.config.get_plugin_config("test_plugin")
        assert cfg["threshold"] == 0.8
        assert cfg["enabled"] is True

    def test_plugin_config_with_defaults(self) -> None:
        """测试插件配置合并默认值"""
        manifest = PluginManifest(
            name="test_plugin",
            display_name="Test",
            version="1.0.0",
            plugin_type=PluginType.CORE,
            entry_point="main",
            config_schema=[
                ConfigSchemaField(
                    name="threshold",
                    field_type="float",
                    default=0.5,
                ),
                ConfigSchemaField(
                    name="window",
                    field_type="int",
                    default=20,
                ),
            ],
        )
        self.config.load()
        self.config.register_defaults("test_plugin", manifest)

        # 未设置用户配置时，返回默认值
        cfg = self.config.get_plugin_config("test_plugin")
        assert cfg["threshold"] == 0.5
        assert cfg["window"] == 20

        # 用户配置覆盖默认值
        self.config.update_plugin_config(
            "test_plugin", "threshold", 0.9
        )
        cfg = self.config.get_plugin_config("test_plugin")
        assert cfg["threshold"] == 0.9
        assert cfg["window"] == 20  # 保持默认

    def test_validate_plugin_config_pass(self) -> None:
        """测试配置验证通过"""
        manifest = PluginManifest(
            name="p1",
            display_name="P1",
            version="1.0.0",
            plugin_type=PluginType.CORE,
            entry_point="main",
            config_schema=[
                ConfigSchemaField(
                    name="rate",
                    field_type="float",
                    default=0.5,
                    min_value=0.0,
                    max_value=1.0,
                ),
            ],
        )
        self.config.load()
        self.config.register_defaults("p1", manifest)
        errors = self.config.validate_plugin_config("p1", manifest)
        assert errors == []

    def test_validate_plugin_config_range_error(self) -> None:
        """测试配置验证范围错误"""
        manifest = PluginManifest(
            name="p2",
            display_name="P2",
            version="1.0.0",
            plugin_type=PluginType.CORE,
            entry_point="main",
            config_schema=[
                ConfigSchemaField(
                    name="rate",
                    field_type="float",
                    min_value=0.0,
                    max_value=1.0,
                    required=True,
                ),
            ],
        )
        self.config.load()
        self.config.set_plugin_config("p2", {"rate": 2.0})
        errors = self.config.validate_plugin_config("p2", manifest)
        assert len(errors) == 1
        assert "大于最大值" in errors[0]

    def test_change_listener(self) -> None:
        """测试配置变更监听"""
        changes = []

        def listener(
            scope: str, key: str, old: object, new: object
        ) -> None:
            changes.append((scope, key, old, new))

        self.config.load()
        self.config.add_change_listener(listener)
        self.config.set("app.debug", True)

        assert len(changes) == 1
        assert changes[0][0] == "global"
        assert changes[0][3] is True

    def test_remove_change_listener(self) -> None:
        """测试移除变更监听"""
        changes = []

        def listener(
            scope: str, key: str, old: object, new: object
        ) -> None:
            changes.append(1)

        self.config.load()
        self.config.add_change_listener(listener)
        self.config.set("a", 1)
        assert len(changes) == 1

        self.config.remove_change_listener(listener)
        self.config.set("b", 2)
        assert len(changes) == 1  # 不再触发

    def test_to_dict(self) -> None:
        """测试导出配置"""
        self.config.load()
        self.config.set("key", "value")
        result = self.config.to_dict()
        assert "global" in result
        assert "plugins" in result
        assert "defaults" in result

    def test_env_override(self) -> None:
        """测试环境变量覆盖"""
        os.environ["WYCKOFF_TEST__KEY"] = "env_value"
        try:
            self.config.load()
            # 环境变量 WYCKOFF_TEST__KEY -> test.key
            val = self.config.get("test.key")
            assert val == "env_value"
        finally:
            del os.environ["WYCKOFF_TEST__KEY"]

    def test_missing_config_file(self) -> None:
        """测试配置文件不存在"""
        config = ConfigSystem("/nonexistent/path.yaml")
        config.load()  # 不应抛出异常
        assert config.is_loaded
