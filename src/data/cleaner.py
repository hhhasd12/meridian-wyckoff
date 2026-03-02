"""
数据清洗模块

提供安全的数据清洗逻辑，彻底解决 NumPy 警告（除零、NaN 值处理）。

设计原则：
1. 所有计算使用 np.errstate() 包裹，防止警告
2. 默认使用 nanmean/nansum 等安全函数
3. 输入状态机的数据必须是完美的
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _setup_error_handler():
    """设置错误处理装饰器"""
    try:
        from src.utils.error_handler import error_handler

        return error_handler
    except ImportError:

        def error_handler_decorator(**kwargs):
            def decorator(func):
                return func

            return decorator

        return error_handler_decorator


error_handler = _setup_error_handler()


@error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    清洗 DataFrame，处理 NaN 和异常值

    Args:
        df: 输入数据

    Returns:
        清洗后的数据
    """
    if df is None or df.empty:
        return df

    result = df.copy()

    # 填充 NaN
    numeric_cols = result.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        with np.errstate(all="ignore"):
            if result[col].isna().any():
                # 使用前向填充，然后后向填充
                result[col] = result[col].fillna(method="ffill").fillna(method="bfill")
                # 最后用0填充剩余的NaN
                result[col] = result[col].fillna(0)

    return result


@error_handler(logger=logger, reraise=False, default_return=0.0)
def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    安全除法，避免除零警告

    Args:
        numerator: 分子
        denominator: 分母
        default: 默认返回值

    Returns:
        计算结果或默认值
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        if denominator == 0 or np.isnan(denominator):
            return default
        result = numerator / denominator
        if np.isnan(result) or np.isinf(result):
            return default
        return float(result)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def safe_mean(values: List[float]) -> float:
    """
    安全计算平均值，避免 NaN 警告

    Args:
        values: 数值列表

    Returns:
        平均值
    """
    if not values:
        return 0.0

    with np.errstate(all="ignore"):
        arr = np.array(values, dtype=np.float64)
        result = np.nanmean(arr)
        if np.isnan(result):
            return 0.0
        return float(result)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def safe_std(values: List[float]) -> float:
    """
    安全计算标准差

    Args:
        values: 数值列表

    Returns:
        标准差
    """
    if not values or len(values) < 2:
        return 0.0

    with np.errstate(all="ignore"):
        arr = np.array(values, dtype=np.float64)
        result = np.nanstd(arr)
        if np.isnan(result):
            return 0.0
        return float(result)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def safe_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """
    安全计算相关系数，避免除零和无效值警告

    Args:
        x: 第一个数组
        y: 第二个数组

    Returns:
        相关系数 [-1, 1]
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        # 过滤 NaN
        mask = ~(np.isnan(x) | np.isnan(y))
        x_clean = x[mask]
        y_clean = y[mask]

        if len(x_clean) < 2:
            return 0.0

        result = np.corrcoef(x_clean, y_clean)[0, 1]

        if np.isnan(result) or np.isinf(result):
            return 0.0

        return float(result)


@error_handler(logger=logger, reraise=False, default_return={})
def calculate_percentiles(
    values: np.ndarray, percentiles: List[float] = [25, 50, 75]
) -> Dict[str, float]:
    """
    安全计算百分位数

    Args:
        values: 数值数组
        percentiles: 百分位数列表

    Returns:
        百分位数字典
    """
    with np.errstate(all="ignore"):
        # 过滤无效值
        clean_values = values[~np.isnan(values) & ~np.isinf(values)]

        if len(clean_values) == 0:
            return {f"p{p}": 0.0 for p in percentiles}

        result = {}
        for p in percentiles:
            val = np.percentile(clean_values, p)
            result[f"p{p}"] = float(val) if not np.isnan(val) else 0.0

        return result


@error_handler(logger=logger, reraise=False, default_return=0.0)
def safe_rolling_mean(series: pd.Series, window: int) -> float:
    """
    安全计算滚动均值

    Args:
        series: 数据系列
        window: 窗口大小

    Returns:
        滚动均值
    """
    with np.errstate(all="ignore"):
        result = series.rolling(window=window, min_periods=1).mean().iloc[-1]
        if pd.isna(result):
            return 0.0
        return float(result)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def safe_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
) -> float:
    """
    安全计算 ATR (Average True Range)

    Args:
        high: 最高价数组
        low: 最低价数组
        close: 收盘价数组
        period: ATR 周期

    Returns:
        ATR 值
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)

        # 计算 True Range
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))

        # 处理第一个元素的 NaN
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        tr[0] = tr1[0] if not np.isnan(tr1[0]) else 0.0

        # 过滤无效值
        tr = tr[~np.isnan(tr) & ~np.isinf(tr)]

        if len(tr) == 0:
            return 0.0

        # 计算 ATR
        atr = np.mean(tr[-period:])

        if np.isnan(atr) or np.isinf(atr):
            return 0.0

        return float(atr)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def safe_std_dev(values: np.ndarray, period: int = 20) -> float:
    """
    安全计算标准差

    Args:
        values: 数值数组
        period: 计算周期

    Returns:
        标准差
    """
    with np.errstate(all="ignore"):
        clean_values = values[~np.isnan(values) & ~np.isinf(values)]

        if len(clean_values) < period:
            return 0.0

        result = np.std(clean_values[-period:])

        if np.isnan(result) or np.isinf(result):
            return 0.0

        return float(result)


