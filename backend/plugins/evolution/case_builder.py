"""案例构建器 — annotation 事件 → EventCase 转换

> ⚠️ 核心算法已移除。此文件为接口占位，保留类结构和方法签名。
> 完整实现仅在本机开发环境可用。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# K线窗口大小
PRE_BARS = 20
POST_BARS = 20


def build_case(
    annotation_event: dict,
    candles: Any | None = None,
    engine_state: dict | None = None,
    params_version: str = "default",
) -> dict:
    """
    从 annotation 事件构建 EventCase。

    annotation_event 格式：
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

    # 核心特征提取逻辑已移除
    case = {
        "id": case_id,
        "event_type": label.lower() if label else "unknown",
        "event_result": "success",
        "symbol": symbol,
        "timeframe": timeframe,
        "source": "annotation",
        "drawing_id": drawing_id,
        "annotation_label": label,
        "weight": 1.0,
        "params_version": params_version,
        "created_at": now,
        # 以下字段在完整版中填充
        "price_extreme": 0.0,
        "price_body": 0.0,
        "penetration_depth": 0.0,
        "recovery_speed": 0.0,
        "position_in_range": 0.0,
        "volume_ratio": 1.0,
        "effort_vs_result": 0.0,
        "pre_bars": "[]",
        "sequence_bars": "[]",
        "post_bars": "[]",
    }

    if points:
        case["price_extreme"] = points[0].get("price", 0.0)
        case["price_body"] = points[0].get("price", 0.0)

    logger.info("案例构建完成: %s %s %s", symbol, timeframe, label)
    return case
