"""标注数据管理插件 — 存储用户对威科夫事件/水平线/结构的标注

使用 JSONL 文件存储标注数据，按 symbol+timeframe 分文件。
路径格式: data/annotations/{symbol_safe}_{timeframe}.jsonl
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

if TYPE_CHECKING:
    from .suggestion import SuggestionManager

logger = logging.getLogger(__name__)


@dataclass
class WyckoffAnnotation:
    """威科夫标注数据模型

    支持三种标注类型:
    - event: 事件标注 (SC/AR/SPRING 等)
    - level: 水平线标注 (SC_LOW/AR_HIGH/CREEK 等)
    - structure: 结构标注 (ACCUMULATION/DISTRIBUTION)
    """

    id: str  # UUID
    type: str  # 'event' | 'level' | 'structure'
    symbol: str  # 'ETH/USDT'
    timeframe: str  # 'H4'
    # 事件标注字段
    event_type: Optional[str] = None  # "SC" | "AR" | "SPRING" 等
    start_time: Optional[int] = None  # 时间戳(毫秒)
    end_time: Optional[int] = None  # 时间戳(毫秒)
    start_bar_index: Optional[int] = None  # K线序号
    end_bar_index: Optional[int] = None  # K线序号
    # 水平线标注字段
    price: Optional[float] = None  # 水平线价格
    level_label: Optional[str] = None  # "SC_LOW" | "AR_HIGH" | "CREEK"
    # 结构标注字段
    structure_type: Optional[str] = None  # "ACCUMULATION" | "DISTRIBUTION"
    # 通用字段
    confidence: float = 0.8  # 用户标注置信度
    notes: str = ""  # 用户备注
    created_at: str = ""  # ISO时间戳


class AnnotationPlugin(BasePlugin):
    """标注数据管理插件

    提供 CRUD 操作管理威科夫标注数据。
    标注按 symbol+timeframe 分文件存储为 JSONL 格式。
    T5.3: 新增自动对比功能 — 标注数量≥5时自动触发匹配分析。
    """

    def __init__(self, name: str = "annotation") -> None:
        super().__init__(name=name)
        self._data_dir: Optional[Path] = None
        self._annotation_count: int = 0
        self._auto_compare_result: Optional[Dict[str, Any]] = None
        self._min_annotations_for_compare: int = 5

    def on_load(self) -> None:
        """加载插件：创建数据目录"""
        config = self._config or {}
        data_dir = config.get("data_dir", "./data/annotations")
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("标注插件已加载，数据目录: %s", self._data_dir)

    def on_unload(self) -> None:
        """卸载插件：清理"""
        logger.info(
            "标注插件已卸载，共处理 %d 个标注",
            self._annotation_count,
        )

    def _get_file_path(self, symbol: str, timeframe: str) -> Path:
        """返回标注 JSONL 文件路径

        Args:
            symbol: 交易对 (如 'ETH/USDT')
            timeframe: 时间框架 (如 'H4')

        Returns:
            JSONL 文件路径
        """
        symbol_safe = symbol.replace("/", "_")
        assert self._data_dir is not None
        return self._data_dir / f"{symbol_safe}_{timeframe}.jsonl"

    def create_annotation(self, annotation_data: Dict[str, Any]) -> WyckoffAnnotation:
        """创建标注

        Args:
            annotation_data: 标注数据字典，必须包含 type/symbol/timeframe

        Returns:
            创建的 WyckoffAnnotation 实例

        Raises:
            ValueError: 缺少必需字段
        """
        required = ["type", "symbol", "timeframe"]
        for key in required:
            if key not in annotation_data:
                raise ValueError(f"缺少必需字段: {key}")

        # 生成 id 和 created_at
        annotation_data["id"] = str(uuid.uuid4())
        annotation_data["created_at"] = datetime.now(timezone.utc).isoformat()

        # 构建数据类（只传 WyckoffAnnotation 接受的字段）
        valid_fields = {f.name for f in WyckoffAnnotation.__dataclass_fields__.values()}
        filtered = {k: v for k, v in annotation_data.items() if k in valid_fields}
        annotation = WyckoffAnnotation(**filtered)

        # 追加写入 JSONL
        file_path = self._get_file_path(annotation.symbol, annotation.timeframe)
        with open(file_path, "a", encoding="utf-8") as f:
            line = json.dumps(asdict(annotation), ensure_ascii=False)
            f.write(line + "\n")

        self._annotation_count += 1

        # 发布事件
        self.emit_event("annotation.created", asdict(annotation))

        logger.info(
            "创建标注: id=%s type=%s symbol=%s",
            annotation.id,
            annotation.type,
            annotation.symbol,
        )

        # T5.3: 增量标注自动对比 — 达到最小标注量时自动触发匹配分析
        self._try_auto_compare(annotation.symbol, annotation.timeframe)

        return annotation

    def get_annotations(self, symbol: str, timeframe: str) -> List[Dict[str, Any]]:
        """获取指定 symbol+timeframe 的所有标注

        Args:
            symbol: 交易对
            timeframe: 时间框架

        Returns:
            标注数据字典列表
        """
        file_path = self._get_file_path(symbol, timeframe)
        if not file_path.exists():
            return []

        annotations: List[Dict[str, Any]] = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        annotations.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(
                            "跳过无效 JSONL 行: %s",
                            line[:80],
                        )
        return annotations

    def delete_annotation(
        self,
        annotation_id: str,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """删除标注

        读取全部→过滤→重写文件。

        Args:
            annotation_id: 标注 UUID
            symbol: 交易对
            timeframe: 时间框架

        Returns:
            是否成功删除（找到并移除）
        """
        file_path = self._get_file_path(symbol, timeframe)
        if not file_path.exists():
            return False

        annotations = self.get_annotations(symbol, timeframe)
        original_count = len(annotations)
        filtered = [a for a in annotations if a.get("id") != annotation_id]

        if len(filtered) == original_count:
            return False  # 未找到

        # 重写文件
        with open(file_path, "w", encoding="utf-8") as f:
            for a in filtered:
                line = json.dumps(a, ensure_ascii=False)
                f.write(line + "\n")

        # 发布事件
        self.emit_event(
            "annotation.deleted",
            {
                "annotation_id": annotation_id,
                "symbol": symbol,
                "timeframe": timeframe,
            },
        )

        logger.info("删除标注: id=%s", annotation_id)
        return True

    def get_annotation_count(self) -> Dict[str, int]:
        """按 symbol_timeframe 返回标注计数

        Returns:
            字典 {filename: count}
        """
        assert self._data_dir is not None
        counts: Dict[str, int] = {}
        if not self._data_dir.exists():
            return counts

        for f in self._data_dir.glob("*.jsonl"):
            count = 0
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        count += 1
            counts[f.stem] = count
        return counts

    def compare_with_detections(
        self,
        symbol: str,
        timeframe: str,
        transition_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """对比标注和状态机检测结果

        Args:
            symbol: 交易对
            timeframe: 时间框架
            transition_history: 状态机转换历史

        Returns:
            匹配报告字典
        """
        from .matcher import AnnotationMatcher

        annotations = self.get_annotations(symbol, timeframe)
        matcher = AnnotationMatcher(tolerance_bars=3)
        report = matcher.match(annotations, transition_history)
        return {
            "total_annotations": report.total_annotations,
            "total_detections": report.total_detections,
            "matched": report.matched,
            "missed": report.missed,
            "false_positives": report.false_positives,
            "type_mismatches": report.type_mismatches,
            "match_score": report.match_score,
            "results": [
                {
                    "type": r.type,
                    "details": r.details,
                    "annotation": r.annotation,
                    "detection": r.detection,
                }
                for r in report.results
            ],
        }

    # ── 修改建议管理 ──

    def get_suggestion_manager(self) -> "SuggestionManager":
        """获取或创建修改建议管理器（懒加载）"""
        if not hasattr(self, "_suggestion_manager"):
            from .suggestion import SuggestionManager

            assert self._data_dir is not None
            data_dir = str(self._data_dir / "suggestions")
            self._suggestion_manager = SuggestionManager(data_dir)
        return self._suggestion_manager

    def create_suggestion(self, ai_output: Dict[str, Any]) -> Dict[str, Any]:
        """从 AI 输出创建修改建议

        Args:
            ai_output: AI 返回的结构化诊断结果

        Returns:
            创建的建议数据字典
        """
        mgr = self.get_suggestion_manager()
        s = mgr.create_from_ai_response(ai_output)
        return asdict(s)

    def get_suggestions(self, status: str = "") -> List[Dict[str, Any]]:
        """获取修改建议列表

        Args:
            status: 按状态筛选（pending/applied/rejected），空字符串返回全部

        Returns:
            建议数据字典列表
        """
        mgr = self.get_suggestion_manager()
        if status:
            return [s for s in mgr.get_all_suggestions() if s["status"] == status]
        return mgr.get_all_suggestions()

    # ── 诊断顾问集成 ──

    def get_diagnosis_advisor(self) -> Any:
        """获取诊断顾问实例（惰性初始化）

        Returns:
            DiagnosisAdvisor 实例
        """
        if not hasattr(self, "_diagnosis_advisor"):
            from .diagnosis import DiagnosisAdvisor

            self._diagnosis_advisor = DiagnosisAdvisor(self._config)
        return self._diagnosis_advisor

    def diagnose_chat(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """诊断对话 — AI 分析标注与检测差异

        Args:
            message: 用户消息
            context: 诊断上下文

        Returns:
            结构化诊断结果字典
        """
        advisor = self.get_diagnosis_advisor()
        response = advisor.diagnose_chat(message, context)
        return {
            "text": response.text,
            "suggested_params": response.suggested_params,
            "highlighted_bars": response.highlighted_bars,
            "follow_up_question": response.follow_up_question,
            "confidence": response.confidence,
        }

    # ── T5.3: 增量标注自动对比 ──

    def _try_auto_compare(self, symbol: str, timeframe: str) -> None:
        """T5.3: 标注达到最小数量时自动触发对比分析

        对比结果缓存在 _auto_compare_result 中供前端查询。
        只在 event 类型标注≥5个时触发。

        Args:
            symbol: 交易对
            timeframe: 时间框架
        """
        try:
            annotations = self.get_annotations(symbol, timeframe)
            event_anns = [a for a in annotations if a.get("type") == "event"]
            if len(event_anns) < self._min_annotations_for_compare:
                return

            # 获取状态机转换历史（如果可用）
            transition_history = self._get_transition_history(symbol, timeframe)
            if not transition_history:
                return

            from .matcher import AnnotationMatcher

            matcher = AnnotationMatcher(tolerance_bars=3)
            report = matcher.match(event_anns, transition_history)

            self._auto_compare_result = {
                "symbol": symbol,
                "timeframe": timeframe,
                "total_annotations": report.total_annotations,
                "total_detections": report.total_detections,
                "matched": report.matched,
                "missed": report.missed,
                "false_positives": report.false_positives,
                "type_mismatches": report.type_mismatches,
                "match_score": report.match_score,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                "自动对比完成: %s/%s match_score=%.3f (%d标注/%d检测)",
                symbol,
                timeframe,
                report.match_score,
                report.total_annotations,
                report.total_detections,
            )
        except Exception as e:
            logger.debug("自动对比失败: %s", e)

    def _get_transition_history(
        self, symbol: str, timeframe: str
    ) -> List[Dict[str, Any]]:
        """获取状态机转换历史

        尝试从 wyckoff_engine 插件获取当前转换历史。
        如果插件不可用则返回空列表。

        Args:
            symbol: 交易对
            timeframe: 时间框架

        Returns:
            转换历史列表
        """
        try:
            if self._plugin_manager is None:
                return []
            engine = self._plugin_manager.get_plugin("wyckoff_engine")
            if engine is None:
                return []
            if hasattr(engine, "_engine") and engine._engine is not None:
                sm = getattr(engine._engine, "_state_machine", None)
                if sm is not None and hasattr(sm, "_transition_history"):
                    return list(sm._transition_history)
        except Exception:
            pass
        return []

    def get_auto_compare_result(self) -> Optional[Dict[str, Any]]:
        """T5.3: 返回最新的自动对比结果

        Returns:
            对比结果字典，无结果时返回 None
        """
        return self._auto_compare_result

    # ── 对话历史持久化 ──

    def save_chat_message(self, message: Dict[str, Any]) -> None:
        """保存对话消息到JSONL文件"""
        assert self._data_dir is not None
        chat_dir = self._data_dir / "chat_history"
        chat_dir.mkdir(parents=True, exist_ok=True)
        path = chat_dir / "conversation.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")

    def get_chat_history(self) -> List[Dict[str, Any]]:
        """获取对话历史"""
        assert self._data_dir is not None
        path = self._data_dir / "chat_history" / "conversation.jsonl"
        if not path.exists():
            return []
        messages: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except Exception:
                        pass
        return messages

    def clear_chat_history(self) -> bool:
        """清空对话历史"""
        assert self._data_dir is not None
        path = self._data_dir / "chat_history" / "conversation.jsonl"
        if path.exists():
            path.unlink()
        # 同时重置DiagnosisAdvisor的对话上下文
        if hasattr(self, "_diagnosis_advisor"):
            self._diagnosis_advisor.reset_conversation()
        return True

    # ── 检测器知识库 ──

    def get_knowledge_base(self) -> Any:
        """获取检测器知识库（惰性初始化）"""
        if not hasattr(self, "_knowledge_base"):
            from .knowledge import DetectorKnowledgeBase

            assert self._data_dir is not None
            db_path = str(self._data_dir / "detector_knowledge.db")
            self._knowledge_base = DetectorKnowledgeBase(db_path)
        return self._knowledge_base

    def add_knowledge_rule(
        self,
        detector_name: str,
        rule_text: str,
        source: str = "",
        confidence: float = 0.8,
    ) -> Dict[str, Any]:
        """添加检测器知识规则"""
        kb = self.get_knowledge_base()
        rule = kb.add_rule(detector_name, rule_text, source, confidence)
        from dataclasses import asdict as _asdict

        return _asdict(rule)

    def search_knowledge(
        self,
        query: str,
        detector_name: str = "",
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """搜索检测器知识"""
        kb = self.get_knowledge_base()
        rules = kb.search_rules(query, detector_name, k)
        from dataclasses import asdict as _asdict

        return [_asdict(r) for r in rules]

    def get_knowledge_stats(self) -> Dict[str, Any]:
        """获取知识库统计"""
        kb = self.get_knowledge_base()
        return kb.get_stats()

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        if self._data_dir is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="标注插件未初始化",
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="标注插件正常运行",
            details={
                "data_dir": str(self._data_dir),
                "annotation_count": self._annotation_count,
            },
        )
