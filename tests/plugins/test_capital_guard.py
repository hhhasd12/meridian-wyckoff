"""
资金守卫模块测试 - 强平价格监控 + 亏损限制执行 + 事件发布

测试覆盖：
- 多头/空头强平价格计算 (check_liquidation_risk)
- 日亏损 >5% 阻止交易
- 周亏损 >10% 阻止交易
- 回撤 >20% 阻止交易
- 正常交易（限制内）
- 日/周重置恢复交易
- circuit_breaker_tripped 事件发布
"""

import pytest
from unittest.mock import MagicMock

from src.plugins.risk_management.capital_guard import CapitalGuard


class TestLiquidationPriceCalculation:
    """测试强平价格计算公式"""

    def setup_method(self) -> None:
        """初始化资金守卫，使用默认配置"""
        self.guard = CapitalGuard({"capital_management": {}, "liquidation_buffer": 0.1})

    # -------------------------------------------------------
    # 多头（Long）测试
    # -------------------------------------------------------

    def test_long_5x_liq_price(self) -> None:
        """5x杠杆多头: liq_price = 100 * (1 - 0.2*0.9) = 82"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=95.0,
        )
        assert abs(result["liq_price"] - 82.0) < 0.01

    def test_long_5x_warning(self) -> None:
        """5x多头 entry=100, price=83 → 距离liq(82)仅1.2% → warning"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=83.0,
        )
        assert result["action"] == "warning"
        assert result["at_risk"] is True
        assert result["distance_pct"] < 0.1  # 在buffer范围内

    def test_long_5x_force_close(self) -> None:
        """5x多头 entry=100, price=80 → 低于liq(82) → force_close"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=80.0,
        )
        assert result["action"] == "force_close"
        assert result["at_risk"] is True

    def test_long_5x_safe(self) -> None:
        """5x多头 entry=100, price=95 → 距离liq(82)约13.7% → safe"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=95.0,
        )
        assert result["action"] == "safe"
        assert result["at_risk"] is False
        assert result["distance_pct"] > 0.1

    def test_long_exactly_at_liq_price(self) -> None:
        """多头价格恰好等于强平价 → force_close"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=82.0,
        )
        assert result["action"] == "force_close"
        assert result["at_risk"] is True

    # -------------------------------------------------------
    # 空头（Short）测试
    # -------------------------------------------------------

    def test_short_5x_liq_price(self) -> None:
        """5x杠杆空头: liq_price = 100 * (1 + 0.2*0.9) = 118"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "short"},
            current_price=105.0,
        )
        assert abs(result["liq_price"] - 118.0) < 0.01

    def test_short_5x_warning(self) -> None:
        """5x空头 entry=100, price=117 → 距离liq(118)仅0.86% → warning"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "short"},
            current_price=117.0,
        )
        assert result["action"] == "warning"
        assert result["at_risk"] is True

    def test_short_5x_force_close(self) -> None:
        """5x空头 entry=100, price=120 → 高于liq(118) → force_close"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "short"},
            current_price=120.0,
        )
        assert result["action"] == "force_close"
        assert result["at_risk"] is True

    def test_short_5x_safe(self) -> None:
        """5x空头 entry=100, price=105 → 距离liq(118)约11% → safe"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "short"},
            current_price=105.0,
        )
        assert result["action"] == "safe"
        assert result["at_risk"] is False

    def test_short_exactly_at_liq_price(self) -> None:
        """空头价格恰好等于强平价 → force_close"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "short"},
            current_price=118.0,
        )
        assert result["action"] == "force_close"
        assert result["at_risk"] is True

    # -------------------------------------------------------
    # 低杠杆 / 无杠杆
    # -------------------------------------------------------

    def test_leverage_1x_safe(self) -> None:
        """1x杠杆 → liq_price=10, 距离极远 → safe"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 1.0, "side": "long"},
            current_price=90.0,
        )
        # liq_price = 100*(1-1.0*0.9) = 10
        assert abs(result["liq_price"] - 10.0) < 0.01
        assert result["action"] == "safe"
        assert result["at_risk"] is False
        assert result["distance_pct"] > 0.5  # 远超buffer

    def test_leverage_2x_long(self) -> None:
        """2x杠杆多头: liq=100*(1-0.5*0.9)=55, price=75 → safe"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 2.0, "side": "long"},
            current_price=75.0,
        )
        assert abs(result["liq_price"] - 55.0) < 0.01
        # distance = (75-55)/75 ≈ 0.267 > 0.1 → safe
        assert result["action"] == "safe"

    def test_leverage_2x_long_warning_boundary(self) -> None:
        """2x杠杆多头 liq=55, price=60 → distance=8.3% < 10% → warning"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 2.0, "side": "long"},
            current_price=60.0,
        )
        assert abs(result["liq_price"] - 55.0) < 0.01
        assert result["action"] == "warning"
        assert result["at_risk"] is True

    # -------------------------------------------------------
    # 边界条件 / 无效输入
    # -------------------------------------------------------

    def test_invalid_entry_price_zero(self) -> None:
        """entry_price=0 → safe（无效仓位）"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 0.0, "leverage": 5.0, "side": "long"},
            current_price=100.0,
        )
        assert result["action"] == "safe"
        assert result["at_risk"] is False

    def test_invalid_leverage_zero(self) -> None:
        """leverage=0 → safe（无效杠杆）"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 0.0, "side": "long"},
            current_price=100.0,
        )
        assert result["action"] == "safe"
        assert result["at_risk"] is False

    def test_negative_entry_price(self) -> None:
        """entry_price<0 → safe"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": -100.0, "leverage": 5.0, "side": "long"},
            current_price=100.0,
        )
        assert result["action"] == "safe"

    def test_missing_fields_defaults(self) -> None:
        """缺少字段 → 使用默认值（entry=0 → safe）"""
        result = self.guard.check_liquidation_risk({}, current_price=100.0)
        assert result["action"] == "safe"

    def test_side_case_insensitive(self) -> None:
        """side 字段大小写不敏感"""
        result_upper = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "LONG"},
            current_price=95.0,
        )
        result_lower = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=95.0,
        )
        assert result_upper["liq_price"] == result_lower["liq_price"]
        assert result_upper["action"] == result_lower["action"]


