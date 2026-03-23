"""审计日志插件 — 记录所有交易决策和仓位事件

将交易信号、仓位开平、熔断等关键事件写入 logs/audit.jsonl，
每条记录包含 timestamp、event_type、data、config_hash。
使用 flush+fsync 确保落盘。
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class AuditLoggerPlugin(BasePlugin):
    """审计日志插件

    订阅交易决策相关事件，将完整事件数据写入 JSONL 文件。
    每条记录包含：timestamp, event_type, data, config_hash。

    事件订阅：
    - trading.signal: 交易信号
    - position.opened: 仓位开启
    - position.closed: 仓位关闭
    - risk_management.circuit_breaker_tripped: 熔断触发
    """

    def __init__(self, name: str = "audit_logger") -> None:
        super().__init__(name=name)
        self._log_path: Optional[str] = None
        self._file_handle: Optional[Any] = None
        self._write_count: int = 0
        self._last_error: Optional[str] = None
        self._recent_logs: List[Dict[str, Any]] = []
        self._max_recent: int = 200

    def on_load(self) -> None:
        """加载插件：创建日志目录，打开文件，订阅事件"""
        config = self._config or {}
        log_dir = config.get("log_dir", "./logs")
        log_file = config.get("log_file", "audit.jsonl")

        # 确保日志目录存在
        os.makedirs(log_dir, exist_ok=True)

        self._log_path = os.path.join(log_dir, log_file)

        # 以追加模式打开文件
        try:
            self._file_handle = open(
                self._log_path,  # type: ignore[arg-type]
                "a",
                encoding="utf-8",
            )
        except OSError as e:
            self._last_error = str(e)
            logger.error("无法打开审计日志文件: %s", e)
            return

        # 订阅事件
        self.subscribe_event("trading.signal", self._on_event)
        self.subscribe_event("position.opened", self._on_event)
        self.subscribe_event("position.closed", self._on_event)
        self.subscribe_event(
            "risk_management.circuit_breaker_tripped",
            self._on_event,
        )

        logger.info(
            "审计日志插件已加载，日志路径: %s",
            self._log_path,
        )

    def on_unload(self) -> None:
        """卸载插件：关闭文件句柄"""
        if self._file_handle and not self._file_handle.closed:
            try:
                self._file_handle.flush()
                os.fsync(self._file_handle.fileno())
                self._file_handle.close()
            except OSError:
                pass
        self._file_handle = None
        logger.info(
            "审计日志插件已卸载，共写入 %d 条记录",
            self._write_count,
        )

    def _on_event(self, event_name: str, data: Dict[str, Any]) -> None:
        """统一事件处理：序列化事件并写入 JSONL

        Args:
            event_name: 事件名称
            data: 事件数据字典
        """
        if self._file_handle is None or self._file_handle.closed:
            return

        try:
            record = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "event_type": event_name,
                "data": self._safe_serialize(data),
                "config_hash": self._compute_config_hash(),
            }

            line = json.dumps(record, ensure_ascii=False, default=str)
            self._file_handle.write(line + "\n")
            self._file_handle.flush()
            os.fsync(self._file_handle.fileno())

            self._write_count += 1

            # 保存到内存环形缓冲（供 API get_recent_logs 使用）
            self._recent_logs.append(record)
            if len(self._recent_logs) > self._max_recent:
                self._recent_logs = self._recent_logs[-self._max_recent :]

        except Exception as e:
            self._last_error = str(e)
            logger.error("审计日志写入失败: %s", e)

    def _compute_config_hash(self) -> str:
        """计算当前配置的 MD5 哈希

        Returns:
            配置的 MD5 十六进制摘要
        """
        config_str = json.dumps(self._config, sort_keys=True, default=str)
        return hashlib.md5(config_str.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_serialize(
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """安全序列化事件数据，过滤不可序列化对象

        Args:
            data: 原始事件数据

        Returns:
            可 JSON 序列化的字典
        """
        result: Dict[str, Any] = {}
        for key, value in data.items():
            try:
                json.dumps(value, default=str)
                result[key] = value
            except (TypeError, ValueError):
                result[key] = str(value)
        return result

    def get_recent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的审计日志记录

        供 API WebSocket system_status 主题使用，
        为前端 LogsTab 提供实时日志数据。

        Args:
            limit: 返回记录数量上限

        Returns:
            最近的日志记录列表（时间倒序）
        """
        return self._recent_logs[-limit:]

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        if self._file_handle is None or self._file_handle.closed:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message="审计日志文件未打开",
                details={
                    "write_count": self._write_count,
                    "last_error": self._last_error,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="审计日志插件正常运行",
            details={
                "write_count": self._write_count,
                "log_path": self._log_path,
            },
        )
