"""Numba 加速器测试 — 正确性 + 性能基准

测试覆盖:
1. Pass 1: precompute_features 输出合理性
2. Pass 2: state_machine_numba 状态转换正确性
3. Pass 3: vectorized_backtest 回测逻辑正确性
4. AcceleratedEvaluator 端到端集成
5. 性能基准: Numba vs 纯 Python 对比

注意: 当 Numba 不可用时 (如 NumPy 版本不兼容)，
模块会自动降级为纯 Python 模式，所有测试仍应通过。
"""

import time

import numpy as np
import pandas as pd
import pytest

from src.plugins.evolution.numba_accelerator import (
    HAS_NUMBA,
    AcceleratedEvaluator,
    SIGNAL_BUY,
    SIGNAL_HOLD,
    SIGNAL_SELL,
    STATE_AR,
    STATE_BC,
    STATE_IDLE,
    STATE_SC,
    _rolling_mean,
    _vectorized_adx,
    _vectorized_atr,
    precompute_features,
    state_machine_numba,
    vectorized_backtest,
)


# ================================================================
# 测试数据生成
# ================================================================


def _make_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """生成合理的 OHLCV 测试数据

    模拟一个包含趋势和震荡的价格序列。
    """
    rng = np.random.RandomState(seed)
    # 基础价格：随机游走 + 均值回归
    returns = rng.normal(0.0002, 0.015, n)
    close = 50000.0 * np.exp(np.cumsum(returns))

    # 生成 OHLC
    spread = close * rng.uniform(0.005, 0.02, n)
    high = close + spread * rng.uniform(0.3, 1.0, n)
    low = close - spread * rng.uniform(0.3, 1.0, n)
    open_ = close + spread * rng.uniform(-0.5, 0.5, n)

    # 确保 OHLC 一致性
    high = np.maximum(high, np.maximum(close, open_))
    low = np.minimum(low, np.minimum(close, open_))

    volume = rng.uniform(100, 1000, n)

    idx = pd.date_range("2025-01-01", periods=n, freq="4h")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _make_data_dict(n: int = 500, seed: int = 42) -> dict:
    """生成多TF数据字典"""
    return {"H4": _make_ohlcv(n, seed)}


def _make_accumulation_data(n: int = 300) -> pd.DataFrame:
    """生成包含明确吸筹特征的数据

    阶段:
    1. 下跌（产生 SC）
    2. 反弹（产生 AR）
    3. 回测（产生 ST）
    4. Spring + 上涨
    """
    prices = []
    volumes = []
    base = 50000.0

    # Phase 1: 下跌到SC (0-60)
    for i in range(60):
        base *= 0.997
        prices.append(base)
        # SC 处放量
        volumes.append(800.0 if i > 50 else 200.0)

    sc_low = base

    # Phase 2: AR 反弹 (60-90)
    for i in range(30):
        base *= 1.004
        prices.append(base)
        volumes.append(300.0)

    # Phase 3: ST 回测 (90-130)
    for i in range(40):
        base *= 0.999
        prices.append(base)
        volumes.append(150.0)

    # Phase 4: Spring + 上涨 (130-300)
    for i in range(n - 130):
        base *= 1.002
        prices.append(base)
        volumes.append(400.0 if i < 20 else 250.0)

    close = np.array(prices)
    spread = close * 0.008
    rng = np.random.RandomState(99)
    high = close + spread * rng.uniform(0.3, 1.0, n)
    low = close - spread * rng.uniform(0.3, 1.0, n)
    open_ = close + spread * rng.uniform(-0.3, 0.3, n)
    high = np.maximum(high, np.maximum(close, open_))
    low = np.minimum(low, np.minimum(close, open_))

    idx = pd.date_range("2025-01-01", periods=n, freq="4h")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.array(volumes),
        },
        index=idx,
    )


# ================================================================
# Pass 1: 向量化辅助函数和特征预计算
# ================================================================


