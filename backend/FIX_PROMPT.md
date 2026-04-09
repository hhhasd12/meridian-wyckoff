# 修复施工提示词— annotation缝隙 + engine 死代码

>2个文件，约55行改动。按顺序执行。

---

## 修复 1：engine/plugin.py — CRITICAL死代码

**文件**：`backend/plugins/engine/plugin.py`
**问题**：`_on_annotation` 方法中 ST 分支，`return` 语句后的所有代码不可达。标注→区间创建主路径完全断裂。

**修复方法**：将 ST 分支中`return` 之后的代码块退缩进一级。

找到 `_on_annotation` 方法中的这段代码（约第170行）：

```python
            elif label == "ST":
                # 莱恩标注了ST → 如果有候选+AR → 创建区间
                candidate = self.range_engine.candidate_extreme
                ar = engine_state.ar_anchor
                if candidate is None or ar is None:
                    logger.warning(
                        "ST标注忽略：缺少SC候选或AR锚点 (candidate=%s, ar=%s)",
                        candidate is not None,
                        ar is not None,
                    )
                    returnst_anchor = AnchorPoint(
                        bar_index=bar_idx,
                        extreme_price=price,
                        body_price=price,
                        volume=0,
                    )
                    new_range = self.range_engine.create_range(
                        candidate, ar, st_anchor, engine_state.direction
                    )
                    new_range.timeframe = tf
                    engine_state.active_range = new_range
                    engine_state.current_phase = Phase.B
                    # 清理
                    self.range_engine.candidate_extreme = None
                    engine_state.ar_anchor = None
                    engine_state.candidate_extreme = None
                    logger.info(
                        "标注→区间创建: range_id=%s, phase=B",
                        new_range.range_id[:8],
                    )
                    if self.ctx:
                        await self.ctx.event_bus.publish(
                            "engine.range_created",
                            {"symbol": symbol, "timeframe": tf, "range": new_range},
                        )
```

替换为（注意 `st_anchor` 开始的代码退缩进一级，与 `if candidate is None` 同级）：

```python
            elif label == "ST":
                # 莱恩标注了ST → 如果有候选+AR → 创建区间
                candidate = self.range_engine.candidate_extreme
                ar = engine_state.ar_anchor
                if candidate is None or ar is None:
                    logger.warning(
                        "ST标注忽略：缺少SC候选或AR锚点 (candidate=%s, ar=%s)",
                        candidate is not None,
                        ar is not None,
                    )
                    return
                st_anchor = AnchorPoint(
                    bar_index=bar_idx,
                    extreme_price=price,
                    body_price=price,
                    volume=0,
                )
                new_range = self.range_engine.create_range(
                    candidate, ar, st_anchor, engine_state.direction
                )
                new_range.timeframe = tf
                engine_state.active_range = new_range
                engine_state.current_phase = Phase.B
                # 清理
                self.range_engine.candidate_extreme = None
                engine_state.ar_anchor = None
                engine_state.candidate_extreme = None
                logger.info(
                    "标注→区间创建: range_id=%s, phase=B",
                    new_range.range_id[:8],
                )
                if self.ctx:
                    await self.ctx.event_bus.publish(
                        "engine.range_created",
                        {"symbol": symbol, "timeframe": tf, "range": new_range},
                    )
```

**改动量**：~15行只改缩进，0行新增。

---

## 修复 2：annotation/routes.py — 完整替换

**文件**：`backend/plugins/annotation/routes.py`
**问题**：三个缝隙
1. `from .local_loader import load_csv_from_binary` — annotation包内无此模块，运行时ImportError
2. 事件载荷无 symbol/timeframe — engine 收到后无法定位状态
3. 特征未自动提取 — create/update 保存后跳过特征提取

**修复方法**：完整替换 routes.py 内容。

