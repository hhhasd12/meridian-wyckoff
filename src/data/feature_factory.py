"""
特征工厂模块

提供基础指标计算（如成交量加权均价、量价分布）。

设计原则：
1. 使用安全计算函数避免 NumPy 警告
2. 使用 @error_handler 装饰器
3. 专注于单一职责的特征计算
"""

import logging
from typing import Dict, Tuple

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


@error_handler(logger=logger, reraise=False, default_return=0.0)
def calculate_vwap(df: pd.DataFrame) -> float:
    """
    计算成交量加权均价 (VWAP)
    
    Args:
        df: OHLCV DataFrame
        
    Returns:
        VWAP 值
    """
    if df is None or len(df) == 0:
        return 0.0

    with np.errstate(all="ignore"):
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap = (typical_price * df["volume"]).sum() / df["volume"].sum()

        if np.isnan(vwap) or np.isinf(vwap):
            return 0.0

        return float(vwap)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def calculate_volume_profile(
    df: pd.DataFrame,
    bins: int = 20
) -> Dict[str, float]:
    """
    计算成交量分布
    
    Args:
        df: OHLCV DataFrame
        bins: 分箱数量
        
    Returns:
        成交量分布字典
    """
    if df is None or len(df) == 0:
        return {}

    with np.errstate(all="ignore"):
        price_range = df["high"].max() - df["low"].min()
        if price_range == 0 or np.isnan(price_range):
            return {}

        # 创建价格分箱
        bin_edges = np.linspace(df["low"].min(), df["high"].max(), bins + 1)

        # 计算每个分箱的成交量
        volume_profile = {}
        for i in range(bins):
            mask = (df["close"] >= bin_edges[i]) & (df["close"] < bin_edges[i + 1])
            volume = df.loc[mask, "volume"].sum()
            volume_profile[f"bin_{i}"] = float(volume)

        return volume_profile


@error_handler(logger=logger, reraise=False, default_return=0.0)
def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> float:
    """
    计算 ATR (Average True Range)
    
    Args:
        high: 最高价系列
        low: 最低价系列
        close: 收盘价系列
        period: ATR 周期
        
    Returns:
        ATR 值
    """
    if high is None or low is None or close is None or len(high) < period:
        return 0.0

    with np.errstate(all="ignore"):
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean().iloc[-1]

        if pd.isna(atr) or np.isinf(atr):
            return 0.0

        return float(atr)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def calculate_rsi(
    close: pd.Series,
    period: int = 14
) -> float:
    """
    计算 RSI (Relative Strength Index)
    
    Args:
        close: 收盘价系列
        period: RSI 周期
        
    Returns:
        RSI 值 [0, 100]
    """
    if close is None or len(close) < period + 1:
        return 50.0

    with np.errstate(all="ignore"):
        delta = close.diff()

        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        rsi_value = rsi.iloc[-1]

        if pd.isna(rsi_value) or np.isinf(rsi_value):
            return 50.0

        return float(rsi_value)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def calculate_ema(
    close: pd.Series,
    period: int = 20
) -> float:
    """
    计算 EMA (Exponential Moving Average)
    
    Args:
        close: 收盘价系列
        period: EMA 周期
        
    Returns:
        EMA 值
    """
    if close is None or len(close) < period:
        return 0.0

    with np.errstate(all="ignore"):
        ema = close.ewm(span=period, adjust=False).mean().iloc[-1]

        if pd.isna(ema) or np.isinf(ema):
            return 0.0

        return float(ema)


