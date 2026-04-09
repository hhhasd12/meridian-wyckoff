"""案例库 — SQLite 存储层（event_cases + evolution_runs + params_history）"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_cases (
    id                TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    event_result      TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    timeframe         TEXT NOT NULL,

    -- 时序定位
    sequence_start_bar INTEGER,
    sequence_end_bar   INTEGER,
    sequence_length    INTEGER,

    -- 价格特征（7维）
    price_extreme      REAL,
    price_body         REAL,
    penetration_depth  REAL,
    recovery_speed     REAL,
    position_in_range  REAL,
    volume_ratio       REAL,
    effort_vs_result   REAL,

    -- 上下文特征
    trend_slope        REAL,
    trend_length       INTEGER,
    support_distance   REAL,
    wick_ratio         REAL,
    body_position      REAL,

    -- 区间上下文
    range_id           TEXT,
    phase              TEXT,
    direction          TEXT,
    structure_type     TEXT,
    range_width        REAL,

    -- K线快照（JSON数组）
    pre_bars           TEXT,
    sequence_bars      TEXT,
    post_bars          TEXT,

    -- 后续结果
    result_5bar        REAL,
    result_10bar       REAL,
    result_20bar       REAL,

    -- 来源与权重
    source             TEXT NOT NULL,
    drawing_id         TEXT,
    annotation_label   TEXT,
    weight             REAL DEFAULT 1.0,
    params_version     TEXT,

    -- 变体（P2）
    variant_tag        TEXT,

    -- 事件链上下文（EVD-10）
    prior_events       TEXT,               -- JSON: ["bc","st","ut","lpsy","sow"]

    -- 元数据
    created_at         TEXT NOT NULL,
    notes              TEXT
);

CREATE INDEX IF NOT EXISTS idx_cases_type ON event_cases(event_type);
CREATE INDEX IF NOT EXISTS idx_cases_result ON event_cases(event_result);
CREATE INDEX IF NOT EXISTS idx_cases_symbol_tf ON event_cases(symbol, timeframe);

CREATE TABLE IF NOT EXISTS evolution_runs (
    id                    TEXT PRIMARY KEY,
    started_at            TEXT NOT NULL,
    completed_at          TEXT,
    status                TEXT DEFAULT 'running',
    cases_used            INTEGER,
    params_version_before TEXT,
    params_version_after  TEXT,
    params_diff           TEXT,
    notes                 TEXT
);

CREATE TABLE IF NOT EXISTS params_history (
    version     TEXT PRIMARY KEY,
    params_json TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    source      TEXT,
    notes       TEXT
);
"""


