"""
周期权重系统插件测试

测试 WeightSystemPlugin 的所有功能。
"""

import pytest
from unittest.mock import MagicMock, patch

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthStatus, PluginState
from src.plugins.weight_system.plugin import WeightSystemPlugin


class TestWeightSystemPluginInit:
    """测试插件初始化"""

    def test_init_default_name(self):
        """测试默认名称"""
        plugin = WeightSystemPlugin()
        assert plugin.name == "weight_system"

    def test_init_custom_name(self):
        """测试自定义名称"""
        plugin = WeightSystemPlugin(name="custom_weight")
        assert plugin.name == "custom_weight"

    def test_init_inherits_base_plugin(self):
        """测试继承 BasePlugin"""
        plugin = WeightSystemPlugin()
        assert isinstance(plugin, BasePlugin)

    def test_init_attributes(self):
        """测试初始属性"""
        plugin = WeightSystemPlugin()
        assert plugin._weight_filter is None
        assert plugin._weights_calc_count == 0
        assert plugin._score_calc_count == 0
        assert plugin._decision_count == 0
        assert plugin._recommend_count == 0
        assert plugin._last_error is None


class TestWeightSystemPluginLoadUnload:
    """测试插件加载和卸载"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_on_load_default_config(self, mock_filter_cls):
        """测试默认配置加载"""
        self.plugin.on_load()
        mock_filter_cls.assert_called_once_with(config=None)
        assert self.plugin._weight_filter is not None

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_on_load_with_config(self, mock_filter_cls):
        """测试带配置加载"""
        self.plugin._config = {
            "weights": {"W": 0.3, "D": 0.2},
            "normalize": True,
            "min_weight": 0.03,
        }
        self.plugin.on_load()
        call_args = mock_filter_cls.call_args
        config = call_args[1]["config"]
        assert config["weights"] == {"W": 0.3, "D": 0.2}
        assert config["normalize"] is True
        assert config["min_weight"] == 0.03

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_on_unload(self, mock_filter_cls):
        """测试卸载"""
        self.plugin.on_load()
        self.plugin._weights_calc_count = 5
        self.plugin._score_calc_count = 3
        self.plugin._decision_count = 2
        self.plugin._recommend_count = 1
        self.plugin._last_error = "some error"

        self.plugin.on_unload()

        assert self.plugin._weight_filter is None
        assert self.plugin._weights_calc_count == 0
        assert self.plugin._score_calc_count == 0
        assert self.plugin._decision_count == 0
        assert self.plugin._recommend_count == 0
        assert self.plugin._last_error is None


class TestWeightSystemPluginConfigUpdate:
    """测试配置更新"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_config_update_when_loaded(self, mock_filter_cls):
        """测试加载后配置更新"""
        self.plugin.on_load()
        old_filter = self.plugin._weight_filter

        new_config = {"min_weight": 0.08, "normalize": False}
        self.plugin.on_config_update(new_config)

        assert mock_filter_cls.call_count == 2
        assert self.plugin._weight_filter is not None

    def test_config_update_when_not_loaded(self):
        """测试未加载时配置更新（不应报错）"""
        self.plugin.on_config_update({"min_weight": 0.1})
        assert self.plugin._weight_filter is None


class TestWeightSystemHealthCheck:
    """测试健康检查"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    def test_health_check_not_active(self):
        """测试非活跃状态"""
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "状态异常" in result.message

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_health_check_active_healthy(self, mock_cls):
        """测试活跃且健康"""
        self.plugin.on_load()
        self.plugin._state = PluginState.ACTIVE
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert "正常" in result.message

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_health_check_active_with_error(self, mock_cls):
        """测试活跃但有错误"""
        self.plugin.on_load()
        self.plugin._state = PluginState.ACTIVE
        self.plugin._last_error = "测试错误"
        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "错误" in result.message

    def test_health_check_filter_none(self):
        """测试 filter 为 None"""
        self.plugin._state = PluginState.ACTIVE
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未初始化" in result.message


class TestWeightSystemGetWeights:
    """测试获取权重"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    def test_get_weights_not_loaded(self):
        """测试未加载时获取权重"""
        with pytest.raises(RuntimeError, match="未加载"):
            self.plugin.get_weights()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_get_weights_default_regime(self, mock_cls):
        """测试默认体制获取权重"""
        from src.plugins.weight_system.period_weight_filter import Timeframe

        mock_filter = MagicMock()
        mock_filter.get_weights.return_value = {
            Timeframe.WEEKLY: 0.22,
            Timeframe.DAILY: 0.18,
        }
        mock_cls.return_value = mock_filter
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        result = self.plugin.get_weights()
        assert result == {"W": 0.22, "D": 0.18}
        assert self.plugin._weights_calc_count == 1
        self.plugin.emit_event.assert_called_once()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_get_weights_trending(self, mock_cls):
        """测试趋势体制获取权重"""
        from src.plugins.weight_system.period_weight_filter import Timeframe

        mock_filter = MagicMock()
        mock_filter.get_weights.return_value = {
            Timeframe.WEEKLY: 0.30,
        }
        mock_cls.return_value = mock_filter
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        result = self.plugin.get_weights("TRENDING")
        assert result == {"W": 0.30}
        mock_filter.get_weights.assert_called_with("TRENDING")

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_get_weights_error(self, mock_cls):
        """测试获取权重异常"""
        mock_filter = MagicMock()
        mock_filter.get_weights.side_effect = ValueError("无效体制")
        mock_cls.return_value = mock_filter
        self.plugin.on_load()

        with pytest.raises(ValueError):
            self.plugin.get_weights("INVALID")
        assert self.plugin._last_error is not None


