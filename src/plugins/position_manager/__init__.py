"""仓位管理插件"""

from src.plugins.position_manager.position_manager import PositionManager
from src.plugins.position_manager.signal_exit_logic import SignalExitLogic
from src.plugins.position_manager.stop_loss_executor import StopLossExecutor
from src.plugins.position_manager.types import (
    ExitCheckResult,
    ExitReason,
    Position,
    PositionSide,
    PositionStatus,
    TradeResult,
)

__all__ = [
    "PositionManager",
    "StopLossExecutor",
    "SignalExitLogic",
    "Position",
    "PositionSide",
    "PositionStatus",
    "TradeResult",
    "ExitReason",
    "ExitCheckResult",
]
