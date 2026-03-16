"""仓位管理插件 - 核心类型定义"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from src.kernel.types import TradingSignal


class PositionSide(Enum):
    """持仓方向"""
    LONG = "long"
    SHORT = "short"


class PositionStatus(Enum):
    """持仓状态"""
    OPEN = "open"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


class ExitReason(Enum):
    """出场原因"""
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    SIGNAL_REVERSAL = "signal_reversal"
    TRAILING_STOP = "trailing_stop"
    TIMEOUT = "timeout"
    MANUAL = "manual"
    LIQUIDATION = "liquidation"
    PARTIAL_PROFIT = "partial_profit"


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    signal_confidence: float
    wyckoff_state: str
    entry_signal: TradingSignal
    status: PositionStatus = PositionStatus.OPEN
    trailing_stop_activated: bool = False
    partial_profits_taken: List[float] = field(default_factory=list)
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price == float('inf'):
            self.lowest_price = self.entry_price

    def update_price_extremes(self, current_price: float) -> None:
        if current_price > self.highest_price:
            self.highest_price = current_price
        if current_price < self.lowest_price:
            self.lowest_price = current_price

    def calculate_unrealized_pnl(self, current_price: float) -> tuple[float, float]:
        if self.side == PositionSide.LONG:
            pnl = (current_price - self.entry_price) * self.size
            pnl_pct = (current_price - self.entry_price) / self.entry_price
        else:
            pnl = (self.entry_price - current_price) * self.size
            pnl_pct = (self.entry_price - current_price) / self.entry_price
        
        self.unrealized_pnl = pnl
        self.unrealized_pnl_pct = pnl_pct
        return pnl, pnl_pct

    def get_risk_amount(self) -> float:
        if self.side == PositionSide.LONG:
            return abs(self.entry_price - self.stop_loss) * self.size
        else:
            return abs(self.stop_loss - self.entry_price) * self.size

    def get_reward_amount(self) -> float:
        if self.side == PositionSide.LONG:
            return abs(self.take_profit - self.entry_price) * self.size
        else:
            return abs(self.entry_price - self.take_profit) * self.size

    def get_risk_reward_ratio(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "size": self.size,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat(),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "signal_confidence": self.signal_confidence,
            "wyckoff_state": self.wyckoff_state,
            "entry_signal": self.entry_signal.value,
            "status": self.status.value,
            "trailing_stop_activated": self.trailing_stop_activated,
            "partial_profits_taken": self.partial_profits_taken,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "risk_reward_ratio": self.get_risk_reward_ratio(),
            "metadata": self.metadata,
        }


@dataclass
class TradeResult:
    """交易结果"""
    symbol: str
    side: PositionSide
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    hold_duration: timedelta
    exit_reason: ExitReason
    entry_signal: TradingSignal
    entry_confidence: float
    entry_wyckoff_state: str
    entry_time: datetime
    exit_time: datetime
    stop_loss: float
    take_profit: float
    highest_price: float
    lowest_price: float
    trailing_activated: bool
    partial_profits: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_profitable(self) -> bool:
        return self.pnl > 0

    @property
    def risk_reward_actual(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        if risk == 0:
            return 0.0
        return abs(self.exit_price - self.entry_price) / risk

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "hold_duration_seconds": self.hold_duration.total_seconds(),
            "exit_reason": self.exit_reason.value,
            "entry_signal": self.entry_signal.value,
            "entry_confidence": self.entry_confidence,
            "entry_wyckoff_state": self.entry_wyckoff_state,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
            "trailing_activated": self.trailing_activated,
            "partial_profits": self.partial_profits,
            "is_profitable": self.is_profitable,
            "risk_reward_actual": self.risk_reward_actual,
            "metadata": self.metadata,
        }


@dataclass
class ExitCheckResult:
    """出场检查结果"""
    should_exit: bool
    reason: Optional[ExitReason] = None
    new_stop_loss: Optional[float] = None
    partial_close_ratio: Optional[float] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_exit": self.should_exit,
            "reason": self.reason.value if self.reason else None,
            "new_stop_loss": self.new_stop_loss,
            "partial_close_ratio": self.partial_close_ratio,
            "message": self.message,
        }
