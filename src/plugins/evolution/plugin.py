"""进化系统插件 — GA + WFA + AntiOverfit 进化主循环

连接组件：
- GeneticAlgorithm: 种群进化
- StandardEvaluator: 逐bar回测评估
- WFAValidator: 滚动窗口验证
- AntiOverfitGuard: 五层防过拟合
- MistakeBook: 错题本反馈

进化流程：
1. GA 产生候选配置种群
2. StandardEvaluator 评估每个配置
3. WFAValidator 验证最佳配置的样本外稳健性
4. AntiOverfitGuard 五层检查
5. 通过则采纳，否则保持当前配置
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class EvolutionPlugin(BasePlugin):
    """进化系统插件 — GA + WFA + AntiOverfit

    进化主循环由 run_evolution_cycle() 驱动。
    """

    def __init__(self, name: str = "evolution") -> None:
        super().__init__(name=name)
        self.is_running = False
        self._is_evolving: bool = False
        self._cycle_count: int = 0
        self._last_error: Optional[str] = None
        self._record_count: int = 0
        self._archivist: Any = None

        # 进化组件（activate 时初始化）
        self._ga: Any = None
        self._evaluator: Any = None
        self._wfa: Any = None
        self._anti_overfit: Any = None
        self._mistake_book: Any = None
        self._current_config: Dict[str, Any] = {}
        self._data_dict: Dict[str, pd.DataFrame] = {}

    async def activate(self, context: dict[str, Any]) -> None:
        """激活插件 — 初始化进化组件"""
        config = context.get("config", {}).get("evolution", {})
        self._current_config = config.get("initial_config", {})

        try:
            from src.plugins.evolution.anti_overfit import AntiOverfitGuard
            from src.plugins.evolution.evaluator import StandardEvaluator
            from src.plugins.evolution.genetic_algorithm import (
                GAConfig,
                GeneticAlgorithm,
            )
            from src.plugins.evolution.wfa_validator import WFAValidator
            from src.plugins.self_correction.mistake_book import MistakeBook

            self._mistake_book = MistakeBook(config.get("mistake_book_config", {}))
            self._evaluator = StandardEvaluator(mistake_book=self._mistake_book)
            self._anti_overfit = AntiOverfitGuard()

            ga_cfg = GAConfig(
                population_size=config.get("population_size", 20),
                max_generations=config.get("max_generations", 50),
            )
            self._ga = GeneticAlgorithm(self._current_config, ga_cfg)
            self._wfa = WFAValidator(evaluator_fn=self._evaluator)

            logger.info("EvolutionPlugin activated with GA+WFA+AntiOverfit")
        except Exception as e:
            logger.warning("EvolutionPlugin activation partial: %s", e)
            self._last_error = str(e)

    async def deactivate(self) -> None:
        """停用插件"""
        self.is_running = False
        self._is_evolving = False
        logger.info("EvolutionPlugin deactivated")

    def on_load(self) -> None:
        """加载插件"""
        pass

    def on_unload(self) -> None:
        """卸载插件"""
        self.is_running = False
        self._is_evolving = False
        self._ga = None
        self._evaluator = None
        self._wfa = None
        self._anti_overfit = None
        self._last_error = None

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        from src.kernel.base_plugin import PluginState

        if self._state != PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="进化系统未激活",
                details={"is_running": self.is_running},
            )

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"进化系统有错误: {self._last_error}",
                details={
                    "is_running": self.is_running,
                    "last_error": self._last_error,
                    "cycle_count": self._cycle_count,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="进化系统正常运行",
            details={
                "is_running": self.is_running,
                "cycle_count": self._cycle_count,
                "record_count": self._record_count,
            },
        )

    # ================================================================
    # 进化控制接口
    # ================================================================

    def set_data(self, data_dict: Dict[str, pd.DataFrame]) -> None:
        """设置数据"""
        self._data_dict = data_dict

    def get_evolution_status(self) -> dict[str, Any]:
        """获取进化状态"""
        return {
            "status": "running" if self._is_evolving else "stopped",
            "cycle_count": self._cycle_count,
            "start_time": None,
        }

    def get_current_config(self) -> dict:
        """获取当前配置"""
        return dict(self._current_config) if self._current_config else {}

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "record_count": self._record_count,
            "last_error": self._last_error,
            "is_evolving": self._is_evolving,
            "cycle_count": self._cycle_count,
        }

    async def start_evolution(self) -> dict[str, str]:
        """启动进化"""
        if self._ga is None and self._evaluator is None:
            return {"status": "error", "message": "工作流未初始化"}
        self._is_evolving = True
        return {"status": "started"}

    async def stop_evolution(self) -> dict[str, str]:
        """停止进化"""
        if not self._is_evolving:
            return {"status": "already_stopped"}
        self._is_evolving = False
        return {"status": "stopped"}

    # ================================================================
    # 兼容旧接口（API层调用）
    # ================================================================

    def start_archivist(self) -> None:
        """启动档案员"""
        if self._archivist is None:
            raise RuntimeError("档案员未初始化")
        self._archivist.start()

    def stop_archivist(self) -> None:
        """停止档案员"""
        if self._archivist is not None:
            self._archivist.stop()

    def record_log(self, log: Any) -> bool:
        """记录进化日志"""
        if self._archivist is None:
            return False
        result = self._archivist.record_log(log)
        if result:
            self._record_count += 1
        return result

    def query_history(self, query: str, top_k: int = 5) -> list:
        """查询进化历史"""
        if self._archivist is None:
            return []
        return self._archivist.query_history(query, top_k=top_k)

    def get_positions(self) -> list:
        """获取进化盘持仓"""
        return []

    def get_position(self, position_id: str) -> Optional[dict]:
        """获取单个持仓"""
        return None

    def add_position(self, position_data: dict) -> dict:
        """添加持仓"""
        return {}

    def close_position(self, position_id: str, close_price: float) -> Optional[dict]:
        """平仓"""
        return None

    def get_trades(self) -> list:
        """获取交易记录"""
        return []

    def get_evolution_statistics(self) -> dict:
        """获取进化统计"""
        return {}
