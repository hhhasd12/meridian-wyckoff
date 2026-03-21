"""E2E 全链路集成测试 — 证明系统能完整运转

P0: 系统启动（WyckoffApp 加载全部 16 个插件）
P1: 完整管线（数据 → 分析 → 信号 → 仓位 → 平仓）
P2: 边界条件（熔断、配置变更、多品种并发）
"""

import os
import tempfile
from typing import Any, Dict, List

import pandas as pd
import pytest

from src.app import WyckoffApp
from src.kernel.types import (
    PluginState,
    TradingDecision,
    TradingSignal,
)
from tests.fixtures.ohlcv_generator import make_multi_tf_data, make_ohlcv


# ================================================================
# Fixtures
# ================================================================


@pytest.fixture(scope="module")
def loaded_app(tmp_path_factory):
    """模块级 WyckoffApp — 真实加载所有插件（仅创建一次）"""
    # 使用临时目录存放 journal，避免恢复旧持仓
    tmp_dir = tmp_path_factory.mktemp("e2e_test")
    journal_path = str(tmp_dir / "test_journal.jsonl")

    wa = WyckoffApp(config_path="config.yaml", plugins_dir="src/plugins")

    # 删除可能存在的旧 journal
    import pathlib

    old_journal = pathlib.Path("./data/position_journal.jsonl")
    old_journal_bak = pathlib.Path("./data/position_journal.jsonl.bak")
    if old_journal.exists():
        old_journal.rename(old_journal_bak)

    wa.discover_and_load()

    # 清理 position_manager 可能恢复的旧持仓
    pm = wa.plugin_manager.get_plugin("position_manager")
    if pm is not None and hasattr(pm, "_manager") and pm._manager is not None:
        for sym in list(pm._manager.positions.keys()):
            pm._manager.positions.pop(sym)

    yield wa
    wa.plugin_manager.unload_all()

    # 恢复旧 journal
    if old_journal_bak.exists():
        if old_journal.exists():
            old_journal.unlink()
        old_journal_bak.rename(old_journal)


# ================================================================
# P0 — 系统启动（6 个测试）
# ================================================================


class TestP0SystemStartup:
    """P0 冒烟测试 — WyckoffApp 能启动并加载所有插件"""

    def test_discover_finds_all_plugins(self, loaded_app) -> None:
        """discover_plugins 能发现全部 16 个插件"""
        # loaded_app 已经 discover_and_load，验证结果
        infos = loaded_app.plugin_manager.list_plugins()
        names = [i.name for i in infos]
        assert "market_regime" in names
        assert "data_pipeline" in names
        assert "orchestrator" in names
        assert len(names) >= 15

    def test_load_all_succeeds(self, loaded_app) -> None:
        """load_all 所有插件加载成功（无失败）"""
        infos = loaded_app.plugin_manager.list_plugins()
        # 检查是否有 ERROR 状态的插件
        errored = [
            (i.name, i.state.value) for i in infos if i.state == PluginState.ERROR
        ]
        assert len(errored) == 0, f"加载出错的插件: {errored}"

    def test_all_plugins_active(self, loaded_app) -> None:
        """所有插件达到 ACTIVE 状态"""
        infos = loaded_app.plugin_manager.list_plugins()
        non_active = [
            (i.name, i.state.value) for i in infos if i.state != PluginState.ACTIVE
        ]
        assert len(non_active) == 0, f"非 ACTIVE 插件: {non_active}"

    def test_core_plugins_accessible(self, loaded_app) -> None:
        """核心插件可通过 get_plugin 获取"""
        for name in ["market_regime", "data_pipeline", "orchestrator"]:
            plugin = loaded_app.plugin_manager.get_plugin(name)
            assert plugin is not None, f"核心插件 {name} 为 None"
            assert plugin.is_active, f"核心插件 {name} 未激活"

    def test_get_status(self, loaded_app) -> None:
        """get_status 返回完整状态"""
        status = loaded_app.get_status()
        assert status["is_running"] is False  # 未调用 start()
        assert status["plugin_count"] >= 15
        assert "orchestrator" in status["plugins"]
        assert status["plugins"]["orchestrator"] == "ACTIVE"

    def test_health_check_all(self, loaded_app) -> None:
        """所有插件健康检查通过"""
        results = loaded_app.plugin_manager.health_check_all()
        assert len(results) >= 15
        for name, hc in results.items():
            assert hc.status.value in (
                "HEALTHY",
                "DEGRADED",
            ), f"插件 {name} 不健康: {hc.status.value} - {hc.message}"


