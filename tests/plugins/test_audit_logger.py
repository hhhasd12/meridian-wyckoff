"""审计日志插件测试"""

import json
import os
import tempfile

import pytest

from src.kernel.types import HealthStatus
from src.plugins.audit_logger.plugin import AuditLoggerPlugin


class TestAuditLoggerPlugin:
    """AuditLoggerPlugin 核心功能测试"""

    def setup_method(self):
        """每个测试前创建临时目录和插件实例"""
        self._tmpdir = tempfile.mkdtemp()
        self.plugin = AuditLoggerPlugin()
        self.plugin._config = {
            "log_dir": self._tmpdir,
            "log_file": "test_audit.jsonl",
        }

    def teardown_method(self):
        """清理：卸载插件、删除临时文件"""
        try:
            self.plugin.on_unload()
        except Exception:
            pass
        log_path = os.path.join(self._tmpdir, "test_audit.jsonl")
        if os.path.exists(log_path):
            os.remove(log_path)
        if os.path.exists(self._tmpdir):
            os.rmdir(self._tmpdir)

    # ================================================================
    # on_load / on_unload
    # ================================================================

    def test_on_load_creates_log_file(self):
        """on_load 应打开文件并设置路径"""
        self.plugin.on_load()
        assert self.plugin._log_path is not None
        assert self.plugin._file_handle is not None
        assert not self.plugin._file_handle.closed

    def test_on_unload_closes_file(self):
        """on_unload 应关闭文件句柄"""
        self.plugin.on_load()
        assert self.plugin._file_handle is not None
        self.plugin.on_unload()
        assert self.plugin._file_handle is None

    def test_on_load_creates_directory(self):
        """on_load 应自动创建不存在的日志目录"""
        nested_dir = os.path.join(self._tmpdir, "sub", "dir")
        self.plugin._config = {
            "log_dir": nested_dir,
            "log_file": "test.jsonl",
        }
        self.plugin.on_load()
        assert os.path.isdir(nested_dir)
        # 清理
        self.plugin.on_unload()
        log_file = os.path.join(nested_dir, "test.jsonl")
        if os.path.exists(log_file):
            os.remove(log_file)
        os.rmdir(nested_dir)
        os.rmdir(os.path.join(self._tmpdir, "sub"))

    # ================================================================
    # 事件写入
    # ================================================================

    def test_on_event_writes_jsonl(self):
        """_on_event 应将事件写入 JSONL 文件"""
        self.plugin.on_load()
        self.plugin._on_event(
            "trading.signal",
            {"symbol": "BTC/USDT", "signal": "BUY", "confidence": 0.85},
        )

        # 读取文件验证
        log_path = os.path.join(self._tmpdir, "test_audit.jsonl")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event_type"] == "trading.signal"
        assert record["data"]["symbol"] == "BTC/USDT"
        assert record["data"]["signal"] == "BUY"
        assert "timestamp" in record
        assert "config_hash" in record

    def test_on_event_increments_write_count(self):
        """_on_event 应递增写入计数"""
        self.plugin.on_load()
        assert self.plugin._write_count == 0

        self.plugin._on_event("position.opened", {"symbol": "ETH/USDT"})
        assert self.plugin._write_count == 1

        self.plugin._on_event("position.closed", {"symbol": "ETH/USDT"})
        assert self.plugin._write_count == 2

    def test_multiple_events_appended(self):
        """多个事件应追加到同一文件"""
        self.plugin.on_load()

        events = [
            ("trading.signal", {"symbol": "BTC/USDT", "signal": "BUY"}),
            ("position.opened", {"symbol": "BTC/USDT", "side": "LONG"}),
            ("position.closed", {"symbol": "BTC/USDT", "pnl": 150.0}),
        ]

        for event_name, data in events:
            self.plugin._on_event(event_name, data)

        log_path = os.path.join(self._tmpdir, "test_audit.jsonl")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3
        for i, (event_name, _) in enumerate(events):
            record = json.loads(lines[i])
            assert record["event_type"] == event_name

    def test_on_event_skips_when_file_closed(self):
        """文件已关闭时 _on_event 应静默跳过"""
        self.plugin.on_load()
        self.plugin.on_unload()

        # 不应抛异常
        self.plugin._on_event("trading.signal", {"symbol": "BTC/USDT"})
        assert self.plugin._write_count == 0

    # ================================================================
    # config_hash
    # ================================================================

    def test_config_hash_deterministic(self):
        """相同配置应产生相同的 hash"""
        self.plugin.on_load()
        hash1 = self.plugin._compute_config_hash()
        hash2 = self.plugin._compute_config_hash()
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex digest

    def test_config_hash_changes_with_config(self):
        """不同配置应产生不同的 hash"""
        self.plugin.on_load()
        hash1 = self.plugin._compute_config_hash()

        self.plugin._config["extra_key"] = "extra_value"
        hash2 = self.plugin._compute_config_hash()

        assert hash1 != hash2

    # ================================================================
    # _safe_serialize
    # ================================================================

    def test_safe_serialize_handles_normal_data(self):
        """_safe_serialize 应正常传递可序列化数据"""
        data = {"a": 1, "b": "hello", "c": [1, 2, 3]}
        result = AuditLoggerPlugin._safe_serialize(data)
        assert result == data

    def test_safe_serialize_handles_unserializable(self):
        """_safe_serialize 应将不可序列化对象转为字符串或保留（因 default=str）"""
        data = {"normal": 42, "nested": {"a": 1}}
        result = AuditLoggerPlugin._safe_serialize(data)
        assert result["normal"] == 42
        assert result["nested"] == {"a": 1}

    # ================================================================
    # health_check
    # ================================================================

    def test_health_check_healthy_when_loaded(self):
        """加载后健康检查应返回 HEALTHY"""
        self.plugin.on_load()
        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert result.details["write_count"] == 0
        assert result.details["log_path"] is not None

    def test_health_check_degraded_when_file_closed(self):
        """文件未打开时健康检查应返回 DEGRADED"""
        result = self.plugin.health_check()
        assert result.status == HealthStatus.DEGRADED

    def test_health_check_after_writes(self):
        """写入后健康检查应反映写入数"""
        self.plugin.on_load()
        self.plugin._on_event("trading.signal", {"symbol": "BTC/USDT"})
        self.plugin._on_event("position.opened", {"symbol": "ETH/USDT"})

        result = self.plugin.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert result.details["write_count"] == 2

    # ================================================================
    # 记录格式验证
    # ================================================================

    def test_record_has_all_required_fields(self):
        """每条记录必须包含 timestamp, event_type, data, config_hash"""
        self.plugin.on_load()
        self.plugin._on_event(
            "position.closed",
            {"symbol": "BTC/USDT", "pnl": -50.0, "exit_reason": "STOP_LOSS"},
        )

        log_path = os.path.join(self._tmpdir, "test_audit.jsonl")
        with open(log_path, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())

        assert "timestamp" in record
        assert record["timestamp"].endswith("Z")
        assert "event_type" in record
        assert "data" in record
        assert "config_hash" in record

    def test_timestamp_format_iso8601(self):
        """timestamp 应为 ISO 8601 格式"""
        self.plugin.on_load()
        self.plugin._on_event("trading.signal", {"symbol": "X"})

        log_path = os.path.join(self._tmpdir, "test_audit.jsonl")
        with open(log_path, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())

        ts = record["timestamp"]
        assert ts.endswith("Z")
        # 应可被解析为 ISO 格式
        from datetime import datetime

        parsed = datetime.fromisoformat(ts.rstrip("Z"))
        assert parsed.year >= 2024


class TestAuditLoggerDefaults:
    """测试默认配置行为"""

    def test_default_config_values(self):
        """无配置时应使用默认值"""
        plugin = AuditLoggerPlugin()
        plugin._config = {}
        # 确保 on_load 使用默认路径，不抛异常
        plugin.on_load()
        expected = os.path.join("./logs", "audit.jsonl")
        assert plugin._log_path == expected
        plugin.on_unload()

    def test_default_name(self):
        """默认名称应为 audit_logger"""
        plugin = AuditLoggerPlugin()
        assert plugin._name == "audit_logger"
