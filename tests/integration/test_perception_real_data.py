"""感知层真实数据测试 — FVGDetector + CandlePhysical + PinBodyAnalyzer

验证感知层组件在真实合成 OHLCV 数据上产出有效结果。
"""

import pathlib
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from src.plugins.perception.fvg_detector import FVGDetector
from src.plugins.perception.candle_physical import CandlePhysical
from src.plugins.perception.pin_body_analyzer import (
    analyze_pin_vs_body,
    AnalysisContext,
)
from tests.fixtures.ohlcv_generator import make_ohlcv


# ================================================================
# FVG Detector
# ================================================================


class TestFVGDetectorRealData:
    """FVG 检测器真实数据测试"""

    def test_fvg_detector_instantiation(self) -> None:
        """FVGDetector 可实例化"""
        det = FVGDetector()
        assert det is not None

    def test_fvg_detect_gaps_trending(self) -> None:
        """趋势数据中检测 FVG"""
        det = FVGDetector()
        df = make_ohlcv(n=200, trend="up", start_price=100.0)
        gaps = det.detect_fvg_gaps(df)
        assert isinstance(gaps, list)

    def test_fvg_detect_gaps_flat(self) -> None:
        """横盘数据中检测 FVG"""
        det = FVGDetector()
        df = make_ohlcv(n=200, trend="flat", start_price=100.0)
        gaps = det.detect_fvg_gaps(df)
        assert isinstance(gaps, list)

    def test_fvg_get_signals(self) -> None:
        """获取 FVG 信号"""
        det = FVGDetector()
        df = make_ohlcv(n=200, trend="up", start_price=100.0)
        det.detect_fvg_gaps(df)
        signals = det.get_fvg_signals(current_price=120.0)
        assert isinstance(signals, dict)

    def test_fvg_statistics(self) -> None:
        """获取 FVG 统计信息"""
        det = FVGDetector()
        df = make_ohlcv(n=200, trend="up", start_price=100.0)
        det.detect_fvg_gaps(df)
        stats = det.get_statistics()
        assert isinstance(stats, dict)

    def test_fvg_minimum_bars(self) -> None:
        """最少 K 线数不崩溃"""
        det = FVGDetector()
        df = make_ohlcv(n=5, trend="flat", start_price=100.0)
        gaps = det.detect_fvg_gaps(df)
        assert isinstance(gaps, list)


# ================================================================
# Candle Physical Properties
# ================================================================


class TestCandlePhysicalRealData:
    """K 线物理属性分析真实数据测试"""

    def test_candle_physical_creation(self) -> None:
        """CandlePhysical 从 OHLCV 数据创建"""
        candle = CandlePhysical(
            open=100.0, high=105.0, low=98.0, close=103.0, volume=1000.0
        )
        assert candle is not None
        assert candle.body > 0
        assert candle.total_range > 0

    def test_candle_body_direction(self) -> None:
        """阳线和阴线方向正确"""
        bullish = CandlePhysical(
            open=100.0, high=105.0, low=99.0, close=104.0, volume=1000.0
        )
        assert bullish.body_direction == 1

        bearish = CandlePhysical(
            open=104.0, high=105.0, low=99.0, close=100.0, volume=1000.0
        )
        assert bearish.body_direction == -1

    def test_candle_shadow_analysis(self) -> None:
        """影线分析"""
        long_upper = CandlePhysical(
            open=100.0, high=110.0, low=99.0, close=101.0, volume=1000.0
        )
        assert long_upper.upper_shadow > long_upper.lower_shadow

        long_lower = CandlePhysical(
            open=100.0, high=101.0, low=90.0, close=99.0, volume=1000.0
        )
        assert long_lower.lower_shadow > long_lower.upper_shadow

    def test_candle_body_ratio(self) -> None:
        """实体比例在 [0, 1] 范围内"""
        candle = CandlePhysical(
            open=100.0, high=105.0, low=95.0, close=103.0, volume=1000.0
        )
        assert 0 <= candle.body_ratio <= 1

    def test_candle_from_real_data_series(self) -> None:
        """从合成数据序列创建多个 CandlePhysical"""
        df = make_ohlcv(n=50, trend="up", start_price=100.0)
        candles = []
        for _, row in df.iterrows():
            c = CandlePhysical(
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            candles.append(c)
            assert c.total_range >= 0

        assert len(candles) == 50


# ================================================================
# Pin Body Analyzer
# ================================================================


class TestPinBodyAnalyzerRealData:
    """针体分析器真实数据测试"""

    def _make_context(self) -> "AnalysisContext":
        """构建分析上下文"""
        return AnalysisContext(
            volatility_index=1.0,
            volume_moving_avg=1000.0,
            avg_body_size=3.0,
            atr14=5.0,
        )

    def test_analyze_pin_vs_body_basic(self) -> None:
        """基础针体分析"""
        candle = CandlePhysical(
            open=100.0, high=108.0, low=95.0, close=103.0, volume=1000.0
        )
        result = analyze_pin_vs_body(candle, self._make_context())
        assert result is not None

    def test_analyze_pin_hammer_pattern(self) -> None:
        """锤子线"""
        hammer = CandlePhysical(
            open=100.0, high=101.0, low=92.0, close=100.5, volume=1500.0
        )
        result = analyze_pin_vs_body(hammer, self._make_context())
        assert result is not None

    def test_analyze_pin_shooting_star(self) -> None:
        """射击之星"""
        star = CandlePhysical(
            open=100.0, high=108.0, low=99.5, close=100.5, volume=1200.0
        )
        result = analyze_pin_vs_body(star, self._make_context())
        assert result is not None


# ================================================================
# Perception Plugin Integration
# ================================================================


class TestPerceptionPluginIntegration:
    """感知层插件集成测试"""

    def test_perception_plugin_loads(self) -> None:
        """感知层插件可通过 WyckoffApp 加载"""
        from src.app import WyckoffApp

        old_journal = pathlib.Path("./data/position_journal.jsonl")
        old_journal_bak = pathlib.Path("./data/position_journal.jsonl.bak.perception")
        if old_journal.exists():
            old_journal.rename(old_journal_bak)

        wa = WyckoffApp(config_path="config.yaml", plugins_dir="src/plugins")
        wa.discover_and_load()

        perception = wa.plugin_manager.get_plugin("perception")
        assert perception is not None
        assert perception.is_active

        wa.plugin_manager.unload_all()

        if old_journal_bak.exists():
            if old_journal.exists():
                old_journal.unlink()
            old_journal_bak.rename(old_journal)
