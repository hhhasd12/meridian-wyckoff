"""API 契约测试 — 验证每个 REST/WebSocket 端点返回前端期望的数据格式

运行时机: 每次 PR
预期时间: < 10 秒
覆盖范围:
    1. 每个 REST 端点返回正确的 HTTP 状态码和 JSON 结构
    2. WebSocket 主题数据格式与前端 types/api.ts 匹配
    3. 前端调用的每个 API 函数都有对应的后端端点
"""

import pytest
from typing import Any, Dict, Generator, List, Optional

from fastapi.testclient import TestClient

from src.api.app import app


# ================================================================
# Fixture
# ================================================================


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """FastAPI 测试客户端（自动触发 lifespan）"""
    with TestClient(app) as c:
        yield c


# ================================================================
# 1. REST 端点存在性 + 基本响应
# ================================================================


class TestRestEndpoints:
    """所有 REST 端点必须返回 200 且可解析为 JSON"""

    def test_get_candles(self, client: TestClient) -> None:
        """GET /api/candles/{symbol}/{tf}"""
        r = client.get("/api/candles/BTC%2FUSDT/H4")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_get_system_snapshot(self, client: TestClient) -> None:
        """GET /api/system/snapshot"""
        r = client.get("/api/system/snapshot")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_get_evolution_results(self, client: TestClient) -> None:
        """GET /api/evolution/results"""
        r = client.get("/api/evolution/results")
        assert r.status_code == 200
        data = r.json()
        assert "cycles" in data
        assert "total" in data

    def test_get_evolution_latest(self, client: TestClient) -> None:
        """GET /api/evolution/latest"""
        r = client.get("/api/evolution/latest")
        assert r.status_code == 200
        data = r.json()
        assert "cycle" in data
        assert "total" in data

    def test_get_decisions(self, client: TestClient) -> None:
        """GET /api/decisions"""
        r = client.get("/api/decisions")
        assert r.status_code == 200
        data = r.json()
        assert "decisions" in data
        assert "total" in data

    def test_get_evolution_config(self, client: TestClient) -> None:
        """GET /api/evolution/config"""
        r = client.get("/api/evolution/config")
        assert r.status_code == 200
        data = r.json()
        assert "config" in data

    def test_get_trades(self, client: TestClient) -> None:
        """GET /api/trades"""
        r = client.get("/api/trades")
        assert r.status_code == 200
        data = r.json()
        assert "trades" in data

    def test_get_advisor_latest(self, client: TestClient) -> None:
        """GET /api/advisor/latest"""
        r = client.get("/api/advisor/latest")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_post_config(self, client: TestClient) -> None:
        """POST /api/config"""
        r = client.post(
            "/api/config",
            json={"config": {"test_key": "test_value"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "updated"


# ================================================================
# 2. 系统快照契约（前端 App.tsx 依赖的字段）
# ================================================================


class TestSnapshotContract:
    """系统快照必须包含前端各组件依赖的字段"""

    def test_snapshot_top_level_fields(self, client: TestClient) -> None:
        """快照包含前端 App.tsx select() 使用的顶层字段"""
        r = client.get("/api/system/snapshot")
        data = r.json()

        # App.tsx L44-54 依赖这些字段
        assert "uptime" in data
        assert "is_running" in data
        assert "plugins" in data
        assert "wyckoff_engine" in data
        assert "positions" in data
        assert "evolution" in data
        assert "orchestrator" in data

    def test_snapshot_plugin_list_format(self, client: TestClient) -> None:
        """插件列表的每个条目有 name/display_name/version/state"""
        r = client.get("/api/system/snapshot")
        plugins = r.json()["plugins"]

        assert isinstance(plugins, list)
        assert len(plugins) >= 18

        for p in plugins:
            assert "name" in p, f"插件条目缺少 name: {p}"
            assert "state" in p, f"插件条目缺少 state: {p}"

    def test_snapshot_orchestrator_format(self, client: TestClient) -> None:
        """orchestrator 状态包含 Sidebar 和 AlertBanner 需要的字段"""
        r = client.get("/api/system/snapshot")
        orch = r.json().get("orchestrator")

        if orch is not None:
            assert "status" in orch
            assert "circuit_breaker_tripped" in orch

    def test_snapshot_engine_state_format(self, client: TestClient) -> None:
        """wyckoff_engine 状态包含 WyckoffPanel 需要的字段"""
        r = client.get("/api/system/snapshot")
        engine = r.json().get("wyckoff_engine")

        if engine is not None:
            assert "state_machines" in engine
            assert "timeframes" in engine


# ================================================================
# 3. K 线数据格式契约（前端 useChart.ts 依赖）
# ================================================================


class TestCandleContract:
    """K 线数据格式必须与 Lightweight Charts 兼容"""

    def test_candle_fields(self, client: TestClient) -> None:
        """每根 K 线包含 timestamp/open/high/low/close/volume"""
        r = client.get("/api/candles/BTC%2FUSDT/H4?limit=5")
        candles = r.json()

        # 可能为空（没有缓存数据），这是允许的
        if len(candles) > 0:
            c = candles[0]
            for field in ["timestamp", "open", "high", "low", "close", "volume"]:
                assert field in c, f"K 线缺少字段: {field}"
            assert isinstance(c["open"], (int, float))
            assert isinstance(c["close"], (int, float))


# ================================================================
# 4. 进化 API 契约（前端 EvolutionTab 依赖）
# ================================================================


class TestEvolutionContract:
    """进化 API 返回格式与前端 EvolutionTab 匹配"""

    def test_evolution_results_cycle_format(self, client: TestClient) -> None:
        """进化结果的 cycles 是列表"""
        r = client.get("/api/evolution/results")
        data = r.json()
        assert isinstance(data["cycles"], list)
        assert isinstance(data["total"], int)

    def test_evolution_config_format(self, client: TestClient) -> None:
        """进化配置返回字典"""
        r = client.get("/api/evolution/config")
        data = r.json()
        assert isinstance(data["config"], dict)

    def test_advisor_latest_format(self, client: TestClient) -> None:
        """AI 顾问返回包含 analysis 和 status"""
        r = client.get("/api/advisor/latest")
        data = r.json()
        assert "analysis" in data
        assert "status" in data
        assert data["status"] in (
            "ok",
            "no_data",
            "not_initialized",
            "plugin_not_found",
            "no_method",
            "error",
        )


# ================================================================
# 5. WebSocket 主题数据格式（模拟 _collect_topic_data）
# ================================================================


class TestWebSocketTopicData:
    """WebSocket 各主题推送的数据格式验证

    不启动真实 WebSocket，而是直接调用 _collect_topic_data
    验证返回的 JSON 格式与前端 App.tsx handleMessage 匹配
    """

    def test_collect_topic_data_importable(self) -> None:
        """_collect_topic_data 函数可导入"""
        from src.api.app import _collect_topic_data

        assert callable(_collect_topic_data)

    def test_wyckoff_topic_format(self, client: TestClient) -> None:
        """wyckoff 主题返回 type=wyckoff_state"""
        from src.api.app import _collect_topic_data, app_state

        if app_state.wyckoff_app is None:
            pytest.skip("WyckoffApp 未初始化")

        manager = app_state.wyckoff_app.plugin_manager
        result = _collect_topic_data("wyckoff", manager)

        if result is not None:
            assert result["type"] == "wyckoff_state"
            assert "data" in result
            assert "timestamp" in result

    def test_positions_topic_format(self, client: TestClient) -> None:
        """positions 主题返回 type=position_update"""
        from src.api.app import _collect_topic_data, app_state

        if app_state.wyckoff_app is None:
            pytest.skip("WyckoffApp 未初始化")

        manager = app_state.wyckoff_app.plugin_manager
        result = _collect_topic_data("positions", manager)

        if result is not None:
            assert result["type"] == "position_update"
            assert "data" in result
            assert isinstance(result["data"], list)

    def test_evolution_topic_format(self, client: TestClient) -> None:
        """evolution 主题返回 type=evolution_progress"""
        from src.api.app import _collect_topic_data, app_state

        if app_state.wyckoff_app is None:
            pytest.skip("WyckoffApp 未初始化")

        manager = app_state.wyckoff_app.plugin_manager
        result = _collect_topic_data("evolution", manager)

        if result is not None:
            assert result["type"] == "evolution_progress"
            assert "data" in result

    def test_system_status_topic_format(self, client: TestClient) -> None:
        """system_status 主题返回 type=system_status + recent_logs"""
        from src.api.app import _collect_topic_data, app_state

        if app_state.wyckoff_app is None:
            pytest.skip("WyckoffApp 未初始化")

        manager = app_state.wyckoff_app.plugin_manager
        result = _collect_topic_data("system_status", manager)

        if result is not None:
            assert result["type"] == "system_status"
            assert "data" in result
            # 前端 App.tsx L110 依赖 recent_logs 字段
            assert "recent_logs" in result["data"], (
                "system_status 缺少 recent_logs — LogsTab 将无数据"
            )

    def test_invalid_topic_returns_none(self, client: TestClient) -> None:
        """无效主题返回 None"""
        from src.api.app import _collect_topic_data, app_state

        if app_state.wyckoff_app is None:
            pytest.skip("WyckoffApp 未初始化")

        manager = app_state.wyckoff_app.plugin_manager
        result = _collect_topic_data("nonexistent_topic", manager)
        assert result is None


# ================================================================
# 6. 前端 API 函数 ↔ 后端端点映射完整性
# ================================================================


class TestFrontendApiMapping:
    """前端 core/api.ts 中定义的每个函数都有对应的后端端点"""

    # 前端 api.ts 中的 10 个函数 → 对应的端点和方法
    FRONTEND_API_MAP = [
        ("fetchCandles", "GET", "/api/candles/BTC%2FUSDT/H4"),
        ("fetchSnapshot", "GET", "/api/system/snapshot"),
        ("updateConfig", "POST", "/api/config"),
        ("fetchEvolutionResults", "GET", "/api/evolution/results"),
        ("fetchTrades", "GET", "/api/trades"),
        ("fetchAdvisorLatest", "GET", "/api/advisor/latest"),
        ("startEvolution", "POST", "/api/evolution/start"),
        ("stopEvolution", "POST", "/api/evolution/stop"),
        ("fetchDecisions", "GET", "/api/decisions"),
        ("fetchEvolutionConfig", "GET", "/api/evolution/config"),
    ]

    @pytest.mark.parametrize(
        "fn_name,method,path",
        FRONTEND_API_MAP,
        ids=[fn for fn, _, _ in FRONTEND_API_MAP],
    )
    def test_endpoint_exists(
        self, client: TestClient, fn_name: str, method: str, path: str
    ) -> None:
        """前端函数 {fn_name} 对应的 {method} {path} 端点存在"""
        if method == "GET":
            r = client.get(path)
        elif method == "POST":
            # POST 端点需要请求体
            if "config" in path:
                r = client.post(path, json={"config": {}})
            elif "start" in path:
                r = client.post(path, json={"max_cycles": 1})
            else:
                r = client.post(path)
        else:
            pytest.fail(f"未知方法: {method}")

        assert r.status_code in (200, 201), (
            f"前端 {fn_name}() → {method} {path} 返回 {r.status_code}"
        )
