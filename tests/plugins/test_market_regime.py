"""market_regime 插件测试

测试 MarketRegimePlugin 的生命周期、事件通信和检测功能。
"""

import numpy as np
import pandas as pd
import pytest

from src.kernel.event_bus import EventBus
from src.kernel.types import HealthStatus, PluginState
from src.plugins.market_regime.detector import (
    MarketRegime,
    RegimeDetector,
)
from src.plugins.market_regime.plugin import MarketRegimePlugin


# ---- 测试数据工具 ----


def _make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """生成模拟OHLCV数据"""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.rand(n) * 2
    low = close - np.random.rand(n) * 2
    open_price = np.roll(close, 1) + np.random.randn(n) * 0.1
    volume = np.random.rand(n) * 1000 + 500

    return pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


# ---- RegimeDetector 单元测试 ----


class TestRegimeDetector:
    """RegimeDetector 核心逻辑测试"""

    def setup_method(self) -> None:
        self.detector = RegimeDetector()

    def test_detect_with_sufficient_data(self) -> None:
        """测试正常数据的体制检测"""
        df = _make_ohlcv(100)
        result = self.detector.detect_regime(df)

        assert "regime" in result
        assert "confidence" in result
        assert "metrics" in result
        assert "reasons" in result
        assert isinstance(result["regime"], MarketRegime)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_detect_with_insufficient_data(self) -> None:
        """测试数据不足的情况"""
        df = _make_ohlcv(5)
        result = self.detector.detect_regime(df)

        assert result["regime"] == MarketRegime.UNKNOWN
        assert result["confidence"] == 0.0

    def test_custom_config(self) -> None:
        """测试自定义配置"""
        config = {
            "atr_period": 10,
            "adx_period": 10,
            "volatility_lookback": 15,
            "trending_threshold": 30.0,
            "volatility_threshold": 2.0,
        }
        detector = RegimeDetector(config=config)
        assert detector.atr_period == 10
        assert detector.trending_threshold == 30.0

    def test_regime_history(self) -> None:
        """测试体制历史记录"""
        df = _make_ohlcv(100)
        self.detector.detect_regime(df)
        history = self.detector.get_regime_history(10)
        assert len(history) == 1

    def test_current_regime(self) -> None:
        """测试获取当前体制"""
        df = _make_ohlcv(100)
        self.detector.detect_regime(df)
        current = self.detector.get_current_regime()
        assert "regime" in current
        assert "confidence" in current

    def test_enum_values(self) -> None:
        """测试 MarketRegime 枚举值"""
        assert MarketRegime.TRENDING.value == "TRENDING"
        assert MarketRegime.RANGING.value == "RANGING"
        assert MarketRegime.VOLATILE.value == "VOLATILE"
        assert MarketRegime.UNKNOWN.value == "UNKNOWN"


# ---- MarketRegimePlugin 插件测试 ----


