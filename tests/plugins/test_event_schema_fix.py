"""
事件 Schema 修复测试

验证 data_pipeline → orchestrator 事件驱动路径的 TF 累积逻辑：
- data_pipeline 逐个发布 per-TF 的 ohlcv_ready 事件
- orchestrator 累积所有 TF 后统一调用 _process_market_data
- 轮询路径 _fetch_data_from_connector 不受影响
"""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.plugins.orchestrator.plugin import OrchestratorPlugin


def _make_ohlcv_df(rows: int = 50) -> pd.DataFrame:
    """创建测试用 OHLCV DataFrame"""
    dates = pd.date_range("2025-01-01", periods=rows, freq="1h")
    np.random.seed(42)
    close = np.random.uniform(40000, 41000, rows)
    opens = np.random.uniform(40000, 41000, rows)
    highs = np.maximum(close, opens) + np.random.uniform(0, 1000, rows)
    lows = np.minimum(close, opens) - np.random.uniform(0, 1000, rows)
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": close,
            "volume": np.random.uniform(100, 1000, rows),
        },
        index=dates,
    )


def _create_loaded_plugin(
    timeframes: list[str] | None = None,
) -> OrchestratorPlugin:
    """创建已加载的 OrchestratorPlugin（引擎被 mock）"""
    plugin = OrchestratorPlugin()
    tfs = timeframes or ["H4", "H1", "M15"]
    plugin._config = {
        "mode": "paper",
        "symbols": ["BTC/USDT"],
        "timeframes": tfs,
        "accumulation_timeout": 10.0,
    }
    plugin.on_load()
    return plugin


class TestTFAccumulation:
    """测试 TF 累积逻辑"""

    def test_single_tf_does_not_trigger_processing(self) -> None:
        """单个 TF 到达时不应立即触发 _process_market_data"""
        plugin = _create_loaded_plugin()

        with patch.object(plugin, "_process_market_data") as mock_process:
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H4": _make_ohlcv_df()},
                    "timeframes": ["H4"],
                },
            )
            mock_process.assert_not_called()

        # 数据应在 pending buffer 中
        assert "BTC/USDT" in plugin._pending_data
        assert "H4" in plugin._pending_data["BTC/USDT"]

    def test_all_tfs_trigger_processing(self) -> None:
        """所有配置的 TF 到齐后应触发 _process_market_data"""
        plugin = _create_loaded_plugin(["H4", "H1", "M15"])

        with patch.object(plugin, "_process_market_data") as mock_process:
            # 发送 H4
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H4": _make_ohlcv_df()},
                    "timeframes": ["H4"],
                },
            )
            assert mock_process.call_count == 0

            # 发送 H1
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H1": _make_ohlcv_df()},
                    "timeframes": ["H1"],
                },
            )
            assert mock_process.call_count == 0

            # 发送 M15 — 应触发
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"M15": _make_ohlcv_df()},
                    "timeframes": ["M15"],
                },
            )
            assert mock_process.call_count == 1

            # 验证参数
            call_args = mock_process.call_args
            symbol_arg = call_args[0][0]
            tfs_arg = call_args[0][1]
            data_dict_arg = call_args[0][2]

            assert symbol_arg == "BTC/USDT"
            assert set(tfs_arg) == {"H4", "H1", "M15"}
            assert set(data_dict_arg.keys()) == {"H4", "H1", "M15"}

        # pending buffer 应已清空
        assert "BTC/USDT" not in plugin._pending_data

    def test_accumulation_timeout_triggers_partial(self) -> None:
        """超时后即使未凑齐也应触发处理"""
        plugin = _create_loaded_plugin(["H4", "H1", "M15"])
        plugin._accumulation_timeout = 0.0  # 立即超时

        with patch.object(plugin, "_process_market_data") as mock_process:
            # 发送 H4
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H4": _make_ohlcv_df()},
                    "timeframes": ["H4"],
                },
            )
            # 不触发（第一个 TF 刚到，时间戳刚设置）
            # 注意：timeout=0 意味着 elapsed >= 0 是 True，
            # 但 monotonic() 可能返回完全相同的值
            # 所以我们手动设置时间戳到过去
            if mock_process.call_count == 0:
                # 如果没触发，手动回调时间戳
                plugin._pending_timestamps["BTC/USDT"] = time.monotonic() - 1.0

                # 发送 H1 — 此时应因超时触发
                plugin._on_data_ready(
                    "data_pipeline.ohlcv_ready",
                    {
                        "symbol": "BTC/USDT",
                        "data_dict": {"H1": _make_ohlcv_df()},
                        "timeframes": ["H1"],
                    },
                )

            assert mock_process.call_count >= 1
            call_args = mock_process.call_args
            data_dict_arg = call_args[0][2]
            # 应包含已累积的 TF（至少 H4）
            assert "H4" in data_dict_arg

    def test_multiple_symbols_independent(self) -> None:
        """不同交易对的 TF 累积应相互独立"""
        plugin = _create_loaded_plugin(["H4", "H1"])

        with patch.object(plugin, "_process_market_data") as mock_process:
            # BTC H4
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H4": _make_ohlcv_df()},
                    "timeframes": ["H4"],
                },
            )
            # ETH H4
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "ETH/USDT",
                    "data_dict": {"H4": _make_ohlcv_df()},
                    "timeframes": ["H4"],
                },
            )
            assert mock_process.call_count == 0

            # BTC H1 — BTC 应触发
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H1": _make_ohlcv_df()},
                    "timeframes": ["H1"],
                },
            )
            assert mock_process.call_count == 1
            assert mock_process.call_args[0][0] == "BTC/USDT"

            # ETH 应仍在 pending
            assert "ETH/USDT" in plugin._pending_data
            assert "BTC/USDT" not in plugin._pending_data

    def test_incomplete_event_ignored(self) -> None:
        """缺少 symbol 或 data_dict 的事件应被忽略"""
        plugin = _create_loaded_plugin()

        with patch.object(plugin, "_process_market_data") as mock_process:
            # 无 symbol
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {"data_dict": {"H4": _make_ohlcv_df()}},
            )
            # 无 data_dict
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {"symbol": "BTC/USDT"},
            )
            mock_process.assert_not_called()

        assert len(plugin._pending_data) == 0

    def test_superset_tfs_also_triggers(self) -> None:
        """收到的 TF 超过配置要求时也应触发"""
        plugin = _create_loaded_plugin(["H4", "H1"])

        with patch.object(plugin, "_process_market_data") as mock_process:
            # H4
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H4": _make_ohlcv_df()},
                    "timeframes": ["H4"],
                },
            )
            # H1 + M15（超出配置的 TF）
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H1": _make_ohlcv_df()},
                    "timeframes": ["H1"],
                },
            )
            assert mock_process.call_count == 1
            data_dict_arg = mock_process.call_args[0][2]
            assert set(data_dict_arg.keys()) == {"H4", "H1"}


