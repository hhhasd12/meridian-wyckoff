"""WyckoffEngine 插件壳 — 插件系统集成"""

import logging
from typing import Any, Optional

from src.kernel.base_plugin import BasePlugin
from src.plugins.wyckoff_engine.engine import WyckoffEngine

logger = logging.getLogger(__name__)


class WyckoffEnginePlugin(BasePlugin):
    """统一信号引擎插件

    将 WyckoffEngine 包装为插件系统可管理的组件。
    """

    def __init__(self, name: str = "wyckoff_engine", **kwargs: Any) -> None:
        super().__init__(name=name, **kwargs)
        self.engine: Optional[WyckoffEngine] = None

    async def activate(self, context: dict[str, Any]) -> None:
        """激活插件，初始化引擎"""
        config = context.get("config", {}).get("wyckoff_engine", {})
        self.engine = WyckoffEngine(config)
        logger.info("WyckoffEngine plugin activated")

    async def deactivate(self) -> None:
        """停用插件"""
        self.engine = None
        logger.info("WyckoffEngine plugin deactivated")

    def on_load(self) -> None:
        """加载插件"""
        pass

    def on_unload(self) -> None:
        """卸载插件"""
        self.engine = None
