"""
性能监控系统模块
实时监控系统健康度，实现异常自愈和自动化运维

设计原则：
1. 全面监控：覆盖所有核心模块的健康状态、性能指标、错误率
2. 实时报警：关键指标超过阈值时立即报警
3. 自动恢复：检测到异常时尝试自动恢复
4. 历史分析：记录性能趋势，支持容量规划和优化
5. 可视化仪表板：提供运维界面，支持实时监控和干预

技术要点：
- 健康度评分：基于多个维度计算系统整体健康度
- 异常检测：使用统计方法和规则检测异常
- 自愈策略：预定义恢复动作和应急方案
- 容量规划：基于历史趋势预测资源需求
"""

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np

# 导入相关模块
try:
    from src.plugins.self_correction.mistake_book import MistakeBook
    from src.plugins.evolution.weight_variator_legacy import WeightVariator
    from src.plugins.evolution.wfa_backtester import WFABacktester
except ImportError:
    # 备用导入：这些模块可能未安装
    pass


class HealthStatus(Enum):
    """健康状态枚举"""

    HEALTHY = "HEALTHY"  # 健康
    DEGRADED = "DEGRADED"  # 降级
    UNHEALTHY = "UNHEALTHY"  # 不健康
    CRITICAL = "CRITICAL"  # 严重
    UNKNOWN = "UNKNOWN"  # 未知


class AlertLevel(Enum):
    """报警级别枚举"""

    INFO = "INFO"  # 信息
    WARNING = "WARNING"  # 警告
    ERROR = "ERROR"  # 错误
    CRITICAL = "CRITICAL"  # 严重


class ModuleType(Enum):
    """模块类型枚举"""

    PERCEPTION = "PERCEPTION"  # 感知层
    STATEMACHINE = "STATEMACHINE"  # 状态机
    MULTITIMEFRAME = "MULTITIMEFRAME"  # 多周期融合
    EVOLUTION = "EVOLUTION"  # 进化层
    DATA_PIPELINE = "DATA_PIPELINE"  # 数据管道
    VISUALIZATION = "VISUALIZATION"  # 可视化


