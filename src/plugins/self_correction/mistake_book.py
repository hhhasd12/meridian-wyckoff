"""
错题本机制模块
记录系统状态误判、错误决策，分析错误模式，为权重变异算法提供输入

设计原则：
1. 全面记录：记录所有关键错误事件，包含完整上下文
2. 智能分类：错误类型自动分类，识别错误模式
3. 模式分析：计算错误频率、关联性、时间分布
4. 权重建议：生成针对性的权重调整建议
5. 防过拟合：WFA验证，避免对噪声过度拟合

错误类型：
1. 状态误判（威科夫状态识别错误）
2. 冲突解决错误（多周期融合决策错误）
3. 入场验证错误（微观入场时机错误）
4. 突破验证错误（SFP欺骗识别错误）
5. 市场体制误判（趋势/盘整判断错误）
6. 数据质量错误（异常数据处理错误）
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import numpy as np


class MistakeType(Enum):
    """错误类型枚举"""

    STATE_MISJUDGMENT = "STATE_MISJUDGMENT"  # 状态误判（威科夫状态识别错误）
    CONFLICT_RESOLUTION_ERROR = "CONFLICT_RESOLUTION_ERROR"  # 冲突解决错误
    ENTRY_VALIDATION_ERROR = "ENTRY_VALIDATION_ERROR"  # 入场验证错误
    BREAKOUT_VALIDATION_ERROR = "BREAKOUT_VALIDATION_ERROR"  # 突破验证错误
    MARKET_REGIME_ERROR = "MARKET_REGIME_ERROR"  # 市场体制误判
    DATA_QUALITY_ERROR = "DATA_QUALITY_ERROR"  # 数据质量错误
    WEIGHT_ASSIGNMENT_ERROR = "WEIGHT_ASSIGNMENT_ERROR"  # 权重分配错误
    TREND_RECOGNITION_ERROR = "TREND_RECOGNITION_ERROR"  # 趋势识别错误
    SUPPORT_RESISTANCE_ERROR = "SUPPORT_RESISTANCE_ERROR"  # 支撑阻力识别错误
    VOLUME_ANALYSIS_ERROR = "VOLUME_ANALYSIS_ERROR"  # 成交量分析错误


class ErrorSeverity(Enum):
    """错误严重程度"""

    LOW = "LOW"  # 低严重度：轻微错误，不影响核心决策
    MEDIUM = "MEDIUM"  # 中等严重度：影响部分决策
    HIGH = "HIGH"  # 高严重度：核心决策错误
    CRITICAL = "CRITICAL"  # 关键严重度：导致重大损失


class ErrorPattern(Enum):
    """错误模式枚举"""

    FREQUENT_FALSE_POSITIVE = "FREQUENT_FALSE_POSITIVE"  # 频繁误报（假阳性）
    FREQUENT_FALSE_NEGATIVE = "FREQUENT_FALSE_NEGATIVE"  # 频繁漏报（假阴性）
    TIMING_ERROR = "TIMING_ERROR"  # 时机错误（过早/过晚）
    MAGNITUDE_ERROR = "MAGNITUDE_ERROR"  # 幅度错误（过度反应/反应不足）
    CONTEXT_SENSITIVITY_ERROR = "CONTEXT_SENSITIVITY_ERROR"  # 上下文敏感性错误
    CORRELATION_ERROR = "CORRELATION_ERROR"  # 相关性误判
    VOLATILITY_ADAPTATION_ERROR = "VOLATILITY_ADAPTATION_ERROR"  # 波动率适应错误
    MULTI_TIMEFRAME_MISALIGNMENT = "MULTI_TIMEFRAME_MISALIGNMENT"  # 多周期错配


class MistakeRecord:
    """
    错误记录类
    记录单个错误事件的完整信息
    """

    def __init__(
        self,
        mistake_type: MistakeType,
        severity: ErrorSeverity,
        timestamp: datetime,
        context: dict[str, Any],
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        confidence_before: float = 0.0,
        confidence_after: float = 0.0,
        impact_score: float = 0.0,
        module_name: str = "unknown",
        timeframe: str = "unknown",
        patterns: Optional[list[ErrorPattern]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """
        初始化错误记录

        Args:
            mistake_type: 错误类型
            severity: 错误严重程度
            timestamp: 错误发生时间
            context: 错误发生时的完整上下文
            expected: 期望结果（如正确状态）
            actual: 实际结果（如错误状态）
            confidence_before: 决策前置信度
            confidence_after: 决策后置信度（如知道正确答案后）
            impact_score: 影响分数（0-1，基于潜在损失或机会成本）
            module_name: 出错的模块名称
            timeframe: 时间框架
            patterns: 识别到的错误模式列表
            metadata: 额外元数据
        """
        self.mistake_type = mistake_type
        self.severity = severity
        self.timestamp = timestamp
        self.context = context
        self.expected = expected
        self.actual = actual
        self.confidence_before = confidence_before
        self.confidence_after = confidence_after
        self.impact_score = impact_score
        self.module_name = module_name
        self.timeframe = timeframe
        self.patterns = patterns or []
        self.metadata = metadata or {}

        # 自动生成错误ID
        self.error_id = self._generate_error_id()

        # 计算学习优先级（基于严重程度、影响分数、置信度差异）
        self.learning_priority = self._calculate_learning_priority()

        # 标记是否已用于学习
        self.used_for_learning = False
        self.learning_timestamp = None
        self.learning_outcome = None

    def _generate_error_id(self) -> str:
        """生成唯一错误ID"""
        # 修复：时间戳可能是int64类型，需要转换为datetime对象
        if isinstance(self.timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime
            timestamp_dt = datetime.fromtimestamp(float(self.timestamp) / 1000.0)
            timestamp_str = timestamp_dt.strftime("%Y%m%d_%H%M%S_%f")
        else:
            # 如果是datetime对象，直接格式化
            timestamp_str = self.timestamp.strftime("%Y%m%d_%H%M%S_%f")

        type_str = self.mistake_type.value.replace("_", "-")
        return f"{timestamp_str}_{type_str}_{self.module_name}"

    def _calculate_learning_priority(self) -> float:
        """计算学习优先级分数（0-1）"""
        # 基础分数：严重程度权重
        severity_weights = {
            ErrorSeverity.LOW: 0.2,
            ErrorSeverity.MEDIUM: 0.5,
            ErrorSeverity.HIGH: 0.8,
            ErrorSeverity.CRITICAL: 1.0,
        }

        severity_score = severity_weights.get(self.severity, 0.5)

        # 置信度差异分数（差异越大，优先级越高）
        confidence_diff = abs(self.confidence_before - self.confidence_after)
        confidence_score = min(confidence_diff, 1.0)

        # 影响分数
        impact_score = self.impact_score

        # 综合优先级（加权平均）
        weights = [0.4, 0.3, 0.3]  # 严重程度 > 置信度差异 > 影响
        scores = [severity_score, confidence_score, impact_score]

        priority = sum(w * s for w, s in zip(weights, scores))
        return min(max(priority, 0.0), 1.0)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_id": self.error_id,
            "mistake_type": self.mistake_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "module_name": self.module_name,
            "timeframe": self.timeframe,
            "expected": self.expected,
            "actual": self.actual,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "impact_score": self.impact_score,
            "learning_priority": self.learning_priority,
            "patterns": [p.value for p in self.patterns],
            "used_for_learning": self.used_for_learning,
            "learning_timestamp": self.learning_timestamp.isoformat()
            if self.learning_timestamp
            else None,
            "learning_outcome": self.learning_outcome,
            "context_summary": self._summarize_context(),
        }

    def _summarize_context(self) -> dict[str, Any]:
        """生成上下文摘要"""
        summary = {}

        # 提取关键上下文信息
        for key in [
            "market_regime",
            "price_action",
            "volume_pattern",
            "trend_direction",
        ]:
            if key in self.context:
                summary[key] = self.context[key]

        # 限制上下文大小
        if len(self.context) > 10:
            summary["context_keys"] = list(self.context.keys())[:10]
            summary["context_size"] = len(self.context)
        else:
            summary.update(self.context)

        return summary

    def mark_as_learned(self, outcome: str = "processed") -> None:
        """标记为已学习"""
        self.used_for_learning = True
        self.learning_timestamp = datetime.now()
        self.learning_outcome = outcome

    def add_pattern(self, pattern: ErrorPattern) -> None:
        """添加错误模式"""
        if pattern not in self.patterns:
            self.patterns.append(pattern)


class MistakeBook:
    """
    错题本管理器
    管理所有错误记录，支持错误分析、模式识别、权重建议生成
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化错题本

        Args:
            config: 配置字典
        """
        self.config = config or {}

        # 错误记录存储
        self.records: dict[str, MistakeRecord] = {}  # error_id -> MistakeRecord
        self.record_history: list[MistakeRecord] = []  # 历史记录（按时间排序）

        # 分析缓存
        self._pattern_cache = None
        self._statistics_cache = None
        self._last_analysis_time = None

        # 配置参数
        self.max_records = self.config.get("max_records", 10000)
        self.auto_cleanup_days = self.config.get("auto_cleanup_days", 30)
        self.min_learning_priority = self.config.get("min_learning_priority", 0.3)
        # BUG-5 修复：从 0.7 降低到 0.15，让模式可以从少量样本中识别
        self.pattern_detection_threshold = self.config.get(
            "pattern_detection_threshold", 0.15
        )

        # 权重调整建议缓存
        self.weight_adjustment_suggestions = []

        # 性能统计
        self.stats = {
            "total_errors": 0,
            "errors_by_type": defaultdict(int),
            "errors_by_severity": defaultdict(int),
            "errors_by_module": defaultdict(int),
            "learning_rate": 0.0,
        }

    def record_mistake(
        self,
        mistake_type: MistakeType,
        severity: ErrorSeverity,
        context: dict[str, Any],
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        confidence_before: float = 0.0,
        confidence_after: float = 0.0,
        impact_score: float = 0.0,
        module_name: str = "unknown",
        timeframe: str = "unknown",
        patterns: Optional[list[ErrorPattern]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        记录一个新错误

        Returns:
            错误ID
        """
        # 创建错误记录
        record = MistakeRecord(
            mistake_type=mistake_type,
            severity=severity,
            timestamp=datetime.now(),
            context=context,
            expected=expected,
            actual=actual,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            impact_score=impact_score,
            module_name=module_name,
            timeframe=timeframe,
            patterns=patterns,
            metadata=metadata,
        )

        # 存储记录
        self.records[record.error_id] = record
        self.record_history.append(record)

        # 更新统计信息
        self._update_statistics(record)

        # 自动清理旧记录
        if len(self.record_history) > self.max_records:
            self._auto_cleanup()

        # 清空分析缓存（因为数据已变更）
        self._pattern_cache = None
        self._statistics_cache = None

        return record.error_id

    def record_trade_mistake(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        hold_bars: int = 0,
        exit_reason: str = "unknown",
        entry_state: str = "unknown",
        timeframe: str = "H4",
    ) -> str:
        """简化接口 — 从回测交易直接记录亏损

        Args:
            side: 交易方向 "LONG"/"SHORT"
            entry_price: 入场价
            exit_price: 出场价
            pnl: 盈亏金额
            pnl_pct: 盈亏百分比
            hold_bars: 持仓K线数
            exit_reason: 退出原因
            entry_state: 入场时威科夫状态
            timeframe: 时间框架

        Returns:
            错误ID
        """
        severity = ErrorSeverity.HIGH if abs(pnl_pct) > 0.03 else ErrorSeverity.MEDIUM
        pattern = (
            ErrorPattern.TIMING_ERROR
            if abs(pnl_pct) < 0.01
            else ErrorPattern.FREQUENT_FALSE_POSITIVE
        )

        return self.record_mistake(
            mistake_type=MistakeType.ENTRY_VALIDATION_ERROR,
            severity=severity,
            context={
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "hold_bars": hold_bars,
                "exit_reason": exit_reason,
                "entry_state": entry_state,
            },
            expected="PROFIT",
            actual=f"LOSS_{pnl:.2f}",
            confidence_before=0.6,
            confidence_after=0.3,
            impact_score=min(abs(pnl_pct) * 10, 1.0),
            module_name="evolution_backtester",
            timeframe=timeframe,
            patterns=[pattern],
        )

    def _update_statistics(self, record: MistakeRecord) -> None:
        """更新统计信息"""
        self.stats["total_errors"] += 1
        self.stats["errors_by_type"][record.mistake_type.value] += 1
        self.stats["errors_by_severity"][record.severity.value] += 1
        self.stats["errors_by_module"][record.module_name] += 1

        # 计算学习率
        learned_count = sum(1 for r in self.records.values() if r.used_for_learning)
        self.stats["learning_rate"] = learned_count / max(len(self.records), 1)

    def _auto_cleanup(self) -> None:
        """自动清理旧记录

        BUG-11 修复：改为保留最近 max_records 条记录，而非按时间清理。
        按时间清理会导致 30 天后错题本完全清空，系统回退到纯随机模式。
        """
        if len(self.record_history) <= self.max_records:
            return

        # 保留最近的 max_records 条
        keep_records = self.record_history[-self.max_records :]
        keep_ids = {r.error_id for r in keep_records}

        # 清理记录字典中不在保留集中的记录
        old_ids = [error_id for error_id in self.records if error_id not in keep_ids]
        for error_id in old_ids:
            del self.records[error_id]

        self.record_history = keep_records

    def analyze_patterns(self, force_recompute: bool = False) -> dict[str, Any]:
        """
        分析错误模式

        Returns:
            模式分析结果字典
        """
        if self._pattern_cache is not None and not force_recompute:
            return self._pattern_cache

        if not self.records:
            return {"patterns": [], "summary": "无错误记录"}

        # 收集所有错误模式
        all_patterns = []
        for record in self.records.values():
            all_patterns.extend(record.patterns)

        # 计算模式频率
        pattern_counter = Counter(all_patterns)
        total_patterns = len(all_patterns)

        # 识别高频模式
        frequent_patterns = []
        for pattern, count in pattern_counter.items():
            frequency = count / max(total_patterns, 1)
            if frequency >= self.pattern_detection_threshold:
                frequent_patterns.append(
                    {
                        "pattern": pattern.value,
                        "count": count,
                        "frequency": frequency,
                        "description": self._get_pattern_description(pattern),
                    }
                )

        # 按模块分析模式
        patterns_by_module = defaultdict(list)
        for record in self.records.values():
            for pattern in record.patterns:
                patterns_by_module[record.module_name].append(pattern)

        module_pattern_analysis = {}
        for module_name, patterns in patterns_by_module.items():
            pattern_counter = Counter(patterns)
            total = len(patterns)
            if total > 0:
                module_pattern_analysis[module_name] = {
                    "total_patterns": total,
                    "top_patterns": [
                        {
                            "pattern": p.value,
                            "count": c,
                            "frequency": c / total,
                        }
                        for p, c in pattern_counter.most_common(3)
                    ],
                }

        # 时间分布分析
        if self.record_history:
            timestamps = [r.timestamp for r in self.record_history]
            time_range = (min(timestamps), max(timestamps))
            errors_by_hour = self._analyze_time_distribution(timestamps)
        else:
            time_range = (None, None)
            errors_by_hour = {}

        # 构建模式分析结果
        analysis_result = {
            "patterns": frequent_patterns,
            "patterns_by_module": module_pattern_analysis,
            "time_analysis": {
                "time_range": time_range,
                "total_days": (time_range[1] - time_range[0]).days
                if time_range[0] and time_range[1]
                else 0,
                "errors_by_hour": errors_by_hour,
            },
            "summary": {
                "total_records": len(self.records),
                "total_patterns": total_patterns,
                "avg_patterns_per_record": total_patterns / len(self.records)
                if self.records
                else 0,
                "most_common_pattern": pattern_counter.most_common(1)[0]
                if pattern_counter
                else None,
            },
        }

        self._pattern_cache = analysis_result
        self._last_analysis_time = datetime.now()

        return analysis_result

    def _analyze_time_distribution(self, timestamps: list[datetime]) -> dict[str, Any]:
        """分析错误时间分布"""
        errors_by_hour = defaultdict(int)
        for ts in timestamps:
            hour = ts.hour
            errors_by_hour[hour] += 1

        # 识别高峰期
        if errors_by_hour:
            max_hour = max(errors_by_hour.items(), key=lambda x: x[1])[0]
            min_hour = min(errors_by_hour.items(), key=lambda x: x[1])[0]
        else:
            max_hour = min_hour = 0

        return {
            "hourly_distribution": dict(errors_by_hour),
            "peak_hour": max_hour,
            "quiet_hour": min_hour,
            "avg_errors_per_hour": sum(errors_by_hour.values()) / 24,
        }

    def _get_pattern_description(self, pattern: ErrorPattern) -> str:
        """获取错误模式描述"""
        descriptions = {
            ErrorPattern.FREQUENT_FALSE_POSITIVE: "频繁误报（假阳性）：系统过于敏感，产生过多错误信号",
            ErrorPattern.FREQUENT_FALSE_NEGATIVE: "频繁漏报（假阴性）：系统过于保守，错过有效信号",
            ErrorPattern.TIMING_ERROR: "时机错误：信号识别过早或过晚",
            ErrorPattern.MAGNITUDE_ERROR: "幅度错误：对市场变化的反应过度或不足",
            ErrorPattern.CONTEXT_SENSITIVITY_ERROR: "上下文敏感性错误：未能根据市场环境调整判断",
            ErrorPattern.CORRELATION_ERROR: "相关性误判：错误判断市场因素间的相关性",
            ErrorPattern.VOLATILITY_ADAPTATION_ERROR: "波动率适应错误：在高低波动率市场中表现不稳定",
            ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT: "多周期错配：不同时间框架间信号不一致",
        }
        return descriptions.get(pattern, "未知错误模式")

    def generate_weight_adjustments(self) -> list[dict[str, Any]]:
        """
        生成权重调整建议

        基于错误模式分析，生成针对性的权重调整建议
        """
        if not self.records:
            return []

        # 分析错误模式
        pattern_analysis = self.analyze_patterns()

        adjustments = []

        # 根据错误模式生成调整建议
        for pattern_info in pattern_analysis.get("patterns", []):
            pattern = pattern_info["pattern"]
            frequency = pattern_info["frequency"]

            # 根据模式类型生成调整建议
            if pattern == ErrorPattern.FREQUENT_FALSE_POSITIVE.value:
                # 假阳性过多 → 降低敏感性，提高阈值
                adjustment = {
                    "pattern": pattern,
                    "module": "threshold_adjustment",
                    "adjustment_type": "INCREASE_THRESHOLD",
                    "parameters": ["confidence_threshold", "volume_threshold"],
                    "adjustment_value": 0.1 * frequency,  # 根据频率调整幅度
                    "reason": f"假阳性频率过高 ({frequency:.2%})，提高置信度和成交量阈值",
                    "priority": frequency,
                }
                adjustments.append(adjustment)

            elif pattern == ErrorPattern.FREQUENT_FALSE_NEGATIVE.value:
                # 假阴性过多 → 提高敏感性，降低阈值
                adjustment = {
                    "pattern": pattern,
                    "module": "threshold_adjustment",
                    "adjustment_type": "DECREASE_THRESHOLD",
                    "parameters": ["confidence_threshold", "volume_threshold"],
                    "adjustment_value": -0.1 * frequency,
                    "reason": f"假阴性频率过高 ({frequency:.2%})，降低阈值提高敏感性",
                    "priority": frequency,
                }
                adjustments.append(adjustment)

            elif pattern == ErrorPattern.TIMING_ERROR.value:
                # 时机错误 → 调整时间窗口参数
                adjustment = {
                    "pattern": pattern,
                    "module": "time_window_adjustment",
                    "adjustment_type": "ADJUST_WINDOW_SIZE",
                    "parameters": ["confirmation_bars", "lookback_period"],
                    "adjustment_value": 0.05 * frequency,
                    "reason": f"时机错误频率 ({frequency:.2%})，调整时间窗口参数",
                    "priority": frequency,
                }
                adjustments.append(adjustment)

            elif pattern == ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT.value:
                # 多周期错配 → 调整周期权重
                adjustment = {
                    "pattern": pattern,
                    "module": "period_weight_filter",
                    "adjustment_type": "ADJUST_TIMEFRAME_WEIGHTS",
                    "parameters": ["timeframe_weights"],
                    "adjustment_value": 0.15 * frequency,
                    "reason": f"多周期错配频率 ({frequency:.2%})，调整时间框架权重分布",
                    "priority": frequency,
                }
                adjustments.append(adjustment)

        # 按模块聚合调整建议
        adjustments_by_module = defaultdict(list)
        for adj in adjustments:
            adjustments_by_module[adj["module"]].append(adj)

        # 为每个模块生成综合调整建议
        final_adjustments = []
        for module, module_adjustments in adjustments_by_module.items():
            if module_adjustments:
                # 计算平均调整值
                avg_adjustment = np.mean(
                    [adj["adjustment_value"] for adj in module_adjustments]
                )
                avg_priority = np.mean([adj["priority"] for adj in module_adjustments])

                # 合并原因
                reasons = [adj["reason"] for adj in module_adjustments]
                combined_reason = "; ".join(reasons[:3])  # 最多合并3个原因

                final_adjustment = {
                    "module": module,
                    "adjustment_type": "COMBINED_ADJUSTMENT",
                    "adjustment_value": avg_adjustment,
                    "reason": combined_reason,
                    "priority": avg_priority,
                    "source_patterns": [adj["pattern"] for adj in module_adjustments],
                    "detailed_adjustments": module_adjustments,
                }
                final_adjustments.append(final_adjustment)

        # 按优先级排序
        final_adjustments.sort(key=lambda x: x["priority"], reverse=True)

        self.weight_adjustment_suggestions = final_adjustments
        return final_adjustments

    def get_learning_batch(self, batch_size: int = 10) -> list[MistakeRecord]:
        """
        获取学习批次（优先级最高的未学习错误）

        Args:
            batch_size: 批次大小

        Returns:
            错误记录列表
        """
        # 获取未学习且优先级高的错误
        unlearned_records = [
            r
            for r in self.records.values()
            if not r.used_for_learning
            and r.learning_priority >= self.min_learning_priority
        ]

        # 按优先级排序
        unlearned_records.sort(key=lambda r: r.learning_priority, reverse=True)

        # 返回批次
        return unlearned_records[:batch_size]

    def mark_batch_as_learned(
        self, record_ids: list[str], outcome: str = "processed"
    ) -> None:
        """
        标记批次为已学习

        Args:
            record_ids: 错误ID列表
            outcome: 学习结果描述
        """
        for error_id in record_ids:
            if error_id in self.records:
                self.records[error_id].mark_as_learned(outcome)

        # 更新统计信息
        learned_count = sum(1 for r in self.records.values() if r.used_for_learning)
        self.stats["learning_rate"] = learned_count / max(len(self.records), 1)

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        if self._statistics_cache is not None:
            return self._statistics_cache

        stats = {
            **self.stats,
            "record_count": len(self.records),
            "historical_record_count": len(self.record_history),
            "unique_modules": len(set(self.stats["errors_by_module"].keys())),
            "unique_mistake_types": len(set(self.stats["errors_by_type"].keys())),
            "avg_impact_score": np.mean([r.impact_score for r in self.records.values()])
            if self.records
            else 0,
            "avg_learning_priority": np.mean(
                [r.learning_priority for r in self.records.values()]
            )
            if self.records
            else 0,
            "last_record_time": max([r.timestamp for r in self.records.values()])
            if self.records
            else None,
            "first_record_time": min([r.timestamp for r in self.records.values()])
            if self.records
            else None,
        }

        self._statistics_cache = stats
        return stats

    def clear_records(self) -> None:
        """清空所有错误记录（谨慎使用）"""
        self.records.clear()
        self.record_history.clear()
        self._pattern_cache = None
        self._statistics_cache = None
        self.weight_adjustment_suggestions.clear()

        # 重置统计信息
        self.stats = {
            "total_errors": 0,
            "errors_by_type": defaultdict(int),
            "errors_by_severity": defaultdict(int),
            "errors_by_module": defaultdict(int),
            "learning_rate": 0.0,
        }

    def export_records(self, format: str = "json") -> str:
        """
        导出错误记录

        Args:
            format: 导出格式 ("json" 或 "csv")

        Returns:
            导出数据字符串
        """
        if format == "json":
            data = {
                "records": [r.to_dict() for r in self.records.values()],
                "statistics": self.get_statistics(),
                "pattern_analysis": self.analyze_patterns(),
                "weight_adjustments": self.weight_adjustment_suggestions,
                "export_time": datetime.now().isoformat(),
            }
            return json.dumps(data, indent=2, ensure_ascii=False, default=str)

        if format == "csv":
            # 创建CSV格式
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # 写入表头
            headers = [
                "error_id",
                "timestamp",
                "mistake_type",
                "severity",
                "module_name",
                "timeframe",
                "learning_priority",
                "impact_score",
                "confidence_before",
                "confidence_after",
                "patterns",
                "used_for_learning",
            ]
            writer.writerow(headers)

            # 写入数据
            for record in self.records.values():
                row = [
                    record.error_id,
                    record.timestamp.isoformat(),
                    record.mistake_type.value,
                    record.severity.value,
                    record.module_name,
                    record.timeframe,
                    record.learning_priority,
                    record.impact_score,
                    record.confidence_before,
                    record.confidence_after,
                    ";".join([p.value for p in record.patterns]),
                    str(record.used_for_learning),
                ]
                writer.writerow(row)

            return output.getvalue()

        raise ValueError(f"不支持的导出格式: {format}")

    def import_records(self, data: str, format: str = "json") -> int:
        """
        导入错误记录

        Args:
            data: 导入数据字符串
            format: 数据格式

        Returns:
            导入的记录数量
        """
        imported_count = 0

        if format == "json":
            parsed_data = json.loads(data)

            if "records" in parsed_data:
                for record_data in parsed_data["records"]:
                    # 转换时间戳
                    if "timestamp" in record_data:
                        record_data["timestamp"] = datetime.fromisoformat(
                            record_data["timestamp"]
                        )

                    # 转换错误类型枚举
                    if "mistake_type" in record_data:
                        record_data["mistake_type"] = MistakeType(
                            record_data["mistake_type"]
                        )

                    # 转换严重程度枚举
                    if "severity" in record_data:
                        record_data["severity"] = ErrorSeverity(record_data["severity"])

                    # 转换错误模式枚举
                    if "patterns" in record_data:
                        patterns = [ErrorPattern(p) for p in record_data["patterns"]]
                        record_data["patterns"] = patterns

                    # 处理context字段（导出时可能保存为context_summary）
                    if (
                        "context" not in record_data
                        and "context_summary" in record_data
                    ):
                        record_data["context"] = record_data["context_summary"]

                    # 过滤出MistakeRecord构造函数接受的参数
                    allowed_keys = {
                        "mistake_type",
                        "severity",
                        "timestamp",
                        "context",
                        "expected",
                        "actual",
                        "confidence_before",
                        "confidence_after",
                        "impact_score",
                        "module_name",
                        "timeframe",
                        "patterns",
                        "metadata",
                    }
                    filtered_data = {
                        k: v for k, v in record_data.items() if k in allowed_keys
                    }

                    # 确保context存在（默认为空字典）
                    if "context" not in filtered_data:
                        filtered_data["context"] = {}

                    # 创建记录
                    record = MistakeRecord(**filtered_data)

                    # 添加到错题本
                    self.records[record.error_id] = record
                    self.record_history.append(record)
                    imported_count += 1

        # 清空缓存
        self._pattern_cache = None
        self._statistics_cache = None

        # 重新计算统计信息
        self.stats = {
            "total_errors": 0,
            "errors_by_type": defaultdict(int),
            "errors_by_severity": defaultdict(int),
            "errors_by_module": defaultdict(int),
            "learning_rate": 0.0,
        }

        for record in self.records.values():
            self._update_statistics(record)

        return imported_count


# 使用示例
if __name__ == "__main__":
    # 创建错题本实例
    mistake_book = MistakeBook(
        {
            "max_records": 1000,
            "auto_cleanup_days": 30,
            "min_learning_priority": 0.3,
        }
    )

    # 记录一个状态误判错误
    error_id = mistake_book.record_mistake(
        mistake_type=MistakeType.STATE_MISJUDGMENT,
        severity=ErrorSeverity.HIGH,
        context={
            "market_regime": "TRENDING_BULLISH",
            "price": 45000.0,
            "volume": 1200,
            "expected_state": "ACCUMULATION",
            "actual_state": "DISTRIBUTION",
            "confidence_scores": {"wyckoff_state_machine": 0.8},
        },
        expected="ACCUMULATION",
        actual="DISTRIBUTION",
        confidence_before=0.8,
        confidence_after=0.2,
        impact_score=0.7,
        module_name="wyckoff_state_machine",
        timeframe="H4",
        patterns=[ErrorPattern.FREQUENT_FALSE_POSITIVE],
    )

    # 分析错误模式
    patterns = mistake_book.analyze_patterns()

    # 生成权重调整建议
    adjustments = mistake_book.generate_weight_adjustments()

    # 获取统计信息
    stats = mistake_book.get_statistics()
