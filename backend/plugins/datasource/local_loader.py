from __future__ import annotations

import logging
import polars as pl
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_timestamp(col: pl.Series) -> pl.Series:
    first = col[0] if len(col) > 0 else None
    if first is None:
        return col.cast(pl.Float64)

    try:
        return col.cast(pl.Float64)
    except Exception:
        pass

    # 尝试多种日期格式
    formats = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt_col = col.str.to_datetime(fmt, time_unit="us")
            return dt_col.dt.epoch("ms").cast(pl.Float64)
        except Exception:
            continue

    logger.warning(f"无法解析timestamp格式，原始值示例: {first}")
    raise ValueError(f"不支持的timestamp格式: {first}")


def load_csv(filepath: Path) -> pl.DataFrame:
    """读取 CSV/TSV，自动识别分隔符，自动映射列名"""
    try:
        df = pl.read_csv(filepath, separator="\t")
        if len(df.columns) <= 1:
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

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"缺少必要列: {col}，文件: {filepath}")

    # W8: 安全解析 timestamp 列
    df = df.with_columns(_parse_timestamp(df["timestamp"]).alias("timestamp"))

    return df.select(required)


def load_csv_from_binary(raw_binary: bytes) -> pl.DataFrame:
    """从二进制数据反序列化为 DataFrame（供其他插件使用）"""
    arr = np.frombuffer(raw_binary, dtype=np.float64).reshape(-1, 6)
    df = pl.DataFrame(
        {
            "timestamp": arr[:, 0],
            "open": arr[:, 1],
            "high": arr[:, 2],
            "low": arr[:, 3],
            "close": arr[:, 4],
            "volume": arr[:, 5],
        }
    )
    return df


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