class TestRollingMean:
    """_rolling_mean 正确性"""

    def test_constant_array(self):
        """常数数组的滚动均值应为自身"""
        arr = np.full(100, 5.0)
        result = _rolling_mean(arr, 20)
        np.testing.assert_allclose(result, 5.0, atol=1e-10)

    def test_known_values(self):
        """已知值验证"""
        arr = np.arange(1.0, 11.0)  # [1,2,...,10]
        result = _rolling_mean(arr, 3)
        # 第3个元素(index=2)起: mean([1,2,3])=2, mean([2,3,4])=3, ...
        assert abs(result[2] - 2.0) < 1e-10
        assert abs(result[3] - 3.0) < 1e-10
        assert abs(result[9] - 9.0) < 1e-10

    def test_output_shape(self):
        """输出长度应与输入相同"""
        arr = np.random.randn(200)
        result = _rolling_mean(arr, 20)
        assert len(result) == 200

    def test_no_nan(self):
        """输出不应包含 NaN"""
        arr = np.random.randn(50)
        result = _rolling_mean(arr, 10)
        assert not np.any(np.isnan(result))


class TestVectorizedATR:
    """_vectorized_atr 正确性"""

    def test_output_positive(self):
        """ATR 应为正值"""
        df = _make_ohlcv(200)
        atr = _vectorized_atr(
            df["high"].values.astype(np.float64),
            df["low"].values.astype(np.float64),
            df["close"].values.astype(np.float64),
        )
        assert np.all(atr >= 0)

    def test_output_shape(self):
        """输出长度应与输入相同"""
        df = _make_ohlcv(200)
        atr = _vectorized_atr(
            df["high"].values.astype(np.float64),
            df["low"].values.astype(np.float64),
            df["close"].values.astype(np.float64),
        )
        assert len(atr) == 200

    def test_no_nan(self):
        """输出不应包含 NaN"""
        df = _make_ohlcv(200)
        atr = _vectorized_atr(
            df["high"].values.astype(np.float64),
            df["low"].values.astype(np.float64),
            df["close"].values.astype(np.float64),
        )
        assert not np.any(np.isnan(atr))

    def test_reasonable_magnitude(self):
        """ATR 应在合理范围内（相对价格的百分比）"""
        df = _make_ohlcv(200)
        close = df["close"].values.astype(np.float64)
        atr = _vectorized_atr(
            df["high"].values.astype(np.float64),
            df["low"].values.astype(np.float64),
            close,
        )
        # ATR / close 应在 0.1% ~ 10% 之间
        ratio = atr[50:] / close[50:]
        assert np.all(ratio < 0.10)
        assert np.mean(ratio) > 0.001


class TestVectorizedADX:
    """_vectorized_adx 正确性"""

    def test_output_range(self):
        """ADX 应在 [0, 100] 范围内"""
        df = _make_ohlcv(200)
        adx = _vectorized_adx(
            df["high"].values.astype(np.float64),
            df["low"].values.astype(np.float64),
            df["close"].values.astype(np.float64),
        )
        assert np.all(adx >= 0)
        assert np.all(adx <= 100)

    def test_output_shape(self):
        """输出长度应与输入相同"""
        df = _make_ohlcv(200)
        adx = _vectorized_adx(
            df["high"].values.astype(np.float64),
            df["low"].values.astype(np.float64),
            df["close"].values.astype(np.float64),
        )
        assert len(adx) == 200

    def test_short_data(self):
        """数据不足时返回全零"""
        adx = _vectorized_adx(
            np.array([1.0, 2.0]),
            np.array([0.5, 1.0]),
            np.array([0.8, 1.5]),
            period=14,
        )
        assert len(adx) == 2
        np.testing.assert_allclose(adx, 0.0)


