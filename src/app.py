"""威科夫全自动逻辑引擎 - 插件化系统入口

WyckoffApp 是整个系统的顶层入口，负责：
1. 初始化内核组件（EventBus、ConfigSystem、PluginManager）
2. 发现并加载所有插件
3. 启动交易循环
4. 优雅关闭和资源清理

Usage::

    app = WyckoffApp(config_path="config.yaml")
    await app.start()
    # ... 运行中 ...
    await app.stop()
"""

import asyncio
import logging
import signal
import sys
from typing import Any, Dict, List, Optional

from src.kernel.config_system import ConfigSystem
from src.kernel.event_bus import EventBus
from src.kernel.plugin_manager import PluginManager
from src.kernel.types import PluginState

logger = logging.getLogger(__name__)


class WyckoffApp:
    """威科夫全自动逻辑引擎应用

    基于插件架构的交易系统入口。通过 PluginManager 管理
    所有功能模块的生命周期，实现模块间松耦合。

    Attributes:
        config_system: 配置管理系统
        event_bus: 事件总线
        plugin_manager: 插件管理器
        is_running: 系统是否正在运行

    Example::

        app = WyckoffApp("config.yaml")
        await app.start()
    """

    def __init__(
        self,
        config_path: str = "config.yaml",
        plugins_dir: str = "src/plugins",
    ) -> None:
        """初始化应用

        Args:
            config_path: 配置文件路径
            plugins_dir: 插件目录路径
        """
        self._config_path = config_path
        self._plugins_dir = plugins_dir
        self._is_running = False
        self._stop_event: Optional[asyncio.Event] = None

        # 初始化内核组件
        self.config_system = ConfigSystem()
        self.event_bus = EventBus()
        self.plugin_manager = PluginManager(
            plugins_dir=plugins_dir,
            config_system=self.config_system,
            event_bus=self.event_bus,
        )

        # 加载配置
        self.config_system.load(config_path)
        logger.info(
            "WyckoffApp 初始化完成, config=%s, plugins_dir=%s",
            config_path,
            plugins_dir,
        )

    @property
    def is_running(self) -> bool:
        """系统是否正在运行"""
        return self._is_running

    def discover_and_load(self) -> Dict[str, bool]:
        """发现并加载所有插件

        Returns:
            加载结果字典: plugin_name -> success
        """
        # 发现插件
        discovered = self.plugin_manager.discover_plugins()
        logger.info("发现 %d 个插件: %s", len(discovered), discovered)

        # 加载所有插件
        results = self.plugin_manager.load_all()

        loaded = [n for n, ok in results.items() if ok]
        failed = [n for n, ok in results.items() if not ok]

        if loaded:
            logger.info("成功加载 %d 个插件: %s", len(loaded), loaded)
        if failed:
            logger.warning("加载失败 %d 个插件: %s", len(failed), failed)

        # 发布系统就绪事件
        self.event_bus.emit(
            "system.ready",
            {
                "loaded_plugins": loaded,
                "failed_plugins": failed,
            },
            publisher="app",
        )

        return results

    async def start(self) -> None:
        """启动系统

        执行以下步骤：
        1. 发现并加载所有插件
        2. 获取 orchestrator 插件
        3. 启动交易循环
        """
        if self._is_running:
            logger.warning("系统已在运行中")
            return

        logger.info("=" * 60)
        logger.info("威科夫全自动逻辑引擎 启动中...")
        logger.info("=" * 60)

        # 发现并加载插件
        results = self.discover_and_load()

        # 检查核心插件是否加载成功
        core_plugins = [
            "market_regime",
            "data_pipeline",
            "orchestrator",
        ]
        for name in core_plugins:
            if not results.get(name, False):
                logger.error(
                    "核心插件 %s 加载失败，系统无法启动", name
                )
                raise RuntimeError(
                    f"核心插件 {name} 加载失败"
                )

        self._is_running = True
        self._stop_event = asyncio.Event()

        # 发布系统启动事件
        self.event_bus.emit(
            "system.started",
            {"plugins": list(results.keys())},
            publisher="app",
        )

        logger.info("系统启动完成，所有核心插件已就绪")

    async def run_loop(self) -> None:
        """运行主循环

        获取 orchestrator 插件并调用其交易循环。
        如果 orchestrator 插件提供了 run_loop 方法，
        则委托给它；否则使用简单的等待循环。
        """
        if not self._is_running:
            await self.start()

        orchestrator = self.plugin_manager.get_plugin("orchestrator")
        if orchestrator is None:
            logger.error("orchestrator 插件未加载")
            return

        if hasattr(orchestrator, "run_loop"):
            logger.info("委托交易循环给 OrchestratorPlugin")
            try:
                await orchestrator.run_loop()
            except asyncio.CancelledError:
                logger.info("交易循环被取消")
        elif self._stop_event:
            logger.info("进入等待模式（orchestrator 无 run_loop 实现）")
            await self._stop_event.wait()

    async def stop(self) -> None:
        """停止系统

        优雅关闭所有插件并清理资源。
        """
        if not self._is_running:
            return

        logger.info("系统正在关闭...")

        # 通知 orchestrator 停止
        orchestrator = self.plugin_manager.get_plugin("orchestrator")
        if orchestrator:
            try:
                if hasattr(orchestrator, "request_stop"):
                    orchestrator.request_stop()
                    logger.info("已通过 request_stop() 通知 orchestrator 停止")
                elif hasattr(orchestrator, "stop_system"):
                    import asyncio

                    if asyncio.iscoroutinefunction(orchestrator.stop_system):
                        await orchestrator.stop_system()
                    else:
                        orchestrator.stop_system()
                    logger.info("已通过 stop_system() 通知 orchestrator 停止")
                else:
                    # 回退：通过事件总线发出停止事件
                    self.event_bus.emit(
                        "system.shutdown_requested",
                        {},
                        publisher="app",
                    )
                    logger.info("已通过事件总线发出 shutdown_requested 事件")
            except Exception as e:
                logger.error("停止 orchestrator 异常: %s", e)

        # 发布系统关闭事件
        self.event_bus.emit(
            "system.stopping",
            {},
            publisher="app",
        )

        # 卸载所有插件
        self.plugin_manager.unload_all()

        self._is_running = False
        if self._stop_event:
            self._stop_event.set()

        logger.info("系统已完全关闭")

    def get_status(self) -> Dict[str, Any]:
        """获取系统状态

        Returns:
            包含系统运行状态的字典
        """
        plugin_statuses: Dict[str, str] = {}
        for name, info in self.plugin_manager._plugin_infos.items():
            plugin_statuses[name] = info.state.value

        return {
            "is_running": self._is_running,
            "config_path": self._config_path,
            "plugins_dir": self._plugins_dir,
            "plugin_count": len(plugin_statuses),
            "plugins": plugin_statuses,
        }
