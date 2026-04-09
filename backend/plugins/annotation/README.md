# annotation 插件 — 标注

## 做什么
管理用户在 K 线图上画的所有标注，持久化到 JSON 文件，并对事件类标注提取 7 维特征。

## API 端点

### GET /api/annotation/drawings/{symbol}
获取某个标的的所有标注。返回 JSON 数组。

### POST /api/annotation/drawings/{symbol}
创建标注。请求体为 Drawing JSON。创建后发布 `annotation.created` 事件。

### PUT /api/annotation/drawings/{symbol}/{drawing_id}
更新标注。发布 `annotation.updated` 事件。

### DELETE /api/annotation/drawings/{symbol}/{drawing_id}
删除标注。发布 `annotation.deleted` 事件。

### GET /api/annotation/features/{symbol}/{drawing_id}
提取指定标注的 7 维特征（仅对有eventType 的标注有效）。

响应示例：
```json
{
  "features": {
    "volume_ratio": 3.5,
    "wick_ratio": 0.65,
    "body_position": 0.15,
    "support_distance": 0.8,
    "effort_result": 0.042,
    "trend_length": 35,
    "trend_slope": -0.0023,
    "subsequent_results": {"5bar": -2.1, "10bar": 1.5, "20bar": 4.3}
  }
}
```

## 7维特征说明
| 维度 | 含义 | 计算方式 |
|------|------|----------|
| volume_ratio | 量比 | 当根成交量 / 过去20根均量 |
| wick_ratio | 下影线占比 | 下影线长度 / K线总长度 |
| body_position | 实体收盘位置 | 0=最底, 1=最顶 |
| support_distance | 距支撑距离 | 距近50根最低价的百分比 |
| effort_result | 努力回报率 | 价格变动% / 量比 |
| trend_length | 前序趋势长度 | 回溯多少根K线 |
| trend_slope | 前序趋势斜率 | 线性回归斜率（归一化） |

## 完整代码

### 1. __init__.py
空文件

### 2. plugin.py

```python
from __future__ import annotations

from backend.core.types import BackendPlugin
from .routes import create_router


class AnnotationPlugin(BackendPlugin):
    id = "annotation"
    name = "标注"
    version = "0.1.0"

    async def on_init(self, ctx):
        self.ctx = ctx
        self.storage = ctx.storage

    async def on_start(self):
        pass

    async def on_stop(self):
        pass

    def get_router(self):
        return create_router(self)
```

### 3. drawing_store.py

```python
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DrawingStore:
    def __init__(self, storage):
        self.storage = storage

    def get_all(self, symbol: str) -> list:
        """获取某标的的所有标注"""
        return self.storage.read_json("drawings", symbol) or []

    def save_all(self, symbol: str, drawings: list) -> None:
        """保存所有标注（原子写入）"""
        self.storage.write_json("drawings", symbol, drawings)

    def create(self, symbol: str, drawing: dict) -> dict:
        """创建标注"""
        ds = self.get_all(symbol)
        ds.append(drawing)
        self.save_all(symbol, ds)
        logger.info(f"创建标注: {symbol} / {drawing.get('id', '?')}")
        return drawing

    def update(self, symbol: str, drawing_id: str, updates: dict) -> dict | None:
        """更新标注，返回更新后的标注，不存在返回None"""
        ds = self.get_all(symbol)
        for i, d in enumerate(ds):
            if d["id"] == drawing_id:
                ds[i] = {**d, **updates}
                self.save_all(symbol, ds)
                logger.info(f"更新标注: {symbol} / {drawing_id}")
                return ds[i]
        return None

    def delete(self, symbol: str, drawing_id: str) -> bool:
        """删除标注，返回是否成功"""
        ds = self.get_all(symbol)
        new = [d for d in ds if d["id"] != drawing_id]
        if len(new) < len(ds):
            self.save_all(symbol, new)
            logger.info(f"删除标注: {symbol} / {drawing_id}")
            return True
        return False
```

### 4. feature_extractor.py

```python
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
```

### 5. routes.py

```python
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Response
from .drawing_store import DrawingStore
from .feature_extractor import FeatureExtractor

logger = logging.getLogger(__name__)


def create_router(plugin) -> APIRouter:
    router = APIRouter()
    store = DrawingStore(plugin.storage)
    extractor = FeatureExtractor()

    @router.get("/drawings/{symbol}")
    async def get_drawings(symbol: str):
        return store.get_all(symbol)

    @router.post("/drawings/{symbol}")
    async def create_drawing(symbol: str, request: Request):
        drawing = await request.json()
        result = store.create(symbol, drawing)
        await plugin.ctx.event_bus.publish("annotation.created", result)
        return result

    @router.put("/drawings/{symbol}/{drawing_id}")
    async def update_drawing(symbol: str, drawing_id: str, request: Request):
        updates = await request.json()
        result = store.update(symbol, drawing_id, updates)
        if result:
            await plugin.ctx.event_bus.publish("annotation.updated", result)
            return result
        return Response(status_code=404, content="标注不存在")

    @router.delete("/drawings/{symbol}/{drawing_id}")
    async def delete_drawing(symbol: str, drawing_id: str):
        if store.delete(symbol, drawing_id):
            await plugin.ctx.event_bus.publish("annotation.deleted", {"id": drawing_id})
            return {"ok": True}
        return Response(status_code=404, content="标注不存在")

    @router.get("/features/{symbol}/{drawing_id}")
    async def get_features(symbol: str, drawing_id: str):
        """获取标注的7维特征"""
        # 找到标注
        drawings = store.get_all(symbol)
        drawing = next((d for d in drawings if d["id"] == drawing_id), None)
        if not drawing:
            return Response(status_code=404, content="标注不存在")

        # 获取K线数据（通过datasource插件）
        datasource = plugin.ctx.get_plugin("datasource")
        if not datasource:
            return {"features": {}, "error": "datasource插件不可用"}

        timeframe = drawing.get("properties", {}).get("timeframe", "1d")
        try:
            from backend.plugins.datasource.local_loader import load_csv
            data_dir = datasource.data_dir / symbol
            fp = None
            for ext in [".csv", ".tsv"]:
                candidate = data_dir / f"{timeframe}{ext}"
                if candidate.exists():
                    fp = candidate
                    break

            if not fp:
                return {"features": {}, "error": "K线数据不存在"}

            candles = load_csv(fp)
            features = extractor.extract(drawing, candles)
            return {"features": features}
        except Exception as e:
            logger.error(f"特征提取失败: {e}")
            return {"features": {}, "error": str(e)}

    return router
```

## 存储结构
```
backend/storage/drawings/
├── ETHUSDT.json← 该标的所有标注的数组
├── BTCUSDT.json
└── ...
```

## 依赖
- numpy（线性回归）
- polars（数据切片）
- 运行时依赖 datasource 插件（特征提取需要K线数据）