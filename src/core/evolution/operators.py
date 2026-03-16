"""
进化模块 - 遗传算子

包含变异算子基类和具体实现。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 详细的中文错误上下文记录
"""

import logging
import random
from datetime import datetime
from typing import Any

from src.kernel.types import MutationType

logger = logging.getLogger(__name__)


def _setup_error_handler():
    """设置错误处理装饰器"""
    try:
        from src.utils.error_handler import error_handler

        return error_handler
    except ImportError:

        def error_handler_decorator(**kwargs):
            def decorator(func):
                return func

            return decorator

        return error_handler_decorator


error_handler = _setup_error_handler()


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

    @error_handler(logger=logger, reraise=False, default_return=None)
    def mutate(
        self,
        value: Any,
        pattern: Any,
        frequency: float,
        severity: Any = None,
    ) -> Any:
        """
        执行变异操作

        Args:
            value: 当前参数值
            pattern: 错误模式
            frequency: 错误频率
            severity: 错误严重程度

        Returns:
            变异后的参数值
        """
        # 基类方法，子类必须实现
        raise NotImplementedError("子类必须实现mutate方法")

    @error_handler(logger=logger, reraise=False, default_return=0.0)
    def get_mutation_direction(self, pattern: Any) -> float:
        """
        根据错误模式获取变异方向

        Returns:
            变异方向：正数表示增加，负数表示减少，0表示中性
        """
        # 尝试导入ErrorPattern
        try:
            from src.core.mistake_book import ErrorPattern
        except ImportError:
            # 如果无法导入，返回默认方向
            return 0.0

        direction = 0.0

        if pattern == ErrorPattern.FREQUENT_FALSE_POSITIVE:
            direction = 1.0
        elif pattern == ErrorPattern.FREQUENT_FALSE_NEGATIVE:
            direction = -1.0
        elif pattern == ErrorPattern.TIMING_ERROR:
            direction = 0.5
        elif pattern == ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT:
            direction = 0.3
        else:
            direction = random.choice([-0.2, 0.2])

        return direction

    @error_handler(logger=logger, reraise=False, default_return=0.0)
    def calculate_mutation_magnitude(
        self, frequency: float, severity: Any = None
    ) -> float:
        """
        计算变异幅度

        Args:
            frequency: 错误频率
            severity: 错误严重程度

        Returns:
            变异幅度
        """
        # 尝试导入ErrorSeverity
        try:
            from src.core.mistake_book import ErrorSeverity
        except ImportError:
            severity = None

        base_magnitude = frequency * self.max_change

        if severity is not None:
            severity_multipliers = {
                ErrorSeverity.LOW: 0.5,
                ErrorSeverity.MEDIUM: 1.0,
                ErrorSeverity.HIGH: 1.5,
                ErrorSeverity.CRITICAL: 2.0,
            }
            multiplier = severity_multipliers.get(severity, 1.0)
            base_magnitude *= multiplier

        return min(base_magnitude, self.max_change)

    @error_handler(logger=logger, reraise=False)
    def record_mutation(
        self, parameter: str, old_value: float, new_value: float, pattern: Any
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
                "pattern": pattern.value if hasattr(pattern, "value") else str(pattern),
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

    @error_handler(logger=logger, reraise=False, default_return=None)
    def mutate(
        self,
        value: Any,
        pattern: Any,
        frequency: float,
        severity: Any = None,
    ) -> Any:
        """执行阈值变异"""
        if not isinstance(value, (int, float)):
            return value

        direction = self.get_mutation_direction(pattern)
        magnitude = self.calculate_mutation_magnitude(frequency, severity)

        # 执行变异
        new_value = value * (1 + direction * magnitude)
        self.record_mutation(
            self.parameters[0] if self.parameters else "unknown",
            float(value),
            float(new_value),
            pattern,
        )

        return new_value


class WeightMutationOperator(MutationOperator):
    """
    权重变异算子
    专门用于调整权重参数（如周期权重）
    """

    def __init__(
        self, target_module: str, parameters: list[str], max_change: float = 0.05
    ):
        super().__init__(
            MutationType.WEIGHT_ADJUSTMENT, target_module, parameters, max_change
        )

    @error_handler(logger=logger, reraise=False, default_return=None)
    def mutate(
        self,
        value: Any,
        pattern: Any,
        frequency: float,
        severity: Any = None,
    ) -> Any:
        """执行权重变异"""
        direction = self.get_mutation_direction(pattern)
        magnitude = self.calculate_mutation_magnitude(frequency, severity)

        if isinstance(value, dict):
            # 如果是权重字典，逐个调整
            result = {}
            for k, v in value.items():
                if isinstance(v, (int, float)):
                    new_v = v * (1 + direction * magnitude * random.uniform(0.5, 1.5))
                    result[k] = max(0.0, min(1.0, new_v))
                else:
                    result[k] = v
            return result
        if isinstance(value, (int, float)):
            new_value = value * (1 + direction * magnitude)
            return max(0.0, min(1.0, new_value))

        return value


# 导出
__all__ = [
    "MutationOperator",
    "MutationType",
    "ThresholdMutationOperator",
    "WeightMutationOperator",
]
