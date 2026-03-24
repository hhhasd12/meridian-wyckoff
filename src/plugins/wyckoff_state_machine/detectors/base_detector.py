"""检测器基类和共享工具函数

NodeDetector ABC 定义在 detector_registry.py 中。
本文件提供检测器常用的辅助函数。
"""

from typing import List, Optional

from src.kernel.types import StateEvidence

from ..detector_registry import NodeDetector, NodeScore, ParamSpec
from ..principles.bar_features import BarFeatures, StructureContext


def make_evidence(
    etype: str,
    value: float,
    confidence: float,
    description: str,
    weight: float = 1.0,
) -> StateEvidence:
    """创建标准化的 StateEvidence"""
    return StateEvidence(
        evidence_type=etype,
        value=value,
        confidence=confidence,
        weight=weight,
        description=description,
    )


def make_score(
    detector_name: str,
    event_name: str,
    confidence: float,
    intensity: float,
    evidences: Optional[List[StateEvidence]] = None,
    **kwargs,
) -> NodeScore:
    """创建标准化的 NodeScore"""
    return NodeScore(
        detector_name=detector_name,
        event_name=event_name,
        confidence=confidence,
        intensity=intensity,
        evidences=evidences or [],
        **kwargs,
    )


__all__ = [
    "NodeDetector",
    "NodeScore",
    "ParamSpec",
    "BarFeatures",
    "StructureContext",
    "make_evidence",
    "make_score",
]
