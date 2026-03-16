"""
威科夫状态机 - 证据链管理模块

包含 EvidenceChainManager 类，用于管理状态证据链。

设计原则：
1. 证据收集与加权
2. 证据链构建与验证
3. 证据强度计算
4. 证据链可视化
"""

import logging
from typing import Any, Callable

import numpy as np

from src.kernel.types import StateEvidence

logger = logging.getLogger(__name__)


class EvidenceChainManager:
    """
    状态证据链管理器

    功能：
    1. 证据收集与加权
    2. 证据链构建与验证
    3. 证据强度计算
    4. 证据链可视化
    """

    def __init__(self):
        self.evidence_chains: dict[str, list[StateEvidence]] = {}
        self.evidence_weights: dict[str, float] = {}
        self.chain_validation_rules: dict[str, Callable] = {}

        # 初始化默认证据权重
        self._initialize_default_weights()

    def _initialize_default_weights(self):
        """初始化默认证据权重"""
        self.evidence_weights = {
            "volume_ratio": 0.25,  # 成交量比率
            "pin_strength": 0.20,  # 针强度
            "effort_result_score": 0.15,  # 努力结果评分
            "bounce_percent": 0.15,  # 反弹百分比
            "volume_contraction": 0.10,  # 成交量收缩
            "retracement_depth": 0.10,  # 回撤深度
            "spring_strength": 0.05,  # 弹簧强度
        }

    def add_evidence(self, state_name: str, evidence: StateEvidence):
        """为状态添加证据"""
        if state_name not in self.evidence_chains:
            self.evidence_chains[state_name] = []

        self.evidence_chains[state_name].append(evidence)

        # 限制证据链长度
        if len(self.evidence_chains[state_name]) > 20:
            self.evidence_chains[state_name] = self.evidence_chains[state_name][-20:]

    def calculate_state_confidence(self, state_name: str) -> float:
        """计算状态置信度"""
        if state_name not in self.evidence_chains:
            return 0.0

        evidences = self.evidence_chains[state_name]
        if not evidences:
            return 0.0

        # 加权平均计算置信度
        total_weight = 0.0
        weighted_sum = 0.0

        for evidence in evidences[-5:]:  # 只考虑最近5个证据
            weight = self.evidence_weights.get(evidence.evidence_type, 0.1)
            weighted_sum += evidence.confidence * evidence.weight * weight
            total_weight += weight

        confidence = weighted_sum / total_weight if total_weight > 0 else 0.0

        return min(1.0, max(0.0, confidence))

    def validate_evidence_chain(self, state_name: str) -> dict[str, Any]:
        """验证证据链有效性"""
        if state_name not in self.evidence_chains:
            return {"valid": False, "reason": "无证据链"}

        evidences = self.evidence_chains[state_name]
        if len(evidences) < 3:
            return {"valid": False, "reason": "证据不足"}

        # 检查证据一致性
        recent_confidences = [e.confidence for e in evidences[-3:]]
        avg_confidence = np.mean(recent_confidences)
        confidence_std = np.std(recent_confidences)

        # 检查证据类型分布
        evidence_types = [e.evidence_type for e in evidences]
        unique_types = set(evidence_types)

        return {
            "valid": avg_confidence > 0.6 and confidence_std < 0.3,
            "avg_confidence": avg_confidence,
            "confidence_std": confidence_std,
            "evidence_count": len(evidences),
            "unique_evidence_types": len(unique_types),
            "recent_evidences": [
                {"type": e.evidence_type, "confidence": e.confidence, "value": e.value}
                for e in evidences[-3:]
            ],
        }


    def get_evidence_report(self, state_name: str) -> dict[str, Any]:
        """获取证据报告"""
        if state_name not in self.evidence_chains:
            return {"state": state_name, "evidence_count": 0, "evidences": []}

        evidences = self.evidence_chains[state_name]

        # 按证据类型分组
        evidence_by_type = {}
        for evidence in evidences:
            if evidence.evidence_type not in evidence_by_type:
                evidence_by_type[evidence.evidence_type] = []
            evidence_by_type[evidence.evidence_type].append(evidence)

        # 计算各类型证据的平均置信度
        type_confidence = {}
        for evidence_type, type_evidences in evidence_by_type.items():
            avg_confidence = np.mean([e.confidence for e in type_evidences])
            type_confidence[evidence_type] = avg_confidence

        return {
            "state": state_name,
            "evidence_count": len(evidences),
            "unique_evidence_types": len(evidence_by_type),
            "overall_confidence": self.calculate_state_confidence(state_name),
            "type_confidence": type_confidence,
            "recent_evidences": [
                {
                    "type": e.evidence_type,
                    "confidence": e.confidence,
                    "value": e.value,
                    "description": e.description,
                }
                for e in evidences[-5:]
            ],
        }

