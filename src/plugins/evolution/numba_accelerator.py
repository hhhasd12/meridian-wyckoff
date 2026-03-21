"""Numba 向量化加速器 — 三层 Pass 架构

将进化回测中的热路径从纯 Python 加速到接近原生速度：

Pass 1 (NumPy 向量化): precompute_features()
    预计算所有无状态特征 (ATR/ADX/volume_ratio/body_ratio/shadow 等)。
    所有 GA 个体共用同一份特征数组，每轮进化只计算一次。

Pass 2 (Numba @njit): state_machine_numba()
    22+5 节点状态机编译为机器码。状态用 int 编码，转换逻辑用数值比较。
    不同 GA 个体只是 config 参数不同，特征数组相同。

Pass 3 (Numba @njit): vectorized_backtest()
    回测引擎编译为机器码。输入信号/置信度/价格数组，输出 equity curve。

性能预估 (2000 根 H4):
    Pass 1: 0.1ms (vs 纯 Python 50ms, 500x)
    Pass 2: 0.5ms (vs 纯 Python 50ms, 100x)
    Pass 3: 0.1ms (vs 纯 Python 20ms, 200x)
"""

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

HAS_NUMBA: bool = False

try:
    from numba import njit

    HAS_NUMBA = True
except (ImportError, ModuleNotFoundError):
    # Fallback: njit 装饰器变为 identity（纯 Python 运行）
    def njit(*args, **kwargs):  # type: ignore[no-redef]
        """Fallback njit — 不做任何编译，直接返回原函数"""
        if len(args) == 1 and callable(args[0]):
            return args[0]

        def wrapper(func):  # type: ignore[no-untyped-def]
            return func

        return wrapper


logger = logging.getLogger(__name__)


# ================================================================
# 状态编码常量 — @njit 中不能用 dict/string，全部用 int
# ================================================================

# 吸筹阶段 (Accumulation)
STATE_IDLE = 0
STATE_PS = 1  # Preliminary Support
STATE_SC = 2  # Selling Climax
STATE_AR = 3  # Automatic Rally
STATE_ST = 4  # Secondary Test
STATE_TEST = 5  # Test of SC low
STATE_UTA = 6  # Upthrust Action (in accumulation)
STATE_SPRING = 7  # Spring / Shakeout
STATE_SO = 8  # Sign of Strength (Spring follow-through)
STATE_LPS = 9  # Last Point of Support
STATE_MSOS = 10  # minor Sign of Strength
STATE_MAJOR_SOS = 11  # Major Sign of Strength
STATE_JOC = 12  # Jump Over Creek (breakout)
STATE_BU = 13  # Back Up to Creek

# 派发阶段 (Distribution)
STATE_PSY = 14  # Preliminary Supply
STATE_BC = 15  # Buying Climax
STATE_AR_DIST = 16  # Automatic Reaction (distribution)
STATE_ST_DIST = 17  # Secondary Test (distribution)
STATE_UT = 18  # Upthrust
STATE_UTAD = 19  # Upthrust After Distribution
STATE_LPSY = 20  # Last Point of Supply
STATE_MSOW = 21  # minor Sign of Weakness
STATE_MAJOR_SOW = 22  # Major Sign of Weakness

# 趋势阶段
STATE_UPTREND = 23
STATE_DOWNTREND = 24
STATE_RE_ACCUMULATION = 25
STATE_RE_DISTRIBUTION = 26

# 信号常量
SIGNAL_HOLD = 0
SIGNAL_BUY = 1
SIGNAL_SELL = -1


# ================================================================
# NumPy 向量化辅助函数 (Pass 1 用)
# ================================================================


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """滚动均值 — 纯 NumPy 向量化

    Args:
        arr: 输入数组
        window: 窗口大小

    Returns:
        滚动均值数组（前 window-1 个元素用累积均值填充）
    """
    n = len(arr)
    result = np.empty(n, dtype=np.float64)
    cumsum = np.cumsum(arr)

    # 前 window 个元素：累积均值
    for i in range(min(window, n)):
        result[i] = cumsum[i] / (i + 1)

    # window 之后：标准滚动均值
    if n > window:
        result[window:] = (cumsum[window:] - cumsum[:-window]) / window

    return result


def _vectorized_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """向量化 ATR (Average True Range)

    Args:
        high: 最高价数组
        low: 最低价数组
        close: 收盘价数组
        period: ATR 周期

    Returns:
        ATR 数组
    """
    n = len(close)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]

    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    return _rolling_mean(tr, period)


