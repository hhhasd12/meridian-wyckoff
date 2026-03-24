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
5. WFA+AOF 都通过则采纳，否则保持当前配置
6. 结果持久化到 data/evolution_results.json
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
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

        # 进化组件（on_load 时初始化）
        self._ga: Any = None
        self._evaluator: Any = None
        self._wfa: Any = None
        self._anti_overfit: Any = None
        self._mistake_book: Any = None
        self._current_config: Dict[str, Any] = {}
        self._data_dict: Dict[str, pd.DataFrame] = {}
        self._evolution_task: Optional[asyncio.Task[None]] = None
        self._max_cycles: int = 10
        self._eval_progress: Dict[
            str, Any
        ] = {}  # 评估实时进度（progress_callback 更新）

    def _on_eval_progress(self, progress: Dict[str, Any]) -> None:
        """GA 评估进度回调 — 每完成一个个体更新一次"""
        self._eval_progress = {
            "eval_completed": progress.get("completed", 0),
            "eval_total": progress.get("total", 0),
            "eval_generation": progress.get("generation", 0),
            "eval_elapsed": progress.get("elapsed", 0.0),
            "eval_eta": progress.get("eta", 0.0),
            "eval_workers": progress.get("workers", 1),
        }

    async def activate(self, context: dict[str, Any]) -> None:
        """激活插件 — 向后兼容（实际初始化已在 on_load 中完成）"""
        # 如果 on_load 已初始化，跳过
        if self._ga is not None:
            return
        # 回退：从 context 取配置初始化
        config = context.get("config", {}).get("evolution", {})
        self._init_evolution_components(config)

    async def deactivate(self) -> None:
        """停用插件"""
        self.is_running = False
        self._is_evolving = False
        logger.info("EvolutionPlugin deactivated")

    def on_load(self) -> None:
        """加载插件 — 初始化 GA + WFA + AntiOverfit 组件"""
        config = self._config or {}
        self._init_evolution_components(config)

    def _init_evolution_components(self, config: Dict[str, Any]) -> None:
        """初始化进化组件（GA/Evaluator/WFA/AntiOverfit）

        Args:
            config: 进化配置字典
        """
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
            ann_weight = config.get("annotation_fitness_weight", 0.0)
            self._evaluator = StandardEvaluator(
                mistake_book=self._mistake_book,
                annotation_weight=ann_weight,
            )
            self._anti_overfit = AntiOverfitGuard()

            ga_cfg = GAConfig(
                population_size=config.get("population_size", 20),
                max_generations=config.get("max_generations", 50),
            )
            self._ga = GeneticAlgorithm(self._current_config, ga_cfg)
            self._wfa = WFAValidator(evaluator_fn=self._evaluator)

            logger.info("EvolutionPlugin 组件初始化完成 (GA+WFA+AntiOverfit)")
        except Exception as e:
            logger.warning("EvolutionPlugin 组件初始化部分失败: %s", e)
            self._last_error = str(e)

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
        """获取进化状态（含实时评估进度，供 WebSocket 推送前端）"""
        status: dict[str, Any] = {
            "status": "running" if self._is_evolving else "stopped",
            "is_running": self._is_evolving,
            "cycle_count": self._cycle_count,
            "max_cycles": self._max_cycles,
        }

        # GA 实时进度
        if self._ga is not None:
            stats = self._ga.get_population_stats()
            status["generation"] = stats.get("generation", 0)
            status["best_fitness"] = stats.get("best_fitness", 0.0)
            status["avg_fitness"] = stats.get("avg_fitness", 0.0)
            status["population_size"] = stats.get("size", 0)

        # 评估进度（由 progress_callback 更新）
        status.update(self._eval_progress)

        return status

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

    async def start_evolution(
        self, max_cycles: int = 10, resume: bool = True
    ) -> dict[str, str]:
        """启动进化 — 创建 asyncio.Task 执行实际进化循环

        Args:
            max_cycles: 最大进化 cycle 数
            resume: 是否尝试从 checkpoint 恢复（默认 True）
        """
        if self._ga is None and self._evaluator is None:
            return {"status": "error", "message": "工作流未初始化"}
        if self._is_evolving:
            return {"status": "error", "message": "进化已在运行中"}

        self._is_evolving = True
        self._max_cycles = max_cycles

        # 尝试从 checkpoint 恢复
        resumed = False
        if resume and self._load_checkpoint():
            resumed = True
            # 恢复 evaluator/wfa/anti_overfit（无状态组件从 config 重建）
            self._reinit_stateless_components()

        self._evolution_task = asyncio.create_task(
            self._run_evolution_cycle(resumed=resumed)
        )
        status_msg = (
            f"resumed from cycle {self._cycle_count}" if resumed else str(max_cycles)
        )
        return {
            "status": "resumed" if resumed else "started",
            "max_cycles": str(max_cycles),
            "message": status_msg,
        }

    def _reinit_stateless_components(self) -> None:
        """重建无状态组件（evaluator/wfa/anti_overfit）— checkpoint 恢复后调用"""
        try:
            from src.plugins.evolution.anti_overfit import AntiOverfitGuard
            from src.plugins.evolution.evaluator import StandardEvaluator
            from src.plugins.evolution.wfa_validator import WFAValidator
            from src.plugins.self_correction.mistake_book import MistakeBook

            config = self._config or {}
            self._mistake_book = MistakeBook(config.get("mistake_book_config", {}))
            ann_weight = config.get("annotation_fitness_weight", 0.0)
            self._evaluator = StandardEvaluator(
                mistake_book=self._mistake_book,
                annotation_weight=ann_weight,
            )
            self._anti_overfit = AntiOverfitGuard()
            self._wfa = WFAValidator(evaluator_fn=self._evaluator)
        except Exception as e:
            logger.warning("重建无状态组件失败: %s", e)

    async def stop_evolution(self) -> dict[str, str]:
        """停止进化 — 自动保存 checkpoint 以支持断点续传"""
        if not self._is_evolving:
            return {"status": "already_stopped"}
        self._is_evolving = False

        # 先保存 checkpoint，再取消任务
        self._save_checkpoint()

        if self._evolution_task is not None and not self._evolution_task.done():
            self._evolution_task.cancel()
            self._evolution_task = None
        return {
            "status": "stopped",
            "message": f"已保存 checkpoint (cycle={self._cycle_count}), 下次启动可恢复",
        }

    # ================================================================
    # 进化核心循环
    # ================================================================

    async def _run_evolution_cycle(self, resumed: bool = False) -> None:
        """实际执行进化循环 — 由 asyncio.Task 驱动

        Args:
            resumed: 是否从 checkpoint 恢复（True 则跳过初始化和首次评估）

        修复清单：
        - 消除双重 evaluate_population（每cycle只评估一次新种群）
        - AntiOverfit 结果纳入配置采纳决策
        - 每个 cycle 结果持久化到 data/evolution_results.json
        - evaluate_population 后更新 best_individual
        - 支持 checkpoint 断点续传
        """
        try:
            if self._ga is None or self._evaluator is None:
                self._last_error = "GA/Evaluator 未初始化"
                self._is_evolving = False
                return

            if not self._data_dict:
                self._last_error = "数据未设置，请先调用 set_data()"
                self._is_evolving = False
                return

            # 分割数据：GA用前70%，WFA用后30%（根因1修复）
            h4 = self._data_dict.get("H4")
            if h4 is None or len(h4) < 100:
                self._last_error = "H4数据不足"
                self._is_evolving = False
                return

            h4_len = len(h4)
            split_idx = int(h4_len * 0.7)
            h4_split_time = h4.index[split_idx]

            # GA 训练数据：使用全量历史，确保覆盖完整威科夫周期（吸筹→上涨→派发→下跌）
            # 截断的数据容易导致进化过拟合到单边行情
            ga_train_data: Dict[str, pd.DataFrame] = {}
            wfa_holdout_data: Dict[str, pd.DataFrame] = {}

            for tf_key, tf_df in self._data_dict.items():
                if not isinstance(tf_df, pd.DataFrame):
                    continue
                train_slice = tf_df.loc[tf_df.index < h4_split_time]
                wfa_holdout_data[tf_key] = tf_df.loc[tf_df.index >= h4_split_time]
                ga_train_data[tf_key] = train_slice

            ga_h4_len = len(ga_train_data.get("H4", pd.DataFrame()))
            wfa_h4_len = len(wfa_holdout_data.get("H4", pd.DataFrame()))
            total_bars = sum(
                len(v) for v in ga_train_data.values() if isinstance(v, pd.DataFrame)
            )
            logger.info(
                "进化数据分割: GA训练 H4=%d bars (总%d bars), WFA验证 H4=%d bars",
                ga_h4_len,
                total_bars,
                wfa_h4_len,
            )

            # 初始化种群（恢复模式跳过）
            if resumed:
                logger.info(
                    "从 checkpoint 恢复，跳过种群初始化 (population=%d, generation=%d)",
                    len(self._ga.population),
                    self._ga.generation,
                )
            else:
                self._ga.initialize_population()

                # 第一次评估初始种群（仅在 cycle 0）
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self._ga.evaluate_population(
                        self._evaluator,
                        ga_train_data,
                        progress_callback=self._on_eval_progress,
                    ),
                )

            loop = asyncio.get_event_loop()

            for cycle in range(self._max_cycles):
                if not self._is_evolving:
                    logger.info("进化被外部停止，cycle=%d", cycle)
                    break

                self._cycle_count += 1

                try:
                    # 进化产生新种群（精英保留旧fitness，新个体fitness=0）
                    await loop.run_in_executor(None, self._ga.evolve_generation)
                    # 评估新种群
                    await loop.run_in_executor(
                        None,
                        lambda: self._ga.evaluate_population(
                            self._evaluator,
                            ga_train_data,
                            progress_callback=self._on_eval_progress,
                        ),
                    )

                    best = self._ga.get_best()
                    if best is None:
                        logger.warning("Cycle #%d: 无最佳个体", self._cycle_count)
                        continue

                    stats = self._ga.get_population_stats()

                    # WFA验证（使用独立holdout数据）
                    wfa_report = await loop.run_in_executor(
                        None,
                        lambda: self._wfa.validate(best.config, wfa_holdout_data),
                    )

                    # AntiOverfit 检查
                    aof_passed = None
                    if (
                        best.backtest_result is not None
                        and self._anti_overfit is not None
                    ):
                        verdict = self._anti_overfit.check(
                            best.backtest_result,
                            train_sharpes=(
                                wfa_report.train_sharpes
                                if wfa_report.train_sharpes
                                else None
                            ),
                            test_sharpes=(
                                wfa_report.test_sharpes
                                if wfa_report.test_sharpes
                                else None
                            ),
                            n_trials=self._cycle_count,
                        )
                        aof_passed = verdict.passed

                    # 判定是否采纳（WFA+AOF 都通过 或 AOF 未执行但 WFA 通过）
                    adopted = wfa_report.passed and (
                        aof_passed is True or aof_passed is None
                    )

                    # 构建 cycle 结果
                    cycle_result = {
                        "cycle": self._cycle_count,
                        "generation": self._ga.generation,
                        "best_fitness": best.fitness,
                        "avg_fitness": stats.get("avg_fitness", 0.0),
                        "wfa_passed": wfa_report.passed,
                        "oos_dr": wfa_report.oos_degradation_ratio,
                        "aof_passed": aof_passed,
                        "adopted": adopted,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                    # 通过事件总线发布进度
                    self.emit_event("evolution.cycle_complete", cycle_result)

                    logger.info(
                        "Cycle #%d Gen=%d | best=%.4f avg=%.4f | "
                        "WFA=%s OOS-DR=%.2f AOF=%s → %s",
                        self._cycle_count,
                        self._ga.generation,
                        best.fitness,
                        stats.get("avg_fitness", 0.0),
                        "PASS" if wfa_report.passed else "FAIL",
                        wfa_report.oos_degradation_ratio,
                        "PASS"
                        if aof_passed
                        else ("FAIL" if aof_passed is not None else "N/A"),
                        "ADOPTED" if adopted else "REJECTED",
                    )

                    # 如果通过，更新当前配置
                    if adopted:
                        self._current_config = best.config

                    # 持久化结果
                    self._save_cycle_result(cycle_result, best.config)

                    # 每 cycle 保存 checkpoint（断点续传）
                    self._save_checkpoint()

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        "Cycle #%d 异常: %s",
                        self._cycle_count,
                        e,
                        exc_info=True,
                    )
                    self._last_error = str(e)

                # 让出控制权
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            logger.info("进化任务被取消（checkpoint 已保存）")
        except Exception as e:
            logger.error("进化循环异常终止: %s", e, exc_info=True)
            self._last_error = str(e)
            # 异常终止也保存 checkpoint
            self._save_checkpoint()
        finally:
            self._is_evolving = False
            # 正常跑完全部 cycles 才清理 checkpoint
            if self._cycle_count >= self._max_cycles:
                self._clear_checkpoint()
            self.emit_event(
                "evolution.completed",
                {"total_cycles": self._cycle_count},
            )
            logger.info("进化循环结束，共 %d 个cycle", self._cycle_count)

    # ================================================================
    # 结果持久化
    # ================================================================

    _RESULTS_PATH = os.path.join("data", "evolution_results.json")
    _CHECKPOINT_PATH = os.path.join("data", "evolution_checkpoint.json")

    def _save_checkpoint(self) -> None:
        """保存进化断点 — 每 cycle 结束后调用，支持中断恢复

        保存内容：GA 状态 + 插件级元数据（cycle_count, max_cycles, current_config）
        """
        if self._ga is None:
            return

        try:
            os.makedirs(os.path.dirname(self._CHECKPOINT_PATH), exist_ok=True)

            checkpoint = {
                "ga_state": self._ga.to_checkpoint(),
                "cycle_count": self._cycle_count,
                "max_cycles": self._max_cycles,
                "current_config": self._current_config,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # 先写临时文件再 rename，防止写一半断电导致损坏
            tmp_path = self._CHECKPOINT_PATH + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, indent=2, default=str)
            # Windows 上 rename 目标已存在会报错，先删再改名
            if os.path.exists(self._CHECKPOINT_PATH):
                os.remove(self._CHECKPOINT_PATH)
            os.rename(tmp_path, self._CHECKPOINT_PATH)

            logger.info(
                "Checkpoint 已保存: cycle=%d, generation=%d",
                self._cycle_count,
                self._ga.generation,
            )
        except Exception as e:
            logger.warning("保存 checkpoint 失败: %s", e)

    def _load_checkpoint(self) -> bool:
        """尝试加载断点 — start_evolution() 时调用

        Returns:
            True 表示成功恢复，False 表示无可用断点
        """
        if not os.path.exists(self._CHECKPOINT_PATH):
            return False

        try:
            with open(self._CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)

            from src.plugins.evolution.genetic_algorithm import GeneticAlgorithm

            self._ga = GeneticAlgorithm.from_checkpoint(checkpoint["ga_state"])
            self._cycle_count = checkpoint["cycle_count"]
            self._current_config = checkpoint.get("current_config", {})

            logger.info(
                "从 checkpoint 恢复: cycle=%d, generation=%d, timestamp=%s",
                self._cycle_count,
                self._ga.generation,
                checkpoint.get("timestamp", "unknown"),
            )
            return True
        except Exception as e:
            logger.warning("加载 checkpoint 失败，将从头开始: %s", e)
            return False

    def _clear_checkpoint(self) -> None:
        """清理 checkpoint 文件 — 进化正常完成后调用"""
        try:
            if os.path.exists(self._CHECKPOINT_PATH):
                os.remove(self._CHECKPOINT_PATH)
                logger.info("Checkpoint 已清理（进化正常完成）")
        except Exception as e:
            logger.warning("清理 checkpoint 失败: %s", e)

    def _save_cycle_result(
        self,
        cycle_result: Dict[str, Any],
        best_config: Dict[str, Any],
    ) -> None:
        """将 cycle 结果追加到 data/evolution_results.json

        包含回测详情（trades + equity_curve + bar_phases），支持前端回测可视化。
        文件格式与 API 端 GET /api/evolution/results 对齐。
        """
        try:
            os.makedirs(os.path.dirname(self._RESULTS_PATH), exist_ok=True)

            # 读取已有结果
            existing: List[Dict[str, Any]] = []
            if os.path.exists(self._RESULTS_PATH):
                with open(self._RESULTS_PATH, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        existing = json.loads(content)

            # 序列化 best individual 的回测详情
            backtest_detail = self._serialize_backtest_detail()

            # 追加当前 cycle
            entry = {
                **cycle_result,
                "best_config": best_config,
                "backtest_detail": backtest_detail,
            }
            existing.append(entry)

            # 只保留最近 200 条
            if len(existing) > 200:
                existing = existing[-200:]

            with open(self._RESULTS_PATH, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, default=str)

        except Exception as e:
            logger.warning("保存进化结果失败: %s", e)

    def _serialize_backtest_detail(self) -> Optional[Dict[str, Any]]:
        """序列化 best individual 的 BacktestResult 为可 JSON 持久化的格式"""
        if self._ga is None:
            return None
        best = self._ga.get_best()
        if best is None or best.backtest_result is None:
            return None

        br = best.backtest_result
        return {
            "trades": [
                {
                    "entry_bar": t.entry_bar,
                    "exit_bar": t.exit_bar,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "side": t.side,
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 4),
                    "exit_reason": t.exit_reason,
                    "hold_bars": t.hold_bars,
                    "entry_state": t.entry_state,
                }
                for t in br.trades
            ],
            "total_return": round(br.total_return, 4),
            "sharpe_ratio": round(br.sharpe_ratio, 4),
            "max_drawdown": round(br.max_drawdown, 4),
            "win_rate": round(br.win_rate, 4),
            "profit_factor": round(br.profit_factor, 4),
            "total_trades": br.total_trades,
            # equity_curve 降采样（每10个点取1个），避免JSON文件过大
            "equity_curve": (
                br.equity_curve[::10] if len(br.equity_curve) > 200 else br.equity_curve
            ),
            "equity_curve_full_length": len(br.equity_curve),
            # bar_phases/bar_states 用 RLE 压缩（连续相同值合并）
            "bar_phases_rle": self._rle_encode(br.bar_phases),
            "bar_states_rle": self._rle_encode(br.bar_states),
            # 逐bar状态机完整快照 — 状态机可视化用
            "bar_details": self._serialize_bar_details(br.bar_details),
        }

    @staticmethod
    def _rle_encode(values: List[str]) -> List[Dict[str, Any]]:
        """Run-Length Encoding 压缩连续相同值

        例: ["A","A","A","B","B","C"] → [{"v":"A","n":3},{"v":"B","n":2},{"v":"C","n":1}]
        """
        if not values:
            return []
        result: List[Dict[str, Any]] = []
        current = values[0]
        count = 1
        for v in values[1:]:
            if v == current:
                count += 1
            else:
                result.append({"v": current, "n": count})
                current = v
                count = 1
        result.append({"v": current, "n": count})
        return result

    @staticmethod
    def _serialize_bar_details(
        bar_details: List[Any],
    ) -> List[Dict[str, Any]]:
        """序列化逐bar状态机快照

        对数值字段保留2位小数，critical_levels 只在变化时输出完整值，
        否则输出空字典以节省存储。
        """
        if not bar_details:
            return []

        result: List[Dict[str, Any]] = []
        prev_levels: Dict[str, float] = {}

        for d in bar_details:
            cur_levels = d.critical_levels if d.critical_levels else {}
            # 只在 critical_levels 变化时输出
            levels_out = (
                {k: round(v, 2) for k, v in cur_levels.items()}
                if cur_levels != prev_levels
                else {}
            )
            prev_levels = cur_levels

            result.append(
                {
                    "p": d.phase,  # phase
                    "s": d.state,  # state
                    "c": round(d.confidence, 3),  # confidence
                    "ts": round(d.tr_support, 2) if d.tr_support is not None else None,
                    "tr": round(d.tr_resistance, 2)
                    if d.tr_resistance is not None
                    else None,
                    "tc": round(d.tr_confidence, 3)
                    if d.tr_confidence is not None
                    else None,
                    "mr": d.market_regime,  # market_regime
                    "d": d.direction,  # direction
                    "ss": d.signal_strength,  # signal_strength
                    "sc": d.state_changed,  # state_changed
                    "cl": levels_out,  # critical_levels (delta)
                }
            )

        return result

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
