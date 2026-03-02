"""
权重变异算法模块
基于错题本错误模式分析，实现智能权重变异算法，实现系统自动进化

设计原则：
1. 针对性变异：基于错误模式（假阳性/假阴性/时机错误等）进行有针对性的变异
2. 渐进调整：单次调整不超过5%，防止参数跳跃
3. 遗传算法框架：变异、交叉、选择完整进化流程
4. WFA验证：所有变异需通过Walk-Forward Analysis验证防过拟合
5. 模块化变异：支持对周期权重、市场体制系数、阈值参数等多种参数的变异

技术要点：
- 变异算子：基于错误模式的定向变异
- 交叉算子：模块间权重协调与组合优化
- 选择机制：基于WFA回测性能的选择
- 防过拟合：变异多样性保持，防止早熟收敛
"""

import copy
import random
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np

# 导入错题本模块
try:
    from .mistake_book import ErrorPattern, ErrorSeverity, MistakeBook
except ImportError:
    # 备用导入（如果错题本不在同一目录）
    from mistake_book import ErrorPattern, ErrorSeverity, MistakeBook


class MutationType(Enum):
    """变异类型枚举"""

    THRESHOLD_ADJUSTMENT = "THRESHOLD_ADJUSTMENT"  # 阈值调整
    WEIGHT_ADJUSTMENT = "WEIGHT_ADJUSTMENT"  # 权重调整
    PARAMETER_TUNING = "PARAMETER_TUNING"  # 参数调优
    STRUCTURAL_CHANGE = "STRUCTURAL_CHANGE"  # 结构性改变
    COEFFICIENT_ADJUSTMENT = "COEFFICIENT_ADJUSTMENT"  # 系数调整


class MutationOperator:
    """
    变异算子基类
    定义不同类型的变异操作
    """

    def __init__(
        self,
        mutation_type: MutationType,
        target_module: str,
        parameters: list[str],
        max_change: float = 0.05,
    ):
        """
        初始化变异算子

        Args:
            mutation_type: 变异类型
            target_module: 目标模块名称
            parameters: 目标参数列表
            max_change: 最大变化幅度（默认5%）
        """
        self.mutation_type = mutation_type
        self.target_module = target_module
        self.parameters = parameters
        self.max_change = max_change
        self.mutation_history = []

    def mutate(
        self,
        value: Any,
        pattern: ErrorPattern,
        frequency: float,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    ) -> Any:
        """
        执行变异操作

        Args:
            value: 当前参数值（可以是float、Dict等类型）
            pattern: 错误模式
            frequency: 错误频率（0-1）
            severity: 错误严重程度（默认MEDIUM）

        Returns:
            变异后的参数值
        """
        # 基类方法，子类必须实现
        # 使用所有参数以避免未使用参数警告
        _ = (value, pattern, frequency, severity)
        raise NotImplementedError("子类必须实现mutate方法")

    def get_mutation_direction(self, pattern: ErrorPattern) -> float:
        """
        根据错误模式获取变异方向

        Returns:
            变异方向：正数表示增加，负数表示减少，0表示中性
        """
        # 根据错误模式确定变异方向
        direction = 0.0

        if pattern == ErrorPattern.FREQUENT_FALSE_POSITIVE:
            # 假阳性过多 → 增加阈值/降低敏感性
            direction = 1.0  # 正向调整（增加阈值）
        elif pattern == ErrorPattern.FREQUENT_FALSE_NEGATIVE:
            # 假阴性过多 → 降低阈值/提高敏感性
            direction = -1.0  # 负向调整（降低阈值）
        elif pattern == ErrorPattern.TIMING_ERROR:
            # 时机错误 → 调整时间参数
            direction = 0.5  # 中等正向调整
        elif pattern == ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT:
            # 多周期错配 → 调整周期权重
            direction = 0.3  # 小幅调整
        else:
            # 其他错误模式，随机方向但幅度较小
            direction = random.choice([-0.2, 0.2])

        return direction

    def calculate_mutation_magnitude(
        self, frequency: float, severity: ErrorSeverity
    ) -> float:
        """
        计算变异幅度

        Args:
            frequency: 错误频率（0-1）
            severity: 错误严重程度

        Returns:
            变异幅度（0-max_change）
        """
        # 基础幅度基于频率
        base_magnitude = frequency * self.max_change

        # 根据严重程度调整
        severity_multipliers = {
            ErrorSeverity.LOW: 0.5,
            ErrorSeverity.MEDIUM: 1.0,
            ErrorSeverity.HIGH: 1.5,
            ErrorSeverity.CRITICAL: 2.0,
        }

        multiplier = severity_multipliers.get(severity, 1.0)
        magnitude = base_magnitude * multiplier

        # 确保不超过最大变化
        return min(magnitude, self.max_change)

    def record_mutation(
        self, parameter: str, old_value: float, new_value: float, pattern: ErrorPattern
    ):
        """记录变异历史"""
        timestamp = datetime.now()
        change_percent = (
            abs((new_value - old_value) / old_value * 100) if old_value != 0 else 0
        )
        self.mutation_history.append(
            {
                "timestamp": timestamp,
                "parameter": parameter,
                "old_value": old_value,
                "new_value": new_value,
                "pattern": pattern.value,
                "module": self.target_module,
                "change_percent": change_percent,
            }
        )


