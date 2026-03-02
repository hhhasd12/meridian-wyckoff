"""
系统协调器包

包含系统协调器模块，支持统一调度所有模块，形成完整的交易决策系统。

模块结构：
- config.py: 枚举和数据类定义
- core.py: 核心协调器类 (SystemOrchestrator)
- registry.py: 模块注册表 (ModuleRegistry)
- flow.py: 流程控制 (DataPipeline, DecisionPipeline)
- health.py: 健康检查 (HealthChecker)

导出类：
- SystemOrchestrator: 核心系统协调器
- SystemMode: 系统运行模式枚举
- TradingSignal: 交易信号枚举
- WyckoffSignal: 威科夫信号枚举
- DecisionContext: 决策上下文数据类
- TradingDecision: 交易决策数据类
- ModuleRegistry: 模块注册表
- DataPipeline: 数据处理流水线
- DecisionPipeline: 决策流水线
- HealthChecker: 健康检查器
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 直接从原始文件导入（避免循环导入）
# 保持向后兼容性 - 原始文件已重命名为 _legacy.py
from src.core.system_orchestrator_legacy import SystemOrchestrator

# 从各模块导入
from .config import (
    DecisionContext,
    SystemMode,
    TradingDecision,
    TradingSignal,
    WyckoffSignal,
)
from .flow import (
    DataFlowPipeline,
    DataPipeline,   # 向后兼容别名，指向 DataFlowPipeline
    DecisionPipeline,
)
from .health import (
    AlertLevel,
    HealthChecker,
    HealthStatus,
)
from .registry import ModuleRegistry

__all__ = [
    "AlertLevel",
    # 流程控制
    "DataFlowPipeline",
    "DataPipeline",      # 向后兼容别名
    "DecisionContext",
    "DecisionPipeline",
    # 健康检查
    "HealthChecker",
    "HealthStatus",
    # 注册表
    "ModuleRegistry",
    # 配置类
    "SystemMode",
    # 核心类
    "SystemOrchestrator",
    "TradingDecision",
    "TradingSignal",
    "WyckoffSignal",
]
