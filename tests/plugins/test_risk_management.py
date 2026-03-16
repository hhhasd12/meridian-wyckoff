"""
风险管理插件测试

测试 RiskManagementPlugin 的完整功能，包括：
- 生命周期管理（加载/卸载）
- 熔断器功能
- 异常验证功能
- 事件发布
- 健康检查
- 配置更新
- 错误处理
"""

from unittest.mock import MagicMock, patch

import pytest

from src.kernel.types import HealthStatus, PluginState
from src.plugins.risk_management.plugin import (
    RiskManagementPlugin,
)


class TestRiskManagementPluginInit:
    """测试插件初始化"""

    def test_default_name(self) -> None:
        """测试默认插件名称"""
        plugin = RiskManagementPlugin()
        assert plugin.name == "risk_management"

    def test_custom_name(self) -> None:
        """测试自定义插件名称"""
        plugin = RiskManagementPlugin(name="custom_risk")
        assert plugin.name == "custom_risk"

    def test_initial_state(self) -> None:
        """测试初始状态"""
        plugin = RiskManagementPlugin()
        assert plugin._circuit_breaker is None
        assert plugin._anomaly_validator is None
        assert plugin._quality_update_count == 0
        assert plugin._anomaly_validate_count == 0
        assert plugin._last_error is None


class TestRiskManagementPluginLifecycle:
    """测试插件生命周期"""

    def setup_method(self) -> None:
        """初始化测试"""
        self.plugin = RiskManagementPlugin()
        self.plugin._state = PluginState.LOADING

    @patch("src.plugins.risk_management.anomaly_validator.AnomalyValidator")
    @patch("src.plugins.risk_management.circuit_breaker.CircuitBreaker")
    def test_on_load_default_config(
        self, mock_cb_cls: MagicMock, mock_av_cls: MagicMock
    ) -> None:
        """测试默认配置加载"""
        self.plugin.on_load()

        mock_cb_cls.assert_called_once_with(
            trip_threshold=0.3,
            recovery_threshold=0.8,
            min_recovery_time=60,
            max_trip_duration=300,
        )
        mock_av_cls.assert_called_once_with(
            correlation_threshold=2.0,
            price_deviation_threshold=0.02,
            min_confidence=0.7,
        )
        assert self.plugin._circuit_breaker is not None
        assert self.plugin._anomaly_validator is not None

    @patch("src.plugins.risk_management.anomaly_validator.AnomalyValidator")
    @patch("src.plugins.risk_management.circuit_breaker.CircuitBreaker")
    def test_on_load_custom_config(
        self, mock_cb_cls: MagicMock, mock_av_cls: MagicMock
    ) -> None:
        """测试自定义配置加载"""
        self.plugin._config = {
            "circuit_breaker": {
                "trip_threshold": 0.5,
                "recovery_threshold": 0.9,
                "min_recovery_time": 120,
                "max_trip_duration": 600,
            },
            "anomaly_validator": {
                "correlation_threshold": 3.0,
                "price_deviation_threshold": 0.05,
                "min_confidence": 0.8,
            },
        }
        self.plugin.on_load()

        mock_cb_cls.assert_called_once_with(
            trip_threshold=0.5,
            recovery_threshold=0.9,
            min_recovery_time=120,
            max_trip_duration=600,
        )
        mock_av_cls.assert_called_once_with(
            correlation_threshold=3.0,
            price_deviation_threshold=0.05,
            min_confidence=0.8,
        )

    @patch("src.plugins.risk_management.anomaly_validator.AnomalyValidator")
    @patch("src.plugins.risk_management.circuit_breaker.CircuitBreaker")
    def test_on_unload(
        self, mock_cb_cls: MagicMock, mock_av_cls: MagicMock
    ) -> None:
        """测试卸载清理"""
        self.plugin.on_load()
        self.plugin._quality_update_count = 10
        self.plugin._anomaly_validate_count = 5
        self.plugin._last_error = "some error"

        self.plugin.on_unload()

        assert self.plugin._circuit_breaker is None
        assert self.plugin._anomaly_validator is None
        assert self.plugin._quality_update_count == 0
        assert self.plugin._anomaly_validate_count == 0
        assert self.plugin._last_error is None


