"""交易所执行器 - 封装交易执行逻辑"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.plugins.position_manager.types import (
    Position,
    PositionSide,
    TradeResult,
    ExitReason,
)

logger = logging.getLogger(__name__)


class ExchangeExecutor:
    """交易所执行器
    
    功能：
    1. 下单执行（市价、限价）
    2. 持仓查询
    3. 平仓执行
    4. 模拟交易支持
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.paper_trading = config.get("paper_trading", True)
        self.default_exchange = config.get("default_exchange", "binance")
        self.leverage = config.get("leverage", 5)
        self.margin_mode = config.get("margin_mode", "isolated")
        
        self._exchange: Optional[Any] = None
        self._paper_positions: Dict[str, Dict[str, Any]] = {}
        self._paper_balance: float = config.get("initial_balance", 10000.0)
        self._paper_orders: List[Dict[str, Any]] = []
        self._order_count: int = 0
        self._last_error: Optional[str] = None

    def connect(self, exchange: Optional[Any] = None) -> bool:
        """连接交易所
        
        Args:
            exchange: ccxt交易所实例（可选）
        
        Returns:
            连接是否成功
        """
        if self.paper_trading:
            logger.info("模拟交易模式 - 无需实际连接交易所")
            return True
        
        if exchange:
            self._exchange = exchange
            return True
        
        try:
            import ccxt
            
            api_key = os.environ.get("WYCKOFF_API_KEY", "")
            api_secret = os.environ.get("WYCKOFF_API_SECRET", "")
            
            exchange_class = getattr(ccxt, self.default_exchange)
            self._exchange = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {'defaultType': 'future'},
                'enableRateLimit': True,
            })
            
            self._exchange.load_markets()
            logger.info(f"交易所 {self.default_exchange} 连接成功")
            return True
            
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"交易所连接失败: {e}")
            return False

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """下单
        
        Args:
            symbol: 交易对
            side: 方向 ("buy" / "sell")
            order_type: 订单类型 ("market" / "limit")
            size: 数量
            price: 价格（限价单需要）
            params: 额外参数
        
        Returns:
            订单信息
        """
        if self.paper_trading:
            return self._simulate_order(symbol, side, order_type, size, price)
        
        if not self._exchange:
            raise RuntimeError("交易所未连接")
        
        try:
            order_params = params or {}
            
            if self.leverage and self.leverage != 1:
                self._exchange.set_leverage(self.leverage, symbol)
            
            order = self._exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=size,
                price=price,
                params=order_params,
            )
            
            self._order_count += 1
            logger.info(
                f"订单已创建: {symbol} {side} {size} @ {price or 'market'} "
                f"id={order.get('id')}"
            )
            
            return order
            
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"下单失败: {e}")
            raise

    def close_position(
        self,
        symbol: str,
        side: PositionSide,
        size: float,
        order_type: str = "market",
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """平仓
        
        Args:
            symbol: 交易对
            side: 持仓方向
            size: 数量
            order_type: 订单类型
            price: 价格
        
        Returns:
            订单信息
        """
        close_side = "sell" if side == PositionSide.LONG else "buy"
        
        return self.place_order(
            symbol=symbol,
            side=close_side,
            order_type=order_type,
            size=size,
            price=price,
        )

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取持仓
        
        Args:
            symbol: 交易对
        
        Returns:
            持仓信息
        """
        if self.paper_trading:
            return self._paper_positions.get(symbol)
        
        if not self._exchange:
            raise RuntimeError("交易所未连接")
        
        try:
            positions = self._exchange.fetch_positions([symbol])
            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) != 0:
                    return pos
            return None
            
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"获取持仓失败: {e}")
            raise

    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额
        
        Returns:
            余额信息
        """
        if self.paper_trading:
            return {
                "total": self._paper_balance,
                "free": self._paper_balance,
                "used": 0.0,
            }
        
        if not self._exchange:
            raise RuntimeError("交易所未连接")
        
        try:
            balance = self._exchange.fetch_balance()
            return balance.get('total', {})
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"获取余额失败: {e}")
            raise

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单
        
        Args:
            order_id: 订单ID
            symbol: 交易对
        
        Returns:
            是否成功
        """
        if self.paper_trading:
            for order in self._paper_orders:
                if order['id'] == order_id and order['status'] == 'open':
                    order['status'] = 'canceled'
                    return True
            return False
        
        if not self._exchange:
            raise RuntimeError("交易所未连接")
        
        try:
            self._exchange.cancel_order(order_id, symbol)
            logger.info(f"订单已取消: {order_id}")
            return True
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"取消订单失败: {e}")
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取未完成订单
        
        Args:
            symbol: 交易对（可选）
        
        Returns:
            订单列表
        """
        if self.paper_trading:
            orders = [o for o in self._paper_orders if o['status'] == 'open']
            if symbol:
                orders = [o for o in orders if o['symbol'] == symbol]
            return orders
        
        if not self._exchange:
            raise RuntimeError("交易所未连接")
        
        try:
            symbols = [symbol] if symbol else None
            return self._exchange.fetch_open_orders(symbols)
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"获取订单失败: {e}")
            raise

    def _simulate_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """模拟下单"""
        self._order_count += 1
        order_id = f"paper_{self._order_count}"
        
        execution_price = price
        if order_type == "market":
            execution_price = price or self._get_simulated_price(symbol)
        
        order = {
            "id": order_id,
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": size,
            "price": execution_price,
            "status": "closed",
            "filled": size,
            "remaining": 0.0,
            "timestamp": datetime.now().isoformat(),
            "info": {
                "paper_trading": True,
            },
        }
        
        self._paper_orders.append(order)
        
        if side == "buy":
            position_side = PositionSide.LONG
        else:
            position_side = PositionSide.SHORT
        
        existing = self._paper_positions.get(symbol)
        if existing:
            if existing['side'] != position_side:
                del self._paper_positions[symbol]
            else:
                existing['size'] += size
                existing['avg_price'] = (
                    existing['avg_price'] * (existing['size'] - size) + 
                    (execution_price or 0) * size
                ) / existing['size']
        else:
            self._paper_positions[symbol] = {
                "symbol": symbol,
                "side": position_side,
                "size": size,
                "avg_price": execution_price,
                "entry_time": datetime.now(),
            }
        
        logger.info(
            f"[模拟] 订单已执行: {symbol} {side} {size} @ {execution_price}"
        )
        
        return order

    def _get_simulated_price(self, symbol: str) -> float:
        """获取模拟价格"""
        base_prices = {
            "BTC/USDT": 50000.0,
            "ETH/USDT": 3000.0,
            "SOL/USDT": 100.0,
        }
        return base_prices.get(symbol, 100.0)

    def _get_simulated_position(self, symbol: str) -> Optional[Dict]:
        """获取模拟持仓"""
        return self._paper_positions.get(symbol)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "paper_trading": self.paper_trading,
            "order_count": self._order_count,
            "connected": self._exchange is not None or self.paper_trading,
            "last_error": self._last_error,
            "open_positions": len(self._paper_positions) if self.paper_trading else "N/A",
        }

    def execute_trade_result(
        self,
        position: Position,
        exit_price: float,
        exit_reason: ExitReason,
    ) -> TradeResult:
        """执行交易并返回结果
        
        Args:
            position: 持仓信息
            exit_price: 出场价格
            exit_reason: 出场原因
        
        Returns:
            TradeResult: 交易结果
        """
        from datetime import timedelta
        
        exit_time = datetime.now()
        
        if position.side == PositionSide.LONG:
            pnl = (exit_price - position.entry_price) * position.size
            pnl_pct = (exit_price - position.entry_price) / position.entry_price
        else:
            pnl = (position.entry_price - exit_price) * position.size
            pnl_pct = (position.entry_price - exit_price) / position.entry_price
        
        return TradeResult(
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_duration=exit_time - position.entry_time,
            exit_reason=exit_reason,
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
