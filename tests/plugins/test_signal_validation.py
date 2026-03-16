"""信号验证插件测试"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginState
from src.plugins.signal_validation.plugin import SignalValidationPlugin


class TestSignalValidationPluginInit:
    """测试插件初始化"""

    def test_plugin_creation(self):
        """测试插件创建"""
        plugin = SignalValidationPlugin()
        assert plugin.name == "signal_validation"
        assert isinstance(plugin, BasePlugin)

    def test_plugin_custom_name(self):
        """测试自定义名称"""
        plugin = SignalValidationPlugin(name="custom_sv")
        assert plugin.name == "custom_sv"

    def test_initial_state(self):
        """测试初始状态"""
        plugin = SignalValidationPlugin()
        assert plugin._breakout_validator is None
        assert plugin._micro_entry_validator is None
        assert plugin._conflict_resolver is None
        assert plugin._breakout_detect_count == 0
        assert plugin._entry_validate_count == 0
        assert plugin._conflict_resolve_count == 0
        assert plugin._last_error is None


class TestSignalValidationHealthCheck:
    """测试健康检查"""

    def test_healthy_state(self):
        """测试健康状态"""
        plugin = SignalValidationPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._breakout_validator = MagicMock()
        plugin._micro_entry_validator = MagicMock()
        plugin._conflict_resolver = MagicMock()

        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert "正常" in result.message

    def test_unhealthy_not_active(self):
        """测试非活跃状态"""
        plugin = SignalValidationPlugin()
        plugin._state = PluginState.UNLOADED

        result = plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未处于活跃" in result.message

    def test_unhealthy_missing_components(self):
        """测试缺少组件"""
        plugin = SignalValidationPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._breakout_validator = MagicMock()

        result = plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未初始化" in result.message

    def test_degraded_with_error(self):
        """测试有错误时降级"""
        plugin = SignalValidationPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._breakout_validator = MagicMock()
        plugin._micro_entry_validator = MagicMock()
        plugin._conflict_resolver = MagicMock()
        plugin._last_error = "test error"

        result = plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "错误" in result.message


class TestSignalValidationPluginLoad:
    """测试插件加载和卸载"""

    @patch("src.plugins.signal_validation.conflict_resolver.ConflictResolutionManager")
    @patch("src.plugins.signal_validation.micro_entry_validator.MicroEntryValidator")
    @patch("src.plugins.signal_validation.breakout_validator.BreakoutValidator")
    def test_on_load_creates_components(
        self, mock_bv, mock_me, mock_cr
    ):
        """测试加载时创建三个组件"""
        plugin = SignalValidationPlugin()
        plugin._config = {}
        plugin.on_load()

        mock_bv.assert_called_once()
        mock_me.assert_called_once()
        mock_cr.assert_called_once()
        assert plugin._breakout_validator is not None
        assert plugin._micro_entry_validator is not None
        assert plugin._conflict_resolver is not None

    @patch("src.plugins.signal_validation.conflict_resolver.ConflictResolutionManager")
    @patch("src.plugins.signal_validation.micro_entry_validator.MicroEntryValidator")
    @patch("src.plugins.signal_validation.breakout_validator.BreakoutValidator")
    def test_on_load_with_config(
        self, mock_bv, mock_me, mock_cr
    ):
        """测试带配置的加载"""
        plugin = SignalValidationPlugin()
        plugin._config = {
            "breakout_validator": {"atr_multiplier": 2.0},
            "micro_entry_validator": {"volume_threshold": 2.0},
            "conflict_resolver": {"conflict_threshold": 0.5},
        }
        plugin.on_load()

        mock_bv.assert_called_once_with(
            config={"atr_multiplier": 2.0}
        )
        mock_me.assert_called_once_with(
            config={"volume_threshold": 2.0}
        )
        mock_cr.assert_called_once_with(
            config={"conflict_threshold": 0.5}
        )

    @patch("src.plugins.signal_validation.conflict_resolver.ConflictResolutionManager")
    @patch("src.plugins.signal_validation.micro_entry_validator.MicroEntryValidator")
    @patch("src.plugins.signal_validation.breakout_validator.BreakoutValidator")
    def test_on_load_none_config(
        self, mock_bv, mock_me, mock_cr
    ):
        """测试无配置时使用空字典"""
        plugin = SignalValidationPlugin()
        plugin._config = None
        plugin.on_load()

        mock_bv.assert_called_once_with(config={})
        mock_me.assert_called_once_with(config={})
        mock_cr.assert_called_once_with(config={})

    @patch("src.plugins.signal_validation.conflict_resolver.ConflictResolutionManager")
    @patch("src.plugins.signal_validation.micro_entry_validator.MicroEntryValidator")
    @patch("src.plugins.signal_validation.breakout_validator.BreakoutValidator")
    def test_on_unload_clears_all(
        self, mock_bv, mock_me, mock_cr
    ):
        """测试卸载清理所有状态"""
        plugin = SignalValidationPlugin()
        plugin._config = {}
        plugin.on_load()

        plugin._breakout_detect_count = 5
        plugin._entry_validate_count = 3
        plugin._conflict_resolve_count = 2
        plugin._last_error = "some error"

        plugin.on_unload()

        assert plugin._breakout_validator is None
        assert plugin._micro_entry_validator is None
        assert plugin._conflict_resolver is None
        assert plugin._breakout_detect_count == 0
        assert plugin._entry_validate_count == 0
        assert plugin._conflict_resolve_count == 0
        assert plugin._last_error is None


class TestBreakoutValidationAPI:
    """测试突破验证 API"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = SignalValidationPlugin()
        self.plugin._breakout_validator = MagicMock()
        self.plugin._micro_entry_validator = MagicMock()
        self.plugin._conflict_resolver = MagicMock()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_detect_breakout_success(self):
        """测试成功检测突破"""
        mock_result = {
            "breakout_id": "breakout_1",
            "direction": 1,
            "breakout_price": 100.0,
            "breakout_strength": 1.5,
            "volume_confirmation": True,
        }
        self.plugin._breakout_validator.detect_initial_breakout.return_value = mock_result
        df = pd.DataFrame({"close": [1, 2, 3]})

        result = self.plugin.detect_breakout(df, 100.0, 90.0, 5.0)

        assert result == mock_result
        assert self.plugin._breakout_detect_count == 1
        self.plugin.emit_event.assert_called_once()

    def test_detect_breakout_no_breakout(self):
        """测试无突破"""
        self.plugin._breakout_validator.detect_initial_breakout.return_value = None
        df = pd.DataFrame({"close": [1, 2, 3]})

        result = self.plugin.detect_breakout(df, 100.0, 90.0, 5.0)

        assert result is None
        assert self.plugin._breakout_detect_count == 1
        self.plugin.emit_event.assert_not_called()

    def test_detect_breakout_not_loaded(self):
        """测试未加载时抛出异常"""
        self.plugin._breakout_validator = None

        with pytest.raises(RuntimeError, match="突破验证器未加载"):
            self.plugin.detect_breakout(
                pd.DataFrame(), 100.0, 90.0, 5.0
            )

    def test_get_breakout_signal(self):
        """测试获取突破信号"""
        mock_signal = {"status": "CONFIRMED"}
        self.plugin._breakout_validator.get_breakout_signal.return_value = mock_signal

        result = self.plugin.get_breakout_signal("breakout_1")
        assert result == mock_signal

    def test_get_breakout_signal_not_loaded(self):
        """测试未加载时获取突破信号"""
        self.plugin._breakout_validator = None

        with pytest.raises(RuntimeError, match="突破验证器未加载"):
            self.plugin.get_breakout_signal("breakout_1")

    def test_cleanup_old_breakouts(self):
        """测试清理过期突破"""
        self.plugin.cleanup_old_breakouts(48)
        self.plugin._breakout_validator.cleanup_old_breakouts.assert_called_once_with(48)

    def test_cleanup_not_loaded(self):
        """测试未加载时清理"""
        self.plugin._breakout_validator = None

        with pytest.raises(RuntimeError, match="突破验证器未加载"):
            self.plugin.cleanup_old_breakouts()


