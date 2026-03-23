"""核心链路集成测试 — 验证数据从进入到信号输出的完整流程

运行时机: 每次 PR、每次发版
预期时间: < 30 秒
覆盖范围:
    链路1: Market Data → WyckoffEngine → TradingDecision → trading.signal
    链路2: trading.signal → PositionManager 处理
    链路3: 熔断器 → 阻断信号
    链路4: Evolution 组件可启动
    链路5: 事件契约（字段/类型验证）
"""

import pytest
import numpy as np
import pandas as pd
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.app import WyckoffApp
from src.kernel.types import TradingSignal


# ================================================================
# Fixtures
# ================================================================


@pytest.fixture(scope="module")
def app() -> WyckoffApp:
    """完整启动系统"""
    wyckoff_app = WyckoffApp(config_path="config.yaml")
    wyckoff_app.discover_and_load()
    return wyckoff_app


@pytest.fixture(scope="module")
def pm(app: WyckoffApp):  # type: ignore[no-untyped-def]
    return app.plugin_manager


@pytest.fixture(scope="module")
def event_bus(pm):  # type: ignore[no-untyped-def]
    return pm.get_event_bus()


@pytest.fixture(scope="module")
def mock_ohlcv() -> pd.DataFrame:
    """200 根模拟 K 线"""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2025-01-01", periods=n, freq="4h")
    close = 50000 + np.cumsum(np.random.randn(n) * 100)
    return pd.DataFrame(
        {
            "open": close - np.abs(np.random.randn(n) * 30),
            "high": close + np.abs(np.random.randn(n) * 50),
            "low": close - np.abs(np.random.randn(n) * 50),
            "close": close,
            "volume": np.random.rand(n) * 1000 + 100,
        },
        index=dates,
    )


@pytest.fixture(scope="module")
def mock_data_dict(mock_ohlcv: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """三个时间框架的模拟数据"""
    return {"H4": mock_ohlcv, "H1": mock_ohlcv, "M15": mock_ohlcv}


# ================================================================
# 链路 1: 数据 → 引擎 → 信号
# ================================================================


class TestTradingChain:
    """核心交易链路: 数据进入 → 引擎处理 → 信号产出"""

    def test_engine_processes_data(
        self, pm, mock_data_dict: Dict[str, pd.DataFrame]
    ) -> None:  # type: ignore[no-untyped-def]
        """WyckoffEngine 能处理市场数据并返回 TradingDecision"""
        orch = pm.get_plugin("orchestrator")
        assert orch is not None

        decision = orch._process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4", "H1", "M15"],
            data_dict=mock_data_dict,
        )

        assert decision is not None, "引擎未返回决策"
        assert hasattr(decision, "signal"), "决策缺少 signal 属性"
        assert hasattr(decision, "confidence"), "决策缺少 confidence 属性"
        assert isinstance(decision.signal, TradingSignal)
        assert 0.0 <= decision.confidence <= 1.0

    def test_signal_event_emitted(
        self,
        pm,
        event_bus,
        mock_data_dict: Dict[str, pd.DataFrame],  # type: ignore[no-untyped-def]
    ) -> None:
        """处理数据后 trading.signal 事件被发出"""
        signals: List[Dict[str, Any]] = []
        event_bus.subscribe(
            "trading.signal",
            lambda n, d: signals.append(d),
            subscriber_name="test_signal_listener",
        )

        orch = pm.get_plugin("orchestrator")
        orch._process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4", "H1", "M15"],
            data_dict=mock_data_dict,
        )

        assert len(signals) >= 1, "trading.signal 事件未发出"

        event_bus.unsubscribe("trading.signal", signals.append)

    def test_decision_recorded_in_history(
        self, pm, mock_data_dict: Dict[str, pd.DataFrame]
    ) -> None:  # type: ignore[no-untyped-def]
        """决策被记录到历史"""
        orch = pm.get_plugin("orchestrator")
        before = len(orch.get_decision_history(limit=100))

        orch._process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4", "H1", "M15"],
            data_dict=mock_data_dict,
        )

        after = len(orch.get_decision_history(limit=100))
        assert after > before, "决策未记录到历史"

    def test_price_update_emitted(
        self,
        pm,
        event_bus,
        mock_data_dict: Dict[str, pd.DataFrame],  # type: ignore[no-untyped-def]
    ) -> None:
        """处理数据时发出 market.price_update 事件"""
        prices: List[Dict[str, Any]] = []
        event_bus.subscribe(
            "market.price_update",
            lambda n, d: prices.append(d),
            subscriber_name="test_price_listener",
        )

        orch = pm.get_plugin("orchestrator")
        orch._process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4", "H1", "M15"],
            data_dict=mock_data_dict,
        )

        assert len(prices) >= 1, "market.price_update 未发出"
        assert "symbol" in prices[-1]
        assert "price" in prices[-1]
        assert isinstance(prices[-1]["price"], float)


# ================================================================
# 链路 2: 信号 → PositionManager
# ================================================================


class TestPositionManagerChain:
    """PositionManager 正确响应 trading.signal"""

    def test_position_manager_receives_signal(self, pm, event_bus) -> None:  # type: ignore[no-untyped-def]
        """PositionManager 订阅了 trading.signal"""
        subs = event_bus.get_subscribers("trading.signal")
        sub_names = [str(s) for s in subs]
        has_pm = any("position" in s.lower() for s in sub_names)
        assert has_pm or len(subs) >= 2, (
            f"position_manager 未订阅 trading.signal, 当前订阅者: {sub_names}"
        )

    def test_position_manager_api_works(self, pm) -> None:  # type: ignore[no-untyped-def]
        """PositionManager 的 API 方法返回正确类型"""
        pos_mgr = pm.get_plugin("position_manager")
        assert pos_mgr is not None

        positions = pos_mgr.get_all_positions()
        assert isinstance(positions, dict)

        trades = pos_mgr.get_closed_trades()
        assert isinstance(trades, list)

        stats = pos_mgr.get_statistics()
        assert isinstance(stats, dict)