class ThresholdMutationOperator(MutationOperator):
    """
    阈值变异算子
    专门用于调整各类阈值参数
    """

    def __init__(
        self, target_module: str, parameters: list[str], max_change: float = 0.05
    ):
        super().__init__(
            MutationType.THRESHOLD_ADJUSTMENT, target_module, parameters, max_change
        )
        self.max_change = max_change  # 确保属性存在（已在父类设置）

    def mutate(
        self,
        value: Any,
        pattern: ErrorPattern,
        frequency: float,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    ) -> Any:
        """
        执行阈值变异

        Args:
            value: 当前阈值（应为float类型）
            pattern: 错误模式
            frequency: 错误频率
            severity: 错误严重程度

        Returns:
            变异后的阈值
        """
        # 确保输入为float类型
        if not isinstance(value, (int, float)):
            raise TypeError(f"阈值变异需要数值类型，但收到 {type(value)}")

        current_value = float(value)

        # 获取变异方向
        direction = self.get_mutation_direction(pattern)

        # 计算变异幅度
        magnitude = self.calculate_mutation_magnitude(frequency, severity)

        # 计算新值
        if direction > 0:
            # 正向调整（增加阈值）
            new_value = current_value * (1 + magnitude)
        elif direction < 0:
            # 负向调整（降低阈值）
            new_value = current_value * (1 - magnitude)
        else:
            # 中性调整，小幅度随机变异
            random_change = random.uniform(-magnitude / 2, magnitude / 2)
            new_value = current_value * (1 + random_change)

        # 确保新值在合理范围内
        return max(new_value, 0.01)  # 最小1%



