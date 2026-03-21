"""端到端事件链测试 — Phase 3 核心验证

测试完整信号链：
    数据到达 → WyckoffEngine 处理 → trading.signal 发布
    → PositionManager 接收 → ExchangeExecutor 执行

P0: 冒烟测试（5个）— 各组件基础初始化
P1: 集成测试（6个）— 事件链端到端
P2: 边界条件（5个）— 异常输入处理
"""

import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
import pytest

from src.kernel.event_bus import EventBus
from src.kernel.types import (
    DecisionContext,
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
from src.plugins.orchestrator.plugin import OrchestratorPlugin
from src.plugins.position_manager.plugin import (
    PositionManagerPlugin,
)
from src.plugins.position_manager.position_journal import (
    PositionJournal,
)
from tests.fixtures.ohlcv_generator import (
    make_multi_tf_data,
    make_ohlcv,
)


# ================================================================
# 辅助函数
# ================================================================


def _make_bus() -> EventBus:
    """创建启用历史的 EventBus"""
    return EventBus(enable_history=True)


def _make_orchestrator(
    bus: EventBus,
    config: Dict[str, Any] | None = None,
) -> OrchestratorPlugin:
    """创建并加载 OrchestratorPlugin"""
    plugin = OrchestratorPlugin()
    plugin._config = config or {
        "mode": "paper",
        "symbols": ["BTC/USDT"],
        "timeframes": ["H4", "H1", "M15"],
    }
    plugin._set_event_bus(bus)
    plugin.on_load()
    return plugin


def _make_position_manager(
    bus: EventBus,
    journal_path: str,
    config: Dict[str, Any] | None = None,
) -> PositionManagerPlugin:
    """创建并加载 PositionManagerPlugin"""
    plugin = PositionManagerPlugin()
    plugin._config = config or {
        "paper_trading": True,
        "initial_balance": 10000.0,
        "max_positions": 3,
        "risk_per_trade": 0.02,
        "min_confidence": 0.5,
        "journal_path": journal_path,
        "executor": {
            "paper_trading": True,
            "initial_balance": 10000.0,
        },
        "stop_loss": {"method": "fixed", "fixed_percentage": 0.02},
        "signal_exit": {"signal_reversal_enabled": True},
    }
    plugin._set_event_bus(bus)
    plugin.on_load()
    return plugin


# ================================================================
# P0 — 冒烟测试（5个）
# ================================================================


class TestP0SignalChainSmoke:
    """P0 冒烟测试 — 各组件基础初始化"""

    def test_orchestrator_holds_engine(self) -> None:
        """OrchestratorPlugin.on_load() 创建 WyckoffEngine"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        assert orch.engine is not None

    def test_orchestrator_processes_data(self) -> None:
        """_process_market_data() 返回 TradingDecision"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        data_dict = make_multi_tf_data()

        decision = orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )
        assert decision is not None
        assert isinstance(decision, TradingDecision)

    def test_orchestrator_publishes_trading_signal(self) -> None:
        """EventBus 接收到 trading.signal 事件"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        captured: List[Dict[str, Any]] = []

        def handler(name: str, data: Dict[str, Any]) -> None:
            captured.append({"event": name, "data": data})

        bus.subscribe("trading.signal", handler)
        data_dict = make_multi_tf_data()
        orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )
        assert len(captured) == 1
        assert captured[0]["data"]["symbol"] == "BTC/USDT"
        assert "signal" in captured[0]["data"]

    def test_executor_execute_returns_order_result(self) -> None:
        """ExchangeExecutor.execute() 返回 OrderResult"""
        executor = ExchangeExecutor({"paper_trading": True, "initial_balance": 10000.0})
        executor.connect()

        request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=0.01,
            price=50000.0,
        )
        result = executor.execute(request)

        assert isinstance(result, OrderResult)
        assert result.is_filled
        assert result.filled_size == 0.01

    def test_position_journal_roundtrip(self) -> None:
        """PositionJournal 写入后可恢复"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.jsonl")
            journal = PositionJournal(path)

            from src.plugins.position_manager.types import (
                Position,
                PositionSide,
            )

            pos = Position(
                symbol="BTC/USDT",
                side=PositionSide.LONG,
                size=0.1,
                entry_price=50000.0,
                entry_time=datetime.now(),
                stop_loss=49000.0,
                take_profit=52000.0,
                signal_confidence=0.8,
                wyckoff_state="SOS",
                entry_signal=TradingSignal.BUY,
            )
            journal.record_open(pos)

            recovered = journal.recover_positions()
            assert "BTC/USDT" in recovered
            assert recovered["BTC/USDT"].entry_price == 50000.0


# ================================================================
# P1 — 集成测试（6个）
# ================================================================


