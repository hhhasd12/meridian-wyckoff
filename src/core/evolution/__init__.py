"""
进化模块包

包含权重变异和遗传算法相关模块。

模块结构：
- operators.py: 遗传算子 (MutationOperator, ThresholdMutationOperator, WeightMutationOperator)
- variator.py: 变异器 (WeightVariator)

导出类：
- WeightVariator: 权重变异器
- MutationType: 变异类型枚举
- MutationOperator: 变异算子基类
- ThresholdMutationOperator: 阈值变异算子
- WeightMutationOperator: 权重变异算子
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 导入各模块
from src.kernel.types import MutationType
from .operators import (
    MutationOperator,
    ThresholdMutationOperator,
    WeightMutationOperator,
)
from src.core.weight_variator_legacy import WeightVariator

__all__ = [
    "MutationOperator",
    # 算子
    "MutationType",
    "ThresholdMutationOperator",
    "WeightMutationOperator",
    # 变异器
    "WeightVariator",
]
