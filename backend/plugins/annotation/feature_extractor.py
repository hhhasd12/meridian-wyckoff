from __future__ import annotations

import logging
import numpy as np
import polars as pl

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """提取标注事件的7维特征"""

    def extract(self, drawing: dict, candles: pl.DataFrame) -> dict:
        """
        输入：一个标注 + 对应的K线数据
        输出：7维特征字典（无eventType时返回空字典）
        """
        event_type = drawing.get("properties", {}).get("eventType")
        if not event_type:
            return {}

        # 找到事件对应的K线位置
        event_time = drawing["points"][0]["time"]
        idx = candles.filter(pl.col("timestamp") <= event_time).height - 1
        if idx < 0:
            return {}

        bar = candles.row(idx, named=True)

        # 1. 量比：当根成交量 / 过去20根均量
        lookback = min(20, idx)
        if lookback > 0:
            avg_vol = candles.slice(idx - lookback, lookback)["volume"].mean()
        else:
            avg_vol = bar["volume"]
        volume_ratio = bar["volume"] / avg_vol if avg_vol > 0 else 1.0

        # 2. 下影线占比
        total_range = bar["high"] - bar["low"]
        if total_range > 0:
            lower_wick = min(bar["open"], bar["close"]) - bar["low"]
            wick_ratio = lower_wick / total_range
        else:
            wick_ratio = 0

        # 3. 实体收盘位置 (0=底, 1=顶)
        if total_range > 0:
            body_position = (bar["close"] - bar["low"]) / total_range
        else:
            body_position = 0.5

        # 4. 距支撑：距近50根最低价的百分比
        lb = min(50, idx)
        if lb > 0:
            recent_low = candles.slice(idx - lb, lb)["low"].min()
        else:
            recent_low = bar["low"]
        support_distance = (bar["low"] - recent_low) / recent_low * 100 if recent_low > 0 else 0

        # 5. 努力回报率：价格变动% / 量比
        price_change = abs(bar["close"] - bar["open"]) / bar["open"] * 100 if bar["open"] > 0 else 0
        effort_result = price_change / volume_ratio if volume_ratio > 0 else 0

        # 6&7. 前序趋势（线性回归）
        tlb = min(50, idx)
        if tlb >= 5:
            closes = candles.slice(idx - tlb, tlb)["close"].to_numpy()
            slope, _ = np.polyfit(np.arange(len(closes)), closes, 1)
            trend_length = tlb
            trend_slope = slope / closes.mean() if closes.mean() > 0 else 0
        else:
            trend_length = 0
            trend_slope = 0.0

        # 后续结果：5/10/20根后的价格变动%
        subsequent = {}
        for ahead in [5, 10, 20]:
            future_idx = idx + ahead
            if future_idx < candles.height:
                future_close = candles.row(future_idx, named=True)["close"]
                pct = (future_close - bar["close"]) / bar["close"] * 100
                subsequent[f"{ahead}bar"] = round(pct, 2)

        return {
            "volume_ratio": round(volume_ratio, 2),
            "wick_ratio": round(wick_ratio, 3),
            "body_position": round(body_position, 3),
            "support_distance": round(support_distance, 2),
            "effort_result": round(effort_result, 3),
            "trend_length": trend_length,
            "trend_slope": round(trend_slope, 6),
            "subsequent_results": subsequent,
        }
