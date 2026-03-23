"""Telegram 告警通知插件 — 单元测试

测试覆盖：
  - 插件初始化与 graceful 降级
  - 环境变量读取
  - 事件订阅
  - 消息格式化与发送（mock urllib）
  - 发送失败时的错误处理
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.plugins.telegram_notifier.plugin import (
    TELEGRAM_API_URL,
    TelegramNotifierPlugin,
)
from src.kernel.types import HealthStatus


class TestTelegramNotifierInit:
    """测试插件初始化"""

    def setup_method(self) -> None:
        self.plugin = TelegramNotifierPlugin()

    def test_default_state(self) -> None:
        """默认状态应该是禁用"""
        assert self.plugin._enabled is False
        assert self.plugin._bot_token == ""
        assert self.plugin._chat_id == ""
        assert self.plugin._send_count == 0
        assert self.plugin._last_error is None

    def test_name(self) -> None:
        """插件名应为 telegram_notifier"""
        assert self.plugin.name == "telegram_notifier"

    @patch.dict(
        "os.environ",
        {
            "WYCKOFF_TELEGRAM_BOT_TOKEN": "test_token",
            "WYCKOFF_TELEGRAM_CHAT_ID": "12345",
        },
    )
    def test_load_with_env_vars(self) -> None:
        """设置环境变量后应启用"""
        plugin = TelegramNotifierPlugin()
        plugin._event_bus = MagicMock()
        plugin.on_load()
        assert plugin._enabled is True
        assert plugin._bot_token == "test_token"
        assert plugin._chat_id == "12345"

    @patch.dict("os.environ", {}, clear=True)
    def test_load_without_env_vars(self) -> None:
        """无环境变量时应 graceful 降级"""
        plugin = TelegramNotifierPlugin()
        plugin.on_load()
        assert plugin._enabled is False

    @patch.dict("os.environ", {}, clear=True)
    def test_load_with_config(self) -> None:
        """可从 config 读取 token/chat_id"""
        plugin = TelegramNotifierPlugin()
        plugin._config = {
            "bot_token": "cfg_token",
            "chat_id": "67890",
        }
        plugin._event_bus = MagicMock()
        plugin.on_load()
        assert plugin._enabled is True
        assert plugin._bot_token == "cfg_token"
        assert plugin._chat_id == "67890"

    def test_unload(self) -> None:
        """卸载应清除状态"""
        self.plugin._enabled = True
        self.plugin._bot_token = "tok"
        self.plugin._chat_id = "cid"
        self.plugin.on_unload()
        assert self.plugin._enabled is False
        assert self.plugin._bot_token == ""
        assert self.plugin._chat_id == ""


class TestTelegramNotifierSend:
    """测试消息发送"""

    def setup_method(self) -> None:
        self.plugin = TelegramNotifierPlugin()
        self.plugin._bot_token = "test_token"
        self.plugin._chat_id = "12345"
        self.plugin._enabled = True

    def test_send_disabled(self) -> None:
        """禁用时不发送"""
        self.plugin._enabled = False
        result = self.plugin._send_message("test")
        assert result is False
        assert self.plugin._send_count == 0

    @patch("urllib.request.urlopen")
    def test_send_success(self, mock_urlopen: MagicMock) -> None:
        """成功发送消息"""
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = self.plugin._send_message("hello")
        assert result is True
        assert self.plugin._send_count == 1
        assert self.plugin._last_error is None

        # 验证调用参数
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "test_token" in req.full_url
        body = json.loads(req.data.decode("utf-8"))
        assert body["chat_id"] == "12345"
        assert body["text"] == "hello"
        assert body["parse_mode"] == "HTML"

    @patch(
        "urllib.request.urlopen",
        side_effect=Exception("network error"),
    )
    def test_send_failure(self, mock_urlopen: MagicMock) -> None:
        """发送失败不崩溃"""
        result = self.plugin._send_message("hello")
        assert result is False
        assert self.plugin._send_count == 0
        assert self.plugin._last_error == "network error"


class TestTelegramNotifierEvents:
    """测试事件处理器"""

    def setup_method(self) -> None:
        self.plugin = TelegramNotifierPlugin()
        self.plugin._bot_token = "test_token"
        self.plugin._chat_id = "12345"
        self.plugin._enabled = True

    @patch.object(TelegramNotifierPlugin, "_send_message")
    def test_on_position_opened(self, mock_send: MagicMock) -> None:
        """开仓事件应格式化并发送"""
        mock_send.return_value = True
        data = {
            "symbol": "BTC/USDT",
            "side": "LONG",
            "size": 0.1,
            "price": 65000.0,
            "leverage": 10,
        }
        self.plugin._on_position_opened("position.opened", data)
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "开仓通知" in msg
        assert "BTC/USDT" in msg
        assert "LONG" in msg
        assert "65000" in msg
        assert "10x" in msg

    @patch.object(TelegramNotifierPlugin, "_send_message")
    def test_on_position_closed_profit(self, mock_send: MagicMock) -> None:
        """盈利平仓事件"""
        mock_send.return_value = True
        data = {
            "symbol": "ETH/USDT",
            "pnl": 150.5,
            "pnl_pct": 3.25,
        }
        self.plugin._on_position_closed("position.closed", data)
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "平仓通知" in msg
        assert "ETH/USDT" in msg
        assert "+150.5" in msg
        assert "+3.25%" in msg
        assert "🟢" in msg

    @patch.object(TelegramNotifierPlugin, "_send_message")
    def test_on_position_closed_loss(self, mock_send: MagicMock) -> None:
        """亏损平仓事件"""
        mock_send.return_value = True
        data = {
            "symbol": "BTC/USDT",
            "pnl": -80.0,
            "pnl_pct": -2.5,
        }
        self.plugin._on_position_closed("position.closed", data)
        msg = mock_send.call_args[0][0]
        assert "🔴" in msg
        assert "-80.0" in msg

    @patch.object(TelegramNotifierPlugin, "_send_message")
    def test_on_circuit_breaker(self, mock_send: MagicMock) -> None:
        """熔断事件应格式化并发送"""
        mock_send.return_value = True
        data = {"reason": "连续亏损超过阈值"}
        self.plugin._on_circuit_breaker(
            "risk_management.circuit_breaker_tripped",
            data,
        )
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "熔断告警" in msg
        assert "连续亏损超过阈值" in msg
        assert "交易已暂停" in msg

    @patch.object(TelegramNotifierPlugin, "_send_message")
    def test_on_shutdown(self, mock_send: MagicMock) -> None:
        """系统关闭事件"""
        mock_send.return_value = True
        data = {"reason": "用户手动停止"}
        self.plugin._on_shutdown("system.shutdown", data)
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "系统关闭" in msg
        assert "用户手动停止" in msg

    @patch.object(TelegramNotifierPlugin, "_send_message")
    def test_event_with_missing_fields(self, mock_send: MagicMock) -> None:
        """事件数据缺失时使用默认值"""
        mock_send.return_value = True
        self.plugin._on_position_opened("position.opened", {})
        msg = mock_send.call_args[0][0]
        assert "N/A" in msg


class TestTelegramNotifierHealthCheck:
    """测试健康检查"""

    def setup_method(self) -> None:
        self.plugin = TelegramNotifierPlugin()

    def test_health_disabled(self) -> None:
        """禁用时应返回 HEALTHY"""
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert result.details["enabled"] is False

    def test_health_enabled_ok(self) -> None:
        """启用且无错误"""
        self.plugin._enabled = True
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert result.details["enabled"] is True

    def test_health_with_error(self) -> None:
        """有发送错误时应返回 DEGRADED"""
        self.plugin._enabled = True
        self.plugin._last_error = "timeout"
        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED
        assert "timeout" in result.message


class TestTelegramNotifierEventSubscription:
    """测试事件订阅"""

    @patch.dict(
        "os.environ",
        {
            "WYCKOFF_TELEGRAM_BOT_TOKEN": "tok",
            "WYCKOFF_TELEGRAM_CHAT_ID": "cid",
        },
    )
    def test_subscribes_all_events(self) -> None:
        """启用后应订阅4个事件"""
        plugin = TelegramNotifierPlugin()
        mock_bus = MagicMock()
        plugin._event_bus = mock_bus
        plugin.on_load()

        assert mock_bus.subscribe.call_count == 4
        event_names = [c[0][0] for c in mock_bus.subscribe.call_args_list]
        assert "position.opened" in event_names
        assert "position.closed" in event_names
        assert "risk_management.circuit_breaker_tripped" in event_names
        assert "system.shutdown" in event_names
