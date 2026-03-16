"""
性能监控系统单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import time
import threading
from datetime import datetime, timedelta
from src.plugins.dashboard.performance_monitor import (
    PerformanceMonitor,
    HealthStatus,
    AlertLevel,
    ModuleType,
)


class MockModule:
    """模拟模块用于测试"""

    def __init__(self, name, health_status=None, metrics=None):
        self.name = name
        self.health_status = health_status or HealthStatus.HEALTHY
        self.metrics = metrics or {"error_rate": 0.01, "response_time": 0.5}
        self.reset_called = False

    def health_check(self):
        return self.health_status

    def collect_metrics(self):
        return self.metrics

    def reset(self):
        self.reset_called = True


class TestPerformanceMonitor:
    """测试性能监控系统"""

    def test_initialization(self):
        """测试初始化"""
        monitor = PerformanceMonitor()
        assert monitor is not None
        assert monitor.monitoring_interval == 60
        assert monitor.health_check_interval == 300
        assert monitor.alert_cooldown == 300
        assert monitor.auto_recovery_enabled is True
        assert monitor.system_health == HealthStatus.UNKNOWN
        assert len(monitor.modules) == 0
        assert monitor.monitoring_active is False

    def test_initialization_with_custom_config(self):
        """测试自定义配置初始化"""
        config = {
            "monitoring_interval": 30,
            "health_check_interval": 60,
            "alert_cooldown": 120,
            "max_history_days": 7,
            "auto_recovery_enabled": False,
            "dashboard_enabled": False,
            "log_level": "ERROR",
        }
        monitor = PerformanceMonitor(config)

        assert monitor.monitoring_interval == 30
        assert monitor.health_check_interval == 60
        assert monitor.alert_cooldown == 120
        assert monitor.max_history_days == 7
        assert monitor.auto_recovery_enabled is False
        assert monitor.dashboard_enabled is False
        assert monitor.log_level == "ERROR"

    def test_register_module(self):
        """测试注册模块"""
        monitor = PerformanceMonitor()
        module = MockModule("TestModule")

        monitor.register_module(
            "TestModule",
            module,
            ModuleType.STATEMACHINE,
            health_check_func=module.health_check,
            metrics_func=module.collect_metrics,
        )

        assert "TestModule" in monitor.modules
        assert monitor.modules["TestModule"]["instance"] == module
        assert monitor.modules["TestModule"]["type"] == ModuleType.STATEMACHINE
        assert monitor.modules["TestModule"]["health_check_func"] == module.health_check
        assert monitor.modules["TestModule"]["metrics_func"] == module.collect_metrics
        assert monitor.module_health["TestModule"] == HealthStatus.UNKNOWN

    def test_start_stop_monitoring(self):
        """测试启动和停止监控"""
        monitor = PerformanceMonitor(
            {"monitoring_interval": 1, "health_check_interval": 2}
        )
        module = MockModule("TestModule")

        monitor.register_module(
            "TestModule",
            module,
            ModuleType.STATEMACHINE,
            health_check_func=module.health_check,
            metrics_func=module.collect_metrics,
        )

        # 启动监控
        monitor.start_monitoring()
        assert monitor.monitoring_active is True
        assert monitor.monitoring_thread is not None
        assert monitor.health_check_thread is not None

        # 等待一小段时间确保线程启动
        time.sleep(0.5)

        # 停止监控
        monitor.stop_monitoring()
        assert monitor.monitoring_active is False

        # 等待线程结束
        if monitor.monitoring_thread:
            monitor.monitoring_thread.join(timeout=2.0)
        if monitor.health_check_thread:
            monitor.health_check_thread.join(timeout=2.0)

    def test_collect_metrics(self):
        """测试收集指标"""
        monitor = PerformanceMonitor()
        module = MockModule("TestModule", metrics={"metric1": 1.0, "metric2": 2.0})

        monitor.register_module(
            "TestModule",
            module,
            ModuleType.STATEMACHINE,
            metrics_func=module.collect_metrics,
        )

        # 手动调用收集指标
        monitor._collect_metrics()

        # 检查指标是否记录
        assert f"TestModule.metric1" in monitor.metrics_history
        assert f"TestModule.metric2" in monitor.metrics_history
        assert len(monitor.metrics_history[f"TestModule.metric1"]) > 0
        assert len(monitor.metrics_history[f"TestModule.metric2"]) > 0

        # 检查模块指标缓存
        assert "metric1" in monitor.module_metrics["TestModule"]
        assert "metric2" in monitor.module_metrics["TestModule"]

    def test_perform_health_checks(self):
        """测试执行健康检查"""
        monitor = PerformanceMonitor()
        module = MockModule("TestModule", health_status=HealthStatus.HEALTHY)

        monitor.register_module(
            "TestModule",
            module,
            ModuleType.STATEMACHINE,
            health_check_func=module.health_check,
        )

        # 手动执行健康检查
        monitor._perform_health_checks()

        # 检查健康状态更新
        assert monitor.module_health["TestModule"] == HealthStatus.HEALTHY
        assert monitor.modules["TestModule"]["last_health_check"] is not None

    def test_infer_health_from_metrics(self):
        """测试从指标推断健康状态"""
        monitor = PerformanceMonitor()

        # 添加一些指标数据
        metric_name = "TestModule.error_rate"
        for i in range(10):
            monitor._record_metric(
                metric_name,
                value=0.02,  # 低错误率
                timestamp=datetime.now() - timedelta(minutes=10 - i),
            )

        # 推断健康状态
        health_status = monitor._infer_health_from_metrics("TestModule")

        # 低错误率应返回健康
        assert health_status == HealthStatus.HEALTHY

    def test_infer_health_with_high_error_rate(self):
        """测试高错误率时的健康推断"""
        monitor = PerformanceMonitor()

        # 添加高错误率指标
        metric_name = "TestModule.error_rate"
        for i in range(10):
            monitor._record_metric(
                metric_name,
                value=0.25,  # 高错误率，超过CRITICAL阈值0.20
                timestamp=datetime.now() - timedelta(minutes=10 - i),
            )

        # 推断健康状态
        health_status = monitor._infer_health_from_metrics("TestModule")

        # 高错误率应返回不健康或严重
        assert health_status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]

    def test_check_thresholds(self):
        """测试检查阈值"""
        monitor = PerformanceMonitor()

        # 添加超过阈值的指标
        metric_name = "TestModule.error_rate"
        monitor._record_metric(
            metric_name,
            value=0.15,  # 超过ERROR阈值0.10
            timestamp=datetime.now(),
        )

        # 检查阈值
        monitor._check_thresholds()

        # 应记录报警
        assert len(monitor.alerts_history) > 0
        alert = monitor.alerts_history[-1]
        assert "THRESHOLD_EXCEEDED" in alert["alert_id"]
        assert alert["level"] == "ERROR"

    def test_attempt_auto_recovery(self):
        """测试尝试自动恢复"""
        monitor = PerformanceMonitor({"auto_recovery_enabled": True})

        # 注册一个可重置的模块
        module = MockModule("TestModule")
        monitor.register_module("TestModule", module, ModuleType.STATEMACHINE)

        # 尝试从高错误率恢复
        recovery_action = monitor._attempt_auto_recovery("TestModule.error_rate", 0.25)

        # 由于模块有reset方法，应执行恢复
        assert recovery_action is not None
        assert "RESET_MODULE" in recovery_action["action"]
        assert recovery_action["module"] == "TestModule"

        # 检查恢复动作记录
        assert len(monitor.recovery_actions) > 0

    def test_update_system_health(self):
        """测试更新系统整体健康状态"""
        monitor = PerformanceMonitor()

        # 注册多个模块
        healthy_module = MockModule("HealthyModule", health_status=HealthStatus.HEALTHY)
        degraded_module = MockModule(
            "DegradedModule", health_status=HealthStatus.DEGRADED
        )

        monitor.register_module(
            "HealthyModule",
            healthy_module,
            ModuleType.STATEMACHINE,
            health_check_func=healthy_module.health_check,
        )
        monitor.register_module(
            "DegradedModule",
            degraded_module,
            ModuleType.MULTITIMEFRAME,
            health_check_func=degraded_module.health_check,
        )

        # 手动设置模块健康状态
        monitor.module_health["HealthyModule"] = HealthStatus.HEALTHY
        monitor.module_health["DegradedModule"] = HealthStatus.DEGRADED

        # 更新系统健康状态
        monitor._update_system_health()

        # 检查系统健康状态
        assert monitor.system_health in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        assert monitor.system_health_score > 0

        # 检查健康历史记录
        assert len(monitor.health_history) > 0

    def test_get_dashboard_data(self):
        """测试获取仪表板数据"""
        monitor = PerformanceMonitor()

        # 注册模块并添加一些数据
        module = MockModule("TestModule")
        monitor.register_module(
            "TestModule",
            module,
            ModuleType.STATEMACHINE,
            health_check_func=module.health_check,
            metrics_func=module.collect_metrics,
        )

        # 执行一次健康检查和指标收集
        monitor._perform_health_checks()
        monitor._collect_metrics()

        # 获取仪表板数据
        dashboard = monitor.get_dashboard_data()

        assert "timestamp" in dashboard
        assert "system_health" in dashboard
        assert "module_health" in dashboard
        assert "recent_metrics" in dashboard
        assert "alerts" in dashboard
        assert "recoveries" in dashboard
        assert "performance_trends" in dashboard
        assert "stats" in dashboard

        # 检查模块健康信息
        assert "TestModule" in dashboard["module_health"]
        assert (
            dashboard["module_health"]["TestModule"]["status"]
            == HealthStatus.HEALTHY.value
        )

    def test_get_health_report(self):
        """测试获取健康报告"""
        monitor = PerformanceMonitor()

        # 添加一些模块
        for i in range(3):
            module = MockModule(f"Module{i}", health_status=HealthStatus.HEALTHY)
            monitor.register_module(
                f"Module{i}",
                module,
                ModuleType.STATEMACHINE,
                health_check_func=module.health_check,
            )
            monitor.module_health[f"Module{i}"] = HealthStatus.HEALTHY

        # 获取健康报告
        report = monitor.get_health_report()

        assert "timestamp" in report
        assert "system_health" in report
        assert "system_health_score" in report
        assert "module_count" in report
        assert report["module_count"] == 3
        assert "healthy_modules" in report
        assert report["healthy_modules"] == 3
        assert "recommendations" in report
        assert isinstance(report["recommendations"], list)

    def test_record_alert(self):
        """测试记录报警"""
        monitor = PerformanceMonitor()

        details = {"metric": "error_rate", "value": 0.15}
        monitor._record_alert(
            "TEST_ALERT",
            AlertLevel.ERROR,
            "测试报警消息",
            details,
        )

        assert len(monitor.alerts_history) == 1
        alert = monitor.alerts_history[0]
        assert alert["alert_id"] == "TEST_ALERT"
        assert alert["level"] == "ERROR"
        assert alert["message"] == "测试报警消息"
        assert alert["details"] == details
        assert alert["acknowledged"] is False
        assert alert["resolved"] is False

        # 检查统计信息
        assert monitor.stats["total_alerts"] == 1

    def test_acknowledge_alert(self):
        """测试确认报警"""
        monitor = PerformanceMonitor()

        # 记录报警
        monitor._record_alert(
            "TEST_ALERT",
            AlertLevel.ERROR,
            "测试报警消息",
            {},
        )

        # 确认报警
        monitor.acknowledge_alert("TEST_ALERT", resolved=True)

        # 检查报警状态
        alert = monitor.alerts_history[0]
        assert alert["acknowledged"] is True
        assert alert["resolved"] is True
        assert "resolved_time" in alert

    def test_record_metric(self):
        """测试记录指标"""
        monitor = PerformanceMonitor()
        timestamp = datetime.now()

        monitor._record_metric("test.metric", 42.0, timestamp)

        assert "test.metric" in monitor.metrics_history
        queue = monitor.metrics_history["test.metric"]
        assert len(queue) == 1
        assert queue[0]["value"] == 42.0
        assert queue[0]["timestamp"] == timestamp

    def test_record_health_change(self):
        """测试记录健康状态变化"""
        monitor = PerformanceMonitor()
        timestamp = datetime.now()

        # 此方法为内部方法，直接调用
        monitor._record_health_change(
            "TestModule",
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
            timestamp,
        )

        # 主要检查不抛出异常
        # 健康状态变化会在日志中记录

    def test_generate_recommendations(self):
        """测试生成优化建议"""
        monitor = PerformanceMonitor()

        # 添加不健康模块
        module = MockModule("UnhealthyModule", health_status=HealthStatus.UNHEALTHY)
        monitor.register_module(
            "UnhealthyModule",
            module,
            ModuleType.STATEMACHINE,
            health_check_func=module.health_check,
        )
        monitor.module_health["UnhealthyModule"] = HealthStatus.UNHEALTHY

        # 生成建议
        recommendations = monitor._generate_recommendations()

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        assert "UnhealthyModule" in recommendations[0]

    def test_reset_stats(self):
        """测试重置统计信息"""
        monitor = PerformanceMonitor()

        # 修改统计信息
        monitor.stats["total_alerts"] = 10
        monitor.stats["total_recoveries"] = 5
        monitor.stats["total_metrics_collected"] = 1000
        monitor.stats["uptime_seconds"] = 3600.0

        # 重置统计信息
        monitor.reset_stats()

        # 检查重置结果
        assert monitor.stats["total_alerts"] == 0
        assert monitor.stats["total_recoveries"] == 0
        assert monitor.stats["total_metrics_collected"] == 0
        assert monitor.stats["uptime_seconds"] == 0.0

    def test_alert_level_enum(self):
        """测试报警级别枚举"""
        assert AlertLevel.INFO.value == "INFO"
        assert AlertLevel.WARNING.value == "WARNING"
        assert AlertLevel.ERROR.value == "ERROR"
        assert AlertLevel.CRITICAL.value == "CRITICAL"

    def test_health_status_enum(self):
        """测试健康状态枚举"""
        assert HealthStatus.HEALTHY.value == "HEALTHY"
        assert HealthStatus.DEGRADED.value == "DEGRADED"
        assert HealthStatus.UNHEALTHY.value == "UNHEALTHY"
        assert HealthStatus.CRITICAL.value == "CRITICAL"
        assert HealthStatus.UNKNOWN.value == "UNKNOWN"

    def test_module_type_enum(self):
        """测试模块类型枚举"""
        assert ModuleType.PERCEPTION.value == "PERCEPTION"
        assert ModuleType.STATEMACHINE.value == "STATEMACHINE"
        assert ModuleType.MULTITIMEFRAME.value == "MULTITIMEFRAME"
        assert ModuleType.EVOLUTION.value == "EVOLUTION"
        assert ModuleType.DATA_PIPELINE.value == "DATA_PIPELINE"
        assert ModuleType.VISUALIZATION.value == "VISUALIZATION"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
