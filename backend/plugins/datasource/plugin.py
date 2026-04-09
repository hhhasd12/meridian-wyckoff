from __future__ import annotations

from pathlib import Path
import logging
from backend.core.types import BackendPlugin
from .routes import create_router
from .local_loader import load_csv, df_to_binary

logger = logging.getLogger(__name__)


class DataSourcePlugin(BackendPlugin):
    id = "datasource"
    name = "数据源"
    version = "0.1.0"

    async def on_init(self, ctx):
        self.ctx = ctx
        data_dir = ctx.config.get("data_dir", "./data")
        self.data_dir = Path(data_dir).resolve()

    async def on_start(self):
        pass

    async def on_stop(self):
        pass

    def get_router(self):
        return create_router(self)

    def load_candles(self, symbol: str, timeframe: str) -> bytes | None:
        """公开方法：供其他插件通过 get_plugin().load_candles() 调用"""
        data_dir = self.data_dir / symbol
        if not data_dir.exists():
            return None
        for ext in [".csv", ".tsv"]:
            fp = data_dir / f"{timeframe}{ext}"
            if fp.exists():
                try:
                    df = load_csv(fp)
                    return df_to_binary(df)
                except Exception as e:
                    logger.error(f"加载数据失败: {fp} — {e}")
                    return None
        return None

    def get_candles_df(self, symbol: str, timeframe: str):
        """公开方法：返回Polars DataFrame，供其他插件调用"""
        data_dir = self.data_dir / symbol
        if not data_dir.exists():
            return None
        for ext in [".csv", ".tsv"]:
            fp = data_dir / f"{timeframe}{ext}"
            if fp.exists():
                try:
                    return load_csv(fp)
                except Exception as e:
                    logger.error("加载数据失败: %s — %s", fp, e)
                    return None
        return None