class DataCleaner:
    """
    数据清洗器 - 批量处理数据清洗

    功能：
    1. 一键清洗 DataFrame
    2. 批量处理 OHLCV 数据
    3. 验证数据完整性
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化清洗器

        Args:
            config: 配置字典
        """
        self.config = config or {}
        self._stats = {
            "nan_count": 0,
            "inf_count": 0,
            "negative_count": 0,
            "zero_count": 0,
        }
        logger.info("DataCleaner initialized")

    @error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
    def clean_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗 OHLCV 数据

        Args:
            df: OHLCV DataFrame

        Returns:
            清洗后的数据
        """
        if df is None or df.empty:
            return df

        result = df.copy()
        required_cols = ["open", "high", "low", "close", "volume"]

        # 检查必要列
        for col in required_cols:
            if col not in result.columns:
                logger.warning(f"Missing required column: {col}")
                return df

        # 清洗数值列
        for col in required_cols:
            # 替换 inf
            result[col] = result[col].replace([np.inf, -np.inf], np.nan)
            # 替换负值（对于价格和成交量）
            if col in ["open", "high", "low", "close"]:
                negative_count = (result[col] < 0).sum()
                self._stats["negative_count"] += negative_count
                result[col] = result[col].clip(lower=0)

            # 填充 NaN
            result[col] = (
                result[col].fillna(method="ffill").fillna(method="bfill").fillna(0)
            )

        # 统计
        self._stats["nan_count"] = result[required_cols].isna().sum().sum()
        self._stats["zero_count"] = (result[required_cols] == 0).sum().sum()

        return result

    @error_handler(logger=logger, reraise=False, default_return=True)
    def validate_ohlcv(self, df: pd.DataFrame) -> bool:
        """
        验证 OHLCV 数据有效性

        Args:
            df: OHLCV DataFrame

        Returns:
            是否有效
        """
        if df is None or df.empty:
            return False

        required_cols = ["open", "high", "low", "close", "volume"]

        # 检查列
        for col in required_cols:
            if col not in df.columns:
                return False

        # 检查逻辑关系: high >= low, high >= open, high >= close 等
        with np.errstate(all="ignore"):
            valid = (
                (df["high"] >= df["low"]).all()
                and (df["high"] >= df["open"]).all()
                and (df["high"] >= df["close"]).all()
                and (df["low"] <= df["open"]).all()
                and (df["low"] <= df["close"]).all()
                and (df["volume"] >= 0).all()
            )

        return bool(valid)

    def get_stats(self) -> Dict[str, int]:
        """获取清洗统计"""
        return self._stats.copy()

    def reset_stats(self):
        """重置统计"""
        self._stats = {
            "nan_count": 0,
            "inf_count": 0,
            "negative_count": 0,
            "zero_count": 0,
        }


__all__ = [
    "DataCleaner",
    "calculate_percentiles",
    "safe_ATR",
    "safe_correlation",
    "safe_divide",
    "safe_mean",
    "safe_rolling_mean",
    "safe_std",
    "safe_std_dev",
    "sanitize_dataframe",
]