class TestEntryValidationAPI:
    """测试入场验证 API"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = SignalValidationPlugin()
        self.plugin._breakout_validator = MagicMock()
        self.plugin._micro_entry_validator = MagicMock()
        self.plugin._conflict_resolver = MagicMock()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_validate_entry_success(self):
        """测试成功验证入场"""
        mock_result = {
            "signal_type": "LONG",
            "confidence": 0.85,
            "entry_price": 100.0,
            "stop_loss": 95.0,
        }
        self.plugin._micro_entry_validator.validate_entry.return_value = mock_result

        result = self.plugin.validate_entry(
            h4_structure={"trend": "up"},
            m15_data=pd.DataFrame({"close": [1, 2]}),
            m5_data=pd.DataFrame({"close": [1, 2]}),
            macro_bias="bullish",
            market_context={"regime": "trending"},
        )

        assert result == mock_result
        assert self.plugin._entry_validate_count == 1
        self.plugin.emit_event.assert_called_once()

    def test_validate_entry_not_loaded(self):
        """测试未加载时验证入场"""
        self.plugin._micro_entry_validator = None

        with pytest.raises(RuntimeError, match="微观入场验证器未加载"):
            self.plugin.validate_entry(
                h4_structure={},
                m15_data=pd.DataFrame(),
                m5_data=pd.DataFrame(),
                macro_bias="NEUTRAL",
            )

    def test_get_validation_history(self):
        """测试获取验证历史"""
        mock_history = [{"id": 1}, {"id": 2}]
        self.plugin._micro_entry_validator.get_validation_history.return_value = (
            mock_history
        )

        result = self.plugin.get_validation_history(limit=10)
        assert result == mock_history

    def test_get_validation_history_not_loaded(self):
        """测试未加载时获取历史"""
        self.plugin._micro_entry_validator = None

        with pytest.raises(RuntimeError, match="微观入场验证器未加载"):
            self.plugin.get_validation_history()

    def test_clear_validation_history(self):
        """测试清除验证历史"""
        self.plugin.clear_validation_history()
        self.plugin._micro_entry_validator.clear_history.assert_called_once()

    def test_clear_validation_history_not_loaded(self):
        """测试未加载时清除历史"""
        self.plugin._micro_entry_validator = None

        with pytest.raises(RuntimeError, match="微观入场验证器未加载"):
            self.plugin.clear_validation_history()


class TestConflictResolutionAPI:
    """测试冲突解决 API"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = SignalValidationPlugin()
        self.plugin._breakout_validator = MagicMock()
        self.plugin._micro_entry_validator = MagicMock()
        self.plugin._conflict_resolver = MagicMock()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_resolve_conflict_success(self):
        """测试成功解决冲突"""
        mock_result = {
            "resolution": "BULLISH",
            "confidence": 0.75,
            "conflicts": [],
        }
        self.plugin._conflict_resolver.resolve_conflict.return_value = mock_result

        result = self.plugin.resolve_conflict(
            timeframe_states={"H4": "bullish", "M15": "bearish"},
            market_context={"regime": "trending"},
        )

        assert result == mock_result
        assert self.plugin._conflict_resolve_count == 1
        self.plugin.emit_event.assert_called_once()

    def test_resolve_conflict_not_loaded(self):
        """测试未加载时解决冲突"""
        self.plugin._conflict_resolver = None

        with pytest.raises(RuntimeError, match="冲突解决器未加载"):
            self.plugin.resolve_conflict(
                timeframe_states={}, market_context={}
            )

    def test_get_resolution_history(self):
        """测试获取解决历史"""
        mock_history = [{"id": 1}]
        self.plugin._conflict_resolver.get_resolution_history.return_value = (
            mock_history
        )

        result = self.plugin.get_resolution_history(limit=5)
        assert result == mock_history

    def test_get_resolution_history_not_loaded(self):
        """测试未加载时获取历史"""
        self.plugin._conflict_resolver = None

        with pytest.raises(RuntimeError, match="冲突解决器未加载"):
            self.plugin.get_resolution_history()

    def test_clear_resolution_history(self):
        """测试清除解决历史"""
        self.plugin.clear_resolution_history()
        self.plugin._conflict_resolver.clear_history.assert_called_once()

    def test_clear_resolution_history_not_loaded(self):
        """测试未加载时清除历史"""
        self.plugin._conflict_resolver = None

        with pytest.raises(RuntimeError, match="冲突解决器未加载"):
            self.plugin.clear_resolution_history()