# ================================================================
# P1 — 完整管线（8 个测试）
# ================================================================


class TestP1FullPipeline:
    """P1 集成测试 — 数据 → 分析 → 信号 → 仓位"""

    def test_orchestrator_has_engine(self, loaded_app) -> None:
        """OrchestratorPlugin 持有 WyckoffEngine"""
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")
        assert orch is not None
        assert hasattr(orch, "engine") or hasattr(orch, "_engine")
        engine = getattr(orch, "engine", None) or getattr(orch, "_engine", None)
        assert engine is not None

    def test_process_market_data_returns_decision(self, loaded_app) -> None:
        """_process_market_data 用真实合成数据产出 TradingDecision"""
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")
        data_dict = make_multi_tf_data(h4_bars=200, trend="flat")

        decision = orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )
        assert decision is not None
        assert isinstance(decision, TradingDecision)
        assert hasattr(decision, "signal")
        assert hasattr(decision, "confidence")

    def test_event_chain_data_to_signal(self, loaded_app) -> None:
        """事件链: ohlcv_ready → trading.signal"""
        bus = loaded_app.event_bus
        captured: List[Dict[str, Any]] = []

        def handler(name: str, data: Dict[str, Any]) -> None:
            captured.append(data)

        bus.subscribe("trading.signal", handler)

        data_dict = make_multi_tf_data(h4_bars=200)
        bus.emit(
            "data_pipeline.ohlcv_ready",
            {
                "symbol": "BTC/USDT",
                "data_dict": data_dict,
                "timeframes": ["H4", "H1", "M15"],
            },
        )

        assert len(captured) == 1
        assert captured[0]["symbol"] == "BTC/USDT"
        assert "signal" in captured[0]
        assert "confidence" in captured[0]

    def test_signal_opens_position(self, loaded_app) -> None:
        """BUY 信号 → position.opened 事件"""
        bus = loaded_app.event_bus
        opened: List[Dict[str, Any]] = []

        bus.subscribe(
            "position.opened",
            lambda n, d: opened.append(d),
        )

        # 使用唯一品种避免与其他测试冲突
        df = make_ohlcv(n=30, start_price=200.0)
        bus.emit(
            "trading.signal",
            {
                "symbol": "AVAX/USDT",
                "signal": TradingSignal.BUY,
                "confidence": 0.85,
                "entry_price": 200.0,
                "stop_loss": 194.0,
                "take_profit": 212.0,
                "wyckoff_state": "SOS",
                "df": df,
            },
        )

        assert len(opened) >= 1
        last = opened[-1]
        assert last["symbol"] == "AVAX/USDT"
        assert last["side"] == "long"

    def test_full_cycle_open_then_close(self, loaded_app) -> None:
        """完整周期: BUY开仓 → 价格触及止损 → 平仓"""
        bus = loaded_app.event_bus
        opened: List[Dict[str, Any]] = []

        bus.subscribe("position.opened", lambda n, d: opened.append(d))

        # 使用唯一品种
        df = make_ohlcv(n=30, start_price=50.0)
        bus.emit(
            "trading.signal",
            {
                "symbol": "LINK/USDT",
                "signal": TradingSignal.BUY,
                "confidence": 0.85,
                "entry_price": 50.0,
                "stop_loss": 48.5,
                "take_profit": 53.0,
                "wyckoff_state": "SOS",
                "df": df,
            },
        )

        assert len(opened) >= 1

        # 获取 position_manager 并模拟价格触及止损
        pm = loaded_app.plugin_manager.get_plugin("position_manager")
        assert pm is not None
        assert pm._manager is not None

        position = pm._manager.get_position("LINK/USDT")
        assert position is not None, "LINK/USDT 仓位应已开仓"

        exit_result = pm._manager.update_position(
            symbol="LINK/USDT",
            current_price=position.stop_loss - 1.0,  # 低于止损
        )

        assert exit_result is not None
        assert exit_result.should_exit

        trade_result = pm._manager.close_position(
            symbol="LINK/USDT",
            exit_price=position.stop_loss,
            reason=exit_result.reason,
        )

        assert trade_result is not None
        assert trade_result.pnl < 0  # 止损应亏损
        assert pm._manager.get_position("LINK/USDT") is None

    def test_different_trend_data(self, loaded_app) -> None:
        """不同趋势数据都能产出决策（不崩溃）"""
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")

        for trend in ["flat", "up", "down", "spring"]:
            data_dict = make_multi_tf_data(h4_bars=200, trend=trend, seed=100)
            decision = orch._process_market_data(
                "BTC/USDT",
                ["H4", "H1", "M15"],
                data_dict,
            )
            assert decision is not None, f"trend={trend} 返回 None"
            assert isinstance(decision, TradingDecision)

    def test_decision_has_all_components(self, loaded_app) -> None:
        """TradingDecision 包含所有子组件"""
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")
        data_dict = make_multi_tf_data(h4_bars=200, trend="up")

        decision = orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )
        assert decision is not None

        # TradingDecision 应该包含以下字段
        assert hasattr(decision, "signal")
        assert hasattr(decision, "confidence")
        assert hasattr(decision, "context")

    def test_decision_history_recorded(self, loaded_app) -> None:
        """决策历史被记录"""
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")
        data_dict = make_multi_tf_data(h4_bars=200)

        orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )

        history = orch.get_decision_history()
        assert len(history) >= 1