class PerformanceMonitor:
    """
    性能监控系统

    功能：
    1. 实时监控各模块健康状态
    2. 收集性能指标和错误统计
    3. 检测异常并触发报警
    4. 执行自动恢复动作
    5. 提供运维仪表板数据
    6. 支持容量规划和趋势分析
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化性能监控系统

        Args:
            config: 配置字典，包含以下参数：
                - monitoring_interval: 监控间隔秒数（默认60）
                - health_check_interval: 健康检查间隔秒数（默认300）
                - alert_cooldown: 报警冷却时间秒数（默认300）
                - max_history_days: 最大历史记录天数（默认30）
                - thresholds: 各指标阈值字典
                - auto_recovery_enabled: 是否启用自动恢复（默认True）
                - dashboard_enabled: 是否启用仪表板（默认True）
                - log_level: 日志级别（"INFO", "WARNING", "ERROR", "CRITICAL"）
        """
        self.config = config or {}

        # 监控参数
        self.monitoring_interval = self.config.get("monitoring_interval", 60)
        self.health_check_interval = self.config.get("health_check_interval", 300)
        self.alert_cooldown = self.config.get("alert_cooldown", 300)
        self.max_history_days = self.config.get("max_history_days", 30)

        # 功能开关
        self.auto_recovery_enabled = self.config.get("auto_recovery_enabled", True)
        self.dashboard_enabled = self.config.get("dashboard_enabled", True)
        self.log_level = self.config.get("log_level", "INFO")

        # 阈值配置
        self.thresholds = self.config.get("thresholds", self._get_default_thresholds())

        # 数据存储
        self.metrics_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)  # 每个指标最多保存10000个记录
        )
        self.alerts_history: list[dict[str, Any]] = []
        self.health_history: list[dict[str, Any]] = []
        self.recovery_actions: list[dict[str, Any]] = []

        # 模块引用
        self.modules: dict[str, Any] = {}
        self.module_health: dict[str, HealthStatus] = {}
        self.module_metrics: dict[str, dict[str, float]] = {}

        # 报警冷却
        self.alert_cooldown_timers: dict[str, datetime] = {}

        # 监控线程
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        self.health_check_thread: Optional[threading.Thread] = None

        # 系统整体健康状态
        self.system_health = HealthStatus.UNKNOWN
        self.system_health_score = 0.0  # 0-100分

        # 性能基准
        self.performance_baseline: Optional[dict[str, float]] = None
        self.performance_trends: dict[str, list[float]] = defaultdict(list)

        # 初始化时间
        self.start_time = datetime.now()
        self.last_monitoring_time = None
        self.last_health_check_time = None

        # 统计信息
        self.stats = {
            "total_alerts": 0,
            "total_recoveries": 0,
            "total_metrics_collected": 0,
            "uptime_seconds": 0.0,
            "downtime_seconds": 0.0,
        }

    def _get_default_thresholds(self) -> dict[str, dict[str, float]]:
        """获取默认阈值配置"""
        return {
            "error_rate": {"WARNING": 0.05, "ERROR": 0.10, "CRITICAL": 0.20},
            "response_time": {"WARNING": 2.0, "ERROR": 5.0, "CRITICAL": 10.0},  # 秒
            "memory_usage": {
                "WARNING": 0.70,
                "ERROR": 0.85,
                "CRITICAL": 0.95,
            },  # 百分比
            "cpu_usage": {"WARNING": 0.80, "ERROR": 0.90, "CRITICAL": 0.95},  # 百分比
            "queue_length": {"WARNING": 100, "ERROR": 500, "CRITICAL": 1000},
            "health_score": {"WARNING": 80.0, "ERROR": 60.0, "CRITICAL": 40.0},  # 分
        }

    def register_module(
        self,
        module_name: str,
        module_instance: Any,
        module_type: ModuleType = ModuleType.EVOLUTION,
        health_check_func: Optional[Callable] = None,
        metrics_func: Optional[Callable] = None,
    ):
        """
        注册模块到监控系统

        Args:
            module_name: 模块名称
            module_instance: 模块实例
            module_type: 模块类型
            health_check_func: 健康检查函数（返回HealthStatus）
            metrics_func: 指标收集函数（返回指标字典）
        """
        self.modules[module_name] = {
            "instance": module_instance,
            "type": module_type,
            "health_check_func": health_check_func,
            "metrics_func": metrics_func,
            "registration_time": datetime.now(),
            "last_health_check": None,
            "last_metrics_collection": None,
        }

        self.module_health[module_name] = HealthStatus.UNKNOWN
        self.module_metrics[module_name] = {}

        self._log(f"模块 '{module_name}' 已注册到监控系统", AlertLevel.INFO)

    def start_monitoring(self):
        """启动监控系统"""
        if self.monitoring_active:
            self._log("监控系统已在运行中", AlertLevel.WARNING)
            return

        self.monitoring_active = True

        # 启动监控线程
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True, name="PerformanceMonitor"
        )
        self.monitoring_thread.start()

        # 启动健康检查线程
        self.health_check_thread = threading.Thread(
            target=self._health_check_loop, daemon=True, name="HealthCheck"
        )
        self.health_check_thread.start()

        self._log("性能监控系统已启动", AlertLevel.INFO)

    def stop_monitoring(self):
        """停止监控系统"""
        self.monitoring_active = False

        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5.0)

        if self.health_check_thread:
            self.health_check_thread.join(timeout=5.0)

        self._log("性能监控系统已停止", AlertLevel.INFO)

    def _monitoring_loop(self):
        """监控主循环"""
        while self.monitoring_active:
            try:
                self._collect_metrics()
                self._check_thresholds()
                self._update_system_health()
                self._cleanup_old_data()

                self.last_monitoring_time = datetime.now()
                self.stats["uptime_seconds"] = float(  # type: ignore
                    (self.last_monitoring_time - self.start_time).total_seconds()
                )
                self.stats["total_metrics_collected"] = sum(
                    len(queue) for queue in self.metrics_history.values()
                )

            except Exception as e:
                self._log(f"监控循环出错: {e}", AlertLevel.ERROR)
                self._record_alert(
                    "MONITORING_ERROR",
                    AlertLevel.ERROR,
                    f"监控循环异常: {e!s}",
                    {"exception": str(e), "traceback": "N/A"},
                )

            # 等待下一个监控周期
            time.sleep(self.monitoring_interval)

    def _health_check_loop(self):
        """健康检查循环"""
        while self.monitoring_active:
            try:
                self._perform_health_checks()
                self.last_health_check_time = datetime.now()
            except Exception as e:
                self._log(f"健康检查出错: {e}", AlertLevel.ERROR)

            # 等待下一个健康检查周期
            time.sleep(self.health_check_interval)

    def _collect_metrics(self):
        """收集各模块指标"""
        current_time = datetime.now()

        for module_name, module_info in self.modules.items():
            try:
                metrics_func = module_info["metrics_func"]
                if metrics_func is not None:
                    metrics = metrics_func()
                    if isinstance(metrics, dict):
                        # 记录指标
                        for metric_name, metric_value in metrics.items():
                            if isinstance(metric_value, (int, float)):
                                self._record_metric(
                                    f"{module_name}.{metric_name}",
                                    metric_value,
                                    current_time,
                                )

                        # 更新模块指标缓存
                        self.module_metrics[module_name] = metrics
                        module_info["last_metrics_collection"] = current_time

                # 收集系统级指标（简化实现）
                self._collect_system_metrics(module_name)

            except Exception as e:
                self._log(
                    f"收集模块 '{module_name}' 指标时出错: {e}", AlertLevel.WARNING
                )
                self._record_alert(
                    f"METRICS_COLLECTION_ERROR_{module_name}",
                    AlertLevel.WARNING,
                    f"模块指标收集失败: {module_name}",
                    {"error": str(e), "module": module_name},
                )

    def _collect_system_metrics(self, module_name: str):
        """收集系统级指标（简化实现）"""
        # 在实际应用中，这里可以收集CPU、内存、磁盘、网络等指标
        # 这里使用模拟数据

        current_time = datetime.now()

        # 模拟错误率（基于模块名称的哈希）
        import hashlib

        hash_val = int(hashlib.md5(module_name.encode()).hexdigest(), 16)
        error_rate = (hash_val % 1000) / 10000.0  # 0-0.1之间的值

        self._record_metric(f"{module_name}.error_rate", error_rate, current_time)

        # 模拟响应时间
        response_time = 0.5 + (hash_val % 100) / 100.0  # 0.5-1.5秒
        self._record_metric(f"{module_name}.response_time", response_time, current_time)

        # 模拟内存使用率
        memory_usage = 0.3 + (hash_val % 70) / 100.0  # 30%-100%
        self._record_metric(f"{module_name}.memory_usage", memory_usage, current_time)

    def _perform_health_checks(self):
        """执行健康检查"""
        current_time = datetime.now()

        for module_name, module_info in self.modules.items():
            try:
                health_check_func = module_info["health_check_func"]
                if health_check_func is not None:
                    health_status = health_check_func()
                    if isinstance(health_status, HealthStatus):
                        old_status = self.module_health.get(
                            module_name, HealthStatus.UNKNOWN
                        )
                        self.module_health[module_name] = health_status
                        module_info["last_health_check"] = current_time

                        # 如果状态变化，记录事件
                        if old_status != health_status:
                            self._record_health_change(
                                module_name, old_status, health_status, current_time
                            )

                # 如果没有健康检查函数，根据指标推断健康状态
                else:
                    inferred_status = self._infer_health_from_metrics(module_name)
                    old_status = self.module_health.get(
                        module_name, HealthStatus.UNKNOWN
                    )
                    self.module_health[module_name] = inferred_status
                    module_info["last_health_check"] = current_time

                    if old_status != inferred_status:
                        self._record_health_change(
                            module_name, old_status, inferred_status, current_time
                        )

            except Exception as e:
                self._log(
                    f"检查模块 '{module_name}' 健康状态时出错: {e}", AlertLevel.WARNING
                )
                self.module_health[module_name] = HealthStatus.UNHEALTHY

    def _infer_health_from_metrics(self, module_name: str) -> HealthStatus:
        """根据指标推断健康状态"""
        # 获取最近指标
        recent_metrics = {}
        for metric_name in ["error_rate", "response_time", "memory_usage"]:
            full_name = f"{module_name}.{metric_name}"
            if self.metrics_history.get(full_name):
                recent_values = list(self.metrics_history[full_name])
                if recent_values:
                    # 取最近5个值的平均
                    recent_metrics[metric_name] = np.mean(
                        [v["value"] for v in recent_values[-5:]]
                    )

        # 根据阈值判断
        health_score = 100.0

        if "error_rate" in recent_metrics:
            error_rate = recent_metrics["error_rate"]
            if error_rate > self.thresholds["error_rate"]["CRITICAL"]:
                health_score -= 45
            elif error_rate > self.thresholds["error_rate"]["ERROR"]:
                health_score -= 25
            elif error_rate > self.thresholds["error_rate"]["WARNING"]:
                health_score -= 10

        if "response_time" in recent_metrics:
            response_time = recent_metrics["response_time"]
            if response_time > self.thresholds["response_time"]["CRITICAL"]:
                health_score -= 30
            elif response_time > self.thresholds["response_time"]["ERROR"]:
                health_score -= 20
            elif response_time > self.thresholds["response_time"]["WARNING"]:
                health_score -= 10

        if "memory_usage" in recent_metrics:
            memory_usage = recent_metrics["memory_usage"]
            if memory_usage > self.thresholds["memory_usage"]["CRITICAL"]:
                health_score -= 30
            elif memory_usage > self.thresholds["memory_usage"]["ERROR"]:
                health_score -= 20
            elif memory_usage > self.thresholds["memory_usage"]["WARNING"]:
                health_score -= 10

        # 根据健康分数确定状态
        if health_score >= self.thresholds["health_score"]["WARNING"]:
            return HealthStatus.HEALTHY
        if health_score >= self.thresholds["health_score"]["ERROR"]:
            return HealthStatus.DEGRADED
        if health_score >= self.thresholds["health_score"]["CRITICAL"]:
            return HealthStatus.UNHEALTHY
        return HealthStatus.CRITICAL

    def _check_thresholds(self):
        """检查指标阈值并触发报警"""
        current_time = datetime.now()

        for metric_full_name, metric_queue in self.metrics_history.items():
            if not metric_queue:
                continue

            # 获取最近值
            recent_values = list(metric_queue)[-10:]  # 最近10个值
            if not recent_values:
                continue

            current_value = recent_values[-1]["value"]
            metric_name = (
                metric_full_name.split(".")[-1]
                if "." in metric_full_name
                else metric_full_name
            )

            # 检查阈值
            if metric_name in self.thresholds:
                thresholds = self.thresholds[metric_name]

                # 确定当前级别
                current_level = None
                for level_name, threshold_value in thresholds.items():
                    if current_value >= threshold_value:
                        current_level = AlertLevel[level_name]

                if current_level:
                    # 检查是否在冷却期内
                    alert_key = f"{metric_full_name}_{current_level.value}"
                    if alert_key in self.alert_cooldown_timers:
                        last_alert_time = self.alert_cooldown_timers[alert_key]
                        if (
                            current_time - last_alert_time
                        ).total_seconds() < self.alert_cooldown:
                            continue  # 仍在冷却期

                    # 触发报警
                    self._record_alert(
                        f"THRESHOLD_EXCEEDED_{metric_full_name}",
                        current_level,
                        f"指标 '{metric_full_name}' 超过阈值: {current_value:.4f} >= {thresholds[current_level.name]}",
                        {
                            "metric": metric_full_name,
                            "value": current_value,
                            "threshold": thresholds[current_level.name],
                            "threshold_level": current_level.value,
                            "recent_values": [v["value"] for v in recent_values],
                        },
                    )

                    # 设置冷却计时器
                    self.alert_cooldown_timers[alert_key] = current_time

                    # 如果达到严重级别，尝试自动恢复
                    if (
                        current_level == AlertLevel.CRITICAL
                        and self.auto_recovery_enabled
                    ):
                        self._attempt_auto_recovery(metric_full_name, current_value)

    def _attempt_auto_recovery(self, metric_name: str, metric_value: float):
        """尝试自动恢复"""
        # 根据指标类型执行不同的恢复动作
        recovery_action = None

        if "error_rate" in metric_name:
            recovery_action = self._recover_from_high_error_rate(metric_name)
        elif "response_time" in metric_name:
            recovery_action = self._recover_from_high_response_time(metric_name)
        elif "memory_usage" in metric_name:
            recovery_action = self._recover_from_high_memory_usage(metric_name)

        if recovery_action:
            self.recovery_actions.append(recovery_action)
            self.stats["total_recoveries"] += 1

            self._log(
                f"已执行自动恢复动作: {recovery_action['action']}", AlertLevel.INFO
            )

        return recovery_action

    def _recover_from_high_error_rate(
        self, metric_name: str
    ) -> Optional[dict[str, Any]]:
        """从高错误率恢复"""
        # 提取模块名称
        parts = metric_name.split(".")
        if len(parts) >= 2:
            module_name = parts[0]

            # 尝试重启模块
            if module_name in self.modules:
                module_info = self.modules[module_name]
                module_instance = module_info["instance"]

                # 检查是否有重置或重启方法
                if hasattr(module_instance, "reset"):
                    try:
                        module_instance.reset()
                        return {
                            "timestamp": datetime.now(),
                            "metric": metric_name,
                            "action": f"RESET_MODULE_{module_name}",
                            "module": module_name,
                            "success": True,
                            "details": f"模块 {module_name} 已重置",
                        }
                    except Exception as e:
                        return {
                            "timestamp": datetime.now(),
                            "metric": metric_name,
                            "action": f"RESET_MODULE_{module_name}",
                            "module": module_name,
                            "success": False,
                            "details": f"重置失败: {e!s}",
                        }

        return None

    def _recover_from_high_response_time(
        self, metric_name: str
    ) -> Optional[dict[str, Any]]:
        """从高响应时间恢复"""
        # 简化实现：记录需要人工干预
        return {
            "timestamp": datetime.now(),
            "metric": metric_name,
            "action": "LOG_FOR_MANUAL_REVIEW",
            "module": metric_name.split(".")[0] if "." in metric_name else "unknown",
            "success": True,
            "details": "高响应时间需要人工检查",
        }

    def _recover_from_high_memory_usage(
        self, metric_name: str
    ) -> Optional[dict[str, Any]]:
        """从高内存使用率恢复"""
        # 简化实现：建议清理缓存
        return {
            "timestamp": datetime.now(),
            "metric": metric_name,
            "action": "SUGGEST_CACHE_CLEANUP",
            "module": metric_name.split(".")[0] if "." in metric_name else "unknown",
            "success": True,
            "details": "建议清理内存缓存",
        }

    def _update_system_health(self):
        """更新系统整体健康状态"""
        if not self.module_health:
            self.system_health = HealthStatus.UNKNOWN
            self.system_health_score = 0.0
            return

        # 计算健康分数
        health_scores = []
        for module_name, health_status in self.module_health.items():
            if health_status == HealthStatus.HEALTHY:
                health_scores.append(100.0)
            elif health_status == HealthStatus.DEGRADED:
                health_scores.append(75.0)
            elif health_status == HealthStatus.UNHEALTHY:
                health_scores.append(50.0)
            elif health_status == HealthStatus.CRITICAL:
                health_scores.append(25.0)
            else:
                health_scores.append(0.0)

        avg_health_score = np.mean(health_scores) if health_scores else 0.0
        self.system_health_score = avg_health_score

        # 确定整体健康状态
        if avg_health_score >= self.thresholds["health_score"]["WARNING"]:
            self.system_health = HealthStatus.HEALTHY
        elif avg_health_score >= self.thresholds["health_score"]["ERROR"]:
            self.system_health = HealthStatus.DEGRADED
        elif avg_health_score >= self.thresholds["health_score"]["CRITICAL"]:
            self.system_health = HealthStatus.UNHEALTHY
        else:
            self.system_health = HealthStatus.CRITICAL

        # 记录健康历史
        self.health_history.append(
            {
                "timestamp": datetime.now(),
                "system_health": self.system_health.value,
                "system_health_score": self.system_health_score,
                "module_health": dict(self.module_health),
                "module_scores": dict(zip(self.module_health.keys(), health_scores)),
            }
        )

    def _cleanup_old_data(self):
        """清理旧数据"""
        cutoff_time = datetime.now() - timedelta(days=self.max_history_days)

        # 清理指标历史
        for metric_name, metric_queue in self.metrics_history.items():
            # 由于使用deque有限长度，自动清理旧数据
            pass

        # 清理报警历史
        self.alerts_history = [
            alert for alert in self.alerts_history if alert["timestamp"] > cutoff_time
        ]

        # 清理健康历史
        self.health_history = [
            health
            for health in self.health_history
            if health["timestamp"] > cutoff_time
        ]

    def _record_metric(self, metric_name: str, value: float, timestamp: datetime):
        """记录指标"""
        self.metrics_history[metric_name].append(
            {
                "timestamp": timestamp,
                "value": value,
            }
        )

    def _record_alert(
        self, alert_id: str, level: AlertLevel, message: str, details: dict[str, Any]
    ):
        """记录报警"""
        alert = {
            "alert_id": alert_id,
            "timestamp": datetime.now(),
            "level": level.value,
            "message": message,
            "details": details,
            "acknowledged": False,
            "resolved": False,
        }

        self.alerts_history.append(alert)
        self.stats["total_alerts"] += 1

        # 根据级别记录日志
        self._log(f"报警 [{level.value}]: {message}", level)

        # 如果达到严重级别，尝试通知（简化实现）
        if level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
            self._notify_critical_alert(alert)

    def _record_health_change(
        self,
        module_name: str,
        old_status: HealthStatus,
        new_status: HealthStatus,
        timestamp: datetime,
    ):
        """记录健康状态变化"""
        self._log(
            f"模块 '{module_name}' 健康状态变化: {old_status.value} -> {new_status.value}",
            AlertLevel.INFO
            if new_status.value in ["HEALTHY", "DEGRADED"]
            else AlertLevel.WARNING,
        )

    def _notify_critical_alert(self, alert: dict[str, Any]):
        """通知严重报警（简化实现）"""
        # 在实际应用中，这里可以发送邮件、短信、Slack消息等
        # 这里仅记录日志
        self._log(f"严重报警需要人工干预: {alert['message']}", AlertLevel.CRITICAL)

    def _log(self, message: str, level: AlertLevel):
        """记录日志"""
        # 根据配置的日志级别过滤
        level_order = {
            AlertLevel.INFO: 0,
            AlertLevel.WARNING: 1,
            AlertLevel.ERROR: 2,
            AlertLevel.CRITICAL: 3,
        }

        config_level = getattr(AlertLevel, self.log_level, AlertLevel.INFO)

        if level_order[level] >= level_order[config_level]:
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_dashboard_data(self) -> dict[str, Any]:
        """获取仪表板数据"""
        current_time = datetime.now()

        # 计算最近一小时的平均指标
        one_hour_ago = current_time - timedelta(hours=1)

        recent_metrics = {}
        for metric_name, metric_queue in self.metrics_history.items():
            recent_values = [
                m["value"] for m in metric_queue if m["timestamp"] > one_hour_ago
            ]
            if recent_values:
                recent_metrics[metric_name] = {
                    "current": recent_values[-1] if recent_values else 0.0,
                    "avg": np.mean(recent_values) if recent_values else 0.0,
                    "min": min(recent_values) if recent_values else 0.0,
                    "max": max(recent_values) if recent_values else 0.0,
                    "count": len(recent_values),
                }

        # 获取未解决的报警
        unresolved_alerts = [
            alert
            for alert in self.alerts_history[-20:]  # 最近20个报警
            if not alert["resolved"] and alert["level"] in ["ERROR", "CRITICAL"]
        ]

        # 获取最近恢复动作
        recent_recoveries = self.recovery_actions[-10:] if self.recovery_actions else []

        return {
            "timestamp": current_time.isoformat(),
            "system_health": {
                "status": self.system_health.value,
                "score": self.system_health_score,
                "uptime_seconds": self.stats["uptime_seconds"],
            },
            "module_health": {
                module_name: {
                    "status": health_status.value,
                    "last_check": self.modules[module_name].get("last_health_check"),
                    "metrics": self.module_metrics.get(module_name, {}),
                }
                for module_name, health_status in self.module_health.items()
            },
            "recent_metrics": recent_metrics,
            "alerts": {
                "total": self.stats["total_alerts"],
                "unresolved": len(unresolved_alerts),
                "recent": unresolved_alerts[:5],
            },
            "recoveries": {
                "total": self.stats["total_recoveries"],
                "recent": recent_recoveries,
            },
            "performance_trends": {
                metric_name: values[-24:] if values else []  # 最近24个值
                for metric_name, values in self.performance_trends.items()
            },
            "stats": self.stats,
        }

    def get_health_report(self) -> dict[str, Any]:
        """获取健康报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "system_health": self.system_health.value,
            "system_health_score": self.system_health_score,
            "module_count": len(self.modules),
            "healthy_modules": sum(
                1
                for status in self.module_health.values()
                if status == HealthStatus.HEALTHY
            ),
            "degraded_modules": sum(
                1
                for status in self.module_health.values()
                if status == HealthStatus.DEGRADED
            ),
            "unhealthy_modules": sum(
                1
                for status in self.module_health.values()
                if status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]
            ),
            "alerts_last_24h": len(
                [
                    alert
                    for alert in self.alerts_history
                    if alert["timestamp"] > datetime.now() - timedelta(hours=24)
                ]
            ),
            "recoveries_last_24h": len(
                [
                    recovery
                    for recovery in self.recovery_actions
                    if recovery["timestamp"] > datetime.now() - timedelta(hours=24)
                ]
            ),
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> list[str]:
        """生成优化建议"""
        recommendations = []

        # 检查模块健康状态
        for module_name, health_status in self.module_health.items():
            if health_status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
                recommendations.append(
                    f"模块 '{module_name}' 状态不佳 ({health_status.value})，建议检查"
                )

        # 检查错误率
        for metric_name, metric_queue in self.metrics_history.items():
            if "error_rate" in metric_name and metric_queue:
                recent_values = [m["value"] for m in list(metric_queue)[-10:]]
                if recent_values:
                    avg_error_rate = np.mean(recent_values)
                    if avg_error_rate > self.thresholds["error_rate"]["WARNING"]:
                        recommendations.append(
                            f"指标 '{metric_name}' 错误率较高 ({avg_error_rate:.2%})，建议优化"
                        )

        # 检查响应时间
        for metric_name, metric_queue in self.metrics_history.items():
            if "response_time" in metric_name and metric_queue:
                recent_values = [m["value"] for m in list(metric_queue)[-10:]]
                if recent_values:
                    avg_response_time = np.mean(recent_values)
                    if avg_response_time > self.thresholds["response_time"]["WARNING"]:
                        recommendations.append(
                            f"指标 '{metric_name}' 响应时间较慢 ({avg_response_time:.2f}s)，建议优化"
                        )

        # 如果没有建议，返回积极反馈
        if not recommendations:
            recommendations.append("系统运行良好，继续保持！")

        return recommendations[:5]  # 最多返回5条建议

    def record_success(self, module_name: str, execution_time: float = 0.0) -> None:
        """
        记录模块成功执行

        Args:
            module_name: 模块名称
            execution_time: 执行时间（秒）
        """
        metric_name = f"{module_name}.success_count"
        self.record_metric(metric_name, 1.0)

        if execution_time > 0:
            time_metric = f"{module_name}.execution_time"
            self.record_metric(time_metric, execution_time)

        # 更新模块健康状态
        if module_name in self.module_health:
            if self.module_health[module_name] == HealthStatus.UNKNOWN:
                self.module_health[module_name] = HealthStatus.HEALTHY

    def record_error(
        self, module_name: str, error_type: str = "general", error_details: str = ""
    ) -> None:
        """
        记录模块错误

        Args:
            module_name: 模块名称
            error_type: 错误类型
            error_details: 错误详情
        """
        metric_name = f"{module_name}.error_count"
        self.record_metric(metric_name, 1.0)

        error_metric = f"{module_name}.error_type.{error_type}"
        self.record_metric(error_metric, 1.0)

        # 记录错误详情
        error_record = {
            "timestamp": datetime.now(),
            "module": module_name,
            "error_type": error_type,
            "error_details": error_details,
            "resolved": False,
        }
        self.alerts_history.append(error_record)

        # 更新模块健康状态
        if module_name in self.module_health:
            self.module_health[module_name] = HealthStatus.DEGRADED

    def record_metric(
        self, metric_name: str, value: float, timestamp: Optional[datetime] = None
    ) -> None:
        """
        记录性能指标

        Args:
            metric_name: 指标名称
            value: 指标值
            timestamp: 时间戳（默认为当前时间）
        """
        if timestamp is None:
            timestamp = datetime.now()
        self._record_metric(metric_name, value, timestamp)

    def get_performance_summary(self) -> dict[str, Any]:
        """
        获取性能指标摘要

        Returns:
            包含性能摘要的字典
        """
        current_time = datetime.now()
        one_hour_ago = current_time - timedelta(hours=1)

        summary = {}

        # 计算每个指标最近一小时的平均值
        for metric_name, metric_queue in self.metrics_history.items():
            recent_values = [
                m["value"] for m in metric_queue if m["timestamp"] > one_hour_ago
            ]
            if recent_values:
                summary[metric_name] = {
                    "current": recent_values[-1] if recent_values else 0.0,
                    "average": np.mean(recent_values) if recent_values else 0.0,
                    "min": min(recent_values) if recent_values else 0.0,
                    "max": max(recent_values) if recent_values else 0.0,
                    "count": len(recent_values),
                    "trend": "up"
                    if len(recent_values) >= 2 and recent_values[-1] > recent_values[0]
                    else "down",
                }

        return summary

    def get_dashboard(self) -> dict[str, Any]:
        """
        获取仪表板数据

        Returns:
            包含所有仪表板数据的字典
        """
        return {
            "system_health": self.get_health_report(),
            "module_status": dict(self.module_health),
            "recent_alerts": self.alerts_history[-10:] if self.alerts_history else [],
            "performance_metrics": self.get_performance_summary(),
            "recommendations": self._generate_recommendations(),
            "timestamp": datetime.now().isoformat(),
        }

    def acknowledge_alert(self, alert_id: str, resolved: bool = True):
        """确认报警"""
        for alert in self.alerts_history:
            if alert["alert_id"] == alert_id:
                alert["acknowledged"] = True
                alert["resolved"] = resolved
                alert["resolved_time"] = datetime.now()
                break

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_alerts": 0,
            "total_recoveries": 0,
            "total_metrics_collected": 0,
            "uptime_seconds": 0.0,
            "downtime_seconds": 0.0,
        }
        self._log("统计信息已重置", AlertLevel.INFO)


# 使用示例
if __name__ == "__main__":
    # 创建性能监控系统
    monitor = PerformanceMonitor(
        {
            "monitoring_interval": 10,  # 10秒监控间隔（示例用）
            "health_check_interval": 30,  # 30秒健康检查
            "alert_cooldown": 60,  # 60秒报警冷却
            "auto_recovery_enabled": True,
        }
    )

    # 示例模块
    class ExampleModule:
        def __init__(self, name):
            self.name = name
            self.error_count = 0
            self.request_count = 0

        def health_check(self):
            # 模拟健康检查
            import random

            statuses = [
                HealthStatus.HEALTHY,
                HealthStatus.DEGRADED,
                HealthStatus.UNHEALTHY,
                HealthStatus.CRITICAL,
            ]
            return random.choice(statuses)

        def collect_metrics(self):
            # 模拟指标收集
            import random

            self.request_count += random.randint(1, 10)
            self.error_count += random.randint(0, 2)

            error_rate = self.error_count / max(self.request_count, 1)

            return {
                "request_count": self.request_count,
                "error_count": self.error_count,
                "error_rate": error_rate,
                "response_time_ms": random.uniform(50, 500),
                "memory_usage_mb": random.uniform(100, 500),
            }

    # 创建示例模块实例
    module1 = ExampleModule("WyckoffStateMachine")
    module2 = ExampleModule("PeriodWeightFilter")

    # 注册模块到监控系统
    monitor.register_module(
        "WyckoffStateMachine",
        module1,
        ModuleType.STATEMACHINE,
        health_check_func=module1.health_check,
        metrics_func=module1.collect_metrics,
    )

    monitor.register_module(
        "PeriodWeightFilter",
        module2,
        ModuleType.MULTITIMEFRAME,
        health_check_func=module2.health_check,
        metrics_func=module2.collect_metrics,
    )

    # 启动监控
    monitor.start_monitoring()

    # 运行一段时间
    import time

    time.sleep(10)

    # 停止监控
    monitor.stop_monitoring()

    # 获取仪表板数据
    dashboard = monitor.get_dashboard_data()

    for module_name, health_info in dashboard["module_health"].items():
        pass

    # 获取健康报告
    health_report = monitor.get_health_report()

    for rec in health_report["recommendations"]:
        pass
