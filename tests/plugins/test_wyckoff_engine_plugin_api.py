"""WyckoffEnginePlugin API 测试

验证插件壳层正确暴露 get_current_state() 和 process_market_data()，
确保 src/api/app.py 能通过插件接口访问引擎状态。

测试内容：
1. 未激活时 get_current_state() 返回 None
2. 激活后 get_current_state() 返回有效状态字典
3. 未激活时 process_market_data() 抛出 RuntimeError
4. 激活后 process_market_data() 返回正确类型
5. deactivate 后引擎被清理
6. hasattr 检查（模拟 api/app.py 的调用模式）
"""

import pytest
import pandas as pd

from src.kernel.types import TradingDecision
from src.plugins.wyckoff_engine.engine import EngineEvents
from src.plugins.wyckoff_engine.plugin import WyckoffEnginePlugin
from tests.fixtures.ohlcv_generator import make_multi_tf_data


class TestWyckoffEnginePluginAPI:
    """验证 WyckoffEnginePlugin 暴露的公开 API"""

    def setup_method(self) -> None:
        self.plugin = WyckoffEnginePlugin()

    # ---- 未激活状态 ----

    def test_get_current_state_before_activate_returns_none(self) -> None:
        """未激活时 get_current_state() 应返回 None"""
        assert self.plugin.engine is None
        result = self.plugin.get_current_state()
        assert result is None

    def test_process_market_data_before_activate_raises(self) -> None:
        """未激活时 process_market_data() 应抛出 RuntimeError"""
        data = make_multi_tf_data(h4_bars=50, trend="flat")
        with pytest.raises(RuntimeError, match="未激活"):
            self.plugin.process_market_data(
                symbol="BTC/USDT",
                timeframes=list(data.keys()),
                data_dict=data,
            )

    # ---- 激活后 ----

    @pytest.mark.asyncio
    async def test_get_current_state_after_activate(self) -> None:
        """激活后 get_current_state() 应返回包含引擎状态的字典"""
        await self.plugin.activate({"config": {"wyckoff_engine": {}}})

        state = self.plugin.get_current_state()
        assert state is not None
        assert isinstance(state, dict)
        # 必须包含的顶层键
        assert "timeframes" in state
        assert "state_machines" in state
        assert "last_candle_time" in state
        assert "bar_index" in state
        # 初始状态
        assert state["bar_index"] == 0
        assert state["last_candle_time"] is None

    @pytest.mark.asyncio
    async def test_get_current_state_has_state_machine_entries(self) -> None:
        """每个时间框架应有对应的状态机条目"""
        await self.plugin.activate(
            {
                "config": {
                    "wyckoff_engine": {
                        "timeframes": ["H4", "H1", "M15"],
                    }
                }
            }
        )

        state = self.plugin.get_current_state()
        assert state is not None
        sm = state["state_machines"]
        assert isinstance(sm, dict)
        for tf in ["H4", "H1", "M15"]:
            assert tf in sm, f"缺少时间框架 {tf} 的状态机"
            entry = sm[tf]
            assert "current_state" in entry
            assert "direction" in entry
            assert "confidence" in entry

    @pytest.mark.asyncio
    async def test_process_market_data_after_activate(self) -> None:
        """激活后 process_market_data() 应返回 (TradingDecision, EngineEvents)"""
        await self.plugin.activate({"config": {"wyckoff_engine": {}}})

        data = make_multi_tf_data(h4_bars=100, trend="flat")
        decision, events = self.plugin.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )
        assert isinstance(decision, TradingDecision)
        assert isinstance(events, EngineEvents)

    @pytest.mark.asyncio
    async def test_state_updates_after_processing(self) -> None:
        """处理数据后 get_current_state() 仍然返回有效状态"""
        await self.plugin.activate({"config": {"wyckoff_engine": {}}})

        data = make_multi_tf_data(h4_bars=100, trend="flat")
        decision, events = self.plugin.process_market_data(
            symbol="BTC/USDT",
            timeframes=list(data.keys()),
            data_dict=data,
        )

        # process_market_data 返回了有效结果
        assert isinstance(decision, TradingDecision)
        assert isinstance(events, EngineEvents)

        # 处理后状态快照仍然有效
        state = self.plugin.get_current_state()
        assert state is not None
        assert "state_machines" in state
        # 状态机应有条目（引擎正常工作）
        assert len(state["state_machines"]) > 0

    # ---- 停用 ----

    @pytest.mark.asyncio
    async def test_deactivate_clears_engine(self) -> None:
        """deactivate() 后引擎应被清理"""
        await self.plugin.activate({"config": {"wyckoff_engine": {}}})
        assert self.plugin.engine is not None

        await self.plugin.deactivate()
        assert self.plugin.engine is None
        assert self.plugin.get_current_state() is None

    # ---- API 调用模式（模拟 api/app.py） ----

    def test_hasattr_check_matches_api_pattern(self) -> None:
        """api/app.py 使用 hasattr 检查方法是否存在"""
        # 模拟 api/app.py 的调用模式（L246）
        assert hasattr(self.plugin, "get_current_state")
        assert hasattr(self.plugin, "process_market_data")
        assert callable(self.plugin.get_current_state)
        assert callable(self.plugin.process_market_data)

    @pytest.mark.asyncio
    async def test_api_pattern_returns_non_none_when_active(self) -> None:
        """api/app.py 调用模式：激活引擎后 get_current_state 不应返回 None"""
        await self.plugin.activate({"config": {"wyckoff_engine": {}}})

        # 模拟 api/app.py L244-247 的完整调用链
        engine_state = None
        if hasattr(self.plugin, "get_current_state"):
            engine_state = self.plugin.get_current_state()

        assert engine_state is not None, (
            "api/app.py 会得到 None — 引擎状态不会显示在仪表盘"
        )
        assert isinstance(engine_state, dict)

    def test_on_unload_clears_engine(self) -> None:
        """on_unload() 应清理引擎"""
        self.plugin.engine = "mock"  # type: ignore
        self.plugin.on_unload()
        assert self.plugin.engine is None
