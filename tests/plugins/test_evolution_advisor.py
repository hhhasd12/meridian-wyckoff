"""进化顾问插件单元测试

测试覆盖：
- 插件初始化和生命周期
- 顾问禁用模式
- 事件订阅和异步分析
- Prompt 构建
- Advisor 分析逻辑
- fitness 趋势检测
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginState
from src.plugins.evolution_advisor.advisor import EvolutionAdvisor
from src.plugins.evolution_advisor.plugin import EvolutionAdvisorPlugin
from src.plugins.evolution_advisor.prompts import (
    build_cycle_analysis_prompt,
    build_mistake_translation_prompt,
    build_mutation_direction_prompt,
    build_plateau_detection_prompt,
)


class TestEvolutionAdvisorPluginInit:
    """测试插件初始化"""

    def test_init_default_name(self) -> None:
        """测试默认名称初始化"""
        plugin = EvolutionAdvisorPlugin()
        assert plugin.name == "evolution_advisor"

    def test_init_inherits_base_plugin(self) -> None:
        """测试继承 BasePlugin"""
        plugin = EvolutionAdvisorPlugin()
        assert isinstance(plugin, BasePlugin)

    def test_init_attributes(self) -> None:
        """测试初始属性"""
        plugin = EvolutionAdvisorPlugin()
        assert plugin._advisor is None
        assert plugin._enabled is False
        assert plugin._analysis_count == 0
        assert plugin._last_error is None
        assert plugin._last_analysis is None


class TestEvolutionAdvisorPluginLifecycle:
    """测试插件生命周期"""

    def test_on_load_disabled(self) -> None:
        """禁用模式下加载不初始化 advisor"""
        plugin = EvolutionAdvisorPlugin()
        plugin._config = {"enabled": False}
        plugin.on_load()
        assert plugin._enabled is False
        assert plugin._advisor is None

    def test_on_load_enabled(self) -> None:
        """启用模式下加载初始化 advisor"""
        plugin = EvolutionAdvisorPlugin()
        plugin._config = {
            "enabled": True,
            "provider": "openai",
            "model": "gpt-4o-mini",
        }
        plugin._event_bus = MagicMock()
        plugin.on_load()
        assert plugin._enabled is True
        assert plugin._advisor is not None

    def test_on_unload(self) -> None:
        """卸载清理资源"""
        plugin = EvolutionAdvisorPlugin()
        plugin._advisor = MagicMock()
        plugin._enabled = True
        plugin._last_analysis = {"test": True}
        plugin.on_unload()
        assert plugin._advisor is None
        assert plugin._enabled is False
        assert plugin._last_analysis is None

    def test_health_check_disabled(self) -> None:
        """禁用时健康检查返回 HEALTHY"""
        plugin = EvolutionAdvisorPlugin()
        plugin._enabled = False
        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert "禁用" in result.message

    def test_health_check_with_error(self) -> None:
        """有错误时返回 DEGRADED"""
        plugin = EvolutionAdvisorPlugin()
        plugin._enabled = True
        plugin._last_error = "API 连接失败"
        result = plugin.health_check()
        assert result.status == HealthStatus.DEGRADED

    def test_health_check_healthy(self) -> None:
        """正常运行返回 HEALTHY"""
        plugin = EvolutionAdvisorPlugin()
        plugin._enabled = True
        plugin._advisor = MagicMock()
        plugin._state = PluginState.ACTIVE
        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY


class TestEvolutionAdvisorPluginQueries:
    """测试公共查询接口"""

    def test_get_last_analysis_none(self) -> None:
        """无分析时返回 None"""
        plugin = EvolutionAdvisorPlugin()
        assert plugin.get_last_analysis() is None

    def test_get_last_analysis_with_data(self) -> None:
        """有分析时返回数据"""
        plugin = EvolutionAdvisorPlugin()
        plugin._last_analysis = {"generation": 5}
        result = plugin.get_last_analysis()
        assert result is not None
        assert result["generation"] == 5

    def test_get_analysis_history_no_advisor(self) -> None:
        """无 advisor 时返回空列表"""
        plugin = EvolutionAdvisorPlugin()
        assert plugin.get_analysis_history() == []

    def test_get_fitness_trend_no_advisor(self) -> None:
        """无 advisor 时返回默认趋势"""
        plugin = EvolutionAdvisorPlugin()
        result = plugin.get_fitness_trend()
        assert result["trend"] == "not_initialized"

    def test_get_advisor_status(self) -> None:
        """顾问状态查询"""
        plugin = EvolutionAdvisorPlugin()
        plugin._enabled = True
        plugin._analysis_count = 3
        status = plugin.get_advisor_status()
        assert status["enabled"] is True
        assert status["analysis_count"] == 3
        assert status["has_last_analysis"] is False


class TestPromptBuilders:
    """测试 Prompt 模板构建"""

    def test_cycle_analysis_prompt(self) -> None:
        """测试轮次分析 Prompt"""
        cycle_data = {
            "generation": 10,
            "best_fitness": 0.85,
            "best_config": {
                "STATE_MIN_CONFIDENCE": 0.35,
                "SPRING_FAILURE_BARS": 5,
            },
            "population_stats": {"avg": 0.65, "std": 0.12},
        }
        history = [
            {"generation": 8, "best_fitness": 0.80},
            {"generation": 9, "best_fitness": 0.82},
        ]
        prompt = build_cycle_analysis_prompt(cycle_data, history)
        assert "第 10 轮" in prompt
        assert "0.8500" in prompt
        assert "STATE_MIN_CONFIDENCE" in prompt
        assert "第8轮" in prompt

    def test_cycle_analysis_empty_history(self) -> None:
        """空历史的 Prompt"""
        prompt = build_cycle_analysis_prompt(
            {"generation": 1, "best_fitness": 0.5},
            [],
        )
        assert "无历史数据" in prompt

    def test_mistake_translation_prompt(self) -> None:
        """测试错误模式翻译 Prompt"""
        patterns = [
            {
                "pattern": "FREQUENT_FALSE_POSITIVE",
                "frequency": 0.35,
                "module": "wyckoff_state_machine",
                "description": "频繁误报",
            },
        ]
        prompt = build_mistake_translation_prompt(patterns)
        assert "FREQUENT_FALSE_POSITIVE" in prompt
        assert "35.0%" in prompt

    def test_mistake_translation_empty(self) -> None:
        """空模式的 Prompt"""
        prompt = build_mistake_translation_prompt([])
        assert "没有检测到" in prompt

    def test_plateau_detection_prompt(self) -> None:
        """测试局部最优检测 Prompt"""
        fitness = [0.80, 0.81, 0.81, 0.80, 0.81]
        configs = [
            {"a": 1.0},
            {"a": 1.01},
            {"a": 1.01},
            {"a": 1.02},
            {"a": 1.02},
        ]
        prompt = build_plateau_detection_prompt(fitness, configs)
        assert "停滞" in prompt
        assert "0.8000" in prompt

    def test_plateau_insufficient_data(self) -> None:
        """数据不足的 Prompt"""
        prompt = build_plateau_detection_prompt([0.5], [])
        assert "不足" in prompt

    def test_mutation_direction_prompt(self) -> None:
        """测试变异方向 Prompt"""
        prompt = build_mutation_direction_prompt(
            {"SPRING_FAILURE_BARS": 5, "STATE_MIN_CONFIDENCE": 0.35},
            [{"pattern": "TIMING_ERROR", "frequency": 0.2}],
            0.75,
        )
        assert "SPRING_FAILURE_BARS" in prompt
        assert "TIMING_ERROR" in prompt
        assert "0.7500" in prompt


class TestEvolutionAdvisor:
    """测试 EvolutionAdvisor 核心逻辑"""

    def test_init_defaults(self) -> None:
        """测试默认初始化"""
        advisor = EvolutionAdvisor()
        assert advisor.provider == "openai"
        assert advisor.model == "gpt-4o-mini"
        assert advisor.analysis_history == []

    def test_fitness_trend_insufficient_data(self) -> None:
        """数据不足时的趋势"""
        advisor = EvolutionAdvisor()
        result = advisor.get_fitness_trend()
        assert result["trend"] == "insufficient_data"

    def test_fitness_trend_improving(self) -> None:
        """fitness 上升趋势"""
        advisor = EvolutionAdvisor()
        advisor._fitness_history = [0.5, 0.6, 0.7]
        result = advisor.get_fitness_trend()
        assert result["trend"] == "improving"
        assert result["latest"] == 0.7

    def test_fitness_trend_declining(self) -> None:
        """fitness 下降趋势"""
        advisor = EvolutionAdvisor()
        advisor._fitness_history = [0.7, 0.6, 0.5]
        result = advisor.get_fitness_trend()
        assert result["trend"] == "declining"

    def test_fitness_trend_plateau(self) -> None:
        """fitness 停滞检测"""
        advisor = EvolutionAdvisor()
        advisor._fitness_history = [0.80, 0.80, 0.80, 0.80, 0.80]
        result = advisor.get_fitness_trend()
        assert result["is_plateau"] is True

    def test_analysis_history_limit(self) -> None:
        """分析历史限制"""
        advisor = EvolutionAdvisor(max_history=3)
        advisor.analysis_history = [
            {"g": 1},
            {"g": 2},
            {"g": 3},
            {"g": 4},
        ]
        result = advisor.get_analysis_history(2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_analyze_cycle_basic(self) -> None:
        """基本分析流程（Mock LLM）"""
        advisor = EvolutionAdvisor(provider="openai")

        async def mock_llm(prompt: str) -> str:
            return "分析结果: 表现良好"

        advisor._call_llm = mock_llm  # type: ignore[assignment]

        result = await advisor.analyze_cycle(
            {
                "generation": 5,
                "best_fitness": 0.8,
                "best_config": {"a": 1},
            },
        )
        assert result["generation"] == 5
        assert result["best_fitness"] == 0.8
        assert result["analysis"] == "分析结果: 表现良好"
        assert len(advisor.analysis_history) == 1
        assert len(advisor._fitness_history) == 1

    @pytest.mark.asyncio
    async def test_analyze_cycle_with_mistakes(self) -> None:
        """带错误模式的分析"""
        advisor = EvolutionAdvisor(provider="openai")

        async def mock_llm(prompt: str) -> str:
            return "模拟分析"

        advisor._call_llm = mock_llm  # type: ignore[assignment]

        result = await advisor.analyze_cycle(
            {
                "generation": 10,
                "best_fitness": 0.9,
                "best_config": {"b": 2},
            },
            mistake_patterns=[
                {"pattern": "TIMING_ERROR", "frequency": 0.3},
            ],
        )
        assert result["mistake_summary"] == "模拟分析"
        assert result["mutation_advice"] == "模拟分析"

    @pytest.mark.asyncio
    async def test_call_llm_unknown_provider(self) -> None:
        """未知提供者回退"""
        advisor = EvolutionAdvisor(provider="unknown")
        result = await advisor._call_llm("test")
        assert "未配置" in result

    @pytest.mark.asyncio
    async def test_call_openai_no_key(self) -> None:
        """无 API Key 时的回退"""
        advisor = EvolutionAdvisor(provider="openai", api_key="")
        # 清除环境变量
        with patch.dict("os.environ", {}, clear=True):
            advisor.api_key = ""
            result = await advisor._call_openai("test")
            assert "未配置" in result