class WeightMutationOperator(MutationOperator):
    """
    权重变异算子
    专门用于调整权重参数（如周期权重）
    """

    def __init__(
        self,
        target_module: str,
        parameters: list[str],
        max_change: float = 0.05,
        weight_sum_constraint: bool = True,
    ):
        """
        初始化权重变异算子

        Args:
            weight_sum_constraint: 是否保持权重总和约束（如总和为1）
        """
        super().__init__(
            MutationType.WEIGHT_ADJUSTMENT, target_module, parameters, max_change
        )
        self.weight_sum_constraint = weight_sum_constraint

    def mutate(
        self,
        value: Any,
        pattern: ErrorPattern,
        frequency: float,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        **kwargs,
    ) -> Any:
        """
        执行权重变异

        Args:
            value: 权重字典（Dict[str, float]）
            pattern: 错误模式
            frequency: 错误频率
            severity: 错误严重程度
            **kwargs: 额外关键字参数，包括：
                - focus_parameters: 需要重点调整的参数列表（如None则调整所有参数）

        Returns:
            变异后的权重字典
        """
        # 检查输入类型
        if not isinstance(value, dict):
            raise TypeError(f"权重变异需要字典类型，但收到 {type(value)}")

        weights = value  # 类型提示：应为Dict[str, float]
        focus_parameters = kwargs.get("focus_parameters")

        # 深拷贝原始权重
        new_weights = copy.deepcopy(weights)

        # 确定需要调整的参数
        if focus_parameters is None:
            params_to_adjust = list(weights.keys())
        else:
            params_to_adjust = [p for p in focus_parameters if p in weights]

        if not params_to_adjust:
            return new_weights

        # 根据错误模式确定调整策略
        if pattern == ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT:
            # 多周期错配：调整周期权重分布
            adjustments = self._adjust_for_misalignment(
                weights, params_to_adjust, frequency, severity
            )
        elif pattern == ErrorPattern.FREQUENT_FALSE_POSITIVE:
            # 假阳性过多：降低敏感性较高的权重
            adjustments = self._adjust_for_false_positive(
                weights, params_to_adjust, frequency, severity
            )
        elif pattern == ErrorPattern.FREQUENT_FALSE_NEGATIVE:
            # 假阴性过多：提高敏感性较低的权重
            adjustments = self._adjust_for_false_negative(
                weights, params_to_adjust, frequency, severity
            )
        else:
            # 通用调整：根据错误模式方向调整
            adjustments = self._general_adjustment(
                weights, params_to_adjust, pattern, frequency, severity
            )

        # 应用调整，但限制调整幅度
        for param, adjustment in adjustments.items():
            if param in new_weights:
                # 限制调整幅度不超过max_change
                adjustment = max(min(adjustment, self.max_change), -self.max_change)
                new_weights[param] *= 1 + adjustment

        # 应用权重总和约束
        if self.weight_sum_constraint:
            new_weights = self._normalize_weights(new_weights)

            # 归一化后，再次确保变化幅度不超过限制
            # 计算归一化后的实际变化
            for param in params_to_adjust:
                if param in weights and param in new_weights:
                    original = weights[param]
                    new = new_weights[param]
                    if original > 0:
                        actual_change = (new - original) / original
                        # 如果实际变化超过限制，进行修正
                        if abs(actual_change) > self.max_change:
                            # 将变化限制在max_change范围内
                            if actual_change > 0:
                                new_weights[param] = original * (1 + self.max_change)
                            else:
                                new_weights[param] = original * (1 - self.max_change)

            # 重新归一化以确保总和为1
            new_weights = self._normalize_weights(new_weights)

        # 记录变异
        for param in params_to_adjust:
            if param in weights and param in new_weights:
                self.record_mutation(param, weights[param], new_weights[param], pattern)

        return new_weights

    def _adjust_for_misalignment(
        self,
        weights: dict[str, float],
        params: list[str],
        frequency: float,
        severity: ErrorSeverity,
    ) -> dict[str, float]:
        """针对多周期错配的调整策略"""
        adjustments = {}

        # 多周期错配通常意味着权重分布不合理
        # 计算当前权重的标准差，标准差越大说明权重分布越不均衡
        weight_values = list(weights.values())
        std_dev = np.std(weight_values) if len(weight_values) > 1 else 0

        # 如果标准差较大，向更均衡的方向调整
        if std_dev > 0.1:  # 经验阈值
            mean_weight = np.mean(weight_values)
            for param in params:
                current = weights[param]
                # 向均值方向调整
                if current > mean_weight:
                    adjustments[param] = -frequency * 0.1  # 高于均值则降低
                else:
                    adjustments[param] = frequency * 0.1  # 低于均值则提高
        else:
            # 标准差较小，随机小幅调整以探索
            for param in params:
                adjustments[param] = random.uniform(-0.05, 0.05) * frequency

        return adjustments

    def _adjust_for_false_positive(
        self,
        weights: dict[str, float],
        params: list[str],
        frequency: float,
        severity: ErrorSeverity,
    ) -> dict[str, float]:
        """针对假阳性的调整策略"""
        adjustments = {}

        # 假阳性过多通常意味着系统过于敏感
        # 降低小周期权重（它们通常更敏感），提高大周期权重
        for param in params:
            # 根据参数名称判断是否为小周期（经验判断）
            if any(tf in param.upper() for tf in ["M5", "M15", "H1"]):
                adjustments[param] = -frequency * 0.1  # 降低小周期权重
            elif any(tf in param.upper() for tf in ["H4", "D", "W"]):
                adjustments[param] = frequency * 0.08  # 提高大周期权重
            else:
                adjustments[param] = 0

        # 使用未使用参数以避免警告
        _ = (weights, severity)
        return adjustments

    def _adjust_for_false_negative(
        self,
        weights: dict[str, float],
        params: list[str],
        frequency: float,
        severity: ErrorSeverity,
    ) -> dict[str, float]:
        """针对假阴性的调整策略"""
        adjustments = {}

        # 假阴性过多通常意味着系统过于保守
        # 提高小周期权重，降低大周期权重
        for param in params:
            if any(tf in param.upper() for tf in ["M5", "M15", "H1"]):
                adjustments[param] = frequency * 0.1  # 提高小周期权重
            elif any(tf in param.upper() for tf in ["H4", "D", "W"]):
                adjustments[param] = -frequency * 0.08  # 降低大周期权重
            else:
                adjustments[param] = 0

        # 使用未使用参数以避免警告
        _ = (weights, severity)
        return adjustments

    def _general_adjustment(
        self,
        weights: dict[str, float],
        params: list[str],
        pattern: ErrorPattern,
        frequency: float,
        severity: ErrorSeverity,
    ) -> dict[str, float]:
        """通用调整策略"""
        adjustments = {}
        direction = self.get_mutation_direction(pattern)

        for param in params:
            # 根据错误模式方向调整
            adjustments[param] = direction * frequency * 0.1

        # 使用未使用参数以避免警告
        _ = (weights, severity)
        return adjustments

    def _normalize_weights(self, weights: dict[str, float]) -> dict[str, float]:
        """归一化权重使其总和为1"""
        total = sum(weights.values())
        if total > 0:
            return {k: v / total for k, v in weights.items()}
        return weights


