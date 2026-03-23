"""形态检测插件测试

测试 PatternDetectionPlugin 的完整功能：
- 生命周期管理 (on_load, on_unload, on_config_update)
- 健康检查
- TR检测 (detect_trading_range)
- 威科夫阶段检测 (detect_wyckoff_phases)
- 曲线边界拟合 (fit_boundary)
- TR信号获取 (get_tr_signals)
- 统计信息 (get_statistics)
- 事件发射
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.kernel.types import HealthStatus, PluginState
from src.plugins.pattern_detection.plugin import (
    PatternDetectionPlugin,
)


class TestPatternDetectionLifecycle:
    """插件生命周期测试"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.plugin = PatternDetectionPlugin()

    @patch("src.plugins.pattern_detection.curve_boundary.CurveBoundaryFitter")
    @patch("src.plugins.pattern_detection.wyckoff_phase_detector.WyckoffPhaseDetector")
    @patch("src.plugins.pattern_detection.tr_detector.TRDetector")
    def test_on_load_creates_detectors(
        self,
        mock_tr_cls: MagicMock,
        mock_phase_cls: MagicMock,
        mock_boundary_cls: MagicMock,
    ) -> None:
        """测试 on_load 创建三个检测器"""
        self.plugin.on_load()

        mock_tr_cls.assert_called_once_with({})
        mock_phase_cls.assert_called_once_with({})
        mock_boundary_cls.assert_called_once_with({})
        assert self.plugin._tr_detector is not None
        assert self.plugin._phase_detector is not None
        assert self.plugin._boundary_fitter is not None

    @patch("src.plugins.pattern_detection.curve_boundary.CurveBoundaryFitter")
    @patch("src.plugins.pattern_detection.wyckoff_phase_detector.WyckoffPhaseDetector")
    @patch("src.plugins.pattern_detection.tr_detector.TRDetector")
    def test_on_load_with_config(
        self,
        mock_tr_cls: MagicMock,
        mock_phase_cls: MagicMock,
        mock_boundary_cls: MagicMock,
    ) -> None:
        """测试带配置的 on_load"""
        self.plugin._config = {
            "tr_detector": {"threshold": 0.5},
            "wyckoff_phase": {"min_bars": 10},
            "curve_boundary": {"window": 20},
        }
        self.plugin.on_load()

        mock_tr_cls.assert_called_once_with({"threshold": 0.5})
        mock_phase_cls.assert_called_once_with({"min_bars": 10})
        mock_boundary_cls.assert_called_once_with({"window": 20})

    @patch("src.plugins.pattern_detection.curve_boundary.CurveBoundaryFitter")
    @patch("src.plugins.pattern_detection.wyckoff_phase_detector.WyckoffPhaseDetector")
    @patch("src.plugins.pattern_detection.tr_detector.TRDetector")
    def test_on_unload_clears_all(
        self,
        mock_tr_cls: MagicMock,
        mock_phase_cls: MagicMock,
        mock_boundary_cls: MagicMock,
    ) -> None:
        """测试 on_unload 清理所有资源"""
        self.plugin.on_load()
        self.plugin._tr_detect_count = 5
        self.plugin._phase_detect_count = 3
        self.plugin._boundary_fit_count = 2
        self.plugin._last_error = "some error"

        self.plugin.on_unload()

        assert self.plugin._tr_detector is None
        assert self.plugin._phase_detector is None
        assert self.plugin._boundary_fitter is None
        assert self.plugin._tr_detect_count == 0
        assert self.plugin._phase_detect_count == 0
        assert self.plugin._boundary_fit_count == 0
        assert self.plugin._last_error is None

    @patch("src.plugins.pattern_detection.curve_boundary.CurveBoundaryFitter")
    @patch("src.plugins.pattern_detection.wyckoff_phase_detector.WyckoffPhaseDetector")
    @patch("src.plugins.pattern_detection.tr_detector.TRDetector")
    def test_on_config_update_recreates_detectors(
        self,
        mock_tr_cls: MagicMock,
        mock_phase_cls: MagicMock,
        mock_boundary_cls: MagicMock,
    ) -> None:
        """测试配置更新时重新创建检测器"""
        self.plugin.on_load()
        assert mock_tr_cls.call_count == 1

        new_config = {
            "tr_detector": {"new_param": True},
            "wyckoff_phase": {"updated": True},
            "curve_boundary": {"changed": True},
        }
        self.plugin.on_config_update(new_config)

        assert mock_tr_cls.call_count == 2
        assert mock_phase_cls.call_count == 2
        assert mock_boundary_cls.call_count == 2

    def test_on_config_update_skips_when_not_loaded(
        self,
    ) -> None:
        """测试未加载时配置更新不执行"""
        self.plugin.on_config_update({"key": "value"})
        assert self.plugin._tr_detector is None


