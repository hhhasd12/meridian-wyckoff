"""仓位管理插件 - 插件入口"""

import logging
from typing import Any, Dict, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus, TradingSignal
from src.plugins.position_manager.position_manager import PositionManager
from src.plugins.position_manager.types import (
    ExitCheckResult,
    ExitReason,
    Position,
    PositionSide,
    TradeResult,
)

logger = logging.getLogger(__name__)


class PositionManagerPlugin(BasePlugin):
    """仓位管理插件
    
    功能：
    1. 管理持仓生命周期
    2. 止损止盈执行
    3. 信号反转出场
    4. 交易记录管理
    
    事件：
    - 发布：position.opened, position.closed, position.updated
    - 订阅：trading.signal, market.price_update
    """

    def __init__(self, name: str = "position_manager") -> None:
        super().__init__(name)
        self._manager: Optional[PositionManager] = None
        self._open_count: int = 0
        self._close_count: int = 0
        self._update_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件"""
        config = self._config or {}
        
        self._manager = PositionManager(config)
        
        self.subscribe_event("trading.signal", self._on_trading_signal)
        self.subscribe_event("market.price_update", self._on_price_update)
        self.subscribe_event("system.shutdown", self._on_shutdown)
        
        logger.info("仓位管理插件加载完成")

    def on_unload(self) -> None:
        """卸载插件"""
        if self._manager:
            positions = self._manager.get_all_positions()
            if positions:
                logger.warning(f"卸载时仍有 {len(positions)} 个持仓未关闭")
        
        self._manager = None
        self._open_count = 0
        self._close_count = 0
        self._update_count = 0
        self._last_error = None
        logger.info("仓位管理插件已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """配置更新"""
        if self._manager:
            self._manager = PositionManager(new_config)
            logger.info("仓位管理插件配置已更新")

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        if self._manager is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="PositionManager not initialized",
                details={"error": self._last_error},
            )
        
        stats = self._manager.get_statistics()
        open_positions = self._manager.get_open_position_count()
        
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"PositionManager running, {open_positions} open positions",
            details={
                "open_positions": open_positions,
                "total_trades": stats["total_trades"],
                "win_rate": stats["win_rate"],
                "total_pnl": stats["total_pnl"],
                "open_count": self._open_count,
                "close_count": self._close_count,
            },
        )

    def _on_trading_signal(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理交易信号事件"""
        try:
            symbol = data.get("symbol")
            signal = data.get("signal")
            confidence = data.get("confidence", 0.0)
            wyckoff_state = data.get("wyckoff_state", "")
            price = data.get("price", 0.0)
            df = data.get("df")
            
            if not symbol or not signal:
                return
            
            position = self._manager.get_position(symbol)
            
            if position:
                exit_result = self._manager.update_position(
                    symbol=symbol,
                    current_price=price,
                    new_signal=signal,
                    new_wyckoff_state=wyckoff_state,
                    signal_confidence=confidence,
                )
                
                if exit_result and exit_result.should_exit:
                    self._execute_exit(symbol, price, exit_result)
            else:
                if signal in [TradingSignal.BUY, TradingSignal.STRONG_BUY]:
                    self._try_open_position(
                        symbol, PositionSide.LONG, price, confidence,
                        wyckoff_state, signal, df, data
                    )
                elif signal in [TradingSignal.SELL, TradingSignal.STRONG_SELL]:
                    self._try_open_position(
                        symbol, PositionSide.SHORT, price, confidence,
                        wyckoff_state, signal, df, data
                    )
                    
        except Exception as e:
            self._last_error = str(e)
            logger.exception(f"处理交易信号失败: {e}")

    def _on_price_update(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理价格更新事件"""
        try:
            symbol = data.get("symbol")
            price = data.get("price")
            
            if not symbol or not price:
                return
            
            position = self._manager.get_position(symbol)
            if not position:
                return
            
            exit_result = self._manager.update_position(
                symbol=symbol,
                current_price=price,
            )
            
            if exit_result:
                if exit_result.should_exit:
                    self._execute_exit(symbol, price, exit_result)
                elif exit_result.partial_close_ratio:
                    self._execute_partial_close(symbol, price, exit_result)
                    
        except Exception as e:
            self._last_error = str(e)
            logger.exception(f"处理价格更新失败: {e}")

    def _on_shutdown(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理系统关闭事件"""
        logger.info("系统关闭，平仓所有持仓...")
        
        if self._manager:
            positions = self._manager.get_all_positions()
            exit_prices = {
                symbol: pos.entry_price
                for symbol, pos in positions.items()
            }
            results = self._manager.force_close_all(exit_prices)
            logger.info(f"已平仓 {len(results)} 个持仓")

    def _try_open_position(
        self,
        symbol: str,
        side: PositionSide,
        price: float,
        confidence: float,
        wyckoff_state: str,
        signal: TradingSignal,
        df: Optional[pd.DataFrame],
        data: Dict[str, Any],
    ) -> None:
        """尝试开仓"""
        if not self._manager.can_open_position(symbol):
            logger.debug(f"无法开仓 {symbol}: 已有持仓或达到最大持仓数")
            return
        
        min_confidence = self._config.get("min_confidence", 0.65)
        if confidence < min_confidence:
            logger.debug(f"置信度不足 {confidence:.2f} < {min_confidence}")
            return
        
        account_balance = data.get("account_balance", 10000.0)
        
        if df is not None and len(df) > 0:
            stop_loss = self._manager.stop_loss_executor.calculate_stop_loss(
                entry_price=price,
                side=side,
                df=df,
            )
        else:
            stop_loss = price * 0.98 if side == PositionSide.LONG else price * 1.02
        
        size = self._manager.calculate_position_size(
            account_balance=account_balance,
            entry_price=price,
            stop_loss=stop_loss,
        )
        
        if size <= 0:
            logger.warning(f"仓位大小计算失败: {symbol}")
            return
        
        position = self._manager.open_position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=price,
            signal_confidence=confidence,
            wyckoff_state=wyckoff_state,
            entry_signal=signal,
            df=df,
            metadata={"account_balance": account_balance},
        )
        
        if position:
            self._open_count += 1
            self.emit_event("position.opened", position.to_dict())

    def _execute_exit(
        self,
        symbol: str,
        price: float,
        exit_result: ExitCheckResult,
    ) -> None:
        """执行平仓"""
        reason = exit_result.reason or ExitReason.MANUAL
        
        result = self._manager.close_position(
            symbol=symbol,
            exit_price=price,
            reason=reason,
        )
        
        if result:
            self._close_count += 1
            self.emit_event("position.closed", result.to_dict())
            logger.info(
                f"持仓已平仓: {symbol} reason={reason.value} "
                f"pnl={result.pnl:.2f} ({result.pnl_pct*100:.2f}%)"
            )

    def _execute_partial_close(
        self,
        symbol: str,
        price: float,
        exit_result: ExitCheckResult,
    ) -> None:
        """执行部分平仓"""
        ratio = exit_result.partial_close_ratio
        if not ratio:
            return
        
        result = self._manager.close_position(
            symbol=symbol,
            exit_price=price,
            reason=ExitReason.PARTIAL_PROFIT,
            partial_ratio=ratio,
        )
        
        if result:
            self.emit_event("position.partial_close", {
                **result.to_dict(),
                "remaining_size": self._manager.get_position(symbol).size if self._manager.get_position(symbol) else 0,
            })
            logger.info(
                f"部分平仓: {symbol} ratio={ratio*100:.0f}% "
                f"pnl={result.pnl:.2f}"
            )

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        size: float,
        entry_price: float,
        signal_confidence: float,
        wyckoff_state: str,
        entry_signal: TradingSignal,
        df: Optional[pd.DataFrame] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Position]:
        """手动开仓接口"""
        if not self._manager:
            return None
        
        position = self._manager.open_position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            signal_confidence=signal_confidence,
            wyckoff_state=wyckoff_state,
            entry_signal=entry_signal,
            df=df,
            metadata=metadata,
        )
        
        if position:
            self._open_count += 1
            self.emit_event("position.opened", position.to_dict())
        
        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: ExitReason = ExitReason.MANUAL,
    ) -> Optional[TradeResult]:
        """手动平仓接口"""
        if not self._manager:
            return None
        
        result = self._manager.close_position(
            symbol=symbol,
            exit_price=exit_price,
            reason=reason,
        )
        
        if result:
            self._close_count += 1
            self.emit_event("position.closed", result.to_dict())
        
        return result

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        if not self._manager:
            return None
        return self._manager.get_position(symbol)

    def get_all_positions(self) -> Dict[str, Position]:
        """获取所有持仓"""
        if not self._manager:
            return {}
        return self._manager.get_all_positions()

    def get_statistics(self) -> Dict[str, Any]:
        """获取交易统计"""
        if not self._manager:
            return {}
        return self._manager.get_statistics()

    def get_trade_history(self, limit: int = 100) -> list:
        """获取交易历史（供API调用）

        Args:
            limit: 返回记录数量限制

        Returns:
            List: 交易历史列表
        """
        if not self._manager:
            return []
        
        history = self._manager.trade_history[-limit:] if hasattr(self._manager, 'trade_history') else []
        return [
            {
                "symbol": t.symbol,
                "side": t.side.value,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size": t.size,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "exit_reason": t.exit_reason.value,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
            }
            for t in history
        ]

    def get_performance_by_day(self, days: int = 7) -> Dict[str, Any]:
        """获取按日统计的性能数据（供API调用）

        Args:
            days: 统计天数

        Returns:
            Dict: 包含data和labels的字典
        """
        if not self._manager or not hasattr(self._manager, 'trade_history'):
            return {"data": [], "labels": []}
        
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        history = self._manager.trade_history
        if not history:
            return {"data": [], "labels": []}
        
        daily_pnl = defaultdict(float)
        today = datetime.now().date()
        
        for trade in history:
            trade_date = trade.exit_time.date()
            days_ago = (today - trade_date).days
            if days_ago < days:
                daily_pnl[trade_date] += trade.pnl_pct * 100
        
        data = []
        labels = []
        for i in range(days - 1, -1, -1):
            date = today - timedelta(days=i)
            data.append(daily_pnl.get(date, 0))
            labels.append(date.strftime('%m-%d'))
        
        return {"data": data, "labels": labels}
