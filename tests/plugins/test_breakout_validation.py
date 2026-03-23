"""突破验证 is_valid 键名一致性测试

验证 M4 问题：breakout_validator._create_breakout_record() 返回的字典
包含 "is_valid" 键，且 engine.py 通过 raw_breakout.get("is_valid", False)
能正确读取该值并传递到 BreakoutInfo 数据类。

结论：该 bug 不存在，is_valid 键在 validator 返回值和 engine 消费端完全一致。
"""

import numpy as np
import pandas as pd
import pytest

from src.kernel.types import BreakoutInfo
from src.plugins.signal_validation.breakout_validator import (
    BreakoutStatus,
    BreakoutValidator,
)


def _make_ohlcv(n: int = 30, base_price: float = 100.0) -> pd.DataFrame:
    """生成用于测试的 OHLCV DataFrame"""
    dates = pd.date_range("2026-01-01", periods=n, freq="h")
    np.random.seed(42)
    close = base_price + np.cumsum(np.random.randn(n) * 0.5)
    opens = close - np.random.uniform(0.1, 0.5, n)
    highs = close + np.random.uniform(0.5, 2.0, n)
    lows = close - np.random.uniform(0.5, 2.0, n)
    # 确保 OHLC 有效性: high >= max(open, close), low <= min(open, close)
    highs = np.maximum(highs, np.maximum(opens, close))
    lows = np.minimum(lows, np.minimum(opens, close))
    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": close,
            "volume": np.random.uniform(100, 1000, n),
        },
        index=dates,
    )
    return df


class TestBreakoutRecordContainsIsValid:
    """测试 _create_breakout_record 返回字典包含 is_valid 键"""

    def setup_method(self):
        self.validator = BreakoutValidator()

    def test_create_breakout_record_has_is_valid_key(self):
        """_create_breakout_record 返回的字典必须包含 is_valid 键"""
        record = self.validator._create_breakout_record(
            direction=1,
            breakout_price=105.0,
            breakout_level=100.0,
            breakout_strength=1.5,
            volume_confirmation=True,
            timestamp=pd.Timestamp("2026-01-01"),  # type: ignore[arg-type]
            atr=2.0,
        )

        assert "is_valid" in record, "返回字典缺少 is_valid 键"
        assert record["is_valid"] is True, "is_valid 应为 True"

    def test_create_breakout_record_has_status_field(self):
        """_create_breakout_record 同时包含 status 字段（BreakoutStatus 枚举）"""
        record = self.validator._create_breakout_record(
            direction=-1,
            breakout_price=95.0,
            breakout_level=100.0,
            breakout_strength=1.2,
            volume_confirmation=False,
            timestamp=pd.Timestamp("2026-01-02"),  # type: ignore[arg-type]
            atr=2.0,
        )

        assert "status" in record
        assert record["status"] == BreakoutStatus.INITIAL_BREAKOUT

    def test_breakout_record_all_required_keys_for_engine(self):
        """验证返回字典包含 engine.py 所读取的全部键"""
        record = self.validator._create_breakout_record(
            direction=1,
            breakout_price=105.0,
            breakout_level=100.0,
            breakout_strength=1.5,
            volume_confirmation=True,
            timestamp=pd.Timestamp("2026-01-01"),  # type: ignore[arg-type]
            atr=2.0,
        )

        # engine.py:503-511 所需的全部键
        required_keys = [
            "is_valid",
            "direction",
            "breakout_level",
            "breakout_strength",
            "volume_confirmation",
        ]
        for key in required_keys:
            assert key in record, f"返回字典缺少 engine.py 所需的键: {key}"


