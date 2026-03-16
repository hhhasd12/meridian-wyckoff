"""
系统协调器 - 模块注册表

负责模块的注册、初始化和依赖管理。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 支持依赖注入模式，解耦星型依赖
3. 详细的中文错误上下文记录
"""

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _setup_error_handler():
    """设置错误处理装饰器"""
    try:
        from src.utils.error_handler import error_handler

        return error_handler
    except ImportError:

        def error_handler_decorator(**kwargs):
            def decorator(func):
                return func

            return decorator

        return error_handler_decorator


error_handler = _setup_error_handler()


class ModuleRegistry:
    """
    模块注册表 - 管理所有系统模块的注册和初始化

    通过依赖注入模式解决星型依赖问题。
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        初始化模块注册表

        Args:
            config: 配置字典
        """
        self._config = config or {}
        self._modules: dict[str, Any] = {}
        self._module_initializers: dict[str, Callable] = {}
        self._module_dependencies: dict[str, list[str]] = {}

        logger.info("ModuleRegistry initialized")

    @error_handler(logger=logger, reraise=False)
    def register_module(
        self, name: str, module: Any, dependencies: Optional[list[str]] = None
    ) -> None:
        """
        注册模块

        Args:
            name: 模块名称
            module: 模块实例
            dependencies: 依赖的模块名称列表
        """
        self._modules[name] = module
        self._module_dependencies[name] = dependencies or []

        logger.info(f"Module registered: {name}")

    @error_handler(logger=logger, reraise=False)
    def register_initializer(self, name: str, initializer: Callable) -> None:
        """
        注册模块初始化器

        Args:
            name: 模块名称
            initializer: 初始化函数
        """
        self._module_initializers[name] = initializer
        logger.debug(f"Initializer registered for: {name}")

    @error_handler(logger=logger, reraise=False, default_return=None)
    def get_module(self, name: str) -> Optional[Any]:
        """
        获取已注册的模块

        Args:
            name: 模块名称

        Returns:
            模块实例，如果不存在则返回None
        """
        return self._modules.get(name)

    @error_handler(logger=logger, reraise=False)
    def initialize_module(self, name: str) -> bool:
        """
        初始化指定模块

        Args:
            name: 模块名称

        Returns:
            是否初始化成功
        """
        if name not in self._module_initializers:
            logger.warning(f"No initializer found for module: {name}")
            return False

        try:
            initializer = self._module_initializers[name]
            module = initializer()
            self._modules[name] = module
            logger.info(f"Module initialized: {name}")
            return True
        except Exception:
            logger.exception(f"Failed to initialize module {name}")
            return False

    @error_handler(logger=logger, reraise=False)
    def initialize_all_modules(self) -> dict[str, bool]:
        """
        初始化所有已注册初始化器的模块

        Returns:
            模块名称到初始化成功状态的字典
        """
        results = {}
        for name in self._module_initializers:
            results[name] = self.initialize_module(name)
        return results

    @error_handler(logger=logger, reraise=False, default_return=[])
    def get_dependencies(self, name: str) -> list[str]:
        """
        获取模块的依赖列表

        Args:
            name: 模块名称

        Returns:
            依赖的模块名称列表
        """
        return self._module_dependencies.get(name, [])

    @error_handler(logger=logger, reraise=False)
    def check_dependencies(self, name: str) -> bool:
        """
        检查模块的依赖是否都已满足

        Args:
            name: 模块名称

        Returns:
            是否所有依赖都已满足
        """
        deps = self.get_dependencies(name)
        for dep in deps:
            if dep not in self._modules:
                logger.warning(f"Dependency {dep} not satisfied for {name}")
                return False
        return True

    @error_handler(logger=logger, reraise=False, default_return={})
    def get_all_modules(self) -> dict[str, Any]:
        """
        获取所有已注册的模块

        Returns:
            模块名称到实例的字典
        """
        return self._modules.copy()

    @error_handler(logger=logger, reraise=False)
    def unregister_module(self, name: str) -> None:
        """
        注销模块

        Args:
            name: 模块名称
        """
        if name in self._modules:
            del self._modules[name]
            logger.info(f"Module unregistered: {name}")

        if name in self._module_initializers:
            del self._module_initializers[name]

        if name in self._module_dependencies:
            del self._module_dependencies[name]


# 导出
__all__ = ["ModuleRegistry"]
