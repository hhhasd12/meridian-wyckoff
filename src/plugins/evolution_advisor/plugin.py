"""进化顾问插件 — 订阅进化事件，异步调用 LLM 分析

工作流程：
  进化循环完成 → EventBus: evolution.cycle_complete
    → EvolutionAdvisorPlugin（异步，不阻塞进化）
      → 收集 MistakeBook 模式 + Config 变化 + 性能趋势
      → 调用 LLM (GPT-4o-mini 或 Ollama)
      → 发布 advisor.analysis_complete 事件
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class EvolutionAdvisorPlugin(BasePlugin):
    """进化顾问插件 — LLM 分析进化表现

    订阅 evolution.cycle_complete 事件，异步调用 LLM
    生成分析报告，通过事件总线推送给 Dashboard/WebSocket。
    """

    def __init__(self, name: str = "evolution_advisor") -> None:
        super().__init__(name=name)
        self._advisor: Optional[Any] = None
        self._enabled: bool = False
        self._analysis_count: int = 0
        self._last_error: Optional[str] = None
        self._last_analysis: Optional[Dict[str, Any]] = None

    def on_load(self) -> None:
        """加载插件 — 初始化 Advisor 并订阅事件"""
        config = self._config
        self._enabled = config.get("enabled", False)

        if not self._enabled:
            logger.info("进化顾问已禁用（config.enabled=false）")
            return

        try:
            from src.plugins.evolution_advisor.advisor import (
                EvolutionAdvisor,
            )

            self._advisor = EvolutionAdvisor(
                provider=config.get("provider", "openai"),
                model=config.get("model", "gpt-4o-mini"),
                api_key=config.get("api_key", ""),
                ollama_url=config.get("ollama_url", "http://localhost:11434"),
                max_history=config.get("max_history", 50),
            )
            logger.info("进化顾问初始化完成")
        except Exception as e:
            self._last_error = str(e)
            logger.warning("进化顾问初始化失败: %s", e)
            return

        # 订阅进化完成事件
        self.subscribe_event(
            "evolution.cycle_complete",
            self._on_cycle_complete,
        )
        logger.info("进化顾问已订阅 evolution.cycle_complete")

    def on_unload(self) -> None:
        """卸载插件"""
        self._advisor = None
        self._enabled = False
        self._last_analysis = None

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        if not self._enabled:
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="进化顾问已禁用",
                details={"enabled": False},
            )

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"进化顾问有错误: {self._last_error}",
                details={
                    "enabled": True,
                    "analysis_count": self._analysis_count,
                    "last_error": self._last_error,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="进化顾问正常运行",
            details={
                "enabled": True,
                "analysis_count": self._analysis_count,
                "has_advisor": self._advisor is not None,
            },
        )

    def _on_cycle_complete(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理进化周期完成事件

        异步启动分析任务，不阻塞进化主循环。

        Args:
            event_name: 事件名称
            data: 进化周期数据
        """
        if not self._enabled or self._advisor is None:
            return

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._analyze_async(data))
            else:
                loop.run_until_complete(self._analyze_async(data))
        except RuntimeError:
            logger.debug("无可用事件循环，跳过异步分析")

    async def _analyze_async(
        self,
        cycle_data: Dict[str, Any],
    ) -> None:
        """异步执行 LLM 分析

        Args:
            cycle_data: 进化周期数据
        """
        if self._advisor is None:
            return

        try:
            # 收集 MistakeBook 模式
            mistake_patterns = self._collect_mistake_patterns()

            # 调用 Advisor 分析
            result = await self._advisor.analyze_cycle(
                cycle_data,
                mistake_patterns=mistake_patterns,
            )

            self._analysis_count += 1
            self._last_analysis = result
            self._last_error = None

            # 发布分析完成事件
            self.emit_event(
                "advisor.analysis_complete",
                {
                    "generation": result.get("generation", 0),
                    "analysis": result.get("analysis", ""),
                    "plateau_warning": result.get("plateau_warning"),
                    "mistake_summary": result.get("mistake_summary"),
                    "mutation_advice": result.get("mutation_advice"),
                    "timestamp": result.get("timestamp", ""),
                },
            )

            logger.info(
                "进化顾问分析完成: 第%d轮",
                result.get("generation", 0),
            )

        except Exception as e:
            self._last_error = str(e)
            logger.error("进化顾问分析失败: %s", e)

    def _collect_mistake_patterns(
        self,
    ) -> List[Dict[str, Any]]:
        """从 MistakeBook 收集错误模式

        Returns:
            错误模式列表
        """
        # 尝试通过 self_correction 插件获取 MistakeBook
        self_correction = self.get_plugin("self_correction")
        if self_correction is None:
            return []

        if not hasattr(self_correction, "get_mistake_book"):
            return []

        mistake_book = self_correction.get_mistake_book()  # type: ignore[attr-defined]
        if mistake_book is None:
            return []

        # 获取模式分析
        if hasattr(mistake_book, "analyze_patterns"):
            analysis = mistake_book.analyze_patterns()
            patterns = analysis.get("frequent_patterns", [])
            return patterns

        return []

    # ================================================================
    # 公共查询接口（供 API 层调用）
    # ================================================================

    def get_last_analysis(self) -> Optional[Dict[str, Any]]:
        """获取最近一次分析结果

        Returns:
            分析结果字典，无分析时返回 None
        """
        return self._last_analysis

    def get_analysis_history(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取分析历史

        Args:
            limit: 返回的最大记录数

        Returns:
            分析历史列表
        """
        if self._advisor is None:
            return []
        return self._advisor.get_analysis_history(limit)

    def get_fitness_trend(self) -> Dict[str, Any]:
        """获取 fitness 趋势

        Returns:
            趋势摘要字典
        """
        if self._advisor is None:
            return {"trend": "not_initialized", "values": []}
        return self._advisor.get_fitness_trend()

    def get_advisor_status(self) -> Dict[str, Any]:
        """获取顾问状态

        Returns:
            状态字典
        """
        return {
            "enabled": self._enabled,
            "analysis_count": self._analysis_count,
            "last_error": self._last_error,
            "has_last_analysis": self._last_analysis is not None,
        }
