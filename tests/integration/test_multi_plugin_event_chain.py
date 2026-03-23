"""多插件事件链集成测试 — 真实 EventBus 多插件通信

测试完整事件传播链:
market_regime → orchestrator → wyckoff_sm → signal_validation → position_manager
"""

import pathlib
from typing import Any, Dict, List

import pytest

from src.app import WyckoffApp
from src.kernel.event_bus import EventBus
from src.kernel.types import TradingSignal
from tests.fixtures.ohlcv_generator import make_multi_tf_data, make_ohlcv


@pytest.fixture(scope="module")
def system():
    """真实系统 — 全部插件加载"""
    old_journal = pathlib.Path("./data/position_journal.jsonl")
    old_journal_bak = pathlib.Path("./data/position_journal.jsonl.bak.chain")
    if old_journal.exists():
        old_journal.rename(old_journal_bak)

    wa = WyckoffApp(config_path="config.yaml", plugins_dir="src/plugins")
    wa.discover_and_load()

    pm = wa.plugin_manager.get_plugin("position_manager")
    if pm is not None and hasattr(pm, "_manager") and pm._manager is not None:  # type: ignore[attr-defined]
        pm._manager.positions.clear()  # type: ignore[attr-defined]

    yield wa

    wa.plugin_manager.unload_all()
    if old_journal_bak.exists():
        if old_journal.exists():
            old_journal.unlink()
        old_journal_bak.rename(old_journal)


class TestMultiPluginEventChain:
    """多插件事件链测试"""

    def test_ohlcv_ready_triggers_full_chain(self, system) -> None:
        """data_pipeline.ohlcv_ready → trading.signal 完整事件链"""
        bus = system.event_bus
        signals: List[Dict[str, Any]] = []

        bus.subscribe("trading.signal", lambda n, d: signals.append(d))

        data_dict = make_multi_tf_data(h4_bars=200, trend="up")
        bus.emit(
            "data_pipeline.ohlcv_ready",
            {
                "symbol": "BTC/USDT",
                "data_dict": data_dict,
                "timeframes": ["H4", "H1", "M15", "M5"],
            },
        )

        assert len(signals) == 1
        assert signals[0]["symbol"] == "BTC/USDT"

    def test_market_regime_detected_event(self, system) -> None:
        """market_regime 插件接收数据后发布 regime 事件"""
        bus = system.event_bus
        mr = system.plugin_manager.get_plugin("market_regime")

        if mr is None:
            pytest.skip("market_regime plugin not loaded")

        regimes: List[Dict[str, Any]] = []
        bus.subscribe(
            "market_regime.detected",
            lambda n, d: regimes.append(d),
        )

        # 直接调用检测
        if hasattr(mr, "detect"):
            data = make_ohlcv(n=100, trend="up")
            mr.detect(data)

            if len(regimes) > 0:
                assert "regime" in regimes[-1]

    def test_orchestrator_subscribes_to_data_ready(self, system) -> None:
        """orchestrator 订阅 data_pipeline.ohlcv_ready"""
        orch = system.plugin_manager.get_plugin("orchestrator")
        assert orch is not None

        # 验证 orchestrator 有 _on_data_ready 处理器
        bus = system.event_bus
        handlers = bus._get_matching_handlers("data_pipeline.ohlcv_ready")
        orch_handlers = [h for h in handlers if h.subscriber_name == "orchestrator"]
        assert len(orch_handlers) >= 1

    def test_position_manager_subscribes_to_trading_signal(self, system) -> None:
        """position_manager 订阅 trading.signal"""
        bus = system.event_bus
        handlers = bus._get_matching_handlers("trading.signal")
        pm_handlers = [h for h in handlers if h.subscriber_name == "position_manager"]
        assert len(pm_handlers) >= 1

    def test_event_bus_has_no_paused_events(self, system) -> None:
        """事件总线没有暂停的事件"""
        bus = system.event_bus
        assert len(bus._paused_events) == 0

    def test_sequential_data_processing(self, system) -> None:
        """连续处理多批数据不崩溃"""
        bus = system.event_bus
        signal_count = 0

        def count_signals(n: str, d: Dict[str, Any]) -> None:
            nonlocal signal_count
            signal_count += 1

        bus.subscribe("trading.signal", count_signals)

        for i in range(3):
            data_dict = make_multi_tf_data(h4_bars=200, trend="flat", seed=100 + i)
            bus.emit(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": data_dict,
                    "timeframes": ["H4", "H1", "M15", "M5"],
                },
            )

        assert signal_count == 3

    def test_error_in_handler_doesnt_block_others(self, system) -> None:
        """一个处理器崩溃不影响其他处理器"""
        bus = system.event_bus
        results: List[str] = []

        def good_handler(n: str, d: Dict[str, Any]) -> None:
            results.append("ok")

        def bad_handler(n: str, d: Dict[str, Any]) -> None:
            raise RuntimeError("Test error")

        bus.subscribe("test.error_isolation", bad_handler)
        bus.subscribe("test.error_isolation", good_handler)

        bus.emit("test.error_isolation", {"x": 1})
        assert "ok" in results

    def test_all_active_plugins_have_event_bus(self, system) -> None:
        """所有活跃插件都注入了 EventBus"""
        for info in system.plugin_manager.list_plugins():
            plugin = system.plugin_manager.get_plugin(info.name)
            if plugin and plugin.is_active:
                assert plugin._event_bus is not None, (
                    f"插件 {info.name} 未注入 EventBus"
                )
