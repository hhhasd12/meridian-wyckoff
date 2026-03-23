"""交易所执行器 - 封装交易执行逻辑"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.kernel.types import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
)
from src.plugins.exchange_connector.rate_limiter import RateLimiter
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

        # 纸盘交易滑点和手续费参数（参考 bar_by_bar_backtester 模式）
        self.slippage_rate: float = config.get("slippage_rate", 0.0005)
        self.commission_rate: float = config.get("commission_rate", 0.001)

        self._exchange: Optional[Any] = None
        self._paper_positions: Dict[str, Dict[str, Any]] = {}
        self._paper_balance: float = config.get("initial_balance", 10000.0)
        self._paper_orders: List[Dict[str, Any]] = []
        self._order_count: int = 0
        self._last_error: Optional[str] = None

        # 止损单队列（纸盘模式下维护）
        self._pending_stop_orders: List[Dict[str, Any]] = []

        # 滑动窗口限频器（防止超过交易所API速率限制）
        rate_limit_config = config.get("rate_limit", {})
        self._rate_limiter = RateLimiter(
            max_requests=rate_limit_config.get("max_requests", 1100),
            window_seconds=rate_limit_config.get("window_seconds", 60.0),
        )

    def execute(self, request: OrderRequest) -> OrderResult:
        """执行订单 — 主要公共接口

        将类型安全的 OrderRequest 转换为内部下单调用，
        并将结果封装为 OrderResult 返回。

        Args:
            request: 订单请求（包含交易对、方向、类型、数量等）

        Returns:
            OrderResult: 订单执行结果（含状态、成交价、错误信息）
        """
        side_str = request.side.value  # "buy" / "sell"
        order_type_str = request.order_type.value  # "market" / "limit"

        # 如果请求指定了杠杆且与当前不同，临时覆盖
        original_leverage = self.leverage
        if request.leverage and request.leverage != 1:
            self.leverage = request.leverage

        try:
            raw_order = self._place_order(
                symbol=request.symbol,
                side=side_str,
                order_type=order_type_str,
                size=request.size,
                price=request.price,
            )

            # 还原杠杆设置
            self.leverage = original_leverage

            # 从交易所原始返回中提取信息
            order_id = str(raw_order.get("id", ""))
            filled_size = float(raw_order.get("filled", request.size))
            filled_price = float(raw_order.get("price", 0.0) or 0.0)
            status_str = raw_order.get("status", "")

            # 映射交易所状态到 OrderStatus
            if status_str in ("closed", "filled"):
                status = OrderStatus.FILLED
            elif status_str == "canceled":
                status = OrderStatus.CANCELLED
            elif status_str == "open":
                status = OrderStatus.NEW
            elif status_str == "partial":
                status = OrderStatus.PARTIAL
            elif status_str == "expired":
                status = OrderStatus.EXPIRED
            else:
                status = OrderStatus.FILLED  # 默认视为成交

            return OrderResult(
                order_id=order_id,
                status=status,
                filled_size=filled_size,
                filled_price=filled_price,
                timestamp=datetime.now(),
                raw=raw_order,
            )

        except Exception as e:
            # 还原杠杆设置
            self.leverage = original_leverage
            self._last_error = str(e)
            logger.error(f"execute() 订单执行失败: {e}")

            return OrderResult(
                order_id="",
                status=OrderStatus.ERROR,
                filled_size=0.0,
                filled_price=0.0,
                timestamp=datetime.now(),
                error=str(e),
            )

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
            exchange_instance = exchange_class(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "options": {"defaultType": "future"},
                    "enableRateLimit": True,
                }
            )
            self._exchange = exchange_instance

            exchange_instance.load_markets()
            logger.info(f"交易所 {self.default_exchange} 连接成功")
            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"交易所连接失败: {e}")
            return False

    def _place_order(
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

        return self._place_order(
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
                if pos["symbol"] == symbol and float(pos.get("contracts", 0)) != 0:
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
            return balance.get("total", {})
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"获取余额失败: {e}")
            raise

    def get_balance_total(self) -> float:
        """获取账户总余额（便捷方法）

        Returns:
            总余额数值
        """
        balance = self.get_balance()
        total = balance.get("total", 0.0)
        if isinstance(total, dict):
            # 实盘交易所返回的 total 可能是 {"USDT": 1000, ...} 形式
            return sum(float(v) for v in total.values() if v is not None)
        return float(total)

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
                if order["id"] == order_id and order["status"] == "open":
                    order["status"] = "canceled"
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
            orders = [o for o in self._paper_orders if o["status"] == "open"]
            if symbol:
                orders = [o for o in orders if o["symbol"] == symbol]
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
        """模拟下单（含滑点、手续费、止损单、部分成交）"""
        self._order_count += 1
        order_id = f"paper_{self._order_count}"

        execution_price = price
        if order_type == "market":
            execution_price = price or self._get_simulated_price(symbol)
            # 市价单模拟滑点（参考 bar_by_bar_backtester 模式）
            slippage = execution_price * self.slippage_rate
            if side == "buy":
                execution_price += slippage
            else:
                execution_price -= slippage

        # 限价单部分成交模拟：50%概率部分成交
        filled_size = size
        remaining = 0.0
        status = "closed"
        if order_type == "limit":
            import random

            fill_ratio = random.uniform(0.5, 1.0)
            filled_size = size * fill_ratio
            remaining = size - filled_size
            if remaining > 1e-10:
                status = "partial"
                # 记录限价单创建时间用于超时检查
            else:
                filled_size = size
                remaining = 0.0

        # 扣除手续费
        commission = 0.0
        if execution_price is not None and filled_size > 0:
            commission = execution_price * filled_size * self.commission_rate
            self._paper_balance -= commission

        order = {
            "id": order_id,
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": size,
            "price": execution_price,
            "status": status,
            "filled": filled_size,
            "remaining": remaining,
            "timestamp": datetime.now().isoformat(),
            "created_at": datetime.now(),
            "commission": commission,
            "info": {
                "paper_trading": True,
                "slippage_rate": self.slippage_rate,
                "commission": commission,
            },
        }

        self._paper_orders.append(order)

        if side == "buy":
            position_side = PositionSide.LONG
        else:
            position_side = PositionSide.SHORT

        # 仅对已成交部分更新持仓
        if filled_size > 0 and execution_price is not None:
            existing = self._paper_positions.get(symbol)
            if existing:
                if existing["side"] != position_side:
                    del self._paper_positions[symbol]
                else:
                    old_size = existing["size"]
                    existing["avg_price"] = (
                        existing["avg_price"] * old_size + execution_price * filled_size
                    ) / (old_size + filled_size)
                    existing["size"] = old_size + filled_size
            else:
                self._paper_positions[symbol] = {
                    "symbol": symbol,
                    "side": position_side,
                    "size": filled_size,
                    "avg_price": execution_price,
                    "entry_time": datetime.now(),
                }

            # 开仓成功后自动创建止损单
            if symbol not in self._paper_positions or (
                self._paper_positions.get(symbol, {}).get("side") == position_side
            ):
                self._create_stop_order_from_position(
                    symbol, position_side, filled_size, execution_price
                )

        logger.info(
            f"[模拟] 订单已执行: {symbol} {side} {filled_size:.4f}/{size:.4f}"
            f" @ {execution_price} (手续费: {commission:.4f})"
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

    def get_market_price(self, symbol: str) -> Optional[float]:
        """获取当前市场价格

        纸盘模式返回模拟价格，实盘通过 ccxt fetch_ticker 获取。

        Args:
            symbol: 交易对，如 "BTC/USDT"

        Returns:
            当前价格，获取失败返回 None
        """
        if self.paper_trading:
            return self._get_simulated_price(symbol)

        if not self._exchange:
            return None

        try:
            ticker = self._exchange.fetch_ticker(symbol)
            return float(ticker.get("last", 0.0) or 0.0) or None
        except Exception as e:
            logger.warning("获取 %s 市场价失败: %s", symbol, e)
            return None

    def _get_simulated_position(self, symbol: str) -> Optional[Dict]:
        """获取模拟持仓"""
        return self._paper_positions.get(symbol)

    def _create_stop_order_from_position(
        self,
        symbol: str,
        position_side: PositionSide,
        size: float,
        entry_price: float,
    ) -> None:
        """开仓后自动创建 STOP_MARKET 止损单

        默认止损距离为入场价的 2%（可通过 config 调整）。
        LONG 仓位在入场价下方止损，SHORT 仓位在入场价上方止损。
        """
        stop_distance = self.config.get("stop_loss_pct", 0.02)
        if position_side == PositionSide.LONG:
            stop_price = entry_price * (1 - stop_distance)
            close_side = "sell"
        else:
            stop_price = entry_price * (1 + stop_distance)
            close_side = "buy"

        self._order_count += 1
        stop_order = {
            "id": f"stop_{self._order_count}",
            "symbol": symbol,
            "type": "STOP_MARKET",
            "side": close_side,
            "amount": size,
            "stop_price": stop_price,
            "status": "open",
            "created_at": datetime.now(),
            "position_side": position_side,
            "info": {"paper_trading": True},
        }
        self._pending_stop_orders.append(stop_order)
        logger.info(
            f"[模拟] 止损单已创建: {symbol} {close_side} {size} @ stop={stop_price:.2f}"
        )

    def check_stop_orders(
        self, current_prices: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """检查并触发止损单

        遍历 pending_stop_orders，当市场价格达到止损价时执行平仓。
        LONG 止损：当前价 <= stop_price 触发
        SHORT 止损：当前价 >= stop_price 触发

        Args:
            current_prices: {symbol: current_price} 当前市场价格

        Returns:
            已触发的止损单列表
        """
        triggered = []
        remaining = []

        for stop in self._pending_stop_orders:
            symbol = stop["symbol"]
            current = current_prices.get(symbol)
            if current is None:
                remaining.append(stop)
                continue

            pos_side = stop["position_side"]
            should_trigger = False
            if pos_side == PositionSide.LONG and current <= stop["stop_price"]:
                should_trigger = True
            elif pos_side == PositionSide.SHORT and current >= stop["stop_price"]:
                should_trigger = True

            if should_trigger:
                stop["status"] = "triggered"
                # 执行止损平仓
                close_order = self._simulate_order(
                    symbol=symbol,
                    side=stop["side"],
                    order_type="market",
                    size=stop["amount"],
                    price=current,
                )
                stop["execution_order"] = close_order
                triggered.append(stop)
                logger.info(f"[模拟] 止损触发: {symbol} @ {current}")
            else:
                remaining.append(stop)

        self._pending_stop_orders = remaining
        return triggered

    def check_order_timeouts(
        self, timeout_seconds: float = 30.0
    ) -> List[Dict[str, Any]]:
        """检查限价单超时

        部分成交（PARTIAL）的限价单超过 timeout_seconds 后，
        标记剩余部分为 EXPIRED 并取消。

        Args:
            timeout_seconds: 超时时间（默认30秒）

        Returns:
            已超时的订单列表
        """
        expired_orders = []
        now = datetime.now()

        for order in self._paper_orders:
            if order["status"] != "partial":
                continue
            created = order.get("created_at")
            if created is None:
                continue
            elapsed = (now - created).total_seconds()
            if elapsed >= timeout_seconds:
                order["status"] = "expired"
                expired_orders.append(order)
                logger.info(
                    f"[模拟] 限价单超时: {order['id']} "
                    f"已成交 {order['filled']}/{order['amount']}"
                )

        return expired_orders

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "paper_trading": self.paper_trading,
            "order_count": self._order_count,
            "connected": self._exchange is not None or self.paper_trading,
            "last_error": self._last_error,
            "open_positions": len(self._paper_positions)
            if self.paper_trading
            else "N/A",
            "pending_stop_orders": len(self._pending_stop_orders),
            "paper_balance": self._paper_balance if self.paper_trading else "N/A",
            "slippage_rate": self.slippage_rate,
            "commission_rate": self.commission_rate,
            "rate_limiter_usage": self._rate_limiter.current_usage,
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
            price_change_pct = (
                exit_price - position.entry_price
            ) / position.entry_price
        else:
            pnl = (position.entry_price - exit_price) * position.size
            price_change_pct = (
                position.entry_price - exit_price
            ) / position.entry_price
        # PnL百分比相对于保证金，需乘以杠杆倍数
        pnl_pct = price_change_pct * position.leverage

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
