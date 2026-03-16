"""Dashboard插件测试"""

from unittest.mock import MagicMock, patch

import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginState
from src.plugins.dashboard.plugin import DashboardPlugin


class TestDashboardPluginInit:
    """测试插件初始化"""

    def test_init_default_name(self):
        """测试默认名称"""
        plugin = DashboardPlugin()
        assert plugin.name == "dashboard"

    def test_init_custom_name(self):
        """测试自定义名称"""
        plugin = DashboardPlugin(name="my_dashboard")
        assert plugin.name == "my_dashboard"

    def test_init_inherits_base_plugin(self):
        """测试继承BasePlugin"""
        plugin = DashboardPlugin()
        assert isinstance(plugin, BasePlugin)

    def test_init_attributes(self):
        """测试初始属性"""
        plugin = DashboardPlugin()
        assert plugin._visualizer is None
        assert plugin._monitor is None
        assert plugin._snapshot_count == 0
        assert plugin._alert_count == 0
        assert plugin._metric_count == 0
        assert plugin._last_error is None


class TestDashboardLoadUnload:
    """测试加载和卸载"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_on_load_default(self, mock_vis_cls, mock_mon_cls):
        """测试默认配置加载"""
        self.plugin.on_load()
        assert self.plugin._visualizer is not None
        assert self.plugin._monitor is not None
        mock_vis_cls.assert_called_once_with(config={})
        mock_mon_cls.assert_called_once_with(config={})

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_on_load_with_config(self, mock_vis_cls, mock_mon_cls):
        """测试带配置加载"""
        self.plugin._config = {
            "visualizer": {"dpi": 300},
            "monitor": {"monitoring_interval": 30},
        }
        self.plugin.on_load()
        mock_vis_cls.assert_called_once_with(config={"dpi": 300})
        mock_mon_cls.assert_called_once_with(
            config={"monitoring_interval": 30}
        )

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_on_unload(self, mock_vis_cls, mock_mon_cls):
        """测试卸载"""
        mock_monitor = MagicMock()
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()
        self.plugin._snapshot_count = 5
        self.plugin._alert_count = 3

        self.plugin.on_unload()
        assert self.plugin._visualizer is None
        assert self.plugin._monitor is None
        assert self.plugin._snapshot_count == 0
        assert self.plugin._alert_count == 0
        mock_monitor.stop_monitoring.assert_called_once()

    def test_on_unload_when_not_loaded(self):
        """测试未加载时卸载"""
        self.plugin.on_unload()
        assert self.plugin._visualizer is None
        assert self.plugin._monitor is None


class TestDashboardConfigUpdate:
    """测试配置更新"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    def test_config_update_when_not_loaded(self):
        """测试未加载时配置更新"""
        self.plugin.on_config_update({"key": "value"})
        assert self.plugin._config == {"key": "value"}

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_config_update_restarts_monitoring(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试配置更新时重启监控"""
        mock_monitor = MagicMock()
        mock_monitor.monitoring_active = True
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()

        self.plugin.on_config_update({"monitor": {"interval": 10}})
        mock_monitor.stop_monitoring.assert_called_once()


class TestDashboardHealthCheck:
    """测试健康检查"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    def test_health_check_not_active(self):
        """测试未激活时健康检查"""
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未激活" in result.message

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_health_check_healthy(self, mock_vis_cls, mock_mon_cls):
        """测试健康状态"""
        self.plugin.on_load()
        self.plugin._state = PluginState.ACTIVE

        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_health_check_with_error(self, mock_vis_cls, mock_mon_cls):
        """测试有错误时健康检查"""
        self.plugin.on_load()
        self.plugin._state = PluginState.ACTIVE
        self.plugin._last_error = "测试错误"

        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED

    def test_health_check_nothing_loaded(self):
        """测试无组件加载"""
        self.plugin._state = PluginState.ACTIVE
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未初始化" in result.message


class TestDashboardVisualization:
    """测试可视化方法"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    def test_create_visualization_not_loaded(self):
        """测试未加载时创建可视化"""
        with pytest.raises(RuntimeError, match="可视化器未加载"):
            self.plugin.create_visualization(
                df=MagicMock(),
                symbol="BTC/USDT",
                signal="BUY",
                pattern="spring",
            )

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_create_visualization_success(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试成功创建可视化"""
        mock_visualizer = MagicMock()
        mock_visualizer.create_visualization.return_value = (
            "/tmp/snapshot.png"
        )
        mock_vis_cls.return_value = mock_visualizer
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        result = self.plugin.create_visualization(
            df=MagicMock(),
            symbol="BTC/USDT",
            signal="BUY",
            pattern="spring",
        )
        assert result == "/tmp/snapshot.png"
        assert self.plugin._snapshot_count == 1

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_create_visualization_error(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试可视化异常"""
        mock_visualizer = MagicMock()
        mock_visualizer.create_visualization.side_effect = (
            RuntimeError("绘图失败")
        )
        mock_vis_cls.return_value = mock_visualizer
        self.plugin.on_load()

        with pytest.raises(RuntimeError):
            self.plugin.create_visualization(
                df=MagicMock(),
                symbol="BTC/USDT",
                signal="BUY",
                pattern="spring",
            )
        assert self.plugin._last_error is not None

    def test_visualize_tr_not_loaded(self):
        """测试未加载时TR可视化"""
        with pytest.raises(RuntimeError, match="可视化器未加载"):
            self.plugin.visualize_tr_detection(
                df=MagicMock(),
                symbol="BTC/USDT",
                tr_info={},
            )

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_visualize_tr_success(self, mock_vis_cls, mock_mon_cls):
        """测试成功TR可视化"""
        mock_visualizer = MagicMock()
        mock_visualizer.visualize_tr_detection.return_value = (
            "/tmp/tr.png"
        )
        mock_vis_cls.return_value = mock_visualizer
        self.plugin.on_load()

        result = self.plugin.visualize_tr_detection(
            df=MagicMock(),
            symbol="BTC/USDT",
            tr_info={"type": "accumulation"},
        )
        assert result == "/tmp/tr.png"
        assert self.plugin._snapshot_count == 1

    def test_visualize_state_change_not_loaded(self):
        """测试未加载时状态变化可视化"""
        with pytest.raises(RuntimeError, match="可视化器未加载"):
            self.plugin.visualize_state_change(
                df=MagicMock(),
                symbol="BTC/USDT",
                old_state="ACCUMULATION",
                new_state="MARKUP",
            )

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_visualize_state_change_success(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试成功状态变化可视化"""
        mock_visualizer = MagicMock()
        mock_visualizer.visualize_state_change.return_value = (
            "/tmp/state.png"
        )
        mock_vis_cls.return_value = mock_visualizer
        self.plugin.on_load()

        result = self.plugin.visualize_state_change(
            df=MagicMock(),
            symbol="BTC/USDT",
            old_state="ACCUMULATION",
            new_state="MARKUP",
        )
        assert result == "/tmp/state.png"
        assert self.plugin._snapshot_count == 1


class TestDashboardMonitoring:
    """测试监控方法"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    def test_start_monitoring_not_loaded(self):
        """测试未加载时启动监控"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.start_monitoring()

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_start_monitoring_success(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试成功启动监控"""
        mock_monitor = MagicMock()
        mock_monitor.monitoring_interval = 60
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        self.plugin.start_monitoring()
        mock_monitor.start_monitoring.assert_called_once()

    def test_stop_monitoring_not_loaded(self):
        """测试未加载时停止监控"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.stop_monitoring()

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_stop_monitoring_success(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试成功停止监控"""
        mock_monitor = MagicMock()
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        self.plugin.stop_monitoring()
        mock_monitor.stop_monitoring.assert_called_once()

    def test_register_module_not_loaded(self):
        """测试未加载时注册模块"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.register_module("test", MagicMock())

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_register_module_success(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试成功注册模块"""
        mock_monitor = MagicMock()
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()

        mock_instance = MagicMock()
        self.plugin.register_module("test_module", mock_instance)
        mock_monitor.register_module.assert_called_once()


class TestDashboardMetrics:
    """测试指标记录"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    def test_record_success_not_loaded(self):
        """测试未加载时记录成功"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.record_success("test", 0.5)

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_record_success(self, mock_vis_cls, mock_mon_cls):
        """测试记录成功"""
        mock_monitor = MagicMock()
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()

        self.plugin.record_success("test_module", 0.5)
        mock_monitor.record_success.assert_called_once_with(
            module_name="test_module", execution_time=0.5
        )
        assert self.plugin._metric_count == 1

    def test_record_error_not_loaded(self):
        """测试未加载时记录错误"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.record_error("test", "error msg")

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_record_error(self, mock_vis_cls, mock_mon_cls):
        """测试记录错误"""
        mock_monitor = MagicMock()
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        self.plugin.record_error("test_module", "出错了")
        assert self.plugin._alert_count == 1

    def test_record_metric_not_loaded(self):
        """测试未加载时记录指标"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.record_metric("cpu", 0.8)

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_record_metric(self, mock_vis_cls, mock_mon_cls):
        """测试记录指标"""
        mock_monitor = MagicMock()
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        self.plugin.record_metric("cpu_usage", 0.75)
        assert self.plugin._metric_count == 1


class TestDashboardReports:
    """测试报告方法"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    def test_health_report_not_loaded(self):
        """测试未加载时获取健康报告"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.get_health_report()

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_health_report_success(self, mock_vis_cls, mock_mon_cls):
        """测试成功获取健康报告"""
        mock_monitor = MagicMock()
        mock_monitor.get_health_report.return_value = {
            "status": "HEALTHY",
            "modules": {},
        }
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        report = self.plugin.get_health_report()
        assert report["status"] == "HEALTHY"

    def test_dashboard_data_not_loaded(self):
        """测试未加载时获取仪表板数据"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.get_dashboard_data()

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_dashboard_data_success(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试成功获取仪表板数据"""
        mock_monitor = MagicMock()
        mock_monitor.get_dashboard_data.return_value = {
            "health": "OK"
        }
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()

        data = self.plugin.get_dashboard_data()
        assert data["health"] == "OK"

    def test_performance_summary_not_loaded(self):
        """测试未加载时获取性能摘要"""
        with pytest.raises(RuntimeError, match="监控器未加载"):
            self.plugin.get_performance_summary()

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_performance_summary_success(
        self, mock_vis_cls, mock_mon_cls
    ):
        """测试成功获取性能摘要"""
        mock_monitor = MagicMock()
        mock_monitor.get_performance_summary.return_value = {
            "uptime": 3600
        }
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()

        summary = self.plugin.get_performance_summary()
        assert summary["uptime"] == 3600


class TestDashboardStatistics:
    """测试统计信息"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = DashboardPlugin()

    def test_statistics_initial(self):
        """测试初始统计"""
        stats = self.plugin.get_statistics()
        assert stats["snapshot_count"] == 0
        assert stats["alert_count"] == 0
        assert stats["metric_count"] == 0
        assert stats["last_error"] is None
        assert stats["visualizer_loaded"] is False
        assert stats["monitor_loaded"] is False
        assert stats["monitoring_active"] is False

    @patch("src.plugins.dashboard.performance_monitor.PerformanceMonitor")
    @patch("src.plugins.dashboard.decision_visualizer.DecisionVisualizer")
    def test_statistics_after_ops(self, mock_vis_cls, mock_mon_cls):
        """测试操作后统计"""
        mock_monitor = MagicMock()
        mock_monitor.monitoring_active = True
        mock_mon_cls.return_value = mock_monitor
        self.plugin.on_load()
        self.plugin._snapshot_count = 10
        self.plugin._alert_count = 3
        self.plugin._metric_count = 50

        stats = self.plugin.get_statistics()
        assert stats["snapshot_count"] == 10
        assert stats["alert_count"] == 3
        assert stats["metric_count"] == 50
        assert stats["visualizer_loaded"] is True
        assert stats["monitor_loaded"] is True
        assert stats["monitoring_active"] is True