class TestPrecomputeFeatures:
    """precompute_features 正确性"""

    def test_all_keys_present(self):
        """应返回所有预期的特征键"""
        data = _make_data_dict(200)
        features = precompute_features(data)
        expected_keys = {
            "open",
            "close",
            "high",
            "low",
            "volume",
            "atr",
            "adx",
            "volume_ma20",
            "volume_ratio",
            "body_ratio",
            "upper_shadow",
            "lower_shadow",
            "ma20",
            "ma50",
            "price_ma20_ratio",
        }
        assert set(features.keys()) == expected_keys

    def test_output_lengths(self):
        """所有特征数组长度应一致"""
        data = _make_data_dict(300)
        features = precompute_features(data)
        for key, arr in features.items():
            assert len(arr) == 300, f"{key} 长度不是 300"

    def test_body_ratio_range(self):
        """body_ratio 应在 [0, 1] 范围内"""
        data = _make_data_dict(200)
        features = precompute_features(data)
        assert np.all(features["body_ratio"] >= 0)
        assert np.all(features["body_ratio"] <= 1.0 + 1e-10)

    def test_shadow_ratio_range(self):
        """影线占比应在 [0, 1] 范围内"""
        data = _make_data_dict(200)
        features = precompute_features(data)
        assert np.all(features["upper_shadow"] >= -1e-10)
        assert np.all(features["upper_shadow"] <= 1.0 + 1e-10)
        assert np.all(features["lower_shadow"] >= -1e-10)
        assert np.all(features["lower_shadow"] <= 1.0 + 1e-10)

    def test_volume_ratio_positive(self):
        """volume_ratio 应为正"""
        data = _make_data_dict(200)
        features = precompute_features(data)
        assert np.all(features["volume_ratio"] > 0)

    def test_no_nan_in_features(self):
        """所有特征不应包含 NaN"""
        data = _make_data_dict(300)
        features = precompute_features(data)
        for key, arr in features.items():
            assert not np.any(np.isnan(arr)), f"{key} 包含 NaN"

    def test_idempotent(self):
        """多次调用结果应一致（纯函数）"""
        data = _make_data_dict(200)
        f1 = precompute_features(data)
        f2 = precompute_features(data)
        for key in f1:
            np.testing.assert_array_equal(f1[key], f2[key])


# ================================================================
# Pass 2: Numba 状态机
# ================================================================


class TestStateMachineNumba:
    """state_machine_numba 正确性"""

    def _run_sm(self, df: pd.DataFrame, **kwargs):
        """辅助方法：从 DataFrame 运行状态机"""
        features = precompute_features({"H4": df})
        return state_machine_numba(
            close=features["close"],
            high=features["high"],
            low=features["low"],
            volume_ratio=features["volume_ratio"],
            atr=features["atr"],
            adx=features["adx"],
            body_ratio=features["body_ratio"],
            lower_shadow=features["lower_shadow"],
            upper_shadow=features["upper_shadow"],
            **kwargs,
        )

    def test_output_shapes(self):
        """输出数组长度应与输入一致"""
        df = _make_ohlcv(200)
        states, confs, sigs = self._run_sm(df)
        assert len(states) == 200
        assert len(confs) == 200
        assert len(sigs) == 200

    def test_output_dtypes(self):
        """输出类型正确"""
        df = _make_ohlcv(200)
        states, confs, sigs = self._run_sm(df)
        assert states.dtype == np.int32
        assert confs.dtype == np.float64
        assert sigs.dtype == np.int32

    def test_warmup_zeros(self):
        """前 50 个 bar（warmup）应保持 IDLE 状态"""
        df = _make_ohlcv(200)
        states, confs, sigs = self._run_sm(df)
        np.testing.assert_array_equal(states[:50], 0)
        np.testing.assert_array_equal(confs[:50], 0.0)
        np.testing.assert_array_equal(sigs[:50], 0)

    def test_states_in_valid_range(self):
        """所有状态值应在有效范围 [0, 26] 内"""
        df = _make_ohlcv(500)
        states, _, _ = self._run_sm(df)
        assert np.all(states >= 0)
        assert np.all(states <= 26)

    def test_confidences_in_range(self):
        """置信度应在 [0, 1] 范围内"""
        df = _make_ohlcv(500)
        _, confs, _ = self._run_sm(df)
        assert np.all(confs >= 0.0)
        assert np.all(confs <= 1.0 + 1e-10)

    def test_signals_valid_values(self):
        """信号只能是 -1, 0, 1"""
        df = _make_ohlcv(500)
        _, _, sigs = self._run_sm(df)
        unique = set(np.unique(sigs))
        assert unique.issubset({-1, 0, 1})

    def test_accumulation_produces_states(self):
        """吸筹数据应产生非 IDLE 状态"""
        df = _make_accumulation_data(300)
        states, _, _ = self._run_sm(df)
        # 至少应有一些非 IDLE 状态
        non_idle = np.sum(states != STATE_IDLE)
        assert non_idle > 0, "吸筹数据未产生任何状态转换"

    def test_deterministic(self):
        """相同输入应产生相同输出"""
        df = _make_ohlcv(200, seed=123)
        s1, c1, sig1 = self._run_sm(df)
        s2, c2, sig2 = self._run_sm(df)
        np.testing.assert_array_equal(s1, s2)
        np.testing.assert_array_equal(c1, c2)
        np.testing.assert_array_equal(sig1, sig2)

    def test_config_params_affect_output(self):
        """不同 config 参数应产生不同输出"""
        df = _make_ohlcv(300, seed=77)
        s1, _, _ = self._run_sm(df, vol_climax_threshold=2.0)
        s2, _, _ = self._run_sm(df, vol_climax_threshold=0.5)
        # 降低阈值应产生更多状态转换
        non_idle_1 = np.sum(s1 != STATE_IDLE)
        non_idle_2 = np.sum(s2 != STATE_IDLE)
        # 至少应有差异（不要求哪个更多，只要不完全相同）
        assert not np.array_equal(s1, s2) or (non_idle_1 == 0 and non_idle_2 == 0), (
            "不同阈值应产生不同状态序列"
        )


