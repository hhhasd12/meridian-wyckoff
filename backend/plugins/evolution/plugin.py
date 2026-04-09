"""进化插件入口 — 事件订阅 + 生命周期管理"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from backend.core.types import BackendPlugin, PluginContext
from .case_builder import build_case
from .case_store import CaseStore
from .optimizer import optimize
from .params_manager import ParamsManager
from .routes import create_router

logger = logging.getLogger(__name__)


class EvolutionPlugin(BackendPlugin):
    id = "evolution"
    name = "进化系统"
    version = "0.1.0"
    dependencies = ("datasource", "annotation", "engine")

    def __init__(self):
        self.ctx: PluginContext | None = None
        self.case_store: CaseStore | None = None
        self.params_manager: ParamsManager | None = None

    async def on_init(self, ctx: PluginContext) -> None:
        self.ctx = ctx

        # SQLite 初始化
        db_path = Path(ctx.storage.base_path) / "evolution" / "meridian.db"
        self.case_store = CaseStore(db_path)

        # 参数管理器
        params_root = Path(ctx.storage.base_path) / "evolution"
        self.params_manager = ParamsManager(self.case_store, params_root)

        # 插入默认参数（如果不存在）
        latest = self.case_store.get_latest_params()
        if not latest:
            from ..engine.params import EngineParams

            default_params = EngineParams()
            self.params_manager.save_version(
                default_params, source="default", notes="初始默认参数"
            )

        logger.info("进化插件初始化完成")

    async def on_start(self) -> None:
        logger.info("进化插件启动")

    async def on_stop(self) -> None:
        logger.info("进化插件停止")

    def get_router(self) -> APIRouter:
        return create_router(self)

    def get_subscriptions(self) -> dict:
        return {
            "annotation.created": self._on_annotation_created,
            "annotation.updated": self._on_annotation_updated,
            "annotation.deleted": self._on_annotation_deleted,
            "engine.event_detected": self._on_engine_event,
            "engine.range_created": self._on_range_created,
        }

    # ─── 事件处理 ───

    async def _on_annotation_created(self, data: dict) -> None:
        """
        路径A：标注驱动 — 莱恩标注事件 → 构建 EventCase → 存入案例库
        """
        if not self.case_store:
            return

        label = data.get("label", "")
        if not label:
            return  # 非事件标注，跳过

        symbol = data.get("symbol", "")
        timeframe = data.get("timeframe", "")

        # 获取K线数据
        candles = self._get_candles(symbol, timeframe)

        # 获取引擎状态
        engine_state = self._get_engine_state(symbol, timeframe)

        # 获取当前参数版本
        params_version = "default"
        if self.params_manager:
            latest_params = self.params_manager.load_latest()
            params_version = latest_params.version

        # 构建 EventCase
        case = build_case(data, candles, engine_state, params_version)

        # 写入 SQLite
        case_id = self.case_store.insert_case(case)
        logger.info(
            "案例写入: id=%s type=%s symbol=%s",
            case_id[:8],
            case.get("event_type"),
            symbol,
        )

        # 发布事件
        if self.ctx:
            await self.ctx.event_bus.publish(
                "evolution.case_created",
                {
                    "case_id": case_id,
                    "event_type": case.get("event_type"),
                },
            )

    async def _on_annotation_updated(self, data: dict) -> None:
        """
        路径B：修正驱动 — 莱恩修改标注 → 检测差异 → 生成修正案例
        """
        if not self.case_store:
            return

        drawing_id = data.get("drawing_id", "")
        symbol = data.get("symbol", "")
        timeframe = data.get("timeframe", "")
        label = data.get("label", "")

        if not label:
            return

        # 查找已有的 annotation 案例
        existing = self.case_store.find_by_drawing_id(drawing_id)
        if existing:
            # 更新案例结果
            self.case_store.update_case_result(existing["id"], "success")
            logger.info("案例更新: drawing_id=%s", drawing_id)
        else:
            # 没有已有案例 → 作为新的修正案例写入（weight=3.0）
            candles = self._get_candles(symbol, timeframe)
            engine_state = self._get_engine_state(symbol, timeframe)
            case = build_case(data, candles, engine_state)
            case["source"] = "correction"
            case["weight"] = 3.0  # EVD-5: 修正案例权重 ×3
            case_id = self.case_store.insert_case(case)
            logger.info("修正案例写入: id=%s weight=3.0", case_id[:8])

    async def _on_annotation_deleted(self, data: dict) -> None:
        """标注删除 → 关联案例标记为 REJECTED"""
        if not self.case_store:
            return

        drawing_id = data.get("drawing_id", "")
        if not drawing_id:
            return

        existing = self.case_store.find_by_drawing_id(drawing_id)
        if existing:
            self.case_store.update_case_result(existing["id"], "rejected")
            logger.info("案例标记 REJECTED: drawing_id=%s", drawing_id)

    async def _on_engine_event(self, data: dict) -> None:
        """
        路径C：引擎自动记录 — 检测到事件 → 记录 PENDING 案例
        如果已有莱恩标注则跳过（避免重复）
        """
        if not self.case_store:
            return

        symbol = data.get("symbol", "")
        timeframe = data.get("timeframe", "")
        event = data.get("event")
        if not event:
            return

        # 构建引擎案例
        case = {
            "event_type": event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type),
            "event_result": "pending",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "engine",
            "weight": 0.5,
            "sequence_start_bar": getattr(event, "sequence_start_bar", None),
            "sequence_end_bar": getattr(event, "sequence_end_bar", None),
            "sequence_length": getattr(event, "sequence_length", None),
            "price_extreme": getattr(event, "price_extreme", None),
            "price_body": getattr(event, "price_body", None),
            "volume_ratio": getattr(event, "volume_ratio", None),
            "penetration_depth": getattr(event, "penetration_depth", None),
        }

        case_id = self.case_store.insert_case(case)
        logger.debug("引擎案例写入: id=%s", case_id[:8])

    async def _on_range_created(self, data: dict) -> None:
        """区间创建事件 — 注册到历史区间索引"""
        logger.info("区间创建通知: symbol=%s", data.get("symbol", ""))
        # 后续可扩展：将区间信息注册到历史区间库

    # ─── 进化运行 ───

    async def run_optimization(self) -> dict:
        """
        触发参数优化流程：
        1. 查询所有案例
        2. 调用 optimizer.optimize()
        3. 保存新参数版本
        4. 发布 evolution.params_updated
        """
        if not self.case_store or not self.params_manager:
            return {"error": "插件未初始化"}

        now = datetime.now(timezone.utc).isoformat()
        run_id = str(uuid.uuid4())

        # 创建运行记录
        current_params = self.params_manager.load_latest()
        self.case_store.insert_run(
            {
                "id": run_id,
                "started_at": now,
                "status": "running",
                "params_version_before": current_params.version,
            }
        )

        # 查询所有案例
        all_cases = self.case_store.query_cases(limit=10000)
        if not all_cases:
            self.case_store.update_run(
                run_id,
                {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "notes": "无案例可优化",
                },
            )
            return {"run_id": run_id, "status": "completed", "message": "无案例可优化"}

        # 优化
        current_dict = asdict(current_params)
        new_params_dict, params_diff = optimize(all_cases, current_dict)

        if not params_diff:
            self.case_store.update_run(
                run_id,
                {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "notes": "无需优化（样本不足或无变化）",
                    "cases_used": len(all_cases),
                },
            )
            return {"run_id": run_id, "status": "completed", "message": "无需优化"}

        # 保存新参数
        from .params_manager import _dict_to_params

        new_params = _dict_to_params(new_params_dict)
        new_version = self.params_manager.save_version(
            new_params, source=f"evolution_run:{run_id[:8]}"
        )

        # 更新运行记录
        self.case_store.update_run(
            run_id,
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "cases_used": len(all_cases),
                "params_version_after": new_version,
                "params_diff": params_diff,
            },
        )

        # 发布事件 → engine 热加载
        if self.ctx:
            await self.ctx.event_bus.publish(
                "evolution.params_updated",
                {
                    "version": new_version,
                    "path": str(
                        self.params_manager.storage_root / "params_latest.json"
                    ),
                },
            )
            await self.ctx.event_bus.publish(
                "evolution.run_completed",
                {
                    "run_id": run_id,
                    "improvements": len(params_diff),
                },
            )

        logger.info(
            "优化完成: run=%s, params=%s, changes=%d",
            run_id[:8],
            new_version,
            len(params_diff),
        )

        return {
            "run_id": run_id,
            "status": "completed",
            "params_version": new_version,
            "changes": len(params_diff),
            "params_diff": params_diff,
        }

    # ─── helpers ───

    def _get_candles(self, symbol: str, timeframe: str) -> Any:
        """获取K线数据"""
        if not self.ctx:
            return None
        datasource = self.ctx.get_plugin("datasource")
        if not datasource:
            return None
        try:
            return datasource.get_candles_df(symbol, timeframe)
        except Exception as e:
            logger.warning("获取K线失败: %s/%s: %s", symbol, timeframe, e)
            return None

    def _get_engine_state(self, symbol: str, timeframe: str) -> dict | None:
        """获取引擎状态"""
        if not self.ctx:
            return None
        engine = self.ctx.get_plugin("engine")
        if not engine:
            return None
        try:
            state = engine.get_state(symbol, timeframe)
            if state is None:
                return None
            # 转为 dict（简化版，只取进化需要的字段）
            result = {
                "current_phase": state.current_phase.value
                if hasattr(state.current_phase, "value")
                else str(state.current_phase),
                "direction": state.direction.value
                if hasattr(state.direction, "value")
                else str(state.direction),
                "structure_type": state.structure_type.value
                if hasattr(state.structure_type, "value")
                else str(state.structure_type),
            }
            if state.active_range:
                result["active_range"] = {
                    "range_id": state.active_range.range_id,
                }
            return result
        except Exception as e:
            logger.warning("获取引擎状态失败: %s/%s: %s", symbol, timeframe, e)
            return None
