"""回测插件 — 引擎验证与进化评分"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.core.types import BackendPlugin, PluginContext
from .runner import BacktestRunner
from .scorer import BacktestScorer
from .routes import create_router

logger = logging.getLogger(__name__)


class BacktesterPlugin(BackendPlugin):
    id = "backtester"
    name = "Backtester"
    version = "0.1.0"
    dependencies = ("datasource", "engine", "annotation")

    def __init__(self):
        self.ctx: PluginContext | None = None

    async def on_init(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        logger.info("回测插件初始化完成")

    async def on_start(self) -> None:
        logger.info("回测插件启动")

    async def on_stop(self) -> None:
        logger.info("回测插件停止")

    def get_router(self) -> APIRouter:
        return create_router(self)

    def get_subscriptions(self) -> dict:
        return {}  # 回测插件不订阅事件

    async def health_check(self) -> dict:
        return {"status": "ok"}

    async def run_backtest(
        self,
        symbol: str,
        timeframe: str,
        params=None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict:
        """运行一次回测。

        步骤：
        1. 从 datasource 插件获取K线数据（Polars DataFrame → list[dict]）
        2. 从 engine 插件创建隔离引擎实例
        3. 逐根K线运行引擎
        4. 返回回测结果
        """
        if self.ctx is None:
            raise RuntimeError("插件未初始化")

        # 获取K线数据（Polars DataFrame）
        datasource = self.ctx.get_plugin("datasource")
        df = datasource.get_candles_df(symbol, timeframe)
        if df is None:
            raise ValueError(f"K线数据不存在: {symbol}/{timeframe}")

        # 转为 list[dict]，引擎期望每根K线包含 open/high/low/close/volume
        candles = []
        for row in df.iter_rows(named=True):
            candles.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "timestamp": float(row["timestamp"]),
                }
            )

        # 可选时间范围过滤
        if start_time is not None:
            candles = [c for c in candles if c["timestamp"] >= start_time]
        if end_time is not None:
            candles = [c for c in candles if c["timestamp"] <= end_time]

        if not candles:
            raise ValueError(f"过滤后无K线数据: {symbol}/{timeframe}")

        # 创建隔离引擎实例
        engine_plugin = self.ctx.get_plugin("engine")
        instance = engine_plugin.create_isolated_instance(params)

        # 运行回测
        runner = BacktestRunner(instance, candles, symbol, timeframe)
        result = runner.run()

        return result

    async def score_result(
        self,
        result: dict,
        symbol: str,
        timeframe: str,
    ) -> dict:
        """对回测结果评分（vs标注）。

        从 annotation 插件获取标注数据，转换为 scorer 期望的格式后对比。
        """
        if self.ctx is None:
            logger.warning("插件未初始化，跳过评分")
            scorer = BacktestScorer()
            return scorer.score(result, [])

        # 从 annotation 插件获取标注
        annotation_plugin = self.ctx.get_plugin("annotation")
        if annotation_plugin is None:
            logger.warning("annotation 插件不可用，跳过评分")
            scorer = BacktestScorer()
            return scorer.score(result, [])

        from backend.plugins.annotation.drawing_store import DrawingStore

        store = DrawingStore(self.ctx.storage)
        drawings = store.get_all(symbol)

        # 构建 timestamp → bar_index 映射
        # 前端标注点只有 timestamp/value，没有 bar_index，必须反查K线数据
        ds = self.ctx.get_plugin("datasource")
        ts_to_idx: dict[int, int] = {}
        if ds is not None:
            df = ds.get_candles_df(symbol, timeframe)
            if df is not None:
                ts_to_idx = {
                    int(ts): i for i, ts in enumerate(df["timestamp"].to_list())
                }

        # 将 drawings 转为 scorer 期望的标注格式
        # drawing 结构：{"id": ..., "type": ..., "points": [...], "properties": {...}}
        # scorer 期望：{"event_type": str, "bar_index": int, 可选 "phase": str}
        annotations = []
        for d in drawings:
            props = d.get("properties", {})
            event_type = props.get("eventType", "")
            if not event_type:
                continue
            points = d.get("points", [])
            if not points:
                continue
            point = points[0]
            # 用 timestamp 反查 bar_index，查不到则 fallback 0
            ts = int(point.get("timestamp", 0))
            bar_index = ts_to_idx.get(ts, 0)
            ann = {
                "event_type": event_type.lower(),
                "bar_index": bar_index,
            }
            if "phase" in props:
                ann["phase"] = props["phase"]
            annotations.append(ann)

        scorer = BacktestScorer()
        return scorer.score(result, annotations)
