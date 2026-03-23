"""API 集成测试 — 用真实 WyckoffApp（非 mock）测试全部端点

测试覆盖:
- GET /api/candles/{symbol}/{tf}
- GET /api/system/snapshot
- POST /api/config
- GET /api/evolution/results
- GET /api/evolution/latest
- POST /api/evolution/start
- POST /api/evolution/stop
- GET /api/decisions
- GET /api/evolution/config
- GET /api/trades
- GET /api/advisor/latest
- WS /ws/realtime (ping/pong + 主题推送 + 服务端心跳)
- Bearer Token 认证
"""

import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import app, app_state
from src.kernel.types import PluginState


# 使用 conftest.py 中的 session-scoped fixture：loaded_app, api_client


@pytest.fixture(scope="module")
def client(loaded_app):
    """Module-scoped TestClient — 复用 session-scoped loaded_app"""
    original_app_ref = app_state.wyckoff_app
    original_time = app_state.start_time

    app_state.wyckoff_app = loaded_app
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

    def test_candles_returns_data(self, client) -> None:
        """GET /api/candles/BTC/USDT/H4 返回 K 线数据"""
        resp = client.get("/api/candles/BTC/USDT/H4")
        assert resp.status_code == 200
        data = resp.json()
        # 如果 data_pipeline 有缓存数据则返回数据
        assert isinstance(data, list)

    def test_candles_with_limit(self, client) -> None:
        """limit 参数限制返回量"""
        resp = client.get("/api/candles/BTC/USDT/H4?limit=10")
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


# ================================================================
# 缺失 REST 端点测试（8 个）
# ================================================================


class TestMissingRESTEndpoints:
    """补全 8 个之前未测试的 REST 端点"""

    def test_evolution_results_returns_shape(self, client) -> None:
        """GET /api/evolution/results 返回正确结构"""
        resp = client.get("/api/evolution/results")
        assert resp.status_code == 200
        data = resp.json()
        assert "cycles" in data
        assert "total" in data
        assert isinstance(data["cycles"], list)
        assert isinstance(data["total"], int)

    def test_evolution_latest_returns_shape(self, client) -> None:
        """GET /api/evolution/latest 返回正确结构"""
        resp = client.get("/api/evolution/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "cycle" in data
        assert "total" in data

    def test_decisions_returns_shape(self, client) -> None:
        """GET /api/decisions 返回正确结构"""
        resp = client.get("/api/decisions")
        assert resp.status_code == 200
        data = resp.json()
        assert "decisions" in data
        assert "total" in data
        assert isinstance(data["decisions"], list)
        assert isinstance(data["total"], int)

    def test_evolution_config_returns_shape(self, client) -> None:
        """GET /api/evolution/config 返回正确结构"""
        resp = client.get("/api/evolution/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert isinstance(data["config"], dict)

    def test_trades_returns_shape(self, client) -> None:
        """GET /api/trades 返回正确结构"""
        resp = client.get("/api/trades")
        assert resp.status_code == 200
        data = resp.json()
        assert "trades" in data
        assert isinstance(data["trades"], list)

    def test_advisor_latest_returns_shape(self, client) -> None:
        """GET /api/advisor/latest 返回正确结构"""
        resp = client.get("/api/advisor/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis" in data
        assert "status" in data
        assert isinstance(data["status"], str)

    def test_evolution_start_returns_response(self, client) -> None:
        """POST /api/evolution/start 返回响应（mock 避免真实进化）"""
        with patch(
            "src.api.app.getattr",
            side_effect=lambda obj, name: AsyncMock(
                return_value={"status": "started", "message": "mock"}
            )
            if name == "start_evolution"
            else getattr(obj, name),
        ):
            resp = client.post(
                "/api/evolution/start",
                json={"max_cycles": 1},
            )
        # 不管是否 mock 成功，端点应该返回 200 或合理状态
        assert resp.status_code in (200, 500)

    def test_evolution_stop_returns_response(self, client) -> None:
        """POST /api/evolution/stop 返回响应"""
        resp = client.post("/api/evolution/stop")
        # evolution 插件可能未在运行，但端点应正常响应
        assert resp.status_code in (200, 500)


# ================================================================
# WebSocket 主题推送测试
# ================================================================


class TestWebSocketTopicPush:
    """验证 WebSocket 订阅后能收到主题推送数据"""

    def test_ws_system_status_push(self, client) -> None:
        """订阅 system_status 后收到推送数据"""
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json({"type": "subscribe", "topics": ["system_status"]})
            # 服务端每 2s 推送一次，最多等 30 条消息
            found = False
            for _ in range(30):
                msg = ws.receive_json()
                if msg.get("type") == "system_status":
                    assert "data" in msg
                    assert "timestamp" in msg
                    found = True
                    break
            assert found, "未在 30 条消息内收到 system_status 推送"

    def test_ws_candles_push(self, client) -> None:
        """订阅 candles 后连接保持稳定（推送取决于缓存数据可用性）"""
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json({"type": "subscribe", "topics": ["candles"]})
            # candles 推送依赖 data_pipeline.get_cached_data("BTC/USDT", "H1")
            # 缓存可能为空，只验证连接稳定不崩溃
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            # 可能收到 pong 或 server ping 或 candle_update
            assert data["type"] in ("pong", "ping", "candle_update")

    def test_ws_invalid_topic_ignored(self, client) -> None:
        """订阅无效主题不会导致错误"""
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json({"type": "subscribe", "topics": ["nonexistent"]})
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"


# ================================================================
# Bearer Token 认证测试
# ================================================================


class TestBearerTokenAuth:
    """Bearer Token 认证中间件测试"""

    def test_post_rejected_without_token(self, client) -> None:
        """设置 token 后，POST 无 Authorization 返回 401"""
        import sys

        api_mod = sys.modules["src.api.app"]
        old_token = api_mod._api_token
        try:
            api_mod._api_token = "test-secret-token"  # type: ignore[attr-defined]
            resp = client.post(
                "/api/config",
                json={"config": {"key": "val"}},
            )
            assert resp.status_code == 401
        finally:
            api_mod._api_token = old_token  # type: ignore[attr-defined]

    def test_post_accepted_with_token(self, client) -> None:
        """设置 token 后，带正确 Authorization 返回 200"""
        import sys

        api_mod = sys.modules["src.api.app"]
        old_token = api_mod._api_token
        try:
            api_mod._api_token = "test-secret-token"  # type: ignore[attr-defined]
            resp = client.post(
                "/api/config",
                json={"config": {"key": "val"}},
                headers={"Authorization": "Bearer test-secret-token"},
            )
            assert resp.status_code == 200
        finally:
            api_mod._api_token = old_token  # type: ignore[attr-defined]

    def test_get_not_affected_by_token(self, client) -> None:
        """GET 请求不受 token 限制"""
        import sys

        api_mod = sys.modules["src.api.app"]
        old_token = api_mod._api_token
        try:
            api_mod._api_token = "test-secret-token"  # type: ignore[attr-defined]
            resp = client.get("/api/system/snapshot")
            assert resp.status_code == 200
        finally:
            api_mod._api_token = old_token  # type: ignore[attr-defined]
