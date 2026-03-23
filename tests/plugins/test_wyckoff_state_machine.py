"""
Wyckoff State Machine 插件测试 - 第1部分

测试初始化、加载/卸载、配置更新、健康检查
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginError
from src.plugins.wyckoff_state_machine.plugin import (
    WyckoffStateMachinePlugin,
)


class TestWyckoffSMInit:
    """测试插件初始化"""

    def test_default_name(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        assert plugin.name == "wyckoff_state_machine"

    def test_custom_name(self) -> None:
        plugin = WyckoffStateMachinePlugin(name="my_sm")
        assert plugin.name == "my_sm"

    def test_inherits_base(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        assert isinstance(plugin, BasePlugin)

    def test_initial_attrs(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        assert plugin._state_machine is None
        assert plugin._enhanced_sm is None
        assert plugin._candle_count == 0
        assert plugin._transition_count == 0
        assert plugin._signal_count == 0
        assert plugin._last_error is None


class TestWyckoffSMLoadUnload:
    """测试加载/卸载"""

    @patch("src.plugins.wyckoff_state_machine.state_machine_v4.WyckoffStateMachineV4")
    def test_load_success(self, mock_esm: MagicMock) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin.on_load()
        assert plugin._state_machine is not None
        assert plugin._enhanced_sm is not None
        # 单实例：_state_machine 和 _enhanced_sm 指向同一对象
        assert plugin._state_machine is plugin._enhanced_sm

    @patch(
        "src.plugins.wyckoff_state_machine.state_machine_v4.WyckoffStateMachineV4",
        side_effect=ImportError("not found"),
    )
    def test_load_import_error(self, mock_cls: MagicMock) -> None:
        plugin = WyckoffStateMachinePlugin()
        with pytest.raises(PluginError):
            plugin.on_load()
        assert plugin._state_machine is None
        assert plugin._enhanced_sm is None

    @patch(
        "src.plugins.wyckoff_state_machine.state_machine_v4.WyckoffStateMachineV4",
        side_effect=RuntimeError("init fail"),
    )
    def test_load_runtime_error(self, mock_esm: MagicMock) -> None:
        plugin = WyckoffStateMachinePlugin()
        with pytest.raises(PluginError):
            plugin.on_load()
        assert plugin._last_error == "init fail"

    def test_unload(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin._state_machine = MagicMock()
        plugin._enhanced_sm = MagicMock()
        plugin.on_unload()
        assert plugin._state_machine is None
        assert plugin._enhanced_sm is None

    def test_unload_when_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin.on_unload()
        assert plugin._state_machine is None


class TestWyckoffSMConfig:
    """测试配置更新"""

    def test_config_update_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_config = MagicMock()
        mock_sm.config = mock_config
        plugin._state_machine = mock_sm

        plugin.on_config_update({"heritage_decay": 0.9})
        mock_config.update_from_dict.assert_called_once_with({"heritage_decay": 0.9})

    def test_config_update_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin.on_config_update({"heritage_decay": 0.9})


class TestWyckoffSMHealth:
    """测试健康检查"""

    def test_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        result = plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY

    def test_healthy(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin._state_machine = MagicMock()
        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    def test_degraded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin._state_machine = MagicMock()
        plugin._last_error = "some error"
        result = plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert result.details["last_error"] == "some error"

    def test_health_with_counts(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin._state_machine = MagicMock()
        plugin._candle_count = 100
        plugin._transition_count = 5
        plugin._signal_count = 3
        result = plugin.health_check()
        assert result.details["candle_count"] == 100
        assert result.details["transition_count"] == 5
        assert result.details["signal_count"] == 3


class TestWyckoffSMProcessCandle:
    """测试 process_candle"""

    def test_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        result = plugin.process_candle({"close": 100})
        assert result is None

    def test_success_with_result(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        # process_candle 现在返回 str（状态名）
        mock_sm.process_candle.return_value = "accumulation"
        mock_sm.state_confidences = {"accumulation": 0.85}
        mock_sm.state_intensities = {"accumulation": 0.7}
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.process_candle({"close": 100})
        assert result is not None
        assert result["state_name"] == "accumulation"
        assert result["confidence"] == 0.85
        assert result["intensity"] == 0.7
        assert plugin._candle_count == 1

    def test_state_transition(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.process_candle.return_value = "markup"
        mock_sm.state_confidences = {"markup": 0.9}
        mock_sm.state_intensities = {"markup": 0.8}
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)
        # 设置前一个状态，以触发状态变化检测
        plugin._prev_state = "accumulation"

        plugin.process_candle({"close": 100})
        assert plugin._transition_count == 1
        # 应发射 state_changed 和 candle_processed 两个事件
        assert plugin.emit_event.call_count == 2

    def test_no_transition_same_state(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.process_candle.return_value = "accumulation"
        mock_sm.state_confidences = {"accumulation": 0.8}
        mock_sm.state_intensities = {"accumulation": 0.6}
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)
        plugin._prev_state = "accumulation"

        plugin.process_candle({"close": 100})
        assert plugin._transition_count == 0
        # 只发射 candle_processed
        assert plugin.emit_event.call_count == 1

    def test_none_result(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.process_candle.return_value = None
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.process_candle({"close": 100})
        assert result is None
        assert plugin._candle_count == 1

    def test_error_handling(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.process_candle.side_effect = RuntimeError("boom")
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.process_candle({"close": 100})
        assert result is None
        assert plugin._last_error == "boom"
        plugin.emit_event.assert_called_once_with(
            "state_machine.error_occurred",
            {"error": "boom", "operation": "process_candle"},
        )


class TestWyckoffSMMultiTimeframe:
    """测试 process_multi_timeframe"""

    def test_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        result = plugin.process_multi_timeframe({"1h": pd.DataFrame()})
        assert result is None

    def test_success(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.process_multi_timeframe.return_value = {"consensus": "bullish"}
        plugin._enhanced_sm = mock_esm

        result = plugin.process_multi_timeframe({"1h": pd.DataFrame()})
        assert result == {"consensus": "bullish"}
        # 验证传递了两个参数（timeframe_data + 空 context_dict）
        mock_esm.process_multi_timeframe.assert_called_once()
        call_args = mock_esm.process_multi_timeframe.call_args[0]
        assert "1h" in call_args[0]
        assert call_args[1] == {}

    def test_error(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.process_multi_timeframe.side_effect = ValueError("bad")
        plugin._enhanced_sm = mock_esm

        result = plugin.process_multi_timeframe({"1h": pd.DataFrame()})
        assert result is None
        assert plugin._last_error == "bad"


class TestWyckoffSMGenerateSignals:
    """测试 generate_signals"""

    def test_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        result = plugin.generate_signals(pd.DataFrame())
        assert result is None

    def test_success_with_signal(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        # generate_signals() 现在返回 list[dict]
        mock_esm.generate_signals.return_value = [{"type": "BUY", "confidence": 0.9}]
        plugin._enhanced_sm = mock_esm
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.generate_signals(pd.DataFrame())
        assert result == [{"type": "BUY", "confidence": 0.9}]
        assert plugin._signal_count == 1
        plugin.emit_event.assert_called_once()
        # generate_signals 不传参数（修复 C-04）
        mock_esm.generate_signals.assert_called_once_with()

    def test_no_signal(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.generate_signals.return_value = None
        plugin._enhanced_sm = mock_esm
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.generate_signals(pd.DataFrame())
        assert result is None
        assert plugin._signal_count == 0
        plugin.emit_event.assert_not_called()

    def test_empty_list_signal(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.generate_signals.return_value = []
        plugin._enhanced_sm = mock_esm
        plugin.emit_event = MagicMock(return_value=1)

        result = plugin.generate_signals(pd.DataFrame())
        assert result == []
        assert plugin._signal_count == 0

    def test_error(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.generate_signals.side_effect = RuntimeError("fail")
        plugin._enhanced_sm = mock_esm

        result = plugin.generate_signals(pd.DataFrame())
        assert result is None
        assert plugin._last_error == "fail"


class TestWyckoffSMStateReport:
    """测试 get_state_report"""

    def test_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        result = plugin.get_state_report()
        assert result["status"] == "not_loaded"

    def test_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.get_state_report.return_value = {
            "phase": "accumulation",
            "confidence": 0.8,
        }
        plugin._state_machine = mock_sm

        result = plugin.get_state_report()
        assert result["phase"] == "accumulation"

    def test_error(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.get_state_report.side_effect = RuntimeError("err")
        plugin._state_machine = mock_sm

        result = plugin.get_state_report()
        assert result["status"] == "error"
        assert result["error"] == "err"
        assert plugin._last_error == "err"


class TestWyckoffSMCurrentStateInfo:
    """测试 get_current_state_info"""

    def test_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        result = plugin.get_current_state_info()
        assert result["status"] == "not_loaded"

    def test_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.get_current_state_info.return_value = {
            "state": "markup",
            "direction": "up",
        }
        plugin._enhanced_sm = mock_esm

        result = plugin.get_current_state_info()
        assert result["state"] == "markup"

    def test_error(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.get_current_state_info.side_effect = ValueError("bad")
        plugin._enhanced_sm = mock_esm

        result = plugin.get_current_state_info()
        assert result["status"] == "error"
        assert plugin._last_error == "bad"


class TestWyckoffSMOptimize:
    """测试 optimize_parameters"""

    def test_not_loaded(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        result = plugin.optimize_parameters(pd.DataFrame())
        assert result is None

    def test_success(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.optimize_parameters.return_value = {"best_params": {"decay": 0.95}}
        plugin._enhanced_sm = mock_esm

        result = plugin.optimize_parameters(pd.DataFrame(), {"iterations": 100})
        assert result == {"best_params": {"decay": 0.95}}
        mock_esm.optimize_parameters.assert_called_once()
        args = mock_esm.optimize_parameters.call_args
        assert isinstance(args[0][0], pd.DataFrame)
        assert args[0][1] == {"iterations": 100}

    def test_error(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.optimize_parameters.side_effect = RuntimeError("opt fail")
        plugin._enhanced_sm = mock_esm

        result = plugin.optimize_parameters(pd.DataFrame())
        assert result is None
        assert plugin._last_error == "opt fail"


class TestWyckoffSMStatistics:
    """测试 get_statistics"""

    def test_initial_state(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        stats = plugin.get_statistics()
        assert stats["candle_count"] == 0
        assert stats["transition_count"] == 0
        assert stats["signal_count"] == 0
        assert stats["last_error"] is None
        assert stats["state_machine_loaded"] is False
        assert stats["enhanced_sm_loaded"] is False

    def test_after_operations(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        plugin._candle_count = 50
        plugin._transition_count = 3
        plugin._signal_count = 2
        plugin._last_error = "some error"
        plugin._state_machine = MagicMock()
        plugin._enhanced_sm = MagicMock()

        stats = plugin.get_statistics()
        assert stats["candle_count"] == 50
        assert stats["transition_count"] == 3
        assert stats["signal_count"] == 2
        assert stats["last_error"] == "some error"
        assert stats["state_machine_loaded"] is True
        assert stats["enhanced_sm_loaded"] is True


class TestWyckoffSMEventEmission:
    """测试事件发射"""

    def test_candle_processed_event(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.process_candle.return_value = None
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)

        plugin.process_candle({"close": 100})
        plugin.emit_event.assert_called_once_with(
            "state_machine.candle_processed",
            {"candle_count": 1, "has_result": False},
        )

    def test_state_changed_event_data(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        # process_candle 返回 str
        mock_sm.process_candle.return_value = "distribution"
        mock_sm.state_confidences = {"distribution": 0.75}
        mock_sm.state_intensities = {"distribution": 0.6}
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)
        # 设置前一状态以触发 state_changed
        plugin._prev_state = "markup"

        plugin.process_candle({"close": 100})
        calls = plugin.emit_event.call_args_list
        assert len(calls) == 2
        # 第一个调用是 state_changed
        assert calls[0][0][0] == "state_machine.state_changed"
        assert calls[0][0][1]["from_state"] == "markup"
        assert calls[0][0][1]["to_state"] == "distribution"
        assert calls[0][0][1]["confidence"] == 0.75

    def test_signal_generated_event_data(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_esm = MagicMock()
        mock_esm.generate_signals.return_value = [{"type": "SELL", "confidence": 0.8}]
        plugin._enhanced_sm = mock_esm
        plugin.emit_event = MagicMock(return_value=1)

        plugin.generate_signals(pd.DataFrame())
        plugin.emit_event.assert_called_once_with(
            "state_machine.signal_generated",
            {"signal_count": 1, "signal_type": "SELL"},
        )

    def test_error_event_data(self) -> None:
        plugin = WyckoffStateMachinePlugin()
        mock_sm = MagicMock()
        mock_sm.process_candle.side_effect = TypeError("type err")
        plugin._state_machine = mock_sm
        plugin.emit_event = MagicMock(return_value=1)

        plugin.process_candle({"close": 100})
        plugin.emit_event.assert_called_once_with(
            "state_machine.error_occurred",
            {"error": "type err", "operation": "process_candle"},
        )
