"""参数版本管理 — save/load/rollback/publish"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .case_store import CaseStore
from ..engine.params import EngineParams, save_params, load_params

logger = logging.getLogger(__name__)


class ParamsManager:
    """管理引擎参数的版本化存储"""

    def __init__(self, case_store: CaseStore, storage_root: Path):
        self.case_store = case_store
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def save_version(
        self,
        params: EngineParams,
        source: str = "evolution",
        notes: str = "",
    ) -> str:
        """
        保存新参数版本。
        1. 写入 params_history 表
        2. 更新 params_latest.json（供 engine 热加载）
        返回版本ID。
        """
        version = (
            params.version
            or f"v_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        )
        params.version = version
        params_json = json.dumps(asdict(params), ensure_ascii=False, indent=2)

        # 存入 SQLite
        self.case_store.insert_params(version, params_json, source, notes)

        # 写 params_latest.json
        latest_path = self.storage_root / "params_latest.json"
        save_params(params, latest_path)

        logger.info("参数版本已保存: %s (source=%s)", version, source)
        return version

    def load_latest(self) -> EngineParams:
        """加载最新参数版本"""
        latest_path = self.storage_root / "params_latest.json"
        if latest_path.exists():
            return load_params(latest_path)

        # 尝试从 SQLite 加载
        record = self.case_store.get_latest_params()
        if record and record.get("params_json"):
            try:
                data = json.loads(record["params_json"])
                return _dict_to_params(data)
            except Exception as e:
                logger.warning("从 SQLite 加载参数失败: %s", e)

        return EngineParams()

    def rollback(self, version: str) -> EngineParams | None:
        """
        回滚到指定参数版本。
        1. 从 params_history 读取旧版本
        2. 写入 params_latest.json
        返回旧版本参数。
        """
        record = self.case_store.get_params_version(version)
        if not record or not record.get("params_json"):
            logger.warning("参数版本不存在: %s", version)
            return None

        try:
            data = json.loads(record["params_json"])
            params = _dict_to_params(data)
        except Exception as e:
            logger.error("解析参数版本失败: %s: %s", version, e)
            return None

        # 更新 latest
        latest_path = self.storage_root / "params_latest.json"
        save_params(params, latest_path)

        logger.info("参数已回滚到: %s", version)
        return params

    def save_manual(self, updates: dict, notes: str = "") -> EngineParams:
        """
        手动修改参数。
        updates 是 {param_path: value} 格式，如:
        {"range_engine.st_max_distance_pct": 0.15}
        """
        params = self.load_latest()
        from .optimizer import _set_param

        params_dict = asdict(params)
        for path, value in updates.items():
            _set_param(params_dict, path, value)
        params = _dict_to_params(params_dict)
        version = self.save_version(params, source="manual", notes=notes)
        return params


def _dict_to_params(data: dict) -> EngineParams:
    """将字典转为 EngineParams"""
    from ..engine.params import RangeEngineParams, EventEngineParams, RuleEngineParams

    params = EngineParams(version=data.get("version", "loaded"))
    if "range_engine" in data:
        params.range_engine = RangeEngineParams(**data["range_engine"])
    if "event_engine" in data:
        params.event_engine = EventEngineParams(**data["event_engine"])
    if "rule_engine" in data:
        params.rule_engine = RuleEngineParams(**data["rule_engine"])
    return params
