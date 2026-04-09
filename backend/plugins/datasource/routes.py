from __future__ import annotations

import logging
from fastapi import APIRouter, Response
from .local_loader import load_csv, df_to_binary

logger = logging.getLogger(__name__)


def create_router(plugin) -> APIRouter:
    router = APIRouter()

    @router.get("/candles/{symbol}/{timeframe}")
    async def get_candles(symbol: str, timeframe: str):
        data_dir = plugin.data_dir / symbol
        if not data_dir.exists():
            return Response(status_code=404, content=f"标的不存在: {symbol}")

        # 尝试多种扩展名
        for ext in [".csv", ".tsv"]:
            fp = data_dir / f"{timeframe}{ext}"
            if fp.exists():
                try:
                    df = load_csv(fp)
                    return Response(
                        content=df_to_binary(df),
                        media_type="application/octet-stream"
                    )
                except Exception as e:
                    logger.error(f"加载数据失败: {fp} — {e}")
                    return Response(status_code=500, content=str(e))

        return Response(status_code=404, content=f"数据不存在: {symbol}/{timeframe}")

    @router.get("/symbols")
    async def get_symbols():
        root = plugin.data_dir
        if not root.exists():
            return []
        result = []
        for d in sorted(root.iterdir()):
            if d.is_dir():
                tfs = sorted(set(
                    f.stem for f in d.iterdir()
                    if f.suffix in (".csv", ".tsv")
                ))
                if tfs:
                    result.append({"symbol": d.name, "timeframes": tfs})
        return result

    return router
