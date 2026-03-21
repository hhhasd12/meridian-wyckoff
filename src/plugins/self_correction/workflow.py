"""
自我修正闭环工作流模块
实现错题本 → GA进化 → WFA验证 → 配置更新的完整闭环

设计原则：
1. 数据驱动：基于错题本错误模式进行针对性修正
2. 遗传进化：使用 GeneticAlgorithm 替代旧 WeightVariator 的随机变异
3. 防过拟合：WFAValidator 滚动窗口验证确保泛化能力
4. 标准评估：StandardEvaluator 统一回测评估接口
5. 闭环反馈：修正结果反馈到系统，形成持续优化循环
6. 可追溯性：记录每次修正的完整决策过程

工作流步骤：
1. 错题本分析：收集错误模式，识别系统弱点
2. GA进化：基于错题本驱动遗传算法进化配置
3. WFA验证：使用 WFAValidator 滚动窗口验证候选配置
4. 配置更新：选择最佳配置，平滑过渡到新参数
5. 效果评估：监控修正后的系统表现
"""

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd

# 导入核心模块
try:
    from .mistake_book import ErrorPattern, ErrorSeverity, MistakeBook, MistakeType
except ImportError:
    ErrorPattern = None
    ErrorSeverity = None
    MistakeBook = None
    MistakeType = None

try:
    from src.plugins.evolution.genetic_algorithm import (
        GAConfig,
        GeneticAlgorithm,
    )
except ImportError:
    GAConfig = None
    GeneticAlgorithm = None

try:
    from src.plugins.evolution.wfa_validator import (
        WFAConfig,
        WFAReport,
        WFAValidator,
    )
except ImportError:
    WFAConfig = None
    WFAReport = None
    WFAValidator = None

try:
    from src.plugins.evolution.evaluator import StandardEvaluator
except ImportError:
    StandardEvaluator = None

logger = logging.getLogger(__name__)


class CorrectionStage(Enum):
    """修正阶段枚举"""

    ERROR_ANALYSIS = "ERROR_ANALYSIS"  # 错误分析阶段
    MUTATION_GENERATION = "MUTATION_GENERATION"  # 变异生成阶段
    WFA_VALIDATION = "WFA_VALIDATION"  # WFA验证阶段
    CONFIG_UPDATE = "CONFIG_UPDATE"  # 配置更新阶段
    EVALUATION = "EVALUATION"  # 效果评估阶段


@dataclass
class CorrectionResult:
    """修正结果数据类"""

    stage: CorrectionStage
    timestamp: datetime
    success: bool
    details: dict[str, Any]
    metrics: dict[str, float] = field(default_factory=dict)
    error_message: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "stage": self.stage.value,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "details": self.details,
            "metrics": self.metrics,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
        }


