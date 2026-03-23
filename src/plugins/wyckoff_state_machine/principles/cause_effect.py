"""因果原则分析器

威科夫因果原则：区间是"因"，趋势是"果"。
- 区间持续时间越长，后续趋势幅度越大
- 区间:趋势时间比约 2:1
- 区间内价格振幅收敛/发散是因积累的信号

输出：cause_effect_score (0 ~ 1)
  0 = 无因积累（刚开始或趋势中）
  1 = 因的充分积累（长时间区间盘整）
"""

import logging
import math
from collections import deque
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 参考时间比例：区间:趋势 ≈ 2:1（可进化参数）
_DEFAULT_CAUSE_EFFECT_RATIO = 2.0

# 区间持续N根K线后视为"因"开始有效积累
_MIN_RANGE_BARS = 5

# 完全成熟的区间长度（N根K线后分数趋近1.0）
_MATURE_RANGE_BARS = 60


def calc_cause_effect(
    candle: dict,
    history: deque,
    prev_context: Optional[Any] = None,
) -> float:
    """计算因果原则分数。

    Args:
        candle: 当前K线数据（open/high/low/close/volume）
        history: 滑窗K线历史（含当前K线）
        prev_context: 上一轮 StructureContext，首根K线为 None

    Returns:
        因果分数 0 ~ 1
    """
    scores = []
    weights = []

    # --- 1. 区间持续时间（因的大小）---
    duration_score = _range_duration_score(prev_context)
    scores.append(duration_score)
    weights.append(0.40)

    # --- 2. 振幅收敛/发散 ---
    convergence_score = _convergence_score(history)
    scores.append(convergence_score)
    weights.append(0.30)

    # --- 3. 阶段进度（A→B→C 推进中因持续累积）---
    phase_score = _phase_progress_score(prev_context)
    scores.append(phase_score)
    weights.append(0.30)

    # 加权求和
    total_weight = sum(weights)
    result = sum(s * w for s, w in zip(scores, weights)) / total_weight

    # 钳位到 [0, 1]
    return max(0.0, min(1.0, result))


def _range_duration_score(prev_context: Optional[Any]) -> float:
    """区间持续时间评分。

    区间阶段（A/B/C/D/E）中停留越久，因越大。
    IDLE/MARKUP/MARKDOWN 阶段 → 无因积累。
    """
    if prev_context is None:
        return 0.0

    phase = getattr(prev_context, "current_phase", "IDLE")
    if phase in ("IDLE", "MARKUP", "MARKDOWN"):
        return 0.0

    # 有上下文但不在区间阶段，也无法计算
    # 通过 boundaries 的数量间接推断持续时间
    boundaries = getattr(prev_context, "boundaries", {})
    if not boundaries:
        return 0.1  # 区间阶段但边界未建立，刚开始

    # 边界越多 → 结构越成熟 → 因越大
    boundary_count = len(boundaries)
    # PS+SC=2, +AR=3, +ST=4 → 随着事件增多因累积
    score = min(boundary_count / 4.0, 1.0)

    return score


def _convergence_score(history: deque) -> float:
    """振幅收敛评分。

    价格振幅逐渐缩小 → 能量蓄积（因在累积）
    价格振幅逐渐放大 → 能量释放（因在消耗）
    """
    lookback = min(len(history), 20)
    if lookback < 6:
        return 0.0

    recent = list(history)[-lookback:]
    ranges = [c["high"] - c["low"] for c in recent]

    # 将窗口分成前半和后半
    half = lookback // 2
    first_half_avg = sum(ranges[:half]) / half
    second_half_avg = sum(ranges[half:]) / (lookback - half)

    if first_half_avg <= 0:
        return 0.0

    # 收敛比 < 1 表示振幅缩小（收敛）
    convergence_ratio = second_half_avg / first_half_avg

    if convergence_ratio < 0.7:
        # 强收敛 → 高分
        return min((0.7 - convergence_ratio) / 0.4 + 0.5, 1.0)
    elif convergence_ratio < 1.0:
        # 轻微收敛
        return (1.0 - convergence_ratio) / 0.3 * 0.5
    else:
        # 发散 → 分数低但不为零（发散也是一种因的信息）
        return max(0.0, 0.2 - (convergence_ratio - 1.0) * 0.2)


def _phase_progress_score(prev_context: Optional[Any]) -> float:
    """阶段进度评分。

    越往后的阶段（C > B > A），因越充分。
    """
    if prev_context is None:
        return 0.0

    phase = getattr(prev_context, "current_phase", "IDLE")

    phase_scores = {
        "IDLE": 0.0,
        "A": 0.2,
        "B": 0.5,
        "C": 0.8,
        "D": 0.9,
        "E": 1.0,
        "MARKUP": 0.0,
        "MARKDOWN": 0.0,
    }

    return phase_scores.get(phase, 0.0)