class TestLiquidationWithCustomBuffer:
    """测试不同 liquidation_buffer 配置"""

    def test_tighter_buffer_5pct(self) -> None:
        """buffer=5%: 更紧的预警距离"""
        guard = CapitalGuard({"capital_management": {}, "liquidation_buffer": 0.05})
        # 5x long entry=100: liq = 100*(1-0.2*0.95) = 100*0.81 = 81
        result = guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=83.0,
        )
        assert abs(result["liq_price"] - 81.0) < 0.01
        # distance = (83-81)/83 ≈ 0.024 < 0.05 → warning
        assert result["action"] == "warning"

    def test_zero_buffer(self) -> None:
        """buffer=0: 无缓冲（仅到强平价才force_close）"""
        guard = CapitalGuard({"capital_management": {}, "liquidation_buffer": 0.0})
        # 5x long entry=100: liq = 100*(1-0.2*1.0) = 80
        result = guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=81.0,
        )
        assert abs(result["liq_price"] - 80.0) < 0.01
        # buffer=0, distance=(81-80)/81≈0.0123 > 0 → not < 0 → safe
        assert result["action"] == "safe"


class TestLiquidationReturnFields:
    """测试返回值字段完整性"""

    def setup_method(self) -> None:
        self.guard = CapitalGuard({"capital_management": {}, "liquidation_buffer": 0.1})

    def test_return_has_all_fields(self) -> None:
        """返回值应包含 action, at_risk, liq_price, distance_pct"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=95.0,
        )
        assert "action" in result
        assert "at_risk" in result
        assert "liq_price" in result
        assert "distance_pct" in result

    def test_action_values_are_valid(self) -> None:
        """action 只能是 safe/warning/force_close"""
        for price in [95.0, 83.0, 80.0]:
            result = self.guard.check_liquidation_risk(
                {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
                current_price=price,
            )
            assert result["action"] in ("safe", "warning", "force_close")

    def test_distance_pct_is_positive_when_safe(self) -> None:
        """safe 时 distance_pct > buffer"""
        result = self.guard.check_liquidation_risk(
            {"entry_price": 100.0, "leverage": 5.0, "side": "long"},
            current_price=95.0,
        )
        assert result["distance_pct"] > 0
        assert result["action"] == "safe"


# ==================================================================
# [C3] 亏损限制执行层测试
# ==================================================================


def _make_config(
    daily: float = 0.05,
    weekly: float = 0.1,
    drawdown: float = 0.2,
) -> dict:
    """构建测试配置"""
    return {
        "capital_management": {
            "daily_loss_limit": daily,
            "weekly_loss_limit": weekly,
            "max_drawdown_limit": drawdown,
        },
        "liquidation_buffer": 0.1,
        "max_consecutive_losses": 5,
    }


class TestCapitalGuardNormalOperation:
    """正常操作（限制内）"""

    def setup_method(self) -> None:
        self.guard = CapitalGuard(_make_config())
        self.guard.record_trade_result(0.0, 10000.0)

    def test_initial_state_allows_trading(self) -> None:
        """初始状态允许交易"""
        assert self.guard.is_trading_allowed() is True

    def test_small_loss_allows_trading(self) -> None:
        """小额亏损不触发限制"""
        self.guard.record_trade_result(-100.0, 9900.0)
        assert self.guard.is_trading_allowed() is True

    def test_profit_resets_consecutive_losses(self) -> None:
        """盈利重置连续亏损计数"""
        self.guard.record_trade_result(-100.0, 9900.0)
        assert self.guard._consecutive_losses == 1
        self.guard.record_trade_result(200.0, 10100.0)
        assert self.guard._consecutive_losses == 0

    def test_get_status_returns_correct_fields(self) -> None:
        """get_status 返回所有必需字段"""
        status = self.guard.get_status()
        required_keys = [
            "trading_allowed",
            "halt_reason",
            "daily_loss_pct",
            "daily_limit",
            "weekly_loss_pct",
            "weekly_limit",
            "drawdown_pct",
            "max_drawdown",
            "consecutive_losses",
            "max_consecutive",
            "position_scale",
            "total_trades",
            "peak_balance",
            "current_balance",
        ]
        for key in required_keys:
            assert key in status, f"缺少字段: {key}"

    def test_zero_pnl_no_change(self) -> None:
        """零盈亏不影响计数"""
        self.guard.record_trade_result(0.0, 10000.0)
        assert self.guard._daily_loss == 0.0
        assert self.guard._consecutive_losses == 0


class TestDailyLossLimit:
    """日亏损限制（>=5% 阻止交易）"""

    def setup_method(self) -> None:
        self.callback = MagicMock()
        self.guard = CapitalGuard(
            _make_config(daily=0.05),
            event_callback=self.callback,
        )
        self.guard.record_trade_result(0.0, 10000.0)

    def test_daily_loss_at_limit_blocks_trading(self) -> None:
        """日亏损恰好达到5%阻止交易"""
        self.guard.record_trade_result(-500.0, 9500.0)
        assert self.guard.is_trading_allowed() is False

    def test_daily_loss_exceeds_limit_blocks_trading(self) -> None:
        """日亏损超过5%阻止交易"""
        self.guard.record_trade_result(-600.0, 9400.0)
        assert self.guard.is_trading_allowed() is False

    def test_daily_loss_below_limit_allows_trading(self) -> None:
        """日亏损低于5%允许交易"""
        self.guard.record_trade_result(-400.0, 9600.0)
        assert self.guard.is_trading_allowed() is True

    def test_cumulative_daily_loss(self) -> None:
        """累计日亏损达到限制"""
        self.guard.record_trade_result(-300.0, 9700.0)
        assert self.guard.is_trading_allowed() is True
        self.guard.record_trade_result(-300.0, 9400.0)
        assert self.guard.is_trading_allowed() is False

    def test_daily_loss_emits_event(self) -> None:
        """日亏损触发发布 circuit_breaker_tripped 事件"""
        self.guard.record_trade_result(-500.0, 9500.0)
        self.callback.assert_called_once()
        args = self.callback.call_args
        assert args[0][0] == "risk_management.circuit_breaker_tripped"
        assert args[0][1]["source"] == "capital_guard"
        assert args[0][1]["trigger"] == "daily_loss_limit"

    def test_daily_loss_event_only_once(self) -> None:
        """已停止状态下，后续亏损不重复发布事件"""
        self.guard.record_trade_result(-500.0, 9500.0)
        self.guard.record_trade_result(-100.0, 9400.0)
        assert self.callback.call_count == 1


class TestWeeklyLossLimit:
    """周亏损限制（>=10% 阻止交易）"""

    def setup_method(self) -> None:
        self.callback = MagicMock()
        self.guard = CapitalGuard(
            _make_config(daily=1.0, weekly=0.1),
            event_callback=self.callback,
        )
        self.guard.record_trade_result(0.0, 10000.0)

    def test_weekly_loss_at_limit_blocks_trading(self) -> None:
        """周亏损恰好达到10%阻止交易"""
        self.guard.record_trade_result(-1000.0, 9000.0)
        assert self.guard.is_trading_allowed() is False

    def test_weekly_loss_exceeds_limit(self) -> None:
        """周亏损超过10%阻止交易"""
        self.guard.record_trade_result(-1200.0, 8800.0)
        assert self.guard.is_trading_allowed() is False

    def test_weekly_loss_emits_event(self) -> None:
        """周亏损触发事件"""
        self.guard.record_trade_result(-1000.0, 9000.0)
        self.callback.assert_called_once()
        args = self.callback.call_args
        assert args[0][1]["trigger"] == "weekly_loss_limit"


class TestDrawdownLimit:
    """回撤限制（>=20% 阻止交易）"""

    def setup_method(self) -> None:
        self.callback = MagicMock()
        self.guard = CapitalGuard(
            _make_config(daily=1.0, weekly=1.0, drawdown=0.2),
            event_callback=self.callback,
        )
        self.guard.record_trade_result(0.0, 10000.0)

    def test_drawdown_at_limit_blocks_trading(self) -> None:
        """回撤恰好达到20%阻止交易"""
        self.guard.record_trade_result(-2000.0, 8000.0)
        assert self.guard.is_trading_allowed() is False

    def test_drawdown_exceeds_limit(self) -> None:
        """回撤超过20%阻止交易"""
        self.guard.record_trade_result(-2500.0, 7500.0)
        assert self.guard.is_trading_allowed() is False

    def test_drawdown_below_limit_allows(self) -> None:
        """回撤低于20%允许交易"""
        self.guard.record_trade_result(-1500.0, 8500.0)
        assert self.guard.is_trading_allowed() is True

    def test_drawdown_emits_event(self) -> None:
        """回撤触发事件"""
        self.guard.record_trade_result(-2000.0, 8000.0)
        self.callback.assert_called_once()
        args = self.callback.call_args
        assert args[0][1]["trigger"] == "max_drawdown_limit"

    def test_drawdown_after_profit_peak(self) -> None:
        """盈利后新峰值再回撤"""
        self.guard.record_trade_result(2000.0, 12000.0)
        assert self.guard._peak_balance == 12000.0
        self.guard.record_trade_result(-2400.0, 9600.0)
        assert self.guard.is_trading_allowed() is False


class TestPeriodResets:
    """日/周重置"""

    def setup_method(self) -> None:
        self.guard = CapitalGuard(_make_config())
        self.guard.record_trade_result(0.0, 10000.0)

    def test_reset_daily_restores_trading(self) -> None:
        """reset_daily 恢复交易"""
        self.guard.record_trade_result(-500.0, 9500.0)
        assert self.guard.is_trading_allowed() is False
        self.guard.reset_daily()
        assert self.guard._daily_loss == 0.0
        assert self.guard.is_trading_allowed() is True

    def test_reset_weekly_restores_trading(self) -> None:
        """reset_weekly 恢复交易"""
        guard = CapitalGuard(_make_config(daily=1.0, weekly=0.1))
        guard.record_trade_result(0.0, 10000.0)
        guard.record_trade_result(-1000.0, 9000.0)
        assert guard.is_trading_allowed() is False
        guard.reset_weekly()
        assert guard._weekly_loss == 0.0
        assert guard.is_trading_allowed() is True

    def test_reset_all_restores_everything(self) -> None:
        """reset() 重置所有状态"""
        self.guard.record_trade_result(-500.0, 9500.0)
        assert self.guard.is_trading_allowed() is False
        self.guard.reset()
        assert self.guard._daily_loss == 0.0
        assert self.guard._weekly_loss == 0.0
        assert self.guard._consecutive_losses == 0
        assert self.guard.is_trading_allowed() is True

    def test_reset_daily_does_not_affect_weekly(self) -> None:
        """reset_daily 不影响周累计"""
        self.guard.record_trade_result(-300.0, 9700.0)
        weekly_before = self.guard._weekly_loss
        self.guard.reset_daily()
        assert self.guard._daily_loss == 0.0
        assert self.guard._weekly_loss == weekly_before


class TestNoCallbackSafe:
    """无回调时不报错"""

    def test_no_callback_no_error(self) -> None:
        """event_callback=None 时触发限制不报错"""
        guard = CapitalGuard(_make_config(), event_callback=None)
        guard.record_trade_result(0.0, 10000.0)
        guard.record_trade_result(-600.0, 9400.0)
        assert guard.is_trading_allowed() is False


class TestPositionScaleWithLimits:
    """仓位缩放系数与限制联动"""

    def setup_method(self) -> None:
        self.guard = CapitalGuard(_make_config(daily=1.0, weekly=1.0, drawdown=1.0))
        self.guard.record_trade_result(0.0, 100000.0)

    def test_normal_scale(self) -> None:
        """正常时缩放 1.0"""
        assert self.guard.get_position_scale() == 1.0

    def test_half_scale_after_consecutive_losses(self) -> None:
        """连续亏损 >= max 时缩放 0.5"""
        for _ in range(5):
            self.guard.record_trade_result(-10.0, 99990.0)
        assert self.guard.get_position_scale() == 0.5

    def test_zero_scale_after_extreme_losses(self) -> None:
        """连续亏损 >= 2*max 时缩放 0.0"""
        for _ in range(10):
            self.guard.record_trade_result(-10.0, 99990.0)
        assert self.guard.get_position_scale() == 0.0

    def test_10_consecutive_losses_blocks_trading(self) -> None:
        """10次连续亏损 → is_trading_allowed() = False"""
        for _ in range(10):
            self.guard.record_trade_result(-10.0, 99990.0)
        assert self.guard.is_trading_allowed() is False
        assert "连续亏损" in self.guard._halt_reason

    def test_win_after_5_losses_resets_scale(self) -> None:
        """5次连续亏损后盈利 → 缩放恢复 1.0"""
        for _ in range(5):
            self.guard.record_trade_result(-10.0, 99990.0)
        assert self.guard.get_position_scale() == 0.5
        # 一次盈利重置连续亏损计数
        self.guard.record_trade_result(50.0, 100040.0)
        assert self.guard.get_position_scale() == 1.0
        assert self.guard._consecutive_losses == 0

    def test_mixed_results_reset_counter(self) -> None:
        """交替盈亏 → 连续亏损计数始终被重置"""
        # loss, loss, win, loss, loss → consecutive = 2, not 4
        self.guard.record_trade_result(-10.0, 99990.0)
        self.guard.record_trade_result(-10.0, 99980.0)
        assert self.guard._consecutive_losses == 2
        self.guard.record_trade_result(20.0, 100000.0)
        assert self.guard._consecutive_losses == 0
        self.guard.record_trade_result(-10.0, 99990.0)
        self.guard.record_trade_result(-10.0, 99980.0)
        assert self.guard._consecutive_losses == 2
        assert self.guard.get_position_scale() == 1.0
        assert self.guard.is_trading_allowed() is True

    def test_consecutive_loss_emits_circuit_breaker_event(self) -> None:
        """10次连续亏损触发 circuit_breaker 事件"""
        callback = MagicMock()
        guard = CapitalGuard(
            _make_config(daily=1.0, weekly=1.0, drawdown=1.0),
            event_callback=callback,
        )
        guard.record_trade_result(0.0, 100000.0)
        for _ in range(10):
            guard.record_trade_result(-10.0, 99990.0)
        callback.assert_called_once()
        args = callback.call_args
        assert args[0][0] == "risk_management.circuit_breaker_tripped"
        assert args[0][1]["trigger"] == "consecutive_loss_limit"

    def test_6_losses_half_scale_then_win_restores(self) -> None:
        """6次亏损后缩放0.5，盈利后立刻恢复1.0"""
        for _ in range(6):
            self.guard.record_trade_result(-10.0, 99990.0)
        assert self.guard.get_position_scale() == 0.5
        assert self.guard._consecutive_losses == 6
        self.guard.record_trade_result(100.0, 100090.0)
        assert self.guard.get_position_scale() == 1.0


class TestPluginIntegration:
    """验证 CapitalGuard 在 RiskManagementPlugin 中的集成"""

    def test_capital_guard_created_with_callback(self) -> None:
        """plugin.on_load 创建 CapitalGuard 并传入 emit_event"""
        from src.plugins.risk_management.plugin import RiskManagementPlugin

        plugin = RiskManagementPlugin()
        plugin._config = _make_config()
        plugin.emit_event = MagicMock()
        plugin.on_load()

        assert plugin._capital_guard is not None
        assert plugin._capital_guard._event_callback is plugin.emit_event

    def test_is_trading_allowed_checks_capital_guard(self) -> None:
        """plugin.is_trading_allowed 同时检查 circuit_breaker 和 capital_guard"""
        from src.plugins.risk_management.plugin import RiskManagementPlugin

        plugin = RiskManagementPlugin()
        plugin._config = _make_config()
        plugin.emit_event = MagicMock()
        plugin.on_load()

        # 初始状态允许
        assert plugin.is_trading_allowed() is True

        # 触发资金限制
        assert plugin._capital_guard is not None
        plugin._capital_guard.record_trade_result(0.0, 10000.0)
        plugin._capital_guard.record_trade_result(-600.0, 9400.0)
        assert plugin.is_trading_allowed() is False
