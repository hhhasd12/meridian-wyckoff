"""测试 src/kernel/types.py 中的类型定义"""

import pytest

from src.kernel.types import (
    ConfigDict,
    EventPriority,
    HealthCheckResult,
    HealthStatus,
    ManifestValidationError,
    PluginConfigError,
    PluginDependencyError,
    PluginError,
    PluginInfo,
    PluginLoadError,
    PluginState,
    PluginType,
)


class TestPluginState:
    """测试 PluginState 枚举"""

    def test_enum_values(self) -> None:
        assert PluginState.UNLOADED.value == "UNLOADED"
        assert PluginState.LOADING.value == "LOADING"
        assert PluginState.ACTIVE.value == "ACTIVE"
        assert PluginState.UNLOADING.value == "UNLOADING"
        assert PluginState.ERROR.value == "ERROR"

    def test_all_states_exist(self) -> None:
        states = [s.value for s in PluginState]
        assert len(states) == 5


class TestPluginType:
    """测试 PluginType 枚举"""

    def test_enum_values(self) -> None:
        assert PluginType.CORE.value == "core"
        assert PluginType.OPTIONAL.value == "optional"


class TestEventPriority:
    """测试 EventPriority 枚举"""

    def test_priority_ordering(self) -> None:
        assert EventPriority.HIGH.value < EventPriority.NORMAL.value
        assert EventPriority.NORMAL.value < EventPriority.LOW.value


class TestHealthStatus:
    """测试 HealthStatus 枚举"""

    def test_enum_values(self) -> None:
        assert HealthStatus.HEALTHY.value == "HEALTHY"
        assert HealthStatus.DEGRADED.value == "DEGRADED"
        assert HealthStatus.UNHEALTHY.value == "UNHEALTHY"


class TestPluginInfo:
    """测试 PluginInfo 数据类"""

    def test_default_values(self) -> None:
        info = PluginInfo(
            name="test_plugin",
            display_name="Test Plugin",
            version="1.0.0",
            plugin_type=PluginType.CORE,
        )
        assert info.name == "test_plugin"
        assert info.state == PluginState.UNLOADED
        assert info.dependencies == []
        assert info.capabilities == []
        assert info.load_time == 0.0
        assert info.error_message is None

    def test_custom_values(self) -> None:
        info = PluginInfo(
            name="my_plugin",
            display_name="My Plugin",
            version="2.0.0",
            plugin_type=PluginType.OPTIONAL,
            state=PluginState.ACTIVE,
            dependencies=["dep_a"],
            capabilities=["cap_x"],
        )
        assert info.plugin_type == PluginType.OPTIONAL
        assert info.state == PluginState.ACTIVE
        assert "dep_a" in info.dependencies


class TestHealthCheckResult:
    """测试 HealthCheckResult 数据类"""

    def test_default_healthy(self) -> None:
        result = HealthCheckResult()
        assert result.status == HealthStatus.UNKNOWN
        assert result.message == ""
        assert result.details == {}

    def test_unhealthy_result(self) -> None:
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message="连接超时",
            details={"timeout": 30},
        )
        assert result.status == HealthStatus.UNHEALTHY
        assert "超时" in result.message


class TestExceptions:
    """测试自定义异常类"""

    def test_plugin_error(self) -> None:
        err = PluginError("测试错误", plugin_name="test")
        assert "测试错误" in str(err)
        assert err.plugin_name == "test"

    def test_plugin_load_error(self) -> None:
        err = PluginLoadError("加载失败", plugin_name="p1")
        assert isinstance(err, PluginError)
        assert err.plugin_name == "p1"

    def test_plugin_dependency_error(self) -> None:
        err = PluginDependencyError(
            "缺少依赖",
            plugin_name="p2",
            missing_dependencies=["dep_a", "dep_b"],
        )
        assert isinstance(err, PluginError)
        assert len(err.missing_dependencies) == 2

    def test_plugin_config_error(self) -> None:
        err = PluginConfigError("配置无效")
        assert isinstance(err, PluginError)

    def test_manifest_validation_error(self) -> None:
        err = ManifestValidationError("清单格式错误")
        assert isinstance(err, PluginError)


# ============================================================
# 业务共享类型测试（Phase 3.1 新增）
# ============================================================

from datetime import datetime

