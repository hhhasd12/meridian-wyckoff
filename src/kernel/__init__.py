"""威科夫全自动逻辑引擎 - 插件内核

内核层是系统的不可插拔核心，提供：
- PluginManager: 插件生命周期管理（发现、加载、卸载、重载）
- BasePlugin: 插件抽象基类，定义标准生命周期接口
- PluginManifest: 插件清单解析与验证
- EventBus: 事件总线，替代硬编码的模块间依赖
- ConfigSystem: 统一配置管理，支持插件级配置隔离
- 共享类型定义（PluginState, PluginType 等）

设计原则：
1. 内核层零业务逻辑 — 只负责插件编排
2. 错误隔离 — 单个插件崩溃不影响其他插件
3. 声明式依赖 — 通过 plugin-manifest.yaml 声明依赖关系
4. 事件驱动 — 插件间通过 EventBus 通信，不直接 import

参考架构：VCP Plugin System (e:/VCP/Plugin.js)
"""

from src.kernel.types import (
    PluginState,
    PluginType,
    SystemMode,
    TradingSignal,
    WyckoffSignal,
    DecisionContext,
    TradingDecision,
    StateDirection,
    StateTransitionType,
    StateEvidence,
    StateDetectionResult,
    StateTransition,
    StatePath,
    StateConfig,
    MutationType,
)
from src.kernel.event_bus import EventBus
from src.kernel.plugin_manifest import PluginManifest
from src.kernel.base_plugin import BasePlugin
from src.kernel.config_system import ConfigSystem
from src.kernel.plugin_manager import PluginManager

__all__ = [
    "PluginState",
    "PluginType",
    "SystemMode",
    "TradingSignal",
    "WyckoffSignal",
    "DecisionContext",
    "TradingDecision",
    "StateDirection",
    "StateTransitionType",
    "StateEvidence",
    "StateDetectionResult",
    "StateTransition",
    "StatePath",
    "StateConfig",
    "MutationType",
    "EventBus",
    "PluginManifest",
    "BasePlugin",
    "ConfigSystem",
    "PluginManager",
]

__version__ = "1.0.0"
