from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable
from fastapi import APIRouter


class BackendPlugin(ABC):
    """所有后端插件的基类"""
    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    dependencies: tuple = ()  # 用tuple避免可变默认值

    @abstractmethod
    async def on_init(self, ctx: PluginContext) -> None:
        """初始化：接收上下文，准备资源"""
        ...

    @abstractmethod
    async def on_start(self) -> None:
        """启动：所有插件注册完毕后调用"""
        ...

    @abstractmethod
    async def on_stop(self) -> None:
        """停止：清理资源"""
        ...

    async def on_health_check(self) -> dict:
        """健康检查，默认返回ok"""
        return {"status": "ok"}

    def get_router(self) -> APIRouter | None:
        """返回API路由，自动挂载到/api/{plugin_id}/"""
        return None

    def get_subscriptions(self) -> dict[str, Callable]:
        """声明事件订阅 {事件名: 处理函数}"""
        return {}


@dataclass
class PluginContext:
    """注入给每个插件的上下文"""
    event_bus: Any
    storage: Any
    config: dict = field(default_factory=dict)
    get_plugin: Callable = lambda pid: None