class TestConfigUpdate:
    """测试配置更新"""

    @patch("src.plugins.signal_validation.conflict_resolver.ConflictResolutionManager")
    @patch("src.plugins.signal_validation.micro_entry_validator.MicroEntryValidator")
    @patch("src.plugins.signal_validation.breakout_validator.BreakoutValidator")
    def test_on_config_update_recreates_components(
        self, MockBV, MockMEV, MockCR
    ):
        """测试配置更新重建组件"""
        plugin = SignalValidationPlugin()
        plugin._breakout_validator = MagicMock()
        plugin._micro_entry_validator = MagicMock()
        plugin._conflict_resolver = MagicMock()

        new_config = {
            "breakout_validator": {"atr_multiplier": 2.0},
            "micro_entry_validator": {"min_confirmation_bars": 5},
            "conflict_resolver": {"conflict_threshold": 0.5},
        }

        plugin.on_config_update(new_config)

        MockBV.assert_called_once_with(
            config={"atr_multiplier": 2.0}
        )
        MockMEV.assert_called_once_with(
            config={"min_confirmation_bars": 5}
        )
        MockCR.assert_called_once_with(
            config={"conflict_threshold": 0.5}
        )

    def test_on_config_update_skips_when_not_loaded(self):
        """测试未加载时跳过配置更新"""
        plugin = SignalValidationPlugin()
        # _breakout_validator is None, so should skip
        plugin.on_config_update({"breakout_validator": {}})
        assert plugin._breakout_validator is None

    def test_event_config_update_callback(self):
        """测试事件回调配置更新"""
        plugin = SignalValidationPlugin()
        plugin.on_config_update = MagicMock()

        plugin._on_config_update(
            "system.config_update",
            {"signal_validation": {"breakout_validator": {}}},
        )

        plugin.on_config_update.assert_called_once_with(
            {"breakout_validator": {}}
        )

    def test_event_config_update_ignores_other_plugins(self):
        """测试事件回调忽略其他插件配置"""
        plugin = SignalValidationPlugin()
        plugin.on_config_update = MagicMock()

        plugin._on_config_update(
            "system.config_update",
            {"other_plugin": {"key": "value"}},
        )

        plugin.on_config_update.assert_not_called()


