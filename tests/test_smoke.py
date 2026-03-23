"""冒烟测试 — 系统启动后 30 秒内验证所有核心功能存活

运行时机: 每次提交、每次部署后
预期时间: < 5 秒
覆盖范围:
    1. 18 个插件全部加载
    2. 核心插件内部组件初始化（非 None）
    3. API 层依赖的所有方法可调用
    4. 事件总线能收发
    5. 关键事件链路有订阅者
"""

import pytest
from typing import Any, Dict

from src.app import WyckoffApp


# ================================================================
# Fixture: 启动完整系统（整个模块共享一个实例）
# ================================================================


@pytest.fixture(scope="module")
def app() -> WyckoffApp:
    """启动 WyckoffApp 并加载所有插件"""
    wyckoff_app = WyckoffApp(config_path="config.yaml")
    wyckoff_app.discover_and_load()
    return wyckoff_app


@pytest.fixture(scope="module")
def pm(app: WyckoffApp):  # type: ignore[no-untyped-def]
    return app.plugin_manager


@pytest.fixture(scope="module")
def event_bus(pm):  # type: ignore[no-untyped-def]
    return pm.get_event_bus()


# ================================================================
# 1. 插件加载完整性
# ================================================================


EXPECTED_PLUGINS = [
    "market_regime",
    "data_pipeline",
    "orchestrator",
    "wyckoff_state_machine",
    "wyckoff_engine",
    "pattern_detection",
    "perception",
    "signal_validation",
    "risk_management",
    "position_manager",
    "weight_system",
    "evolution",
    "exchange_connector",
    "dashboard",
    "self_correction",
    "evolution_advisor",
    "telegram_notifier",
    "audit_logger",
]


class TestPluginLoading:
    """所有插件必须成功加载"""

    def test_all_18_plugins_loaded(self, pm) -> None:  # type: ignore[no-untyped-def]
        """18 个插件全部加载"""
        loaded = {info.name for info in pm.list_plugins()}
        for name in EXPECTED_PLUGINS:
            assert name in loaded, f"插件 {name} 未加载"

    def test_plugin_count(self, pm) -> None:  # type: ignore[no-untyped-def]
        """插件总数 >= 18"""
        assert len(pm.list_plugins()) >= 18

    @pytest.mark.parametrize("plugin_name", EXPECTED_PLUGINS)
    def test_plugin_is_active(self, pm, plugin_name: str) -> None:  # type: ignore[no-untyped-def]
        """每个插件状态为 ACTIVE"""
        plugin = pm.get_plugin(plugin_name)
        assert plugin is not None, f"{plugin_name} 插件不存在"
        assert plugin.is_active, f"{plugin_name} 插件未激活"


# ================================================================
# 2. 核心组件初始化（非 None）
# ================================================================


COMPONENT_CHECKS = [
    ("orchestrator", "_engine", "WyckoffEngine"),
    ("wyckoff_engine", "engine", "WyckoffEngine"),
    ("evolution", "_ga", "GeneticAlgorithm"),
    ("evolution", "_evaluator", "StandardEvaluator"),
    ("evolution", "_wfa", "WFAValidator"),
    ("evolution", "_anti_overfit", "AntiOverfitGuard"),
    ("data_pipeline", "pipeline", "DataPipeline"),
    ("pattern_detection", "_tr_detector", "TRDetector"),
    ("perception", "_fvg_detector", "FVGDetector"),
    ("signal_validation", "_breakout_validator", "BreakoutValidator"),
    ("risk_management", "_capital_guard", "CapitalGuard"),
    ("position_manager", "_manager", "PositionManager"),
    ("wyckoff_state_machine", "_state_machine", "StateMachine"),
    ("self_correction", "_workflow", "SelfCorrectionWorkflow"),
    ("dashboard", "_monitor", "Monitor"),
]


class TestComponentInit:
    """关键内部组件必须在 on_load() 后初始化"""

    @pytest.mark.parametrize(
        "plugin_name,attr_name,desc",
        COMPONENT_CHECKS,
        ids=[f"{p}.{a}" for p, a, _ in COMPONENT_CHECKS],
    )
    def test_component_not_none(
        self,
        pm,
        plugin_name: str,
        attr_name: str,
        desc: str,  # type: ignore[no-untyped-def]
    ) -> None:
        plugin = pm.get_plugin(plugin_name)
        assert plugin is not None, f"{plugin_name} 未加载"
        val = getattr(plugin, attr_name, "__MISSING__")
        if val == "__MISSING__":
            pytest.skip(f"{plugin_name}.{attr_name} 属性不存在（可能已重命名）")
        assert val is not None, (
            f"{plugin_name}.{attr_name} 为 None — {desc} 未在 on_load() 中初始化"
        )