class TestPatternDetectionHealthCheck:
    """健康检查测试"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.plugin = PatternDetectionPlugin()

    def test_health_check_unhealthy_not_active(self) -> None:
        """测试非活跃状态返回不健康"""
        self.plugin._state = PluginState.UNLOADED
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未处于活跃状态" in result.message

    def test_health_check_unhealthy_no_tr(self) -> None:
        """测试缺少TR检测器返回不健康"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._tr_detector = None
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "TR检测器" in result.message

    def test_health_check_unhealthy_no_phase(self) -> None:
        """测试缺少阶段检测器返回不健康"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._tr_detector = MagicMock()
        self.plugin._phase_detector = None
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "威科夫阶段检测器" in result.message

    def test_health_check_unhealthy_no_boundary(self) -> None:
        """测试缺少边界拟合器返回不健康"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._tr_detector = MagicMock()
        self.plugin._phase_detector = MagicMock()
        self.plugin._boundary_fitter = None
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "曲线边界拟合器" in result.message

    def test_health_check_degraded_with_error(self) -> None:
        """测试有错误时返回降级"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._tr_detector = MagicMock()
        self.plugin._phase_detector = MagicMock()
        self.plugin._boundary_fitter = MagicMock()
        self.plugin._last_error = "test error"
        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "test error" in result.message

    def test_health_check_healthy(self) -> None:
        """测试正常状态返回健康"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._tr_detector = MagicMock()
        self.plugin._phase_detector = MagicMock()
        self.plugin._boundary_fitter = MagicMock()
        self.plugin._last_error = None
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert "正常运行" in result.message


