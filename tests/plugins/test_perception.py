"""
感知层插件（PerceptionPlugin）单元测试

测试覆盖：
- 初始化和继承
- 生命周期（on_load/on_unload）
- 健康检查
- 配置更新
- K线分析
- FVG检测
- 针vs实体分析
- 统计信息
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginState
from src.plugins.perception.plugin import PerceptionPlugin


class TestPerceptionPluginInit:
    """初始化测试"""

    def test_inherits_base_plugin(self) -> None:
        """测试继承自BasePlugin"""
        plugin = PerceptionPlugin()
        assert isinstance(plugin, BasePlugin)

    def test_default_name(self) -> None:
        """测试默认名称"""
        plugin = PerceptionPlugin()
        assert plugin._name == "perception"

    def test_custom_name(self) -> None:
        """测试自定义名称"""
        plugin = PerceptionPlugin(name="custom_perception")
        assert plugin._name == "custom_perception"

    def test_default_config(self) -> None:
        """测试默认配置"""
        plugin = PerceptionPlugin()
        assert plugin._config == {}

    def test_custom_config(self) -> None:
        """测试自定义配置"""
        config = {"fvg_threshold_percent": 0.8}
        plugin = PerceptionPlugin(config=config)
        assert plugin._config["fvg_threshold_percent"] == 0.8

    def test_fvg_detector_none_before_load(self) -> None:
        """测试加载前FVG检测器为None"""
        plugin = PerceptionPlugin()
        assert plugin._fvg_detector is None

    def test_initial_state_unloaded(self) -> None:
        """测试初始状态为UNLOADED"""
        plugin = PerceptionPlugin()
        assert plugin._state == PluginState.UNLOADED


class TestPerceptionPluginLifecycle:
    """生命周期测试"""

    @patch(
        "src.perception.fvg_detector.FVGDetector"
    )
    def test_on_load_creates_fvg_detector(
        self, mock_fvg_cls: MagicMock
    ) -> None:
        """测试on_load创建FVG检测器"""
        mock_instance = MagicMock()
        mock_fvg_cls.return_value = mock_instance

        plugin = PerceptionPlugin()
        plugin.on_load()

        mock_fvg_cls.assert_called_once()
        assert plugin._fvg_detector is mock_instance

    @patch(
        "src.perception.fvg_detector.FVGDetector"
    )
    def test_on_load_resets_counters(
        self, mock_fvg_cls: MagicMock
    ) -> None:
        """测试on_load重置计数器"""
        plugin = PerceptionPlugin()
        plugin._analysis_count = 10
        plugin._fvg_count = 5
        plugin._last_error = "old error"

        plugin.on_load()

        assert plugin._analysis_count == 0
        assert plugin._fvg_count == 0
        assert plugin._last_error is None

    @patch(
        "src.perception.fvg_detector.FVGDetector"
    )
    def test_on_unload_clears_resources(
        self, mock_fvg_cls: MagicMock
    ) -> None:
        """测试on_unload清理资源"""
        plugin = PerceptionPlugin()
        plugin.on_load()
        plugin._analysis_count = 10
        plugin._fvg_count = 5

        plugin.on_unload()

        assert plugin._fvg_detector is None
        assert plugin._analysis_count == 0
        assert plugin._fvg_count == 0


class TestPerceptionPluginHealthCheck:
    """健康检查测试"""

    def test_health_check_not_loaded(self) -> None:
        """测试未加载时健康检查"""
        plugin = PerceptionPlugin()
        result = plugin.health_check()
        assert result.status == HealthStatus.UNKNOWN

    @patch(
        "src.perception.fvg_detector.FVGDetector"
    )
    def test_health_check_active_healthy(
        self, mock_fvg_cls: MagicMock
    ) -> None:
        """测试活跃且健康状态"""
        plugin = PerceptionPlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE

        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    @patch(
        "src.perception.fvg_detector.FVGDetector"
    )
    def test_health_check_with_last_error(
        self, mock_fvg_cls: MagicMock
    ) -> None:
        """测试有错误时返回DEGRADED"""
        plugin = PerceptionPlugin()
        plugin.on_load()
        plugin._state = PluginState.ACTIVE
        plugin._last_error = "test error"

        result = plugin.health_check()
        assert result.status == HealthStatus.DEGRADED

    def test_health_check_fvg_detector_none_active(self) -> None:
        """测试FVG检测器为None但状态为ACTIVE"""
        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE

        result = plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY


class TestPerceptionPluginConfigUpdate:
    """配置更新测试"""

    @patch(
        "src.perception.fvg_detector.FVGDetector"
    )
    def test_config_update_recreates_fvg_detector(
        self, mock_fvg_cls: MagicMock
    ) -> None:
        """测试配置更新重新创建FVG检测器"""
        plugin = PerceptionPlugin()
        plugin.on_load()

        new_config = {"fvg_threshold_percent": 1.0}
        plugin.on_config_update(new_config)

        # FVGDetector应该被调用两次（on_load + on_config_update）
        assert mock_fvg_cls.call_count == 2
        assert plugin._config["fvg_threshold_percent"] == 1.0

    def test_config_update_before_load(self) -> None:
        """测试加载前配置更新不创建检测器"""
        plugin = PerceptionPlugin()
        plugin.on_config_update({"fvg_threshold_percent": 1.0})

        assert plugin._fvg_detector is None
        assert plugin._config["fvg_threshold_percent"] == 1.0


class TestPerceptionPluginAnalyzeCandle:
    """K线分析测试"""

    def test_analyze_candle_not_loaded_raises(self) -> None:
        """测试未加载时分析K线抛出异常"""
        plugin = PerceptionPlugin()
        with pytest.raises(RuntimeError, match="未加载.*K线"):
            plugin.analyze_candle(100, 110, 95, 105, 1000)

    @patch(
        "src.perception.candle_physical.CandlePhysical"
    )
    def test_analyze_candle_success(
        self, mock_candle_cls: MagicMock
    ) -> None:
        """测试成功分析K线"""
        mock_candle = MagicMock()
        mock_candle.body = 5.0
        mock_candle.body_direction = 1
        mock_candle.upper_shadow = 5.0
        mock_candle.lower_shadow = 5.0
        mock_candle.body_ratio = 0.333
        mock_candle.shadow_ratio = 0.667
        mock_candle_cls.return_value = mock_candle

        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._fvg_detector = MagicMock()

        result = plugin.analyze_candle(100, 110, 95, 105, 1000)

        assert result["body"] == 5.0
        assert result["body_direction"] == 1
        assert plugin._analysis_count == 1

    @patch(
        "src.perception.candle_physical.CandlePhysical"
    )
    def test_analyze_candle_emits_event(
        self, mock_candle_cls: MagicMock
    ) -> None:
        """测试K线分析发布事件"""
        mock_candle = MagicMock()
        mock_candle.body = 5.0
        mock_candle.body_direction = 1
        mock_candle.upper_shadow = 5.0
        mock_candle.lower_shadow = 5.0
        mock_candle.body_ratio = 0.333
        mock_candle.shadow_ratio = 0.667
        mock_candle_cls.return_value = mock_candle

        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._fvg_detector = MagicMock()
        plugin.emit_event = MagicMock(return_value=1)

        plugin.analyze_candle(100, 110, 95, 105, 1000)

        plugin.emit_event.assert_called_once()
        call_args = plugin.emit_event.call_args
        assert call_args[0][0] == "perception.candle_analyzed"


class TestPerceptionPluginDetectFVG:
    """FVG检测测试"""

    def test_detect_fvg_not_loaded_raises(self) -> None:
        """测试未加载时检测FVG抛出异常"""
        plugin = PerceptionPlugin()
        df = pd.DataFrame()
        with pytest.raises(RuntimeError, match="未加载.*FVG"):
            plugin.detect_fvg(df)

    def test_detect_fvg_no_detector_raises(self) -> None:
        """测试检测器为None时抛出异常"""
        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE
        df = pd.DataFrame()
        with pytest.raises(RuntimeError, match="FVG检测器未初始化"):
            plugin.detect_fvg(df)

    def test_detect_fvg_success(self) -> None:
        """测试成功检测FVG"""
        mock_gap = MagicMock()
        mock_gap.gap_id = "gap_001"
        mock_gap.direction.value = "BULLISH"
        mock_gap.max_price = 110.0
        mock_gap.min_price = 105.0
        mock_gap.confidence = 0.85

        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._fvg_detector = MagicMock()
        plugin._fvg_detector.detect_fvg_gaps.return_value = [mock_gap]

        df = pd.DataFrame(
            {"open": [100], "high": [110], "low": [95], "close": [105]}
        )
        gaps = plugin.detect_fvg(df)

        assert len(gaps) == 1
        assert plugin._fvg_count == 1

    def test_detect_fvg_emits_events(self) -> None:
        """测试FVG检测发布事件"""
        mock_gap = MagicMock()
        mock_gap.gap_id = "gap_001"
        mock_gap.direction.value = "BULLISH"
        mock_gap.max_price = 110.0
        mock_gap.min_price = 105.0
        mock_gap.confidence = 0.85

        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._fvg_detector = MagicMock()
        plugin._fvg_detector.detect_fvg_gaps.return_value = [mock_gap]
        plugin.emit_event = MagicMock(return_value=1)

        df = pd.DataFrame()
        plugin.detect_fvg(df)

        plugin.emit_event.assert_called_once()
        call_args = plugin.emit_event.call_args
        assert call_args[0][0] == "perception.fvg_detected"


class TestPerceptionPluginPinBodyAnalysis:
    """针vs实体分析测试"""

    def test_pin_body_not_loaded_raises(self) -> None:
        """测试未加载时分析抛出异常"""
        plugin = PerceptionPlugin()
        with pytest.raises(RuntimeError, match="未加载.*针vs实体"):
            plugin.analyze_pin_vs_body({"open": 100})

    @patch(
        "src.perception.pin_body_analyzer.analyze_pin_vs_body"
    )
    def test_pin_body_success(
        self, mock_analyze: MagicMock
    ) -> None:
        """测试成功分析针vs实体"""
        mock_result = MagicMock()
        mock_result.is_pin_dominant = True
        mock_result.is_body_dominant = False
        mock_result.pin_strength = 0.8
        mock_result.body_strength = 0.2
        mock_result.confidence = 0.75
        mock_analyze.return_value = mock_result

        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._fvg_detector = MagicMock()

        candle_dict = {
            "open": 100, "high": 110, "low": 95,
            "close": 105, "volume": 1000,
        }
        result = plugin.analyze_pin_vs_body(candle_dict)

        assert result.is_pin_dominant is True
        assert result.pin_strength == 0.8
        assert plugin._analysis_count == 1

    @patch(
        "src.perception.pin_body_analyzer.analyze_pin_vs_body"
    )
    def test_pin_body_emits_event(
        self, mock_analyze: MagicMock
    ) -> None:
        """测试针vs实体分析发布事件"""
        mock_result = MagicMock()
        mock_result.is_pin_dominant = True
        mock_result.is_body_dominant = False
        mock_result.pin_strength = 0.8
        mock_result.body_strength = 0.2
        mock_result.confidence = 0.75
        mock_analyze.return_value = mock_result

        plugin = PerceptionPlugin()
        plugin._state = PluginState.ACTIVE
        plugin._fvg_detector = MagicMock()
        plugin.emit_event = MagicMock(return_value=1)

        plugin.analyze_pin_vs_body({"open": 100})

        plugin.emit_event.assert_called_once()
        call_args = plugin.emit_event.call_args
        assert call_args[0][0] == "perception.pin_body_analyzed"


class TestPerceptionPluginStatistics:
    """统计信息测试"""

    def test_statistics_not_loaded(self) -> None:
        """测试未加载时的统计信息"""
        plugin = PerceptionPlugin()
        stats = plugin.get_statistics()

        assert stats["analysis_count"] == 0
        assert stats["fvg_count"] == 0
        assert stats["last_error"] is None
        assert "fvg_statistics" not in stats

    def test_statistics_loaded(self) -> None:
        """测试加载后的统计信息"""
        plugin = PerceptionPlugin()
        plugin._fvg_detector = MagicMock()
        plugin._fvg_detector.get_statistics.return_value = {
            "total_detected": 10,
            "active_gaps": 3,
        }
        plugin._analysis_count = 5
        plugin._fvg_count = 10

        stats = plugin.get_statistics()

        assert stats["analysis_count"] == 5
        assert stats["fvg_count"] == 10
        assert stats["fvg_statistics"]["total_detected"] == 10