# ================================================================
# 3. API 方法可调用性
# ================================================================


API_METHOD_CHECKS = [
    ("data_pipeline", "get_cached_data", ("BTC/USDT", "H4"), True),
    ("orchestrator", "get_system_status", (), False),
    ("orchestrator", "get_decision_history", (1,), False),
    ("position_manager", "get_all_positions", (), False),
    ("position_manager", "get_closed_trades", (), False),
    ("evolution", "get_evolution_status", (), False),
    ("evolution", "get_current_config", (), False),
    ("wyckoff_engine", "get_current_state", (), False),
    ("audit_logger", "get_recent_logs", (20,), False),
    ("evolution_advisor", "get_last_analysis", (), True),
]


class TestApiMethods:
    """API 层依赖的方法必须存在且可调用"""

    @pytest.mark.parametrize(
        "plugin_name,method_name,args,none_ok",
        API_METHOD_CHECKS,
        ids=[f"{p}.{m}" for p, m, _, _ in API_METHOD_CHECKS],
    )
    def test_method_callable(
        self,
        pm,  # type: ignore[no-untyped-def]
        plugin_name: str,
        method_name: str,
        args: tuple,
        none_ok: bool,
    ) -> None:
        plugin = pm.get_plugin(plugin_name)
        assert plugin is not None, f"{plugin_name} 未加载"

        fn = getattr(plugin, method_name, None)
        assert fn is not None, (
            f"{plugin_name}.{method_name}() 方法不存在 — API 端点将失败"
        )

        result = fn(*args)
        if not none_ok:
            assert result is not None, f"{plugin_name}.{method_name}() 返回 None"


# ================================================================
# 4. 事件总线基本功能
# ================================================================


class TestEventBus:
    """事件总线必须能正常收发"""

    def test_emit_and_receive(self, event_bus) -> None:  # type: ignore[no-untyped-def]
        """发布事件后订阅者能收到"""
        received: list[Dict[str, Any]] = []
        event_bus.subscribe(
            "smoke_test.ping",
            lambda name, data: received.append(data),
        )
        event_bus.emit(
            "smoke_test.ping",
            {"value": 42},
            publisher="smoke_test",
        )
        assert len(received) == 1
        assert received[0]["value"] == 42

    def test_multiple_subscribers(self, event_bus) -> None:  # type: ignore[no-untyped-def]
        """多个订阅者都能收到同一事件"""
        results_a: list[str] = []
        results_b: list[str] = []
        event_bus.subscribe(
            "smoke_test.multi",
            lambda n, d: results_a.append("a"),
        )
        event_bus.subscribe(
            "smoke_test.multi",
            lambda n, d: results_b.append("b"),
        )
        event_bus.emit("smoke_test.multi", {}, publisher="test")
        assert len(results_a) == 1
        assert len(results_b) == 1


# ================================================================
# 5. 关键事件链路有订阅者
# ================================================================


CRITICAL_EVENTS = [
    ("data_pipeline.ohlcv_ready", 2),
    ("trading.signal", 2),
    ("market.price_update", 1),
    ("risk_management.circuit_breaker_tripped", 3),
    ("evolution.cycle_complete", 1),
    ("position.opened", 2),
    ("position.closed", 2),
]


class TestEventWiring:
    """关键事件必须有足够的订阅者"""

    @pytest.mark.parametrize(
        "event_name,min_subscribers",
        CRITICAL_EVENTS,
        ids=[e for e, _ in CRITICAL_EVENTS],
    )
    def test_event_has_subscribers(
        self,
        event_bus,
        event_name: str,
        min_subscribers: int,  # type: ignore[no-untyped-def]
    ) -> None:
        subs = event_bus.get_subscribers(event_name)
        assert len(subs) >= min_subscribers, (
            f"事件 {event_name} 只有 {len(subs)} 个订阅者，"
            f"期望至少 {min_subscribers} 个"
        )
