"""
Agent Teams 模块
实现多智能体协作系统，分为代码团队、量化团队、协调团队
"""

# 基础类
from .base_agent import BaseAgent, AgentState, AgentCapability, TaskResult
from .message import AgentMessage, MessageType, Priority

# 代码团队
from .code_diagnostic_agent import CodeDiagnosticAgent
from .code_fixer_agent import CodeFixerAgent
from .code_reviewer_agent import CodeReviewerAgent

# 量化团队
from .strategy_optimizer_agent import StrategyOptimizerAgent
from .backtest_validator_agent import BacktestValidatorAgent

# 协调团队（使用原有的）
from .orchestrator import OrchestratorAgent
from .human_agent import HumanAgent
from .report_agent import ReportAgent

# 向后兼容别名（旧名称 → 新名称）
DiagnosticAgent = CodeDiagnosticAgent
CodeAgent = CodeFixerAgent

__all__ = [
    # 基础类
    "BaseAgent",
    "AgentState",
    "AgentCapability",
    "TaskResult",
    "AgentMessage",
    "MessageType",
    "Priority",
    # 代码团队
    "CodeDiagnosticAgent",
    "CodeFixerAgent",
    "CodeReviewerAgent",
    # 量化团队
    "StrategyOptimizerAgent",
    "BacktestValidatorAgent",
    # 协调团队
    "OrchestratorAgent",
    "HumanAgent",
    "ReportAgent",
]

# Agent团队配置
AGENT_TEAMS = {
    "code": {
        "name": "代码团队",
        "description": "负责代码诊断、修复、审查",
        "color": "#4CAF50",
        "agents": [
            {
                "id": "code_diagnostic",
                "class": "CodeDiagnosticAgent",
                "name": "代码诊断器",
                "description": "诊断代码问题",
                "icon": "🔍",
            },
            {
                "id": "code_fixer",
                "class": "CodeFixerAgent",
                "name": "代码修复器",
                "description": "修复代码bug",
                "icon": "🔧",
            },
            {
                "id": "code_reviewer",
                "class": "CodeReviewerAgent",
                "name": "代码审查器",
                "description": "审查代码质量",
                "icon": "�",
            },
        ],
    },
    "quant": {
        "name": "量化团队",
        "description": "负责策略优化、回测验证、风险评估",
        "color": "#2196F3",
        "agents": [
            {
                "id": "strategy_optimizer",
                "class": "StrategyOptimizerAgent",
                "name": "策略优化器",
                "description": "优化交易策略",
                "icon": "📊",
            },
            {
                "id": "backtest_validator",
                "class": "BacktestValidatorAgent",
                "name": "回测验证器",
                "description": "验证策略效果",
                "icon": "📈",
            },
        ],
    },
    "coordination": {
        "name": "协调团队",
        "description": "负责团队协调、报告生成、人工确认",
        "color": "#FF9800",
        "agents": [
            {
                "id": "orchestrator",
                "class": "OrchestratorAgent",
                "name": "协调器",
                "description": "协调团队工作",
                "icon": "🎯",
            },
            {
                "id": "reporter",
                "class": "ReportAgent",
                "name": "报告器",
                "description": "生成报告",
                "icon": "�",
            },
            {
                "id": "human_interface",
                "class": "HumanAgent",
                "name": "人工接口",
                "description": "人工确认",
                "icon": "👤",
            },
        ],
    },
}