class TestMarketRegimePlugin:
    """MarketRegimePlugin 插件生命周期和事件测试"""

    def setup_method(self) -> None:
        self.event_bus = EventBus(enable_history=True)
        self.plugin = MarketRegimePlugin(
            name="market_regime",
            config={"atr_period": 14, "adx_period": 14},
        )
        # 注入事件总线
        self.plugin._event_bus = self.event_bus

    def test_plugin_init(self) -> None:
        """测试插件初始化"""
        assert self.plugin.name == "market_regime"
        assert self.plugin.detector is None
        assert self.plugin._last_regime is None

    def test_on_load(self) -> None:
        """测试插件加载"""
        self.plugin.on_load()
        assert self.plugin.detector is not None
        assert isinstance(
            self.plugin.detector, RegimeDetector
        )

    def test_on_unload(self) -> None:
        """测试插件卸载"""
        self.plugin.on_load()
        self.plugin.on_unload()
        assert self.plugin.detector is None
        assert self.plugin._last_regime is None

    def test_detect_after_load(self) -> None:
        """测试加载后手动检测"""
        self.plugin.on_load()
        df = _make_ohlcv(100)
        result = self.plugin.detect(df)

        assert "regime" in result
        assert isinstance(result["regime"], MarketRegime)

    def test_detect_before_load_raises(self) -> None:
        """测试未加载时检测应抛出异常"""
        df = _make_ohlcv(100)
        with pytest.raises(RuntimeError, match="未加载"):
            self.plugin.detect(df)

    def test_event_emission_on_detect(self) -> None:
        """测试检测后发布事件"""
        received_events: list = []

        def handler(
            event_name: str, data: dict
        ) -> None:
            received_events.append(
                (event_name, data)
            )

        self.event_bus.subscribe(
            "market_regime.detected", handler
        )

        self.plugin.on_load()
        df = _make_ohlcv(100)
        self.plugin.detect(df)

        assert len(received_events) == 1
        name, data = received_events[0]
        assert name == "market_regime.detected"
        assert "regime" in data
        assert "confidence" in data

    def test_regime_change_event(self) -> None:
        """测试体制变化事件"""
        change_events: list = []

        def handler(
            event_name: str, data: dict
        ) -> None:
            change_events.append(data)

        self.event_bus.subscribe(
            "market_regime.changed", handler
        )

        self.plugin.on_load()

        # 设置初始体制
        self.plugin._last_regime = MarketRegime.RANGING

        # 执行检测（结果可能不同于 RANGING）
        df = _make_ohlcv(100)
        result = self.plugin.detect(df)

        # 如果体制确实变化了，应该收到变化事件
        if result["regime"] != MarketRegime.RANGING:
            assert len(change_events) == 1
            assert "old_regime" in change_events[0]
            assert "new_regime" in change_events[0]

    def test_ohlcv_ready_event_handler(self) -> None:
        """测试通过事件触发检测"""
        detected_events: list = []

        def handler(
            event_name: str, data: dict
        ) -> None:
            detected_events.append(data)

        self.event_bus.subscribe(
            "market_regime.detected", handler
        )

        self.plugin.on_load()

        # 模拟发送 ohlcv_ready 事件
        df = _make_ohlcv(100)
        self.event_bus.emit(
            "data_pipeline.ohlcv_ready",
            {"df": df},
        )

        assert len(detected_events) == 1

    def test_ohlcv_ready_without_df(self) -> None:
        """测试缺少 DataFrame 的事件"""
        detected_events: list = []

        def handler(
            event_name: str, data: dict
        ) -> None:
            detected_events.append(data)

        self.event_bus.subscribe(
            "market_regime.detected", handler
        )

        self.plugin.on_load()

        # 发送无效事件
        self.event_bus.emit(
            "data_pipeline.ohlcv_ready",
            {"symbol": "BTC"},
        )

        # 不应产生检测事件
        assert len(detected_events) == 0

    def test_config_update(self) -> None:
        """测试配置热更新"""
        self.plugin.on_load()
        new_config = {
            "atr_period": 20,
            "trending_threshold": 30.0,
        }
        self.plugin.on_config_update(new_config)

        assert self.plugin.detector is not None
        assert self.plugin.detector.atr_period == 20
        assert (
            self.plugin.detector.trending_threshold == 30.0
        )

    def test_health_check_healthy(self) -> None:
        """测试健康检查 - 正常状态"""
        self.plugin.on_load()
        self.plugin._state = PluginState.ACTIVE
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    def test_health_check_no_detector(self) -> None:
        """测试健康检查 - detector 未初始化"""
        self.plugin._state = PluginState.ACTIVE
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY

    def test_get_current_regime_before_load(self) -> None:
        """测试未加载时获取当前体制"""
        result = self.plugin.get_current_regime()
        assert result["regime"] == MarketRegime.UNKNOWN

    def test_get_regime_history_before_load(self) -> None:
        """测试未加载时获取历史"""
        history = self.plugin.get_regime_history()
        assert history == []
