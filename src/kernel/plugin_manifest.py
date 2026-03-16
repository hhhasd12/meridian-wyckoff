"""插件清单解析与验证

解析 plugin-manifest.yaml 文件，验证必需字段，
并转换为 PluginManifest 数据类。

清单文件规范：
- manifest_version: "1.0"
- name: 插件唯一标识（snake_case）
- display_name: 显示名称
- version: 语义化版本号
- plugin_type: core | optional
- entry_point: 入口模块路径
- dependencies: 依赖的其他插件列表
- capabilities: 提供的能力列表
- subscriptions: 订阅的事件列表
- publications: 发布的事件列表
- config_schema: 配置参数模式定义
- health_check: 健康检查配置

禁用约定：将文件重命名为 plugin-manifest.yaml.disabled

参考：VCP Plugin/AgentDream/plugin-manifest.json
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.kernel.types import (
    ManifestValidationError,
    PluginType,
)

logger = logging.getLogger(__name__)

# 清单文件名常量
MANIFEST_FILENAME = "plugin-manifest.yaml"
MANIFEST_DISABLED_SUFFIX = ".disabled"

# 必需字段列表
REQUIRED_FIELDS = ["name", "version", "entry_point"]

# 支持的清单版本
SUPPORTED_MANIFEST_VERSIONS = ["1.0"]


@dataclass
class ConfigSchemaField:
    """配置参数模式字段

    Attributes:
        name: 参数名称
        field_type: 参数类型（str, int, float, bool, list, dict）
        default: 默认值
        description: 参数描述
        required: 是否必需
        min_value: 最小值（数值类型）
        max_value: 最大值（数值类型）
        choices: 可选值列表
    """

    name: str
    field_type: str = "str"
    default: Any = None
    description: str = ""
    required: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: Optional[List[Any]] = None


@dataclass
class HealthCheckConfig:
    """健康检查配置

    Attributes:
        enabled: 是否启用健康检查
        interval_seconds: 检查间隔（秒）
        timeout_seconds: 超时时间（秒）
        failure_threshold: 连续失败阈值
    """

    enabled: bool = True
    interval_seconds: int = 60
    timeout_seconds: int = 10
    failure_threshold: int = 3


@dataclass
class PluginManifest:
    """插件清单数据类

    从 plugin-manifest.yaml 解析而来，
    包含插件的所有声明式元数据。

    Attributes:
        manifest_version: 清单格式版本
        name: 插件唯一标识名（snake_case）
        display_name: 插件显示名称
        version: 插件版本号（语义化版本）
        description: 插件描述
        plugin_type: 插件类型（core/optional）
        entry_point: 入口模块路径（相对于插件目录）
        dependencies: 依赖的其他插件名列表
        capabilities: 提供的能力列表
        subscriptions: 订阅的事件列表
        publications: 发布的事件列表
        config_schema: 配置参数模式
        health_check: 健康检查配置
        plugin_dir: 插件目录路径（解析时填充）
        manifest_path: 清单文件路径（解析时填充）
        metadata: 额外的元数据
    """

    manifest_version: str = "1.0"
    name: str = ""
    display_name: str = ""
    version: str = "0.0.0"
    description: str = ""
    plugin_type: PluginType = PluginType.OPTIONAL
    entry_point: str = "plugin.py"
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    subscriptions: List[str] = field(default_factory=list)
    publications: List[str] = field(default_factory=list)
    config_schema: List[ConfigSchemaField] = field(
        default_factory=list
    )
    health_check: HealthCheckConfig = field(
        default_factory=HealthCheckConfig
    )
    plugin_dir: str = ""
    manifest_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def parse_manifest(manifest_path: str) -> PluginManifest:
    """解析插件清单文件

    Args:
        manifest_path: plugin-manifest.yaml 文件的完整路径

    Returns:
        解析后的 PluginManifest 实例

    Raises:
        ManifestValidationError: 清单文件格式错误或缺少必需字段
        FileNotFoundError: 清单文件不存在
    """
    path = Path(manifest_path)

    if not path.exists():
        raise FileNotFoundError(
            f"清单文件不存在: {manifest_path}"
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ManifestValidationError(
            f"YAML 解析错误: {e}",
            validation_errors=[str(e)],
        ) from e

    if not isinstance(raw_data, dict):
        raise ManifestValidationError(
            "清单文件内容必须是字典格式",
            validation_errors=["根节点不是字典"],
        )

    return _build_manifest(raw_data, manifest_path)


def _build_manifest(
    data: Dict[str, Any], manifest_path: str
) -> PluginManifest:
    """从字典数据构建 PluginManifest

    Args:
        data: 从 YAML 解析的字典数据
        manifest_path: 清单文件路径

    Returns:
        构建的 PluginManifest 实例

    Raises:
        ManifestValidationError: 验证失败
    """
    # 验证必需字段
    errors = _validate_required_fields(data)
    if errors:
        raise ManifestValidationError(
            f"清单验证失败: {', '.join(errors)}",
            plugin_name=data.get("name"),
            validation_errors=errors,
        )

    # 验证清单版本
    manifest_version = str(data.get("manifest_version", "1.0"))
    if manifest_version not in SUPPORTED_MANIFEST_VERSIONS:
        raise ManifestValidationError(
            f"不支持的清单版本: {manifest_version}",
            plugin_name=data.get("name"),
            validation_errors=[
                f"支持的版本: {SUPPORTED_MANIFEST_VERSIONS}"
            ],
        )

    # 解析插件类型
    plugin_type_str = data.get("plugin_type", "optional")
    try:
        plugin_type = PluginType(plugin_type_str)
    except ValueError:
        plugin_type = PluginType.OPTIONAL
        logger.warning(
            "未知的插件类型 '%s'，默认为 optional",
            plugin_type_str,
        )

    # 解析配置模式
    config_schema = _parse_config_schema(
        data.get("config_schema", {})
    )

    # 解析健康检查配置
    health_check = _parse_health_check(
        data.get("health_check", {})
    )

    # 提取已知字段外的额外元数据
    known_fields = {
        "manifest_version",
        "name",
        "display_name",
        "version",
        "description",
        "plugin_type",
        "entry_point",
        "dependencies",
        "capabilities",
        "subscriptions",
        "publications",
        "config_schema",
        "health_check",
    }
    metadata = {
        k: v for k, v in data.items() if k not in known_fields
    }

    plugin_dir = str(Path(manifest_path).parent)

    manifest = PluginManifest(
        manifest_version=manifest_version,
        name=data["name"],
        display_name=data.get("display_name", data["name"]),
        version=data["version"],
        description=data.get("description", ""),
        plugin_type=plugin_type,
        entry_point=data.get("entry_point", "plugin.py"),
        dependencies=data.get("dependencies", []),
        capabilities=data.get("capabilities", []),
        subscriptions=data.get("subscriptions", []),
        publications=data.get("publications", []),
        config_schema=config_schema,
        health_check=health_check,
        plugin_dir=plugin_dir,
        manifest_path=manifest_path,
        metadata=metadata,
    )

    logger.debug(
        "清单解析成功: name=%s, version=%s, type=%s",
        manifest.name,
        manifest.version,
        manifest.plugin_type.value,
    )

    return manifest


def _validate_required_fields(
    data: Dict[str, Any],
) -> List[str]:
    """验证必需字段

    Args:
        data: 清单数据字典

    Returns:
        验证错误列表（空列表表示验证通过）
    """
    errors: List[str] = []

    for field_name in REQUIRED_FIELDS:
        if field_name not in data:
            errors.append(f"缺少必需字段: {field_name}")
        elif not data[field_name]:
            errors.append(f"必需字段不能为空: {field_name}")

    # 验证 name 格式（必须是 snake_case）
    name = data.get("name", "")
    if name and not _is_valid_plugin_name(name):
        errors.append(
            f"插件名称格式无效: '{name}' "
            f"（必须是 snake_case，仅包含小写字母、数字和下划线）"
        )

    return errors


def _is_valid_plugin_name(name: str) -> bool:
    """验证插件名称是否符合 snake_case 规范

    Args:
        name: 插件名称

    Returns:
        是否有效
    """
    if not name:
        return False
    # 允许小写字母、数字和下划线，不能以数字或下划线开头
    import re

    return bool(re.match(r"^[a-z][a-z0-9_]*$", name))


def _parse_config_schema(
    schema_data: Any,
) -> List[ConfigSchemaField]:
    """解析配置参数模式

    Args:
        schema_data: 配置模式数据（字典或列表）

    Returns:
        ConfigSchemaField 列表
    """
    if not schema_data:
        return []

    fields: List[ConfigSchemaField] = []

    if isinstance(schema_data, dict):
        for name, field_def in schema_data.items():
            if isinstance(field_def, dict):
                fields.append(
                    ConfigSchemaField(
                        name=name,
                        field_type=field_def.get("type", "str"),
                        default=field_def.get("default"),
                        description=field_def.get(
                            "description", ""
                        ),
                        required=field_def.get("required", False),
                        min_value=field_def.get("min"),
                        max_value=field_def.get("max"),
                        choices=field_def.get("choices"),
                    )
                )
            else:
                # 简写形式：name: default_value
                fields.append(
                    ConfigSchemaField(
                        name=name,
                        default=field_def,
                    )
                )
    elif isinstance(schema_data, list):
        for item in schema_data:
            if isinstance(item, dict) and "name" in item:
                fields.append(
                    ConfigSchemaField(
                        name=item["name"],
                        field_type=item.get("type", "str"),
                        default=item.get("default"),
                        description=item.get("description", ""),
                        required=item.get("required", False),
                        min_value=item.get("min"),
                        max_value=item.get("max"),
                        choices=item.get("choices"),
                    )
                )

    return fields


def _parse_health_check(
    hc_data: Any,
) -> HealthCheckConfig:
    """解析健康检查配置

    Args:
        hc_data: 健康检查配置数据

    Returns:
        HealthCheckConfig 实例
    """
    if not isinstance(hc_data, dict):
        return HealthCheckConfig()

    return HealthCheckConfig(
        enabled=hc_data.get("enabled", True),
        interval_seconds=hc_data.get("interval_seconds", 60),
        timeout_seconds=hc_data.get("timeout_seconds", 10),
        failure_threshold=hc_data.get("failure_threshold", 3),
    )


def discover_manifests(
    plugins_dir: str,
) -> List[str]:
    """发现插件目录下所有有效的清单文件

    扫描 plugins_dir 下的每个子目录，
    查找 plugin-manifest.yaml 文件。
    跳过 .disabled 后缀的清单文件。

    Args:
        plugins_dir: 插件根目录路径

    Returns:
        有效清单文件路径列表
    """
    manifests: List[str] = []
    plugins_path = Path(plugins_dir)

    if not plugins_path.exists():
        logger.warning("插件目录不存在: %s", plugins_dir)
        return manifests

    for item in sorted(plugins_path.iterdir()):
        if not item.is_dir():
            continue

        # 跳过以 . 或 _ 开头的目录
        if item.name.startswith((".","_")):
            continue

        manifest_path = item / MANIFEST_FILENAME
        disabled_path = item / (
            MANIFEST_FILENAME + MANIFEST_DISABLED_SUFFIX
        )

        if disabled_path.exists():
            logger.info(
                "插件已禁用（跳过）: %s", item.name
            )
            continue

        if manifest_path.exists():
            manifests.append(str(manifest_path))
            logger.debug(
                "发现插件清单: %s", manifest_path
            )
        else:
            logger.debug(
                "目录无清单文件（跳过）: %s", item.name
            )

    logger.info(
        "插件发现完成: 共发现 %d 个插件", len(manifests)
    )
    return manifests


def is_plugin_disabled(plugin_dir: str) -> bool:
    """检查插件是否被禁用

    Args:
        plugin_dir: 插件目录路径

    Returns:
        是否被禁用
    """
    disabled_path = Path(plugin_dir) / (
        MANIFEST_FILENAME + MANIFEST_DISABLED_SUFFIX
    )
    return disabled_path.exists()


def enable_plugin(plugin_dir: str) -> bool:
    """启用插件（将 .disabled 后缀移除）

    Args:
        plugin_dir: 插件目录路径

    Returns:
        是否成功启用
    """
    disabled_path = Path(plugin_dir) / (
        MANIFEST_FILENAME + MANIFEST_DISABLED_SUFFIX
    )
    enabled_path = Path(plugin_dir) / MANIFEST_FILENAME

    if not disabled_path.exists():
        logger.warning(
            "插件未被禁用，无需启用: %s", plugin_dir
        )
        return False

    try:
        disabled_path.rename(enabled_path)
        logger.info("插件已启用: %s", plugin_dir)
        return True
    except OSError as e:
        logger.error(
            "启用插件失败: %s, error=%s", plugin_dir, e
        )
        return False


def disable_plugin(plugin_dir: str) -> bool:
    """禁用插件（添加 .disabled 后缀）

    Args:
        plugin_dir: 插件目录路径

    Returns:
        是否成功禁用
    """
    enabled_path = Path(plugin_dir) / MANIFEST_FILENAME
    disabled_path = Path(plugin_dir) / (
        MANIFEST_FILENAME + MANIFEST_DISABLED_SUFFIX
    )

    if not enabled_path.exists():
        logger.warning(
            "清单文件不存在，无法禁用: %s", plugin_dir
        )
        return False

    try:
        enabled_path.rename(disabled_path)
        logger.info("插件已禁用: %s", plugin_dir)
        return True
    except OSError as e:
        logger.error(
            "禁用插件失败: %s, error=%s", plugin_dir, e
        )
        return False
