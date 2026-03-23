"""仓位管理插件 v3 — 接通 ExchangeExecutor + PositionJournal

核心改动（Phase 3）：
1. 持有 ExchangeExecutor — 通过 execute(OrderRequest) 实际下单
2. 集成 PositionJournal — 每次仓位变化写盘，崩溃恢复
3. _on_trading_signal 接收完整 TradingDecision（由 Orchestrator 发布）
4. 启动时从 PositionJournal 恢复 open positions

事件流：
    trading.signal → _on_trading_signal()
        → 检查信号/仓位 → 生成 OrderRequest
        → ExchangeExecutor.execute() → OrderResult
        → PositionJournal 记录
        → position.opened / position.closed 事件
"""

import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import (
    HealthCheckResult,
    HealthStatus,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingDecision,
    TradingSignal,
)
from src.plugins.exchange_connector.exchange_executor import (
    ExchangeExecutor,
)
from src.plugins.position_manager.position_journal import (
    PositionJournal,
)
from src.plugins.position_manager.position_manager import (
    PositionManager,
)
from src.plugins.position_manager.types import (
    ExitCheckResult,
    ExitReason,
    Position,
    PositionSide,
    TradeResult,
)

logger = logging.getLogger(__name__)


class PositionManagerPlugin(BasePlugin):
    """仓位管理插件 v3

    功能：
    1. 管理持仓生命周期（开仓/平仓/部分平仓）
    2. 通过 ExchangeExecutor 实际执行交易
    3. 通过 PositionJournal 持久化仓位状态
    4. 启动时从 journal 恢复 open positions
    5. 止损止盈执行 + 信号反转出场

    事件：
    - 订阅：trading.signal, market.price_update, system.shutdown
    - 发布：position.opened, position.closed, position.updated
    """

    def __init__(self, name: str = "position_manager") -> None:
        super().__init__(name)
        self._manager: Optional[PositionManager] = None
        self._executor: Optional[ExchangeExecutor] = None
        self._journal: Optional[PositionJournal] = None
        self._open_count: int = 0
        self._close_count: int = 0
        self._update_count: int = 0
        self._last_error: Optional[str] = None
        self._last_prices: Dict[str, float] = {}
        self._pending_exits: List[Dict[str, Any]] = []
        self._circuit_breaker_active: bool = False

    def on_load(self) -> None:
        """加载插件：初始化 PositionManager/Executor/Journal"""
        config = self._config or {}

        # 初始化仓位管理器
        self._manager = PositionManager(config)

        # 初始化交易执行器
        executor_config = config.get("executor", {})
        executor_config.setdefault("paper_trading", config.get("paper_trading", True))
        executor_config.setdefault(
            "initial_balance",
            config.get("initial_balance", 10000.0),
        )
        self._executor = ExchangeExecutor(executor_config)
        self._executor.connect()

        # 初始化持仓日志
        journal_path = config.get("journal_path", "./data/position_journal.jsonl")
        self._journal = PositionJournal(journal_path)

        # 从日志恢复持仓
        self._recover_positions()

        # 订阅事件
        self.subscribe_event("trading.signal", self._on_trading_signal)
        self.subscribe_event("market.price_update", self._on_price_update)
        self.subscribe_event("system.shutdown", self._on_shutdown)
        self.subscribe_event(
            "risk_management.circuit_breaker_tripped",
            self._on_circuit_breaker_tripped,
        )
        self.subscribe_event(
            "risk_management.circuit_breaker_recovered",
            self._on_circuit_breaker_recovered,
        )

        logger.info("仓位管理插件 v3 加载完成")

    def _recover_positions(self) -> None:
        """从 PositionJournal 恢复持仓"""
        if self._journal is None or self._manager is None:
            return

        recovered = self._journal.recover_positions()
        if not recovered:
            return

        for symbol, position in recovered.items():
            self._manager.positions[symbol] = position
            logger.info(
                "恢复持仓: %s %s %.4f @ %.2f",
                symbol,
                position.side.value,
                position.size,
                position.entry_price,
            )

        logger.info("从日志恢复 %d 个持仓", len(recovered))

        # 启动对账：比较 journal 恢复的持仓 vs exchange 报告的持仓
        self._reconcile_with_exchange(recovered)

        # 验证市场价：检查止损是否已被击穿，更新 unrealized_pnl
        self._validate_recovered_positions(recovered)

    def _validate_recovered_positions(self, recovered: Dict[str, "Position"]) -> None:
        """恢复持仓后验证市场价

        系统重启期间价格可能已穿过止损线（5x杠杆下可能爆仓），
        因此需要获取当前市场价并逐一检查：
        1. 止损是否已被击穿 → 标记为需要立即平仓
        2. 更新 unrealized_pnl

        如果无法获取市场价（交易所未连接），记录 WARNING 并跳过。
        """
        if self._executor is None or self._manager is None:
            return

        breached_symbols: list[str] = []

        for symbol, position in recovered.items():
            price = self._executor.get_market_price(symbol)
            if price is None:
                logger.warning(
                    "恢复验证: %s 无法获取市场价，跳过验证",
                    symbol,
                )
                continue

            # 更新 unrealized_pnl
            position.calculate_unrealized_pnl(price)
            position.update_price_extremes(price)
            self._last_prices[symbol] = price

            # 检查止损是否已被击穿
            stop_breached = False
            if position.side == PositionSide.LONG:
                stop_breached = price <= position.stop_loss
            else:
                stop_breached = price >= position.stop_loss

            if stop_breached:
                breached_symbols.append(symbol)
                logger.warning(
                    "恢复验证: %s 止损已击穿 "
                    "(side=%s price=%.2f stop=%.2f pnl=%.2f)，"
                    "标记立即平仓",
                    symbol,
                    position.side.value,
                    price,
                    position.stop_loss,
                    position.unrealized_pnl,
                )
            else:
                logger.info(
                    "恢复验证: %s 止损安全 (price=%.2f stop=%.2f pnl=%.2f)",
                    symbol,
                    price,
                    position.stop_loss,
                    position.unrealized_pnl,
                )

        # 对已击穿止损的持仓执行立即平仓
        for symbol in breached_symbols:
            price = self._last_prices.get(symbol, 0.0)
            exit_result = ExitCheckResult(
                should_exit=True,
                reason=ExitReason.STOP_LOSS,
                message=f"恢复验证: 止损已击穿 price={price:.2f}",
            )
            self._execute_exit(symbol, price, exit_result)

        if breached_symbols:
            logger.warning(
                "恢复验证完成: %d/%d 个持仓止损已击穿并触发平仓",
                len(breached_symbols),
                len(recovered),
            )

    def _reconcile_with_exchange(self, journal_positions: Dict[str, Any]) -> None:
        """对账：比较 journal 恢复的持仓 vs exchange 实际持仓

        仅记录 WARNING 日志报告差异，不自动修复。
        如果 exchange_connector 不可用，静默跳过。

        Args:
            journal_positions: 从 journal 恢复的持仓字典
        """
        if self._executor is None:
            return

        try:
            # 遍历 journal 持仓，逐个与 exchange 对比
            for symbol, j_pos in journal_positions.items():
                ex_pos = self._executor.get_position(symbol)

                if ex_pos is None:
                    logger.warning(
                        "对账差异: %s journal 有持仓(%.4f @ %.2f) 但 exchange 无记录",
                        symbol,
                        j_pos.size,
                        j_pos.entry_price,
                    )
                    continue

                # 比较仓位大小（允许 1% 误差）
                ex_size = float(ex_pos.get("size", 0.0))
                if abs(ex_size - j_pos.size) > j_pos.size * 0.01:
                    logger.warning(
                        "对账差异: %s 仓位大小不一致 journal=%.4f exchange=%.4f",
                        symbol,
                        j_pos.size,
                        ex_size,
                    )

            logger.info(
                "启动对账完成，检查 %d 个持仓",
                len(journal_positions),
            )

        except Exception as e:
            # 对账失败不阻止系统启动
            logger.warning("启动对账跳过: %s", e)

    def on_unload(self) -> None:
        """卸载插件"""
        if self._manager:
            positions = self._manager.get_all_positions()
            if positions:
                logger.warning(
                    "卸载时仍有 %d 个持仓未关闭",
                    len(positions),
                )
        self._manager = None
        self._executor = None
        self._journal = None
        logger.info("仓位管理插件已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """配置更新"""
        if self._manager:
            self._manager = PositionManager(new_config)
            logger.info("仓位管理插件配置已更新")

    # ================================================================
    # 核心事件处理
    # ================================================================

    def _on_trading_signal(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理交易信号事件

        由 OrchestratorPlugin 发布的 trading.signal 事件触发。
        data 中包含:
        - symbol: 交易对
        - signal: TradingSignal 枚举
        - confidence: 置信度
        - decision: TradingDecision 对象
        - df: 主时间框架 DataFrame（可选）
        - wyckoff_state: 威科夫状态
        """
        try:
            symbol = data.get("symbol")
            signal = data.get("signal")
            confidence = data.get("confidence", 0.0)
            wyckoff_state = data.get("wyckoff_state", "")
            df = data.get("df")
            decision: Optional[TradingDecision] = data.get("decision")

            if not symbol or not signal:
                return

            # 从 decision 中提取更多信息
            entry_price = data.get("entry_price", 0.0)
            stop_loss_hint = data.get("stop_loss")
            take_profit_hint = data.get("take_profit")

            if decision:
                entry_price = decision.entry_price or entry_price
                stop_loss_hint = decision.stop_loss or stop_loss_hint
                take_profit_hint = decision.take_profit or take_profit_hint

            # 如果没有价格，跳过
            if not entry_price or entry_price <= 0:
                logger.debug("信号无入场价格，跳过: %s", symbol)
                return

            # 检查现有持仓
            if self._manager is None:
                return

            position = self._manager.get_position(symbol)

            if position:
                # 已有持仓 — 检查是否需要退出
                self._check_signal_exit(
                    symbol,
                    position,
                    signal,
                    wyckoff_state,
                    confidence,
                    entry_price,
                )
            else:
                # 无持仓 — 检查是否开仓
                if signal in (
                    TradingSignal.BUY,
                    TradingSignal.STRONG_BUY,
                ):
                    self._try_open_position(
                        symbol,
                        PositionSide.LONG,
                        entry_price,
                        confidence,
                        wyckoff_state,
                        signal,
                        df,
                        data,
                        stop_loss_hint,
                        take_profit_hint,
                    )
                elif signal in (
                    TradingSignal.SELL,
                    TradingSignal.STRONG_SELL,
                ):
                    self._try_open_position(
                        symbol,
                        PositionSide.SHORT,
                        entry_price,
                        confidence,
                        wyckoff_state,
                        signal,
                        df,
                        data,
                        stop_loss_hint,
                        take_profit_hint,
                    )

        except Exception as e:
            self._last_error = str(e)
            logger.exception("处理交易信号失败: %s", e)

    def _get_capital_guard(self) -> Optional[Any]:
        """获取资金守卫实例（graceful降级）

        通过 plugin_manager 获取 risk_management 插件，
        再取其 capital_guard 属性。获取不到则返回 None（放行）。
        """
        try:
            rm_plugin = self.get_plugin("risk_management")
            if rm_plugin is not None:
                return getattr(rm_plugin, "capital_guard", None)
        except Exception as e:
            logger.warning("risk_management 查找失败: %s", e)
        return None

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
        stop_loss_hint: Optional[float],
        take_profit_hint: Optional[float],
    ) -> None:
        """尝试开仓 — 通过 ExchangeExecutor 执行"""
        # TODO: 多品种持仓相关性检查（避免同方向过度暴露）
        if self._manager is None or self._executor is None:
            return

        # ---- 熔断器检查 ----
        if self._circuit_breaker_active:
            logger.warning("熔断器激活中，拒绝开仓: %s", symbol)
            return

        # ---- 资金守卫熔断检查 ----
        capital_guard = self._get_capital_guard()
        if capital_guard is not None:
            if not capital_guard.is_trading_allowed():
                logger.warning("资金守卫熔断中，拒绝开仓: %s", symbol)
                return
            position_scale = capital_guard.get_position_scale()
        else:
            position_scale = 1.0

        if not self._manager.can_open_position(symbol):
            logger.debug("无法开仓 %s: 已有持仓或达到上限", symbol)
            return

        min_confidence = self._config.get("min_confidence", 0.65)
        if confidence < min_confidence:
            logger.debug(
                "置信度不足 %.2f < %.2f",
                confidence,
                min_confidence,
            )
            return

        # 计算止损
        if stop_loss_hint:
            stop_loss = stop_loss_hint
        elif df is not None and len(df) > 0:
            stop_loss = self._manager.stop_loss_executor.calculate_stop_loss(
                entry_price=price,
                side=side,
                df=df,
            )
        else:
            stop_loss = price * 0.98 if side == PositionSide.LONG else price * 1.02

        # 计算仓位大小
        account_balance = data.get(
            "account_balance",
            self._executor.get_balance_total(),
        )
        default_leverage = self._config.get("default_leverage", 1.0)
        leverage = float(data.get("leverage", default_leverage))
        size = self._manager.calculate_position_size(
            account_balance=account_balance,
            entry_price=price,
            stop_loss=stop_loss,
            leverage=leverage,
        )
        if size <= 0:
            logger.warning("仓位大小计算为0: %s", symbol)
            return

        # 应用资金守卫仓位缩放
        if position_scale < 1.0:
            original_size = size
            size = size * position_scale
            logger.info(
                "资金守卫缩放仓位 %s: %.4f -> %.4f (scale=%.2f)",
                symbol,
                original_size,
                size,
                position_scale,
            )
            if size <= 0:
                logger.warning("缩放后仓位为0，跳过开仓: %s", symbol)
                return

        # 通过 ExchangeExecutor 下单
        order_side = OrderSide.BUY if side == PositionSide.LONG else OrderSide.SELL
        request = OrderRequest(
            symbol=symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            size=size,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit_hint,
            metadata={
                "signal": signal.value,
                "confidence": confidence,
                "wyckoff_state": wyckoff_state,
            },
        )

        result = self._executor.execute(request)

        if result.is_error:
            logger.error(
                "开仓执行失败: %s error=%s",
                symbol,
                result.error,
            )
            return

        # 执行成功 — 记录到 PositionManager
        filled_price = result.filled_price or price
        filled_size = result.filled_size or size

        # 计算止盈
        take_profit = take_profit_hint
        if not take_profit:
            risk = abs(filled_price - stop_loss)
            if side == PositionSide.LONG:
                take_profit = filled_price + risk * 2.0
            else:
                take_profit = filled_price - risk * 2.0

        position = self._manager.open_position(
            symbol=symbol,
            side=side,
            size=filled_size,
            entry_price=filled_price,
            signal_confidence=confidence,
            wyckoff_state=wyckoff_state,
            entry_signal=signal,
            df=df if df is not None else pd.DataFrame(),
            metadata={
                "order_id": result.order_id,
                "account_balance": account_balance,
            },
            leverage=leverage,
        )

        if position:
            self._open_count += 1
            # 记录到日志
            if self._journal:
                self._journal.record_open(position)
            self.emit_event("position.opened", position.to_dict())
            logger.info(
                "开仓成功: %s %s %.4f @ %.2f (order_id=%s)",
                symbol,
                side.value,
                filled_size,
                filled_price,
                result.order_id,
            )

    def _check_signal_exit(
        self,
        symbol: str,
        position: Position,
        signal: TradingSignal,
        wyckoff_state: str,
        confidence: float,
        current_price: float,
    ) -> None:
        """检查是否需要信号反转退出"""
        if self._manager is None:
            return

        exit_result = self._manager.update_position(
            symbol=symbol,
            current_price=current_price,
            new_signal=signal,
            new_wyckoff_state=wyckoff_state,
            signal_confidence=confidence,
        )

        if exit_result and exit_result.should_exit:
            self._execute_exit(symbol, current_price, exit_result)
        elif exit_result and exit_result.partial_close_ratio:
            self._execute_partial_close(symbol, current_price, exit_result)

        # 记录更新到日志
        if self._journal:
            self._journal.record_update(
                symbol,
                {
                    "current_price": current_price,
                    "signal": signal.value,
                    "wyckoff_state": wyckoff_state,
                },
            )

    def _execute_exit(
        self,
        symbol: str,
        price: float,
        exit_result: ExitCheckResult,
    ) -> None:
        """执行平仓 — 通过 ExchangeExecutor（带指数退避重试）"""
        if self._manager is None or self._executor is None:
            return

        position = self._manager.get_position(symbol)
        if not position:
            return

        reason = exit_result.reason or ExitReason.MANUAL

        # 通过 ExchangeExecutor 执行平仓（指数退避重试）
        close_side = (
            OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY
        )
        request = OrderRequest(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            size=position.size,
            price=price,
            metadata={"exit_reason": reason.value},
        )

        max_retries = 3
        order_result: Optional[OrderResult] = None
        for attempt in range(max_retries):
            order_result = self._executor.execute(request)
            if not order_result.is_error:
                break
            wait = 2**attempt  # 1s, 2s, 4s
            logger.warning(
                "平仓重试 %d/%d: %s error=%s (等待%ds)",
                attempt + 1,
                max_retries,
                symbol,
                order_result.error,
                wait,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)

        if order_result is None or order_result.is_error:
            logger.critical(
                "平仓 %d 次均失败: %s error=%s，加入待重试队列",
                max_retries,
                symbol,
                order_result.error if order_result else "unknown",
            )
            self._pending_exits.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "exit_result": exit_result,
                    "timestamp": time.time(),
                }
            )
            return

        # 部分成交处理：仅平掉已成交部分，剩余重新排队
        filled_price = order_result.filled_price or price
        filled_size = order_result.filled_size or position.size

        if order_result.status == OrderStatus.PARTIAL and filled_size < position.size:
            # 部分成交：按已成交比例部分平仓
            partial_ratio = filled_size / position.size
            trade_result = self._manager.close_position(
                symbol=symbol,
                exit_price=filled_price,
                reason=reason,
                partial_ratio=partial_ratio,
            )
            if trade_result:
                self._close_count += 1
                if self._journal:
                    self._journal.record_close(symbol, trade_result)
                self.emit_event("position.partial_close", trade_result.to_dict())
                logger.info(
                    "部分平仓(部分成交): %s filled=%.4f/%.4f reason=%s",
                    symbol,
                    filled_size,
                    position.size,
                    reason.value,
                )
            # 将剩余部分加入待重试队列
            self._pending_exits.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "exit_result": exit_result,
                    "timestamp": time.time(),
                }
            )
            return

        # 全部成交 — 记录平仓
        trade_result = self._manager.close_position(
            symbol=symbol,
            exit_price=filled_price,
            reason=reason,
        )

        if trade_result:
            self._close_count += 1
            if self._journal:
                self._journal.record_close(symbol, trade_result)
            self.emit_event("position.closed", trade_result.to_dict())
            logger.info(
                "平仓成功: %s reason=%s pnl=%.2f (%.2f%%)",
                symbol,
                reason.value,
                trade_result.pnl,
                trade_result.pnl_pct * 100,
            )

    def _execute_partial_close(
        self,
        symbol: str,
        price: float,
        exit_result: ExitCheckResult,
    ) -> None:
        """执行部分平仓"""
        ratio = exit_result.partial_close_ratio
        if not ratio or self._manager is None:
            return

        result = self._manager.close_position(
            symbol=symbol,
            exit_price=price,
            reason=ExitReason.PARTIAL_PROFIT,
            partial_ratio=ratio,
        )

        if result:
            pos = self._manager.get_position(symbol)
            self.emit_event(
                "position.partial_close",
                {
                    **result.to_dict(),
                    "remaining_size": (pos.size if pos else 0),
                },
            )
            logger.info(
                "部分平仓: %s ratio=%.0f%% pnl=%.2f",
                symbol,
                ratio * 100,
                result.pnl,
            )

    def _check_pending_exits(self) -> None:
        """定期重试失败的平仓请求"""
        if not self._pending_exits or self._manager is None:
            return

        remaining: List[Dict[str, Any]] = []
        for pending in self._pending_exits:
            symbol: str = pending["symbol"]
            last = self._last_prices.get(symbol)
            exit_price: float = last if last is not None else pending["price"]
            exit_result = pending["exit_result"]

            position = self._manager.get_position(symbol)
            if not position:
                # 仓位已不存在，丢弃
                continue

            logger.info("重试待处理平仓: %s", symbol)
            old_pending_len = len(self._pending_exits)
            self._execute_exit(symbol, exit_price, exit_result)
            # 若 _execute_exit 再次失败会 append 到 _pending_exits
            if len(self._pending_exits) > old_pending_len:
                remaining.append(self._pending_exits.pop())

        self._pending_exits = remaining

    def _on_price_update(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理价格更新事件"""
        try:
            symbol = data.get("symbol")
            price = data.get("price")

            if not symbol or not price:
                return

            # 记录最后已知价格，用于 shutdown 平仓
            self._last_prices[symbol] = price

            if self._manager is None:
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

            # 顺便检查待重试平仓
            self._check_pending_exits()

        except Exception as e:
            self._last_error = str(e)
            logger.exception("处理价格更新失败: %s", e)

    def _on_shutdown(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理系统关闭事件 — 使用最后已知市场价平仓"""
        logger.info("系统关闭，平仓所有持仓...")

        if self._manager:
            positions = self._manager.get_all_positions()
            # 使用最后已知市场价，而非入场价（避免零PnL假象）
            exit_prices: Dict[str, float] = {}
            for symbol, pos in positions.items():
                market_price = self._last_prices.get(symbol)
                if market_price is not None:
                    exit_prices[symbol] = market_price
                else:
                    logger.warning(
                        "shutdown: %s 无最后市场价，使用入场价兜底",
                        symbol,
                    )
                    exit_prices[symbol] = pos.entry_price
            results = self._manager.force_close_all(exit_prices)
            logger.info("已平仓 %d 个持仓", len(results))

    # ================================================================
    # 熔断器事件处理
    # ================================================================

    def _on_circuit_breaker_tripped(
        self, event_name: str, data: Dict[str, Any]
    ) -> None:
        """处理熔断器触发事件 — 停止开仓"""
        reason = data.get("reason", "unknown")
        self._circuit_breaker_active = True
        logger.warning("熔断器触发，仓位管理停止开仓: %s", reason)

    def _on_circuit_breaker_recovered(
        self, event_name: str, data: Dict[str, Any]
    ) -> None:
        """处理熔断器恢复事件 — 恢复开仓"""
        self._circuit_breaker_active = False
        logger.info("熔断器恢复，仓位管理恢复开仓")

    # ================================================================
    # 健康检查
    # ================================================================

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
            message=(f"PositionManager running, {open_positions} open positions"),
            details={
                "open_positions": open_positions,
                "total_trades": stats["total_trades"],
                "win_rate": stats["win_rate"],
                "total_pnl": stats["total_pnl"],
                "open_count": self._open_count,
                "close_count": self._close_count,
                "executor_connected": (self._executor is not None),
                "journal_active": (self._journal is not None),
            },
        )

    # ================================================================
    # 公共 API（保持向后兼容）
    # ================================================================

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

    def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取交易历史"""
        if not self._manager:
            return []

        history = (
            self._manager.trade_history[-limit:]
            if hasattr(self._manager, "trade_history")
            else []
        )
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

    def get_closed_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取已平仓交易记录

        API /api/trades 端点使用此方法。
        代理到 get_trade_history()。

        Args:
            limit: 返回记录数量上限

        Returns:
            交易记录字典列表
        """
        return self.get_trade_history(limit=limit)
