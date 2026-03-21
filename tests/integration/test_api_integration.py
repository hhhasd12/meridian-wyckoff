"""API 集成测试 — 用真实 WyckoffApp（非 mock）测试全部端点

测试 4 个端点:
- GET /api/candles/{symbol}/{tf}
- GET /api/system/snapshot
- POST /api/config
- WS /ws/realtime
"""

import pathlib
import time
from typing import Any, Dict, List

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.app import app, app_state
from src.app import WyckoffApp
from src.kernel.types import PluginState


@pytest.fixture(scope="module")
def real_app():
    """模块级真实 WyckoffApp（非 mock）"""
    # 备份旧 journal
    old_journal = pathlib.Path("./data/position_journal.jsonl")
    old_journal_bak = pathlib.Path("./data/position_journal.jsonl.bak.api")
    if old_journal.exists():
        old_journal.rename(old_journal_bak)

    wa = WyckoffApp(config_path="config.yaml", plugins_dir="src/plugins")
    wa.discover_and_load()

    # 清理恢复的旧持仓
    pm = wa.plugin_manager.get_plugin("position_manager")
    if pm is not None and hasattr(pm, "_manager") and pm._manager is not None:
        pm._manager.positions.clear()

    # 注入数据到 data_pipeline 的缓存（模拟已获取数据）
    dp = wa.plugin_manager.get_plugin("data_pipeline")
    if dp is not None and hasattr(dp, "_cache"):
        from tests.fixtures.ohlcv_generator import make_ohlcv

        df = make_ohlcv(n=100, start_price=50000.0, trend="up")
        dp._cache[("BTC/USDT", "H4")] = df

    yield wa

    wa.plugin_manager.unload_all()
    if old_journal_bak.exists():
        if old_journal.exists():
            old_journal.unlink()
        old_journal_bak.rename(old_journal)


@pytest.fixture(scope="module")
def client(real_app):
    """TestClient 使用真实 WyckoffApp"""
    original_app_ref = app_state.wyckoff_app
    original_time = app_state.start_time

    app_state.wyckoff_app = real_app
    app_state.start_time = time.time() - 60.0

    tc = TestClient(app, raise_server_exceptions=False)
    yield tc

    app_state.wyckoff_app = original_app_ref
    app_state.start_time = original_time


# ================================================================
# REST 端点测试
# ================================================================


class TestRESTEndpoints:
    """真实后端 REST 端点测试"""

    def test_candles_returns_data(self, client, real_app) -> None:
        """GET /api/candles/BTC-USDT/H4 返回 K 线数据"""
        resp = client.get("/api/candles/BTC-USDT/H4")
        assert resp.status_code == 200
        data = resp.json()
        # 如果 data_pipeline 有缓存数据则返回数据
        assert isinstance(data, list)

    def test_candles_with_limit(self, client) -> None:
        """limit 参数限制返回量"""
        resp = client.get("/api/candles/BTC-USDT/H4?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    def test_snapshot_has_all_fields(self, client) -> None:
        """系统快照包含完整字段"""
        resp = client.get("/api/system/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert "uptime" in data
        assert "is_running" in data
        assert "plugin_count" in data
        assert "plugins" in data
        assert data["plugin_count"] >= 15
        assert isinstance(data["plugins"], list)

    def test_snapshot_plugins_have_state(self, client) -> None:
        """快照中每个插件包含 name/state"""
        resp = client.get("/api/system/snapshot")
        data = resp.json()
        for plugin in data["plugins"]:
            assert "name" in plugin
            assert "state" in plugin

    def test_snapshot_uptime_positive(self, client) -> None:
        """uptime 为正数"""
        resp = client.get("/api/system/snapshot")
        data = resp.json()
        assert data["uptime"] >= 0

    def test_config_update_success(self, client) -> None:
        """POST /api/config 更新配置成功"""
        resp = client.post(
            "/api/config",
            json={"config": {"test_key": "test_value"}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_config_update_invalid_body(self, client) -> None:
        """无效请求体返回 422"""
        resp = client.post(
            "/api/config",
            json={"wrong_key": "val"},
        )
        assert resp.status_code == 422


# ================================================================
# WebSocket 端点测试
# ================================================================


class TestWebSocketEndpoint:
    """真实后端 WebSocket 端点测试"""

    def test_ws_ping_pong(self, client) -> None:
        """WebSocket ping/pong"""
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data

    def test_ws_subscribe_topics(self, client) -> None:
        """订阅主题后连接正常"""
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json(
                {
                    "type": "subscribe",
                    "topics": ["system_status", "candles", "wyckoff"],
                }
            )
            # 验证连接仍然正常
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_invalid_json_ignored(self, client) -> None:
        """无效 JSON 被忽略"""
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_text("not-json-at-all")
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_multiple_pings(self, client) -> None:
        """多次 ping 均正常响应"""
        with client.websocket_connect("/ws/realtime") as ws:
            for _ in range(5):
                ws.send_json({"type": "ping"})
                data = ws.receive_json()
                assert data["type"] == "pong"
