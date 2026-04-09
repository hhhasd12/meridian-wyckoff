"""回测 API 端点"""

from __future__ import annotations

import json
import uuid
import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)


def create_router(plugin) -> APIRouter:
    router = APIRouter()

    @router.post("/run")
    async def run_backtest(body: dict):
        """启动回测"""
        symbol = body.get("symbol", "ETHUSDT")
        timeframe = body.get("timeframe", "1d")
        params = body.get("params")
        start_time = body.get("start_time")
        end_time = body.get("end_time")

        result = await plugin.run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            start_time=start_time,
            end_time=end_time,
        )

        score = await plugin.score_result(result, symbol, timeframe)

        # 保存结果
        run_id = uuid.uuid4().hex[:8]
        results_dir = plugin.ctx.storage.base_path / "backtester" / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        output = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "result": result,
            "score": score,
        }

        result_file = results_dir / f"{run_id}.json"
        result_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))

        return {
            "run_id": run_id,
            "total_bars": result["total_bars"],
            "total_events": len(result["events"]),
            "total_transitions": len(result["transitions"]),
            "score": score,
        }

    @router.get("/result/{run_id}")
    async def get_result(run_id: str):
        """获取回测结果"""
        results_dir = plugin.ctx.storage.base_path / "backtester" / "results"
        result_file = results_dir / f"{run_id}.json"

        if not result_file.exists():
            return {"error": f"Result {run_id} not found"}

        return json.loads(result_file.read_text())

    @router.get("/history")
    async def list_history():
        """历史回测列表"""
        results_dir = plugin.ctx.storage.base_path / "backtester" / "results"
        if not results_dir.exists():
            return {"runs": []}

        runs = []
        for f in sorted(results_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                runs.append(
                    {
                        "run_id": data.get("run_id"),
                        "symbol": data.get("symbol"),
                        "timeframe": data.get("timeframe"),
                        "total_bars": data.get("result", {}).get("total_bars", 0),
                        "total_events": len(data.get("result", {}).get("events", [])),
                        "score_summary": {
                            "detection_rate": data.get("score", {}).get(
                                "detection_rate", 0
                            ),
                            "false_positive_rate": data.get("score", {}).get(
                                "false_positive_rate", 0
                            ),
                        },
                    }
                )
            except Exception:
                continue

        return {"runs": runs}

    return router
