"""仓位管理器 - 管理所有持仓的生命周期"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.types import TradingSignal
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

logger = logging.getLogger(__name__)


class PositionManager:
    """仓位管理器

    功能：
    1. 开仓/平仓管理
    2. 止损止盈跟踪
    3. 信号反转出场
    4. 交易记录管理
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeResult] = []

        self.stop_loss_executor = StopLossExecutor(config.get("stop_loss", {}))
        self.signal_exit_logic = SignalExitLogic(config.get("signal_exit", {}))

        self._max_positions = config.get("max_positions", 3)
        self._max_position_size = config.get("max_position_size", 0.1)
        self._min_position_size = config.get("min_position_size", 0.01)
        self._risk_per_trade = config.get("risk_per_trade", 0.02)

    def can_open_position(self, symbol: str) -> bool:
        """检查是否可以开仓"""
        if symbol in self.positions:
            return False
        if len(self.positions) >= self._max_positions:
            return False
        return True

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
    ) -> float:
        """计算仓位大小

        Args:
            account_balance: 账户余额
            entry_price: 入场价格
            stop_loss: 止损价格

        Returns:
            仓位大小（合约数量）
        """
        risk_amount = account_balance * self._risk_per_trade
        price_risk = abs(entry_price - stop_loss)

        if price_risk == 0:
            return 0.0

        position_size = risk_amount / price_risk

        max_size_by_balance = account_balance * self._max_position_size / entry_price
        min_size_by_balance = account_balance * self._min_position_size / entry_price

        position_size = min(position_size, max_size_by_balance)

        if position_size < min_size_by_balance:
            logger.warning(
                f"Position size {position_size} below minimum {min_size_by_balance}"
            )
            return 0.0

        return position_size

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        size: float,
        entry_price: float,
        signal_confidence: float,
        wyckoff_state: str,
        entry_signal: TradingSignal,
        df: pd.DataFrame,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Position]:
        """开仓

        Args:
            symbol: 交易品种
            side: 持仓方向
            size: 仓位大小
            entry_price: 入场价格
            signal_confidence: 信号置信度
            wyckoff_state: 威科夫状态
            entry_signal: 入场信号
            df: K线数据（用于计算止损止盈）
            metadata: 额外元数据

        Returns:
            Position: 创建的持仓，失败返回None
        """
        if not self.can_open_position(symbol):
            logger.warning(f"Cannot open position for {symbol}")
            return None

        stop_loss = self.stop_loss_executor.calculate_stop_loss(
            entry_price=entry_price,
            side=side,
            df=df,
        )

        take_profit = self.stop_loss_executor.calculate_take_profit(
            entry_price=entry_price,
            stop_loss=stop_loss,
            side=side,
        )

        # PM-C3: 计算入场ATR供trailing stop使用
        entry_atr = self.stop_loss_executor._calculate_atr(df) if len(df) >= 14 else 0.0

        position = Position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_confidence=signal_confidence,
            wyckoff_state=wyckoff_state,
            entry_signal=entry_signal,
            entry_atr=entry_atr,
            metadata=metadata or {},
        )

        self.positions[symbol] = position

        logger.info(
            f"Position opened: {symbol} {side.value} "
            f"size={size:.4f} entry={entry_price:.2f} "
            f"SL={stop_loss:.2f} TP={take_profit:.2f}"
        )

        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: ExitReason,
        partial_ratio: Optional[float] = None,
    ) -> Optional[TradeResult]:
        """平仓

        Args:
            symbol: 交易品种
            exit_price: 出场价格
            reason: 出场原因
            partial_ratio: 部分平仓比例（None表示全部平仓）

        Returns:
            TradeResult: 交易结果
        """
        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol}")
            return None

        position = self.positions[symbol]
        exit_time = datetime.now()

        if partial_ratio and 0 < partial_ratio < 1:
            close_size = position.original_size * partial_ratio  # 基于原始仓位计算
            # 确保不超过剩余仓位
            close_size = min(close_size, position.size)
            remaining_size = position.size - close_size

            pnl = self._calculate_pnl(
                position.side, position.entry_price, exit_price, close_size
            )
            pnl_pct = self._calculate_pnl_pct(
                position.side, position.entry_price, exit_price
            )

            trade_result = TradeResult(
                symbol=symbol,
                side=position.side,
                entry_price=position.entry_price,
                exit_price=exit_price,
                size=close_size,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_duration=exit_time - position.entry_time,
                exit_reason=reason,
                entry_signal=position.entry_signal,
                entry_confidence=position.signal_confidence,
                entry_wyckoff_state=position.wyckoff_state,
                entry_time=position.entry_time,
                exit_time=exit_time,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                highest_price=position.highest_price,
                lowest_price=position.lowest_price,
                trailing_activated=position.trailing_stop_activated,
                partial_profits=position.partial_profits_taken.copy(),
            )

            position.size = remaining_size

            logger.info(
                f"Partial close: {symbol} {position.side.value} "
                f"closed={partial_ratio * 100:.0f}% pnl={pnl:.2f} ({pnl_pct * 100:.2f}%)"
            )
        else:
            pnl = self._calculate_pnl(
                position.side, position.entry_price, exit_price, position.size
            )
            pnl_pct = self._calculate_pnl_pct(
                position.side, position.entry_price, exit_price
            )

            trade_result = TradeResult(
                symbol=symbol,
                side=position.side,
                entry_price=position.entry_price,
                exit_price=exit_price,
                size=position.size,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_duration=exit_time - position.entry_time,
                exit_reason=reason,
                entry_signal=position.entry_signal,
                entry_confidence=position.signal_confidence,
                entry_wyckoff_state=position.wyckoff_state,
                entry_time=position.entry_time,
                exit_time=exit_time,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                highest_price=position.highest_price,
                lowest_price=position.lowest_price,
                trailing_activated=position.trailing_stop_activated,
                partial_profits=position.partial_profits_taken.copy(),
            )

            position.status = PositionStatus.CLOSED
            del self.positions[symbol]

            logger.info(
                f"Position closed: {symbol} {position.side.value} "
                f"pnl={pnl:.2f} ({pnl_pct * 100:.2f}%) reason={reason.value}"
            )

        self.trade_history.append(trade_result)

        return trade_result

    def update_position(
        self,
        symbol: str,
        current_price: float,
        new_signal: Optional[TradingSignal] = None,
        new_wyckoff_state: Optional[str] = None,
        signal_confidence: float = 0.0,
    ) -> Optional[ExitCheckResult]:
        """更新持仓状态并检查出场条件

        Args:
            symbol: 交易品种
            current_price: 当前价格
            new_signal: 新的交易信号
            new_wyckoff_state: 新的威科夫状态
            signal_confidence: 信号置信度

        Returns:
            ExitCheckResult: 出场检查结果
        """
        if symbol not in self.positions:
            return None

        position = self.positions[symbol]

        exit_result = self.stop_loss_executor.check_exit_conditions(
            position, current_price
        )

        if exit_result.should_exit:
            return exit_result

        if exit_result.new_stop_loss:
            position.stop_loss = exit_result.new_stop_loss
            logger.info(f"Stop loss updated for {symbol}: {exit_result.new_stop_loss}")

        if new_signal and new_wyckoff_state:
            signal_exit = self.signal_exit_logic.should_exit_on_signal(
                position, new_signal, new_wyckoff_state, signal_confidence
            )
            if signal_exit.should_exit:
                return signal_exit

        timeout_exit = self.signal_exit_logic.check_timeout_exit(
            position, datetime.now()
        )
        if timeout_exit.should_exit:
            return timeout_exit

        if exit_result.partial_close_ratio:
            return exit_result

        return ExitCheckResult(should_exit=False)

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定品种的持仓"""
        return self.positions.get(symbol)

    def get_all_positions(self) -> Dict[str, Position]:
        """获取所有持仓"""
        return self.positions.copy()

    def get_open_position_count(self) -> int:
        """获取当前持仓数量"""
        return len(self.positions)

    def get_trade_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[TradeResult]:
        """获取交易历史"""
        history = self.trade_history
        if symbol:
            history = [t for t in history if t.symbol == symbol]
        return history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """获取交易统计"""
        if not self.trade_history:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
            }

        wins = [t for t in self.trade_history if t.is_profitable]
        losses = [t for t in self.trade_history if not t.is_profitable]

        total_pnl = sum(t.pnl for t in self.trade_history)
        avg_pnl = total_pnl / len(self.trade_history)
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0

        return {
            "total_trades": len(self.trade_history),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(self.trade_history),
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses))
            if losses and sum(t.pnl for t in losses) != 0
            else float("inf"),
        }

    def _calculate_pnl(
        self,
        side: PositionSide,
        entry_price: float,
        exit_price: float,
        size: float,
    ) -> float:
        """计算盈亏"""
        if side == PositionSide.LONG:
            return (exit_price - entry_price) * size
        else:
            return (entry_price - exit_price) * size

    def _calculate_pnl_pct(
        self,
        side: PositionSide,
        entry_price: float,
        exit_price: float,
    ) -> float:
        """计算盈亏百分比"""
        if side == PositionSide.LONG:
            return (exit_price - entry_price) / entry_price
        else:
            return (entry_price - exit_price) / entry_price

    def force_close_all(self, exit_prices: Dict[str, float]) -> List[TradeResult]:
        """强制平仓所有持仓

        Args:
            exit_prices: 各品种的出场价格

        Returns:
            List[TradeResult]: 所有交易结果
        """
        results = []
        for symbol, position in list(self.positions.items()):
            exit_price = exit_prices.get(symbol)
            if exit_price is None:
                # PM-H1修复：强制平仓必须用市场价，不能用入场价（零PnL假象）
                logger.error(f"force_close_all: 未提供{symbol}的市场价，跳过平仓")
                continue
            result = self.close_position(
                symbol=symbol,
                exit_price=exit_price,
                reason=ExitReason.MANUAL,
            )
            if result:
                results.append(result)
        return results