@error_handler(logger=logger, reraise=False, default_return=0.0)
def calculate_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[float, float, float]:
    """
    计算布林带
    
    Args:
        close: 收盘价系列
        period: 移动平均周期
        std_dev: 标准差倍数
        
    Returns:
        (upper, middle, lower) 布林带值
    """
    if close is None or len(close) < period:
        return (0.0, 0.0, 0.0)

    with np.errstate(all="ignore"):
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        upper_val = upper.iloc[-1]
        middle_val = middle.iloc[-1]
        lower_val = lower.iloc[-1]

        upper_val = upper_val if not (pd.isna(upper_val) or np.isinf(upper_val)) else 0.0
        middle_val = middle_val if not (pd.isna(middle_val) or np.isinf(middle_val)) else 0.0
        lower_val = lower_val if not (pd.isna(lower_val) or np.isinf(lower_val)) else 0.0

        return (float(upper_val), float(middle_val), float(lower_val))


@error_handler(logger=logger, reraise=False, default_return=0.0)
def calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Tuple[float, float, float]:
    """
    计算 MACD
    
    Args:
        close: 收盘价系列
        fast: 快线周期
        slow: 慢线周期
        signal: 信号线周期
        
    Returns:
        (macd, signal, histogram) 值
    """
    if close is None or len(close) < slow:
        return (0.0, 0.0, 0.0)

    with np.errstate(all="ignore"):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        macd = macd_line.iloc[-1]
        sig = signal_line.iloc[-1]
        hist = histogram.iloc[-1]

        macd = macd if not (pd.isna(macd) or np.isinf(macd)) else 0.0
        sig = sig if not (pd.isna(sig) or np.isinf(sig)) else 0.0
        hist = hist if not (pd.isna(hist) or np.isinf(hist)) else 0.0

        return (float(macd), float(sig), float(hist))


class FeatureFactory:
    """
    特征工厂 - 批量计算市场特征
    
    功能：
    1. 一键计算所有基础指标
    2. 返回标准特征字典
    3. 支持自定义指标
    """

    def __init__(self):
        """初始化特征工厂"""
        logger.info("FeatureFactory initialized")

    @error_handler(logger=logger, reraise=False, default_return={})
    def calculate_features(
        self,
        df: pd.DataFrame,
        include_volume: bool = True,
        include_momentum: bool = True
    ) -> Dict[str, float]:
        """
        计算所有特征
        
        Args:
            df: OHLCV DataFrame
            include_volume: 是否包含成交量特征
            include_momentum: 是否包含动量特征
            
        Returns:
            特征字典
        """
        features = {}

        # 基础价格特征
        if "close" in df.columns:
            features["close"] = float(df["close"].iloc[-1])
            features["open"] = float(df["open"].iloc[-1])
            features["high"] = float(df["high"].iloc[-1])
            features["low"] = float(df["low"].iloc[-1])

        # VWAP
        if "volume" in df.columns:
            features["vwap"] = calculate_vwap(df)

        # ATR
        if all(c in df.columns for c in ["high", "low", "close"]):
            features["atr"] = calculate_atr(
                df["high"], df["low"], df["close"]
            )

        # RSI
        if "close" in df.columns and include_momentum:
            features["rsi"] = calculate_rsi(df["close"])

        # EMA
        if "close" in df.columns and include_momentum:
            features["ema_20"] = calculate_ema(df["close"], 20)

        # 布林带
        if "close" in df.columns and include_momentum:
            upper, middle, lower = calculate_bollinger_bands(df["close"])
            features["bb_upper"] = upper
            features["bb_middle"] = middle
            features["bb_lower"] = lower

        # MACD
        if "close" in df.columns and include_momentum:
            macd, signal, hist = calculate_macd(df["close"])
            features["macd"] = macd
            features["macd_signal"] = signal
            features["macd_histogram"] = hist

        # 成交量特征
        if "volume" in df.columns and include_volume:
            features["volume"] = float(df["volume"].iloc[-1])
            features["volume_ma_20"] = float(
                df["volume"].rolling(20).mean().iloc[-1]
            )

            # 成交量分布
            vp = calculate_volume_profile(df)
            features.update(vp)

        return features


__all__ = [
    "FeatureFactory",
    "calculate_atr",
    "calculate_bollinger_bands",
    "calculate_ema",
    "calculate_macd",
    "calculate_rsi",
    "calculate_volume_profile",
    "calculate_vwap",
]