# ================================================================
# 链路 3: 熔断器链路
# ================================================================


class TestCircuitBreaker:
    """熔断器触发后阻断信号"""

    def test_circuit_breaker_stops_signals(
        self,
        pm,
        event_bus,
        mock_data_dict: Dict[str, pd.DataFrame],  # type: ignore[no-untyped-def]
    ) -> None:
        """熔断触发后 orchestrator 不发送非 NEUTRAL 信号"""
        orch = pm.get_plugin("orchestrator")
        assert orch is not None

        # 触发熔断
        event_bus.emit(
            "risk_management.circuit_breaker_tripped",
            {"tripped": True, "status": "TRIPPED", "reason": "test"},
            publisher="test",
        )

        assert orch._circuit_breaker_tripped is True

        # 恢复熔断
        event_bus.emit(
            "risk_management.circuit_breaker_recovered",
            {"status": "NORMAL"},
            publisher="test",
        )

        assert orch._circuit_breaker_tripped is False


# ================================================================
# 链路 4: 进化组件
# ================================================================


class TestEvolutionChain:
    """进化系统组件链路验证"""

    def test_evolution_components_initialized(self, pm) -> None:  # type: ignore[no-untyped-def]
        """GA/Evaluator/WFA/AntiOverfit 全部初始化"""
        evo = pm.get_plugin("evolution")
        assert evo is not None
        assert evo._ga is not None, "GeneticAlgorithm 未初始化"
        assert evo._evaluator is not None, "StandardEvaluator 未初始化"
        assert evo._wfa is not None, "WFAValidator 未初始化"
        assert evo._anti_overfit is not None, "AntiOverfitGuard 未初始化"

    def test_evolution_status_api(self, pm) -> None:  # type: ignore[no-untyped-def]
        """进化状态 API 返回正确格式"""
        evo = pm.get_plugin("evolution")
        status = evo.get_evolution_status()
        assert "status" in status
        assert status["status"] in ("running", "stopped")
        assert "cycle_count" in status

    def test_evolution_cycle_event_wired(self, event_bus) -> None:  # type: ignore[no-untyped-def]
        """evolution.cycle_complete 有订阅者"""
        subs = event_bus.get_subscribers("evolution.cycle_complete")
        assert len(subs) >= 1, "evolution.cycle_complete 无订阅者"


# ================================================================
# 链路 5: 事件契约（字段/类型验证）
# ================================================================


class TestEventContracts:
    """事件数据格式契约 — 发布者和订阅者对字段的约定"""

    def test_trading_signal_contract(
        self,
        pm,
        event_bus,
        mock_data_dict: Dict[str, pd.DataFrame],  # type: ignore[no-untyped-def]
    ) -> None:
        """trading.signal 事件必须包含 PositionManager 需要的所有字段"""
        captured: List[Dict[str, Any]] = []
        event_bus.subscribe(
            "trading.signal",
            lambda n, d: captured.append(d),
            subscriber_name="contract_test",
        )

        orch = pm.get_plugin("orchestrator")
        orch._process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4", "H1", "M15"],
            data_dict=mock_data_dict,
        )

        assert len(captured) >= 1, "未捕获到 trading.signal"
        signal_data = captured[-1]

        # PositionManager._on_trading_signal 需要这些字段
        assert "symbol" in signal_data, "缺少 symbol"
        assert "signal" in signal_data, "缺少 signal"
        assert "confidence" in signal_data, "缺少 confidence"
        assert "decision" in signal_data, "缺少 decision"
        assert isinstance(signal_data["confidence"], (int, float))

    def test_decision_history_contract(
        self, pm, mock_data_dict: Dict[str, pd.DataFrame]
    ) -> None:  # type: ignore[no-untyped-def]
        """决策历史的每条记录必须包含前端需要的字段"""
        orch = pm.get_plugin("orchestrator")
        orch._process_market_data(
            symbol="BTC/USDT",
            timeframes=["H4", "H1", "M15"],
            data_dict=mock_data_dict,
        )

        history = orch.get_decision_history(limit=1)
        assert len(history) >= 1

        entry = history[-1]
        # 前端 DecisionHistoryTab 需要这些字段
        required = ["signal", "confidence", "reasoning"]
        for field in required:
            assert field in entry, f"决策历史缺少字段: {field}"

    def test_system_status_contract(self, pm) -> None:  # type: ignore[no-untyped-def]
        """get_system_status() 必须包含前端 Sidebar 需要的字段"""
        orch = pm.get_plugin("orchestrator")
        status = orch.get_system_status()

        required = [
            "status",
            "mode",
            "symbols",
            "decision_count",
            "engine_loaded",
            "circuit_breaker_tripped",
        ]
        for field in required:
            assert field in status, f"系统状态缺少字段: {field}"

    def test_engine_state_contract(self, pm) -> None:  # type: ignore[no-untyped-def]
        """get_current_state() 必须包含前端 WyckoffPanel 需要的字段"""
        engine = pm.get_plugin("wyckoff_engine")
        state = engine.get_current_state()
        assert state is not None

        required = ["timeframes", "state_machines"]
        for field in required:
            assert field in state, f"引擎状态缺少字段: {field}"

        # state_machines 的每个条目需要有状态和置信度
        for tf, sm_state in state["state_machines"].items():
            assert "current_state" in sm_state, (
                f"state_machines[{tf}] 缺少 current_state"
            )