class CaseStore:
    """SQLite CRUD for evolution plugin"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """创建三表 + 索引"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(SCHEMA_SQL)
        logger.info("SQLite 初始化完成: %s", self.db_path)

    # ─── event_cases ───

    def insert_case(self, case: dict) -> str:
        """插入案例，返回 case_id"""
        case_id = case.get("id") or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO event_cases (
                    id, event_type, event_result, symbol, timeframe,
                    sequence_start_bar, sequence_end_bar, sequence_length,
                    price_extreme, price_body, penetration_depth,
                    recovery_speed, position_in_range, volume_ratio,
                    effort_vs_result, trend_slope, trend_length,
                    support_distance, wick_ratio, body_position,
                    range_id, phase, direction, structure_type, range_width,
                    pre_bars, sequence_bars, post_bars,
                    result_5bar, result_10bar, result_20bar,
                    source, drawing_id, annotation_label, weight,
                    params_version, variant_tag, prior_events, created_at, notes
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""",
                (
                    case_id,
                    case.get("event_type", ""),
                    case.get("event_result", "pending"),
                    case.get("symbol", ""),
                    case.get("timeframe", ""),
                    case.get("sequence_start_bar"),
                    case.get("sequence_end_bar"),
                    case.get("sequence_length"),
                    case.get("price_extreme"),
                    case.get("price_body"),
                    case.get("penetration_depth"),
                    case.get("recovery_speed"),
                    case.get("position_in_range"),
                    case.get("volume_ratio"),
                    case.get("effort_vs_result"),
                    case.get("trend_slope"),
                    case.get("trend_length"),
                    case.get("support_distance"),
                    case.get("wick_ratio"),
                    case.get("body_position"),
                    case.get("range_id"),
                    case.get("phase"),
                    case.get("direction"),
                    case.get("structure_type"),
                    case.get("range_width"),
                    _to_json(case.get("pre_bars")),
                    _to_json(case.get("sequence_bars")),
                    _to_json(case.get("post_bars")),
                    case.get("result_5bar"),
                    case.get("result_10bar"),
                    case.get("result_20bar"),
                    case.get("source", "annotation"),
                    case.get("drawing_id"),
                    case.get("annotation_label"),
                    case.get("weight", 1.0),
                    case.get("params_version"),
                    case.get("variant_tag"),
                    case.get("prior_events"),
                    case.get("created_at", now),
                    case.get("notes"),
                ),
            )
        return case_id

    def query_cases(
        self,
        event_type: str | None = None,
        event_result: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """查询案例，支持筛选"""
        clauses: list[str] = []
        params: list[Any] = []

        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if event_result:
            clauses.append("event_result = ?")
            params.append(event_result)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            clauses.append("timeframe = ?")
            params.append(timeframe)
        if source:
            clauses.append("source = ?")
            params.append(source)

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM event_cases{where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_dict(r) for r in rows]

    def get_case(self, case_id: str) -> dict | None:
        """获取单个案例"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM event_cases WHERE id = ?", (case_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None

    def delete_case(self, case_id: str) -> bool:
        """删除案例"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM event_cases WHERE id = ?", (case_id,))
            return cursor.rowcount > 0

    def update_case_result(self, case_id: str, result: str) -> bool:
        """更新案例结果"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "UPDATE event_cases SET event_result = ? WHERE id = ?",
                (result, case_id),
            )
            return cursor.rowcount > 0

    def get_stats(self) -> dict:
        """按事件类型统计：数量/成功率/平均特征"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT
                    event_type,
                    COUNT(*) as total,
                    SUM(CASE WHEN event_result = 'success' THEN 1 ELSE 0 END) as successes,
                    SUM(CASE WHEN event_result = 'rejected' THEN 1 ELSE 0 END) as rejected,
                    AVG(volume_ratio) as avg_volume_ratio,
                    AVG(penetration_depth) as avg_penetration_depth,
                    AVG(recovery_speed) as avg_recovery_speed,
                    AVG(effort_vs_result) as avg_effort_vs_result
                FROM event_cases
                GROUP BY event_type"""
            ).fetchall()

            stats = {}
            for r in rows:
                d = _row_to_dict(r)
                total = d["total"] or 0
                d["success_rate"] = (d["successes"] or 0) / total if total > 0 else 0
                stats[d["event_type"]] = d
            return stats

    def find_by_drawing_id(self, drawing_id: str) -> dict | None:
        """通过 drawing_id 查找关联案例"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM event_cases WHERE drawing_id = ?", (drawing_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None

    # ─── evolution_runs ───

    def insert_run(self, run: dict) -> str:
        """插入进化运行记录"""
        run_id = run.get("id") or str(uuid.uuid4())
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO evolution_runs (
                    id, started_at, completed_at, status, cases_used,
                    params_version_before, params_version_after, params_diff, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    run.get("started_at", ""),
                    run.get("completed_at"),
                    run.get("status", "running"),
                    run.get("cases_used"),
                    run.get("params_version_before"),
                    run.get("params_version_after"),
                    _to_json(run.get("params_diff")),
                    run.get("notes"),
                ),
            )
        return run_id

    def update_run(self, run_id: str, updates: dict) -> bool:
        """更新运行记录"""
        sets: list[str] = []
        params: list[Any] = []
        for key in (
            "completed_at",
            "status",
            "cases_used",
            "params_version_after",
            "params_diff",
            "notes",
        ):
            if key in updates:
                val = updates[key]
                if key == "params_diff" and isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                sets.append(f"{key} = ?")
                params.append(val)
        if not sets:
            return False
        params.append(run_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                f"UPDATE evolution_runs SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            return cursor.rowcount > 0

    def get_run(self, run_id: str) -> dict | None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM evolution_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None

    def get_runs(self, limit: int = 50) -> list[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM evolution_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

    # ─── params_history ───

    def insert_params(
        self, version: str, params_json: str, source: str = "", notes: str = ""
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO params_history
                    (version, params_json, created_at, source, notes)
                    VALUES (?, ?, ?, ?, ?)""",
                (version, params_json, now, source, notes),
            )

    def get_latest_params(self) -> dict | None:
        """获取最新参数版本"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM params_history ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return _row_to_dict(row) if row else None

    def get_params_history(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM params_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

    def get_params_version(self, version: str) -> dict | None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM params_history WHERE version = ?", (version,)
            ).fetchone()
            return _row_to_dict(row) if row else None


# ─── helpers ───


def _to_json(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # 解析 JSON 字段
    for key in (
        "pre_bars",
        "sequence_bars",
        "post_bars",
        "params_diff",
        "prior_events",
    ):
        val = d.get(key)
        if isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return d
