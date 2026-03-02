"""
配置加载工具模块

提供统一的配置文件加载功能，支持YAML和JSON格式。
支持环境变量覆盖和多配置合并。

使用方式：
    from src.utils.config_loader import ConfigLoader, load_config

    # 方式1: 使用加载器类
    loader = ConfigLoader()
    config = loader.load("config.yaml")

    # 方式2: 使用便捷函数
    config = load_config("config.yaml")

    # 方式3: 带环境变量覆盖
    config = load_config("config.yaml", env_override=True)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Union

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    配置加载器

    功能：
    - 支持 YAML 和 JSON 格式
    - 支持环境变量覆盖
    - 支持配置合并
    - 支持默认值
    - 支持配置验证
    """

    def __init__(
        self,
        base_dir: Optional[Union[str, Path]] = None,
        env_prefix: str = "WYCKOFF_",
    ):
        """
        初始化配置加载器

        Args:
            base_dir: 基础目录，默认当前工作目录
            env_prefix: 环境变量前缀
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.env_prefix = env_prefix
        self._cache: dict[str, dict] = {}

    def load(
        self,
        config_path: Union[str, Path],
        env_override: bool = True,
        validate: bool = False,
    ) -> dict[str, Any]:
        """
        加载配置文件

        Args:
            config_path: 配置文件路径（相对于base_dir）
            env_override: 是否用环境变量覆盖配置
            validate: 是否验证配置

        Returns:
            配置字典
        """
        config_path = Path(config_path)

        # 如果是绝对路径，直接使用
        if not config_path.is_absolute():
            config_path = self.base_dir / config_path

        # 检查缓存
        cache_key = str(config_path)
        if cache_key in self._cache and not env_override:
            return self._cache[cache_key].copy()

        # 加载配置
        config = self._load_file(config_path)

        # 环境变量覆盖
        if env_override:
            config = self._apply_env_override(config)

        # 缓存
        self._cache[cache_key] = config

        # 验证
        if validate:
            self._validate(config)

        return config

    def load_multiple(
        self,
        config_paths: list[Union[str, Path]],
        merge: bool = True,
    ) -> dict[str, Any]:
        """
        加载多个配置文件

        Args:
            config_paths: 配置文件路径列表
            merge: 是否合并配置，False则返回列表

        Returns:
            合并后的配置字典或配置列表
        """
        configs = [self.load(p) for p in config_paths]

        if not merge:
            return configs

        # 合并配置
        result = {}
        for config in configs:
            result = self._merge_dict(result, config)

        return result

    def _load_file(self, path: Path) -> dict[str, Any]:
        """加载单个配置文件"""
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        suffix = path.suffix.lower()

        if suffix in (".yaml", ".yml"):
            return self._load_yaml(path)
        if suffix == ".json":
            return self._load_json(path)
        raise ValueError(f"不支持的配置文件格式: {suffix}")

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """加载YAML文件"""
        try:
            with open(path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config or {}
        except yaml.YAMLError:
            logger.exception(f"YAML解析错误 {path}")
            raise

    def _load_json(self, path: Path) -> dict[str, Any]:
        """加载JSON文件"""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.exception(f"JSON解析错误 {path}")
            raise

    def _apply_env_override(self, config: dict[str, Any]) -> dict[str, Any]:
        """应用环境变量覆盖"""
        result = config.copy()

        for key, value in config.items():
            env_key = f"{self.env_prefix}{key.upper()}"
            env_value = os.environ.get(env_key)

            if env_value is not None:
                # 尝试转换类型
                result[key] = self._parse_env_value(env_value)
                logger.info(f"环境变量覆盖: {key} = {result[key]}")

            # 递归处理嵌套字典
            if isinstance(value, dict):
                result[key] = self._apply_env_override(value)

        return result

    def _parse_env_value(self, value: str) -> Any:
        """解析环境变量值"""
        # 布尔值
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # 数字
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # 字符串
        return value

    def _merge_dict(self, base: dict, override: dict) -> dict:
        """深度合并字典"""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dict(result[key], value)
            else:
                result[key] = value

        return result

    def _validate(self, config: dict[str, Any]) -> None:
        """验证配置（基础验证）"""
        # 检查必需字段
        required_fields = ["symbols", "timeframes"]
        for field in required_fields:
            if field not in config:
                logger.warning(f"配置缺少必需字段: {field}")

    def clear_cache(self) -> None:
        """清空配置缓存"""
        self._cache.clear()


# 全局默认加载器
_default_loader: Optional[ConfigLoader] = None


def get_loader() -> ConfigLoader:
    """获取全局默认加载器"""
    global _default_loader
    if _default_loader is None:
        _default_loader = ConfigLoader()
    return _default_loader


def load_config(
    config_path: Union[str, Path],
    env_override: bool = True,
    validate: bool = False,
) -> dict[str, Any]:
    """
    便捷配置加载函数

    Args:
        config_path: 配置文件路径
        env_override: 是否用环境变量覆盖配置
        validate: 是否验证配置

    Returns:
        配置字典
    """
    return get_loader().load(config_path, env_override, validate)


def load_config_with_defaults(
    config_path: Union[str, Path],
    defaults: dict[str, Any],
    env_override: bool = True,
) -> dict[str, Any]:
    """
    加载配置并合并默认值

    Args:
        config_path: 配置文件路径
        defaults: 默认配置
        env_override: 是否用环境变量覆盖

    Returns:
        合并后的配置
    """
    loader = get_loader()

    # 加载用户配置
    try:
        user_config = loader.load(config_path, env_override=False)
    except FileNotFoundError:
        user_config = {}

    # 合并配置（用户配置覆盖默认配置）
    result = defaults.copy()
    result = loader._merge_dict(result, user_config)

    # 应用环境变量覆盖
    if env_override:
        result = loader._apply_env_override(result)

    return result


# 导出
__all__ = [
    "ConfigLoader",
    "get_loader",
    "load_config",
    "load_config_with_defaults",
]