class TestDetectTradingRange:
    """TR检测测试"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.plugin = PatternDetectionPlugin()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_detect_tr_unloaded_raises(self) -> None:
        """测试未加载时抛出异常"""
        with pytest.raises(RuntimeError, match="未加载.*TR"):
            self.plugin.detect_trading_range(pd.DataFrame())

    def test_detect_tr_success(self) -> None:
        """测试成功检测TR"""
        mock_result = MagicMock()
        mock_result.status.value = "ACTIVE"
        mock_result.confidence = 0.85

        self.plugin._tr_detector = MagicMock()
        self.plugin._tr_detector.detect_trading_range.return_value = mock_result

        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        result = self.plugin.detect_trading_range(df)

        assert result == mock_result
        assert self.plugin._tr_detect_count == 1
        assert self.plugin._last_error is None
        self.plugin.emit_event.assert_called_once_with(  # type: ignore[attr-defined]
            "pattern_detection.tr_detected",
            {"status": "ACTIVE", "confidence": 0.85},
        )

    def test_detect_tr_result_without_status(self) -> None:
        """测试结果没有status属性时的处理"""
        mock_result = MagicMock(spec=[])
        del mock_result.status
        del mock_result.confidence

        self.plugin._tr_detector = MagicMock()
        self.plugin._tr_detector.detect_trading_range.return_value = mock_result

        df = pd.DataFrame({"close": [1.0, 2.0]})
        result = self.plugin.detect_trading_range(df)

        assert result == mock_result
        self.plugin.emit_event.assert_called_once_with(  # type: ignore[attr-defined]
            "pattern_detection.tr_detected",
            {"status": "UNKNOWN", "confidence": 0.0},
        )

    def test_detect_tr_exception_sets_error(self) -> None:
        """测试异常时设置last_error"""
        self.plugin._tr_detector = MagicMock()
        self.plugin._tr_detector.detect_trading_range.side_effect = ValueError(
            "数据不足"
        )

        df = pd.DataFrame()
        with pytest.raises(ValueError, match="数据不足"):
            self.plugin.detect_trading_range(df)

        assert self.plugin._last_error == "数据不足"
        assert self.plugin._tr_detect_count == 0


class TestDetectWyckoffPhases:
    """威科夫阶段检测测试"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.plugin = PatternDetectionPlugin()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_detect_phases_unloaded_raises(self) -> None:
        """测试未加载时抛出异常"""
        with pytest.raises(RuntimeError, match="未加载.*威科夫"):
            self.plugin.detect_wyckoff_phases(pd.Series(), {}, "IDLE")

    def test_detect_phases_success(self) -> None:
        """测试成功检测威科夫阶段"""
        mock_results = {
            "PS": {"confidence": 0.3, "detected": False},
            "SC": {"confidence": 0.8, "detected": True},
            "AR": {"confidence": 0.5, "detected": False},
        }

        self.plugin._phase_detector = MagicMock()
        self.plugin._phase_detector.detect.return_value = mock_results

        candle = pd.Series({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5})
        context = {"trend": "up"}
        result = self.plugin.detect_wyckoff_phases(candle, context, "ACCUMULATION")

        assert result == mock_results
        assert self.plugin._phase_detect_count == 1
        self.plugin.emit_event.assert_called_once_with(  # type: ignore[attr-defined]
            "pattern_detection.wyckoff_phase_detected",
            {
                "best_phase": "SC",
                "best_confidence": 0.8,
                "phase_count": 3,
            },
        )

    def test_detect_phases_no_confident_phase(self) -> None:
        """测试所有阶段置信度为0"""
        mock_results = {
            "PS": {"confidence": 0.0},
            "SC": {"confidence": 0.0},
        }

        self.plugin._phase_detector = MagicMock()
        self.plugin._phase_detector.detect.return_value = mock_results

        candle = pd.Series({"close": 1.0})
        result = self.plugin.detect_wyckoff_phases(candle, {}, "IDLE")

        assert result == mock_results
        self.plugin.emit_event.assert_called_once_with(  # type: ignore[attr-defined]
            "pattern_detection.wyckoff_phase_detected",
            {
                "best_phase": None,
                "best_confidence": 0.0,
                "phase_count": 2,
            },
        )

    def test_detect_phases_exception(self) -> None:
        """测试异常时设置last_error"""
        self.plugin._phase_detector = MagicMock()
        self.plugin._phase_detector.detect.side_effect = RuntimeError("检测失败")

        with pytest.raises(RuntimeError, match="检测失败"):
            self.plugin.detect_wyckoff_phases(pd.Series(), {}, "IDLE")

        assert self.plugin._last_error == "检测失败"


