"""标准评估器 — 替代 run_evolution.py 中 broken 的 real_performance_evaluator

职责：
1. 用 BarByBarBacktester 逐根生成信号并回测
2. 计算标准化性能指标
3. 记录亏损交易到 MistakeBook
4. 返回 WFA/GA 可消费的指标字典
5. 可选：集成标注匹配度到 fitness（T5.1）
"""

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.kernel.types import BacktestResult, BacktestTrade

logger = logging.getLogger(__name__)


class StandardEvaluator:
    """标准化评估器 — WFA 和 GA 的回调接口

    使用方式：
        evaluator = StandardEvaluator(mistake_book=book)
        metrics = evaluator(config, data_dict)

    标注匹配度（T5.1）：
        如果设置了 annotation_weight > 0 且 data/annotations/ 有标注数据，
        最终 fitness 会混入标注匹配度分数。无标注时不影响现有行为。

    WFA 元数据协议：
        data_dict 中可能包含 "__test_start_ts__" 和 "__warmup_bars__"
        这些会在调用前被 pop 出来，不传给回测器
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0005,
        warmup_bars: int = 50,
        mistake_book: Optional[Any] = None,
        annotation_weight: float = 0.0,
        annotation_dir: str = "data/annotations",
        min_annotations: int = 5,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.warmup_bars = warmup_bars
        self.mistake_book = mistake_book
        self.last_backtest_result: Optional[BacktestResult] = None
        # T5.1: 标注匹配度
        self.annotation_weight = annotation_weight
        self.annotation_dir = annotation_dir
        self.min_annotations = min_annotations

    def __call__(
        self,
        config: Dict[str, Any],
        data: Dict[str, Any],
    ) -> Dict[str, float]:
        """评估单个配置的性能

        Args:
            config: 进化配置字典
            data: 多TF数据 {"H4": df, "H1": df, ...}
                  可能包含WFA元数据键 "__test_start_ts__", "__warmup_bars__"

        Returns:
            标准化指标字典
        """
        # 延迟导入避免循环依赖
        from src.plugins.evolution.bar_by_bar_backtester import BarByBarBacktester

        _EMPTY = self._empty_metrics()

        # 1. 提取WFA元数据（pop 出来，不传给回测器）
        data = dict(data)  # 浅拷贝，不修改原始dict
        test_start_ts = data.pop("__test_start_ts__", None)
        warmup = data.pop("__warmup_bars__", self.warmup_bars)

        # 2. 检查数据有效性
        h4 = data.get("H4")
        if not isinstance(h4, pd.DataFrame) or len(h4) < 50:
            logger.debug("H4数据不足50根，返回空指标")
            return _EMPTY

        # 3. 计算 test_start_idx
        test_start_idx: Optional[int] = None
        if test_start_ts is not None:
            test_start_idx = int(h4.index.searchsorted(test_start_ts))

        # 4. 逐bar回测
        backtester = BarByBarBacktester(
            config=config,
            warmup_bars=warmup,
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
            slippage_rate=self.slippage_rate,
        )
        result = backtester.run("EVOLUTION", data, test_start_idx=test_start_idx)

        # 缓存最近一次回测结果，供 GA 存入 individual（根因7修复）
        self.last_backtest_result = result

        # 5. 记录亏损到 MistakeBook
        if self.mistake_book is not None:
            self._record_losses(result)

        # 6. 计算指标
        metrics = self._compute_metrics(result)

        # 7. T5.1: 混入标注匹配度（如果有标注数据且权重 > 0）
        if self.annotation_weight > 0:
            ann_score = self._compute_annotation_score(result)
            metrics["ANNOTATION_SCORE"] = ann_score
            if ann_score > 0:
                base = metrics["COMPOSITE_SCORE"]
                w = self.annotation_weight
                metrics["COMPOSITE_SCORE"] = base * (1 - w) + ann_score * w

        return metrics

    def _compute_annotation_score(self, result: BacktestResult) -> float:
        """T5.1: 从回测结果的 transition_history 计算标注匹配度

        流程：
        1. 扫描 data/annotations/ 目录找到标注文件
        2. 用 AnnotationMatcher 计算 match_score (F1)
        3. 标注数不足 min_annotations 时返回 0（不干扰 fitness）

        Returns:
            match_score [0, 1]，无标注或不足最小量时返回 0.0
        """
        try:
            ann_dir = Path(self.annotation_dir)
            if not ann_dir.exists():
                return 0.0

            # 收集所有标注文件
            jsonl_files = list(ann_dir.glob("*.jsonl"))
            if not jsonl_files:
                return 0.0

            import json
            from src.plugins.annotation.matcher import AnnotationMatcher

            all_annotations: list = []
            for f in jsonl_files:
                with open(f, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                all_annotations.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue

            # 只有 event 类型标注参与匹配
            event_anns = [a for a in all_annotations if a.get("type") == "event"]
            if len(event_anns) < self.min_annotations:
                return 0.0

            # 从回测结果构建 transition_history
            # BacktestResult.bar_details 中有 state_changed + state 信息
            transition_history = self._extract_transitions(result)
            if not transition_history:
                return 0.0

            matcher = AnnotationMatcher(tolerance_bars=3)
            report = matcher.match(event_anns, transition_history)
            return report.match_score
        except Exception as e:
            logger.debug("标注匹配度计算失败: %s", e)
            return 0.0

    @staticmethod
    def _extract_transitions(result: BacktestResult) -> list:
        """从 BacktestResult.bar_details 提取状态转换历史

        Returns:
            转换历史列表 [{"from": str, "to": str, "bar": int}]
        """
        transitions = []
        prev_state = ""
        for i, detail in enumerate(result.bar_details):
            cur_state = detail.state if hasattr(detail, "state") else ""
            if cur_state and cur_state != prev_state and prev_state:
                transitions.append(
                    {
                        "from": prev_state,
                        "to": cur_state,
                        "bar": i,
                        "confidence": detail.confidence
                        if hasattr(detail, "confidence")
                        else 0.5,
                    }
                )
            prev_state = cur_state
        return transitions

    def _record_losses(self, result: BacktestResult) -> None:
        """记录亏损交易到错题本"""
        from src.plugins.self_correction.mistake_book import (
            ErrorPattern,
            ErrorSeverity,
            MistakeType,
        )

        for trade in result.trades:
            if trade.pnl < 0:
                severity = (
                    ErrorSeverity.HIGH
                    if abs(trade.pnl_pct) > 0.03
                    else ErrorSeverity.MEDIUM
                )
                pattern = (
                    ErrorPattern.TIMING_ERROR
                    if abs(trade.pnl_pct) < 0.01
                    else ErrorPattern.FREQUENT_FALSE_POSITIVE
                )
                if self.mistake_book is None:
                    continue
                self.mistake_book.record_mistake(
                    mistake_type=MistakeType.ENTRY_VALIDATION_ERROR,
                    severity=severity,
                    context={
                        "side": trade.side,
                        "entry_price": trade.entry_price,
                        "exit_price": trade.exit_price,
                        "pnl": trade.pnl,
                        "pnl_pct": trade.pnl_pct,
                        "hold_bars": trade.hold_bars,
                        "exit_reason": trade.exit_reason,
                        "entry_state": trade.entry_state,
                    },
                    expected="PROFIT",
                    actual=f"LOSS_{trade.pnl:.2f}",
                    confidence_before=0.6,
                    confidence_after=0.3,
                    impact_score=min(abs(trade.pnl_pct) * 10, 1.0),
                    module_name="evolution_backtester",
                    timeframe="H4",
                    patterns=[pattern],
                )

    @classmethod
    def _compute_metrics(cls, result: BacktestResult) -> Dict[str, float]:
        """从 BacktestResult 计算标准化指标"""
        # 根因3修复：交易数不足时返回空指标，防止0-trade配置获得高分
        if result.total_trades < 5:
            return {**cls._empty_metrics(), "TOTAL_TRADES": result.total_trades}

        sharpe = result.sharpe_ratio if not np.isnan(result.sharpe_ratio) else 0.0
        drawdown = result.max_drawdown
        win_rate = result.win_rate
        profit_factor = result.profit_factor

        calmar = (sharpe / drawdown) if drawdown > 0 else sharpe
        stability = max(0.0, 1.0 - drawdown)

        # sigmoid(sharpe) 映射：Sharpe=0→0.5, Sharpe=2→0.88, Sharpe=-2→0.12
        sharpe_component = 1.0 / (1.0 + np.exp(-sharpe))

        composite = (
            sharpe_component * 0.25
            + (1.0 - drawdown) * 0.20
            + win_rate * 0.15
            + min(profit_factor, 3.0) / 3.0 * 0.15
            + stability * 0.25
        )

        return {
            "SHARPE_RATIO": sharpe,
            "MAX_DRAWDOWN": drawdown,
            "WIN_RATE": win_rate,
            "PROFIT_FACTOR": profit_factor,
            "CALMAR_RATIO": calmar,
            "STABILITY_SCORE": stability,
            "COMPOSITE_SCORE": composite,
            "TOTAL_TRADES": result.total_trades,
            "TOTAL_RETURN": result.total_return,
        }

    @staticmethod
    def _empty_metrics() -> Dict[str, float]:
        """空指标（数据不足时返回）"""
        return {
            "SHARPE_RATIO": 0.0,
            "MAX_DRAWDOWN": 1.0,
            "WIN_RATE": 0.0,
            "PROFIT_FACTOR": 0.0,
            "CALMAR_RATIO": 0.0,
            "STABILITY_SCORE": 0.0,
            "COMPOSITE_SCORE": 0.0,
            "TOTAL_TRADES": 0,
            "TOTAL_RETURN": 0.0,
        }
