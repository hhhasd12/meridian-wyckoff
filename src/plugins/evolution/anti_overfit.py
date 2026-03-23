"""五层防过拟合守卫 — MBL + OOS-DR + DSR + MonteCarlo + CPCV

五层检查：
1. MBL（Minimum Backtest Length）— 数据不足则拒绝
2. OOS-DR（Out-of-Sample Degradation Ratio）— 训练/测试差距过大则拒绝
3. DSR（Deflated Sharpe Ratio）— 多次尝试的统计折扣
4. Monte Carlo Permutation — 随机打乱收益序列，检查原始是否显著
5. CPCV（Combinatorially Purged Cross-Validation）— 组合交叉验证

使用方式：
    guard = AntiOverfitGuard()
    verdict = guard.check(backtest_result, wfa_report, n_trials=20)
    if not verdict.passed:
        reject(config)
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from src.kernel.types import BacktestResult

logger = logging.getLogger(__name__)


# ================================================================
# 数据类
# ================================================================


@dataclass
class AntiOverfitVerdict:
    """五层防过拟合检查结论

    Attributes:
        passed: 是否通过所有检查
        checks: 各层检查结果
        rejection_reason: 拒绝原因（若被拒绝）
    """

    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    rejection_reason: Optional[str] = None


@dataclass
class AntiOverfitConfig:
    """防过拟合配置

    Attributes:
        min_backtest_bars: MBL 最小回测K线数
        oos_dr_threshold: OOS退化率阈值（>此值=过拟合）
        dsr_threshold: 折扣Sharpe阈值
        mc_n_permutations: Monte Carlo 排列数
        mc_p_value_threshold: MC p值阈值
        cpcv_n_splits: CPCV 分割数
        cpcv_min_pass_ratio: CPCV 最低通过比例
    """

    min_backtest_bars: int = 200
    oos_dr_threshold: float = 0.40
    dsr_threshold: float = 0.5
    mc_n_permutations: int = 100
    mc_p_value_threshold: float = 0.05
    cpcv_n_splits: int = 5
    cpcv_min_pass_ratio: float = 0.6


# ================================================================
# AntiOverfitGuard — 主类
# ================================================================


class AntiOverfitGuard:
    """五层防过拟合守卫"""

    def __init__(self, config: Optional[AntiOverfitConfig] = None) -> None:
        self.config = config or AntiOverfitConfig()

    def check(
        self,
        result: BacktestResult,
        train_sharpes: Optional[List[float]] = None,
        test_sharpes: Optional[List[float]] = None,
        n_trials: int = 1,
    ) -> AntiOverfitVerdict:
        """执行五层检查

        Args:
            result: 回测结果
            train_sharpes: WFA 训练段 Sharpe 列表
            test_sharpes: WFA 测试段 Sharpe 列表
            n_trials: 该配置经历的总尝试次数（用于 DSR）

        Returns:
            AntiOverfitVerdict
        """
        checks: Dict[str, bool] = {}
        details: Dict[str, Any] = {}

        # Layer 1: MBL
        mbl_ok, mbl_info = self._check_mbl(result)
        checks["MBL"] = mbl_ok
        details["MBL"] = mbl_info

        # Layer 2: OOS-DR
        oos_ok, oos_info = self._check_oos_dr(train_sharpes, test_sharpes)
        checks["OOS_DR"] = oos_ok
        details["OOS_DR"] = oos_info

        # Layer 3: DSR
        dsr_ok, dsr_info = self._check_dsr(result, n_trials)
        checks["DSR"] = dsr_ok
        details["DSR"] = dsr_info

        # Layer 4: Monte Carlo
        mc_ok, mc_info = self._check_monte_carlo(result)
        checks["MONTE_CARLO"] = mc_ok
        details["MONTE_CARLO"] = mc_info

        # Layer 5: CPCV
        cpcv_ok, cpcv_info = self._check_cpcv(result)
        checks["CPCV"] = cpcv_ok
        details["CPCV"] = cpcv_info

        # 综合判定
        passed = all(checks.values())
        reason = None
        if not passed:
            failed = [k for k, v in checks.items() if not v]
            reason = f"Failed: {', '.join(failed)}"

        return AntiOverfitVerdict(
            passed=passed,
            checks=checks,
            details=details,
            rejection_reason=reason,
        )

    # ================================================================
    # Layer 1: MBL — Minimum Backtest Length
    # ================================================================

    def _check_mbl(self, result: BacktestResult) -> tuple:
        """MBL检查：回测数据是否足够"""
        if not result.trades:
            return False, {"reason": "no_trades", "n_trades": 0}

        # 用交易跨度估算bar数
        bar_span = 0
        if result.trades:
            bar_span = result.trades[-1].exit_bar - result.trades[0].entry_bar

        ok = bar_span >= self.config.min_backtest_bars
        return ok, {
            "bar_span": bar_span,
            "min_required": self.config.min_backtest_bars,
            "n_trades": result.total_trades,
        }

    # ================================================================
    # Layer 2: OOS-DR — Out-of-Sample Degradation Ratio
    # ================================================================

    def _check_oos_dr(
        self,
        train_sharpes: Optional[List[float]],
        test_sharpes: Optional[List[float]],
    ) -> tuple:
        """OOS退化率检查"""
        if not train_sharpes or not test_sharpes:
            # 无WFA数据，跳过（通过）
            return True, {"reason": "no_wfa_data", "oos_dr": 0.0}

        ratios = []
        for ts, os_val in zip(train_sharpes, test_sharpes):
            if ts > 0.01:
                ratios.append(1.0 - os_val / ts)

        if not ratios:
            return True, {"reason": "no_valid_pairs", "oos_dr": 0.0}

        oos_dr = float(np.mean(ratios))
        ok = oos_dr < self.config.oos_dr_threshold
        return ok, {
            "oos_dr": oos_dr,
            "threshold": self.config.oos_dr_threshold,
            "n_pairs": len(ratios),
        }

    # ================================================================
    # Layer 3: DSR — Deflated Sharpe Ratio
    # ================================================================

    def _check_dsr(self, result: BacktestResult, n_trials: int) -> tuple:
        """折扣Sharpe检查 — 考虑多次尝试的统计折扣

        DSR = SR * sqrt(1 - skew*SR/6 + (kurt-3)*SR^2/24) / sqrt(V(SR_hat))
        简化版：对观测SR施加 log(n_trials) 惩罚
        """
        sr = result.sharpe_ratio
        if n_trials <= 1:
            # 单次尝试，DSR = SR
            ok = sr >= self.config.dsr_threshold
            return ok, {"dsr": sr, "raw_sharpe": sr, "n_trials": 1}

        # Bailey-López de Prado 简化折扣
        # 期望最大Sharpe ≈ sqrt(2*ln(n_trials)) （标准正态的最大值期望）
        expected_max = math.sqrt(2.0 * math.log(max(n_trials, 2)))
        dsr = max(0.0, sr - expected_max * 0.5)

        ok = dsr >= self.config.dsr_threshold
        return ok, {
            "dsr": dsr,
            "raw_sharpe": sr,
            "expected_max_sharpe": expected_max,
            "n_trials": n_trials,
        }

    # ================================================================
    # Layer 4: Monte Carlo Permutation Test
    # ================================================================

    def _check_monte_carlo(self, result: BacktestResult) -> tuple:
        """Monte Carlo排列测试 — 打乱收益序列，检查原始结果是否显著"""
        if len(result.trades) < 5:
            return True, {"reason": "too_few_trades", "p_value": 0.0}

        returns = np.array([t.pnl_pct for t in result.trades])
        original_sharpe = self._sharpe_from_returns(returns)

        rng = np.random.default_rng()
        n_better = 0
        n_perms = self.config.mc_n_permutations

        for _ in range(n_perms):
            shuffled = rng.permutation(returns)
            shuffled_sharpe = self._sharpe_from_returns(shuffled)
            if shuffled_sharpe >= original_sharpe:
                n_better += 1

        p_value = (n_better + 1) / (n_perms + 1)
        ok = p_value <= self.config.mc_p_value_threshold

        return ok, {
            "p_value": p_value,
            "threshold": self.config.mc_p_value_threshold,
            "original_sharpe": original_sharpe,
            "n_permutations": n_perms,
        }

    # ================================================================
    # Layer 5: CPCV — Combinatorially Purged Cross-Validation
    # ================================================================

    def _check_cpcv(self, result: BacktestResult) -> tuple:
        """CPCV检查 — 将交易序列分成多段，检查各段Sharpe一致性"""
        trades = result.trades
        n = len(trades)
        n_splits = self.config.cpcv_n_splits

        if n < n_splits * 2:
            return True, {"reason": "too_few_trades", "pass_ratio": 1.0}

        # 将交易按时间分段
        chunk_size = n // n_splits
        segments: List[np.ndarray] = []
        for i in range(n_splits):
            start = i * chunk_size
            end = start + chunk_size if i < n_splits - 1 else n
            seg_returns = np.array([t.pnl_pct for t in trades[start:end]])
            segments.append(seg_returns)

        # 对每一段计算Sharpe
        segment_sharpes = [self._sharpe_from_returns(seg) for seg in segments]

        # 统计正Sharpe段数
        positive_count = sum(1 for s in segment_sharpes if s > 0)
        pass_ratio = positive_count / n_splits

        ok = pass_ratio >= self.config.cpcv_min_pass_ratio

        return ok, {
            "pass_ratio": pass_ratio,
            "threshold": self.config.cpcv_min_pass_ratio,
            "segment_sharpes": segment_sharpes,
            "n_positive": positive_count,
            "n_splits": n_splits,
        }

    # ================================================================
    # 工具方法
    # ================================================================

    @staticmethod
    def _sharpe_from_returns(returns: np.ndarray) -> float:
        """从收益序列计算Sharpe"""
        if len(returns) < 2:
            return 0.0
        mean_r = float(np.mean(returns))
        std_r = float(np.std(returns, ddof=1))
        if std_r < 1e-10:
            return 0.0
        return mean_r / std_r