class SelfCorrectionWorkflow:
    """
    自我修正闭环工作流管理器

    功能：
    1. 管理完整的自我修正流程
    2. 协调错题本、GeneticAlgorithm、WFAValidator、StandardEvaluator
    3. 记录修正历史和决策过程
    4. 提供修正效果评估
    """

    def __init__(
        self,
        config: dict[str, Any],
        mistake_book: Optional["MistakeBook"] = None,
        genetic_algorithm: Optional["GeneticAlgorithm"] = None,
        wfa_validator: Optional["WFAValidator"] = None,
        evaluator: Optional["StandardEvaluator"] = None,
    ):
        """
        初始化自我修正工作流

        Args:
            config: 工作流配置
            mistake_book: 错题本实例
            genetic_algorithm: 遗传算法实例（替代旧 WeightVariator）
            wfa_validator: WFA滚动窗口验证器（替代旧 WFABacktester）
            evaluator: 标准评估器实例
        """
        self.config = config

        # 初始化组件
        self.mistake_book = mistake_book or (
            MistakeBook(config.get("mistake_book_config", {}))
            if MistakeBook is not None
            else None
        )

        # GA 配置
        initial_config = config.get("initial_config", {})
        ga_cfg_dict = config.get("ga_config", {})
        ga_cfg = (
            GAConfig(**ga_cfg_dict) if GAConfig is not None and ga_cfg_dict else None
        )
        self.genetic_algorithm = genetic_algorithm or (
            GeneticAlgorithm(baseline_config=initial_config, config=ga_cfg)
            if GeneticAlgorithm is not None
            else None
        )

        # WFA 验证器配置
        wfa_cfg_dict = config.get("wfa_config", {})
        wfa_cfg = (
            WFAConfig(**wfa_cfg_dict)
            if WFAConfig is not None and wfa_cfg_dict
            else None
        )
        self.wfa_validator = wfa_validator or (
            WFAValidator(config=wfa_cfg) if WFAValidator is not None else None
        )

        # 标准评估器
        eval_cfg = config.get("evaluator_config", {})
        self.evaluator = evaluator or (
            StandardEvaluator(
                mistake_book=self.mistake_book,
                **eval_cfg,
            )
            if StandardEvaluator is not None
            else None
        )

        # 将评估器连接到 WFA 验证器
        if self.wfa_validator is not None and self.evaluator is not None:
            self.wfa_validator.set_evaluator(self.evaluator)

        # 工作流状态
        self.current_stage = CorrectionStage.ERROR_ANALYSIS
        self.is_running = False
        self.current_config: dict[str, Any] = copy.deepcopy(initial_config)
        self.baseline_config: dict[str, Any] = copy.deepcopy(initial_config)

        # 历史记录
        self.correction_history: list[CorrectionResult] = []
        self.performance_history: list[dict[str, Any]] = []

        # 历史数据（多TF字典）
        self.historical_data: Optional[Dict[str, pd.DataFrame]] = None

        # 配置参数
        self.min_errors_for_correction = config.get("min_errors_for_correction", 10)
        self.ga_generations = config.get("ga_generations", 10)
        self.cycle_interval_hours = config.get("cycle_interval_hours", 24)
        self.last_correction_time: Optional[datetime] = None

        logger.info("自我修正闭环工作流初始化完成（GA+WFA+Evaluator）")

    def set_historical_data(
        self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]
    ) -> None:
        """设置历史数据（支持单个DataFrame或多周期字典）"""
        if isinstance(data, pd.DataFrame):
            # 向后兼容：单个DataFrame视为H4
            self.historical_data = {"H4": data}
        else:
            self.historical_data = data

    def run_correction_cycle(self) -> dict[str, Any]:
        """
        运行一个完整的修正周期

        Returns:
            修正周期结果摘要
        """
        start_time = datetime.now()
        self.is_running = True
        cycle_results = {}

        try:
            # 1. 错误分析阶段
            error_analysis_result = self._run_error_analysis()
            self.correction_history.append(error_analysis_result)
            cycle_results["error_analysis"] = error_analysis_result.to_dict()

            if not error_analysis_result.success:
                logger.warning("错误分析阶段失败，终止修正周期")
                return self._create_cycle_summary(start_time, False, cycle_results)

            # 2. 变异生成阶段
            mutation_result = self._generate_mutations(error_analysis_result.details)
            self.correction_history.append(mutation_result)
            cycle_results["mutation_generation"] = mutation_result.to_dict()

            if not mutation_result.success:
                logger.warning("变异生成阶段失败，终止修正周期")
                return self._create_cycle_summary(start_time, False, cycle_results)

            # 3. WFA验证阶段
            validation_result = self._validate_mutations(mutation_result.details)
            self.correction_history.append(validation_result)
            cycle_results["wfa_validation"] = validation_result.to_dict()

            if not validation_result.success:
                logger.warning("WFA验证阶段失败，终止修正周期")
                return self._create_cycle_summary(start_time, False, cycle_results)

            # 4. 配置更新阶段
            update_result = self._update_configuration(validation_result.details)
            self.correction_history.append(update_result)
            cycle_results["config_update"] = update_result.to_dict()

            if not update_result.success:
                logger.warning("配置更新阶段失败")
                return self._create_cycle_summary(start_time, False, cycle_results)

            # 5. 效果评估阶段
            evaluation_result = self._evaluate_correction()
            self.correction_history.append(evaluation_result)
            cycle_results["evaluation"] = evaluation_result.to_dict()

            # 更新最后修正时间
            self.last_correction_time = datetime.now()

            return self._create_cycle_summary(start_time, True, cycle_results)

        except Exception as e:
            logger.exception("修正周期执行异常")
            error_result = CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=False,
                details={"error": str(e)},
                error_message=str(e),
            )
            self.correction_history.append(error_result)
            return self._create_cycle_summary(start_time, False, {"error": str(e)})

        finally:
            self.is_running = False

    def _run_error_analysis(self) -> CorrectionResult:
        """执行错误分析"""
        start_time = datetime.now()
        self.current_stage = CorrectionStage.ERROR_ANALYSIS

        try:
            stats = self.mistake_book.get_statistics()
            total_errors = stats.get("total_errors", 0)

            if total_errors < self.min_errors_for_correction:
                logger.info(
                    f"错误数量不足 ({total_errors} < {self.min_errors_for_correction})，将使用随机变异模式"
                )
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=True,
                    details={
                        "total_errors": total_errors,
                        "min_required": self.min_errors_for_correction,
                        "weight_adjustments": [],
                        "pattern_analysis": {"patterns": []},
                        "learning_batch_size": 0,
                        "error_distribution": {
                            "by_type": {},
                            "by_severity": {},
                            "by_module": {},
                        },
                        "mode": "random_mutation",
                    },
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # 分析错误模式
            pattern_analysis = self.mistake_book.analyze_patterns(force_recompute=True)

            # 生成权重调整建议
            weight_adjustments = self.mistake_book.generate_weight_adjustments()

            # 获取学习批次（高优先级错误）
            learning_batch = self.mistake_book.get_learning_batch(
                batch_size=self.config.get("learning_batch_size", 20)
            )

            result_details = {
                "total_errors": total_errors,
                "pattern_analysis": pattern_analysis,
                "weight_adjustments": weight_adjustments,
                "learning_batch_size": len(learning_batch),
                "error_distribution": {
                    "by_type": stats.get("errors_by_type", {}),
                    "by_severity": stats.get("errors_by_severity", {}),
                    "by_module": stats.get("errors_by_module", {}),
                },
            }

            # 计算分析质量指标
            metrics = {
                "error_coverage": min(total_errors / 100, 1.0),  # 错误覆盖度
                "pattern_clarity": len(pattern_analysis.get("patterns", [])) / 10,
                "adjustment_quality": len(weight_adjustments) / 5,
            }

            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=True,
                details=result_details,
                metrics=metrics,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            logger.exception("错误分析失败")
            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=False,
                details={"error": str(e)},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _generate_mutations(self, analysis_details: dict[str, Any]) -> CorrectionResult:
        """使用 GeneticAlgorithm 生成进化配置"""
        start_time = datetime.now()
        self.current_stage = CorrectionStage.MUTATION_GENERATION

        try:
            if self.genetic_algorithm is None:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=False,
                    details={"reason": "GeneticAlgorithm 不可用"},
                    error_message="遗传算法未初始化",
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            if self.evaluator is None or self.historical_data is None:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=False,
                    details={"reason": "Evaluator或历史数据不可用"},
                    error_message="缺少评估器或历史数据",
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # 更新 GA 的 baseline 为当前配置
            self.genetic_algorithm.baseline = copy.deepcopy(self.current_config)

            # 初始化种群
            self.genetic_algorithm.initialize_population()

            # 运行有限代数的 GA 进化（不运行完整 ga.run，手动控制代数）
            for gen in range(self.ga_generations):
                self.genetic_algorithm.evaluate_population(
                    self.evaluator, self.historical_data
                )
                self.genetic_algorithm.evolve_generation()

            # 最后一次评估
            self.genetic_algorithm.evaluate_population(
                self.evaluator, self.historical_data
            )

            # 收集种群中的候选配置（排除 baseline 本身）
            population = self.genetic_algorithm.population
            baseline_hash = self.genetic_algorithm._hash_config(self.current_config)
            candidate_configs: List[Dict[str, Any]] = []
            mutation_details: List[Dict[str, Any]] = []

            sorted_pop = sorted(population, key=lambda x: x.fitness, reverse=True)
            for ind in sorted_pop:
                if ind.config_hash == baseline_hash:
                    continue
                candidate_configs.append(ind.config)
                mutation_details.append(
                    {
                        "fitness": ind.fitness,
                        "generation": ind.generation,
                        "config_summary": self._summarize_config(ind.config),
                        "_config_full": ind.config,
                    }
                )
                if len(candidate_configs) >= 10:
                    break

            if not candidate_configs:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=False,
                    details={"reason": "GA未能生成优于baseline的配置"},
                    error_message="遗传算法未产生有效候选",
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            ga_stats = self.genetic_algorithm.get_population_stats()
            result_details = {
                "total_mutations": len(candidate_configs),
                "mutation_details": mutation_details,
                "ga_generations": self.ga_generations,
                "ga_stats": ga_stats,
                "source_patterns": analysis_details.get("pattern_analysis", {}).get(
                    "patterns", []
                ),
            }

            metrics = {
                "best_fitness": ga_stats.get("best_fitness", 0.0),
                "avg_fitness": ga_stats.get("avg_fitness", 0.0),
                "population_size": float(ga_stats.get("size", 0)),
            }

            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=True,
                details=result_details,
                metrics=metrics,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            logger.exception("GA进化生成失败")
            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=False,
                details={"error": str(e)},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _validate_mutations(self, mutation_details: dict[str, Any]) -> CorrectionResult:
        """使用 WFAValidator 验证 GA 产生的候选配置"""
        start_time = datetime.now()
        self.current_stage = CorrectionStage.WFA_VALIDATION

        try:
            if self.wfa_validator is None:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=False,
                    details={"reason": "WFAValidator 不可用"},
                    error_message="WFA验证器未初始化",
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            if self.historical_data is None:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=False,
                    details={"reason": "历史数据不可用"},
                    error_message="缺少历史数据",
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # 从 mutation_details 中取出候选配置
            candidate_configs: List[Dict[str, Any]] = []
            for detail in mutation_details.get("mutation_details", []):
                cfg = detail.get("_config_full")
                if cfg is not None:
                    candidate_configs.append(cfg)

            if not candidate_configs:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=True,
                    details={
                        "total_validated": 0,
                        "has_best_config": False,
                        "reason": "无候选配置需要验证",
                    },
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # 先对 baseline 进行 WFA 验证，获取基准 Sharpe
            baseline_report = self.wfa_validator.validate(
                self.current_config, self.historical_data
            )
            baseline_sharpe = baseline_report.avg_test_sharpe

            # 对每个候选配置执行 WFA 验证
            reports = self.wfa_validator.validate_population(
                candidate_configs, self.historical_data
            )

            # 筛选通过 WFA 且优于 baseline 的配置
            best_config: Optional[Dict[str, Any]] = None
            best_score = baseline_sharpe
            accepted_count = 0
            rejected_count = 0
            validation_details: List[Dict[str, Any]] = []

            for i, (cfg, report) in enumerate(zip(candidate_configs, reports)):
                detail = {
                    "index": i,
                    "passed": report.passed,
                    "avg_test_sharpe": report.avg_test_sharpe,
                    "oos_degradation": report.oos_degradation_ratio,
                    "avg_test_trades": report.avg_test_trades,
                }
                validation_details.append(detail)

                if report.passed and report.avg_test_sharpe > best_score:
                    best_score = report.avg_test_sharpe
                    best_config = cfg
                    accepted_count += 1
                else:
                    rejected_count += 1

            improvement = best_score - baseline_sharpe

            result_details: Dict[str, Any] = {
                "total_validated": len(candidate_configs),
                "accepted": accepted_count,
                "rejected": rejected_count,
                "baseline_sharpe": baseline_sharpe,
                "best_config_score": best_score,
                "improvement": improvement,
                "has_best_config": best_config is not None,
                "validation_details": validation_details,
            }

            if best_config is not None:
                result_details["best_config"] = self._summarize_config(best_config)
                result_details["_best_config_full"] = best_config

            metrics = {
                "acceptance_rate": (
                    accepted_count / len(candidate_configs)
                    if candidate_configs
                    else 0.0
                ),
                "improvement": improvement,
                "validation_quality": min(accepted_count / 3.0, 1.0),
            }

            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=True,
                details=result_details,
                metrics=metrics,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            logger.exception("WFA验证失败")
            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=False,
                details={"error": str(e)},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _update_configuration(
        self, validation_details: dict[str, Any]
    ) -> CorrectionResult:
        """更新系统配置"""
        start_time = datetime.now()
        self.current_stage = CorrectionStage.CONFIG_UPDATE

        try:
            # 本轮 WFA 无改进 → 跳过更新，仍算周期成功（观望是正常结果）
            if not validation_details.get("has_best_config", False):
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=True,
                    details={"reason": "本轮无改进配置，保持当前参数不变"},
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # 获取最佳配置
            best_config = validation_details.get("_best_config_full")
            if not best_config:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=True,
                    details={"reason": "最佳配置对象未存储，保持当前参数不变"},
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # 保存旧配置
            old_config = copy.deepcopy(self.current_config)

            # 应用平滑过渡
            self._apply_configuration_update(best_config)

            # BUG-10 修复：仅在有变异被接受时才标记错题本中的错误为已学习
            learning_batch: list = []
            if validation_details.get("has_best_config", False):
                # 标记错题本中的错误为已学习
                learning_batch = self.mistake_book.get_learning_batch(batch_size=20)
                if learning_batch:
                    record_ids = [record.error_id for record in learning_batch]
                    self.mistake_book.mark_batch_as_learned(
                        record_ids, outcome="configuration_updated"
                    )

            result_details = {
                "old_config_summary": self._summarize_config(old_config),
                "new_config_summary": self._summarize_config(self.current_config),
                "config_changes": self._compare_configs(
                    old_config, self.current_config
                ),
                "errors_marked_as_learned": len(learning_batch),
                "improvement_score": validation_details.get("best_config_score", 0.0),
            }

            metrics = {
                "config_change_magnitude": self._calculate_config_change_magnitude(
                    old_config, self.current_config
                ),
                "learning_utilization": len(learning_batch) / 20,
                "improvement_achieved": max(
                    validation_details.get("best_config_score", 0.0), 0.0
                ),
            }

            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=True,
                details=result_details,
                metrics=metrics,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            logger.exception("配置更新失败")
            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=False,
                details={"error": str(e)},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _evaluate_correction(self) -> CorrectionResult:
        """评估修正效果"""
        start_time = datetime.now()
        self.current_stage = CorrectionStage.EVALUATION

        try:
            # 这里可以添加实际的效果评估逻辑
            # 例如：监控修正后的系统表现，与基准比较等

            # 简化实现：记录评估信息
            evaluation_period = self.config.get("evaluation_period_hours", 24)

            result_details = {
                "evaluation_period_hours": evaluation_period,
                "next_evaluation_time": (
                    datetime.now() + timedelta(hours=evaluation_period)
                ).isoformat(),
                "total_corrections": len(self.correction_history),
                "successful_corrections": sum(
                    1 for r in self.correction_history if r.success
                ),
                "current_config_status": "active",
            }

            # ---- P2-2 修复：基于真实历史数据计算 system_stability 和 performance_trend ----
            # 计算 system_stability：最近 N 次纠正的成功率
            recent_n = min(10, len(self.correction_history))
            if recent_n > 0:
                recent_corrections = self.correction_history[-recent_n:]
                system_stability = (
                    sum(1 for r in recent_corrections if r.success) / recent_n
                )
            else:
                system_stability = 0.5  # 无历史时使用中间值

            # 计算 performance_trend：最近 N 次 COMPOSITE_SCORE 的变化趋势
            performance_trend = 0.0
            if len(self.performance_history) >= 2:
                recent_perf = self.performance_history[-10:]
                scores = [
                    p.get("COMPOSITE_SCORE", p.get("composite_score", 0.0))
                    for p in recent_perf
                    if isinstance(p, dict)
                ]
                if len(scores) >= 2:
                    # 简单线性趋势：最后一个 - 第一个
                    performance_trend = (scores[-1] - scores[0]) / max(
                        len(scores) - 1, 1
                    )

            logger.debug(
                "评估指标: system_stability=%.3f, performance_trend=%.4f",
                system_stability,
                performance_trend,
            )

            metrics = {
                "correction_success_rate": sum(
                    1 for r in self.correction_history if r.success
                )
                / max(len(self.correction_history), 1),
                "system_stability": system_stability,
                "performance_trend": performance_trend,
            }

            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=True,
                details=result_details,
                metrics=metrics,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except Exception as e:
            logger.exception("效果评估失败")
            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=False,
                details={"error": str(e)},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _apply_configuration_update(self, new_config: dict[str, Any]) -> None:
        """应用配置更新并同步 GA baseline

        更新 workflow.current_config 后，同步
        GeneticAlgorithm 的 baseline，让下一轮进化从新配置出发。
        """
        # 更新当前配置
        self.current_config.update(new_config)

        # 同步 GA 的 baseline
        if self.genetic_algorithm is not None:
            self.genetic_algorithm.baseline = copy.deepcopy(self.current_config)

        logger.info("配置已更新，新配置参数数量: %d", len(self.current_config))

    def _summarize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """生成配置摘要"""
        summary = {}

        for key, value in config.items():
            if isinstance(value, dict):
                if key in ["period_weight_filter", "threshold_parameters"]:
                    summary[key] = value
                else:
                    summary[key] = {"type": "dict", "keys": list(value.keys())[:3]}
            elif isinstance(value, (int, float)):
                summary[key] = round(value, 4)
            else:
                summary[key] = str(type(value))

        return summary

    def _estimate_config_complexity(self, configs: list[dict[str, Any]]) -> float:
        """估计配置复杂度"""
        if not configs:
            return 0.0

        complexities = []
        for config in configs:
            # 简单复杂度估计：参数数量
            param_count = self._count_parameters(config)
            complexities.append(min(param_count / 50, 1.0))  # 归一化

        return float(np.mean(complexities)) if complexities else 0.0

    def _count_parameters(self, config: Any) -> int:
        """递归计算参数数量"""
        if isinstance(config, dict):
            return sum(self._count_parameters(v) for v in config.values())
        if isinstance(config, (list, tuple)):
            return sum(self._count_parameters(v) for v in config)
        return 1

    def _compare_configs(
        self, old_config: dict[str, Any], new_config: dict[str, Any]
    ) -> dict[str, Any]:
        """比较两个配置的差异"""
        changes = {}

        all_keys = set(old_config.keys()) | set(new_config.keys())

        for key in all_keys:
            old_val = old_config.get(key)
            new_val = new_config.get(key)

            if old_val != new_val:
                if isinstance(old_val, (int, float)) and isinstance(
                    new_val, (int, float)
                ):
                    changes[key] = {
                        "old": round(old_val, 4),
                        "new": round(new_val, 4),
                        "change": round(new_val - old_val, 4),
                        "change_percent": round((new_val - old_val) / old_val * 100, 2)
                        if old_val != 0
                        else float("inf"),
                    }
                else:
                    changes[key] = {
                        "old": str(old_val)[:50],
                        "new": str(new_val)[:50],
                        "type": "non_numeric",
                    }

        return changes

    def _calculate_config_change_magnitude(
        self, old_config: dict[str, Any], new_config: dict[str, Any]
    ) -> float:
        """计算配置变化幅度"""
        changes = self._compare_configs(old_config, new_config)

        if not changes:
            return 0.0

        # 计算数值变化的平均幅度
        numeric_changes = []
        for change_info in changes.values():
            if "change_percent" in change_info and change_info[
                "change_percent"
            ] != float("inf"):
                numeric_changes.append(abs(change_info["change_percent"]))

        if numeric_changes:
            return float(np.mean(numeric_changes)) / 100  # 归一化到0-1
        return 0.1  # 默认小幅度变化

    def _create_cycle_summary(
        self, start_time: datetime, success: bool, cycle_results: dict[str, Any]
    ) -> dict[str, Any]:
        """创建修正周期摘要"""
        duration = (datetime.now() - start_time).total_seconds()

        summary = {
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "duration_seconds": round(duration, 2),
            "stages_completed": len(cycle_results),
            "cycle_results": cycle_results,
            "current_config": self._summarize_config(self.current_config),
            "workflow_status": {
                "is_running": self.is_running,
                "current_stage": self.current_stage.value,
                "total_corrections": len(self.correction_history),
                "last_correction_time": self.last_correction_time.isoformat()
                if self.last_correction_time
                else None,
            },
        }

        # 添加到性能历史
        self.performance_history.append(summary)

        # 限制历史记录大小
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]

        logger.info(f"修正周期完成: 成功={success}, 耗时={duration:.2f}秒")
        return summary

    def get_workflow_status(self) -> dict[str, Any]:
        """获取工作流状态"""
        status: dict[str, Any] = {
            "is_running": self.is_running,
            "current_stage": self.current_stage.value,
            "current_config": self._summarize_config(self.current_config),
            "correction_history_count": len(self.correction_history),
            "performance_history_count": len(self.performance_history),
            "last_correction_time": self.last_correction_time,
        }

        if self.mistake_book is not None:
            status["mistake_book_stats"] = self.mistake_book.get_statistics()

        if self.genetic_algorithm is not None:
            status["ga_stats"] = self.genetic_algorithm.get_population_stats()

        return status

    def reset_workflow(self) -> None:
        """重置工作流状态"""
        self.current_stage = CorrectionStage.ERROR_ANALYSIS
        self.is_running = False
        self.current_config = copy.deepcopy(self.baseline_config)
        self.correction_history.clear()
        self.performance_history.clear()
        self.last_correction_time = None

        # 重置组件
        if self.mistake_book is not None:
            self.mistake_book.clear_records()
        if self.genetic_algorithm is not None:
            self.genetic_algorithm.population.clear()
            self.genetic_algorithm.generation = 0
            self.genetic_algorithm.best_individual = None
            self.genetic_algorithm.history.clear()

        logger.info("工作流状态已重置")