```python
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Response
from .drawing_store import DrawingStore
from .feature_extractor import FeatureExtractor

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {
    "trend_line", "parallel_channel", "horizontal_line",
    "vertical_line", "rectangle", "callout", "phase_marker",
}


def _build_event_payload(symbol: str, drawing: dict) -> dict:
    """构建结构化事件载荷，对齐 engine._on_annotation 期望格式"""
    props = drawing.get("properties", {})
    return {
        "drawing_id": drawing.get("id", ""),
        "drawing_type": drawing.get("type", ""),
        "symbol": symbol,
        "timeframe": props.get("timeframe", ""),
        "label": props.get("eventType", ""),
        "points": drawing.get("points", []),
        "metadata": props,
    }


def _try_auto_features(plugin, symbol: str, drawing: dict,
                       extractor: FeatureExtractor, store: DrawingStore) -> dict:
    """best-effort 自动特征提取：成功→存入 drawing，失败→静默跳过"""
    props = drawing.get("properties", {})
    if not props.get("eventType"):
        return drawing  # 非事件标注，跳过
    datasource = plugin.ctx.get_plugin("datasource")
    if not datasource:
        return drawing
    tf = props.get("timeframe", "1d")
    try:
        candles = datasource.get_candles_df(symbol, tf)if candles is not None:
            features = extractor.extract(drawing, candles)
            if features:
                drawing["auto_features"] = features
                store.update(symbol, drawing["id"], {"auto_features": features})
    except Exception as e:
        logger.warning("自动特征提取失败: %s", e)
    return drawing


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
        # 输入验证
        if not drawing.get("id"):
            return Response(status_code=400, content="缺少字段: id")
        if not drawing.get("type"):
            return Response(status_code=400, content="缺少字段: type")
        if not isinstance(drawing.get("points"), list) or len(drawing["points"]) == 0:
            return Response(status_code=400, content="缺少或无效字段: points")
        if drawing["type"] not in ALLOWED_TYPES:
            return Response(status_code=400, content=f"不支持的标注类型: {drawing['type']}")

        result = store.create(symbol, drawing)
        # 自动特征提取（best-effort）
        result = _try_auto_features(plugin, symbol, result, extractor, store)
        # 发布结构化事件（含symbol）
        await plugin.ctx.event_bus.publish("annotation.created", _build_event_payload(symbol, result))
        return result

    @router.put("/drawings/{symbol}/{drawing_id}")
    async def update_drawing(symbol: str, drawing_id: str, request: Request):
        updates = await request.json()
        result = store.update(symbol, drawing_id, updates)
        if result:
            result = _try_auto_features(plugin, symbol, result, extractor, store)
            await plugin.ctx.event_bus.publish("annotation.updated", _build_event_payload(symbol, result))return result
        return Response(status_code=404, content="标注不存在")

    @router.delete("/drawings/{symbol}/{drawing_id}")
    async def delete_drawing(symbol: str, drawing_id: str):
        if store.delete(symbol, drawing_id):
            await plugin.ctx.event_bus.publish("annotation.deleted", {
                "drawing_id": drawing_id, "symbol": symbol,
            })
            return {"ok": True}
        return Response(status_code=404, content="标注不存在")

    @router.get("/features/{symbol}/{drawing_id}")
    async def get_features(symbol: str, drawing_id: str):
        """获取标注的7维特征"""
        drawings = store.get_all(symbol)
        drawing = next((d for d in drawings if d["id"] == drawing_id), None)
        if not drawing:
            return Response(status_code=404, content="标注不存在")

        # 如果已有缓存特征，直接返回
        if drawing.get("auto_features"):
            return {"features": drawing["auto_features"]}

        datasource = plugin.ctx.get_plugin("datasource")
        if not datasource:
            return {"features": {}, "error": "datasource插件不可用"}

        timeframe = drawing.get("properties", {}).get("timeframe", "1d")
        try:
            # 直接获取 DataFrame，不再通过 binary 转换
            candles = datasource.get_candles_df(symbol, timeframe)
            if candles is None:
                return {"features": {}, "error": "K线数据不存在"}
            features = extractor.extract(drawing, candles)
            return {"features": features}
        except Exception as e:
            logger.error("特征提取失败: %s", e)
            return {"features": {}, "error": str(e)}

    return router
```

**改动量**：完整替换，约95行。

---

## 验证

修复完成后验证：

1. **启动不报错**：`python -m backend.main` 正常启动，无ImportError
2. **annotation 事件载荷**：POST 创建标注后，检查事件总线发布的数据包含 `symbol` 和 `timeframe` 字段
3. **特征自动提取**：创建带`eventType` 的标注后，返回的drawing 包含 `auto_features` 字段
4. **engine ST 标注**：模拟 annotation.created 事件（label=ST），engine 能创建区间（不再静默跳过）