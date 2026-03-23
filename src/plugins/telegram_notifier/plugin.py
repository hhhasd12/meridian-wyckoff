"""Telegram 告警通知插件 — 订阅关键事件并发送 Telegram 消息

工作流程：
  开仓事件 → position.opened → 格式化并发送开仓通知
  平仓事件 → position.closed → 格式化并发送平仓通知（含PnL）
  熔断事件 → risk_management.circuit_breaker_tripped → 紧急告警
  关机事件 → system.shutdown → 发送关机通知

设计原则：
  1. 无 token/chat_id 时 graceful 降级（WARNING 日志）
  2. 使用 urllib.request，不引入额外依赖
  3. 发送失败时记录 ERROR 日志，不崩溃
"""

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any, Dict, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifierPlugin(BasePlugin):
    """Telegram 告警通知插件

    从环境变量读取 Bot Token 和 Chat ID，
    订阅关键交易事件并通过 Telegram Bot API 发送通知。
    """

    def __init__(self, name: str = "telegram_notifier") -> None:
        super().__init__(name=name)
        self._bot_token: str = ""
        self._chat_id: str = ""
        self._enabled: bool = False
        self._send_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件 — 读取环境变量并订阅事件"""
        self._bot_token = os.environ.get(
            "WYCKOFF_TELEGRAM_BOT_TOKEN", ""
        ) or self._config.get("bot_token", "")
        self._chat_id = os.environ.get(
            "WYCKOFF_TELEGRAM_CHAT_ID", ""
        ) or self._config.get("chat_id", "")

        if not self._bot_token or not self._chat_id:
            logger.warning(
                "Telegram 通知已禁用: 未设置 "
                "WYCKOFF_TELEGRAM_BOT_TOKEN 或 "
                "WYCKOFF_TELEGRAM_CHAT_ID"
            )
            self._enabled = False
            return

        self._enabled = True
        self._subscribe_events()
        logger.info("Telegram 通知插件已启用")

    def _subscribe_events(self) -> None:
        """订阅关键交易事件"""
        self.subscribe_event("position.opened", self._on_position_opened)
        self.subscribe_event("position.closed", self._on_position_closed)
        self.subscribe_event(
            "risk_management.circuit_breaker_tripped",
            self._on_circuit_breaker,
        )
        self.subscribe_event("system.shutdown", self._on_shutdown)

    def on_unload(self) -> None:
        """卸载插件"""
        self._enabled = False
        self._bot_token = ""
        self._chat_id = ""

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        if not self._enabled:
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="Telegram 通知已禁用",
                details={"enabled": False},
            )
        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=(f"Telegram 发送有错误: {self._last_error}"),
                details={
                    "enabled": True,
                    "send_count": self._send_count,
                    "last_error": self._last_error,
                },
            )
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="Telegram 通知正常运行",
            details={
                "enabled": True,
                "send_count": self._send_count,
            },
        )

    # ============================================================
    # Telegram API 发送
    # ============================================================

    def _send_message(self, text: str) -> bool:
        """通过 Telegram Bot API 发送消息

        Args:
            text: 消息文本（支持 HTML 格式）

        Returns:
            发送是否成功
        """
        if not self._enabled:
            return False

        url = TELEGRAM_API_URL.format(token=self._bot_token)
        payload = json.dumps(
            {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
            self._send_count += 1
            self._last_error = None
            return True
        except (urllib.error.URLError, OSError) as e:
            self._last_error = str(e)
            logger.error("Telegram 发送失败: %s", e)
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.error("Telegram 发送异常: %s", e)
            return False

    # ============================================================
    # 事件处理器
    # ============================================================

    def _on_position_opened(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理开仓事件"""
        symbol = data.get("symbol", "N/A")
        side = data.get("side", "N/A")
        size = data.get("size", 0)
        price = data.get("price", 0)
        leverage = data.get("leverage", 1)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        text = (
            f"📈 <b>开仓通知</b>\n"
            f"时间: {ts}\n"
            f"品种: <b>{symbol}</b>\n"
            f"方向: {side}\n"
            f"数量: {size}\n"
            f"价格: {price}\n"
            f"杠杆: {leverage}x"
        )
        self._send_message(text)

    def _on_position_closed(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理平仓事件"""
        symbol = data.get("symbol", "N/A")
        pnl = data.get("pnl", 0)
        pnl_pct = data.get("pnl_pct", 0)
        emoji = "🟢" if pnl >= 0 else "🔴"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        text = (
            f"{emoji} <b>平仓通知</b>\n"
            f"时间: {ts}\n"
            f"品种: <b>{symbol}</b>\n"
            f"盈亏: {pnl:+.4f}\n"
            f"盈亏率: {pnl_pct:+.2f}%"
        )
        self._send_message(text)

    def _on_circuit_breaker(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理熔断事件"""
        reason = data.get("reason", "未知原因")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        text = f"🚨 <b>熔断告警</b>\n时间: {ts}\n原因: {reason}\n状态: 交易已暂停"
        self._send_message(text)

    def _on_shutdown(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理系统关闭事件"""
        reason = data.get("reason", "正常关闭")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        text = f"⚙️ <b>系统关闭</b>\n时间: {ts}\n原因: {reason}"
        self._send_message(text)