# ================================================================
# Pass 3: 向量化回测
# ================================================================


class TestVectorizedBacktest:
    """vectorized_backtest 正确性"""

    def test_no_trades_on_hold(self):
        """全 HOLD 信号应不产生交易"""
        n = 200
        close = np.linspace(50000, 51000, n)
        signals = np.zeros(n, dtype=np.int32)
        confs = np.zeros(n, dtype=np.float64)
        atr = np.full(n, 500.0)

        equity, trades, wins, dd = vectorized_backtest(
            close,
            signals,
            confs,
            atr,
        )
        assert trades == 0
        assert wins == 0
        assert equity[-1] == 10000.0

    def test_buy_signal_creates_trade(self):
        """BUY 信号应产生交易"""
        n = 200
        close = np.linspace(50000, 55000, n)
        signals = np.zeros(n, dtype=np.int32)
        signals[60] = SIGNAL_BUY
        confs = np.zeros(n, dtype=np.float64)
        confs[60] = 0.8
        atr = np.full(n, 500.0)

        equity, trades, wins, dd = vectorized_backtest(
            close,
            signals,
            confs,
            atr,
        )
        assert trades >= 1

    def test_low_confidence_no_trade(self):
        """置信度低于阈值时不应开仓"""
        n = 200
        close = np.linspace(50000, 55000, n)
        signals = np.zeros(n, dtype=np.int32)
        signals[60] = SIGNAL_BUY
        confs = np.zeros(n, dtype=np.float64)
        confs[60] = 0.1  # 低于默认阈值 0.3
        atr = np.full(n, 500.0)

        equity, trades, wins, dd = vectorized_backtest(
            close,
            signals,
            confs,
            atr,
        )
        assert trades == 0

    def test_sell_signal_creates_trade(self):
        """SELL 信号应产生空头交易"""
        n = 200
        close = np.linspace(55000, 50000, n)  # 下跌行情
        signals = np.zeros(n, dtype=np.int32)
        signals[60] = SIGNAL_SELL
        confs = np.zeros(n, dtype=np.float64)
        confs[60] = 0.8
        atr = np.full(n, 500.0)

        equity, trades, wins, dd = vectorized_backtest(
            close,
            signals,
            confs,
            atr,
        )
        assert trades >= 1

    def test_stop_loss_triggers(self):
        """下跌行情中的多头应触发止损"""
        n = 200
        close = np.empty(n)
        close[:80] = 50000.0
        # 开仓后暴跌
        for i in range(80, n):
            close[i] = 50000.0 - (i - 80) * 100.0

        signals = np.zeros(n, dtype=np.int32)
        signals[80] = SIGNAL_BUY
        confs = np.zeros(n, dtype=np.float64)
        confs[80] = 0.8
        atr = np.full(n, 500.0)

        equity, trades, wins, dd = vectorized_backtest(
            close,
            signals,
            confs,
            atr,
        )
        assert trades >= 1
        # 止损触发，权益应低于初始值
        assert equity[-1] < 10000.0

    def test_equity_curve_length(self):
        """权益曲线长度应与输入一致"""
        n = 300
        close = np.linspace(50000, 51000, n)
        signals = np.zeros(n, dtype=np.int32)
        confs = np.zeros(n, dtype=np.float64)
        atr = np.full(n, 500.0)

        equity, _, _, _ = vectorized_backtest(close, signals, confs, atr)
        assert len(equity) == n

    def test_max_drawdown_range(self):
        """最大回撤应在 [0, 1] 范围内"""
        df = _make_ohlcv(300)
        features = precompute_features({"H4": df})
        _, _, sigs = state_machine_numba(
            features["close"],
            features["high"],
            features["low"],
            features["volume_ratio"],
            features["atr"],
            features["adx"],
            features["body_ratio"],
            features["lower_shadow"],
            features["upper_shadow"],
        )
        _, confs, _ = state_machine_numba(
            features["close"],
            features["high"],
            features["low"],
            features["volume_ratio"],
            features["atr"],
            features["adx"],
            features["body_ratio"],
            features["lower_shadow"],
            features["upper_shadow"],
        )
        equity, _, _, dd = vectorized_backtest(
            features["close"],
            sigs,
            confs,
            features["atr"],
        )
        assert 0.0 <= dd <= 1.0

    def test_initial_equity(self):
        """初始权益应为指定值"""
        n = 100
        close = np.full(n, 50000.0)
        signals = np.zeros(n, dtype=np.int32)
        confs = np.zeros(n, dtype=np.float64)
        atr = np.full(n, 500.0)

        equity, _, _, _ = vectorized_backtest(
            close,
            signals,
            confs,
            atr,
            initial_capital=20000.0,
        )
        assert equity[0] == 20000.0


