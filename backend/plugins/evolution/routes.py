"""进化插件 API 路由 — 12 个端点"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)


def create_router(plugin) -> APIRouter:
    router = APIRouter()

    # ─── 案例管理 ───

    @router.get("/cases")
    async def list_cases(
        event_type: str | None = None,
        event_result: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ):
        """案例列表（支持筛选）"""
        if not plugin.case_store:
            return {"error": "案例库未初始化"}
        cases = plugin.case_store.query_cases(
            event_type=event_type,
            event_result=event_result,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            limit=limit,
        )
        return {"cases": cases, "total": len(cases)}

    @router.get("/cases/stats")
    async def get_case_stats():
        """按类型统计（数量/成功率/平均特征）"""
        if not plugin.case_store:
            return {"error": "案例库未初始化"}
        return plugin.case_store.get_stats()

    @router.get("/cases/{case_id}")
    async def get_case(case_id: str):
        """案例详情"""
        if not plugin.case_store:
            return {"error": "案例库未初始化"}
        case = plugin.case_store.get_case(case_id)
        if case:
            return case
        return Response(status_code=404, content="案例不存在")

    @router.delete("/cases/{case_id}")
    async def delete_case(case_id: str):
        """删除案例"""
        if not plugin.case_store:
            return {"error": "案例库未初始化"}
        if plugin.case_store.delete_case(case_id):
            return {"ok": True}
        return Response(status_code=404, content="案例不存在")

    # ─── 进化运行 ───

    @router.post("/run")
    async def run_optimization():
        """触发参数优化"""
        result = await plugin.run_optimization()
        return result

    @router.get("/runs")
    async def list_runs(limit: int = 50):
        """历史运行记录"""
        if not plugin.case_store:
            return {"error": "案例库未初始化"}
        runs = plugin.case_store.get_runs(limit=limit)
        return {"runs": runs}

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str):
        """运行详情（含params_diff）"""
        if not plugin.case_store:
            return {"error": "案例库未初始化"}
        run = plugin.case_store.get_run(run_id)
        if run:
            return run
        return Response(status_code=404, content="运行记录不存在")

    # ─── 参数管理 ───

    @router.get("/params/current")
    async def get_current_params():
        """当前参数"""
        if not plugin.params_manager:
            return {"error": "参数管理器未初始化"}
        params = plugin.params_manager.load_latest()
        from dataclasses import asdict

        return asdict(params)

    @router.get("/params/history")
    async def get_params_history(limit: int = 20):
        """参数版本历史"""
        if not plugin.case_store:
            return {"error": "案例库未初始化"}
        history = plugin.case_store.get_params_history(limit=limit)
        return {"history": history}

    @router.post("/params/rollback/{version}")
    async def rollback_params(version: str):
        """回滚到指定版本"""
        if not plugin.params_manager or not plugin.ctx:
            return {"error": "参数管理器未初始化"}
        params = plugin.params_manager.rollback(version)
        if params is None:
            return Response(status_code=404, content="参数版本不存在")

        # 通知 engine 热加载
        await plugin.ctx.event_bus.publish(
            "evolution.params_updated",
            {
                "version": params.version,
                "path": str(plugin.params_manager.storage_root / "params_latest.json"),
            },
        )
        from dataclasses import asdict

        return {"ok": True, "params": asdict(params)}

    @router.post("/params/manual")
    async def manual_update_params(request: Request):
        """手动修改参数"""
        if not plugin.params_manager:
            return {"error": "参数管理器未初始化"}
        body = await request.json()
        updates = body.get("updates", {})
        notes = body.get("notes", "")
        if not updates:
            return Response(status_code=400, content="缺少 updates 字段")
        params = plugin.params_manager.save_manual(updates, notes=notes)

        # 通知 engine
        if plugin.ctx:
            await plugin.ctx.event_bus.publish(
                "evolution.params_updated",
                {
                    "version": params.version,
                    "path": str(
                        plugin.params_manager.storage_root / "params_latest.json"
                    ),
                },
            )
        from dataclasses import asdict

        return {"ok": True, "params": asdict(params)}

    return router