# 使用示例
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 创建工作流配置
    workflow_config = {
        "initial_config": {
            "period_weight_filter": {
                "weights": {
                    "W": 0.25,
                    "D": 0.20,
                    "H4": 0.18,
                    "H1": 0.15,
                    "M15": 0.12,
                    "M5": 0.10,
                },
            },
            "threshold_parameters": {
                "confidence_threshold": 0.7,
                "volume_threshold": 1.5,
            },
        },
        "min_errors_for_correction": 5,
        "ga_generations": 5,
        "ga_config": {
            "population_size": 10,
            "max_generations": 5,
        },
        "cycle_interval_hours": 1,
        "mistake_book_config": {
            "max_records": 100,
            "auto_cleanup_days": 7,
        },
    }

    # 创建自我修正工作流
    workflow = SelfCorrectionWorkflow(workflow_config)

    # 添加一些模拟错误到错题本
    if workflow.mistake_book is not None and MistakeType is not None:
        for i in range(10):
            workflow.mistake_book.record_mistake(
                mistake_type=MistakeType.STATE_MISJUDGMENT,
                severity=ErrorSeverity.MEDIUM,
                context={
                    "market_regime": "TRENDING_BULLISH",
                    "price": 45000.0 + i * 100,
                    "volume": 1200 + i * 50,
                    "expected_state": "ACCUMULATION",
                    "actual_state": "DISTRIBUTION",
                },
                expected="ACCUMULATION",
                actual="DISTRIBUTION",
                confidence_before=0.8,
                confidence_after=0.3,
                impact_score=0.5,
                module_name="wyckoff_state_machine",
                timeframe="H4",
                patterns=[ErrorPattern.FREQUENT_FALSE_POSITIVE],
            )

    # 运行修正周期
    cycle_result = workflow.run_correction_cycle()

    # 获取工作流状态
    status = workflow.get_workflow_status()