class TestStatisticsAndStatusReport:
    """测试统计和状态报告"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = SignalValidationPlugin()
        self.plugin._breakout_validator = MagicMock()
        self.plugin._micro_entry_validator = MagicMock()
        self.plugin._conflict_resolver = MagicMock()

    def test_get_statistics(self):
        """测试获取统计信息"""
        self.plugin._breakout_validator.get_statistics.return_value = {
            "total_breakouts": 10
        }
        self.plugin._breakout_detect_count = 5
        self.plugin._entry_validate_count = 3

        stats = self.plugin.get_statistics()

        assert "plugin_stats" in stats
        assert stats["plugin_stats"]["breakout_detect_count"] == 5
        assert stats["plugin_stats"]["entry_validate_count"] == 3
        assert stats["breakout_statistics"]["total_breakouts"] == 10

    def test_get_statistics_not_loaded(self):
        """测试未加载时获取统计"""
        self.plugin._breakout_validator = None

        with pytest.raises(RuntimeError, match="信号验证插件未加载"):
            self.plugin.get_statistics()

    def test_get_status_report(self):
        """测试获取状态报告"""
        self.plugin._breakout_detect_count = 2
        self.plugin._conflict_resolve_count = 1

        report = self.plugin.get_status_report()

        assert report["plugin_name"] == "signal_validation"
        assert report["components"]["breakout_validator"] is True
        assert report["components"]["micro_entry_validator"] is True
        assert report["components"]["conflict_resolver"] is True
        assert report["counters"]["breakout_detect_count"] == 2
        assert report["counters"]["conflict_resolve_count"] == 1
        assert report["last_error"] is None

    def test_get_status_report_partial_load(self):
        """测试部分加载时的状态报告"""
        self.plugin._micro_entry_validator = None

        report = self.plugin.get_status_report()

        assert report["components"]["breakout_validator"] is True
        assert report["components"]["micro_entry_validator"] is False
        assert report["components"]["conflict_resolver"] is True
