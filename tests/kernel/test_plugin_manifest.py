"""测试 src/kernel/plugin_manifest.py 中的清单解析器"""

import os
import tempfile

import pytest
import yaml

from src.kernel.plugin_manifest import (
    MANIFEST_DISABLED_SUFFIX,
    MANIFEST_FILENAME,
    PluginManifest,
    discover_manifests,
    disable_plugin,
    enable_plugin,
    parse_manifest,
)
from src.kernel.types import (
    ManifestValidationError,
    PluginType,
)


class TestParseManifest:
    """测试清单解析"""

    def _create_manifest(
        self, data: dict, dirname: str = "test_plugin"
    ) -> str:
        """创建临时清单文件并返回路径"""
        tmpdir = tempfile.mkdtemp()
        plugin_dir = os.path.join(tmpdir, dirname)
        os.makedirs(plugin_dir, exist_ok=True)
        path = os.path.join(plugin_dir, MANIFEST_FILENAME)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        return path

    def test_parse_valid_manifest(self) -> None:
        """测试解析有效清单"""
        data = {
            "manifest_version": "1.0",
            "name": "test_plugin",
            "display_name": "Test Plugin",
            "version": "1.0.0",
            "plugin_type": "core",
            "entry_point": "main",
        }
        path = self._create_manifest(data)
        manifest = parse_manifest(path)

        assert manifest.name == "test_plugin"
        assert manifest.display_name == "Test Plugin"
        assert manifest.version == "1.0.0"
        assert manifest.plugin_type == PluginType.CORE
        assert manifest.entry_point == "main"
        assert manifest.dependencies == []

    def test_parse_with_dependencies(self) -> None:
        """测试解析带依赖的清单"""
        data = {
            "manifest_version": "1.0",
            "name": "dependent_plugin",
            "display_name": "Dependent",
            "version": "1.0.0",
            "plugin_type": "optional",
            "entry_point": "plugin",
            "dependencies": ["data_pipeline", "market_regime"],
        }
        path = self._create_manifest(
            data, dirname="dependent_plugin"
        )
        manifest = parse_manifest(path)

        assert manifest.plugin_type == PluginType.OPTIONAL
        assert len(manifest.dependencies) == 2
        assert "data_pipeline" in manifest.dependencies

    def test_parse_with_config_schema(self) -> None:
        """测试解析带配置模式的清单"""
        data = {
            "manifest_version": "1.0",
            "name": "schema_plugin",
            "display_name": "Schema",
            "version": "1.0.0",
            "plugin_type": "core",
            "entry_point": "main",
            "config_schema": [
                {
                    "name": "threshold",
                    "type": "float",
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "description": "检测阈值",
                },
            ],
        }
        path = self._create_manifest(
            data, dirname="schema_plugin"
        )
        manifest = parse_manifest(path)

        assert len(manifest.config_schema) == 1
        field = manifest.config_schema[0]
        assert field.name == "threshold"
        assert field.default == 0.5

    def test_parse_missing_required_field(self) -> None:
        """测试缺少必需字段"""
        data = {
            "manifest_version": "1.0",
            "name": "bad_plugin",
            # 缺少 display_name, version 等
        }
        path = self._create_manifest(
            data, dirname="bad_plugin"
        )
        with pytest.raises(ManifestValidationError):
            parse_manifest(path)

    def test_parse_invalid_plugin_name(self) -> None:
        """测试无效的插件名称"""
        data = {
            "manifest_version": "1.0",
            "name": "Invalid-Name",
            "display_name": "Bad",
            "version": "1.0.0",
            "plugin_type": "core",
            "entry_point": "main",
        }
        path = self._create_manifest(
            data, dirname="invalid_name"
        )
        with pytest.raises(ManifestValidationError):
            parse_manifest(path)


class TestDiscoverManifests:
    """测试清单发现"""

    def test_discover_in_directory(self) -> None:
        """测试目录扫描"""
        tmpdir = tempfile.mkdtemp()
        # 创建两个插件目录
        for name in ["plugin_a", "plugin_b"]:
            plugin_dir = os.path.join(tmpdir, name)
            os.makedirs(plugin_dir)
            path = os.path.join(plugin_dir, MANIFEST_FILENAME)
            with open(path, "w") as f:
                yaml.dump({"name": name}, f)

        paths = discover_manifests(tmpdir)
        assert len(paths) == 2

    def test_skip_disabled_manifests(self) -> None:
        """测试跳过禁用的清单"""
        tmpdir = tempfile.mkdtemp()
        plugin_dir = os.path.join(tmpdir, "disabled_plugin")
        os.makedirs(plugin_dir)
        # 创建禁用的清单
        disabled_path = os.path.join(
            plugin_dir,
            MANIFEST_FILENAME + MANIFEST_DISABLED_SUFFIX,
        )
        with open(disabled_path, "w") as f:
            yaml.dump({"name": "disabled"}, f)

        paths = discover_manifests(tmpdir)
        assert len(paths) == 0


class TestEnableDisablePlugin:
    """测试启用/禁用插件"""

    def test_disable_and_enable(self) -> None:
        """测试禁用和启用插件"""
        tmpdir = tempfile.mkdtemp()
        plugin_dir = os.path.join(tmpdir, "my_plugin")
        os.makedirs(plugin_dir)
        manifest_path = os.path.join(
            plugin_dir, MANIFEST_FILENAME
        )
        with open(manifest_path, "w") as f:
            yaml.dump({"name": "my_plugin"}, f)

        # 禁用
        result = disable_plugin(plugin_dir)
        assert result is True
        assert not os.path.exists(manifest_path)
        assert os.path.exists(
            manifest_path + MANIFEST_DISABLED_SUFFIX
        )

        # 启用
        result = enable_plugin(plugin_dir)
        assert result is True
        assert os.path.exists(manifest_path)
        assert not os.path.exists(
            manifest_path + MANIFEST_DISABLED_SUFFIX
        )