class TestP1SignalChainIntegration:
    """P1 集成测试 — 事件链端到端"""

    def test_full_chain_data_to_signal(self) -> None:
        """模拟 ohlcv_ready 事件 → 检查 trading.signal"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        captured: List[Dict[str, Any]] = []

        def handler(name: str, data: Dict[str, Any]) -> None:
            captured.append(data)

        bus.subscribe("trading.signal", handler)

        data_dict = make_multi_tf_data()
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

    def test_full_chain_signal_to_position(self) -> None:
        """发送 BUY 信号 → 检查 position.opened"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "j.jsonl")
            bus = _make_bus()
            pm = _make_position_manager(bus, path)
            opened: List[Dict[str, Any]] = []

            def handler(name: str, data: Dict[str, Any]) -> None:
                opened.append(data)

            bus.subscribe("position.opened", handler)

            # 发送 BUY 信号
            bus.emit(
                "trading.signal",
                {
                    "symbol": "BTC/USDT",
                    "signal": TradingSignal.BUY,
                    "confidence": 0.8,
                    "entry_price": 50000.0,
                    "stop_loss": 49000.0,
                    "take_profit": 52000.0,
                    "wyckoff_state": "SOS",
                    "df": make_ohlcv(n=30),
                },
            )

            assert len(opened) == 1
            assert opened[0]["symbol"] == "BTC/USDT"
            assert opened[0]["side"] == "long"

    def test_circuit_breaker_blocks_signal(self) -> None:
        """熔断时不发布有效信号"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        captured: List[Dict[str, Any]] = []

        def handler(name: str, data: Dict[str, Any]) -> None:
            captured.append(data)

        bus.subscribe("trading.signal", handler)

        # 触发熔断
        bus.emit(
            "risk_management.circuit_breaker_tripped",
            {"reason": "test"},
        )

        # 发送数据
        data_dict = make_multi_tf_data()
        orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )

        # 熔断中不应发布 trading.signal
        assert len(captured) == 0

    def test_circuit_breaker_recovery(self) -> None:
        """熔断恢复后恢复信号发布"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        captured: List[Dict[str, Any]] = []

        def handler(name: str, data: Dict[str, Any]) -> None:
            captured.append(data)

        bus.subscribe("trading.signal", handler)

        # 熔断 → 恢复
        bus.emit(
            "risk_management.circuit_breaker_tripped",
            {"reason": "test"},
        )
        bus.emit(
            "risk_management.circuit_breaker_recovered",
            {},
        )

        data_dict = make_multi_tf_data()
        orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )

        # 恢复后应发布 trading.signal
        assert len(captured) == 1

    def test_position_journal_records_open(self) -> None:
        """开仓后 journal 文件包含记录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "j.jsonl")
            bus = _make_bus()
            pm = _make_position_manager(bus, path)

            bus.emit(
                "trading.signal",
                {
                    "symbol": "BTC/USDT",
                    "signal": TradingSignal.BUY,
                    "confidence": 0.8,
                    "entry_price": 50000.0,
                    "stop_loss": 49000.0,
                    "wyckoff_state": "SOS",
                    "df": make_ohlcv(n=30),
                },
            )

            assert os.path.exists(path)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) >= 1
            assert '"open"' in lines[0]

    def test_decision_history_recorded(self) -> None:
        """决策历史被记录"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        data_dict = make_multi_tf_data()

        orch._process_market_data(
            "BTC/USDT",
            ["H4", "H1", "M15"],
            data_dict,
        )

        history = orch.get_decision_history()
        assert len(history) == 1


# ================================================================
# P2 — 边界条件（5个）
# ================================================================


class TestP2SignalChainEdgeCases:
    """P2 边界条件 — 异常输入处理"""

    def test_neutral_signal_no_position(self) -> None:
        """NEUTRAL 信号不开仓"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "j.jsonl")
            bus = _make_bus()
            pm = _make_position_manager(bus, path)
            opened: List[Dict[str, Any]] = []

            bus.subscribe(
                "position.opened",
                lambda n, d: opened.append(d),
            )

            bus.emit(
                "trading.signal",
                {
                    "symbol": "BTC/USDT",
                    "signal": TradingSignal.NEUTRAL,
                    "confidence": 0.9,
                    "entry_price": 50000.0,
                },
            )

            assert len(opened) == 0

    def test_low_confidence_no_position(self) -> None:
        """低置信度不开仓"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "j.jsonl")
            bus = _make_bus()
            pm = _make_position_manager(
                bus,
                path,
                config={
                    "paper_trading": True,
                    "initial_balance": 10000.0,
                    "max_positions": 3,
                    "risk_per_trade": 0.02,
                    "min_confidence": 0.9,
                    "journal_path": path,
                    "executor": {
                        "paper_trading": True,
                        "initial_balance": 10000.0,
                    },
                    "stop_loss": {
                        "method": "fixed",
                        "fixed_percentage": 0.02,
                    },
                    "signal_exit": {
                        "signal_reversal_enabled": True,
                    },
                },
            )
            opened: List[Dict[str, Any]] = []

            bus.subscribe(
                "position.opened",
                lambda n, d: opened.append(d),
            )

            bus.emit(
                "trading.signal",
                {
                    "symbol": "BTC/USDT",
                    "signal": TradingSignal.BUY,
                    "confidence": 0.3,
                    "entry_price": 50000.0,
                    "stop_loss": 49000.0,
                    "df": make_ohlcv(n=30),
                },
            )

            assert len(opened) == 0

    def test_missing_data_dict_ignored(self) -> None:
        """ohlcv_ready 无 data_dict 被忽略"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        captured: List[Dict[str, Any]] = []

        bus.subscribe(
            "trading.signal",
            lambda n, d: captured.append(d),
        )

        bus.emit(
            "data_pipeline.ohlcv_ready",
            {"symbol": "BTC/USDT"},
        )

        assert len(captured) == 0

    def test_orchestrator_engine_none_returns_none(self) -> None:
        """Engine 为 None 时优雅返回"""
        bus = _make_bus()
        orch = _make_orchestrator(bus)
        orch._engine = None

        result = orch._process_market_data(
            "BTC/USDT",
            ["H4"],
            {},
        )
        assert result is None

    def test_no_entry_price_skips_open(self) -> None:
        """无入场价格跳过开仓"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "j.jsonl")
            bus = _make_bus()
            pm = _make_position_manager(bus, path)
            opened: List[Dict[str, Any]] = []

            bus.subscribe(
                "position.opened",
                lambda n, d: opened.append(d),
            )

            bus.emit(
                "trading.signal",
                {
                    "symbol": "BTC/USDT",
                    "signal": TradingSignal.BUY,
                    "confidence": 0.8,
                    # 无 entry_price
                },
            )

            assert len(opened) == 0
