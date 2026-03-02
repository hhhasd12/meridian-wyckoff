"""
回测包

提供高性能回测引擎和报告生成功能。

模块结构：
- engine.py: 回测引擎 (BacktestEngine)
- reporter.py: 报告生成器 (BacktestReporter)

导出：
- BacktestEngine: 回测引擎
- BacktestResult: 回测结果
- BacktestReporter: 报告生成器
"""

from .engine import BacktestEngine, BacktestResult, Trade
from .reporter import BacktestReporter

__all__ = [
    "BacktestEngine",
    "BacktestReporter",
    "BacktestResult",
    "Trade",
]
