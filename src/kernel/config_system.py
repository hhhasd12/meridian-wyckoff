"""统一配置管理系统

提供分层配置管理，支持：
1. 全局配置（config.yaml）
2. 插件级配置隔离（plugins.{name}.config）
3. 配置模式验证（基于 plugin-manifest.yaml 的 config_schema）
4. 环境变量覆盖
5. 配置变更通知

配置优先级（从高到低）：
    环境变量 > 运行时修改 > config.yaml > 默认值
"""

import copy
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import yaml

from src.kernel.plugin_manifest import (
    ConfigSchemaField,
    PluginManifest,
)
from src.kernel.types import PluginConfigError

logger = logging.getLogger(__name__)

# 环境变量前缀
ENV_PREFIX = "WYCKOFF_"


class ConfigSystem:
    """统一配置管理系统

    管理全局配置和插件级配置，支持分层覆盖、
    模式验证和变更通知。

    Example:
        >>> config = ConfigSystem("config.yaml")
        >>> config.load()
        >>> db_host = config.get("database.host", "localhost")
        >>> plugin_cfg = config.get_plugin_config("market_regime")
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
    ) -> None:
        """初始化配置系统

        Args:
            config_path: 全局配置文件路径（YAML 格式）
        """
        self._config_path = config_path
        self._global_config: Dict[str, Any] = {}
        self._plugin_configs: Dict[str, Dict[str, Any]] = {}
        self._defaults: Dict[str, Dict[str, Any]] = {}
        self._change_listeners: List[
            Callable[[str, str, Any, Any], None]
        ] = []
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """配置是否已加载"""
        return self._loaded

    def load(
        self, config_path: Optional[str] = None
    ) -> None:
        """加载全局配置文件

        Args:
            config_path: 配置文件路径（覆盖构造函数中的路径）

        Raises:
            FileNotFoundError: 配置文件不存在
            PluginConfigError: 配置文件格式错误
        """
        path = config_path or self._config_path
        if path is None:
            logger.info("未指定配置文件路径，使用空配置")
            self._apply_env_overrides()
            self._loaded = True
            return

        config_file = Path(path)
        if not config_file.exists():
            logger.warning(
                "配置文件不存在: %s，使用空配置", path
            )
            self._apply_env_overrides()
            self._loaded = True
            return

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise PluginConfigError(
                f"配置文件解析错误: {e}"
            ) from e

        if not isinstance(raw_config, dict):
            raise PluginConfigError(
                "配置文件根节点必须是字典格式"
            )

        self._global_config = raw_config

        # 提取插件级配置
        plugins_section = raw_config.get("plugins", {})
        if isinstance(plugins_section, dict):
            for plugin_name, plugin_cfg in plugins_section.items():
                if isinstance(plugin_cfg, dict):
                    self._plugin_configs[plugin_name] = (
                        plugin_cfg.get("config", plugin_cfg)
                    )

        # 应用环境变量覆盖
        self._apply_env_overrides()

        self._loaded = True
        logger.info(
            "配置加载完成: %s, 插件配置数: %d",
            path,
            len(self._plugin_configs),
        )

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """获取全局配置值

        支持点号分隔的嵌套键。

        Args:
            key: 配置键名（如 "database.host"）
            default: 默认值

        Returns:
            配置值
        """
        return self._get_nested(
            self._global_config, key, default
        )

    def set(self, key: str, value: Any) -> None:
        """设置全局配置值

        Args:
            key: 配置键名（支持点号分隔）
            value: 配置值
        """
        old_value = self.get(key)
        self._set_nested(self._global_config, key, value)
        self._notify_change("global", key, old_value, value)

    def get_plugin_config(
        self,
        plugin_name: str,
    ) -> Dict[str, Any]:
        """获取插件级配置

        合并默认值和用户配置，返回完整的插件配置。

        Args:
            plugin_name: 插件名称

        Returns:
            插件配置字典
        """
        defaults = self._defaults.get(plugin_name, {})
        user_config = self._plugin_configs.get(
            plugin_name, {}
        )

        # 默认值 + 用户配置（用户配置优先）
        merged = copy.deepcopy(defaults)
        merged.update(user_config)
        return merged

    def set_plugin_config(
        self,
        plugin_name: str,
        config: Dict[str, Any],
    ) -> None:
        """设置插件级配置

        Args:
            plugin_name: 插件名称
            config: 配置字典
        """
        old_config = self._plugin_configs.get(
            plugin_name, {}
        )
        self._plugin_configs[plugin_name] = config
        self._notify_change(
            plugin_name, "*", old_config, config
        )

    def update_plugin_config(
        self,
        plugin_name: str,
        key: str,
        value: Any,
    ) -> None:
        """更新插件级配置的单个键

        Args:
            plugin_name: 插件名称
            key: 配置键名
            value: 配置值
        """
        if plugin_name not in self._plugin_configs:
            self._plugin_configs[plugin_name] = {}

        old_value = self._plugin_configs[plugin_name].get(key)
        self._plugin_configs[plugin_name][key] = value
        self._notify_change(
            plugin_name, key, old_value, value
        )

    def register_defaults(
        self,
        plugin_name: str,
        manifest: PluginManifest,
    ) -> None:
        """从清单的 config_schema 注册默认配置值

        Args:
            plugin_name: 插件名称
            manifest: 插件清单
        """
        defaults: Dict[str, Any] = {}
        for field_def in manifest.config_schema:
            if field_def.default is not None:
                defaults[field_def.name] = field_def.default
        self._defaults[plugin_name] = defaults
        logger.debug(
            "注册默认配置: plugin=%s, keys=%s",
            plugin_name,
            list(defaults.keys()),
        )

    def validate_plugin_config(
        self,
        plugin_name: str,
        manifest: PluginManifest,
    ) -> List[str]:
        """验证插件配置是否符合清单中的 config_schema

        Args:
            plugin_name: 插件名称
            manifest: 插件清单

        Returns:
            验证错误列表（空列表表示验证通过）
        """
        config = self.get_plugin_config(plugin_name)
        errors: List[str] = []

        for field_def in manifest.config_schema:
            value = config.get(field_def.name)

            # 检查必需字段
            if field_def.required and value is None:
                errors.append(
                    f"缺少必需配置: {field_def.name}"
                )
                continue

            if value is None:
                continue

            # 类型检查
            type_error = self._check_type(
                field_def.name,
                value,
                field_def.field_type,
            )
            if type_error:
                errors.append(type_error)
                continue

            # 范围检查
            if isinstance(value, (int, float)):
                if (
                    field_def.min_value is not None
                    and value < field_def.min_value
                ):
                    errors.append(
                        f"{field_def.name}: 值 {value} "
                        f"小于最小值 {field_def.min_value}"
                    )
                if (
                    field_def.max_value is not None
                    and value > field_def.max_value
                ):
                    errors.append(
                        f"{field_def.name}: 值 {value} "
                        f"大于最大值 {field_def.max_value}"
                    )

            # 选项检查
            if (
                field_def.choices is not None
                and value not in field_def.choices
            ):
                errors.append(
                    f"{field_def.name}: 值 '{value}' "
                    f"不在可选范围 {field_def.choices} 内"
                )

        return errors

    def add_change_listener(
        self,
        listener: Callable[[str, str, Any, Any], None],
    ) -> None:
        """添加配置变更监听器

        监听器签名: (scope, key, old_value, new_value) -> None
        scope 为 "global" 或插件名称。

        Args:
            listener: 变更回调函数
        """
        self._change_listeners.append(listener)

    def remove_change_listener(
        self,
        listener: Callable[[str, str, Any, Any], None],
    ) -> None:
        """移除配置变更监听器

        Args:
            listener: 要移除的回调函数
        """
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def to_dict(self) -> Dict[str, Any]:
        """导出完整配置为字典

        Returns:
            包含全局配置和插件配置的字典
        """
        return {
            "global": copy.deepcopy(self._global_config),
            "plugins": copy.deepcopy(self._plugin_configs),
            "defaults": copy.deepcopy(self._defaults),
        }

    # ---- 内部方法 ----

    def _get_nested(
        self,
        data: Dict[str, Any],
        key: str,
        default: Any = None,
    ) -> Any:
        """获取嵌套字典中的值

        Args:
            data: 数据字典
            key: 点号分隔的键名
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split(".")
        value: Any = data

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def _set_nested(
        self,
        data: Dict[str, Any],
        key: str,
        value: Any,
    ) -> None:
        """设置嵌套字典中的值

        Args:
            data: 数据字典
            key: 点号分隔的键名
            value: 要设置的值
        """
        keys = key.split(".")
        current = data

        for k in keys[:-1]:
            if k not in current or not isinstance(
                current[k], dict
            ):
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def _apply_env_overrides(self) -> None:
        """应用环境变量覆盖

        环境变量格式: WYCKOFF_{SECTION}_{KEY}
        例如: WYCKOFF_DATABASE_HOST -> database.host
        """
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(ENV_PREFIX):
                continue

            # 移除前缀并转换为配置键
            config_key = (
                env_key[len(ENV_PREFIX):]
                .lower()
                .replace("__", ".")
            )

            # 尝试类型转换
            typed_value = self._parse_env_value(env_value)
            self._set_nested(
                self._global_config, config_key, typed_value
            )
            logger.debug(
                "环境变量覆盖: %s -> %s",
                env_key,
                config_key,
            )

    def _parse_env_value(self, value: str) -> Any:
        """解析环境变量值的类型

        Args:
            value: 环境变量字符串值

        Returns:
            类型转换后的值
        """
        # 布尔值
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # 整数
        try:
            return int(value)
        except ValueError:
            pass

        # 浮点数
        try:
            return float(value)
        except ValueError:
            pass

        return value

    def _check_type(
        self,
        name: str,
        value: Any,
        expected_type: str,
    ) -> Optional[str]:
        """检查值的类型是否匹配

        Args:
            name: 字段名称
            value: 字段值
            expected_type: 期望的类型字符串

        Returns:
            错误信息，None 表示类型匹配
        """
        type_map = {
            "str": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "list": list,
            "dict": dict,
        }

        expected = type_map.get(expected_type)
        if expected is None:
            return None  # 未知类型，跳过检查

        if not isinstance(value, expected):
            return (
                f"{name}: 类型不匹配，"
                f"期望 {expected_type}，"
                f"实际 {type(value).__name__}"
            )

        return None

    def _notify_change(
        self,
        scope: str,
        key: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """通知配置变更

        Args:
            scope: 变更范围（"global" 或插件名称）
            key: 变更的键名
            old_value: 旧值
            new_value: 新值
        """
        for listener in self._change_listeners:
            try:
                listener(scope, key, old_value, new_value)
            except Exception as e:
                logger.error(
                    "配置变更监听器异常: %s", e,
                    exc_info=True,
                )