class TestFitBoundary:
    """曲线边界拟合测试"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.plugin = PatternDetectionPlugin()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_fit_boundary_unloaded_raises(self) -> None:
        """测试未加载时抛出异常"""
        with pytest.raises(RuntimeError, match="未加载.*边界"):
            self.plugin.fit_boundary(pd.DataFrame())

    def test_fit_boundary_success(self) -> None:
        """测试成功拟合边界"""
        mock_pivots = {
            "highs": [10.0, 12.0],
            "lows": [8.0, 7.5, 9.0],
        }
        mock_history = [{"type": "support"}]
        mock_current = {"upper": 12.0, "lower": 7.5}

        self.plugin._boundary_fitter = MagicMock()
        self.plugin._boundary_fitter.detect_pivot_points.return_value = mock_pivots
        self.plugin._boundary_fitter.get_boundary_history.return_value = mock_history
        self.plugin._boundary_fitter.get_current_boundary.return_value = mock_current

        df = pd.DataFrame({"close": [10.0, 11.0, 9.0, 12.0, 8.0]})
        result = self.plugin.fit_boundary(df)

        assert result["pivots"] == mock_pivots
        assert result["boundary_history"] == mock_history
        assert result["current_boundary"] == mock_current
        assert self.plugin._boundary_fit_count == 1
        self.plugin.emit_event.assert_called_once_with(  # type: ignore[attr-defined]
            "pattern_detection.boundary_fitted",
            {"high_count": 2, "low_count": 3},
        )

    def test_fit_boundary_exception(self) -> None:
        """测试异常时设置last_error"""
        self.plugin._boundary_fitter = MagicMock()
        self.plugin._boundary_fitter.detect_pivot_points.side_effect = KeyError("close")

        df = pd.DataFrame()
        with pytest.raises(KeyError):
            self.plugin.fit_boundary(df)

        assert (
            self.plugin._last_error is not None and "close" in self.plugin._last_error
        )


class TestGetTRSignals:
    """TR信号获取测试"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.plugin = PatternDetectionPlugin()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_get_signals_unloaded_raises(self) -> None:
        """测试未加载时抛出异常"""
        with pytest.raises(RuntimeError, match="未加载.*TR信号"):
            self.plugin.get_tr_signals(100.0)

    def test_get_signals_success(self) -> None:
        """测试成功获取TR信号"""
        mock_signals = {
            "breakout": "UP",
            "strength": 0.7,
        }

        self.plugin._tr_detector = MagicMock()
        self.plugin._tr_detector.get_tr_signals.return_value = mock_signals

        result = self.plugin.get_tr_signals(50000.0)

        assert result == mock_signals
        assert self.plugin._last_error is None
        self.plugin.emit_event.assert_called_once_with(  # type: ignore[attr-defined]
            "pattern_detection.tr_signals",
            {"price": 50000.0},
        )

    def test_get_signals_exception(self) -> None:
        """测试异常时设置last_error"""
        self.plugin._tr_detector = MagicMock()
        self.plugin._tr_detector.get_tr_signals.side_effect = ValueError("无效价格")

        with pytest.raises(ValueError, match="无效价格"):
            self.plugin.get_tr_signals(-1.0)

        assert self.plugin._last_error == "无效价格"


class TestGetStatistics:
    """统计信息测试"""

    def setup_method(self) -> None:
        """每个测试前初始化"""
        self.plugin = PatternDetectionPlugin()

    def test_statistics_without_detector(self) -> None:
        """测试无检测器时的统计"""
        stats = self.plugin.get_statistics()
        assert stats["tr_detect_count"] == 0
        assert stats["phase_detect_count"] == 0
        assert stats["boundary_fit_count"] == 0
        assert stats["last_error"] is None
        assert "tr_statistics" not in stats

    def test_statistics_with_detector(self) -> None:
        """测试有检测器时包含tr_statistics"""
        self.plugin._tr_detector = MagicMock()
        self.plugin._tr_detector.get_statistics.return_value = {"total_ranges": 5}
        self.plugin._tr_detect_count = 10
        self.plugin._phase_detect_count = 7
        self.plugin._boundary_fit_count = 3
        self.plugin._last_error = "prev error"

        stats = self.plugin.get_statistics()
        assert stats["tr_detect_count"] == 10
        assert stats["phase_detect_count"] == 7
        assert stats["boundary_fit_count"] == 3
        assert stats["last_error"] == "prev error"
        assert stats["tr_statistics"] == {"total_ranges": 5}

    def test_statistics_detector_error_fallback(
        self,
    ) -> None:
        """测试检测器统计出错时返回空字典"""
        self.plugin._tr_detector = MagicMock()
        self.plugin._tr_detector.get_statistics.side_effect = Exception("统计失败")

        stats = self.plugin.get_statistics()
        assert stats["tr_statistics"] == {}
