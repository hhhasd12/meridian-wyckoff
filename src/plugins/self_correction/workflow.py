"""
自我修正闭环工作流模块
实现错题本 → 权重变异 → WFA验证 → 配置更新的完整闭环

设计原则：
1. 数据驱动：基于错题本错误模式进行针对性修正
2. 渐进优化：小步快跑，每次调整幅度有限
3. 防过拟合：WFA验证确保泛化能力
4. 闭环反馈：修正结果反馈到系统，形成持续优化循环
5. 可追溯性：记录每次修正的完整决策过程

工作流步骤：
1. 错题本分析：收集错误模式，识别系统弱点
2. 权重变异生成：基于错误模式生成针对性变异配置
3. WFA验证：使用Walk-Forward Analysis验证变异配置
4. 配置更新：选择最佳配置，平滑过渡到新参数
5. 效果评估：监控修正后的系统表现
"""

import copy
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

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
    from src.core.weight_variator import WeightVariator  # legacy，暂无插件版本
    from src.kernel.types import MutationType
except ImportError:
    WeightVariator = None
    MutationType = None

try:
    from src.plugins.evolution.wfa_backtester import (
        PerformanceMetric,
        ValidationResult,
        WFABacktester,
    )
except ImportError:
    PerformanceMetric = None
    ValidationResult = None
    WFABacktester = None

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
    2. 协调错题本、权重变异器、WFA回测引擎
    3. 记录修正历史和决策过程
    4. 提供修正效果评估
    """

    def __init__(
        self,
        config: dict[str, Any],
        mistake_book: Optional[MistakeBook] = None,
        weight_variator: Optional[WeightVariator] = None,
        wfa_backtester: Optional[WFABacktester] = None,
    ):
        """
        初始化自我修正工作流

        Args:
            config: 工作流配置
            mistake_book: 错题本实例
            weight_variator: 权重变异器实例
            wfa_backtester: WFA回测引擎实例
        """
        self.config = config

        # 初始化组件
        self.mistake_book = mistake_book or MistakeBook(
            config.get("mistake_book_config", {})
        )
        self.weight_variator = weight_variator or WeightVariator(
            config.get("weight_variator_config", {})
        )
        self.wfa_backtester = wfa_backtester or WFABacktester(
            config.get("wfa_backtester_config", {})
        )

        # 工作流状态
        self.current_stage = CorrectionStage.ERROR_ANALYSIS
        self.is_running = False
        self.current_config = config.get("initial_config", {})
        self.baseline_config = copy.deepcopy(self.current_config)

        # 历史记录
        self.correction_history: list[CorrectionResult] = []
        self.performance_history: list[dict[str, Any]] = []

        # 性能评估器（需要外部提供）
        self.performance_evaluator: Optional[Callable] = None
        self.historical_data: Optional[pd.DataFrame] = None

        # 配置参数
        self.min_errors_for_correction = config.get("min_errors_for_correction", 10)
        self.max_mutations_per_cycle = config.get("max_mutations_per_cycle", 5)
        self.cycle_interval_hours = config.get("cycle_interval_hours", 24)
        self.last_correction_time: Optional[datetime] = None

        logger.info("自我修正闭环工作流初始化完成")

    def set_performance_evaluator(self, evaluator: Callable) -> None:
        """设置性能评估函数"""
        self.performance_evaluator = evaluator

    def set_historical_data(self, data: pd.DataFrame) -> None:
        """设置历史数据"""
        self.historical_data = data

    def initialize_wfa_baseline(self) -> bool:
        """初始化WFA基准配置"""
        try:
            if self.performance_evaluator is None:
                logger.warning("未设置性能评估器，使用模拟评估")

            logger.info(f"开始初始化WFA基准，配置: {self.baseline_config}")
            logger.info(
                f"历史数据: {len(self.historical_data) if self.historical_data is not None else 'None'} 条"
            )

            baseline_perf = self.wfa_backtester.initialize_with_baseline(
                baseline_config=self.baseline_config,
                historical_data=self.historical_data,
                performance_evaluator=self.performance_evaluator,
            )

            logger.info(
                f"WFA基准配置初始化完成，综合评分: {baseline_perf.get('COMPOSITE_SCORE', 'N/A')}"
            )
            return True

        except Exception as e:
            logger.exception(f"初始化WFA基准配置失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False

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
        """生成变异配置"""
        start_time = datetime.now()
        self.current_stage = CorrectionStage.MUTATION_GENERATION

        try:
            weight_adjustments = analysis_details.get("weight_adjustments", [])
            pattern_analysis = analysis_details.get("pattern_analysis", {})

            # 无调整建议时降级为纯随机变异，而非终止周期
            if not weight_adjustments:
                mutated_configs = self._add_random_mutations([])
                mutation_details = []
                if not mutated_configs:
                    return CorrectionResult(
                        stage=self.current_stage,
                        timestamp=datetime.now(),
                        success=False,
                        details={"reason": "无调整建议且随机变异生成失败"},
                        error_message="无法生成任何变异配置",
                        duration_seconds=(datetime.now() - start_time).total_seconds(),
                    )
                result_details = {
                    "total_mutations": len(mutated_configs),
                    "mutation_details": [
                        {"_config_full": c, "config_summary": self._summarize_config(c)}
                        for c in mutated_configs
                    ],
                    "pattern_based_mutations": 0,
                    "random_mutations": len(mutated_configs),
                    "source_patterns": [],
                }
                metrics = {
                    "mutation_diversity": len(mutated_configs)
                    / self.max_mutations_per_cycle,
                    "pattern_coverage": 0.0,
                    "config_complexity": self._estimate_config_complexity(
                        mutated_configs
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

            # 生成变异配置
            mutated_configs = []
            mutation_details = []

            # ---- P0-2 修复：只在种群为空时初始化，后续使用 evolve_from_existing ----
            if not getattr(self.weight_variator, "population", None):
                self.weight_variator.generate_initial_population(self.current_config)
                logger.debug(
                    "首次初始化种群, size=%d",
                    len(self.weight_variator.population),
                )
            else:
                # 后续调用：从现有种群进化，传入 weight_adjustments 作为偏置
                if hasattr(self.weight_variator, "evolve_from_existing"):
                    self.weight_variator.evolve_from_existing(
                        self.current_config,
                        weight_adjustments=weight_adjustments,
                    )
                    logger.debug(
                        "从现有种群进化, size=%d",
                        len(self.weight_variator.population),
                    )
                else:
                    self.weight_variator.generate_initial_population(
                        self.current_config
                    )

            for i, adjustment in enumerate(
                weight_adjustments[: self.max_mutations_per_cycle]
            ):
                try:
                    # ---- P0-2 修复：不再每次循环重置种群 ----
                    # 从种群中取独立的变异体（跳过 index 0 的 base config）
                    if (
                        hasattr(self.weight_variator, "population")
                        and len(self.weight_variator.population) > 1
                    ):
                        # 确保每个 adjustment 对应独立的变异体
                        # 使用 i+1 但用取模防止越界
                        pop_size = len(self.weight_variator.population)
                        pop_idx = (i + 1) % pop_size
                        if pop_idx == 0:
                            pop_idx = 1  # 跳过 base config
                        mutated_config = [
                            self.weight_variator.population[pop_idx]["config"]
                        ]
                    else:
                        # 回退到简单变异
                        mutated_config = [
                            self._simple_mutate(self.current_config, adjustment)
                        ]

                    if mutated_config:
                        mutated_configs.append(mutated_config[0])
                        mutation_details.append(
                            {
                                "adjustment_index": i,
                                "adjustment": adjustment,
                                "config_summary": self._summarize_config(
                                    mutated_config[0]
                                ),
                                # 保留完整 config 对象，供 _validate_mutations 直接使用
                                "_config_full": mutated_config[0],
                            }
                        )

                except Exception as e:
                    logger.warning(f"生成变异配置 {i} 失败: {e}")

            if not mutated_configs:
                return CorrectionResult(
                    stage=self.current_stage,
                    timestamp=datetime.now(),
                    success=False,
                    details={"reason": "无法生成有效变异配置"},
                    error_message="权重变异器未能生成有效配置",
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # 添加一些随机变异以增加多样性
            random_mutations = self._add_random_mutations(mutated_configs)
            mutated_configs.extend(random_mutations)

            result_details = {
                "total_mutations": len(mutated_configs),
                "mutation_details": mutation_details,
                "pattern_based_mutations": len(mutation_details),
                "random_mutations": len(random_mutations),
                "source_patterns": pattern_analysis.get("patterns", []),
            }

            metrics = {
                "mutation_diversity": len(mutated_configs)
                / self.max_mutations_per_cycle,
                "pattern_coverage": len(mutation_details) / len(weight_adjustments),
                "config_complexity": self._estimate_config_complexity(mutated_configs),
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
            logger.exception("变异生成失败")
            return CorrectionResult(
                stage=self.current_stage,
                timestamp=datetime.now(),
                success=False,
                details={"error": str(e)},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _validate_mutations(self, mutation_details: dict[str, Any]) -> CorrectionResult:
        """验证变异配置"""
        start_time = datetime.now()
        self.current_stage = CorrectionStage.WFA_VALIDATION

        try:
            # 从 mutation_details 中直接取出 _generate_mutations 传递的真实 config 对象
            mutated_configs = []
            for detail in mutation_details.get("mutation_details", []):
                cfg = detail.get("_config_full")
                if cfg is not None:
                    mutated_configs.append(cfg)

            # 若上层未传入有效 config（理论不会发生），用随机变异兜底
            if not mutated_configs:
                mutated_configs = self._add_random_mutations([])

            # 执行WFA验证
            accepted_configs, rejected_configs, validation_report = (
                self.wfa_backtester.validate_mutations(
                    mutated_configs=mutated_configs,
                    historical_data=self.historical_data,
                    performance_evaluator=self.performance_evaluator,
                    mistake_book=self.mistake_book,
                )
            )

            # 分析验证结果
            best_config = None
            best_score = -float("inf")

            if accepted_configs and validation_report.get("validation_details"):
                for i, detail in enumerate(validation_report["validation_details"]):
                    if detail.get("result") == ValidationResult.ACCEPTED.value:
                        score = detail.get("improvement", 0.0)
                        if score > best_score and i < len(accepted_configs):
                            best_score = score
                            best_config = accepted_configs[i]

            result_details = {
                "total_validated": len(mutated_configs),
                "accepted": len(accepted_configs),
                "rejected": len(rejected_configs),
                "acceptance_rate": validation_report.get("acceptance_rate", 0.0),
                "average_improvement": validation_report.get(
                    "average_improvement", 0.0
                ),
                "best_config_score": best_score,
                "has_best_config": best_config is not None,
                "validation_report": validation_report,
            }

            metrics = {
                "acceptance_rate": validation_report.get("acceptance_rate", 0.0),
                "average_improvement": validation_report.get(
                    "average_improvement", 0.0
                ),
                "validation_quality": min(len(accepted_configs) / 3, 1.0),
            }

            # 存储最佳配置供后续使用
            if best_config:
                result_details["best_config"] = self._summarize_config(best_config)
                result_details["_best_config_full"] = best_config  # 内部使用

            # WFA 本身运行成功；accepted=0 是"无改进"的正常结果，不是错误
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
        """应用配置更新（平滑过渡）"""
        # 简单实现：直接替换
        # 实际应用中可能需要更复杂的合并逻辑
        self.current_config.update(new_config)

        # 记录配置更新
        logger.info(f"配置已更新，新配置参数数量: {len(self.current_config)}")

    def _simple_mutate(
        self, base_config: dict[str, Any], adjustment: dict[str, Any]
    ) -> dict[str, Any]:
        """简单变异方法（当权重变异器不可用时使用）"""
        mutated_config = copy.deepcopy(base_config)

        # 根据调整建议进行简单变异
        adjustment_value = adjustment.get("adjustment_value", 0.05)
        module = adjustment.get("module", "")

        if (
            module == "threshold_adjustment"
            and "threshold_parameters" in mutated_config
        ):
            params = mutated_config["threshold_parameters"]
            for param in ["confidence_threshold", "volume_threshold"]:
                if param in params:
                    params[param] = max(0.01, params[param] + adjustment_value)

        elif (
            module == "period_weight_filter"
            and "period_weight_filter" in mutated_config
        ):
            weights = mutated_config["period_weight_filter"].get("weights", {})
            if weights:
                # 简单调整：增加第一个权重，减少最后一个权重
                keys = list(weights.keys())
                if len(keys) >= 2:
                    weights[keys[0]] = min(0.5, weights[keys[0]] + adjustment_value / 2)
                    weights[keys[-1]] = max(
                        0.01, weights[keys[-1]] - adjustment_value / 2
                    )

        return mutated_config

    def _add_random_mutations(
        self, base_mutations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """添加随机变异以增加多样性"""
        random_mutations = []

        max_random = min(2, self.max_mutations_per_cycle - len(base_mutations))
        if max_random < 1:
            return []
        num_random = random.randint(1, max_random)

        for _ in range(num_random):
            try:
                random_config = copy.deepcopy(self.current_config)

                if "period_weight_filter" in random_config:
                    weights = random_config["period_weight_filter"].get("weights", {})
                    if weights:
                        key = random.choice(list(weights.keys()))
                        change = random.uniform(-0.03, 0.03)
                        weights[key] = max(0.01, weights[key] + change)

                if "threshold_parameters" in random_config:
                    params = random_config["threshold_parameters"]
                    if params:
                        key = random.choice(list(params.keys()))
                        if isinstance(params[key], (int, float)):
                            change = random.uniform(-0.05, 0.05)
                            params[key] = max(0.01, params[key] + change)

                for key in random_config:
                    if isinstance(random_config[key], (int, float)) and key not in [
                        "period_weight_filter",
                        "threshold_parameters",
                    ]:
                        change = random.uniform(-0.05, 0.05)
                        random_config[key] = max(0.01, random_config[key] + change)

                if random_config:
                    random_mutations.append(random_config)

            except Exception as e:
                logger.warning(f"生成随机变异失败: {e}")

        return random_mutations

    def _create_mock_mutations(self) -> list[dict[str, Any]]:
        """创建模拟变异配置（用于测试）"""
        mutations = []

        # 基于当前配置创建几个变异
        base_config = self.current_config

        # 变异1：调整周期权重
        config1 = copy.deepcopy(base_config)
        if "period_weight_filter" in config1:
            weights = config1["period_weight_filter"].get("weights", {})
            if "W" in weights and "D" in weights:
                weights["W"] = min(0.3, weights["W"] + 0.02)
                weights["D"] = max(0.15, weights["D"] - 0.02)
        mutations.append(config1)

        # 变异2：调整阈值参数
        config2 = copy.deepcopy(base_config)
        if "threshold_parameters" in config2:
            params = config2["threshold_parameters"]
            if "confidence_threshold" in params:
                params["confidence_threshold"] = min(
                    0.8, params["confidence_threshold"] + 0.03
                )
        mutations.append(config2)

        # 变异3：综合调整
        config3 = copy.deepcopy(base_config)
        if "period_weight_filter" in config3 and "threshold_parameters" in config3:
            weights = config3["period_weight_filter"].get("weights", {})
            params = config3["threshold_parameters"]

            if "H4" in weights:
                weights["H4"] = min(0.25, weights["H4"] + 0.015)
            if "volume_threshold" in params:
                params["volume_threshold"] = max(1.2, params["volume_threshold"] - 0.1)
        mutations.append(config3)

        return mutations

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

        return np.mean(complexities) if complexities else 0.0

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
            return np.mean(numeric_changes) / 100  # 归一化到0-1
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
        return {
            "is_running": self.is_running,
            "current_stage": self.current_stage.value,
            "current_config": self._summarize_config(self.current_config),
            "correction_history_count": len(self.correction_history),
            "performance_history_count": len(self.performance_history),
            "last_correction_time": self.last_correction_time,
            "mistake_book_stats": self.mistake_book.get_statistics(),
            "wfa_status": self.wfa_backtester.get_performance_summary(),
        }

    def reset_workflow(self) -> None:
        """重置工作流状态"""
        self.current_stage = CorrectionStage.ERROR_ANALYSIS
        self.is_running = False
        self.current_config = copy.deepcopy(self.baseline_config)
        self.correction_history.clear()
        self.performance_history.clear()
        self.last_correction_time = None

        # 重置组件
        self.mistake_book.clear_records()
        self.wfa_backtester.reset()

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
        "max_mutations_per_cycle": 3,
        "cycle_interval_hours": 1,
        "mistake_book_config": {
            "max_records": 100,
            "auto_cleanup_days": 7,
        },
        "weight_variator_config": {
            "mutation_strength": 0.05,
            "mutation_probability": 0.3,
        },
        "wfa_backtester_config": {
            "train_days": 30,
            "test_days": 10,
            "step_days": 5,
            "min_performance_improvement": 0.01,
        },
    }

    # 创建自我修正工作流
    workflow = SelfCorrectionWorkflow(workflow_config)

    # 添加一些模拟错误到错题本
    mistake_book = workflow.mistake_book
    for i in range(10):
        mistake_book.record_mistake(
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