class WeightVariator:
    """
    权重变异算法主类
    管理所有变异算子，协调权重变异过程
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化权重变异器

        Args:
            config: 配置字典，包含以下参数：
                - mutation_rate: 变异率（默认0.3）
                - crossover_rate: 交叉率（默认0.5）
                - max_mutation_percent: 最大变异百分比（默认5%）
                - population_size: 种群大小（默认10）
                - selection_pressure: 选择压力（默认2.0）
                - enable_elitism: 是否启用精英保留（默认True）
                - mutation_operators: 自定义变异算子配置
        """
        self.config = config or {}

        # 遗传算法参数
        self.mutation_rate = self.config.get("mutation_rate", 0.3)
        self.crossover_rate = self.config.get("crossover_rate", 0.5)
        self.max_mutation_percent = self.config.get("max_mutation_percent", 0.05)
        self.population_size = self.config.get("population_size", 10)
        self.selection_pressure = self.config.get("selection_pressure", 2.0)
        self.enable_elitism = self.config.get("enable_elitism", True)

        # 变异算子集合
        self.mutation_operators: dict[str, MutationOperator] = {}

        # 初始化默认变异算子
        self._initialize_default_operators()

        # 自定义变异算子
        if "mutation_operators" in self.config:
            self._initialize_custom_operators(self.config["mutation_operators"])

        # 种群存储（权重配置集合）
        self.population: list[dict[str, Any]] = []

        # 性能历史记录
        self.performance_history: list[dict[str, Any]] = []

        # 错题本引用（将在运行时设置）
        self.mistake_book: Optional[MistakeBook] = None

        # 当前最佳配置
        self.best_configuration: Optional[dict[str, Any]] = None
        self.best_performance: float = 0.0

    def _initialize_default_operators(self):
        """初始化默认变异算子"""
        # 周期权重变异算子
        period_weight_operator = WeightMutationOperator(
            target_module="period_weight_filter",
            parameters=["W", "D", "H4", "H1", "M15", "M5"],
            max_change=self.max_mutation_percent,
            weight_sum_constraint=True,
        )
        self.mutation_operators["period_weight"] = period_weight_operator

        # 阈值变异算子（通用）
        threshold_operator = ThresholdMutationOperator(
            target_module="threshold_parameters",
            parameters=[
                "confidence_threshold",
                "volume_threshold",
                "breakout_threshold",
                "confirmation_bars",
            ],
            max_change=self.max_mutation_percent,
        )
        self.mutation_operators["threshold"] = threshold_operator

        # 市场体制系数变异算子
        regime_coefficient_operator = WeightMutationOperator(
            target_module="regime_coefficients",
            parameters=[
                "TRENDING_W",
                "TRENDING_D",
                "TRENDING_H4",
                "RANGING_W",
                "RANGING_D",
                "RANGING_H4",
                "VOLATILE_W",
                "VOLATILE_D",
                "VOLATILE_H4",
            ],
            max_change=self.max_mutation_percent,
            weight_sum_constraint=False,
        )
        self.mutation_operators["regime_coefficient"] = regime_coefficient_operator

    def _initialize_custom_operators(self, operators_config: dict):
        """初始化自定义变异算子"""
        if not operators_config:
            return

        for op_name, op_config in operators_config.items():
            op_type = op_config.get("type", "weight")
            target_module = op_config.get("target_module", "unknown")
            parameters = op_config.get("parameters", [])
            max_change = op_config.get("max_change", self.max_mutation_percent)

            if op_type == "threshold":
                operator = ThresholdMutationOperator(
                    target_module=target_module,
                    parameters=parameters,
                    max_change=max_change,
                )
            elif op_type == "weight":
                weight_sum_constraint = op_config.get("weight_sum_constraint", True)
                operator = WeightMutationOperator(
                    target_module=target_module,
                    parameters=parameters,
                    max_change=max_change,
                    weight_sum_constraint=weight_sum_constraint,
                )
            else:
                # 默认为权重算子
                operator = WeightMutationOperator(
                    target_module=target_module,
                    parameters=parameters,
                    max_change=max_change,
                )

            self.mutation_operators[op_name] = operator

    def set_mistake_book(self, mistake_book: MistakeBook):
        """设置错题本引用"""
        book = mistake_book
        self.mistake_book = book

    def generate_initial_population(self, base_config: dict[str, Any]):
        """
        生成初始种群

        Args:
            base_config: 基础配置（将作为种群中的一个个体）
        """
        self.population = []

        # 将基础配置作为第一个个体
        self.population.append(
            {
                "id": 0,
                "config": copy.deepcopy(base_config),
                "performance": 0.0,
                "fitness": 0.0,
                "generation": 0,
            }
        )

        # 生成变异个体
        for i in range(1, self.population_size):
            mutated_config = self._mutate_configuration(base_config)
            self.population.append(
                {
                    "id": i,
                    "config": mutated_config,
                    "performance": 0.0,
                    "fitness": 0.0,
                    "generation": 0,
                }
            )

        # 初始化最佳配置
        self.best_configuration = copy.deepcopy(base_config)
        self.best_performance = 0.0

        return self.population

    def _mutate_configuration(self, config: dict[str, Any]) -> dict[str, Any]:
        """变异配置"""
        mutated_config = copy.deepcopy(config)

        # 如果没有错题本，使用随机变异
        if self.mistake_book is None:
            return self._random_mutate(mutated_config)

        # 从错题本获取错误模式和调整建议
        try:
            adjustments = self.mistake_book.generate_weight_adjustments()
            self.mistake_book.analyze_patterns()
        except Exception:
            # 如果错题本分析失败，回退到随机变异
            return self._random_mutate(mutated_config)

        # 如果没有调整建议，使用随机变异
        if not adjustments:
            return self._random_mutate(mutated_config)

        # 基于错题本建议进行智能变异
        for adjustment in adjustments[:3]:  # 最多处理前3个建议
            module = adjustment.get("module", "")
            adjustment.get("adjustment_type", "")
            adjustment_value = adjustment.get("adjustment_value", 0.0)
            source_patterns = adjustment.get("source_patterns", [])

            # 根据模块类型应用变异
            if "period_weight" in module.lower():
                self._apply_period_weight_mutation(
                    mutated_config, adjustment_value, source_patterns
                )
            elif "threshold" in module.lower():
                self._apply_threshold_mutation(
                    mutated_config, adjustment_value, source_patterns
                )
            elif "regime" in module.lower():
                self._apply_regime_mutation(
                    mutated_config, adjustment_value, source_patterns
                )

        return mutated_config

    def _random_mutate(self, config: dict[str, Any]) -> dict[str, Any]:
        """随机变异配置"""
        mutated = copy.deepcopy(config)

        # 随机选择变异算子
        if self.mutation_operators and random.random() < self.mutation_rate:
            op_name = random.choice(list(self.mutation_operators.keys()))
            operator = self.mutation_operators[op_name]

            # 随机选择参数进行变异
            if operator.parameters:
                param = random.choice(operator.parameters)

                # 查找配置中的参数
                param_path = self._find_parameter_path(mutated, param)
                if param_path:
                    current_value = self._get_nested_value(mutated, param_path)
                    if isinstance(current_value, (int, float)):
                        # 随机变异
                        change = random.uniform(
                            -self.max_mutation_percent, self.max_mutation_percent
                        )
                        new_value = current_value * (1 + change)
                        self._set_nested_value(mutated, param_path, new_value)

        return mutated

    def _apply_period_weight_mutation(
        self, config: dict[str, Any], adjustment_value: float, patterns: list[str]
    ):
        """应用周期权重变异"""
        # 查找周期权重配置
        if "period_weight_filter" not in config:
            return

        weights = config["period_weight_filter"].get("weights", {})
        if not weights:
            return

        # 使用权重变异算子
        operator = self.mutation_operators.get("period_weight")
        if not operator:
            return

        # 模拟错误模式（这里简化处理）
        pattern = ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT
        if patterns and "FREQUENT_FALSE_POSITIVE" in patterns:
            pattern = ErrorPattern.FREQUENT_FALSE_POSITIVE
        elif patterns and "FREQUENT_FALSE_NEGATIVE" in patterns:
            pattern = ErrorPattern.FREQUENT_FALSE_NEGATIVE

        # 执行变异
        frequency = min(abs(adjustment_value) * 10, 1.0)
        new_weights = operator.mutate(weights, pattern, frequency, ErrorSeverity.MEDIUM)
        config["period_weight_filter"]["weights"] = new_weights

    def _apply_threshold_mutation(
        self, config: dict[str, Any], adjustment_value: float, patterns: list[str]
    ):
        """应用阈值变异"""
        # 查找阈值参数
        if "threshold_parameters" not in config:
            return

        thresholds = config["threshold_parameters"]
        if not thresholds:
            return

        # 使用阈值变异算子
        operator = self.mutation_operators.get("threshold")
        if not operator:
            return

        # 模拟错误模式（根据patterns）
        pattern = ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT
        if patterns and "FREQUENT_FALSE_POSITIVE" in patterns:
            pattern = ErrorPattern.FREQUENT_FALSE_POSITIVE
        elif patterns and "FREQUENT_FALSE_NEGATIVE" in patterns:
            pattern = ErrorPattern.FREQUENT_FALSE_NEGATIVE
        elif patterns and "TIMING_ERROR" in patterns:
            pattern = ErrorPattern.TIMING_ERROR

        # 执行变异
        frequency = min(abs(adjustment_value) * 10, 1.0)
        for param_name in list(thresholds.keys()):
            if param_name in operator.parameters:
                current_value = thresholds[param_name]
                if isinstance(current_value, (int, float)):
                    new_value = operator.mutate(
                        current_value,
                        pattern,
                        frequency,
                        ErrorSeverity.MEDIUM,
                    )
                    thresholds[param_name] = new_value
        config["threshold_parameters"] = thresholds

    def _apply_regime_mutation(
        self, config: dict[str, Any], adjustment_value: float, patterns: list[str]
    ):
        """应用市场体制系数变异"""
        # 查找市场体制系数配置
        if "period_weight_filter" not in config:
            return

        regime_adjustments = config["period_weight_filter"].get(
            "regime_adjustments", {}
        )
        if not regime_adjustments:
            return

        operator = self.mutation_operators.get("regime_coefficient")
        if not operator:
            return

        # 将嵌套字典展平
        flat_weights = self._flatten_regime_weights(regime_adjustments)

        # 执行变异
        pattern = ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT
        frequency = min(abs(adjustment_value) * 10, 1.0)
        new_weights = operator.mutate(
            flat_weights, pattern, frequency, ErrorSeverity.MEDIUM
        )

        # 恢复嵌套结构
        new_regime_adjustments = self._unflatten_regime_weights(new_weights)
        config["period_weight_filter"]["regime_adjustments"] = new_regime_adjustments

        # 使用未使用参数以避免警告
        _ = patterns

    def _flatten_regime_weights(self, regime_weights: dict) -> dict[str, float]:
        """展平市场体制权重字典"""
        flat = {}
        for regime, adjustments in regime_weights.items():
            for timeframe, weight in adjustments.items():
                key = f"{regime}_{timeframe}"
                flat[key] = weight
        return flat

    def _unflatten_regime_weights(self, flat_weights: dict[str, float]) -> dict:
        """恢复市场体制权重嵌套结构"""
        regime_weights = {}
        for key, weight in flat_weights.items():
            parts = key.split("_", 1)
            if len(parts) == 2:
                regime, timeframe = parts
                if regime not in regime_weights:
                    regime_weights[regime] = {}
                regime_weights[regime][timeframe] = weight
        return regime_weights

    def _find_parameter_path(self, config: dict, param: str) -> Optional[list[str]]:
        """在配置中查找参数路径"""
        # 简化的查找逻辑，实际实现可能需要递归搜索
        if param in config:
            return [param]

        # 在嵌套字典中查找
        for key, value in config.items():
            if isinstance(value, dict):
                if param in value:
                    return [key, param]
                # 进一步递归搜索
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, dict) and param in subvalue:
                        return [key, subkey, param]

        return None

    def _get_nested_value(self, config: dict, path: list[str]) -> Any:
        """获取嵌套值"""
        current = config
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _set_nested_value(self, config: dict, path: list[str], value: Any):
        """设置嵌套值"""
        current = config
        for i, key in enumerate(path[:-1]):
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        if path:
            current[path[-1]] = value

    def evolve_population(self, performance_scores: dict[int, float]):
        """
        进化种群（选择、交叉、变异）

        Args:
            performance_scores: 个体ID到性能分数的映射
        """
        if not self.population:
            return

        # 更新种群性能
        for individual in self.population:
            individual_id = individual["id"]
            if individual_id in performance_scores:
                individual["performance"] = performance_scores[individual_id]

        # 计算适应度
        self._calculate_fitness()

        # 选择操作
        selected_indices = self._selection()

        # 交叉操作
        children = self._crossover(selected_indices)

        # 变异操作
        children = self._mutate_children(children)

        # 创建新一代种群（精英保留）
        new_population = []

        # 精英保留（保留最佳个体）
        if self.enable_elitism:
            best_individual = max(self.population, key=lambda x: x["fitness"])
            new_population.append(best_individual)

        # 添加子代
        for child in children:
            new_population.append(child)

        # 如果种群数量不足，用随机个体补充
        while len(new_population) < self.population_size:
            base_config = self.population[0]["config"]
            mutated_config = self._mutate_configuration(base_config)
            new_population.append(
                {
                    "id": len(new_population),
                    "config": mutated_config,
                    "performance": 0.0,
                    "fitness": 0.0,
                    "generation": self.population[0]["generation"] + 1,
                }
            )

        # 限制种群大小
        self.population = new_population[: self.population_size]

        # 更新最佳配置
        self._update_best_configuration()

        # 记录性能历史
        self._record_performance_history()

    def _calculate_fitness(self):
        """计算适应度（基于性能分数）"""
        # 简单线性排名适应度分配
        sorted_pop = sorted(
            self.population, key=lambda x: x["performance"], reverse=True
        )

        for i, individual in enumerate(sorted_pop):
            # 排名适应度（最佳个体适应度最高）
            rank = len(sorted_pop) - i
            individual["fitness"] = rank / len(sorted_pop)

    def _selection(self) -> list[int]:
        """选择操作（锦标赛选择）"""
        selected_indices = []

        # 锦标赛选择
        tournament_size = max(2, int(len(self.population) * 0.3))

        for _ in range(len(self.population)):
            # 随机选择锦标赛参与者
            tournament = random.sample(range(len(self.population)), tournament_size)

            # 选择适应度最高的
            tournament_fitness = [
                (idx, self.population[idx]["fitness"]) for idx in tournament
            ]
            winner = max(tournament_fitness, key=lambda x: x[1])[0]

            selected_indices.append(winner)

        return selected_indices

    def _crossover(self, selected_indices: list[int]) -> list[dict]:
        """交叉操作（单点交叉）"""
        children = []

        # 随机配对
        pairs = []
        indices = selected_indices.copy()
        random.shuffle(indices)

        for i in range(0, len(indices) - 1, 2):
            pairs.append((indices[i], indices[i + 1]))

        # 对每对进行交叉
        for parent1_idx, parent2_idx in pairs:
            if random.random() < self.crossover_rate:
                parent1 = self.population[parent1_idx]
                parent2 = self.population[parent2_idx]

                # 单点交叉
                child1_config, child2_config = self._single_point_crossover(
                    parent1["config"], parent2["config"]
                )

                # 创建子代个体
                child1 = {
                    "id": len(children),
                    "config": child1_config,
                    "performance": 0.0,
                    "fitness": 0.0,
                    "generation": parent1["generation"] + 1,
                }

                child2 = {
                    "id": len(children) + 1,
                    "config": child2_config,
                    "performance": 0.0,
                    "fitness": 0.0,
                    "generation": parent1["generation"] + 1,
                }

                children.extend([child1, child2])

        return children

    def _single_point_crossover(
        self, config1: dict, config2: dict
    ) -> tuple[dict, dict]:
        """单点交叉"""
        # 深拷贝配置
        child1 = copy.deepcopy(config1)
        child2 = copy.deepcopy(config2)

        # 随机选择交叉点（模块级别）
        modules1 = list(config1.keys())
        modules2 = list(config2.keys())

        if modules1 and modules2:
            # 找到共同模块
            common_modules = list(set(modules1) & set(modules2))

            if common_modules:
                # 随机选择交叉点
                crossover_point = (
                    random.randint(1, len(common_modules) - 1)
                    if len(common_modules) > 1
                    else 0
                )

                # 执行交叉
                for i, module in enumerate(common_modules):
                    if i >= crossover_point:
                        # 交换模块配置
                        if module in config1 and module in config2:
                            child1[module] = copy.deepcopy(config2[module])
                            child2[module] = copy.deepcopy(config1[module])

        return child1, child2

    def _mutate_children(self, children: list[dict]) -> list[dict]:
        """对子代进行变异"""
        mutated_children = []

        for child in children:
            if random.random() < self.mutation_rate:
                mutated_config = self._mutate_configuration(child["config"])
                child["config"] = mutated_config

            mutated_children.append(child)

        return mutated_children

    def _update_best_configuration(self):
        """更新最佳配置"""
        if not self.population:
            return

        best_individual = max(self.population, key=lambda x: x["performance"])

        if best_individual["performance"] > self.best_performance:
            self.best_configuration = copy.deepcopy(best_individual["config"])
            self.best_performance = best_individual["performance"]

    def _record_performance_history(self):
        """记录性能历史"""
        if not self.population:
            return

        avg_performance = np.mean([ind["performance"] for ind in self.population])
        max_performance = max(ind["performance"] for ind in self.population)
        min_performance = min(ind["performance"] for ind in self.population)

        self.performance_history.append(
            {
                "timestamp": datetime.now(),
                "generation": self.population[0]["generation"],
                "avg_performance": avg_performance,
                "max_performance": max_performance,
                "min_performance": min_performance,
                "best_performance": self.best_performance,
                "population_size": len(self.population),
            }
        )

    def get_best_configuration(self) -> Optional[dict[str, Any]]:
        """获取最佳配置"""
        return self.best_configuration

    def get_performance_report(self) -> dict[str, Any]:
        """获取性能报告"""
        if not self.performance_history:
            return {"status": "no_history"}

        latest = self.performance_history[-1]

        return {
            "status": "active",
            "generations": len(self.performance_history),
            "latest_generation": latest["generation"],
            "best_performance": self.best_performance,
            "latest_avg_performance": latest["avg_performance"],
            "population_size": latest["population_size"],
            "mutation_rate": self.mutation_rate,
            "crossover_rate": self.crossover_rate,
            "mutation_operators": list(self.mutation_operators.keys()),
        }


