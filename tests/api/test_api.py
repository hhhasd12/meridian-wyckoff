"""API 端点测试

测试 4 个 API 端点：
- GET /api/candles/{symbol}/{tf}
- GET /api/system/snapshot
- POST /api/config
- WS /ws/realtime
"""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.app import app, app_state
from src.kernel.types import PluginInfo, PluginState, PluginType


@pytest.fixture(autouse=True)
def reset_app_state():
    """每个测试前后重置 app_state"""
    original_app = app_state.wyckoff_app
    original_time = app_state.start_time
    yield
    app_state.wyckoff_app = original_app
    app_state.start_time = original_time


def _make_mock_app():
    """创建模拟的 WyckoffApp"""
    mock_app = MagicMock()
    mock_app.is_running = True
    mock_app.plugin_manager = MagicMock()
    mock_app.config_system = MagicMock()
    mock_app.config_system._global_config = {"key": "value"}
    mock_app.get_status.return_value = {
        "is_running": True,
        "plugin_count": 2,
        "plugins": {"orchestrator": "ACTIVE"},
    }
    mock_app.plugin_manager.list_plugins.return_value = [
        PluginInfo(
            name="orchestrator",
            display_name="系统编排器",
            version="1.0.0",
            plugin_type=PluginType.CORE,
            state=PluginState.ACTIVE,
        ),
        PluginInfo(
            name="data_pipeline",
            display_name="数据管道",
            version="1.0.0",
            plugin_type=PluginType.CORE,
            state=PluginState.ACTIVE,
        ),
    ]
    mock_app.plugin_manager.get_plugin.return_value = None
    return mock_app


def _make_candle_df():
    """创建模拟的K线 DataFrame"""
    data = {
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [99.0, 100.0, 101.0],
        "close": [104.0, 105.0, 106.0],
        "volume": [1000.0, 1100.0, 1200.0],
    }
    index = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    return pd.DataFrame(data, index=index)


client = TestClient(app, raise_server_exceptions=False)


class TestGetCandles:
    """GET /api/candles/{symbol}/{tf} 测试"""

    def test_candles_no_app(self):
        """未初始化时返回空列表"""
        app_state.wyckoff_app = None
        resp = client.get("/api/candles/BTC-USDT/H1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_candles_plugin_not_found(self):
        """data_pipeline 插件不存在时返回空列表"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        resp = client.get("/api/candles/BTC-USDT/H1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_candles_no_cached_data_method(self):
        """插件无 get_cached_data 方法时返回空列表"""
        mock_app = _make_mock_app()
        dp_plugin = MagicMock(spec=[])
        mock_app.plugin_manager.get_plugin.return_value = dp_plugin
        app_state.wyckoff_app = mock_app
        resp = client.get("/api/candles/BTC-USDT/H1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_candles_empty_dataframe(self):
        """缓存数据为空 DataFrame 时返回空列表"""
        mock_app = _make_mock_app()
        dp_plugin = MagicMock()
        dp_plugin.get_cached_data.return_value = pd.DataFrame()
        mock_app.plugin_manager.get_plugin.return_value = dp_plugin
        app_state.wyckoff_app = mock_app
        resp = client.get("/api/candles/BTC-USDT/H1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_candles_with_data(self):
        """正常返回K线数据"""
        mock_app = _make_mock_app()
        dp_plugin = MagicMock()
        dp_plugin.get_cached_data.return_value = _make_candle_df()
        mock_app.plugin_manager.get_plugin.return_value = dp_plugin
        app_state.wyckoff_app = mock_app
        resp = client.get("/api/candles/BTC-USDT/H1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data[0]["open"] == 100.0
        assert data[2]["close"] == 106.0
        assert "timestamp" in data[0]
        assert "volume" in data[0]

    def test_candles_with_limit(self):
        """limit 参数限制返回数量"""
        mock_app = _make_mock_app()
        dp_plugin = MagicMock()
        dp_plugin.get_cached_data.return_value = _make_candle_df()
        mock_app.plugin_manager.get_plugin.return_value = dp_plugin
        app_state.wyckoff_app = mock_app
        resp = client.get("/api/candles/BTC-USDT/H1?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


class TestSystemSnapshot:
    """GET /api/system/snapshot 测试"""

    def test_snapshot_no_app(self):
        """未初始化时返回默认快照"""
        app_state.wyckoff_app = None
        resp = client.get("/api/system/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["uptime"] == 0
        assert data["plugin_count"] == 0
        assert data["plugins"] == []

    def test_snapshot_with_plugins(self):
        """正常返回系统快照"""
        import time

        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        app_state.start_time = time.time() - 120.0
        resp = client.get("/api/system/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_running"] is True
        assert data["plugin_count"] == 2
        assert len(data["plugins"]) == 2
        assert data["plugins"][0]["name"] == "orchestrator"
        assert data["plugins"][0]["state"] == "ACTIVE"
        assert data["uptime"] >= 119.0

    def test_snapshot_optional_fields_null(self):
        """插件不存在时可选字段为 null"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        app_state.start_time = 0.0
        resp = client.get("/api/system/snapshot")
        data = resp.json()
        assert data["orchestrator"] is None
        assert data["positions"] is None
        assert data["evolution"] is None
        assert data["wyckoff_engine"] is None

    def test_snapshot_with_orchestrator(self):
        """orchestrator 插件存在时返回其状态"""
        mock_app = _make_mock_app()

        orch = MagicMock()
        orch.get_system_status.return_value = {
            "is_running": True,
            "mode": "paper",
        }

        def side_effect(name):
            if name == "orchestrator":
                return orch
            return None

        mock_app.plugin_manager.get_plugin.side_effect = side_effect
        app_state.wyckoff_app = mock_app
        app_state.start_time = 0.0
        resp = client.get("/api/system/snapshot")
        data = resp.json()
        assert data["orchestrator"]["is_running"] is True
        assert data["orchestrator"]["mode"] == "paper"


class TestConfig:
    """POST /api/config 测试"""

    def test_config_update_no_app(self):
        """未初始化时返回 not_initialized"""
        app_state.wyckoff_app = None
        resp = client.post(
            "/api/config",
            json={"config": {"key": "val"}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_initialized"

    def test_config_update_success(self):
        """正常更新配置"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        resp = client.post(
            "/api/config",
            json={"config": {"new_key": "new_val"}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"
        cfg = mock_app.config_system._global_config
        assert cfg["new_key"] == "new_val"

    def test_config_update_invalid_body(self):
        """请求体格式错误返回 422"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        resp = client.post(
            "/api/config",
            json={"wrong_key": "val"},
        )
        assert resp.status_code == 422


class TestWebSocket:
    """WS /ws/realtime 测试"""

    def test_ws_connect_and_disconnect(self):
        """WebSocket 连接和断开"""
        app_state.wyckoff_app = None
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data

    def test_ws_ping_pong(self):
        """ping/pong 心跳"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_subscribe_valid_topics(self):
        """订阅有效主题"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json(
                {
                    "type": "subscribe",
                    "topics": ["system_status"],
                }
            )
            # 发送 ping 确认连接正常
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_subscribe_invalid_topic_ignored(self):
        """无效主题被忽略不报错"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_json(
                {
                    "type": "subscribe",
                    "topics": ["invalid_topic"],
                }
            )
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_invalid_json_ignored(self):
        """非法 JSON 消息被忽略"""
        mock_app = _make_mock_app()
        app_state.wyckoff_app = mock_app
        with client.websocket_connect("/ws/realtime") as ws:
            ws.send_text("not-json")
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