# ================================================================
# AcceleratedEvaluator 集成测试
# ================================================================


class TestAcceleratedEvaluator:
    """AcceleratedEvaluator 端到端集成"""

    def test_precompute_returns_features(self):
        """precompute 应返回特征字典"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(200)
        features = evaluator.precompute(data)
        assert "close" in features
        assert "atr" in features

    def test_evaluate_returns_metrics(self):
        """evaluate 应返回标准化指标字典"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(300)
        features = evaluator.precompute(data)
        config = {
            "threshold_parameters": {"confidence_threshold": 0.3},
            "state_machine": {},
            "backtest": {},
        }
        metrics = evaluator.evaluate(config, features)

        expected_keys = {
            "SHARPE_RATIO",
            "MAX_DRAWDOWN",
            "WIN_RATE",
            "PROFIT_FACTOR",
            "CALMAR_RATIO",
            "STABILITY_SCORE",
            "COMPOSITE_SCORE",
            "TOTAL_TRADES",
            "TOTAL_RETURN",
        }
        assert set(metrics.keys()) == expected_keys

    def test_metrics_values_reasonable(self):
        """指标值应在合理范围内"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(500)
        features = evaluator.precompute(data)
        config = {
            "threshold_parameters": {"confidence_threshold": 0.3},
            "state_machine": {"vol_climax_threshold": 1.5},
            "backtest": {},
        }
        metrics = evaluator.evaluate(config, features)

        assert 0.0 <= metrics["MAX_DRAWDOWN"] <= 1.0
        assert 0.0 <= metrics["WIN_RATE"] <= 1.0
        assert metrics["PROFIT_FACTOR"] >= 0.0
        assert 0.0 <= metrics["STABILITY_SCORE"] <= 1.0
        assert 0.0 <= metrics["COMPOSITE_SCORE"] <= 1.0
        assert metrics["TOTAL_TRADES"] >= 0

    def test_different_configs_different_results(self):
        """不同配置应产生不同结果"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(500, seed=55)
        features = evaluator.precompute(data)

        config_a = {
            "threshold_parameters": {"confidence_threshold": 0.1},
            "state_machine": {"vol_climax_threshold": 1.0},
            "backtest": {},
        }
        config_b = {
            "threshold_parameters": {"confidence_threshold": 0.8},
            "state_machine": {"vol_climax_threshold": 3.0},
            "backtest": {},
        }
        m_a = evaluator.evaluate(config_a, features)
        m_b = evaluator.evaluate(config_b, features)

        # 低阈值应产生更多交易
        assert m_a["TOTAL_TRADES"] >= m_b["TOTAL_TRADES"]

    def test_warmup_jit(self):
        """warmup_jit 应能正常执行不报错"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(200)
        features = evaluator.precompute(data)
        evaluator.warmup_jit(features)
        assert evaluator._compiled is True

    def test_warmup_jit_idempotent(self):
        """多次调用 warmup_jit 不应报错"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(200)
        features = evaluator.precompute(data)
        evaluator.warmup_jit(features)
        evaluator.warmup_jit(features)
        assert evaluator._compiled is True