def _vectorized_adx(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """向量化 ADX (Average Directional Index)

    简化版 ADX：使用 DI+/DI- 的差异比来衡量趋势强度。
    范围 [0, 100]。

    Args:
        high: 最高价数组
        low: 最低价数组
        close: 收盘价数组
        period: ADX 周期

    Returns:
        ADX 数组（[0, 100]）
    """
    n = len(close)
    if n < period + 1:
        return np.zeros(n, dtype=np.float64)

    # Directional Movement
    up_move = np.diff(high, prepend=high[0])
    down_move = np.diff(-low, prepend=-low[0])

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr = _vectorized_atr(high, low, close, period)
    atr_safe = np.where(atr > 1e-10, atr, 1e-10)

    plus_di = _rolling_mean(plus_dm, period) / atr_safe * 100.0
    minus_di = _rolling_mean(minus_dm, period) / atr_safe * 100.0

    di_sum = plus_di + minus_di
    di_sum_safe = np.where(di_sum > 1e-10, di_sum, 1e-10)
    dx = np.abs(plus_di - minus_di) / di_sum_safe * 100.0

    adx = _rolling_mean(dx, period)
    return np.clip(adx, 0.0, 100.0)


# ================================================================
# Pass 1: 特征预计算 — NumPy 向量化
# ================================================================


def precompute_features(
    data_dict: Dict[str, pd.DataFrame],
) -> Dict[str, np.ndarray]:
    """一次性预计算所有无状态特征，返回 numpy 数组

    所有 GA 个体共用同一份特征数组。特征值不依赖 config 参数，
    只有权重/阈值在个体间不同。每轮进化只需调用一次。

    Args:
        data_dict: 多TF数据 {"H4": DataFrame, ...}
                   DataFrame 必须包含 open/high/low/close/volume 列

    Returns:
        特征字典，每个值都是 np.ndarray:
            close, high, low, open, volume,
            atr, adx, volume_ma20, volume_ratio,
            body_ratio, upper_shadow, lower_shadow,
            ma20, ma50, price_ma20_ratio
    """
    h4 = data_dict["H4"]
    open_ = h4["open"].values.astype(np.float64)
    close = h4["close"].values.astype(np.float64)
    high = h4["high"].values.astype(np.float64)
    low = h4["low"].values.astype(np.float64)
    volume = h4["volume"].values.astype(np.float64)

    # 防除零
    hl_range = high - low
    hl_safe = np.where(hl_range > 1e-10, hl_range, 1e-10)
    vol_ma20 = _rolling_mean(volume, 20)
    vol_ma20_safe = np.where(vol_ma20 > 1e-10, vol_ma20, 1e-10)

    # 移动均线
    ma20 = _rolling_mean(close, 20)
    ma50 = _rolling_mean(close, 50)
    ma20_safe = np.where(ma20 > 1e-10, ma20, 1e-10)

    return {
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": volume,
        "atr": _vectorized_atr(high, low, close, period=14),
        "adx": _vectorized_adx(high, low, close, period=14),
        "volume_ma20": vol_ma20,
        "volume_ratio": volume / vol_ma20_safe,
        "body_ratio": np.abs(close - open_) / hl_safe,
        "upper_shadow": (high - np.maximum(close, open_)) / hl_safe,
        "lower_shadow": (np.minimum(close, open_) - low) / hl_safe,
        "ma20": ma20,
        "ma50": ma50,
        "price_ma20_ratio": close / ma20_safe,
    }


# ================================================================
# Pass 2: Numba 状态机 — @njit 编译为机器码
# ================================================================


@njit(cache=True)
def state_machine_numba(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume_ratio: np.ndarray,
    atr: np.ndarray,
    adx: np.ndarray,
    body_ratio: np.ndarray,
    lower_shadow: np.ndarray,
    upper_shadow: np.ndarray,
    # Config 参数 — 不同 GA 个体不同
    min_confidence: float = 0.30,
    spring_failure_bars: int = 10,
    vol_climax_threshold: float = 2.0,
    vol_confirm_threshold: float = 1.5,
    adx_trend_threshold: float = 25.0,
    body_ratio_threshold: float = 0.6,
    shadow_threshold: float = 0.3,
    max_bars_in_state: int = 30,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Numba 编译的状态机 — 比纯 Python 快 100-500x

    22+5 个状态用 int 编码，转换逻辑用数值比较。
    输入是预计算的 numpy 数组 + config 参数。

    Args:
        close: 收盘价数组
        high: 最高价数组
        low: 最低价数组
        volume_ratio: 成交量比（相对20MA）
        atr: ATR 数组
        adx: ADX 数组
        body_ratio: K线实体占比
        lower_shadow: 下影线占比
        upper_shadow: 上影线占比
        min_confidence: 最低信号置信度
        spring_failure_bars: Spring 失败判定 bar 数
        vol_climax_threshold: 量能高潮阈值
        vol_confirm_threshold: 量能确认阈值
        adx_trend_threshold: ADX 趋势阈值
        body_ratio_threshold: 实体占比阈值
        shadow_threshold: 影线占比阈值
        max_bars_in_state: 单状态最大停留 bar 数

    Returns:
        (states, confidences, signals) 三个数组:
            states: int32, 状态编码
            confidences: float64, 置信度 [0, 1]
            signals: int32, SIGNAL_BUY=1 / SIGNAL_SELL=-1 / SIGNAL_HOLD=0
    """
    n = len(close)
    states = np.zeros(n, dtype=np.int32)
    confidences = np.zeros(n, dtype=np.float64)
    signals = np.zeros(n, dtype=np.int32)

    current_state = 0  # IDLE
    bars_in_state = 0
    # 关键价格锚点
    sc_low = 0.0  # Selling Climax 低点
    ar_high = 0.0  # Automatic Rally 高点
    bc_high = 0.0  # Buying Climax 高点
    ar_dist_low = 0.0  # AR(distribution) 低点
    creek_level = 0.0  # Creek 水平线
    ice_level = 0.0  # Ice 水平线
    warmup = 50

    for i in range(warmup, n):
        bars_in_state += 1
        conf = 0.0
        sig = 0  # HOLD

        # 超时回退 — 在任何状态停留太久则重置
        if bars_in_state > max_bars_in_state and current_state not in (
            23,
            24,
            25,
            26,  # 趋势态不超时
        ):
            current_state = 0
            bars_in_state = 0

        # ============================================================
        # 吸筹阶段转换 (Accumulation)
        # ============================================================

        if current_state == 0:  # IDLE
            # → SC: 放量下跌 (Selling Climax)
            if volume_ratio[i] > vol_climax_threshold and close[i] < close[i - 1]:
                current_state = 2  # SC
                sc_low = low[i]
                conf = min(volume_ratio[i] / 4.0, 1.0)
                bars_in_state = 0
            # → PSY: 放量上涨 (Preliminary Supply → 派发)
            elif volume_ratio[i] > vol_climax_threshold and close[i] > close[i - 1]:
                current_state = 14  # PSY
                conf = min(volume_ratio[i] / 4.0, 0.8)
                bars_in_state = 0

        elif current_state == 1:  # PS → SC
            if volume_ratio[i] > vol_climax_threshold and close[i] < close[i - 1]:
                current_state = 2
                sc_low = low[i]
                conf = min(volume_ratio[i] / 4.0, 1.0)
                bars_in_state = 0

        elif current_state == 2:  # SC → AR
            # 价格反弹
            if close[i] > close[i - 1] and bars_in_state < 10:
                current_state = 3  # AR
                ar_high = high[i]
                creek_level = high[i]
                conf = 0.6
                bars_in_state = 0

        elif current_state == 3:  # AR → ST
            # 二次测试SC低点附近
            if close[i] < close[i - 1] and low[i] < ar_high:
                current_state = 4  # ST
                conf = 0.5
                bars_in_state = 0
                # 更新AR高点
                if high[i] > ar_high:
                    ar_high = high[i]
                    creek_level = high[i]

        elif current_state == 4:  # ST → TEST / SPRING / UTA
            # Spring: 跌破SC低点后快速收回
            if low[i] < sc_low and close[i] > sc_low:
                current_state = 7  # SPRING
                conf = min(0.5 + lower_shadow[i], 1.0)
                bars_in_state = 0
            # TEST: 缩量测试SC低点
            elif (
                abs(low[i] - sc_low) / (atr[i] + 1e-10) < 1.5 and volume_ratio[i] < 1.0
            ):
                current_state = 5  # TEST
                conf = 0.55
                bars_in_state = 0
            # UTA: 假突破上方
            elif high[i] > ar_high and close[i] < ar_high:
                current_state = 6  # UTA
                conf = 0.4
                bars_in_state = 0

        elif current_state == 5:  # TEST → SPRING / mSOS
            # Spring after test
            if low[i] < sc_low and close[i] > sc_low:
                current_state = 7  # SPRING
                conf = 0.65
                bars_in_state = 0
            # minor SOS: 放量上涨
            elif (
                close[i] > close[i - 1]
                and volume_ratio[i] > vol_confirm_threshold
                and body_ratio[i] > body_ratio_threshold
            ):
                current_state = 10  # mSOS
                conf = 0.6
                bars_in_state = 0

        elif current_state == 6:  # UTA → ST / TEST
            # 回落到区间内
            if close[i] < ar_high and close[i] > sc_low:
                current_state = 4  # 回到 ST
                conf = 0.4
                bars_in_state = 0

        elif current_state == 7:  # SPRING → SO / 失败回 IDLE
            # Sign of Strength after Spring
            if close[i] > close[i - 1] and volume_ratio[i] > vol_confirm_threshold:
                current_state = 8  # SO
                conf = 0.7
                sig = 1  # BUY signal
                bars_in_state = 0
            # Spring 失败
            elif bars_in_state > spring_failure_bars and close[i] < sc_low:
                current_state = 0  # 回 IDLE
                conf = 0.0
                bars_in_state = 0

        elif current_state == 8:  # SO → LPS
            # Last Point of Support: 回调缩量
            if close[i] < close[i - 1] and volume_ratio[i] < 1.0:
                current_state = 9  # LPS
                conf = 0.65
                bars_in_state = 0

        elif current_state == 9:  # LPS → mSOS / JOC
            # Jump Over Creek
            if close[i] > creek_level and volume_ratio[i] > vol_confirm_threshold:
                current_state = 12  # JOC
                conf = 0.8
                sig = 1  # BUY signal
                bars_in_state = 0
            # minor SOS
            elif close[i] > close[i - 1] and body_ratio[i] > body_ratio_threshold:
                current_state = 10  # mSOS
                conf = 0.6
                bars_in_state = 0

        elif current_state == 10:  # mSOS → MAJOR_SOS / LPS
            # Major SOS: 持续放量突破
            if (
                close[i] > close[i - 1]
                and volume_ratio[i] > vol_climax_threshold
                and adx[i] > adx_trend_threshold
            ):
                current_state = 11  # MAJOR_SOS
                conf = 0.85
                sig = 1  # BUY
                bars_in_state = 0
            # 回调 → LPS
            elif close[i] < close[i - 1] and volume_ratio[i] < 1.0:
                current_state = 9  # LPS
                conf = 0.55
                bars_in_state = 0

        elif current_state == 11:  # MAJOR_SOS → JOC / UPTREND
            if close[i] > creek_level:
                current_state = 12  # JOC
                conf = 0.85
                sig = 1  # BUY
                bars_in_state = 0

        elif current_state == 12:  # JOC → BU / UPTREND
            # Back Up to Creek (回踩)
            if close[i] < close[i - 1] and low[i] >= creek_level * 0.98:
                current_state = 13  # BU
                conf = 0.75
                sig = 1  # BUY — 回踩确认
                bars_in_state = 0
            # 直接进入上升趋势
            elif bars_in_state > 3 and close[i] > creek_level:
                current_state = 23  # UPTREND
                conf = 0.8
                bars_in_state = 0

        elif current_state == 13:  # BU → UPTREND
            # 站稳creek → 上升趋势
            if close[i] > creek_level and bars_in_state >= 2:
                current_state = 23  # UPTREND
                conf = 0.8
                bars_in_state = 0

        # ============================================================
        # 派发阶段转换 (Distribution)
        # ============================================================

        elif current_state == 14:  # PSY → BC
            # Buying Climax: 放量冲高
            if (
                volume_ratio[i] > vol_climax_threshold
                and close[i] > close[i - 1]
                and upper_shadow[i] > shadow_threshold
            ):
                current_state = 15  # BC
                bc_high = high[i]
                conf = min(volume_ratio[i] / 4.0, 1.0)
                bars_in_state = 0

        elif current_state == 15:  # BC → AR_DIST
            # Automatic Reaction: 价格下跌
            if close[i] < close[i - 1] and bars_in_state < 10:
                current_state = 16  # AR_DIST
                ar_dist_low = low[i]
                ice_level = low[i]
                conf = 0.6
                bars_in_state = 0

        elif current_state == 16:  # AR_DIST → ST_DIST
            # Secondary Test of BC high
            if close[i] > close[i - 1] and high[i] < bc_high * 1.02:
                current_state = 17  # ST_DIST
                conf = 0.5
                bars_in_state = 0
                if low[i] < ar_dist_low:
                    ar_dist_low = low[i]
                    ice_level = low[i]

        elif current_state == 17:  # ST_DIST → UT / UTAD / LPSY
            # Upthrust: 冲破BC高点后回落
            if high[i] > bc_high and close[i] < bc_high:
                current_state = 18  # UT
                conf = 0.65
                bars_in_state = 0
            # LPSY: 缩量上涨无力
            elif (
                close[i] > close[i - 1]
                and volume_ratio[i] < 1.0
                and body_ratio[i] < body_ratio_threshold
            ):
                current_state = 20  # LPSY
                conf = 0.55
                bars_in_state = 0

        elif current_state == 18:  # UT → UTAD / mSOW
            # UTAD: 再次冲高失败
            if high[i] > bc_high and close[i] < bc_high:
                current_state = 19  # UTAD
                conf = 0.7
                sig = -1  # SELL signal
                bars_in_state = 0
            # minor SOW
            elif close[i] < close[i - 1] and volume_ratio[i] > vol_confirm_threshold:
                current_state = 21  # mSOW
                conf = 0.6
                bars_in_state = 0

        elif current_state == 19:  # UTAD → LPSY / mSOW
            # LPSY after UTAD
            if close[i] < close[i - 1] and volume_ratio[i] < 1.0:
                current_state = 20  # LPSY
                conf = 0.65
                sig = -1  # SELL
                bars_in_state = 0

        elif current_state == 20:  # LPSY → mSOW / MAJOR_SOW
            # minor Sign of Weakness
            if (
                close[i] < close[i - 1]
                and volume_ratio[i] > vol_confirm_threshold
                and body_ratio[i] > body_ratio_threshold
            ):
                current_state = 21  # mSOW
                conf = 0.7
                sig = -1  # SELL
                bars_in_state = 0

        elif current_state == 21:  # mSOW → MAJOR_SOW
            # Major SOW: 跌破 ice level
            if close[i] < ice_level and volume_ratio[i] > vol_climax_threshold:
                current_state = 22  # MAJOR_SOW
                conf = 0.85
                sig = -1  # SELL
                bars_in_state = 0
            # 弱反弹 → LPSY
            elif close[i] > close[i - 1] and volume_ratio[i] < 1.0:
                current_state = 20  # LPSY
                conf = 0.5
                bars_in_state = 0

        elif current_state == 22:  # MAJOR_SOW → DOWNTREND
            if close[i] < ice_level and bars_in_state >= 2:
                current_state = 24  # DOWNTREND
                conf = 0.8
                sig = -1  # SELL
                bars_in_state = 0

        # ============================================================
        # 趋势态 + 再积累/再派发
        # ============================================================

        elif current_state == 23:  # UPTREND
            # 趋势维持：ADX 高
            if adx[i] > adx_trend_threshold:
                conf = 0.7
            else:
                conf = 0.4
            # 放量反转 → 可能进入派发 (PSY)
            if (
                volume_ratio[i] > vol_climax_threshold
                and close[i] < close[i - 1]
                and upper_shadow[i] > shadow_threshold
            ):
                current_state = 14  # PSY
                conf = 0.5
                bars_in_state = 0
            # 缩量回调 → 再积累
            elif (
                close[i] < close[i - 1] and volume_ratio[i] < 0.8 and bars_in_state > 5
            ):
                current_state = 25  # RE_ACCUMULATION
                conf = 0.5
                bars_in_state = 0

        elif current_state == 24:  # DOWNTREND
            if adx[i] > adx_trend_threshold:
                conf = 0.7
            else:
                conf = 0.4
            # 放量反转 → 可能进入吸筹 (SC)
            if (
                volume_ratio[i] > vol_climax_threshold
                and close[i] > close[i - 1]
                and lower_shadow[i] > shadow_threshold
            ):
                current_state = 2  # SC
                sc_low = low[i]
                conf = 0.5
                bars_in_state = 0
            # 缩量反弹 → 再派发
            elif (
                close[i] > close[i - 1] and volume_ratio[i] < 0.8 and bars_in_state > 5
            ):
                current_state = 26  # RE_DISTRIBUTION
                conf = 0.5
                bars_in_state = 0

        elif current_state == 25:  # RE_ACCUMULATION
            # 回到上升趋势
            if close[i] > close[i - 1] and volume_ratio[i] > vol_confirm_threshold:
                current_state = 23  # UPTREND
                conf = 0.7
                sig = 1  # BUY
                bars_in_state = 0
            # 趋势反转
            elif close[i] < close[i - 1] and volume_ratio[i] > vol_climax_threshold:
                current_state = 2  # SC
                sc_low = low[i]
                conf = 0.5
                bars_in_state = 0

        elif current_state == 26:  # RE_DISTRIBUTION
            # 回到下降趋势
            if close[i] < close[i - 1] and volume_ratio[i] > vol_confirm_threshold:
                current_state = 24  # DOWNTREND
                conf = 0.7
                sig = -1  # SELL
                bars_in_state = 0
            # 趋势反转
            elif close[i] > close[i - 1] and volume_ratio[i] > vol_climax_threshold:
                current_state = 14  # PSY
                conf = 0.5
                bars_in_state = 0

        # 记录当前 bar
        states[i] = current_state
        confidences[i] = conf
        signals[i] = sig

    return states, confidences, signals


# ================================================================
# Pass 3: 向量化回测 — @njit 编译为机器码
# ================================================================


@njit(cache=True)
def vectorized_backtest(
    close: np.ndarray,
    signals: np.ndarray,
    confidences: np.ndarray,
    atr: np.ndarray,
    min_confidence: float = 0.30,
    atr_sl_mult: float = 2.0,
    atr_tp_mult: float = 3.0,
    commission: float = 0.001,
    initial_capital: float = 10000.0,
    risk_pct: float = 0.02,
    max_hold_bars: int = 50,
) -> Tuple[np.ndarray, int, int, float]:
    """Numba 编译的回测引擎

    支持多空双向交易、ATR止损止盈、超时退出、佣金。

    Args:
        close: 收盘价数组
        signals: 信号数组 (1=BUY, -1=SELL, 0=HOLD)
        confidences: 置信度数组
        atr: ATR 数组
        min_confidence: 最低开仓置信度
        atr_sl_mult: 止损 ATR 倍数
        atr_tp_mult: 止盈 ATR 倍数
        commission: 佣金率
        initial_capital: 初始资金
        risk_pct: 单笔风险比例
        max_hold_bars: 最大持仓 bar 数

    Returns:
        (equity_curve, total_trades, winning_trades, max_drawdown)
    """
    n = len(close)
    equity = np.empty(n, dtype=np.float64)
    equity[0] = initial_capital

    position = 0.0  # >0 多头数量, <0 空头数量, 0 空仓
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    entry_bar = 0
    total_trades = 0
    winning_trades = 0
    peak_equity = initial_capital
    max_drawdown = 0.0
    current_equity = initial_capital

    for i in range(1, n):
        equity[i] = current_equity

        # ---- 持仓中：检查退出条件 ----
        if position != 0.0:
            hold_bars = i - entry_bar

            # 多头退出
            if position > 0.0:
                # 止损
                if close[i] <= stop_loss:
                    pnl = (stop_loss - entry_price) * position
                    cost = abs(pnl) * commission
                    current_equity += pnl - cost
                    total_trades += 1
                    if pnl > 0:
                        winning_trades += 1
                    position = 0.0
                # 止盈
                elif close[i] >= take_profit:
                    pnl = (take_profit - entry_price) * position
                    cost = abs(pnl) * commission
                    current_equity += pnl - cost
                    total_trades += 1
                    if pnl > 0:
                        winning_trades += 1
                    position = 0.0
                # 超时
                elif hold_bars >= max_hold_bars:
                    pnl = (close[i] - entry_price) * position
                    cost = abs(pnl) * commission
                    current_equity += pnl - cost
                    total_trades += 1
                    if pnl > 0:
                        winning_trades += 1
                    position = 0.0

            # 空头退出
            elif position < 0.0:
                abs_pos = -position
                # 止损
                if close[i] >= stop_loss:
                    pnl = (entry_price - stop_loss) * abs_pos
                    cost = abs(pnl) * commission
                    current_equity += pnl - cost
                    total_trades += 1
                    if pnl > 0:
                        winning_trades += 1
                    position = 0.0
                # 止盈
                elif close[i] <= take_profit:
                    pnl = (entry_price - take_profit) * abs_pos
                    cost = abs(pnl) * commission
                    current_equity += pnl - cost
                    total_trades += 1
                    if pnl > 0:
                        winning_trades += 1
                    position = 0.0
                # 超时
                elif hold_bars >= max_hold_bars:
                    pnl = (entry_price - close[i]) * abs_pos
                    cost = abs(pnl) * commission
                    current_equity += pnl - cost
                    total_trades += 1
                    if pnl > 0:
                        winning_trades += 1
                    position = 0.0

        # ---- 空仓：检查开仓信号 ----
        if position == 0.0 and confidences[i] > min_confidence:
            stop_dist = atr[i] * atr_sl_mult
            if stop_dist < 1e-10:
                stop_dist = 1e-10

            if signals[i] == 1:  # BUY
                risk_amount = current_equity * risk_pct
                position = risk_amount / stop_dist
                entry_price = close[i]
                stop_loss = close[i] - stop_dist
                take_profit = close[i] + atr[i] * atr_tp_mult
                entry_bar = i
                # 开仓佣金
                current_equity -= close[i] * position * commission

            elif signals[i] == -1:  # SELL (short)
                risk_amount = current_equity * risk_pct
                position = -(risk_amount / stop_dist)
                entry_price = close[i]
                stop_loss = close[i] + stop_dist
                take_profit = close[i] - atr[i] * atr_tp_mult
                entry_bar = i
                current_equity -= close[i] * (-position) * commission

        # 更新权益曲线
        equity[i] = current_equity

        # 更新最大回撤
        if current_equity > peak_equity:
            peak_equity = current_equity
        if peak_equity > 0:
            dd = (peak_equity - current_equity) / peak_equity
            if dd > max_drawdown:
                max_drawdown = dd

    # 强制平仓
    if position > 0.0:
        pnl = (close[n - 1] - entry_price) * position
        current_equity += pnl - abs(pnl) * commission
        total_trades += 1
        if pnl > 0:
            winning_trades += 1
        equity[n - 1] = current_equity
    elif position < 0.0:
        abs_pos = -position
        pnl = (entry_price - close[n - 1]) * abs_pos
        current_equity += pnl - abs(pnl) * commission
        total_trades += 1
        if pnl > 0:
            winning_trades += 1
        equity[n - 1] = current_equity

    return equity, total_trades, winning_trades, max_drawdown


# ================================================================
# AcceleratedEvaluator — 三层 Pass 的 Python 封装
# ================================================================


class AcceleratedEvaluator:
    """加速评估器 — 将三层 Pass 串联为 GA 可消费的评估函数

    使用方式:
        evaluator = AcceleratedEvaluator()
        features = evaluator.precompute(data_dict)   # 每轮一次
        metrics = evaluator.evaluate(config, features)  # 每个个体一次

    与 StandardEvaluator 的区别:
        StandardEvaluator 每次评估都要重新创建 WyckoffEngine 并逐bar处理，
        AcceleratedEvaluator 预计算特征后，状态机和回测都用 Numba 编译的机器码。
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        warmup_bars: int = 50,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.warmup_bars = warmup_bars
        self._compiled = False

    def precompute(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, np.ndarray]:
        """Pass 1: 预计算特征（每轮进化调用一次）

        Args:
            data_dict: 多TF数据

        Returns:
            特征字典
        """
        return precompute_features(data_dict)

    def warmup_jit(self, features: Dict[str, np.ndarray]) -> None:
        """预热 JIT 编译（首次调用会编译，后续调用跳过）

        Args:
            features: precompute() 返回的特征字典
        """
        if self._compiled:
            return

        n = min(100, len(features["close"]))
        small = {k: v[:n].copy() for k, v in features.items()}

        # 触发 Pass 2 编译
        state_machine_numba(
            small["close"],
            small["high"],
            small["low"],
            small["volume_ratio"],
            small["atr"],
            small["adx"],
            small["body_ratio"],
            small["lower_shadow"],
            small["upper_shadow"],
        )

        # 触发 Pass 3 编译
        dummy_signals = np.zeros(n, dtype=np.int32)
        dummy_conf = np.zeros(n, dtype=np.float64)
        vectorized_backtest(
            small["close"],
            dummy_signals,
            dummy_conf,
            small["atr"],
        )

        self._compiled = True
        logger.info("Numba JIT 编译完成")

    def evaluate(
        self,
        config: Dict[str, Any],
        features: Dict[str, np.ndarray],
    ) -> Dict[str, float]:
        """评估单个配置的性能 — Pass 2 + Pass 3

        Args:
            config: 进化配置字典
            features: precompute() 返回的特征字典

        Returns:
            标准化指标字典（与 StandardEvaluator 格式兼容）
        """
        # 提取 config 参数
        thresh = config.get("threshold_parameters", {})
        sm_cfg = config.get("state_machine", {})
        bt_cfg = config.get("backtest", {})

        min_confidence = thresh.get("confidence_threshold", 0.30)

        # Pass 2: 状态机
        states, confidences, signals = state_machine_numba(
            close=features["close"],
            high=features["high"],
            low=features["low"],
            volume_ratio=features["volume_ratio"],
            atr=features["atr"],
            adx=features["adx"],
            body_ratio=features["body_ratio"],
            lower_shadow=features["lower_shadow"],
            upper_shadow=features["upper_shadow"],
            min_confidence=min_confidence,
            spring_failure_bars=sm_cfg.get("spring_failure_bars", 10),
            vol_climax_threshold=sm_cfg.get("vol_climax_threshold", 2.0),
            vol_confirm_threshold=sm_cfg.get("vol_confirm_threshold", 1.5),
            adx_trend_threshold=sm_cfg.get("adx_trend_threshold", 25.0),
            body_ratio_threshold=sm_cfg.get("body_ratio_threshold", 0.6),
            shadow_threshold=sm_cfg.get("shadow_threshold", 0.3),
            max_bars_in_state=sm_cfg.get("max_bars_in_state", 30),
        )

        # Pass 3: 回测
        atr_sl = bt_cfg.get("atr_sl_mult", 2.0)
        atr_tp = bt_cfg.get("atr_tp_mult", 3.0)

        equity, total_trades, winning_trades, max_dd = vectorized_backtest(
            close=features["close"],
            signals=signals,
            confidences=confidences,
            atr=features["atr"],
            min_confidence=min_confidence,
            atr_sl_mult=atr_sl,
            atr_tp_mult=atr_tp,
            commission=self.commission_rate,
            initial_capital=self.initial_capital,
            risk_pct=bt_cfg.get("risk_pct", 0.02),
            max_hold_bars=bt_cfg.get("max_hold_bars", 50),
        )

        return self._compute_metrics(
            equity,
            total_trades,
            winning_trades,
            max_dd,
        )

    def _compute_metrics(
        self,
        equity: np.ndarray,
        total_trades: int,
        winning_trades: int,
        max_drawdown: float,
    ) -> Dict[str, float]:
        """从回测结果计算标准化指标

        Args:
            equity: 权益曲线
            total_trades: 总交易数
            winning_trades: 盈利交易数
            max_drawdown: 最大回撤

        Returns:
            指标字典（与 StandardEvaluator._compute_metrics 格式兼容）
        """
        total_return = (equity[-1] - self.initial_capital) / self.initial_capital
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        # Sharpe Ratio — 基于权益曲线的逐bar收益率
        if len(equity) > 1:
            returns = np.diff(equity) / np.maximum(equity[:-1], 1e-10)
            mean_r = np.mean(returns)
            std_r = np.std(returns, ddof=1)
            sharpe = float(mean_r / std_r * np.sqrt(252.0)) if std_r > 1e-10 else 0.0
        else:
            sharpe = 0.0

        # Profit Factor (近似：用总收益/总亏损)
        if len(equity) > 1:
            gains = np.sum(np.maximum(np.diff(equity), 0.0))
            losses = np.sum(np.maximum(-np.diff(equity), 0.0))
            profit_factor = float(gains / losses) if losses > 1e-10 else 2.0
        else:
            profit_factor = 0.0

        calmar = (sharpe / max_drawdown) if max_drawdown > 1e-10 else sharpe
        stability = max(0.0, 1.0 - max_drawdown)
        sharpe_component = 1.0 / (1.0 + np.exp(-sharpe))

        composite = (
            sharpe_component * 0.25
            + (1.0 - max_drawdown) * 0.20
            + win_rate * 0.15
            + min(profit_factor, 3.0) / 3.0 * 0.15
            + stability * 0.25
        )

        return {
            "SHARPE_RATIO": sharpe,
            "MAX_DRAWDOWN": max_drawdown,
            "WIN_RATE": win_rate,
            "PROFIT_FACTOR": profit_factor,
            "CALMAR_RATIO": calmar,
            "STABILITY_SCORE": stability,
            "COMPOSITE_SCORE": float(composite),
            "TOTAL_TRADES": total_trades,
            "TOTAL_RETURN": total_return,
        }