from src.kernel.types import (
    DecisionContext,
    SystemMode,
    TradingDecision,
    TradingSignal,
    WyckoffSignal,
)

import numpy as np


class TestSystemMode:
    """测试 SystemMode 枚举"""

    def test_enum_values(self) -> None:
        assert SystemMode.BACKTEST.value == "backtest"
        assert SystemMode.PAPER_TRADING.value == "paper"
        assert SystemMode.LIVE_TRADING.value == "live"
        assert SystemMode.EVOLUTION.value == "evolution"

    def test_all_modes_exist(self) -> None:
        modes = list(SystemMode)
        assert len(modes) == 4

    def test_mode_comparison(self) -> None:
        assert SystemMode.BACKTEST == SystemMode.BACKTEST
        assert SystemMode.BACKTEST != SystemMode.LIVE_TRADING


class TestTradingSignal:
    """测试 TradingSignal 枚举"""

    def test_enum_values(self) -> None:
        assert TradingSignal.STRONG_BUY.value == "strong_buy"
        assert TradingSignal.BUY.value == "buy"
        assert TradingSignal.NEUTRAL.value == "neutral"
        assert TradingSignal.SELL.value == "sell"
        assert TradingSignal.STRONG_SELL.value == "strong_sell"
        assert TradingSignal.WAIT.value == "wait"

    def test_all_signals_exist(self) -> None:
        signals = list(TradingSignal)
        assert len(signals) == 6


class TestWyckoffSignal:
    """测试 WyckoffSignal 枚举"""

    def test_enum_values(self) -> None:
        assert WyckoffSignal.BUY_SIGNAL.value == "buy_signal"
        assert WyckoffSignal.SELL_SIGNAL.value == "sell_signal"
        assert WyckoffSignal.NO_SIGNAL.value == "no_signal"

    def test_all_signals_exist(self) -> None:
        signals = list(WyckoffSignal)
        assert len(signals) == 3


class TestDecisionContext:
    """测试 DecisionContext 数据类"""

    def test_required_fields(self) -> None:
        now = datetime.now()
        ctx = DecisionContext(
            timestamp=now,
            market_regime="TRENDING",
            regime_confidence=0.85,
            timeframe_weights={"1h": 0.5, "4h": 0.3},
            detected_conflicts=[],
        )
        assert ctx.timestamp == now
        assert ctx.market_regime == "TRENDING"
        assert ctx.regime_confidence == 0.85
        assert len(ctx.timeframe_weights) == 2
        assert ctx.detected_conflicts == []

    def test_optional_defaults(self) -> None:
        ctx = DecisionContext(
            timestamp=datetime.now(),
            market_regime="RANGING",
            regime_confidence=0.7,
            timeframe_weights={},
            detected_conflicts=[],
        )
        assert ctx.wyckoff_state is None
        assert ctx.wyckoff_confidence == 0.0
        assert ctx.breakout_status is None
        assert ctx.fvg_signals == []
        assert ctx.anomaly_flags == []
        assert ctx.circuit_breaker_status is None

    def test_custom_optional_fields(self) -> None:
        ctx = DecisionContext(
            timestamp=datetime.now(),
            market_regime="VOLATILE",
            regime_confidence=0.6,
            timeframe_weights={"1h": 1.0},
            detected_conflicts=[{"type": "signal_conflict"}],
            wyckoff_state="accumulation",
            wyckoff_confidence=0.8,
            breakout_status={"direction": "up"},
            fvg_signals=[{"gap": 100}],
            anomaly_flags=[{"type": "volume_spike"}],
            circuit_breaker_status={"tripped": False},
        )
        assert ctx.wyckoff_state == "accumulation"
        assert ctx.wyckoff_confidence == 0.8
        assert ctx.breakout_status == {"direction": "up"}
        assert len(ctx.fvg_signals) == 1
        assert len(ctx.anomaly_flags) == 1

    def test_to_dict(self) -> None:
        now = datetime(2026, 1, 15, 10, 30, 0)
        ctx = DecisionContext(
            timestamp=now,
            market_regime="TRENDING",
            regime_confidence=0.9,
            timeframe_weights={"1h": 0.5},
            detected_conflicts=[],
        )
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert d["timestamp"] == now.isoformat()
        assert d["market_regime"] == "TRENDING"
        assert d["regime_confidence"] == 0.9
        assert d["timeframe_weights"] == {"1h": 0.5}

    def test_to_dict_numpy_timestamp(self) -> None:
        """测试 numpy int64 时间戳的转换"""
        np_ts = np.int64(1705312200000)  # 毫秒时间戳
        ctx = DecisionContext(
            timestamp=np_ts,
            market_regime="RANGING",
            regime_confidence=0.5,
            timeframe_weights={},
            detected_conflicts=[],
        )
        d = ctx.to_dict()
        # numpy int64 会被转换为 ISO 格式字符串
        assert isinstance(d["timestamp"], str)