# ================================================================
# 性能基准测试
# ================================================================


def _python_rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """纯 Python 滚动均值（基准对照）"""
    n = len(arr)
    result = np.empty(n, dtype=np.float64)
    for i in range(n):
        start = max(0, i - window + 1)
        result[i] = np.mean(arr[start : i + 1])
    return result


def _python_state_machine(
    close: np.ndarray,
    volume_ratio: np.ndarray,
) -> np.ndarray:
    """纯 Python 简化状态机（基准对照）"""
    n = len(close)
    states = np.zeros(n, dtype=np.int32)
    current_state = 0
    for i in range(50, n):
        if current_state == 0:
            if volume_ratio[i] > 2.0 and close[i] < close[i - 1]:
                current_state = 2
        elif current_state == 2:
            if close[i] > close[i - 1]:
                current_state = 3
        elif current_state == 3:
            if close[i] < close[i - 1]:
                current_state = 4
        elif current_state == 4:
            current_state = 0
        states[i] = current_state
    return states


def _python_backtest(
    close: np.ndarray,
    signals: np.ndarray,
    confidences: np.ndarray,
    atr: np.ndarray,
) -> np.ndarray:
    """纯 Python 简化回测（基准对照）"""
    n = len(close)
    equity = np.ones(n) * 10000.0
    position = 0.0
    entry_price = 0.0
    stop_loss = 0.0
    for i in range(1, n):
        equity[i] = equity[i - 1]
        if position > 0 and close[i] < stop_loss:
            pnl = (close[i] - entry_price) * position
            equity[i] += pnl
            position = 0.0
        if position == 0 and signals[i] == 1 and confidences[i] > 0.3:
            stop_dist = atr[i] * 2.0
            if stop_dist > 1e-10:
                position = (equity[i] * 0.02) / stop_dist
                entry_price = close[i]
                stop_loss = close[i] - stop_dist
    return equity