class TestBreakoutInfoFromValidatorResult:
    """测试从 validator 返回值构建 BreakoutInfo 的完整路径"""

    def setup_method(self):
        self.validator = BreakoutValidator()

    def test_breakout_info_from_raw_result(self):
        """模拟 engine.py:502-512 的逻辑：从 raw_breakout 构建 BreakoutInfo"""
        raw_breakout = self.validator._create_breakout_record(
            direction=1,
            breakout_price=105.0,
            breakout_level=100.0,
            breakout_strength=1.5,
            volume_confirmation=True,
            timestamp=pd.Timestamp("2026-01-01"),  # type: ignore[arg-type]
            atr=2.0,
        )

        # 完全复制 engine.py:502-512 的逻辑
        breakout_status = BreakoutInfo(
            is_valid=raw_breakout.get("is_valid", False),
            direction=raw_breakout.get("direction", 0),
            breakout_level=float(raw_breakout.get("breakout_level", 0.0)),
            breakout_strength=float(raw_breakout.get("breakout_strength", 0.0)),
            volume_confirmation=raw_breakout.get("volume_confirmation", False),
        )

        assert breakout_status.is_valid is True
        assert breakout_status.direction == 1
        assert breakout_status.breakout_level == 100.0
        assert breakout_status.breakout_strength == 1.5
        assert breakout_status.volume_confirmation is True

    def test_downward_breakout_propagation(self):
        """向下突破同样正确传递 is_valid"""
        raw_breakout = self.validator._create_breakout_record(
            direction=-1,
            breakout_price=95.0,
            breakout_level=100.0,
            breakout_strength=0.8,
            volume_confirmation=False,
            timestamp=pd.Timestamp("2026-01-02"),  # type: ignore[arg-type]
            atr=3.0,
        )

        breakout_status = BreakoutInfo(
            is_valid=raw_breakout.get("is_valid", False),
            direction=raw_breakout.get("direction", 0),
            breakout_level=float(raw_breakout.get("breakout_level", 0.0)),
            breakout_strength=float(raw_breakout.get("breakout_strength", 0.0)),
            volume_confirmation=raw_breakout.get("volume_confirmation", False),
        )

        assert breakout_status.is_valid is True
        assert breakout_status.direction == -1
        assert breakout_status.breakout_level == 100.0
        assert breakout_status.volume_confirmation is False


class TestDetectInitialBreakoutEndToEnd:
    """端到端测试：detect_initial_breakout → is_valid 传播"""

    def setup_method(self):
        self.validator = BreakoutValidator()

    def test_upward_breakout_detected_and_is_valid(self):
        """向上突破场景：收盘突破阻力位后，返回 is_valid=True"""
        df = _make_ohlcv(n=30, base_price=100.0)
        # 最后一根K线强势突破阻力位
        resistance = 101.0
        df.iloc[-1, df.columns.get_loc("close")] = 105.0
        df.iloc[-1, df.columns.get_loc("high")] = 106.0
        # 放量确认
        df.iloc[-1, df.columns.get_loc("volume")] = 2000.0

        result = self.validator.detect_initial_breakout(
            df=df,
            resistance_level=resistance,
            support_level=95.0,
            current_atr=1.0,
        )

        assert result is not None, "应检测到向上突破"
        assert result["is_valid"] is True
        assert result["direction"] == 1
        assert result["status"] == BreakoutStatus.INITIAL_BREAKOUT

        # 模拟 engine.py 消费路径
        breakout_info = BreakoutInfo(
            is_valid=result.get("is_valid", False),
            direction=result.get("direction", 0),
            breakout_level=float(result.get("breakout_level", 0.0)),
            breakout_strength=float(result.get("breakout_strength", 0.0)),
            volume_confirmation=result.get("volume_confirmation", False),
        )
        assert breakout_info.is_valid is True

    def test_no_breakout_returns_none(self):
        """无突破场景：价格未突破任何水平"""
        df = _make_ohlcv(n=30, base_price=100.0)
        # 确保价格在通道内
        df["close"] = 100.0
        df["high"] = 101.0
        df["low"] = 99.0

        result = self.validator.detect_initial_breakout(
            df=df,
            resistance_level=110.0,
            support_level=90.0,
            current_atr=2.0,
        )

        assert result is None, "不应检测到突破"

    def test_insufficient_data_returns_none(self):
        """数据不足（<5根K线）应返回 None"""
        df = _make_ohlcv(n=3, base_price=100.0)

        result = self.validator.detect_initial_breakout(
            df=df,
            resistance_level=101.0,
            support_level=99.0,
            current_atr=1.0,
        )

        assert result is None

    def test_downward_breakout_detected(self):
        """向下突破场景：收盘跌破支撑位"""
        df = _make_ohlcv(n=30, base_price=100.0)
        support = 99.0
        # 最后一根K线跌破支撑
        df.iloc[-1, df.columns.get_loc("close")] = 95.0
        df.iloc[-1, df.columns.get_loc("low")] = 94.0
        df.iloc[-1, df.columns.get_loc("volume")] = 2000.0

        result = self.validator.detect_initial_breakout(
            df=df,
            resistance_level=110.0,
            support_level=support,
            current_atr=1.0,
        )

        assert result is not None, "应检测到向下突破"
        assert result["is_valid"] is True
        assert result["direction"] == -1

        # engine.py 消费路径
        breakout_info = BreakoutInfo(
            is_valid=result.get("is_valid", False),
            direction=result.get("direction", 0),
            breakout_level=float(result.get("breakout_level", 0.0)),
            breakout_strength=float(result.get("breakout_strength", 0.0)),
            volume_confirmation=result.get("volume_confirmation", False),
        )
        assert breakout_info.is_valid is True
        assert breakout_info.direction == -1