class TestRiskManagementPluginConfigUpdate:
    """测试配置更新"""

    def setup_method(self) -> None:
        """初始化测试"""
        self.plugin = RiskManagementPlugin()
        self.plugin._state = PluginState.ACTIVE

    def test_config_update_before_load(self) -> None:
        """测试加载前配置更新（应忽略）"""
        self.plugin.on_config_update({"circuit_breaker": {}})
        assert self.plugin._circuit_breaker is None

    @patch("src.plugins.risk_management.anomaly_validator.AnomalyValidator")
    @patch("src.plugins.risk_management.circuit_breaker.CircuitBreaker")
    def test_config_update_after_load(
        self, mock_cb_cls: MagicMock, mock_av_cls: MagicMock
    ) -> None:
        """测试加载后配置更新"""
        self.plugin._state = PluginState.LOADING
        self.plugin.on_load()

        mock_cb_cls.reset_mock()
        mock_av_cls.reset_mock()

        new_config = {
            "circuit_breaker": {
                "trip_threshold": 0.6,
                "recovery_threshold": 0.95,
            },
            "anomaly_validator": {
                "correlation_threshold": 4.0,
            },
        }
        self.plugin.on_config_update(new_config)

        mock_cb_cls.assert_called_once_with(
            trip_threshold=0.6,
            recovery_threshold=0.95,
            min_recovery_time=60,
            max_trip_duration=300,
        )
        mock_av_cls.assert_called_once_with(
            correlation_threshold=4.0,
            price_deviation_threshold=0.02,
            min_confidence=0.7,
        )


