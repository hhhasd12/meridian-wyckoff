"""
系统协调器 - 配置模块

包含所有枚举和数据类定义。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 详细的中文错误上下文记录
3. 支持依赖注入模式
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _setup_error_handler():
    """设置错误处理装饰器"""
    try:
        from src.utils.error_handler import error_handler

        return error_handler
    except ImportError:
        # 如果装饰器不可用，创建简单的装饰器
        def error_handler_decorator(**kwargs):
            def decorator(func):
                return func

            return decorator

        return error_handler_decorator


error_handler = _setup_error_handler()


class SystemMode(Enum):
    """系统运行模式"""

    BACKTEST = "backtest"  # 回测模式
    PAPER_TRADING = "paper"  # 模拟交易模式
    LIVE_TRADING = "live"  # 实盘交易模式
    EVOLUTION = "evolution"  # 进化模式（专注系统优化）


class TradingSignal(Enum):
    """交易信号枚举"""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    WAIT = "wait"  # 等待确认


class WyckoffSignal(Enum):
    """威科夫信号枚举"""

    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"
    NO_SIGNAL = "no_signal"


@error_handler(logger=logger, reraise=False, default_return=None)
def _convert_timestamp_to_iso(timestamp: Any) -> str:
    """
    将时间戳转换为ISO格式字符串

    Args:
        timestamp: 时间戳（可以是datetime、int64或numpy.integer）

    Returns:
        ISO格式字符串
    """
    if timestamp is None:
        return datetime.now().isoformat()

    if isinstance(timestamp, (int, np.integer)):
        timestamp_dt = datetime.fromtimestamp(float(timestamp) / 1000.0)
        return timestamp_dt.isoformat()
    if isinstance(timestamp, datetime):
        return timestamp.isoformat()
    return str(timestamp)


@dataclass
class DecisionContext:
    """
    决策上下文 - 包含当前分析的所有相关信息

    属性:
        timestamp: 时间戳
        market_regime: 市场体制
        regime_confidence: 体制置信度
        timeframe_weights: 时间框架权重
        detected_conflicts: 检测到的冲突
        wyckoff_state: 威科夫状态
        wyckoff_confidence: 威科夫置信度
        breakout_status: 突破状态
        fvg_signals: FVG信号列表
        anomaly_flags: 异常标志列表
        circuit_breaker_status: 熔断器状态
    """

    timestamp: datetime
    market_regime: str
    regime_confidence: float
    timeframe_weights: dict[str, float]
    detected_conflicts: list[dict[str, Any]]
    wyckoff_state: Optional[Any] = None
    wyckoff_confidence: float = 0.0
    breakout_status: Optional[dict[str, Any]] = None
    fvg_signals: list[dict[str, Any]] = field(default_factory=list)
    anomaly_flags: list[dict[str, Any]] = field(default_factory=list)
    circuit_breaker_status: Optional[dict[str, Any]] = None

    @error_handler(logger=logger, reraise=False, default_return={})
    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典

        Returns:
            包含所有属性的字典
        """
        return {
            "timestamp": _convert_timestamp_to_iso(self.timestamp),
            "market_regime": self.market_regime,
            "regime_confidence": self.regime_confidence,
            "timeframe_weights": self.timeframe_weights,
            "detected_conflicts": self.detected_conflicts,
            "wyckoff_state": str(self.wyckoff_state) if self.wyckoff_state else None,
            "wyckoff_confidence": self.wyckoff_confidence,
            "breakout_status": self.breakout_status,
            "fvg_signals": self.fvg_signals,
            "anomaly_flags": self.anomaly_flags,
            "circuit_breaker_status": self.circuit_breaker_status,
        }


@dataclass
class TradingDecision:
    """
    交易决策结果

    属性:
        signal: 交易信号
        confidence: 置信度
        context: 决策上下文
        entry_price: 入场价格
        stop_loss: 止损价格
        take_profit: 止盈价格
        position_size: 仓位大小
        reasoning: 推理过程
        timestamp: 时间戳
    """

    signal: TradingSignal
    confidence: float
    context: DecisionContext
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    reasoning: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @error_handler(logger=logger, reraise=False, default_return={})
    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典

        Returns:
            包含所有属性的字典
        """
        return {
            "signal": self.signal.value,
            "confidence": self.confidence,
            "context": self.context.to_dict(),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": self.position_size,
            "reasoning": self.reasoning,
            "timestamp": _convert_timestamp_to_iso(self.timestamp),
        }


# 导出所有类型
__all__ = [
    "DecisionContext",
    "SystemMode",
    "TradingDecision",
    "TradingSignal",
    "WyckoffSignal",
]