class TestTradingDecision:
    """测试 TradingDecision 数据类"""

    def _make_context(self) -> DecisionContext:
        """创建测试用的 DecisionContext"""
        return DecisionContext(
            timestamp=datetime(2026, 1, 15, 10, 30, 0),
            market_regime="TRENDING",
            regime_confidence=0.85,
            timeframe_weights={"1h": 0.5},
            detected_conflicts=[],
        )

    def test_required_fields(self) -> None:
        ctx = self._make_context()
        td = TradingDecision(
            signal=TradingSignal.BUY,
            confidence=0.8,
            context=ctx,
        )
        assert td.signal == TradingSignal.BUY
        assert td.confidence == 0.8
        assert td.context is ctx

    def test_optional_defaults(self) -> None:
        ctx = self._make_context()
        td = TradingDecision(
            signal=TradingSignal.NEUTRAL,
            confidence=0.5,
            context=ctx,
        )
        assert td.entry_price is None
        assert td.stop_loss is None
        assert td.take_profit is None
        assert td.position_size is None
        assert td.reasoning == []
        assert isinstance(td.timestamp, datetime)

    def test_custom_optional_fields(self) -> None:
        ctx = self._make_context()
        td = TradingDecision(
            signal=TradingSignal.STRONG_BUY,
            confidence=0.95,
            context=ctx,
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=55000.0,
            position_size=0.1,
            reasoning=["突破阻力位", "成交量放大"],
        )
        assert td.entry_price == 50000.0
        assert td.stop_loss == 49000.0
        assert td.take_profit == 55000.0
        assert td.position_size == 0.1
        assert len(td.reasoning) == 2

    def test_to_dict(self) -> None:
        ctx = self._make_context()
        td = TradingDecision(
            signal=TradingSignal.SELL,
            confidence=0.7,
            context=ctx,
            entry_price=48000.0,
            reasoning=["趋势反转"],
        )
        d = td.to_dict()
        assert isinstance(d, dict)
        assert d["signal"] == "sell"
        assert d["confidence"] == 0.7
        assert d["entry_price"] == 48000.0
        assert d["reasoning"] == ["趋势反转"]
        assert isinstance(d["context"], dict)
        assert d["context"]["market_regime"] == "TRENDING"

    def test_to_dict_numpy_timestamp(self) -> None:
        """测试 numpy int64 时间戳的转换"""
        ctx = self._make_context()
        np_ts = np.int64(1705312200000)
        td = TradingDecision(
            signal=TradingSignal.WAIT,
            confidence=0.3,
            context=ctx,
            timestamp=np_ts,
        )
        d = td.to_dict()
        assert isinstance(d["timestamp"], str)


class TestCompatibilityImports:
    """测试从兼容层导入业务类型"""

    def test_import_from_system_orchestrator(self) -> None:
        """验证从 src.plugins.orchestrator 导入业务类型"""
        from src.plugins.orchestrator.system_orchestrator_legacy import (
            SystemOrchestrator,
        )
        from src.kernel.types import (
            DecisionContext as DC,
            SystemMode as SM,
            TradingDecision as TD,
            TradingSignal as TS,
            WyckoffSignal as WS,
        )

        # 确保是同一个类（从kernel导入）
        assert SM is SystemMode
        assert TS is TradingSignal
        assert WS is WyckoffSignal
        assert DC is DecisionContext
        assert TD is TradingDecision

    def test_import_from_kernel(self) -> None:
        """验证从 src.kernel 导入业务类型"""
        from src.kernel import (
            DecisionContext as DC,
            SystemMode as SM,
            TradingDecision as TD,
            TradingSignal as TS,
            WyckoffSignal as WS,
        )

        assert SM is SystemMode
        assert TS is TradingSignal
        assert WS is WyckoffSignal
        assert DC is DecisionContext
        assert TD is TradingDecision
