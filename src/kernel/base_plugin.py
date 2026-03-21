"""插件抽象基类

定义所有插件必须实现的标准生命周期接口。
每个插件继承 BasePlugin 并实现 on_load() 和 on_unload()。

生命周期状态转换：
    UNLOADED → LOADING → ACTIVE
    ACTIVE → UNLOADING → UNLOADED
    任意状态 → ERROR
    ERROR → UNLOADING → UNLOADED（恢复路径）

设计原则：
1. 最小化抽象方法 — 只有 on_load/on_unload 是必须实现的
2. 提供便捷方法 — emit_event, get_config 等
3. 错误隔离 — _safe_call 包装器捕获异常
4. 健康检查 — 可选覆盖 health_check 方法

参考：VCP Plugin.js 中的插件执行模式
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from src.kernel.types import (
    ConfigDict,
    HealthCheckResult,
    HealthStatus,
    PluginError,
    PluginInfo,
    PluginState,
    PluginType,
)

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    """插件抽象基类

    所有插件必须继承此类并实现 on_load() 和 on_unload() 方法。
    BasePlugin 提供标准的生命周期管理、事件通信和配置访问。

    Example:
        >>> class MarketRegimePlugin(BasePlugin):
        ...     def on_load(self) -> None:
        ...         self.detector = RegimeDetector(self.config)
        ...
        ...     def on_unload(self) -> None:
        ...         self.detector = None
        ...
        ...     def detect(self, df):
        ...         return self.detector.detect_regime(df)

    Attributes:
        name: 插件唯一标识名
        state: 当前生命周期状态
        config: 插件配置字典
        plugin_info: 插件运行时信息
    """

    def __init__(
        self,
        name: str,
        config: Optional[ConfigDict] = None,
    ) -> None:
        """初始化插件基类

        Args:
            name: 插件唯一标识名
            config: 插件配置字典
        """
        self._name = name
        self._state = PluginState.UNLOADED
        self._config: ConfigDict = config or {}
        self._event_bus: Any = None  # 由 PluginManager 注入
        self._plugin_manager: Any = None  # 由 PluginManager 注入
        self._plugin_info: Optional[PluginInfo] = None
        self._load_time: float = 0.0
        self._error_message: Optional[str] = None
        self._logger = logging.getLogger(
            f"plugin.{name}"
        )

    # ---- 属性 ----

    @property
    def name(self) -> str:
        """插件唯一标识名"""
        return self._name

    @property
    def state(self) -> PluginState:
        """当前生命周期状态"""
        return self._state

    @property
    def config(self) -> ConfigDict:
        """插件配置字典"""
        return self._config

    @property
    def plugin_info(self) -> Optional[PluginInfo]:
        """插件运行时信息"""
        return self._plugin_info

    @property
    def is_active(self) -> bool:
        """插件是否处于活跃状态"""
        return self._state == PluginState.ACTIVE

    @property
    def is_error(self) -> bool:
        """插件是否处于错误状态"""
        return self._state == PluginState.ERROR

    # ---- 抽象方法（子类必须实现） ----

    @abstractmethod
    def on_load(self) -> None:
        """插件加载回调

        在此方法中初始化插件所需的资源、
        注册事件订阅、创建内部对象等。

        此方法由 PluginManager 在加载插件时调用，
        不应由插件自身调用。

        Raises:
            PluginError: 加载失败时抛出
        """
        ...

    @abstractmethod
    def on_unload(self) -> None:
        """插件卸载回调

        在此方法中释放资源、取消事件订阅、
        清理临时文件等。

        此方法由 PluginManager 在卸载插件时调用，
        不应由插件自身调用。
        """
        ...

    # ---- 可选覆盖方法 ----

    def on_config_update(
        self, new_config: ConfigDict
    ) -> None:
        """配置更新回调

        当插件配置发生变化时调用。
        默认实现直接替换配置字典。
        子类可覆盖此方法实现热更新逻辑。

        Args:
            new_config: 新的配置字典
        """
        self._config = new_config
        self._logger.info("配置已更新")

    def health_check(self) -> HealthCheckResult:
        """健康检查

        返回插件当前的健康状态。
        默认实现基于插件状态返回结果。
        子类可覆盖此方法实现自定义检查逻辑。

        Returns:
            HealthCheckResult 实例
        """
        if self._state == PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message=f"插件 {self._name} 运行正常",
            )
        elif self._state == PluginState.ERROR:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=(
                    f"插件 {self._name} 处于错误状态: "
                    f"{self._error_message}"
                ),
            )
        else:
            return HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message=(
                    f"插件 {self._name} 状态: "
                    f"{self._state.value}"
                ),
            )

    # ---- 便捷方法（子类可直接使用） ----

    def emit_event(
        self,
        event_name: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """发布事件到事件总线

        Args:
            event_name: 事件名称
            data: 事件数据

        Returns:
            成功处理的处理器数量
        """
        if self._event_bus is None:
            self._logger.warning(
                "事件总线未注入，无法发布事件: %s",
                event_name,
            )
            return 0

        return self._event_bus.emit(
            event_name,
            data or {},
            publisher=self._name,
        )

    def subscribe_event(
        self,
        event_pattern: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """订阅事件

        Args:
            event_pattern: 事件名称或通配符模式
            handler: 事件处理回调函数
        """
        if self._event_bus is None:
            self._logger.warning(
                "事件总线未注入，无法订阅事件: %s",
                event_pattern,
            )
            return

        self._event_bus.subscribe(
            event_pattern,
            handler,
            subscriber_name=self._name,
        )

    def get_plugin(self, plugin_name: str) -> Optional["BasePlugin"]:
        """获取其他插件的引用

        通过 PluginManager 获取其他已加载的插件实例。
        注意：应优先使用事件总线通信，
        仅在必要时才直接引用其他插件。

        Args:
            plugin_name: 目标插件名称

        Returns:
            目标插件实例，未找到返回 None
        """
        if self._plugin_manager is None:
            self._logger.warning(
                "PluginManager 未注入，无法获取插件: %s",
                plugin_name,
            )
            return None

        return self._plugin_manager.get_plugin(plugin_name)

    def get_config_value(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """获取配置值

        支持点号分隔的嵌套键，如 "database.host"。

        Args:
            key: 配置键名（支持点号分隔）
            default: 默认值

        Returns:
            配置值，不存在时返回默认值
        """
        keys = key.split(".")
        value: Any = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    # ---- 内部方法（由 PluginManager 调用） ----

    def _set_event_bus(self, event_bus: Any) -> None:
        """注入事件总线引用

        Args:
            event_bus: EventBus 实例
        """
        self._event_bus = event_bus

    def _set_plugin_manager(self, manager: Any) -> None:
        """注入 PluginManager 引用

        Args:
            manager: PluginManager 实例
        """
        self._plugin_manager = manager

    def _set_plugin_info(self, info: PluginInfo) -> None:
        """设置插件运行时信息

        Args:
            info: PluginInfo 实例
        """
        self._plugin_info = info

    def _set_state(self, state: PluginState) -> None:
        """设置插件状态

        Args:
            state: 新的插件状态
        """
        old_state = self._state
        self._state = state
        self._logger.debug(
            "状态变更: %s → %s",
            old_state.value,
            state.value,
        )

    def _set_error(self, error_message: str) -> None:
        """设置错误状态

        Args:
            error_message: 错误描述信息
        """
        self._state = PluginState.ERROR
        self._error_message = error_message
        self._logger.error("进入错误状态: %s", error_message)

    def _do_load(self) -> None:
        """执行加载流程（由 PluginManager 调用）

        包含状态转换和计时逻辑。

        Raises:
            PluginError: 加载失败
        """
        self._set_state(PluginState.LOADING)
        start_time = time.time()

        try:
            self.on_load()
            self._load_time = time.time() - start_time
            self._set_state(PluginState.ACTIVE)
            self._logger.info(
                "加载完成 (耗时 %.3fs)", self._load_time
            )
        except Exception as e:
            self._load_time = time.time() - start_time
            self._set_error(str(e))
            raise PluginError(
                f"加载失败: {e}", plugin_name=self._name
            ) from e

    def _do_unload(self) -> None:
        """执行卸载流程（由 PluginManager 调用）"""
        self._set_state(PluginState.UNLOADING)

        try:
            # 取消所有事件订阅
            if self._event_bus is not None:
                self._event_bus.unsubscribe_all(self._name)

            self.on_unload()
            self._set_state(PluginState.UNLOADED)
            self._logger.info("卸载完成")
        except Exception as e:
            # 记录错误信息但直接设为 UNLOADED（而非先 ERROR 再 UNLOADED）
            self._error_message = f"卸载异常: {e}"
            self._logger.error(
                "卸载异常: %s", e, exc_info=True
            )
            self._set_state(PluginState.UNLOADED)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}"
            f"(name={self._name}, "
            f"state={self._state.value})>"
        )