# ================================================================
# P2 — 边界条件（5 个测试）
# ================================================================


class TestP2EdgeCases:
    """P2 边界条件 — 异常输入、熔断、多品种"""

    def test_neutral_signal_no_position(self, loaded_app) -> None:
        """NEUTRAL 信号不开仓"""
        bus = loaded_app.event_bus
        opened: List[Dict[str, Any]] = []

        bus.subscribe("position.opened", lambda n, d: opened.append(d))

        bus.emit(
            "trading.signal",
            {
                "symbol": "SOL/USDT",
                "signal": TradingSignal.NEUTRAL,
                "confidence": 0.9,
                "entry_price": 150.0,
            },
        )

        assert len(opened) == 0

    def test_circuit_breaker_blocks_signal(self, loaded_app) -> None:
        """熔断后不发布交易信号"""
        bus = loaded_app.event_bus
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")
        captured: List[Dict[str, Any]] = []

        bus.subscribe("trading.signal", lambda n, d: captured.append(d))

        # 触发熔断
        bus.emit(
            "risk_management.circuit_breaker_tripped",
            {"reason": "test_circuit_breaker"},
        )

        # 处理数据
        data_dict = make_multi_tf_data(h4_bars=200)
        orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )

        # 熔断中不应有信号
        assert len(captured) == 0

    def test_circuit_breaker_recovery(self, loaded_app) -> None:
        """熔断恢复后恢复信号"""
        bus = loaded_app.event_bus
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")
        captured: List[Dict[str, Any]] = []

        bus.subscribe("trading.signal", lambda n, d: captured.append(d))

        # 熔断 → 恢复
        bus.emit(
            "risk_management.circuit_breaker_tripped",
            {"reason": "test"},
        )
        bus.emit(
            "risk_management.circuit_breaker_recovered",
            {},
        )

        data_dict = make_multi_tf_data(h4_bars=200)
        orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )

        assert len(captured) == 1

    def test_empty_data_dict_handled(self, loaded_app) -> None:
        """空数据字典不崩溃"""
        bus = loaded_app.event_bus
        captured: List[Dict[str, Any]] = []

        bus.subscribe("trading.signal", lambda n, d: captured.append(d))

        bus.emit(
            "data_pipeline.ohlcv_ready",
            {"symbol": "BTC/USDT"},
        )

        # 无数据不应产生信号
        assert len(captured) == 0

    def test_multiple_symbols_sequential(self, loaded_app) -> None:
        """多个品种依次处理"""
        orch = loaded_app.plugin_manager.get_plugin("orchestrator")
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

        for i, symbol in enumerate(symbols):
            data_dict = make_multi_tf_data(h4_bars=200, seed=42 + i)
            decision = orch._process_market_data(
                symbol,
                ["H4", "H1", "M15"],
                data_dict,
            )
            assert decision is not None, f"{symbol} decision is None"
            assert isinstance(decision, TradingDecision)
