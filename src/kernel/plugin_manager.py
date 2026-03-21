"""插件管理器 - 内核核心组件

PluginManager 负责插件的完整生命周期管理：
- 发现：扫描 plugins 目录，解析 plugin-manifest.yaml
- 加载：按依赖顺序加载插件，注入 EventBus 和配置
- 卸载：安全卸载插件，清理资源
- 重载：热重载单个插件
- 健康检查：定期检查所有插件状态
- 错误隔离：单个插件崩溃不影响其他插件

参考：VCP Plugin.js 中的 PluginManager 类
"""

import importlib
import importlib.util
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type

from src.kernel.base_plugin import BasePlugin
from src.kernel.config_system import ConfigSystem
from src.kernel.event_bus import EventBus
from src.kernel.plugin_manifest import (
    PluginManifest,
    discover_manifests,
    parse_manifest,
)
from src.kernel.types import (
    ConfigDict,
    HealthCheckResult,
    HealthStatus,
    PluginDependencyError,
    PluginError,
    PluginInfo,
    PluginLoadError,
    PluginState,
    PluginType,
)

logger = logging.getLogger(__name__)


class PluginManager:
    """插件管理器

    管理所有插件的生命周期，提供发现、加载、卸载、
    重载、健康检查等功能。

    Example:
        >>> manager = PluginManager(
        ...     plugins_dir="src/plugins",
        ...     config_system=config,
        ...     event_bus=bus,
        ... )
        >>> manager.discover_plugins()
        >>> manager.load_all()
        >>> regime_plugin = manager.get_plugin("market_regime")
    """

    def __init__(
        self,
        plugins_dir: str = "src/plugins",
        config_system: Optional[ConfigSystem] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._plugins_dir = plugins_dir
        self._config = config_system or ConfigSystem()
        self._event_bus = event_bus or EventBus()
        # 已注册的清单: name -> PluginManifest
        self._manifests: Dict[str, PluginManifest] = {}
        # 已加载的插件实例: name -> BasePlugin
        self._plugins: Dict[str, BasePlugin] = {}
        # 插件运行时信息: name -> PluginInfo
        self._plugin_infos: Dict[str, PluginInfo] = {}
        # 加载顺序记录
        self._load_order: List[str] = []

    # ---- 公共 API ----

    def discover_plugins(self) -> List[str]:
        """发现所有可用插件

        扫描插件目录，解析清单文件，注册到管理器。

        Returns:
            发现的插件名称列表
        """
        manifest_paths = discover_manifests(self._plugins_dir)
        discovered: List[str] = []

        for path in manifest_paths:
            try:
                manifest = parse_manifest(path)
                self._manifests[manifest.name] = manifest
                # 注册默认配置
                self._config.register_defaults(
                    manifest.name, manifest
                )
                discovered.append(manifest.name)
                logger.info(
                    "注册插件: %s v%s (%s)",
                    manifest.name,
                    manifest.version,
                    manifest.plugin_type.value,
                )
            except Exception as e:
                logger.error(
                    "解析清单失败: %s, error=%s",
                    path, e,
                )

        self._event_bus.emit(
            "kernel.plugins_discovered",
            {"plugins": discovered, "count": len(discovered)},
            publisher="kernel",
        )
        return discovered

    def load_plugin(self, name: str) -> BasePlugin:
        """加载单个插件

        Args:
            name: 插件名称

        Returns:
            加载的插件实例

        Raises:
            PluginLoadError: 插件不存在或加载失败
            PluginDependencyError: 依赖未满足
        """
        if name in self._plugins:
            plugin = self._plugins[name]
            if plugin.is_active:
                logger.debug("插件已加载: %s", name)
                return plugin

        manifest = self._manifests.get(name)
        if manifest is None:
            raise PluginLoadError(
                f"插件未注册: {name}", plugin_name=name
            )

        # 检查依赖
        self._check_dependencies(name, manifest)

        # 加载依赖（递归）
        for dep in manifest.dependencies:
            if dep not in self._plugins or not self._plugins[dep].is_active:
                self.load_plugin(dep)

        # 动态导入插件模块
        plugin_instance = self._import_plugin(name, manifest)

        # 注入依赖
        plugin_config = self._config.get_plugin_config(name)
        plugin_instance._config = plugin_config
        plugin_instance._set_event_bus(self._event_bus)
        plugin_instance._set_plugin_manager(self)

        # 创建运行时信息
        info = PluginInfo(
            name=name,
            display_name=manifest.display_name,
            version=manifest.version,
            plugin_type=manifest.plugin_type,
            entry_point=manifest.entry_point,
            plugin_dir=manifest.plugin_dir,
            dependencies=manifest.dependencies,
            capabilities=manifest.capabilities,
        )
        plugin_instance._set_plugin_info(info)
        self._plugin_infos[name] = info

        # 执行加载
        try:
            plugin_instance._do_load()
            self._plugins[name] = plugin_instance
            self._load_order.append(name)
            info.state = PluginState.ACTIVE
            info.load_time = plugin_instance._load_time

            self._event_bus.emit(
                "plugin.loaded",
                {"name": name, "version": manifest.version},
                publisher="kernel",
            )
            return plugin_instance

        except PluginError as pe:
            info.state = PluginState.ERROR
            info.error_message = plugin_instance._error_message
            self._plugin_infos[name] = info
            raise PluginLoadError(
                str(pe), plugin_name=name
            ) from pe
        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            self._plugin_infos[name] = info
            raise PluginLoadError(
                f"加载失败: {e}", plugin_name=name
            ) from e

    def unload_plugin(self, name: str) -> bool:
        """卸载单个插件

        Args:
            name: 插件名称

        Returns:
            是否成功卸载
        """
        plugin = self._plugins.get(name)
        if plugin is None:
            logger.warning("插件未加载: %s", name)
            return False

        # 检查是否有其他插件依赖此插件
        dependents = self._get_dependents(name)
        if dependents:
            logger.warning(
                "无法卸载 %s，以下插件依赖它: %s",
                name, dependents,
            )
            return False

        # 执行卸载
        plugin._do_unload()
        del self._plugins[name]
        if name in self._load_order:
            self._load_order.remove(name)

        if name in self._plugin_infos:
            self._plugin_infos[name].state = PluginState.UNLOADED

        self._event_bus.emit(
            "plugin.unloaded",
            {"name": name},
            publisher="kernel",
        )
        logger.info("插件已卸载: %s", name)
        return True

    def reload_plugin(self, name: str) -> BasePlugin:
        """热重载插件

        Args:
            name: 插件名称

        Returns:
            重载后的插件实例

        Raises:
            PluginLoadError: 重载失败
        """
        logger.info("开始重载插件: %s", name)

        if name in self._plugins:
            self.unload_plugin(name)

        # 重新解析清单
        manifest = self._manifests.get(name)
        if manifest and manifest.manifest_path:
            try:
                new_manifest = parse_manifest(
                    manifest.manifest_path
                )
                self._manifests[name] = new_manifest
            except Exception as e:
                logger.error(
                    "重新解析清单失败: %s", e
                )

        return self.load_plugin(name)

    def load_all(self) -> Dict[str, bool]:
        """加载所有已发现的插件

        按依赖顺序加载，core 类型优先。

        Returns:
            加载结果字典: name -> success
        """
        results: Dict[str, bool] = {}
        load_order = self._resolve_load_order()

        for name in load_order:
            try:
                self.load_plugin(name)
                results[name] = True
            except Exception as e:
                results[name] = False
                manifest = self._manifests.get(name)
                if manifest and manifest.plugin_type == PluginType.CORE:
                    logger.error(
                        "核心插件加载失败: %s, error=%s",
                        name, e,
                    )
                else:
                    logger.warning(
                        "可选插件加载失败: %s, error=%s",
                        name, e,
                    )

        loaded = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        logger.info(
            "批量加载完成: 成功=%d, 失败=%d",
            loaded, failed,
        )

        self._event_bus.emit(
            "kernel.all_plugins_loaded",
            {"results": results},
            publisher="kernel",
        )
        return results

    def unload_all(self) -> None:
        """卸载所有插件（按加载逆序）"""
        for name in reversed(list(self._load_order)):
            try:
                plugin = self._plugins.get(name)
                if plugin:
                    plugin._do_unload()
            except Exception as e:
                logger.error(
                    "卸载插件异常: %s, error=%s",
                    name, e,
                )

        self._plugins.clear()
        self._load_order.clear()

        # 更新所有插件信息的状态为 UNLOADED
        for info in self._plugin_infos.values():
            if info.state == PluginState.ACTIVE:
                info.state = PluginState.UNLOADED

        logger.info("所有插件已卸载")

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """获取已加载的插件实例

        Args:
            name: 插件名称

        Returns:
            插件实例，未找到返回 None
        """
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginInfo]:
        """列出所有已注册插件的信息

        Returns:
            PluginInfo 列表
        """
        infos: List[PluginInfo] = []
        for name, manifest in self._manifests.items():
            if name in self._plugin_infos:
                infos.append(self._plugin_infos[name])
            else:
                infos.append(
                    PluginInfo(
                        name=name,
                        display_name=manifest.display_name,
                        version=manifest.version,
                        plugin_type=manifest.plugin_type,
                        state=PluginState.UNLOADED,
                    )
                )
        return infos

    def health_check_all(self) -> Dict[str, HealthCheckResult]:
        """对所有活跃插件执行健康检查

        Returns:
            健康检查结果字典: name -> HealthCheckResult
        """
        results: Dict[str, HealthCheckResult] = {}

        for name, plugin in self._plugins.items():
            try:
                result = plugin.health_check()
                results[name] = result
                if name in self._plugin_infos:
                    self._plugin_infos[name].last_health_check = result
            except Exception as e:
                results[name] = HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message=f"健康检查异常: {e}",
                )

        return results

    def get_event_bus(self) -> EventBus:
        """获取事件总线实例"""
        return self._event_bus

    def get_config_system(self) -> ConfigSystem:
        """获取配置系统实例"""
        return self._config

    # ---- 内部方法 ----

    def _import_plugin(
        self,
        name: str,
        manifest: PluginManifest,
    ) -> BasePlugin:
        """动态导入插件模块并实例化

        Args:
            name: 插件名称
            manifest: 插件清单

        Returns:
            插件实例

        Raises:
            PluginLoadError: 导入或实例化失败
        """
        plugin_dir = Path(manifest.plugin_dir)
        entry_point = manifest.entry_point

        # 构建模块路径
        if entry_point.endswith(".py"):
            entry_point = entry_point[:-3]

        module_file = plugin_dir / f"{entry_point}.py"
        if not module_file.exists():
            raise PluginLoadError(
                f"入口文件不存在: {module_file}",
                plugin_name=name,
            )

        # 构建模块名：优先通过 src/plugins 路径结构推断
        module_name = self._infer_module_name(
            module_file, name, entry_point
        )

        if module_name.endswith(".py"):
            module_name = module_name[:-3]

        try:
            # 使用 importlib 动态加载
            spec = importlib.util.spec_from_file_location(
                module_name, str(module_file)
            )
            if spec is None or spec.loader is None:
                raise PluginLoadError(
                    f"无法创建模块规格: {module_file}",
                    plugin_name=name,
                )

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 查找 BasePlugin 子类
            plugin_class = self._find_plugin_class(
                module, name
            )
            if plugin_class is None:
                raise PluginLoadError(
                    f"未找到 BasePlugin 子类: {module_name}",
                    plugin_name=name,
                )

            # 实例化
            instance = plugin_class(name=name)
            return instance

        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(
                f"导入模块失败: {e}",
                plugin_name=name,
            ) from e

    @staticmethod
    def _infer_module_name(
        module_file: Path,
        name: str,
        entry_point: str,
    ) -> str:
        """推断插件模块名

        优先通过 src/plugins 路径结构推断，不依赖 Path.cwd()。
        例如: .../src/plugins/market_regime/plugin.py -> src.plugins.market_regime.plugin

        Args:
            module_file: 模块文件路径
            name: 插件名称
            entry_point: 入口点名称

        Returns:
            推断的模块名
        """
        # 优先从路径中查找 "src" 目录作为锚点
        parts = module_file.parts
        for i, part in enumerate(parts):
            if part == "src" and i + 1 < len(parts):
                # 从 "src" 开始构建模块路径
                module_parts = parts[i:]
                module_name = ".".join(module_parts)
                if module_name.endswith(".py"):
                    module_name = module_name[:-3]
                return module_name

        # 回退：使用 Path.cwd()（兼容旧行为）
        try:
            rel_path = module_file.relative_to(Path.cwd())
            module_name = str(rel_path).replace(
                "\\", "."
            ).replace("/", ".")
        except ValueError:
            module_name = f"plugins.{name}.{entry_point}"

        if module_name.endswith(".py"):
            module_name = module_name[:-3]
        return module_name

    def _find_plugin_class(
        self,
        module: Any,
        name: str,
    ) -> Optional[Type[BasePlugin]]:
        """在模块中查找 BasePlugin 子类

        Args:
            module: 已导入的模块
            name: 插件名称

        Returns:
            找到的插件类，未找到返回 None
        """
        candidates: List[Type[BasePlugin]] = []

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
                candidates.append(attr)

        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            # 优先选择名称匹配的类
            for cls in candidates:
                cls_name_lower = cls.__name__.lower()
                if name.replace("_", "") in cls_name_lower:
                    return cls
            return candidates[0]

        return None

    def _check_dependencies(
        self,
        name: str,
        manifest: PluginManifest,
    ) -> None:
        """检查插件依赖是否可满足

        Args:
            name: 插件名称
            manifest: 插件清单

        Raises:
            PluginDependencyError: 依赖不可满足
        """
        missing: List[str] = []
        for dep in manifest.dependencies:
            if dep not in self._manifests:
                missing.append(dep)

        if missing:
            raise PluginDependencyError(
                f"缺少依赖: {missing}",
                plugin_name=name,
                missing_dependencies=missing,
            )

    def _get_dependents(self, name: str) -> List[str]:
        """获取依赖指定插件的其他活跃插件

        Args:
            name: 插件名称

        Returns:
            依赖此插件的活跃插件名列表
        """
        dependents: List[str] = []
        for plugin_name, plugin in self._plugins.items():
            if plugin_name == name:
                continue
            manifest = self._manifests.get(plugin_name)
            if manifest and name in manifest.dependencies:
                if plugin.is_active:
                    dependents.append(plugin_name)
        return dependents

    def _resolve_load_order(self) -> List[str]:
        """解析插件加载顺序（拓扑排序）

        core 类型优先，然后按依赖关系排序。

        Returns:
            排序后的插件名称列表
        """
        # 分离 core 和 optional
        core_plugins: List[str] = []
        optional_plugins: List[str] = []

        for name, manifest in self._manifests.items():
            if manifest.plugin_type == PluginType.CORE:
                core_plugins.append(name)
            else:
                optional_plugins.append(name)

        # 对每组进行拓扑排序
        sorted_core = self._topological_sort(core_plugins)
        sorted_optional = self._topological_sort(
            optional_plugins
        )

        return sorted_core + sorted_optional

    def _topological_sort(
        self, plugin_names: List[str]
    ) -> List[str]:
        """拓扑排序（含循环依赖检测）

        使用三色标记法（WHITE/GRAY/BLACK）检测循环依赖：
        - WHITE: 未访问
        - GRAY: 正在访问（在递归栈中）
        - BLACK: 已完成访问

        Args:
            plugin_names: 待排序的插件名列表

        Returns:
            排序后的列表

        Raises:
            PluginDependencyError: 检测到循环依赖
        """
        name_set = set(plugin_names)
        # 三色标记: 0=WHITE(未访问), 1=GRAY(访问中), 2=BLACK(已完成)
        color: Dict[str, int] = {n: 0 for n in plugin_names}
        result: List[str] = []

        def visit(name: str, path: List[str]) -> None:
            if color.get(name, 0) == 2:  # BLACK - 已完成
                return
            if color.get(name, 0) == 1:  # GRAY - 循环依赖
                cycle_start = path.index(name)
                cycle = path[cycle_start:] + [name]
                raise PluginDependencyError(
                    f"检测到循环依赖: {' -> '.join(cycle)}",
                    plugin_name=name,
                    missing_dependencies=[],
                )
            color[name] = 1  # 标记为 GRAY（访问中）
            manifest = self._manifests.get(name)
            if manifest:
                for dep in manifest.dependencies:
                    if dep in name_set:
                        visit(dep, path + [name])
            color[name] = 2  # 标记为 BLACK（已完成）
            result.append(name)

        for name in plugin_names:
            if color.get(name, 0) == 0:
                visit(name, [])

        return result