class TestPerformanceBenchmark:
    """性能基准测试 — 验证 Numba/NumPy 加速效果"""

    def test_pass1_faster_than_python(self):
        """Pass 1: NumPy 向量化应比纯 Python 快

        注意: 首次调用可能包含编译开销，使用第二次调用计时。
        """
        arr = np.random.randn(2000)

        # 预热
        _rolling_mean(arr, 20)
        _python_rolling_mean(arr, 20)

        # Python 基准
        t0 = time.perf_counter()
        for _ in range(10):
            _python_rolling_mean(arr, 20)
        python_time = time.perf_counter() - t0

        # NumPy 向量化
        t0 = time.perf_counter()
        for _ in range(10):
            _rolling_mean(arr, 20)
        numpy_time = time.perf_counter() - t0

        speedup = python_time / max(numpy_time, 1e-10)
        # NumPy 应至少快 2x（保守阈值，实际通常 10-100x）
        assert speedup > 2.0, (
            f"NumPy 加速不够: {speedup:.1f}x "
            f"(python={python_time:.4f}s, numpy={numpy_time:.4f}s)"
        )

    def test_pass2_numba_compiles_and_runs(self):
        """Pass 2: Numba 状态机应能编译运行且结果合理"""
        data = _make_data_dict(2000)
        features = precompute_features(data)

        # 首次调用（含编译）
        t0 = time.perf_counter()
        states, confs, sigs = state_machine_numba(
            features["close"],
            features["high"],
            features["low"],
            features["volume_ratio"],
            features["atr"],
            features["adx"],
            features["body_ratio"],
            features["lower_shadow"],
            features["upper_shadow"],
        )
        first_call = time.perf_counter() - t0

        # 第二次调用（已编译）
        t0 = time.perf_counter()
        for _ in range(100):
            state_machine_numba(
                features["close"],
                features["high"],
                features["low"],
                features["volume_ratio"],
                features["atr"],
                features["adx"],
                features["body_ratio"],
                features["lower_shadow"],
                features["upper_shadow"],
            )
        cached_time = (time.perf_counter() - t0) / 100

        if HAS_NUMBA:
            # 已编译版本应远快于首次编译
            assert cached_time < first_call, (
                f"缓存版本不快: first={first_call:.4f}s, cached={cached_time:.6f}s"
            )
            # 2000根数据，已编译后单次应 < 50ms
            assert cached_time < 0.050, (
                f"Numba 状态机太慢: {cached_time * 1000:.2f}ms (目标<50ms)"
            )
        else:
            # 无 Numba: 仅验证能正常执行
            assert len(states) == 2000

    def test_pass3_numba_backtest_speed(self):
        """Pass 3: Numba 回测应能快速执行"""
        n = 2000
        close = np.linspace(50000, 55000, n)
        signals = np.zeros(n, dtype=np.int32)
        # 每 50 根插入一个 BUY
        for i in range(100, n, 50):
            signals[i] = 1
        confs = np.where(signals != 0, 0.8, 0.0)
        atr = np.full(n, 500.0)

        # 首次（含编译）
        vectorized_backtest(close, signals, confs, atr)

        # 已编译
        t0 = time.perf_counter()
        for _ in range(100):
            vectorized_backtest(close, signals, confs, atr)
        cached_time = (time.perf_counter() - t0) / 100

        if HAS_NUMBA:
            # 2000根，已编译后单次应 < 10ms
            assert cached_time < 0.010, (
                f"Numba 回测太慢: {cached_time * 1000:.2f}ms (目标<10ms)"
            )
        else:
            assert cached_time < 1.0  # 纯 Python 应 < 1s

    def test_end_to_end_accelerated_evaluator_speed(self):
        """端到端: AcceleratedEvaluator 单次评估应 < 100ms（已编译后）"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(2000, seed=99)
        features = evaluator.precompute(data)

        config = {
            "threshold_parameters": {"confidence_threshold": 0.3},
            "state_machine": {"vol_climax_threshold": 1.5},
            "backtest": {},
        }

        # 首次（含编译）
        evaluator.evaluate(config, features)

        # 已编译
        t0 = time.perf_counter()
        for _ in range(50):
            evaluator.evaluate(config, features)
        avg_time = (time.perf_counter() - t0) / 50

        if HAS_NUMBA:
            assert avg_time < 0.100, f"评估太慢: {avg_time * 1000:.2f}ms (目标<100ms)"
        else:
            assert avg_time < 5.0  # 纯 Python 宽松阈值

    def test_precompute_shared_across_individuals(self):
        """特征预计算应在多个个体间共享（只算一次）"""
        evaluator = AcceleratedEvaluator()
        data = _make_data_dict(1000)

        # 预计算
        t0 = time.perf_counter()
        features = evaluator.precompute(data)
        precompute_time = time.perf_counter() - t0

        # 20 个个体评估
        configs = [
            {
                "threshold_parameters": {"confidence_threshold": 0.2 + i * 0.02},
                "state_machine": {"vol_climax_threshold": 1.5 + i * 0.1},
                "backtest": {},
            }
            for i in range(20)
        ]

        # 首次评估触发编译
        evaluator.evaluate(configs[0], features)

        t0 = time.perf_counter()
        for cfg in configs:
            evaluator.evaluate(cfg, features)
        eval_time = time.perf_counter() - t0

        # 20 个个体评估时间应远小于 20 次预计算
        # （因为特征共享，每次只跑 Pass 2 + Pass 3）
        assert eval_time < precompute_time * 20, (
            f"特征未共享: eval={eval_time:.4f}s, "
            f"precompute*20={precompute_time * 20:.4f}s"
        )
