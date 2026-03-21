"""止损止盈执行器 - 计算和管理止损止盈"""

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.plugins.position_manager.types import (
    ExitCheckResult,
    ExitReason,
    Position,
    PositionSide,
)

logger = logging.getLogger(__name__)


class StopLossExecutor:
    """止损止盈执行器
    
    功能：
    1. 计算止损价格（ATR、固定比例、波动率）
    2. 计算止盈价格（风险回报比、固定比例）
    3. 管理跟踪止损
    4. 检查分批止盈
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.atr_period = config.get("atr_period", 14)
        
    def calculate_stop_loss(
        self,
        entry_price: float,
        side: PositionSide,
        df: pd.DataFrame,
        method: Optional[str] = None,
    ) -> float:
        """计算止损价格
        
        Args:
            entry_price: 入场价格
            side: 持仓方向
            df: K线数据（用于计算ATR）
            method: 止损方法（atr, fixed, volatility）
        
        Returns:
            止损价格
        """
        method = method or self.config.get("method", "atr")
        
        if method == "atr":
            atr = self._calculate_atr(df)
            multiplier = self.config.get("atr_multiplier", 1.5)
            if side == PositionSide.LONG:
                return entry_price - atr * multiplier
            else:
                return entry_price + atr * multiplier
                
        elif method == "fixed":
            pct = self.config.get("fixed_percentage", 0.02)
            if side == PositionSide.LONG:
                return entry_price * (1 - pct)
            else:
                return entry_price * (1 + pct)
                
        elif method == "volatility":
            volatility = self._calculate_volatility(df)
            multiplier = self.config.get("volatility_multiplier", 2.0)
            stop_distance = entry_price * volatility * multiplier
            if side == PositionSide.LONG:
                return entry_price - stop_distance
            else:
                return entry_price + stop_distance
        else:
            logger.warning(f"Unknown stop loss method: {method}, using fixed")
            pct = self.config.get("fixed_percentage", 0.02)
            if side == PositionSide.LONG:
                return entry_price * (1 - pct)
            else:
                return entry_price * (1 + pct)

    def calculate_take_profit(
        self,
        entry_price: float,
        stop_loss: float,
        side: PositionSide,
        method: Optional[str] = None,
    ) -> float:
        """计算止盈价格
        
        Args:
            entry_price: 入场价格
            stop_loss: 止损价格
            side: 持仓方向
            method: 止盈方法（risk_reward, fixed）
        
        Returns:
            止盈价格
        """
        method = method or self.config.get("take_profit_method", "risk_reward")
        
        if method == "risk_reward":
            risk = abs(entry_price - stop_loss)
            ratio = self.config.get("risk_reward_ratio", 2.0)
            if side == PositionSide.LONG:
                return entry_price + risk * ratio
            else:
                return entry_price - risk * ratio
                
        elif method == "fixed":
            pct = self.config.get("take_profit_percentage", 0.04)
            if side == PositionSide.LONG:
                return entry_price * (1 + pct)
            else:
                return entry_price * (1 - pct)
        else:
            logger.warning(f"Unknown take profit method: {method}, using risk_reward")
            risk = abs(entry_price - stop_loss)
            ratio = self.config.get("risk_reward_ratio", 2.0)
            if side == PositionSide.LONG:
                return entry_price + risk * ratio
            else:
                return entry_price - risk * ratio

    def check_exit_conditions(
        self,
        position: Position,
        current_price: float,
    ) -> ExitCheckResult:
        """检查出场条件
        
        Args:
            position: 持仓信息
            current_price: 当前价格
        
        Returns:
            ExitCheckResult: 出场检查结果
        """
        position.update_price_extremes(current_price)
        position.calculate_unrealized_pnl(current_price)
        
        if position.side == PositionSide.LONG:
            return self._check_long_exit(position, current_price)
        else:
            return self._check_short_exit(position, current_price)

    def _check_long_exit(
        self,
        position: Position,
        current_price: float,
    ) -> ExitCheckResult:
        """检查多头出场条件"""
        if current_price <= position.stop_loss:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.STOP_LOSS,
                message=f"Stop loss triggered: {current_price} <= {position.stop_loss}",
            )
        
        if current_price >= position.take_profit:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.TAKE_PROFIT,
                message=f"Take profit triggered: {current_price} >= {position.take_profit}",
            )
        
        trailing_result = self._check_trailing_stop_long(position, current_price)
        if trailing_result.should_exit:
            return trailing_result
        
        partial_result = self._check_partial_profit_long(position, current_price)
        if partial_result.should_exit or partial_result.partial_close_ratio:
            return partial_result
        
        new_stop = self._update_trailing_stop_long(position, current_price)
        if new_stop:
            return ExitCheckResult(
                should_exit=False,
                new_stop_loss=new_stop,
                message=f"Trailing stop updated to {new_stop}",
            )
        
        return ExitCheckResult(should_exit=False)

    def _check_short_exit(
        self,
        position: Position,
        current_price: float,
    ) -> ExitCheckResult:
        """检查空头出场条件"""
        if current_price >= position.stop_loss:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.STOP_LOSS,
                message=f"Stop loss triggered: {current_price} >= {position.stop_loss}",
            )
        
        if current_price <= position.take_profit:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.TAKE_PROFIT,
                message=f"Take profit triggered: {current_price} <= {position.take_profit}",
            )
        
        trailing_result = self._check_trailing_stop_short(position, current_price)
        if trailing_result.should_exit:
            return trailing_result
        
        partial_result = self._check_partial_profit_short(position, current_price)
        if partial_result.should_exit or partial_result.partial_close_ratio:
            return partial_result
        
        new_stop = self._update_trailing_stop_short(position, current_price)
        if new_stop:
            return ExitCheckResult(
                should_exit=False,
                new_stop_loss=new_stop,
                message=f"Trailing stop updated to {new_stop}",
            )
        
        return ExitCheckResult(should_exit=False)

    def _check_trailing_stop_long(
        self,
        position: Position,
        current_price: float,
    ) -> ExitCheckResult:
        """检查多头跟踪止损"""
        if not position.trailing_stop_activated:
            return ExitCheckResult(should_exit=False)
        
        trailing_distance = self._get_trailing_distance(position)
        trailing_stop = position.highest_price - trailing_distance
        
        if current_price <= trailing_stop:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.TRAILING_STOP,
                message=f"Trailing stop triggered: {current_price} <= {trailing_stop}",
            )
        
        return ExitCheckResult(should_exit=False)

    def _check_trailing_stop_short(
        self,
        position: Position,
        current_price: float,
    ) -> ExitCheckResult:
        """检查空头跟踪止损"""
        if not position.trailing_stop_activated:
            return ExitCheckResult(should_exit=False)
        
        trailing_distance = self._get_trailing_distance(position)
        trailing_stop = position.lowest_price + trailing_distance
        
        if current_price >= trailing_stop:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.TRAILING_STOP,
                message=f"Trailing stop triggered: {current_price} >= {trailing_stop}",
            )
        
        return ExitCheckResult(should_exit=False)

    def _update_trailing_stop_long(
        self,
        position: Position,
        current_price: float,
    ) -> Optional[float]:
        """更新多头跟踪止损"""
        if not self.config.get("trailing_enabled", True):
            return None
        
        activation_pct = self.config.get("trailing_activation_pct", 0.015)
        profit_pct = (current_price - position.entry_price) / position.entry_price
        
        if profit_pct >= activation_pct:
            position.trailing_stop_activated = True
            trailing_distance = self._get_trailing_distance(position)
            new_stop = current_price - trailing_distance
            
            if new_stop > position.stop_loss:
                logger.info(
                    f"Trailing stop updated for {position.symbol}: "
                    f"{position.stop_loss} -> {new_stop}"
                )
                return new_stop
        
        return None

    def _update_trailing_stop_short(
        self,
        position: Position,
        current_price: float,
    ) -> Optional[float]:
        """更新空头跟踪止损"""
        if not self.config.get("trailing_enabled", True):
            return None
        
        activation_pct = self.config.get("trailing_activation_pct", 0.015)
        profit_pct = (position.entry_price - current_price) / position.entry_price
        
        if profit_pct >= activation_pct:
            position.trailing_stop_activated = True
            trailing_distance = self._get_trailing_distance(position)
            new_stop = current_price + trailing_distance
            
            if new_stop < position.stop_loss:
                logger.info(
                    f"Trailing stop updated for {position.symbol}: "
                    f"{position.stop_loss} -> {new_stop}"
                )
                return new_stop
        
        return None

    def _check_partial_profit_long(
        self,
        position: Position,
        current_price: float,
    ) -> ExitCheckResult:
        """检查多头分批止盈"""
        levels = self.config.get("partial_profit_levels", [0.5, 0.8, 1.0])
        sizes = self.config.get("partial_profit_sizes", [0.3, 0.3, 0.4])
        
        target_profit = position.take_profit - position.entry_price
        current_profit = current_price - position.entry_price
        profit_ratio = current_profit / target_profit if target_profit > 0 else 0
        
        for i, level in enumerate(levels):
            if profit_ratio >= level and level not in position.partial_profits_taken:
                position.partial_profits_taken.append(level)
                return ExitCheckResult(
                    should_exit=False,
                    reason=ExitReason.PARTIAL_PROFIT,
                    partial_close_ratio=sizes[i],
                    message=f"Partial profit level {level} triggered, close {sizes[i]*100}%",
                )
        
        return ExitCheckResult(should_exit=False)

    def _check_partial_profit_short(
        self,
        position: Position,
        current_price: float,
    ) -> ExitCheckResult:
        """检查空头分批止盈"""
        levels = self.config.get("partial_profit_levels", [0.5, 0.8, 1.0])
        sizes = self.config.get("partial_profit_sizes", [0.3, 0.3, 0.4])
        
        target_profit = position.entry_price - position.take_profit
        current_profit = position.entry_price - current_price
        profit_ratio = current_profit / target_profit if target_profit > 0 else 0
        
        for i, level in enumerate(levels):
            if profit_ratio >= level and level not in position.partial_profits_taken:
                position.partial_profits_taken.append(level)
                return ExitCheckResult(
                    should_exit=False,
                    reason=ExitReason.PARTIAL_PROFIT,
                    partial_close_ratio=sizes[i],
                    message=f"Partial profit level {level} triggered, close {sizes[i]*100}%",
                )
        
        return ExitCheckResult(should_exit=False)

    def _get_trailing_distance(self, position: Position) -> float:
        """获取跟踪止损距离"""
        distance_pct = self.config.get("trailing_distance_pct", 0.01)
        distance_atr = self.config.get("trailing_distance_atr", 0.5)
        
        if distance_atr > 0 and hasattr(position, 'entry_atr') and position.entry_atr:
            return position.entry_atr * distance_atr
        else:
            return position.entry_price * distance_pct

    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """计算ATR（Average True Range）"""
        if len(df) < self.atr_period:
            return df['close'].std() if len(df) > 0 else 0.0
        
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        tr[0] = tr1[0]
        
        atr = np.mean(tr[-self.atr_period:])
        return float(atr)

    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """计算历史波动率"""
        if len(df) < 2:
            return 0.02
        
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)
        return float(volatility)