class TestRiskManagementPluginHealthCheck:
    """测试健康检查"""

    def setup_method(self) -> None:
        """初始化测试"""
        self.plugin = RiskManagementPlugin()

    def test_health_check_not_active(self) -> None:
        """测试非活跃状态的健康检查"""
        self.plugin._state = PluginState.UNLOADED
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "未处于活跃状态" in result.message

    def test_health_check_no_circuit_breaker(self) -> None:
        """测试熔断器未初始化"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._circuit_breaker = None
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "熔断器未初始化" in result.message

    def test_health_check_no_anomaly_validator(self) -> None:
        """测试异常验证器未初始化"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._circuit_breaker = MagicMock()
        self.plugin._anomaly_validator = None
        result = self.plugin.health_check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "异常验证器未初始化" in result.message

    def test_health_check_with_error(self) -> None:
        """测试有错误时的健康检查"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._circuit_breaker = MagicMock()
        self.plugin._anomaly_validator = MagicMock()
        self.plugin._last_error = "test error"
        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "最近有错误" in result.message

    def test_health_check_healthy(self) -> None:
        """测试正常健康检查"""
        self.plugin._state = PluginState.ACTIVE
        self.plugin._circuit_breaker = MagicMock()
        self.plugin._anomaly_validator = MagicMock()
        self.plugin._quality_update_count = 5
        self.plugin._anomaly_validate_count = 3
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert "5次" in result.message
        assert "3次" in result.message


class TestCircuitBreakerFunctions:
    """测试熔断器功能"""

    def setup_method(self) -> None:
        """初始化测试"""
        self.plugin = RiskManagementPlugin()
        self.plugin._state = PluginState.ACTIVE
        self.mock_cb = MagicMock()
        self.plugin._circuit_breaker = self.mock_cb
        self.plugin._anomaly_validator = MagicMock()
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_update_data_quality_no_trip(self) -> None:
        """测试数据质量更新（未触发熔断）"""
        self.mock_cb.update_data_quality.return_value = False
        self.mock_cb.status.value = "NORMAL"
        metrics = MagicMock()

        result = self.plugin.update_data_quality(metrics)

        assert result is False
        assert self.plugin._quality_update_count == 1
        self.plugin.emit_event.assert_called_once_with(
            "risk_management.data_quality_updated",
            {"tripped": False, "status": "NORMAL"},
        )

    def test_update_data_quality_tripped(self) -> None:
        """测试数据质量更新（触发熔断）"""
        self.mock_cb.update_data_quality.return_value = True
        self.mock_cb.status.value = "TRIPPED"
        metrics = MagicMock()

        result = self.plugin.update_data_quality(metrics)

        assert result is True
        assert self.plugin._quality_update_count == 1
        self.plugin.emit_event.assert_called_once_with(
            "risk_management.circuit_breaker_tripped",
            {"tripped": True, "status": "TRIPPED"},
        )

    def test_update_data_quality_not_loaded(self) -> None:
        """测试未加载时更新数据质量"""
        self.plugin._circuit_breaker = None
        with pytest.raises(
            RuntimeError, match="未加载.*数据质量"
        ):
            self.plugin.update_data_quality(MagicMock())

    def test_update_data_quality_error(self) -> None:
        """测试数据质量更新异常"""
        self.mock_cb.update_data_quality.side_effect = (
            ValueError("bad metrics")
        )
        metrics = MagicMock()

        with pytest.raises(ValueError, match="bad metrics"):
            self.plugin.update_data_quality(metrics)

        assert self.plugin._last_error == "bad metrics"

    def test_is_trading_allowed(self) -> None:
        """测试交易权限检查"""
        self.mock_cb.is_trading_allowed.return_value = True
        assert self.plugin.is_trading_allowed() is True

    def test_is_trading_not_allowed(self) -> None:
        """测试交易被禁止"""
        self.mock_cb.is_trading_allowed.return_value = False
        assert self.plugin.is_trading_allowed() is False

    def test_is_trading_allowed_not_loaded(self) -> None:
        """测试未加载时检查交易权限"""
        self.plugin._circuit_breaker = None
        with pytest.raises(
            RuntimeError, match="未加载.*交易权限"
        ):
            self.plugin.is_trading_allowed()

    def test_get_status_report(self) -> None:
        """测试获取状态报告"""
        expected = {"status": "NORMAL", "trips": 0}
        self.mock_cb.get_status_report.return_value = expected
        result = self.plugin.get_status_report()
        assert result == expected

    def test_get_status_report_not_loaded(self) -> None:
        """测试未加载时获取状态报告"""
        self.plugin._circuit_breaker = None
        with pytest.raises(
            RuntimeError, match="未加载.*状态报告"
        ):
            self.plugin.get_status_report()


class TestAnomalyValidatorFunctions:
    """测试异常验证功能"""

    def setup_method(self) -> None:
        """初始化测试"""
        self.plugin = RiskManagementPlugin()
        self.plugin._state = PluginState.ACTIVE
        self.mock_av = MagicMock()
        self.plugin._circuit_breaker = MagicMock()
        self.plugin._anomaly_validator = self.mock_av
        self.plugin.emit_event = MagicMock(return_value=1)

    def test_validate_anomaly_success(self) -> None:
        """测试异常验证成功"""
        anomaly = MagicMock()
        anomaly.anomaly_id = "test_001"
        result_event = MagicMock()
        result_event.validation_result = "CONFIRMED"
        self.mock_av.validate_anomaly.return_value = (
            result_event
        )

        result = self.plugin.validate_anomaly(anomaly)

        assert result == result_event
        assert self.plugin._anomaly_validate_count == 1
        assert self.plugin._last_error is None
        self.plugin.emit_event.assert_called_once_with(
            "risk_management.anomaly_validated",
            {
                "anomaly_id": "test_001",
                "validation_result": "CONFIRMED",
            },
        )

    def test_validate_anomaly_with_exchange_data(
        self,
    ) -> None:
        """测试带多交易所数据的异常验证"""
        anomaly = MagicMock()
        anomaly.anomaly_id = "test_002"
        exchange_data = {"binance": MagicMock()}
        correlation = {"btc_eth": 0.95}
        result_event = MagicMock()
        result_event.validation_result = "REJECTED"
        self.mock_av.validate_anomaly.return_value = (
            result_event
        )

        result = self.plugin.validate_anomaly(
            anomaly, exchange_data, correlation
        )

        self.mock_av.validate_anomaly.assert_called_once_with(
            anomaly, exchange_data, correlation
        )
        assert result == result_event

    def test_validate_anomaly_not_loaded(self) -> None:
        """测试未加载时验证异常"""
        self.plugin._anomaly_validator = None
        with pytest.raises(
            RuntimeError, match="未加载.*验证异常"
        ):
            self.plugin.validate_anomaly(MagicMock())

    def test_validate_anomaly_error(self) -> None:
        """测试异常验证失败"""
        self.mock_av.validate_anomaly.side_effect = (
            ValueError("invalid anomaly")
        )
        anomaly = MagicMock()

        with pytest.raises(
            ValueError, match="invalid anomaly"
        ):
            self.plugin.validate_anomaly(anomaly)

        assert (
            self.plugin._last_error == "invalid anomaly"
        )

    def test_validate_anomaly_without_id(self) -> None:
        """测试验证没有anomaly_id的异常"""
        anomaly = MagicMock(spec=[])
        result_event = MagicMock()
        result_event.validation_result = "UNKNOWN"
        self.mock_av.validate_anomaly.return_value = (
            result_event
        )

        self.plugin.validate_anomaly(anomaly)

        call_args = self.plugin.emit_event.call_args
        assert call_args[0][1]["anomaly_id"] == "unknown"


class TestRiskManagementStatistics:
    """测试统计信息"""

    def setup_method(self) -> None:
        """初始化测试"""
        self.plugin = RiskManagementPlugin()

    def test_statistics_not_loaded(self) -> None:
        """测试未加载时的统计信息"""
        stats = self.plugin.get_statistics()
        assert stats["quality_update_count"] == 0
        assert stats["anomaly_validate_count"] == 0
        assert stats["last_error"] is None
        assert stats["trading_allowed"] is None
        assert stats["breaker_status"] is None

    def test_statistics_loaded(self) -> None:
        """测试加载后的统计信息"""
        mock_cb = MagicMock()
        mock_cb.is_trading_allowed.return_value = True
        mock_cb.status.value = "NORMAL"
        self.plugin._circuit_breaker = mock_cb
        self.plugin._quality_update_count = 10
        self.plugin._anomaly_validate_count = 5
        self.plugin._last_error = "test error"

        stats = self.plugin.get_statistics()
        assert stats["quality_update_count"] == 10
        assert stats["anomaly_validate_count"] == 5
        assert stats["last_error"] == "test error"
        assert stats["trading_allowed"] is True
        assert stats["breaker_status"] == "NORMAL"

    def test_counter_increments(self) -> None:
        """测试计数器递增"""
        mock_cb = MagicMock()
        mock_cb.update_data_quality.return_value = False
        mock_cb.status.value = "NORMAL"
        self.plugin._circuit_breaker = mock_cb

        mock_av = MagicMock()
        result_event = MagicMock()
        result_event.validation_result = "CONFIRMED"
        mock_av.validate_anomaly.return_value = (
            result_event
        )
        self.plugin._anomaly_validator = mock_av
        self.plugin.emit_event = MagicMock(return_value=1)

        self.plugin.update_data_quality(MagicMock())
        self.plugin.update_data_quality(MagicMock())
        self.plugin.update_data_quality(MagicMock())
        assert self.plugin._quality_update_count == 3

        anomaly = MagicMock()
        anomaly.anomaly_id = "test"
        self.plugin.validate_anomaly(anomaly)
        self.plugin.validate_anomaly(anomaly)
        assert self.plugin._anomaly_validate_count == 2


class TestRiskManagementPluginImport:
    """测试插件导入"""

    def test_import_from_package(self) -> None:
        """测试从包导入"""
        from src.plugins.risk_management import (
            RiskManagementPlugin,
        )

        plugin = RiskManagementPlugin()
        assert plugin.name == "risk_management"

    def test_import_from_module(self) -> None:
        """测试从模块导入"""
        from src.plugins.risk_management.plugin import (
            RiskManagementPlugin,
        )

        plugin = RiskManagementPlugin()
        assert plugin.name == "risk_management"
