"""OHLCV 数据验证器测试

验证 validate_ohlcv() 的6项检查：
1. 必需列存在性
2. high >= max(open, close)
3. low <= min(open, close)
4. volume >= 0
5. 无 NaN 值
6. 时间索引单调递增
"""

import numpy as np
import pandas as pd
import pytest

from src.plugins.data_pipeline.ohlcv_validator import validate_ohlcv


def _make_valid_df(n: int = 10) -> pd.DataFrame:
    """生成一个完全合法的 OHLCV DataFrame"""
    idx = pd.date_range("2025-01-01", periods=n, freq="1h")
    close = 100.0 + np.arange(n, dtype=float) * 0.1
    open_ = close - 0.05
    high = np.maximum(close, open_) + 0.5
    low = np.minimum(close, open_) - 0.5
    volume = np.full(n, 1000.0)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


class TestValidData:
    """合法数据应全部通过"""

    def test_valid_df_passes(self) -> None:
        result = validate_ohlcv(_make_valid_df())
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["rows_checked"] == 10


class TestEmptyAndNone:
    """空/None 输入"""

    def test_none_input(self) -> None:
        result = validate_ohlcv(None)
        assert result["valid"] is False
        assert any("空" in e or "None" in e for e in result["errors"])
        assert result["rows_checked"] == 0

    def test_empty_dataframe(self) -> None:
        result = validate_ohlcv(pd.DataFrame())
        assert result["valid"] is False
        assert result["rows_checked"] == 0


class TestMissingColumns:
    """缺少必需列"""

    def test_missing_volume(self) -> None:
        df = _make_valid_df()
        df = df.drop(columns=["volume"])
        result = validate_ohlcv(df)
        assert result["valid"] is False
        assert any("volume" in str(e) for e in result["errors"])

    def test_missing_multiple_columns(self) -> None:
        df = pd.DataFrame({"open": [1.0], "close": [2.0]})
        result = validate_ohlcv(df)
        assert result["valid"] is False
        assert any("缺少必需列" in e for e in result["errors"])


class TestNaNValues:
    """NaN 值检测"""

    def test_nan_in_close(self) -> None:
        df = _make_valid_df()
        df.iloc[3, df.columns.get_loc("close")] = np.nan
        result = validate_ohlcv(df)
        assert result["valid"] is False
        assert any("NaN" in e for e in result["errors"])

    def test_nan_in_volume(self) -> None:
        df = _make_valid_df()
        df.iloc[0, df.columns.get_loc("volume")] = np.nan
        result = validate_ohlcv(df)
        assert result["valid"] is False


class TestHighLowConstraints:
    """high/low 约束检查"""

    def test_high_below_max_open_close(self) -> None:
        """high < max(open, close) → 警告"""
        df = _make_valid_df()
        # 强制 high < close
        df.iloc[2, df.columns.get_loc("high")] = df.iloc[2]["close"] - 1.0
        result = validate_ohlcv(df)
        assert any("high" in w for w in result["warnings"])

    def test_low_above_min_open_close(self) -> None:
        """low > min(open, close) → 警告"""
        df = _make_valid_df()
        # 强制 low > open
        df.iloc[2, df.columns.get_loc("low")] = df.iloc[2]["open"] + 1.0
        result = validate_ohlcv(df)
        assert any("low" in w for w in result["warnings"])


class TestVolumeConstraint:
    """成交量约束"""

    def test_negative_volume(self) -> None:
        """volume < 0 → 错误"""
        df = _make_valid_df()
        df.iloc[0, df.columns.get_loc("volume")] = -100.0
        result = validate_ohlcv(df)
        assert result["valid"] is False
        assert any("负成交量" in e for e in result["errors"])

    def test_zero_volume_passes(self) -> None:
        """volume == 0 应该合法"""
        df = _make_valid_df()
        df.iloc[0, df.columns.get_loc("volume")] = 0.0
        result = validate_ohlcv(df)
        # 零成交量不是错误
        assert not any("负成交量" in e for e in result["errors"])


class TestTimeIndex:
    """时间索引单调性"""

    def test_non_monotonic_index_warns(self) -> None:
        """时间索引非单调递增 → 警告"""
        df = _make_valid_df()
        # 交换两行使索引非单调
        idx = list(df.index)
        idx[1], idx[2] = idx[2], idx[1]
        df.index = pd.DatetimeIndex(idx)
        result = validate_ohlcv(df)
        assert any("单调" in w for w in result["warnings"])

    def test_integer_index_no_crash(self) -> None:
        """整数索引不触发时间检查但不崩溃"""
        df = _make_valid_df().reset_index(drop=True)
        result = validate_ohlcv(df)
        # 整数 RangeIndex 也有 is_monotonic_increasing，应该通过
        assert result["valid"] is True
