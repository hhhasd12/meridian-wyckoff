"""供需原则分析器

量价关系是供需力量的核心表达：
- 放量上涨 = 需求（买方力量）
- 放量下跌 = 供应（卖方力量）
- 缩量回调 = 供应枯竭
- 接近支撑位的需求测试 / 接近阻力位的供应测试
- 连续N根K线的供需方向一致性

输出：supply_demand_score (-1 ~ +1)
  -1 = 纯供应（强卖压）
  +1 = 纯需求（强买压）
   0 = 均衡
"""

import logging
from collections import deque
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def calc_supply_demand(
    candle: dict,
    history: deque,
    prev_context: Optional[Any] = None,
) -> float:
    """计算供需原则分数。

    Args:
        candle: 当前K线数据（open/high/low/close/volume）
        history: 滑窗K线历史（含当前K线）
        prev_context: 上一轮 StructureContext，首根K线为 None

    Returns:
        供需分数 -1 ~ +1
    """
    scores = []
    weights = []

    # --- 1. 量价关系（核心）---
    vp_score = _volume_price_score(candle, history)
    scores.append(vp_score)
    weights.append(0.40)

    # --- 2. 位置加权（接近支撑=需求测试，接近阻力=供应测试）---
    pos_score = _position_score(prev_context)
    scores.append(pos_score)
    weights.append(0.25)

    # --- 3. 连续性（多根K线方向一致性）---
    cont_score = _continuity_score(history)
    scores.append(cont_score)
    weights.append(0.20)

    # --- 4. 缩量回调检测 ---
    exhaust_score = _exhaustion_score(candle, history)
    scores.append(exhaust_score)
    weights.append(0.15)

    # 加权求和
    total_weight = sum(weights)
    result = sum(s * w for s, w in zip(scores, weights)) / total_weight

    # 钳位到 [-1, +1]
    return max(-1.0, min(1.0, result))


def _volume_price_score(candle: dict, history: deque) -> float:
    """量价关系评分。

    放量上涨 → 正（需求）
    放量下跌 → 负（供应）
    缩量 → 趋近零
    """
    close = candle["close"]
    open_ = candle["open"]
    volume = candle["volume"]

    # 价格方向
    price_change = close - open_
    full_range = candle["high"] - candle["low"]
    if full_range <= 0:
        return 0.0

    # 标准化价格变动方向 (-1 ~ +1)
    direction = price_change / full_range

    # 成交量相对强度
    if len(history) < 2:
        vol_strength = 1.0
    else:
        window = min(len(history) - 1, 20)
        recent = list(history)[-window - 1 : -1]
        avg_vol = sum(c["volume"] for c in recent) / len(recent)
        vol_strength = volume / avg_vol if avg_vol > 0 else 1.0

    # 量价综合：方向 × 量的强度（用 log 衰减防止极端值）
    import math

    vol_factor = math.log1p(vol_strength) / math.log1p(3.0)
    vol_factor = min(vol_factor, 2.0)  # 上限

    return direction * vol_factor


def _position_score(prev_context: Optional[Any]) -> float:
    """位置加权评分。

    接近支撑 → 正（潜在需求区）
    接近阻力 → 负（潜在供应区）
    无上下文 → 0
    """
    if prev_context is None:
        return 0.0

    position = getattr(prev_context, "position_in_tr", 0.5)

    # position_in_tr: 0 = 支撑位, 1 = 阻力位
    # 接近支撑（position < 0.3）→ 正分（需求测试区域）
    # 接近阻力（position > 0.7）→ 负分（供应测试区域）
    # 中间区域 → 接近零
    if position < 0.3:
        return (0.3 - position) / 0.3  # 0~1
    elif position > 0.7:
        return -(position - 0.7) / 0.3  # -1~0
    else:
        return 0.0


def _continuity_score(history: deque) -> float:
    """连续性评分：最近N根K线的供需方向一致性。

    连续上涨 → 正（持续需求）
    连续下跌 → 负（持续供应）
    混合 → 趋近零
    """
    lookback = min(len(history), 5)
    if lookback < 2:
        return 0.0

    recent = list(history)[-lookback:]
    up_count = sum(1 for c in recent if c["close"] > c["open"])
    down_count = lookback - up_count

    # -1 ~ +1 线性映射
    return (up_count - down_count) / lookback


def _exhaustion_score(candle: dict, history: deque) -> float:
    """缩量回调检测：供应/需求枯竭信号。

    缩量回调（下跌但量缩）→ 正（供应枯竭，利多）
    缩量反弹（上涨但量缩）→ 负（需求枯竭，利空）
    """
    if len(history) < 3:
        return 0.0

    close = candle["close"]
    open_ = candle["open"]
    volume = candle["volume"]

    # 对比前一根K线的量
    prev = list(history)[-2]
    prev_volume = prev["volume"]

    if prev_volume <= 0:
        return 0.0

    vol_ratio = volume / prev_volume
    is_shrinking = vol_ratio < 0.7  # 量缩30%以上

    if not is_shrinking:
        return 0.0

    # 缩量下跌 → 供应枯竭 → 正分
    if close < open_:
        shrink_strength = (0.7 - vol_ratio) / 0.7
        return min(shrink_strength, 1.0)

    # 缩量上涨 → 需求枯竭 → 负分
    if close > open_:
        shrink_strength = (0.7 - vol_ratio) / 0.7
        return -min(shrink_strength, 1.0)

    return 0.0