# 使用示例
if __name__ == "__main__":
    # 创建权重变异器
    variator = WeightVariator(
        {
            "mutation_rate": 0.3,
            "crossover_rate": 0.5,
            "max_mutation_percent": 0.05,
            "population_size": 10,
        }
    )

    # 示例基础配置
    base_config = {
        "period_weight_filter": {
            "weights": {
                "W": 0.25,
                "D": 0.20,
                "H4": 0.18,
                "H1": 0.15,
                "M15": 0.12,
                "M5": 0.10,
            },
            "regime_adjustments": {
                "TRENDING": {
                    "W": 1.2,
                    "D": 1.1,
                    "H4": 1.0,
                    "H1": 0.9,
                    "M15": 0.8,
                    "M5": 0.7,
                },
                "RANGING": {
                    "W": 0.8,
                    "D": 0.9,
                    "H4": 1.1,
                    "H1": 1.2,
                    "M15": 1.1,
                    "M5": 1.0,
                },
                "VOLATILE": {
                    "W": 0.7,
                    "D": 0.8,
                    "H4": 1.0,
                    "H1": 1.1,
                    "M15": 1.2,
                    "M5": 1.3,
                },
            },
        },
        "threshold_parameters": {
            "confidence_threshold": 0.7,
            "volume_threshold": 1.5,
            "breakout_threshold": 0.02,
        },
    }

    # 生成初始种群
    variator.generate_initial_population(base_config)


    # 模拟性能分数（在实际应用中来自WFA回测）
    performance_scores = {
        i: random.uniform(0.5, 0.9) for i in range(len(variator.population))
    }

    # 执行进化
    variator.evolve_population(performance_scores)

    # 获取性能报告
    report = variator.get_performance_report()

    # 获取最佳配置
    best_config = variator.get_best_configuration()
    if best_config:
        weights = best_config.get("period_weight_filter", {}).get("weights", {})
        for tf, w in weights.items():
            pass
