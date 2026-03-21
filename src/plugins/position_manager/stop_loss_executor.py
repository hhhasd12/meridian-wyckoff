"""止损止盈执行器 - 已迁移到 risk_management

保留此文件作为兼容层，新代码请使用:
    from src.plugins.risk_management.stop_loss_executor import StopLossExecutor
"""

# 兼容导入：从新位置re-export
from src.plugins.risk_management.stop_loss_executor import StopLossExecutor  # noqa: F401

__all__ = ["StopLossExecutor"]
