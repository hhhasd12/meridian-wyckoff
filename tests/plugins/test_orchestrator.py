"""
Orchestrator 插件测试

测试 OrchestratorPlugin 的所有功能，包括：
- 初始化和继承
- 加载/卸载生命周期
- 配置更新
- 健康检查
- 系统启动/停止
- 系统状态查询
- 统计信息
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginState
from src.plugins.orchestrator.plugin import OrchestratorPlugin


class TestOrchestratorPluginInit:
    """测试插件初始化"""

    def test_init_default_name(self) -> None:
        """测试默认名称初始化"""
        plugin = OrchestratorPlugin()
        assert plugin.name == "orchestrator"

    def test_init_custom_name(self) -> None:
        """测试自定义名称初始化"""
        plugin = OrchestratorPlugin(name="my_orchestrator")
        assert plugin.name == "my_orchestrator"

    def test_init_inherits_base_plugin(self) -> None:
        """测试继承 BasePlugin"""
        plugin = OrchestratorPlugin()
        assert isinstance(plugin, BasePlugin)

    def test_init_attributes(self) -> None:
        """测试初始属性"""
        plugin = OrchestratorPlugin()
        assert plugin._decision_count == 0
        assert plugin._process_count == 0
        assert plugin._last_error is None
        assert plugin._is_running is False
        assert plugin._mode == "paper"


class TestOrchestratorLoadUnload:
    """测试加载/卸载生命周期"""

    def test_on_load_success(self) -> None:
        """测试成功加载"""
        plugin = OrchestratorPlugin()
        plugin._config = {"mode": "paper", "symbols": ["BTC/USDT"]}
        plugin.on_load()

        assert plugin._mode == "paper"
        assert plugin._symbols == ["BTC/USDT"]

    def test_on_unload(self) -> None:
        """测试卸载"""
        plugin = OrchestratorPlugin()
        plugin._config = {"mode": "paper"}
        plugin.on_load()
        plugin._is_running = True

        plugin.on_unload()

        assert plugin._is_running is False
        assert plugin._engine is None


class TestOrchestratorHealthCheck:
    """测试健康检查"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = OrchestratorPlugin()

    def test_health_check_healthy(self) -> None:
        """测试健康状态"""
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert "正常" in result.message

    def test_health_check_with_error(self) -> None:
        """测试有错误时健康检查"""
        self.plugin._last_error = "测试错误"
        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "错误" in result.message


class TestOrchestratorStartStop:
    """测试启动和停止"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = OrchestratorPlugin()

    @pytest.mark.asyncio
    async def test_start_system(self) -> None:
        """测试启动系统"""
        self.plugin._config = {"mode": "paper"}
        self.plugin.on_load()

        result = await self.plugin.start_system()

        assert result["success"] is True
        assert self.plugin._is_running is True

    @pytest.mark.asyncio
    async def test_stop_system(self) -> None:
        """测试停止系统"""
        self.plugin._is_running = True
        self.plugin._stop_event = asyncio.Event()

        result = await self.plugin.stop_system()

        assert result["success"] is True
        assert self.plugin._is_running is False


class TestOrchestratorSystemStatus:
    """测试系统状态"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = OrchestratorPlugin()

    def test_status_stopped(self) -> None:
        """测试停止状态"""
        status = self.plugin.get_system_status()
        assert status["status"] == "stopped"
        assert status["mode"] == "paper"

    def test_status_running(self) -> None:
        """测试运行状态"""
        self.plugin._is_running = True
        status = self.plugin.get_system_status()
        assert status["status"] == "running"


class TestOrchestratorStatistics:
    """测试统计信息"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = OrchestratorPlugin()

    def test_statistics_initial(self) -> None:
        """测试初始统计"""
        stats = self.plugin.get_statistics()

        assert stats["decision_count"] == 0
        assert stats["process_count"] == 0
        assert stats["is_running"] is False
        assert stats["mode"] == "paper"

    def test_statistics_after_ops(self) -> None:
        """测试操作后统计"""
        self.plugin._decision_count = 5
        self.plugin._process_count = 10
        self.plugin._is_running = True

        stats = self.plugin.get_statistics()

        assert stats["decision_count"] == 5
        assert stats["process_count"] == 10
        assert stats["is_running"] is True


class TestOrchestratorDecisionHistory:
    """测试决策历史"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = OrchestratorPlugin()

    def test_decision_history_empty(self) -> None:
        """测试空决策历史"""
        history = self.plugin.get_decision_history()
        assert history == []

    def test_decision_history_limit(self) -> None:
        """测试决策历史限制"""
        from src.kernel.types import TradingDecision, TradingSignal, DecisionContext
        from datetime import datetime

        for i in range(10):
            decision = TradingDecision(
                signal=TradingSignal.BUY,
                confidence=0.8,
                context=DecisionContext(
                    timestamp=datetime.now(),
                    market_regime="TRENDING",
                    regime_confidence=0.8,
                    timeframe_weights={"H4": 1.0},
                    detected_conflicts=[],
                ),
            )
            self.plugin._decision_history.append(decision)

        history = self.plugin.get_decision_history(limit=5)
        assert len(history) == 5


class TestOrchestratorRunLoop:
    """测试运行循环"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = OrchestratorPlugin()

    @pytest.mark.asyncio
    async def test_run_loop_starts_system(self) -> None:
        """测试运行循环启动系统"""
        self.plugin._config = {"mode": "paper", "data_refresh_interval": 1}
        self.plugin.on_load()

        task = asyncio.create_task(self.plugin.run_loop())
        await asyncio.sleep(0.1)

        assert self.plugin._is_running is True

        self.plugin.request_stop()
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def test_request_stop(self) -> None:
        """测试请求停止"""
        self.plugin._is_running = True
        self.plugin._stop_event = asyncio.Event()

        self.plugin.request_stop()

        assert self.plugin._is_running is False
        assert self.plugin._stop_event.is_set()
