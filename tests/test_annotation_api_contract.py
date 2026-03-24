"""标注 API 契约测试 — 验证 POST/GET/DELETE /api/annotations 端点

运行时机: 每次 PR
预期时间: < 5 秒
覆盖范围:
    1. POST 创建标注，验证 success=True + annotation 返回
    2. GET 获取标注列表
    3. DELETE 删除标注
    4. 缺少必要参数时返回 error
    5. 插件未加载时的降级行为
"""

import pytest
from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.api.app import app, app_state


# ================================================================
# Fixture — lifespan 正常执行后替换 app_state
# ================================================================


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """正常启动的测试客户端（有 annotation 插件）"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_plugin() -> Generator[TestClient, None, None]:
    """模拟 annotation 插件未加载的客户端

    先让 lifespan 正常初始化，然后替换 app_state 为 mock。
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        # lifespan 已执行，现在替换为 mock
        original = app_state.wyckoff_app
        mock_app = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_plugin.return_value = None
        mock_app.plugin_manager = mock_manager
        app_state.wyckoff_app = mock_app

        yield c

        app_state.wyckoff_app = original


# ================================================================
# 测试用例
# ================================================================


class TestAnnotationCRUD:
    """标注 CRUD 端点契约验证"""

    def test_create_annotation_endpoint(self, client: TestClient) -> None:
        """POST /api/annotations — 创建标注，验证 success + annotation"""
        r = client.post(
            "/api/annotations",
            json={
                "symbol": "TEST/USDT",
                "timeframe": "M15",
                "type": "event",
                "event_type": "SC",
                "start_bar_index": 100,
                "notes": "Selling Climax test",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "annotation" in data
        ann = data["annotation"]
        assert ann["symbol"] == "TEST/USDT"
        assert ann["timeframe"] == "M15"
        assert ann["type"] == "event"
        assert "id" in ann

    def test_get_annotations_endpoint(self, client: TestClient) -> None:
        """GET /api/annotations?symbol=&timeframe= — 获取标注列表"""
        # 先创建一条
        client.post(
            "/api/annotations",
            json={
                "symbol": "TEST/USDT",
                "timeframe": "M15",
                "type": "event",
                "event_type": "AR",
            },
        )
        # 查询
        r = client.get("/api/annotations?symbol=TEST/USDT&timeframe=M15")
        assert r.status_code == 200
        data = r.json()
        assert "annotations" in data
        assert isinstance(data["annotations"], list)
        assert len(data["annotations"]) >= 1

    def test_delete_annotation_endpoint(self, client: TestClient) -> None:
        """DELETE /api/annotations/{id} — 删除标注"""
        # 先创建
        cr = client.post(
            "/api/annotations",
            json={
                "symbol": "DEL/USDT",
                "timeframe": "H1",
                "type": "level",
                "price": 1500.0,
                "level_label": "SC_LOW",
            },
        )
        ann_id = cr.json()["annotation"]["id"]
        # 删除
        r = client.delete(f"/api/annotations/{ann_id}?symbol=DEL/USDT&timeframe=H1")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True

    def test_get_annotations_missing_params(self, client: TestClient) -> None:
        """GET /api/annotations 缺少 symbol/timeframe 参数时返回 error"""
        # 完全缺少参数
        r = client.get("/api/annotations")
        assert r.status_code == 200
        data = r.json()
        assert "error" in data

        # 只有 symbol
        r2 = client.get("/api/annotations?symbol=ETHUSDT")
        data2 = r2.json()
        assert "error" in data2

    def test_annotation_plugin_not_loaded(self, client_no_plugin: TestClient) -> None:
        """插件未加载时 POST 返回 error，GET 返回空列表"""
        # POST — 返回 error
        r = client_no_plugin.post(
            "/api/annotations",
            json={
                "symbol": "ETHUSDT",
                "timeframe": "H4",
                "type": "event",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "error" in data

        # GET — 返回空列表（降级）
        r2 = client_no_plugin.get("/api/annotations?symbol=ETHUSDT&timeframe=H4")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["annotations"] == []

        # DELETE — 返回 error
        r3 = client_no_plugin.delete(
            "/api/annotations/ann_1?symbol=ETHUSDT&timeframe=H4"
        )
        assert r3.status_code == 200
        data3 = r3.json()
        assert "error" in data3
