"""自我纠错插件

将 SelfCorrectionWorkflow 包装为标准插件，提供：
1. 生命周期管理（on_load / on_unload）
2. 事件驱动：订阅 evolution.cycle_complete 触发纠错
3. 发布 self_correction.cycle_completed 事件
4. 健康检查

核心逻辑复用 src/plugins/self_correction/workflow.py 中的
SelfCorrectionWorkflow 类（使用 GeneticAlgorithm + WFAValidator + StandardEvaluator）。
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class SelfCorrectionPlugin(BasePlugin):
    """自我纠错插件

    封装 SelfCorrectionWorkflow，通过事件总线与其他插件通信。
    当进化周期完成后自动触发自我纠错流程。

    Attributes:
        _workflow: SelfCorrectionWorkflow 实例
        _correction_count: 纠错执行计数
        _last_error: 最近一次错误信息
        _last_correction_time: 最近一次纠错时间
    """

    def __init__(
        self,
        name: str = "self_correction",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name=name, config=config)
        self._workflow: Any = None
        self._correction_count: int = 0
        self._last_error: Optional[str] = None
        self._last_correction_time: Optional[datetime] = None

    def on_load(self) -> None:
        """加载插件：初始化 SelfCorrectionWorkflow 并订阅事件

        Raises:
            PluginError: 当核心 Workflow 模块无法导入时
        """
        try:
            from src.plugins.self_correction.workflow import (
                SelfCorrectionWorkflow,
            )

            self._workflow = SelfCorrectionWorkflow(config=self._config)
        except ImportError as e:
            self._logger.error("SelfCorrectionWorkflow 导入失败: %s", e)
            from src.kernel.types import PluginError

            raise PluginError(
                f"核心 Workflow 模块导入失败: {e}",
                plugin_name=self._name,
            ) from e

        self._correction_count = 0
        self._last_error = None
        self._last_correction_time = None

        # 订阅进化周期完成事件
        self.subscribe_event(
            "evolution.cycle_complete",
            self._on_evolution_cycle_completed,
        )

        self._logger.info(
            "SelfCorrectionPlugin 已加载，enabled=%s",
            self._config.get("enabled", True),
        )

    def on_unload(self) -> None:
        """卸载插件：清理资源"""
        self._workflow = None
        self._correction_count = 0
        self._last_error = None
        self._last_correction_time = None
        self._logger.info("SelfCorrectionPlugin 已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """配置热更新"""
        self._config = new_config
        if self._workflow is not None:
            try:
                from src.plugins.self_correction.workflow import (
                    SelfCorrectionWorkflow,
                )

                self._workflow = SelfCorrectionWorkflow(config=new_config)
                self._logger.info("SelfCorrectionPlugin 配置已热更新")
            except ImportError:
                self._logger.warning("配置更新时 SelfCorrectionWorkflow 导入失败")

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        base_check = super().health_check()
        if base_check.status != HealthStatus.HEALTHY:
            return base_check

        if not self._config.get("enabled", True):
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="自我纠错已禁用",
            )

        if self._workflow is None:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message="SelfCorrectionWorkflow 未初始化",
            )

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近错误: {self._last_error}",
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=(f"运行正常，已执行 {self._correction_count} 次纠错"),
        )

    # ---- 事件处理器 ----

    def _on_evolution_cycle_completed(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理进化周期完成事件，触发自我纠错

        Args:
            event_name: 事件名称
            data: 事件数据
        """
        if not self._config.get("enabled", True):
            self._logger.debug("自我纠错已禁用，跳过")
            return

        cycle_count = data.get("cycle_count", 0)
        self._logger.info(
            "收到进化周期完成事件 (cycle=%d)，触发自我纠错",
            cycle_count,
        )

        result = self.run_correction_cycle()

        if result.get("success", False):
            self._logger.info(
                "自我纠错完成: %s",
                result.get("summary", "无摘要"),
            )
        else:
            self._logger.warning(
                "自我纠错未成功: %s",
                result.get("error", "未知错误"),
            )

    # ---- 公共 API ----

    def run_correction_cycle(self) -> Dict[str, Any]:
        """执行一次纠错周期

        Returns:
            纠错结果字典
        """
        if self._workflow is None:
            self._logger.warning("SelfCorrectionWorkflow 未初始化，跳过纠错")
            return {
                "success": False,
                "error": "workflow_not_initialized",
            }

        self.emit_event(
            "self_correction.cycle_started",
            {"correction_count": self._correction_count},
        )

        try:
            result = self._workflow.run_correction_cycle()
            self._correction_count += 1
            self._last_error = None
            self._last_correction_time = datetime.now()

            self.emit_event(
                "self_correction.cycle_completed",
                {
                    "correction_count": self._correction_count,
                    "result": result,
                },
            )

            if result.get("applied", False):
                self.emit_event(
                    "self_correction.correction_applied",
                    {
                        "correction_count": (self._correction_count),
                        "changes": result.get("changes", {}),
                    },
                )

            return {
                "success": True,
                "summary": result.get("summary", ""),
                "result": result,
            }

        except (ValueError, RuntimeError, KeyError) as e:
            self._last_error = str(e)
            self._logger.error("纠错周期执行失败: %s", e)
            self.emit_event(
                "self_correction.error_occurred",
                {
                    "error": str(e),
                    "correction_count": (self._correction_count),
                },
            )
            return {"success": False, "error": str(e)}

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "correction_count": self._correction_count,
            "last_error": self._last_error,
            "last_correction_time": (
                self._last_correction_time.isoformat()
                if self._last_correction_time
                else None
            ),
            "enabled": self._config.get("enabled", True),
            "workflow_initialized": (self._workflow is not None),
        }

    def set_historical_data(self, data: Dict[str, Any]) -> None:
        """设置历史数据供 GA+WFA 使用

        Args:
            data: 多TF数据字典 {"H4": df, "H1": df, ...}
        """
        if self._workflow is not None:
            self._workflow.set_historical_data(data)
