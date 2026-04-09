# datasource 插件 — 数据源

## 做什么
加载本地 CSV/TSV 格式的 K 线数据，转成二进制格式传给前端。

## 数据目录结构
```
data/
├── ETHUSDT/
│   ├── 5m.csv
│   ├── 15m.csv
│   ├── 1h.csv
│   ├── 4h.csv
│   └── 1d.csv
├── BTCUSDT/
│   └── 1d.csv
└── ...
```

## API 端点

### GET /api/datasource/candles/{symbol}/{timeframe}
返回二进制 K 线数据。`application/octet-stream`

每根 K 线 = 6 个 float64 = 48 字节：`[timestamp, open, high, low, close, volume]`
- timestamp：毫秒级 Unix 时间戳
- 前端解析：`new Float64Array(arrayBuffer)`，每6 个元素为一根 K 线

### GET /api/datasource/symbols
返回所有可用标的及其周期列表。JSON 格式：
```json
[
  {"symbol": "ETHUSDT", "timeframes": ["5m", "15m", "1h", "4h", "1d"]},
  {"symbol": "BTCUSDT", "timeframes": ["1d"]}
]
```

## 完整代码

###1. __init__.py
空文件

### 2. plugin.py

```python
from __future__ import annotations

from pathlib import Path
from backend.core.types import BackendPlugin
from .routes import create_router


class DataSourcePlugin(BackendPlugin):
    id = "datasource"
    name = "数据源"
    version = "0.1.0"

    async def on_init(self, ctx):
        self.ctx = ctx
        # 从全局配置读取数据目录，默认 ./data
        data_dir = ctx.config.get("data_dir", "./data")
        self.data_dir = Path(data_dir).resolve()

    async def on_start(self):
        pass

    async def on_stop(self):
        pass

    def get_router(self):
        return create_router(self)
```

### 3. local_loader.py

```python
from __future__ import annotations

import logging
import polars as pl
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)


def load_csv(filepath: Path) -> pl.DataFrame:
    """读取 CSV/TSV，自动识别分隔符，自动映射列名"""
    #尝试 tab 分隔，失败则用逗号
    try:
        df = pl.read_csv(filepath, separator="\t")if len(df.columns) <= 1:
            df = pl.read_csv(filepath, separator=",")
    except Exception:
        df = pl.read_csv(filepath, separator=",")

    # 列名自动映射（不区分大小写）
    col_map = {}
    for col in df.columns:
        lo = col.lower().strip()
        if "time" in lo or "date" in lo:
            col_map[col] = "timestamp"
        elif lo in ("open", "o"):
            col_map[col] = "open"
        elif lo in ("high", "h"):
            col_map[col] = "high"
        elif lo in ("low", "l"):
            col_map[col] = "low"
        elif lo in ("close", "c"):
            col_map[col] = "close"
        elif "vol" in lo:
            col_map[col] = "volume"

    df = df.rename(col_map)

    # 确保必要列存在
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"缺少必要列: {col}，文件: {filepath}")

    return df.select(required)


def df_to_binary(df: pl.DataFrame) -> bytes:
    """DataFrame → 二进制（6个float64 × N根K线）"""
    arr = np.column_stack([
        df["timestamp"].cast(pl.Float64).to_numpy(),
        df["open"].cast(pl.Float64).to_numpy(),
        df["high"].cast(pl.Float64).to_numpy(),
        df["low"].cast(pl.Float64).to_numpy(),
        df["close"].cast(pl.Float64).to_numpy(),
        df["volume"].cast(pl.Float64).to_numpy(),
    ])
    return arr.tobytes()
```

### 4. routes.py

```python
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
                    if f.suffix in(".csv", ".tsv")
                ))
                if tfs:
                    result.append({"symbol": d.name, "timeframes": tfs})
        return result

    return router
```

## 依赖
- polars（数据加载）
- numpy（二进制转换）