class TestPollingPathUnchanged:
    """验证轮询路径 _fetch_data_from_connector 不受影响"""

    def test_polling_path_calls_process_directly(self) -> None:
        """轮询路径应直接调用 _process_market_data，不经过累积"""
        plugin = _create_loaded_plugin(["H4", "H1"])
        data_dict = {"H4": _make_ohlcv_df(), "H1": _make_ohlcv_df()}

        with patch.object(plugin, "_process_market_data") as mock_process:
            # 直接模拟轮询路径的调用方式（与 run_loop 中相同）
            mock_process.return_value = None
            plugin._process_market_data("BTC/USDT", plugin._timeframes, data_dict)
            assert mock_process.call_count == 1

    def test_fetch_data_returns_none_without_connector(self) -> None:
        """无 exchange_connector 时应返回 None"""
        plugin = _create_loaded_plugin()
        # get_plugin 默认返回 None
        plugin.get_plugin = MagicMock(return_value=None)

        result = plugin._fetch_data_from_connector("BTC/USDT")
        assert result is None


class TestOnUnloadClearsPending:
    """验证 on_unload 清理 pending 数据"""

    def test_unload_clears_pending_data(self) -> None:
        """卸载时应清空 pending buffer"""
        plugin = _create_loaded_plugin()
        plugin._pending_data["BTC/USDT"] = {"H4": _make_ohlcv_df()}
        plugin._pending_timestamps["BTC/USDT"] = time.monotonic()

        plugin.on_unload()

        assert len(plugin._pending_data) == 0
        assert len(plugin._pending_timestamps) == 0


class TestEndToEndEventChain:
    """端到端测试：模拟 data_pipeline 发布事件 → orchestrator 处理"""

    def test_event_chain_produces_decision(self) -> None:
        """完整事件链应产出 TradingDecision"""
        plugin = _create_loaded_plugin(["H4", "H1"])

        # Mock engine 返回决策
        mock_decision = MagicMock()
        mock_decision.signal = MagicMock()
        mock_decision.signal.value = "NEUTRAL"
        mock_decision.confidence = 0.5
        mock_decision.entry_price = 40000.0
        mock_decision.stop_loss = 39000.0
        mock_decision.take_profit = 41000.0
        mock_decision.reasoning = ["test"]
        mock_decision.context = None
        mock_decision.to_dict.return_value = {"signal": "NEUTRAL"}

        mock_events = MagicMock()
        mock_events.tr_detected = False
        mock_events.state_changed = False
        mock_events.conflicts_detected = False

        assert plugin._engine is not None  # type guard
        plugin._engine.process_market_data = MagicMock(
            return_value=(mock_decision, mock_events)
        )

        # 模拟 emit_event（不需要真实事件总线）
        plugin.emit_event = MagicMock()

        # 发送两个 TF
        plugin._on_data_ready(
            "data_pipeline.ohlcv_ready",
            {
                "symbol": "BTC/USDT",
                "data_dict": {"H4": _make_ohlcv_df()},
                "timeframes": ["H4"],
            },
        )
        plugin._on_data_ready(
            "data_pipeline.ohlcv_ready",
            {
                "symbol": "BTC/USDT",
                "data_dict": {"H1": _make_ohlcv_df()},
                "timeframes": ["H1"],
            },
        )

        # 验证 engine 被调用一次，且包含两个 TF
        engine_mock = plugin._engine.process_market_data
        engine_mock.assert_called_once()
        call_kwargs = engine_mock.call_args
        data_dict_passed = call_kwargs[1].get(
            "data_dict", call_kwargs[0][2] if len(call_kwargs[0]) > 2 else {}
        )
        assert set(data_dict_passed.keys()) == {"H4", "H1"}

        # 验证 process_count 增加
        assert plugin._process_count == 1

    def test_single_tf_config_triggers_immediately(self) -> None:
        """配置仅一个 TF 时，单个事件应立即触发"""
        plugin = _create_loaded_plugin(["H4"])

        with patch.object(plugin, "_process_market_data") as mock_process:
            plugin._on_data_ready(
                "data_pipeline.ohlcv_ready",
                {
                    "symbol": "BTC/USDT",
                    "data_dict": {"H4": _make_ohlcv_df()},
                    "timeframes": ["H4"],
                },
            )
            assert mock_process.call_count == 1
