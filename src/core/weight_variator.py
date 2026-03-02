"""
权重变异器向后兼容模块

此模块提供向后兼容导入。
"""

# 导入所有从原始文件需要的类
from src.core.weight_variator_legacy import (
    MutationOperator,
    MutationType,
    ThresholdMutationOperator,
    WeightMutationOperator,
    WeightVariator,
)

# 导出
__all__ = [
    "MutationOperator",
    "MutationType",
    "ThresholdMutationOperator",
    "WeightMutationOperator",
    "WeightVariator",
]
