"""
资金守卫模块 - 亏损限制 + 强平监控 + 连续亏损保护

职责：
1. [C3] 日/周/回撤亏损限制执行
2. [C4] 强平价格监控与预警
3. [M8] 连续亏损保护（仓位缩放）
"""

import logging
from datetime import date
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CapitalGuard:
    """资金守卫 — 交易资金安全的最后防线

    设计原则：
    1. 独立模块，不依赖其他插件
    2. 通过 record_trade_result 被动接收交易结果
    3. 通过 is_trading_allowed / get_position_scale 被查询
    4. 日/周亏损自动按日期重置
    5. 限制触发时通过回调发布 circuit_breaker_tripped 事件
    """

    def __init__(
        self,
        config: Dict[str, Any],
        event_callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        """初始化资金守卫

        Args:
            config: risk_management 配置节，包含：
                capital_management.daily_loss_limit (0.05)
                capital_management.weekly_loss_limit (0.1)
                capital_management.max_drawdown_limit (0.2)
                liquidation_buffer (0.1)
            event_callback: 事件发布回调函数，签名 (event_name, data)
        """
        cap = config.get("capital_management", {})
        self._daily_limit: float = cap.get("daily_loss_limit", 0.05)
        self._weekly_limit: float = cap.get("weekly_loss_limit", 0.1)
        self._max_drawdown: float = cap.get("max_drawdown_limit", 0.2)
        self._liq_buffer: float = config.get("liquidation_buffer", 0.1)
        # 连续亏损保护
        self._max_consecutive: int = config.get("max_consecutive_losses", 5)

        # 事件回调
        self._event_callback = event_callback

        # 运行时状态
        self._daily_loss: float = 0.0
        self._weekly_loss: float = 0.0
        self._peak_balance: float = 0.0
        self._current_balance: float = 0.0
        self._consecutive_losses: int = 0
        self._total_trades: int = 0

        # 日期追踪（用于自动重置）
        self._current_date: date = date.today()
        self._current_week: int = date.today().isocalendar()[1]

        # 停止交易标志
        self._halted: bool = False
        self._halt_reason: str = ""

        logger.info(
            "资金守卫初始化: 日限%.1f%% 周限%.1f%% 回撤限%.1f%% 强平缓冲%.1f%%",
            self._daily_limit * 100,
            self._weekly_limit * 100,
            self._max_drawdown * 100,
            self._liq_buffer * 100,
        )

    def record_trade_result(self, pnl: float, balance: float) -> None:
        """记录交易结果，更新所有计数器

        Args:
            pnl: 本笔盈亏金额（正=盈利，负=亏损）
            balance: 交易后账户余额
        """
        self._check_date_reset()
        self._total_trades += 1
        self._current_balance = balance

        # 更新峰值余额
        if balance > self._peak_balance:
            self._peak_balance = balance
        if self._peak_balance == 0.0:
            self._peak_balance = balance

        # 累计亏损（仅记录亏损）
        if pnl < 0 and self._peak_balance > 0:
            loss_pct = abs(pnl) / self._peak_balance
            self._daily_loss += loss_pct
            self._weekly_loss += loss_pct
            self._consecutive_losses += 1
        elif pnl > 0:
            self._consecutive_losses = 0

        # 检查是否触发停止
        self._evaluate_limits()

    # ----------------------------------------------------------
    # 查询接口
    # ----------------------------------------------------------

    def is_trading_allowed(self) -> bool:
        """检查是否允许继续交易

        Returns:
            True=允许交易，False=已触发限制
        """
        self._check_date_reset()
        return not self._halted

    def get_status(self) -> Dict[str, Any]:
        """获取资金守卫当前状态快照

        Returns:
            包含所有限制指标的字典
        """
        self._check_date_reset()
        drawdown = 0.0
        if self._peak_balance > 0:
            drawdown = (self._peak_balance - self._current_balance) / self._peak_balance
            drawdown = max(0.0, drawdown)

        return {
            "trading_allowed": not self._halted,
            "halt_reason": self._halt_reason,
            "daily_loss_pct": round(self._daily_loss, 6),
            "daily_limit": self._daily_limit,
            "weekly_loss_pct": round(self._weekly_loss, 6),
            "weekly_limit": self._weekly_limit,
            "drawdown_pct": round(drawdown, 6),
            "max_drawdown": self._max_drawdown,
            "consecutive_losses": self._consecutive_losses,
            "max_consecutive": self._max_consecutive,
            "position_scale": self.get_position_scale(),
            "total_trades": self._total_trades,
            "peak_balance": self._peak_balance,
            "current_balance": self._current_balance,
        }

    # ----------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------

    def _check_date_reset(self) -> None:
        """检查日期变化，自动重置日/周累计"""
        today = date.today()
        if today != self._current_date:
            logger.info(
                "日期变更 %s -> %s, 重置日亏损计数",
                self._current_date,
                today,
            )
            self._daily_loss = 0.0
            self._current_date = today

            # 周重置
            current_week = today.isocalendar()[1]
            if current_week != self._current_week:
                logger.info(
                    "周变更 W%d -> W%d, 重置周亏损计数",
                    self._current_week,
                    current_week,
                )
                self._weekly_loss = 0.0
                self._current_week = current_week

            # 日/周重置后重新评估是否解除停止
            if self._halted:
                self._halted = False
                self._halt_reason = ""
                self._evaluate_limits()

    def _evaluate_limits(self) -> None:
        """评估所有限制条件，决定是否停止交易"""
        was_halted = self._halted

        # 日亏损限制
        if self._daily_loss >= self._daily_limit:
            self._halted = True
            self._halt_reason = (
                f"日亏损 {self._daily_loss:.2%} >= 限制 {self._daily_limit:.2%}"
            )
            logger.warning("资金守卫: %s", self._halt_reason)
            if not was_halted:
                self._emit_circuit_breaker_event("daily_loss_limit")
            return

        # 周亏损限制
        if self._weekly_loss >= self._weekly_limit:
            self._halted = True
            self._halt_reason = (
                f"周亏损 {self._weekly_loss:.2%} >= 限制 {self._weekly_limit:.2%}"
            )
            logger.warning("资金守卫: %s", self._halt_reason)
            if not was_halted:
                self._emit_circuit_breaker_event("weekly_loss_limit")
            return

        # 最大回撤限制
        if self._peak_balance > 0:
            drawdown = (self._peak_balance - self._current_balance) / self._peak_balance
            if drawdown >= self._max_drawdown:
                self._halted = True
                self._halt_reason = (
                    f"回撤 {drawdown:.2%} >= 限制 {self._max_drawdown:.2%}"
                )
                logger.warning("资金守卫: %s", self._halt_reason)
                if not was_halted:
                    self._emit_circuit_breaker_event("max_drawdown_limit")
                return

        # 连续亏损极端情况（2倍阈值 → 停止交易）
        if self._consecutive_losses >= (2 * self._max_consecutive):
            self._halted = True
            self._halt_reason = (
                f"连续亏损 {self._consecutive_losses} 次 >= 2×{self._max_consecutive}"
            )
            logger.warning("资金守卫: %s", self._halt_reason)
            if not was_halted:
                self._emit_circuit_breaker_event("consecutive_loss_limit")
            return

    def _emit_circuit_breaker_event(self, trigger: str) -> None:
        """发布熔断事件

        Args:
            trigger: 触发原因标识
        """
        if self._event_callback is not None:
            self._event_callback(
                "risk_management.circuit_breaker_tripped",
                {
                    "source": "capital_guard",
                    "trigger": trigger,
                    "reason": self._halt_reason,
                    "daily_loss_pct": round(self._daily_loss, 6),
                    "weekly_loss_pct": round(self._weekly_loss, 6),
                },
            )

    # ----------------------------------------------------------
    # [C4] 强平价格监控
    # ----------------------------------------------------------

    def check_liquidation_risk(
        self,
        position: Dict[str, Any],
        current_price: float,
    ) -> Dict[str, Any]:
        """检查仓位强平风险

        逐仓模式下的强平价格计算：
        - 多头: liq = entry × (1 - 1/lev × (1 - buffer))
        - 空头: liq = entry × (1 + 1/lev × (1 - buffer))

        行动判定：
        - price beyond liquidation → action="force_close"
        - distance_pct < buffer (10%) → action="warning"
        - otherwise → action="safe"

        Args:
            position: 仓位字典，需包含：
                entry_price, leverage, side
            current_price: 当前市场价格

        Returns:
            {action, at_risk, liq_price, distance_pct}
            action: "safe" | "warning" | "force_close"
        """
        entry = position.get("entry_price", 0.0)
        leverage = position.get("leverage", 1.0)
        side = position.get("side", "long").lower()

        if entry <= 0 or leverage <= 0:
            return {
                "action": "safe",
                "at_risk": False,
                "liq_price": 0.0,
                "distance_pct": 1.0,
            }

        margin_ratio = 1.0 / leverage
        buffer_adj = 1.0 - self._liq_buffer

        if side == "long":
            liq_price = entry * (1.0 - margin_ratio * buffer_adj)
            # 多头：current_price <= liq_price → 已触及强平
            beyond_liquidation = current_price <= liq_price
            distance_pct = (
                (current_price - liq_price) / current_price
                if current_price > 0
                else 0.0
            )
        else:
            liq_price = entry * (1.0 + margin_ratio * buffer_adj)
            # 空头：current_price >= liq_price → 已触及强平
            beyond_liquidation = current_price >= liq_price
            distance_pct = (
                (liq_price - current_price) / current_price
                if current_price > 0
                else 0.0
            )

        # 判定行动
        if beyond_liquidation:
            action = "force_close"
            at_risk = True
            logger.error(
                "强平触发: %s仓 entry=%.2f liq=%.2f price=%.2f → 强制平仓",
                side,
                entry,
                liq_price,
                current_price,
            )
        elif distance_pct < self._liq_buffer:
            action = "warning"
            at_risk = True
            logger.warning(
                "强平风险预警: %s仓 entry=%.2f liq=%.2f 距离=%.2f%%",
                side,
                entry,
                liq_price,
                distance_pct * 100,
            )
        else:
            action = "safe"
            at_risk = False

        return {
            "action": action,
            "at_risk": at_risk,
            "liq_price": round(liq_price, 8),
            "distance_pct": round(distance_pct, 6),
        }

    # ----------------------------------------------------------
    # [M8] 连续亏损保护
    # ----------------------------------------------------------

    def get_position_scale(self) -> float:
        """根据连续亏损次数返回仓位缩放系数

        规则：
        - 连续亏损 < max: scale = 1.0
        - max <= 连续亏损 < 2×max: scale = 0.5
        - 连续亏损 >= 2×max: scale = 0.0（停止）
        """
        if self._consecutive_losses >= (2 * self._max_consecutive):
            return 0.0
        if self._consecutive_losses >= self._max_consecutive:
            return 0.5
        return 1.0

    def reset_daily(self) -> None:
        """手动重置日亏损计数器"""
        self._daily_loss = 0.0
        # 如果停止原因是日亏损限制，重新评估
        if self._halted:
            self._halted = False
            self._halt_reason = ""
            self._evaluate_limits()
        logger.info("资金守卫: 日亏损计数已重置")

    def reset_weekly(self) -> None:
        """手动重置周亏损计数器"""
        self._weekly_loss = 0.0
        # 如果停止原因是周亏损限制，重新评估
        if self._halted:
            self._halted = False
            self._halt_reason = ""
            self._evaluate_limits()
        logger.info("资金守卫: 周亏损计数已重置")

    def reset(self) -> None:
        """手动重置所有状态（测试或紧急恢复）"""
        self._daily_loss = 0.0
        self._weekly_loss = 0.0
        self._consecutive_losses = 0
        self._halted = False
        self._halt_reason = ""
        self._total_trades = 0
        logger.info("资金守卫已手动重置")
