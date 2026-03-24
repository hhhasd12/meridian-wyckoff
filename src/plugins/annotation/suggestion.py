"""修改建议管理 — 处理AI输出的结构化修改建议

AI诊断系统产出结构化建议后，由 SuggestionManager 管理其生命周期：
- 创建：从AI输出解析为 Suggestion 数据模型
- 持久化：JSONL 格式存储建议历史
- 应用：参数修改建议可直接应用到检测器注册表
- 拒绝：不合理的建议可标记为 rejected
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParamChange:
    """参数修改建议

    Attributes:
        detector: 检测器名称 e.g. "SC"
        param: 参数名 e.g. "volume_threshold"
        current_value: 当前值
        suggested_value: 建议值
        reason: 修改理由
    """

    detector: str
    param: str
    current_value: float
    suggested_value: float
    reason: str = ""


@dataclass
class LogicChange:
    """逻辑修改建议（需要人工或coding agent执行）

    Attributes:
        detector: 检测器名称
        description: 修改描述
        file: 目标文件路径
        method: 目标方法名
        priority: 优先级 high/medium/low
    """

    detector: str
    description: str
    file: str = ""
    method: str = ""
    priority: str = "medium"


@dataclass
class Suggestion:
    """完整修改建议

    Attributes:
        id: UUID
        diagnosis: 诊断描述
        evidence: 支持证据
        param_changes: 参数修改列表
        logic_changes: 逻辑修改列表
        confidence: AI置信度 0~1
        status: pending/applied/rejected
        created_at: 创建时间 ISO格式
        applied_at: 应用时间 ISO格式（可选）
    """

    id: str
    diagnosis: str
    evidence: str
    param_changes: List[ParamChange] = field(default_factory=list)
    logic_changes: List[LogicChange] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "pending"
    created_at: str = ""
    applied_at: Optional[str] = None


class SuggestionManager:
    """修改建议管理器

    负责 AI 输出的结构化建议的完整生命周期管理：
    - 从 AI 响应创建建议
    - JSONL 持久化
    - 参数修改应用到检测器
    - 查询/筛选/拒绝建议
    """

    def __init__(self, data_dir: str = "./data/suggestions") -> None:
        self.data_dir = data_dir
        self._suggestions: List[Suggestion] = []
        os.makedirs(data_dir, exist_ok=True)
        self._load_suggestions()

    def _get_file_path(self) -> str:
        """返回 JSONL 文件路径"""
        return os.path.join(self.data_dir, "suggestions.jsonl")

    def _load_suggestions(self) -> None:
        """从 JSONL 加载建议历史"""
        path = self._get_file_path()
        if not os.path.exists(path):
            return
        self._suggestions = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    param_changes = [
                        ParamChange(**pc) for pc in data.get("param_changes", [])
                    ]
                    logic_changes = [
                        LogicChange(**lc) for lc in data.get("logic_changes", [])
                    ]
                    suggestion = Suggestion(
                        id=data["id"],
                        diagnosis=data.get("diagnosis", ""),
                        evidence=data.get("evidence", ""),
                        param_changes=param_changes,
                        logic_changes=logic_changes,
                        confidence=data.get("confidence", 0.0),
                        status=data.get("status", "pending"),
                        created_at=data.get("created_at", ""),
                        applied_at=data.get("applied_at"),
                    )
                    self._suggestions.append(suggestion)
                except Exception as e:
                    logger.warning("Failed to parse suggestion: %s", e)

    def _save_suggestions(self) -> None:
        """保存所有建议到 JSONL"""
        path = self._get_file_path()
        with open(path, "w", encoding="utf-8") as f:
            for s in self._suggestions:
                record = {
                    "id": s.id,
                    "diagnosis": s.diagnosis,
                    "evidence": s.evidence,
                    "param_changes": [asdict(pc) for pc in s.param_changes],
                    "logic_changes": [asdict(lc) for lc in s.logic_changes],
                    "confidence": s.confidence,
                    "status": s.status,
                    "created_at": s.created_at,
                    "applied_at": s.applied_at,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def create_from_ai_response(self, ai_output: Dict[str, Any]) -> Suggestion:
        """从 AI 输出创建建议

        Args:
            ai_output: AI返回的字典，包含 diagnosis/evidence/param_changes/
                       logic_changes/confidence 等字段

        Returns:
            创建的 Suggestion 实例
        """
        suggestion = Suggestion(
            id=str(uuid.uuid4()),
            diagnosis=ai_output.get("diagnosis", ""),
            evidence=ai_output.get("evidence", ""),
            confidence=ai_output.get("confidence", 0.0),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        for pc in ai_output.get("param_changes", []):
            suggestion.param_changes.append(
                ParamChange(
                    detector=pc.get("detector", ""),
                    param=pc.get("param", ""),
                    current_value=pc.get("from", pc.get("current_value", 0)),
                    suggested_value=pc.get("to", pc.get("suggested_value", 0)),
                    reason=pc.get("reason", ""),
                )
            )

        for lc in ai_output.get("logic_changes", []):
            suggestion.logic_changes.append(
                LogicChange(
                    detector=lc.get("detector", ""),
                    description=lc.get("description", ""),
                    file=lc.get("file", ""),
                    method=lc.get("method", ""),
                    priority=lc.get("priority", "medium"),
                )
            )

        self._suggestions.append(suggestion)
        self._save_suggestions()
        return suggestion

    def apply_param_changes(self, suggestion_id: str, registry: Any) -> Dict[str, Any]:
        """应用参数修改到检测器注册表

        Args:
            suggestion_id: 建议ID
            registry: DetectorRegistry 实例（通过 .get() 获取检测器）

        Returns:
            应用结果 {applied: int, skipped: int, errors: [...]}
        """
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion is None:
            return {"error": "Suggestion not found"}

        result: Dict[str, Any] = {"applied": 0, "skipped": 0, "errors": []}

        for pc in suggestion.param_changes:
            try:
                # DetectorRegistry 提供 .get(name) 方法
                detector = None
                if hasattr(registry, "get"):
                    detector = registry.get(pc.detector)
                if detector is None and hasattr(registry, "_detectors"):
                    detector = registry._detectors.get(pc.detector)

                if detector is None:
                    result["errors"].append(f"Detector {pc.detector} not found")
                    result["skipped"] += 1
                    continue

                if hasattr(detector, "set_params"):
                    detector.set_params({pc.param: pc.suggested_value})
                    result["applied"] += 1
                else:
                    result["errors"].append(f"Detector {pc.detector} has no set_params")
                    result["skipped"] += 1
            except Exception as e:
                result["errors"].append(f"{pc.detector}.{pc.param}: {str(e)}")
                result["skipped"] += 1

        suggestion.status = "applied"
        suggestion.applied_at = datetime.now(timezone.utc).isoformat()
        self._save_suggestions()
        return result

    def get_suggestion(self, suggestion_id: str) -> Optional[Suggestion]:
        """按 ID 查找建议"""
        for s in self._suggestions:
            if s.id == suggestion_id:
                return s
        return None

    def get_pending_suggestions(self) -> List[Dict[str, Any]]:
        """获取所有待处理建议"""
        return [asdict(s) for s in self._suggestions if s.status == "pending"]

    def get_all_suggestions(self) -> List[Dict[str, Any]]:
        """获取所有建议"""
        return [asdict(s) for s in self._suggestions]

    def reject_suggestion(self, suggestion_id: str) -> bool:
        """拒绝建议

        Args:
            suggestion_id: 建议ID

        Returns:
            是否成功拒绝（找到并标记）
        """
        s = self.get_suggestion(suggestion_id)
        if s is not None:
            s.status = "rejected"
            self._save_suggestions()
            return True
        return False

    def format_report(self, suggestion_id: str) -> str:
        """将建议格式化为人类可读报告

        Args:
            suggestion_id: 建议ID

        Returns:
            格式化的报告字符串
        """
        s = self.get_suggestion(suggestion_id)
        if s is None:
            return "Suggestion not found"

        lines: List[str] = []
        lines.append(f"=== 修改建议 [{s.id[:8]}] ===")
        lines.append(f"诊断: {s.diagnosis}")
        lines.append(f"证据: {s.evidence}")
        lines.append(f"置信度: {s.confidence:.1%}")
        lines.append(f"状态: {s.status}")
        lines.append("")

        if s.param_changes:
            lines.append("--- 参数修改 ---")
            for pc in s.param_changes:
                lines.append(
                    f"  [{pc.detector}] {pc.param}: "
                    f"{pc.current_value} → {pc.suggested_value}"
                )
                if pc.reason:
                    lines.append(f"    理由: {pc.reason}")
            lines.append("")

        if s.logic_changes:
            lines.append("--- 逻辑修改 ---")
            for lc in s.logic_changes:
                lines.append(f"  [{lc.detector}] ({lc.priority}) {lc.description}")
                if lc.file:
                    lines.append(f"    文件: {lc.file}")
                if lc.method:
                    lines.append(f"    方法: {lc.method}")

        return "\n".join(lines)
