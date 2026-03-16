"""进化系统插件 - 完整的进化引擎

整合 SelfCorrectionWorkflow、MistakeBook、WFABacktester，
提供统一的进化系统插件接口。

功能：
1. 进化周期运行（本地数据 + WFA验证）
2. 进化记忆管理（向量化存储）
3. 错题本管理
4. 配置进化追踪
5. 进化盘持仓和交易管理（独立于实盘）
"""

import asyncio
import copy
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus
from src.storage.evolution_storage import EvolutionStorage

logger = logging.getLogger(__name__)


class EvolutionPlugin(BasePlugin):
    """进化系统插件

    整合完整的进化逻辑：
    - SelfCorrectionWorkflow: 自我修正闭环
    - MistakeBook: 错题本
    - WFABacktester: WFA回测验证
    - EvolutionArchivist: 向量化记忆

    运行模式：
    - 本地数据进化（使用 data/ 目录的历史数据）
    - WFA验证防止过拟合
    - 进化结果持久化
    """

    def __init__(self, name: str = "evolution") -> None:
        super().__init__(name)

        self._workflow = None
        self._archivist = None

        self._is_evolving: bool = False
        self._evolution_task: Optional[asyncio.Task] = None
        self._cycle_count: int = 0
        self._last_cycle_result: Optional[Dict[str, Any]] = None
        self._start_time: Optional[datetime] = None

        self._config: Dict[str, Any] = {}
        self._symbols: List[str] = ["ETH/USDT"]
        self._timeframes: List[str] = ["H4", "H1", "M15"]
        self._cycle_interval: int = 3600

        self._historical_data: Dict[str, pd.DataFrame] = {}

        self._record_count: int = 0
        self._last_error: Optional[str] = None

        self._storage: Optional[EvolutionStorage] = None

    def on_load(self) -> None:
        """加载插件"""
        self._config = self._config or {}

        from src.plugins.evolution.archivist import EvolutionArchivist

        archivist_config = self._config.get("archivist", {})
        self._archivist = EvolutionArchivist(config=archivist_config)

        self._init_workflow()

        self._load_historical_data()

        self._storage = EvolutionStorage(storage_path="evolution_data")

        logger.info(
            "EvolutionPlugin 已加载 (symbols=%s, timeframes=%s)",
            self._symbols,
            self._timeframes,
        )

    def _init_workflow(self) -> None:
        """初始化自我修正工作流"""
        try:
            from src.plugins.self_correction.workflow import SelfCorrectionWorkflow
            from src.plugins.self_correction.mistake_book import MistakeBook
            from src.core.weight_variator import WeightVariator  # legacy，暂无插件版本
            from src.plugins.evolution.wfa_backtester import WFABacktester
        except ImportError as e:
            logger.error("导入工作流组件失败: %s", e)
            raise

        workflow_config = self._config.get(
            "workflow", self._create_default_workflow_config()
        )

        mistake_book = MistakeBook(workflow_config.get("mistake_book_config", {}))
        weight_variator = WeightVariator(
            workflow_config.get("weight_variator_config", {})
        )
        wfa_backtester = WFABacktester(workflow_config.get("wfa_backtester_config", {}))

        self._workflow = SelfCorrectionWorkflow(
            config=workflow_config,
            mistake_book=mistake_book,
            weight_variator=weight_variator,
            wfa_backtester=wfa_backtester,
        )

        logger.info("SelfCorrectionWorkflow 已初始化")

    def _create_default_workflow_config(self) -> Dict[str, Any]:
        """创建默认工作流配置"""
        return {
            "min_errors_for_correction": 5,
            "max_mutations_per_cycle": 3,
            "cycle_interval_hours": 1,
            "mistake_book_config": {},
            "weight_variator_config": {
                "mutation_rate": 0.9,
                "max_mutation_percent": 0.20,
            },
            "wfa_backtester_config": {
                "train_days": 300,
                "test_days": 100,
                "step_days": 200,
                "min_window_count": 2,
                "max_windows": 5,
                "min_performance_improvement": 0.005,
                "max_weight_change": 2.0,
                "smooth_factor": 0.3,
                "require_statistical_significance": False,
            },
            "initial_config": {
                "period_weight_filter": {
                    "weights": {
                        "D1": 0.25,
                        "H4": 0.30,
                        "H1": 0.25,
                        "M15": 0.12,
                        "M5": 0.08,
                    },
                },
                "threshold_parameters": {
                    "confidence_threshold": 0.40,
                    "volume_threshold": 1.5,
                    "volatility_threshold": 0.02,
                },
            },
            "learning_batch_size": 10,
        }

    def _load_historical_data(self) -> None:
        """加载本地历史数据"""
        data_dir = Path("data")
        if not data_dir.exists():
            logger.warning("data/ 目录不存在，无法加载历史数据")
            return

        col_rename = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }

        csv_map = {
            "D1": "ETHUSDT_1d.csv",
            "H4": "ETHUSDT_4h.csv",
            "H1": "ETHUSDT_1h.csv",
            "M15": "ETHUSDT_15m.csv",
            "M5": "ETHUSDT_5m.csv",
        }

        for tf, filename in csv_map.items():
            filepath = data_dir / filename
            if filepath.exists():
                try:
                    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
                    df = df.rename(columns=col_rename)
                    core_cols = [
                        c
                        for c in ["open", "high", "low", "close", "volume"]
                        if c in df.columns
                    ]
                    df = df[core_cols]
                    self._historical_data[tf] = df
                    logger.info("加载历史数据: %s (%d 条)", tf, len(df))
                except Exception as e:
                    logger.error("加载 %s 失败: %s", filename, e)

        # 设置工作流数据
        if "H4" in self._historical_data:
            h4_data = self._historical_data["H4"].iloc[-2000:]
            self._workflow.set_historical_data(h4_data)

    def on_unload(self) -> None:
        """卸载插件"""
        if self._is_evolving:
            self.stop_evolution()

        if self._archivist is not None:
            try:
                self._archivist.stop()
            except Exception:
                pass

        self._workflow = None
        self._archivist = None
        self._historical_data.clear()

        logger.info("EvolutionPlugin 已卸载")

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        from src.kernel.types import PluginState

        if self._state != PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="插件未激活",
            )

        if self._workflow is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="工作流未初始化",
            )

        details = {
            "is_evolving": self._is_evolving,
            "cycle_count": self._cycle_count,
            "record_count": self._record_count,
            "data_loaded": list(self._historical_data.keys()),
            "last_error": self._last_error,
        }

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近错误: {self._last_error}",
                details=details,
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="进化系统运行正常",
            details=details,
        )

    # === 进化控制 ===

    async def start_evolution(self) -> Dict[str, Any]:
        """启动进化系统

        Returns:
            启动结果
        """
        if self._is_evolving:
            return {"status": "already_running", "cycle_count": self._cycle_count}

        if self._workflow is None:
            return {"status": "error", "message": "工作流未初始化"}

        if not self._historical_data:
            self._load_historical_data()

        if not self._historical_data:
            return {"status": "error", "message": "无历史数据"}

        self._is_evolving = True
        self._start_time = datetime.now()

        # 初始化 WFA 基准
        try:
            self._workflow.initialize_wfa_baseline()
        except Exception as e:
            logger.error("初始化 WFA 基准失败: %s", e)

        # 启动后台进化任务
        self._evolution_task = asyncio.create_task(self._run_evolution_loop())

        self.emit_event(
            "evolution.started",
            {
                "start_time": self._start_time.isoformat(),
                "symbols": self._symbols,
                "timeframes": self._timeframes,
            },
        )

        logger.info("进化系统已启动")
        return {
            "status": "started",
            "start_time": self._start_time.isoformat(),
            "symbols": self._symbols,
        }

    async def stop_evolution(self) -> Dict[str, Any]:
        """停止进化系统

        Returns:
            停止结果
        """
        if not self._is_evolving:
            return {"status": "already_stopped"}

        self._is_evolving = False

        if self._evolution_task is not None:
            self._evolution_task.cancel()
            try:
                await self._evolution_task
            except asyncio.CancelledError:
                pass
            self._evolution_task = None

        self.emit_event(
            "evolution.stopped",
            {
                "cycle_count": self._cycle_count,
                "stop_time": datetime.now().isoformat(),
            },
        )

        logger.info("进化系统已停止，共运行 %d 个周期", self._cycle_count)
        return {
            "status": "stopped",
            "cycle_count": self._cycle_count,
        }

    async def _run_evolution_loop(self) -> None:
        """进化循环主逻辑"""
        logger.info("进化循环开始运行")

        while self._is_evolving:
            try:
                # 运行一个进化周期
                result = await self._run_single_cycle()

                self._cycle_count += 1
                self._last_cycle_result = result

                # 保存结果
                self._save_cycle_result(result)

                # 发布事件
                self.emit_event(
                    "evolution.cycle_completed",
                    {
                        "cycle_count": self._cycle_count,
                        "success": result.get("success", False),
                        "timestamp": datetime.now().isoformat(),
                    },
                )

                # 等待下一个周期
                await asyncio.sleep(self._cycle_interval)

            except asyncio.CancelledError:
                logger.info("进化循环被取消")
                break
            except Exception as e:
                self._last_error = str(e)
                logger.error("进化周期异常: %s", e)
                await asyncio.sleep(60)

        logger.info("进化循环已退出")

    async def _run_single_cycle(self) -> Dict[str, Any]:
        """运行单个进化周期"""
        if self._workflow is None:
            return {"success": False, "error": "工作流未初始化"}

        try:
            # 在线程池中运行同步方法
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._workflow.run_correction_cycle
            )
            return result
        except Exception as e:
            logger.error("运行进化周期失败: %s", e)
            return {"success": False, "error": str(e)}

    def _save_cycle_result(self, result: Dict[str, Any]) -> None:
        """保存进化周期结果"""
        os.makedirs("evolution_results", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"evolution_results/cycle_{self._cycle_count}_{timestamp}.json"

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str, ensure_ascii=False)
            logger.debug("进化结果已保存: %s", filename)
        except Exception as e:
            logger.error("保存进化结果失败: %s", e)

    # === 状态查询 ===

    def get_evolution_status(self) -> Dict[str, Any]:
        """获取进化状态

        Returns:
            进化状态信息
        """
        return {
            "status": "running" if self._is_evolving else "stopped",
            "cycle_count": self._cycle_count,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "symbols": self._symbols,
            "timeframes": self._timeframes,
            "data_loaded": list(self._historical_data.keys()),
            "last_error": self._last_error,
            "workflow_status": self._workflow.get_workflow_status()
            if self._workflow
            else None,
        }

    def get_current_config(self) -> Dict[str, Any]:
        """获取当前进化配置

        Returns:
            当前配置
        """
        if self._workflow is None:
            return {}
        return self._workflow.current_config

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息
        """
        return {
            "is_evolving": self._is_evolving,
            "cycle_count": self._cycle_count,
            "record_count": self._record_count,
            "last_error": self._last_error,
            "data_timeframes": list(self._historical_data.keys()),
        }

    def get_decision_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取决策历史

        Args:
            limit: 返回数量限制

        Returns:
            决策历史列表
        """
        if self._workflow is None:
            return []

        if not hasattr(self._workflow, "correction_history"):
            return []

        if not self._workflow.correction_history:
            return []

        history = []
        for i, result in enumerate(self._workflow.correction_history[-limit:]):
            try:
                entry = result.to_dict() if hasattr(result, "to_dict") else {}
                entry["id"] = str(i)
                history.append(entry)
            except Exception as e:
                logger.warning("处理决策历史条目失败: %s", e)
                continue

        return history

    def get_state_machine_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取状态机转换日志

        Args:
            limit: 返回数量限制

        Returns:
            状态机日志列表
        """
        # TODO: 从实际状态机获取日志
        return []

    # === 档案员接口 ===

    def start_archivist(self) -> None:
        """启动档案员后台线程"""
        if self._archivist is None:
            raise RuntimeError("档案员未初始化")
        self._archivist.start()
        logger.info("进化档案员已启动")

    def stop_archivist(self) -> None:
        """停止档案员后台线程"""
        if self._archivist is not None:
            self._archivist.stop()
            logger.info("进化档案员已停止")

    def record_log(self, log: Any) -> bool:
        """记录进化日志"""
        if self._archivist is None:
            return False
        result = self._archivist.record_log(log)
        if result:
            self._record_count += 1
        return result

    def query_history(self, question: str, limit: int = 5) -> List:
        """查询历史记忆"""
        if self._archivist is None:
            return []
        return self._archivist.query_history(question, limit)

    # === 进化盘持仓管理 ===

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取进化盘持仓

        Returns:
            持仓列表
        """
        if self._storage is None:
            return []
        positions = self._storage.get_positions()
        return [p.to_dict() for p in positions]

    def get_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        """获取单个进化盘持仓

        Args:
            position_id: 持仓ID

        Returns:
            持仓数据，如果不存在则返回 None
        """
        if self._storage is None:
            return None
        position = self._storage.get_position(position_id)
        return position.to_dict() if position else None

    def add_position(self, position_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加进化盘持仓

        Args:
            position_data: 持仓数据

        Returns:
            创建的持仓数据
        """
        if self._storage is None:
            return {}
        position_data["evolution_cycle"] = self._cycle_count
        position = self._storage.add_position(position_data)
        return position.to_dict()

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: str = "manual",
    ) -> Optional[Dict[str, Any]]:
        """平仓进化盘持仓

        Args:
            position_id: 持仓ID
            exit_price: 平仓价格
            exit_reason: 平仓原因

        Returns:
            交易记录，如果持仓不存在则返回 None
        """
        if self._storage is None:
            return None
        trade = self._storage.close_position(
            position_id=position_id,
            exit_price=exit_price,
            exit_reason=exit_reason,
            evolution_cycle=self._cycle_count,
        )
        return trade.to_dict() if trade else None

    def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取进化盘交易历史

        Args:
            limit: 返回数量限制

        Returns:
            交易历史列表
        """
        if self._storage is None:
            return []
        trades = self._storage.get_trades(limit)
        return [t.to_dict() for t in trades]

    def get_evolution_statistics(self) -> Dict[str, Any]:
        """获取进化盘统计信息

        Returns:
            统计信息
        """
        if self._storage is None:
            return {}
        return self._storage.get_statistics()

    def clear_evolution_data(self) -> None:
        """清空进化盘数据"""
        if self._storage is not None:
            self._storage.clear_all()
            logger.info("已清空进化盘数据")
