"""
OHLCV 数据完整性验证器

对 OHLCV DataFrame 进行结构化验证，返回标准化的验证结果。
不阻止数据处理流程，仅以 WARNING 级别记录异常。
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def validate_ohlcv(df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """验证 OHLCV 数据完整性

    检查项目：
    1. 必需列存在性（open/high/low/close/volume）
    2. high >= max(open, close)
    3. low <= min(open, close)
    4. volume >= 0
    5. 无 NaN 值
    6. 时间索引单调递增

    Args:
        df: 包含 OHLCV 数据的 DataFrame

    Returns:
        Dict 包含:
            - valid: bool — 是否全部通过
            - errors: List[str] — 严重问题
            - warnings: List[str] — 非致命警告
            - rows_checked: int — 检查的行数
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 空 DataFrame 快速返回
    if df is None or df.empty:
        return {
            "valid": False,
            "errors": ["DataFrame 为空或 None"],
            "warnings": [],
            "rows_checked": 0,
        }

    rows_checked = len(df)

    # 1. 检查必需列
    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"缺少必需列: {missing}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "rows_checked": rows_checked,
        }

    # 2. 检查 NaN 值
    nan_counts = df[_REQUIRED_COLUMNS].isna().sum()
    nan_cols = nan_counts[nan_counts > 0]
    if not nan_cols.empty:
        errors.append(f"包含 NaN 值: {nan_cols.to_dict()}")

    # 3. high >= max(open, close)
    oc_max = df[["open", "close"]].max(axis=1)
    high_violations = (df["high"] < oc_max).sum()
    if high_violations > 0:
        warnings.append(f"high < max(open,close) 的行数: {high_violations}")

    # 4. low <= min(open, close)
    oc_min = df[["open", "close"]].min(axis=1)
    low_violations = (df["low"] > oc_min).sum()
    if low_violations > 0:
        warnings.append(f"low > min(open,close) 的行数: {low_violations}")

    # 5. volume >= 0
    neg_volume = (df["volume"] < 0).sum()
    if neg_volume > 0:
        errors.append(f"负成交量行数: {neg_volume}")

    # 6. 时间索引单调递增
    if hasattr(df.index, "is_monotonic_increasing"):
        if not df.index.is_monotonic_increasing:
            warnings.append("时间索引非单调递增")

    valid = len(errors) == 0
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "rows_checked": rows_checked,
    }
