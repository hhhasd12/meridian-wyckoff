"""
回测引擎模块

提供高性能的 BacktestEngine，支持加载历史数据并驱动威科夫状态机进行模拟交易。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 高性能向量化回测
3. 详细交易记录
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

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


@dataclass
class Trade:
    """交易记录"""

    timestamp: datetime
    direction: str  # "BUY" or "SELL"
    price: float
    quantity: float
    commission: float = 0.0
    pnl: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    """回测结果"""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)


class BacktestEngine:
    """
    回测引擎

    功能：
    1. 加载历史数据
    2. 驱动威科夫状态机
    3. 模拟交易执行
    4. 性能统计
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
    ):
        """
        初始化回测引擎

        Args:
            initial_capital: 初始资金
            commission_rate: 手续费率
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.capital = initial_capital
        self.position = 0.0
        self.trades: list[Trade] = []
        self.equity_curve: list[float] = []
        self.timestamps: list[datetime] = []

        logger.debug(f"BacktestEngine initialized: capital={initial_capital}")

    @error_handler(logger=logger, reraise=True, default_return=BacktestResult())
    def run(
        self,
        data: pd.DataFrame,
        state_machine: Any,
        signals: list[dict[str, Any]],
    ) -> BacktestResult:
        """
        运行回测

        Args:
            data: OHLCV 数据
            state_machine: 威科夫状态机实例
            signals: 交易信号列表

        Returns:
            回测结果
        """
        logger.debug(f"Starting backtest with {len(data)} bars")

        # 重置状态
        self.capital = self.initial_capital
        self.position = 0.0
        self.trades = []
        self.equity_curve = []
        self.timestamps = []

        # 遍历数据
        # 用指针逐步消耗信号，避免重复触发同一信号
        signal_index = 0

        def _to_naive(t):
            """将任意时间戳统一转为 naive datetime，避免 tz-aware 与 naive 比较报错"""
            if t is None:
                return datetime.min
            if hasattr(t, "to_pydatetime"):
                t = t.to_pydatetime()
            if hasattr(t, "tzinfo") and t.tzinfo is not None:
                t = t.replace(tzinfo=None)
            return t

        sorted_signals = sorted(signals, key=lambda x: _to_naive(x.get("timestamp")))

        for i, (idx, row) in enumerate(data.iterrows()):
            current_price = row["close"]
            current_time = _to_naive(idx)

            # 推进指针到当前时间点的信号
            signal = None
            while signal_index < len(sorted_signals):
                sig = sorted_signals[signal_index]
                sig_time = _to_naive(sig.get("timestamp"))
                if sig_time and sig_time <= current_time:
                    signal = sig
                    signal_index += 1
                    break
                elif sig_time and sig_time > current_time:
                    break
                else:
                    signal_index += 1

            if signal:
                direction = signal.get("signal", "").upper()

                if direction == "BUY" and self.position == 0:
                    # 买入
                    quantity = (self.capital * 0.95) / current_price
                    commission = current_price * quantity * self.commission_rate

                    if self.capital >= current_price * quantity + commission:
                        self.position = quantity
                        self.capital -= current_price * quantity + commission

                        trade = Trade(
                            timestamp=current_time,
                            direction="BUY",
                            price=current_price,
                            quantity=quantity,
                            commission=commission,
                            reason=signal.get("reason", ""),
                        )
                        self.trades.append(trade)
                        logger.debug(f"BUY at {current_price}, qty={quantity}")

                elif direction == "SELL" and self.position > 0:
                    # 卖出
                    commission = current_price * self.position * self.commission_rate
                    pnl = (
                        current_price - self.trades[-1].price
                    ) * self.position - commission

                    self.capital += current_price * self.position - commission

                    trade = self.trades[-1]
                    trade.pnl = pnl

                    self.position = 0
                    logger.debug(f"SELL at {current_price}, PnL={pnl}")

            # 记录权益
            equity = self.capital + self.position * current_price
            self.equity_curve.append(equity)
            self.timestamps.append(current_time)

        # 计算统计
        result = self._calculate_statistics()

        logger.debug(
            f"Backtest complete: {result.total_trades} trades, win_rate={result.win_rate:.2%}"
        )

        return result

    def _get_signal_at_time(
        self,
        signals: list[dict[str, Any]],
        current_time: datetime,
    ) -> Optional[dict[str, Any]]:
        """获取当前时间的信号"""
        for signal in signals:
            signal_time = signal.get("timestamp")
            if signal_time and signal_time <= current_time:
                return signal
        return None

    def _calculate_statistics(self) -> BacktestResult:
        """计算统计指标"""
        if not self.trades:
            return BacktestResult()

        # 统计交易
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]

        total_trades = len(self.trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0

        # 计算收益
        total_pnl = sum(t.pnl for t in self.trades)

        # 计算最大回撤
        max_drawdown = self._calculate_max_drawdown()

        # 计算夏普比率
        sharpe_ratio = self._calculate_sharpe_ratio()

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            total_pnl=total_pnl,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=self.trades,
            equity_curve=self.equity_curve,
            timestamps=self.timestamps,
        )

    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if not self.equity_curve:
            return 0.0

        equity = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity)
        drawdown = (running_max - equity) / running_max

        return float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """计算夏普比率"""
        if len(self.equity_curve) < 2:
            return 0.0

        returns = np.diff(self.equity_curve) / self.equity_curve[:-1]

        if np.std(returns) == 0:
            return 0.0

        excess_returns = returns - risk_free_rate / 252
        sharpe = np.mean(excess_returns) / np.std(returns) * np.sqrt(252)

        return float(sharpe) if not np.isnan(sharpe) else 0.0


__all__ = ["BacktestEngine", "BacktestResult", "Trade"]
