"""测试数据生成器 — OHLCV数据"""

from datetime import datetime, timedelta, timezone
from typing import Dict

import numpy as np
import pandas as pd


def make_ohlcv(
    n: int,
    trend: str = "flat",
    seed: int = 42,
    start_price: float = 100.0,
) -> pd.DataFrame:
    """生成n根OHLCV数据

    Args:
        n: K线数量
        trend: 趋势类型
            "flat"   — 价格在 start_price ± 5% 震荡，成交量稳定
            "up"     — 价格从 start_price 涨到 1.5x，成交量递增
            "down"   — 价格从 1.5x start_price 跌到 start_price，成交量递增
            "spring" — 先跌后涨（模拟威科夫Spring）
        seed: 随机种子（可复现）
        start_price: 起始价格

    Returns:
        DataFrame 包含 open/high/low/close/volume 列，DatetimeIndex
    """
    rng = np.random.RandomState(seed)
    base = start_price

    if trend == "flat":
        closes = base + rng.randn(n).cumsum() * (base * 0.005)
        closes = np.clip(closes, base * 0.9, base * 1.1)
        volumes = 1000 + rng.randint(-200, 200, n)

    elif trend == "up":
        drift = np.linspace(0, base * 0.5, n)
        noise = rng.randn(n).cumsum() * (base * 0.003)
        closes = base + drift + noise
        volumes = np.linspace(800, 1500, n).astype(int) + rng.randint(-100, 100, n)

    elif trend == "down":
        start_high = base * 1.5
        drift = np.linspace(0, -base * 0.5, n)
        noise = rng.randn(n).cumsum() * (base * 0.003)
        closes = start_high + drift + noise
        volumes = np.linspace(800, 1500, n).astype(int) + rng.randint(-100, 100, n)

    elif trend == "spring":
        # 前 60% 下跌，后 40% 反弹
        split = int(n * 0.6)
        down_drift = np.linspace(0, -base * 0.3, split)
        up_drift = np.linspace(0, base * 0.4, n - split)
        drift = np.concatenate([down_drift, down_drift[-1] + up_drift])
        noise = rng.randn(n).cumsum() * (base * 0.002)
        closes = base + drift + noise
        volumes = 1000 + rng.randint(-200, 400, n)
        # Spring 点附近成交量放大
        spring_idx = split - 1
        if spring_idx > 0:
            volumes[max(0, spring_idx - 2) : spring_idx + 3] *= 3

    else:
        raise ValueError(f"Unknown trend type: {trend}")

    # 确保 closes 是正数
    closes = np.maximum(closes, base * 0.1)

    # 生成 OHLC
    spread = np.abs(rng.randn(n)) * (base * 0.005) + base * 0.001
    opens = closes - rng.randn(n) * (base * 0.003)
    highs = np.maximum(closes, opens) + spread
    lows = np.minimum(closes, opens) - spread

    # 确保所有价格正数
    lows = np.maximum(lows, base * 0.05)
    opens = np.maximum(opens, lows)
    closes = np.maximum(closes, lows)
    highs = np.maximum(highs, np.maximum(opens, closes))

    # 确保 volumes 正数
    volumes = np.maximum(volumes, 100)

    # DatetimeIndex（每根K线间隔4小时 — H4）
    start_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    dates = pd.date_range(start=start_time, periods=n, freq="4h")

    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes.astype(float),
        },
        index=dates,
    )
    return df


def make_multi_tf_data(
    h4_bars: int = 200,
    trend: str = "flat",
    seed: int = 42,
) -> Dict[str, pd.DataFrame]:
    """生成时间对齐的多TF数据

    H4: h4_bars 根
    H1: h4_bars * 4 根
    M15: h4_bars * 16 根

    所有TF使用相同趋势方向但独立噪声。

    Args:
        h4_bars: H4级别K线数量
        trend: 趋势类型（同 make_ohlcv）
        seed: 随机种子

    Returns:
        Dict[str, DataFrame] — {"H4": ..., "H1": ..., "M15": ...}
    """
    data: Dict[str, pd.DataFrame] = {}

    # H4
    data["H4"] = make_ohlcv(h4_bars, trend=trend, seed=seed)

    # H1 — 4倍K线数
    h1_bars = h4_bars * 4
    data["H1"] = make_ohlcv(h1_bars, trend=trend, seed=seed + 1)

    # M15 — 16倍K线数
    m15_bars = h4_bars * 16
    data["M15"] = make_ohlcv(m15_bars, trend=trend, seed=seed + 2)

    return data
