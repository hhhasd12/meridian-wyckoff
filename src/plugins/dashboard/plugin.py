"""仪表板插件 - 整合决策可视化和性能监控功能

将 DecisionVisualizer 和 PerformanceMonitor 包装为统一的插件接口，
通过事件总线与其他插件通信。
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus, PluginState

logger = logging.getLogger(__name__)


class DashboardPlugin(BasePlugin):
    """仪表板插件

    整合两个核心组件：
    1. DecisionVisualizer - 决策可视化，生成K线快照
    2. PerformanceMonitor - 性能监控，健康检查和报警
    """

    def __init__(self, name: str = "dashboard") -> None:
        """初始化仪表板插件

        Args:
            name: 插件名称
        """
        super().__init__(name)
        self._visualizer: Any = None
        self._monitor: Any = None
        self._snapshot_count: int = 0
        self._alert_count: int = 0
        self._metric_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件，初始化可视化器和监控器"""
        from src.plugins.dashboard.decision_visualizer import DecisionVisualizer
        from src.plugins.dashboard.performance_monitor import PerformanceMonitor

        config = self._config or {}

        # 初始化可视化器
        vis_config = config.get("visualizer", {})
        self._visualizer = DecisionVisualizer(config=vis_config)

        # 初始化监控器
        mon_config = config.get("monitor", {})
        self._monitor = PerformanceMonitor(config=mon_config)

        logger.info("Dashboard插件加载完成")

    def on_unload(self) -> None:
        """卸载插件，停止监控并清理资源"""
        if self._monitor is not None:
            try:
                self._monitor.stop_monitoring()
            except Exception:
                pass

        self._visualizer = None
        self._monitor = None
        self._snapshot_count = 0
        self._alert_count = 0
        self._metric_count = 0
        self._last_error = None

        logger.info("Dashboard插件已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """配置更新处理

        Args:
            new_config: 新配置字典
        """
        self._config = new_config

        if self._visualizer is not None or self._monitor is not None:
            was_monitoring = (
                self._monitor is not None
                and self._monitor.monitoring_active
            )

            if was_monitoring:
                self._monitor.stop_monitoring()

            self.on_load()

            if was_monitoring:
                self._monitor.start_monitoring()

    def health_check(self) -> HealthCheckResult:
        """执行健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        if self._state != PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="Dashboard插件未激活",
            )

        if self._visualizer is None and self._monitor is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="可视化器和监控器均未初始化",
            )

        if self._last_error is not None:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近错误: {self._last_error}",
                details={
                    "snapshot_count": self._snapshot_count,
                    "alert_count": self._alert_count,
                    "last_error": self._last_error,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="Dashboard插件运行正常",
            details={
                "visualizer_loaded": self._visualizer is not None,
                "monitor_loaded": self._monitor is not None,
                "snapshot_count": self._snapshot_count,
                "alert_count": self._alert_count,
                "metric_count": self._metric_count,
            },
        )

    # ===== 可视化器方法 =====

    def create_visualization(
        self,
        df: Any,
        symbol: str,
        signal: str,
        pattern: str,
        wyckoff_state: Optional[str] = None,
        geometric_results: Optional[Dict] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """创建决策可视化快照

        Args:
            df: 包含OHLCV数据的DataFrame
            symbol: 交易对符号
            signal: 信号类型
            pattern: 模式名称
            wyckoff_state: 威科夫状态
            geometric_results: 几何分析结果
            **kwargs: 其他参数

        Returns:
            快照文件路径，失败返回None

        Raises:
            RuntimeError: 可视化器未加载
        """
        if self._visualizer is None:
            raise RuntimeError("可视化器未加载")

        try:
            result = self._visualizer.create_visualization(
                df=df,
                symbol=symbol,
                signal=signal,
                pattern=pattern,
                wyckoff_state=wyckoff_state,
                geometric_results=geometric_results,
                **kwargs,
            )
            self._snapshot_count += 1
            self.emit_event(
                "dashboard.snapshot_created",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "pattern": pattern,
                    "file_path": result,
                },
            )
            return result
        except Exception as e:
            self._last_error = str(e)
            raise

    def visualize_tr_detection(
        self,
        df: Any,
        symbol: str,
        tr_info: Dict[str, Any],
        **kwargs: Any,
    ) -> Optional[str]:
        """可视化TR检测结果

        Args:
            df: K线数据
            symbol: 交易对
            tr_info: TR检测信息
            **kwargs: 其他参数

        Returns:
            快照文件路径

        Raises:
            RuntimeError: 可视化器未加载
        """
        if self._visualizer is None:
            raise RuntimeError("可视化器未加载")

        try:
            result = self._visualizer.visualize_tr_detection(
                df=df,
                symbol=symbol,
                tr_info=tr_info,
                **kwargs,
            )
            self._snapshot_count += 1
            return result
        except Exception as e:
            self._last_error = str(e)
            raise

    def visualize_state_change(
        self,
        df: Any,
        symbol: str,
        old_state: str,
        new_state: str,
        **kwargs: Any,
    ) -> Optional[str]:
        """可视化状态变化

        Args:
            df: K线数据
            symbol: 交易对
            old_state: 旧状态
            new_state: 新状态
            **kwargs: 其他参数

        Returns:
            快照文件路径

        Raises:
            RuntimeError: 可视化器未加载
        """
        if self._visualizer is None:
            raise RuntimeError("可视化器未加载")

        try:
            result = self._visualizer.visualize_state_change(
                df=df,
                symbol=symbol,
                old_state=old_state,
                new_state=new_state,
                **kwargs,
            )
            self._snapshot_count += 1
            return result
        except Exception as e:
            self._last_error = str(e)
            raise

    # ===== 监控器方法 =====

    def start_monitoring(self) -> None:
        """启动性能监控

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        self._monitor.start_monitoring()
        self.emit_event(
            "dashboard.monitoring_started",
            {"interval": self._monitor.monitoring_interval},
        )

    def stop_monitoring(self) -> None:
        """停止性能监控

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        self._monitor.stop_monitoring()
        self.emit_event("dashboard.monitoring_stopped", {})

    def register_module(
        self,
        module_name: str,
        module_instance: Any,
        health_check_func: Optional[Callable] = None,
        metrics_func: Optional[Callable] = None,
    ) -> None:
        """注册模块到监控系统

        Args:
            module_name: 模块名称
            module_instance: 模块实例
            health_check_func: 健康检查函数
            metrics_func: 指标收集函数

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        self._monitor.register_module(
            module_name=module_name,
            module_instance=module_instance,
            health_check_func=health_check_func,
            metrics_func=metrics_func,
        )

    def record_success(
        self,
        module_name: str,
        execution_time: float = 0.0,
    ) -> None:
        """记录成功操作

        Args:
            module_name: 模块名称
            execution_time: 执行时间

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        self._monitor.record_success(
            module_name=module_name,
            execution_time=execution_time,
        )
        self._metric_count += 1

    def record_error(
        self,
        module_name: str,
        error_message: str,
        error_type: str = "UNKNOWN",
    ) -> None:
        """记录错误

        Args:
            module_name: 模块名称
            error_message: 错误消息
            error_type: 错误类型

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        self._monitor.record_error(
            module_name=module_name,
            error_message=error_message,
            error_type=error_type,
        )
        self._alert_count += 1
        self.emit_event(
            "dashboard.alert_triggered",
            {
                "module": module_name,
                "error": error_message,
                "type": error_type,
            },
        )

    def record_metric(
        self,
        metric_name: str,
        value: float,
        module_name: str = "system",
    ) -> None:
        """记录指标

        Args:
            metric_name: 指标名称
            value: 指标值
            module_name: 模块名称

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        self._monitor.record_metric(
            metric_name=metric_name,
            value=value,
            module_name=module_name,
        )
        self._metric_count += 1
        self.emit_event(
            "dashboard.metric_recorded",
            {
                "metric": metric_name,
                "value": value,
                "module": module_name,
            },
        )

    def get_health_report(self) -> Dict[str, Any]:
        """获取健康报告

        Returns:
            健康报告字典

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        report = self._monitor.get_health_report()
        self.emit_event(
            "dashboard.health_report_generated",
            {"report_keys": list(report.keys())},
        )
        return report

    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据

        Returns:
            仪表板数据字典

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        return self._monitor.get_dashboard_data()

    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要

        Returns:
            性能摘要字典

        Raises:
            RuntimeError: 监控器未加载
        """
        if self._monitor is None:
            raise RuntimeError("监控器未加载")

        return self._monitor.get_performance_summary()

    # ===== 统计方法 =====

    def get_statistics(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            统计信息字典
        """
        monitoring_active = False
        if self._monitor is not None:
            monitoring_active = self._monitor.monitoring_active

        return {
            "snapshot_count": self._snapshot_count,
            "alert_count": self._alert_count,
            "metric_count": self._metric_count,
            "last_error": self._last_error,
            "visualizer_loaded": self._visualizer is not None,
            "monitor_loaded": self._monitor is not None,
            "monitoring_active": monitoring_active,
        }
