"""努力与结果原则分析器

威科夫努力与结果原则：成交量(努力)与价格变动(结果)应和谐。
- 放量大涨 = 努力与结果和谐（趋势延续）
- 放量小涨 = 高努力低结果（潜在转向，顶部信号）
- 缩量大涨 = 低努力高结果（空头陷阱或动能衰竭）
- 关键位置的努力结果更有意义

输出：effort_result_score (-1 ~ +1)
  -1 = 完全背离（高努力低结果，预示反转）
  +1 = 完全和谐（努力与结果一致）
   0 = 中性
"""

import logging
import math
from collections import deque
from typing import Any, Optional

logger = logging.getLogger(__name__)


def calc_effort_result(
    candle: dict,
    history: deque,
    prev_context: Optional[Any] = None,
) -> float:
    """计算努力与结果原则分数。

    Args:
        candle: 当前K线数据（open/high/low/close/volume）
        history: 滑窗K线历史（含当前K线）
        prev_context: 上一轮 StructureContext，首根K线为 None

    Returns:
        努力结果分数 -1 ~ +1
    """
    scores = []
    weights = []

    # --- 1. 当前K线的量价和谐度（核心）---
    harmony_score = _current_bar_harmony(candle, history)
    scores.append(harmony_score)
    weights.append(0.45)

    # --- 2. 与前N根K线对比的背离趋势 ---
    trend_score = _divergence_trend(history)
    scores.append(trend_score)
    weights.append(0.30)

    # --- 3. 关键位置的努力结果放大 ---
    position_score = _position_amplifier(candle, history, prev_context)
    scores.append(position_score)
    weights.append(0.25)

    # 加权求和
    total_weight = sum(weights)
    result = sum(s * w for s, w in zip(scores, weights)) / total_weight

    # 钳位到 [-1, +1]
    return max(-1.0, min(1.0, result))


def _current_bar_harmony(candle: dict, history: deque) -> float:
    """当前K线的量价和谐度。

    和谐 = 量与价变动成比例
    背离 = 量大但价变动小（或反之）
    """
    volume = candle["volume"]
    price_move = abs(candle["close"] - candle["open"])
    full_range = candle["high"] - candle["low"]

    if full_range <= 0:
        return 0.0

    # 计算相对量和相对价格变动
    if len(history) < 2:
        return 0.0

    window = min(len(history) - 1, 20)
    recent = list(history)[-window - 1 : -1]
    avg_volume = sum(c["volume"] for c in recent) / len(recent)
    avg_range = sum(abs(c["close"] - c["open"]) for c in recent) / len(recent)

    if avg_volume <= 0 or avg_range <= 0:
        return 0.0

    vol_ratio = volume / avg_volume
    move_ratio = price_move / avg_range

    # 和谐度：两者比值接近1则和谐
    # vol_ratio ≈ move_ratio → 和谐（+1）
    # vol_ratio >> move_ratio → 高努力低结果（-1）
    # vol_ratio << move_ratio → 低努力高结果（中性偏负）
    if vol_ratio <= 0:
        return 0.0

    ratio = move_ratio / vol_ratio

    if ratio > 0.8 and ratio < 1.3:
        # 和谐区间
        harmony = 1.0 - abs(ratio - 1.0) / 0.3
        return max(0.0, harmony)
    elif ratio < 0.8:
        # 高努力低结果（背离）
        divergence = (0.8 - ratio) / 0.8
        return -min(divergence, 1.0)
    else:
        # 低努力高结果 — 可能是空头陷阱，轻微负
        divergence = (ratio - 1.3) / 1.3
        return -min(divergence * 0.5, 0.5)


def _divergence_trend(history: deque) -> float:
    """背离趋势：最近数根K线量价关系变化方向。

    量持续放大但价格涨幅收窄 → 负（顶部背离）
    量持续缩小但价格跌幅收窄 → 正（底部收敛，供应枯竭）
    """
    lookback = min(len(history), 10)
    if lookback < 4:
        return 0.0

    recent = list(history)[-lookback:]
    volumes = [c["volume"] for c in recent]
    moves = [abs(c["close"] - c["open"]) for c in recent]

    # 计算量的趋势和价格变动的趋势
    vol_trend = _simple_trend(volumes)
    move_trend = _simple_trend(moves)

    # 量增价增 → 和谐 → 正
    # 量增价减 → 背离 → 负
    # 量减价增 → 轻微异常 → 轻微负
    # 量减价减 → 枯竭中 → 轻微正
    if vol_trend > 0 and move_trend > 0:
        return min(vol_trend * move_trend * 4.0, 1.0)
    elif vol_trend > 0 and move_trend < 0:
        return max(-vol_trend * abs(move_trend) * 4.0, -1.0)
    elif vol_trend < 0 and move_trend > 0:
        return max(-abs(vol_trend) * move_trend * 2.0, -0.5)
    elif vol_trend < 0 and move_trend < 0:
        return min(abs(vol_trend) * abs(move_trend) * 2.0, 0.5)

    return 0.0


def _position_amplifier(
    candle: dict,
    history: deque,
    prev_context: Optional[Any],
) -> float:
    """关键位置的努力结果放大。

    在支撑/阻力位附近，努力结果信号更有意义：
    - SC低点附近放量但没跌破 → 强正信号
    - 阻力位放量但突不破 → 强负信号
    """
    if prev_context is None:
        return 0.0

    position = getattr(prev_context, "position_in_tr", 0.5)
    volume = candle["volume"]

    # 计算相对量
    if len(history) < 2:
        return 0.0

    window = min(len(history) - 1, 20)
    recent = list(history)[-window - 1 : -1]
    avg_volume = sum(c["volume"] for c in recent) / len(recent)

    if avg_volume <= 0:
        return 0.0

    vol_ratio = volume / avg_volume
    is_high_volume = vol_ratio > 1.3

    if not is_high_volume:
        return 0.0

    close = candle["close"]
    open_ = candle["open"]
    body_ratio = (
        abs(close - open_) / (candle["high"] - candle["low"])
        if (candle["high"] - candle["low"]) > 0
        else 0.0
    )
    small_body = body_ratio < 0.3

    # 支撑位附近：放量但没跌破（小实体）→ 正（需求吸收了供应）
    if position < 0.25 and small_body:
        return min((vol_ratio - 1.3) / 1.0 + 0.5, 1.0)

    # 阻力位附近：放量但突不破（小实体）→ 负（供应压制了需求）
    if position > 0.75 and small_body:
        return -min((vol_ratio - 1.3) / 1.0 + 0.5, 1.0)

    return 0.0


def _simple_trend(values: list) -> float:
    """简单线性趋势估算。

    返回标准化趋势方向：
    正 = 递增
    负 = 递减
    0 = 无趋势
    """
    n = len(values)
    if n < 2:
        return 0.0

    avg = sum(values) / n
    if avg <= 0:
        return 0.0

    # 简单回归斜率
    x_mean = (n - 1) / 2.0
    numerator = 0.0
    denominator = 0.0

    for i, v in enumerate(values):
        dx = i - x_mean
        numerator += dx * (v - avg)
        denominator += dx * dx

    if denominator <= 0:
        return 0.0

    slope = numerator / denominator

    # 标准化：斜率/平均值，钳位到 [-1, 1]
    normalized = slope / avg
    return max(-1.0, min(1.0, normalized))
