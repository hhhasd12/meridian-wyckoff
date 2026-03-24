"""WFA 滚动窗口验证器 — 替代旧 wfa_backtester.py

使用 BarByBarBacktester 进行逐bar回测，配合 AntiOverfitGuard 进行过拟合防护。
滚动窗口方案：训练窗口→测试窗口→步进→训练窗口→测试窗口...

设计原则：
1. 训练/测试数据严格时间分离（无前视偏差）
2. 多窗口交叉验证（不依赖单一窗口结果）
3. 集成五层防过拟合检查
4. T5.2: 标注数据作为额外约束（Pareto改进）
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.kernel.types import BacktestResult, WFAWindow

logger = logging.getLogger(__name__)


@dataclass
class WFAConfig:
    """WFA 验证器配置"""

    train_bars: int = 300  # 训练窗口大小（H4根数）~50天
    test_bars: int = 300  # 测试窗口大小（H4根数）~50天
    step_bars: int = 300  # 步进大小（= test_bars，消除窗口重叠）
    min_windows: int = 3  # 最少窗口数
    max_windows: int = 5  # 最多窗口数
    warmup_bars: int = 50  # 指标预热期
    min_trades_per_window: int = 3  # 每个窗口最少交易数
    oos_dr_threshold: float = 0.4  # OOS退化率阈值
    # T5.2: 标注回归守护
    annotation_regression_ratio: float = 0.95  # 新配置标注匹配度 < 旧 * 此值 = 回归


@dataclass
class WFAReport:
    """WFA 验证报告"""

    passed: bool
    windows: List[WFAWindow]
    train_sharpes: List[float]
    test_sharpes: List[float]
    oos_degradation_ratio: float
    avg_train_sharpe: float
    avg_test_sharpe: float
    avg_test_trades: float
    annotation_regression_passed: bool = True  # T5.2: 标注回归检查是否通过
    annotation_score: float = 0.0  # T5.2: 当前配置的标注匹配度
    details: Dict[str, Any] = field(default_factory=dict)


class WFAValidator:
    """Walk-Forward Analysis 滚动窗口验证器

    核心流程：
    1. 在锚定TF（H4）上创建滚动窗口
    2. 每个窗口：训练段评估 + 测试段评估
    3. 计算 OOS 退化率
    4. 集成 AntiOverfitGuard 的检查
    """

    def __init__(
        self,
        config: Optional[WFAConfig] = None,
        evaluator_fn: Optional[Callable] = None,
        baseline_annotation_score: float = 0.0,
    ) -> None:
        """初始化 WFA 验证器

        Args:
            config: WFA 配置
            evaluator_fn: 评估函数签名 (config, data_dict) -> Dict[str, float]
            baseline_annotation_score: 基准标注匹配度（旧配置的得分）
        """
        self.config = config or WFAConfig()
        self.evaluator_fn = evaluator_fn
        self.baseline_annotation_score = baseline_annotation_score

    def set_evaluator(self, evaluator_fn: Callable) -> None:
        """设置评估函数"""
        self.evaluator_fn = evaluator_fn

    def create_windows(
        self,
        n_bars: int,
    ) -> List[WFAWindow]:
        """创建滚动窗口

        Args:
            n_bars: 总bar数

        Returns:
            WFAWindow 列表
        """
        cfg = self.config
        windows: List[WFAWindow] = []

        # 从数据末端往前排列窗口
        # 最后一个窗口的test_end = n_bars - 1
        # 往前推 step_bars 创建更多窗口
        required = cfg.train_bars + cfg.test_bars
        if n_bars < required + cfg.warmup_bars:
            logger.warning(
                "数据不足: 需要 %d bars, 实际 %d bars",
                required + cfg.warmup_bars,
                n_bars,
            )
            return []

        # 从后往前创建窗口
        test_end = n_bars - 1
        while len(windows) < cfg.max_windows:
            test_start = test_end - cfg.test_bars + 1
            train_end = test_start - 1
            train_start = train_end - cfg.train_bars + 1

            if train_start < cfg.warmup_bars:
                break  # 训练窗口超出数据范围

            window = WFAWindow(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
            windows.append(window)

            # 步进
            test_end -= cfg.step_bars

        windows.reverse()  # 按时间顺序排列

        if len(windows) < cfg.min_windows:
            logger.warning(
                "窗口数不足: 需要 %d, 实际 %d",
                cfg.min_windows,
                len(windows),
            )
            return []

        logger.info(
            "创建 %d 个WFA窗口 (train=%d, test=%d, step=%d)",
            len(windows),
            cfg.train_bars,
            cfg.test_bars,
            cfg.step_bars,
        )
        return windows

    def validate(
        self,
        config: Dict[str, Any],
        data_dict: Dict[str, pd.DataFrame],
    ) -> WFAReport:
        """对单个配置执行 WFA 验证

        Args:
            config: 待验证的进化配置
            data_dict: 多TF数据

        Returns:
            WFAReport
        """
        if self.evaluator_fn is None:
            raise ValueError("evaluator_fn 未设置，请先调用 set_evaluator()")

        h4 = data_dict.get("H4")
        if h4 is None or not isinstance(h4, pd.DataFrame):
            return self._empty_report("H4数据缺失")

        n_bars = len(h4)
        windows = self.create_windows(n_bars)
        if not windows:
            return self._empty_report("窗口数不足")

        train_sharpes: List[float] = []
        test_sharpes: List[float] = []

        for i, window in enumerate(windows):
            # 训练段评估
            train_data = self._slice_data(
                data_dict, h4, window.train_start, window.train_end
            )
            train_metrics = self.evaluator_fn(config, train_data)
            train_sharpe = train_metrics.get("SHARPE_RATIO", 0.0)
            train_trades = int(train_metrics.get("TOTAL_TRADES", 0))

            # 构建训练段 BacktestResult（简化）
            window.train_result = BacktestResult(
                trades=[],
                total_return=train_metrics.get("TOTAL_RETURN", 0.0),
                sharpe_ratio=train_sharpe,
                max_drawdown=train_metrics.get("MAX_DRAWDOWN", 1.0),
                win_rate=train_metrics.get("WIN_RATE", 0.0),
                profit_factor=train_metrics.get("PROFIT_FACTOR", 0.0),
                total_trades=train_trades,
                avg_hold_bars=0.0,
                config_hash="",
            )

            # 测试段评估 — 独立引擎实例，仅给 warmup 预热数据
            # 根因2修复：不再传入完整训练段数据，避免引擎状态泄漏
            test_warmup_start = max(0, window.test_start - self.config.warmup_bars)
            test_data = self._slice_data(
                data_dict, h4, test_warmup_start, window.test_end
            )
            # 注入测试段起始时间戳，让评估器只统计测试段的信号
            test_data["__test_start_ts__"] = h4.index[window.test_start]  # type: ignore[assignment]
            test_data["__warmup_bars__"] = self.config.warmup_bars  # type: ignore[assignment]

            test_metrics = self.evaluator_fn(config, test_data)
            test_sharpe = test_metrics.get("SHARPE_RATIO", 0.0)
            test_trades = int(test_metrics.get("TOTAL_TRADES", 0))

            window.test_result = BacktestResult(
                trades=[],
                total_return=test_metrics.get("TOTAL_RETURN", 0.0),
                sharpe_ratio=test_sharpe,
                max_drawdown=test_metrics.get("MAX_DRAWDOWN", 1.0),
                win_rate=test_metrics.get("WIN_RATE", 0.0),
                profit_factor=test_metrics.get("PROFIT_FACTOR", 0.0),
                total_trades=test_trades,
                avg_hold_bars=0.0,
                config_hash="",
            )

            train_sharpes.append(train_sharpe)
            test_sharpes.append(test_sharpe)

            logger.debug(
                "窗口 %d/%d: train_sharpe=%.3f (%d trades), test_sharpe=%.3f (%d trades)",
                i + 1,
                len(windows),
                train_sharpe,
                train_trades,
                test_sharpe,
                test_trades,
            )

        # 计算 OOS 退化率
        oos_dr = self._compute_oos_degradation(train_sharpes, test_sharpes)

        # 判定是否通过
        avg_train = float(np.mean(train_sharpes)) if train_sharpes else 0.0
        avg_test = float(np.mean(test_sharpes)) if test_sharpes else 0.0
        avg_test_trades = (
            float(
                np.mean(
                    [
                        w.test_result.total_trades
                        for w in windows
                        if w.test_result is not None
                    ]
                )
            )
            if windows
            else 0.0
        )

        passed = (
            oos_dr < self.config.oos_dr_threshold
            and avg_test > 0.0
            and avg_test_trades >= self.config.min_trades_per_window
        )

        # T5.2: 标注回归守护 — 新配置的标注匹配度不能显著低于基准
        ann_score = 0.0
        ann_regression_passed = True
        if passed and self.baseline_annotation_score > 0:
            # 从测试段指标中取标注匹配度
            ann_scores_per_window = []
            for w in windows:
                if w.test_result is not None:
                    # 用 evaluator_fn 的结果中可能包含 ANNOTATION_SCORE
                    # 但 test_result 只存了标准字段，需从测试段重新评估
                    pass  # 使用下方独立计算
            ann_score = self._compute_config_annotation_score(config, data_dict)
            threshold = (
                self.baseline_annotation_score * self.config.annotation_regression_ratio
            )
            if ann_score < threshold:
                ann_regression_passed = False
                passed = False
                logger.info(
                    "WFA标注回归: 新配置匹配度 %.3f < 基准 %.3f * %.2f = %.3f → REJECT",
                    ann_score,
                    self.baseline_annotation_score,
                    self.config.annotation_regression_ratio,
                    threshold,
                )

        return WFAReport(
            passed=passed,
            windows=windows,
            train_sharpes=train_sharpes,
            test_sharpes=test_sharpes,
            oos_degradation_ratio=oos_dr,
            avg_train_sharpe=avg_train,
            avg_test_sharpe=avg_test,
            avg_test_trades=avg_test_trades,
            annotation_regression_passed=ann_regression_passed,
            annotation_score=ann_score,
            details={
                "n_windows": len(windows),
                "oos_dr_threshold": self.config.oos_dr_threshold,
                "min_trades_per_window": self.config.min_trades_per_window,
                "baseline_annotation_score": self.baseline_annotation_score,
            },
        )

    def validate_population(
        self,
        configs: List[Dict[str, Any]],
        data_dict: Dict[str, pd.DataFrame],
    ) -> List[WFAReport]:
        """验证整个种群

        Args:
            configs: 配置列表
            data_dict: 多TF数据

        Returns:
            WFAReport 列表
        """
        reports = []
        for i, config in enumerate(configs):
            logger.debug("验证种群成员 %d/%d", i + 1, len(configs))
            report = self.validate(config, data_dict)
            reports.append(report)
        return reports

    def _slice_data(
        self,
        data_dict: Dict[str, pd.DataFrame],
        h4: pd.DataFrame,
        start_idx: int,
        end_idx: int,
    ) -> Dict[str, pd.DataFrame]:
        """按H4 bar索引切片多TF数据

        Args:
            data_dict: 原始多TF数据
            h4: H4 DataFrame
            start_idx: 起始bar索引
            end_idx: 结束bar索引

        Returns:
            切片后的多TF数据
        """
        start_time = h4.index[start_idx]
        end_time = h4.index[end_idx]

        result: Dict[str, pd.DataFrame] = {}
        for tf_name, tf_df in data_dict.items():
            if not isinstance(tf_df, pd.DataFrame):
                continue
            sliced = tf_df.loc[(tf_df.index >= start_time) & (tf_df.index <= end_time)]
            if len(sliced) >= 20:
                result[tf_name] = sliced

        return result

    @staticmethod
    def _compute_oos_degradation(
        train_sharpes: List[float],
        test_sharpes: List[float],
    ) -> float:
        """计算 OOS 退化率

        OOS-DR = 1 - mean(test_sharpe / train_sharpe)
        只在 train_sharpe > 0 时计算（避免除零）

        Args:
            train_sharpes: 训练段 Sharpe 列表
            test_sharpes: 测试段 Sharpe 列表

        Returns:
            OOS 退化率 [0, 1+]。> 0.4 = 过拟合风险高
        """
        ratios = []
        for ts, os in zip(train_sharpes, test_sharpes):
            if ts > 0.01:  # 避免除以接近零的值
                ratios.append(1.0 - os / ts)
        return float(np.mean(ratios)) if ratios else 1.0

    def set_baseline_annotation_score(self, score: float) -> None:
        """设置基准标注匹配度（当前生产配置的得分）

        Args:
            score: 基准匹配度 [0, 1]
        """
        self.baseline_annotation_score = score

    def _compute_config_annotation_score(
        self,
        config: Dict[str, Any],
        data_dict: Dict[str, pd.DataFrame],
    ) -> float:
        """T5.2: 计算某个配置的标注匹配度

        使用 evaluator_fn 执行回测，从结果中提取 ANNOTATION_SCORE。
        如果 evaluator 未设置标注权重，则返回 0.0。

        Args:
            config: 待评估的配置
            data_dict: 多TF数据

        Returns:
            标注匹配度 [0, 1]
        """
        if self.evaluator_fn is None:
            return 0.0
        try:
            metrics = self.evaluator_fn(config, dict(data_dict))
            return metrics.get("ANNOTATION_SCORE", 0.0)
        except Exception as e:
            logger.debug("计算标注匹配度失败: %s", e)
            return 0.0

    def _empty_report(self, reason: str) -> WFAReport:
        """空报告"""
        logger.warning("WFA验证跳过: %s", reason)
        return WFAReport(
            passed=False,
            windows=[],
            train_sharpes=[],
            test_sharpes=[],
            oos_degradation_ratio=1.0,
            avg_train_sharpe=0.0,
            avg_test_sharpe=0.0,
            avg_test_trades=0.0,
            details={"reason": reason},
        )
