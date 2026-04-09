"""案例构建器 — annotation 事件 → EventCase 转换"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

# K线窗口大小
PRE_BARS = 20
POST_BARS = 20


def build_case(
    annotation_event: dict,
    candles: pl.DataFrame | None,
    engine_state: dict | None = None,
    params_version: str = "default",
) -> dict:
    """
    从 annotation 事件构建 EventCase。

    annotation_event 格式（与 engine._on_annotation 期望的一致）：
    {
        "drawing_id": "uuid",
        "drawing_type": "callout",
        "symbol": "ETHUSDT",
        "timeframe": "1d",
        "label": "SC",
        "points": [{"time": 1234567890, "bar_index": 100, "price": 1500.0}],
        "metadata": {...}
    }
    """
    case_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    symbol = annotation_event.get("symbol", "")
    timeframe = annotation_event.get("timeframe", "")
    label = annotation_event.get("label", "").upper()
    drawing_id = annotation_event.get("drawing_id", "")
    points = annotation_event.get("points", [])
    metadata = annotation_event.get("metadata", {})

    event_type = _normalize_event_type(label)

    case: dict[str, Any] = {
        "id": case_id,
        "event_type": event_type,
        "event_result": "success",  # 莱恩标注默认成功
        "symbol": symbol,
        "timeframe": timeframe,
        "source": "annotation",
        "drawing_id": drawing_id,
        "annotation_label": label,
        "weight": 1.0,
        "params_version": params_version,
        "created_at": now,
    }

    # 定位事件K线
    if not points or candles is None or candles.height == 0:
        return case

    event_time = points[0].get("time", 0)
    price = points[0].get("price", 0)

    # 找到事件K线索引
    idx = candles.filter(pl.col("timestamp") <= event_time).height - 1
    if idx < 0:
        idx = 0

    bar = candles.row(idx, named=True)

    # ─── 时序定位 ───
    case["sequence_start_bar"] = idx
    case["sequence_end_bar"] = idx
    case["sequence_length"] = 1

    # ─── 7维价格特征 ───
    case["price_extreme"] = price
    case["price_body"] = bar.get("close", price)

    # penetration_depth: 需要区间宽度（有活跃区间时才计算）
    case["penetration_depth"] = None
    case["recovery_speed"] = None

    # position_in_range: 需要区间上下界
    case["position_in_range"] = None

    # volume_ratio
    lookback = min(20, idx)
    if lookback > 0:
        avg_vol = float(candles.slice(idx - lookback, lookback)["volume"].mean())  # type: ignore[arg-type]
    else:
        avg_vol = float(bar.get("volume", 0))
    vol = bar.get("volume", 0)
    avg_vol_f = float(avg_vol) if avg_vol is not None else 0.0
    vol_f = float(vol)
    case["volume_ratio"] = vol_f / avg_vol_f if avg_vol_f > 0 else 1.0

    # effort_vs_result
    price_change = abs(float(bar.get("close", 0)) - float(bar.get("open", 0)))
    total_vol = vol_f
    open_f = float(bar.get("open", 0))
    if total_vol > 0 and open_f > 0:
        efficiency = (
            price_change / open_f / (total_vol / (avg_vol_f if avg_vol_f > 0 else 1.0))
        )
        case["effort_vs_result"] = float(np.clip(efficiency - 1.0, -1.0, 1.0))
    else:
        case["effort_vs_result"] = 0.0

    # ─── 上下文特征 ───
    # trend_slope / trend_length（前序50根线性回归）
    tlb = min(50, idx)
    if tlb >= 5:
        closes = candles.slice(idx - tlb, tlb)["close"].to_numpy()
        slope, _ = np.polyfit(np.arange(len(closes)), closes, 1)
        case["trend_slope"] = float(slope / closes.mean()) if closes.mean() > 0 else 0.0
        case["trend_length"] = tlb
    else:
        case["trend_slope"] = 0.0
        case["trend_length"] = 0

    # support_distance
    lb = min(50, idx)
    if lb > 0:
        recent_low = float(candles.slice(idx - lb, lb)["low"].min())  # type: ignore[arg-type]
    else:
        recent_low = float(bar.get("low", price))
    case["support_distance"] = (
        (float(bar.get("low", price)) - recent_low) / recent_low * 100
        if recent_low > 0
        else 0.0
    )

    # wick_ratio
    total_range = float(bar.get("high", 0)) - float(bar.get("low", 0))
    if total_range > 0:
        lower_wick = min(float(bar.get("open", 0)), float(bar.get("close", 0))) - float(
            bar.get("low", 0)
        )
        case["wick_ratio"] = lower_wick / total_range
    else:
        case["wick_ratio"] = 0.0

    # body_position
    if total_range > 0:
        case["body_position"] = (
            float(bar.get("close", 0)) - float(bar.get("low", 0))
        ) / total_range
    else:
        case["body_position"] = 0.5

    # ─── 区间上下文（从 engine_state） ───
    if engine_state:
        active_range = engine_state.get("active_range")
        case["range_id"] = active_range.get("range_id", "") if active_range else None
        case["phase"] = engine_state.get("current_phase")
        case["direction"] = engine_state.get("direction")
        case["structure_type"] = engine_state.get("structure_type")
        case["range_width"] = None  # 需要活跃区间

        # EVD-10: prior_events — 区间内已发生事件的类型列表
        recent_events = engine_state.get("recent_events", [])
        if recent_events:
            seen: set[str] = set()
            prior: list[str] = []
            for ev in recent_events:
                et = ev.get("event_type", "") if isinstance(ev, dict) else str(ev)
                if et and et != event_type and et not in seen:
                    seen.add(et)
                    prior.append(et)
            case["prior_events"] = json.dumps(prior, ensure_ascii=False)
        else:
            case["prior_events"] = None
    else:
        case["range_id"] = None
        case["phase"] = None
        case["direction"] = None
        case["structure_type"] = None
        case["range_width"] = None
        case["prior_events"] = None

    # ─── K线快照 ───
    pre_start = max(0, idx - PRE_BARS)
    case["pre_bars"] = _bars_to_json(candles, pre_start, idx - pre_start)

    case["sequence_bars"] = _bars_to_json(candles, idx, 1)

    post_end = min(candles.height, idx + 1 + POST_BARS)
    case["post_bars"] = _bars_to_json(candles, idx + 1, post_end - idx - 1)

    # ─── 后续结果 ───
    event_close = float(bar.get("close", 0))
    for ahead in (5, 10, 20):
        future_idx = idx + ahead
        key = f"result_{ahead}bar"
        if future_idx < candles.height:
            future_close = float(candles.row(future_idx, named=True)["close"])
            case[key] = (
                round((future_close - event_close) / event_close * 100, 4)
                if event_close > 0
                else None
            )
        else:
            case[key] = None

    return case


def _normalize_event_type(label: str) -> str:
    """标准化事件类型标签 → 小写"""
    mapping = {
        "SC": "sc",
        "BC": "bc",
        "AR": "ar",
        "ST": "st",
        "ST-B": "st_b",
        "UT": "ut",
        "UTA": "uta",
        "SPRING": "spring",
        "SO": "so",
        "UTAD": "utad",
        "LPS": "lps",
        "LPSY": "lpsy",
        "BU": "bu",
        "SOS": "sos",
        "SOW": "sow",
        "JOC": "joc",
        "BREAK_ICE": "break_ice",
        "MSOS": "msos",
        "MSOW": "msow",
        "PS": "ps",
        "PSY": "psy",
    }
    return mapping.get(label.upper(), label.lower())


def _bars_to_json(candles: pl.DataFrame, start: int, length: int) -> list[dict]:
    """将K线切片转为 [{t, o, h, l, c, v}, ...] 格式"""
    if length <= 0 or start < 0 or start >= candles.height:
        return []
    end = min(start + length, candles.height)
    result = []
    for i in range(start, end):
        row = candles.row(i, named=True)
        result.append(
            {
                "t": int(row.get("timestamp", 0)),
                "o": float(row.get("open", 0)),
                "h": float(row.get("high", 0)),
                "l": float(row.get("low", 0)),
                "c": float(row.get("close", 0)),
                "v": float(row.get("volume", 0)),
            }
        )
    return result