class TestWeightSystemWeightedScore:
    """测试加权分数计算"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    def test_weighted_score_not_loaded(self):
        """测试未加载时计算加权分数"""
        with pytest.raises(RuntimeError, match="未加载"):
            self.plugin.calculate_weighted_score({"W": 0.8})

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_weighted_score_success(self, mock_cls):
        """测试成功计算加权分数"""
        mock_filter = MagicMock()
        mock_filter.calculate_weighted_score.return_value = 0.75
        mock_cls.return_value = mock_filter
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        scores = {"W": 0.8, "D": 0.6, "H4": 0.7}
        result = self.plugin.calculate_weighted_score(scores, "TRENDING")

        assert result == 0.75
        assert self.plugin._score_calc_count == 1
        self.plugin.emit_event.assert_called_once()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_weighted_score_error(self, mock_cls):
        """测试计算加权分数异常"""
        mock_filter = MagicMock()
        mock_filter.calculate_weighted_score.side_effect = (
            ValueError("数据错误")
        )
        mock_cls.return_value = mock_filter
        self.plugin.on_load()

        with pytest.raises(ValueError):
            self.plugin.calculate_weighted_score({})
        assert self.plugin._last_error is not None


class TestWeightSystemWeightedDecision:
    """测试加权决策"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    def test_weighted_decision_not_loaded(self):
        """测试未加载时生成决策"""
        with pytest.raises(RuntimeError, match="未加载"):
            self.plugin.get_weighted_decision({})

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_weighted_decision_success(self, mock_cls):
        """测试成功生成加权决策"""
        mock_filter = MagicMock()
        mock_filter.get_weighted_decision.return_value = {
            "primary_bias": "BULLISH",
            "confidence": 0.8,
            "timeframe_contributions": {},
            "regime": "TRENDING",
        }
        mock_cls.return_value = mock_filter
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        decisions = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "NEUTRAL", "confidence": 0.6},
        }
        result = self.plugin.get_weighted_decision(decisions, "TRENDING")

        assert result["primary_bias"] == "BULLISH"
        assert result["confidence"] == 0.8
        assert self.plugin._decision_count == 1
        self.plugin.emit_event.assert_called_once()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_weighted_decision_error(self, mock_cls):
        """测试生成决策异常"""
        mock_filter = MagicMock()
        mock_filter.get_weighted_decision.side_effect = (
            TypeError("类型错误")
        )
        mock_cls.return_value = mock_filter
        self.plugin.on_load()

        with pytest.raises(TypeError):
            self.plugin.get_weighted_decision({})
        assert self.plugin._last_error is not None


class TestWeightSystemRecommend:
    """测试时间框架推荐"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    def test_recommend_not_loaded(self):
        """测试未加载时推荐"""
        with pytest.raises(RuntimeError, match="未加载"):
            self.plugin.recommend_timeframe_focus()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_recommend_success(self, mock_cls):
        """测试成功推荐"""
        mock_filter = MagicMock()
        mock_filter.recommend_timeframe_focus.return_value = [
            ("W", 0.30), ("D", 0.20), ("H4", 0.15),
        ]
        mock_cls.return_value = mock_filter
        self.plugin.on_load()
        self.plugin.emit_event = MagicMock(return_value=1)

        result = self.plugin.recommend_timeframe_focus(
            "TRENDING", "BULLISH"
        )
        assert len(result) == 3
        assert result[0] == ("W", 0.30)
        assert self.plugin._recommend_count == 1

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_recommend_error(self, mock_cls):
        """测试推荐异常"""
        mock_filter = MagicMock()
        mock_filter.recommend_timeframe_focus.side_effect = (
            RuntimeError("推荐失败")
        )
        mock_cls.return_value = mock_filter
        self.plugin.on_load()

        with pytest.raises(RuntimeError):
            self.plugin.recommend_timeframe_focus()
        assert self.plugin._last_error is not None


class TestWeightSystemConfigReport:
    """测试配置报告"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    def test_config_report_not_loaded(self):
        """测试未加载时获取配置报告"""
        with pytest.raises(RuntimeError, match="未加载"):
            self.plugin.get_config_report()

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_config_report_success(self, mock_cls):
        """测试成功获取配置报告"""
        mock_filter = MagicMock()
        mock_filter.get_config_report.return_value = {
            "base_weights": {"W": 0.22},
            "normalize": True,
            "min_weight": 0.05,
        }
        mock_cls.return_value = mock_filter
        self.plugin.on_load()

        result = self.plugin.get_config_report()
        assert result["normalize"] is True
        assert result["min_weight"] == 0.05


class TestWeightSystemStatistics:
    """测试统计信息"""

    def setup_method(self):
        """初始化测试"""
        self.plugin = WeightSystemPlugin()

    def test_statistics_initial(self):
        """测试初始统计"""
        stats = self.plugin.get_statistics()
        assert stats["weights_calc_count"] == 0
        assert stats["score_calc_count"] == 0
        assert stats["decision_count"] == 0
        assert stats["recommend_count"] == 0
        assert stats["last_error"] is None
        assert stats["filter_loaded"] is False

    @patch("src.plugins.weight_system.period_weight_filter.PeriodWeightFilter")
    def test_statistics_after_operations(self, mock_cls):
        """测试操作后统计"""
        mock_cls.return_value = MagicMock()
        self.plugin.on_load()
        self.plugin._weights_calc_count = 10
        self.plugin._score_calc_count = 5
        self.plugin._decision_count = 3
        self.plugin._recommend_count = 2

        stats = self.plugin.get_statistics()
        assert stats["weights_calc_count"] == 10
        assert stats["score_calc_count"] == 5
        assert stats["decision_count"] == 3
        assert stats["recommend_count"] == 2
        assert stats["filter_loaded"] is True
