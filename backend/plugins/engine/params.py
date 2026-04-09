"""进化参数 — 所有检测条件的阈值，初版极宽松"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RangeEngineParams:
    ar_min_bounce_pct: float = 0.01  # AR最小反弹1%
    ar_min_bars: int = 1  # AR最少1根K线
    st_max_distance_pct: float = 0.20  # ST与SC最大距离20%
    st_max_volume_ratio: float = 999.0  # ST成交量不限制
    range_min_width_pct: float = 0.01  # 区间最小宽度1%
    reentry_threshold: float = 0.5
    confirmation_bars: int = 1
    max_breakout_age: int = 999


@dataclass
class BreakoutParams:
    """突破检测器参数 — 初版极宽松（RD-55）"""

    approach_zone: float = 0.15  # 多近算"接近边界"（占区间宽度比例）
    breakout_depth: float = 0.02  # 穿越多深算候选（占区间宽度比例）
    confirm_distance: float = 0.10  # 远离多远自动确认（占区间宽度比例）
    confirm_bars: int = 5  # 持续多久不回来算确认（备用）
    volume_context_window: int = 20  # 计算量价背景的窗口长度
    return_threshold: float = 0.80  # 回来多深算假突破（占穿越深度比例）


@dataclass
class SupplyDemandParams:
    """供需力量对比检测器参数 — 初版极宽松（RD-55）"""

    move_threshold: float = 0.02  # 多大的移动才算"方向移动"（2%）
    move_window: int = 10  # 检测移动的K线窗口
    strong_retracement: float = 0.7  # 反弹比率超过多少算"强反向"（=不是供需信号）
    consolidation_threshold: float = 0.03  # 横盘区域多窄算"窄幅"（占区间宽度）
    min_consolidation_bars: int = 3  # 最少横盘多少根K线
    effort_result_threshold: float = 0.5  # effort_vs_result低于多少算"弱势"
    volume_decay_threshold: float = 0.6  # 成交量衰减多少算"缩量"（相对移动期均量）
    boundary_proximity: float = 0.15  # 多近算"靠近边界"（占区间宽度，用于LPSY/LPS判定）


@dataclass
class EventEngineParams:
    approach_distance: float = 0.05  # 边界接近5%
    penetrate_min_depth: float = 0.0  # 穿越不设最小深度
    recovery_min_pct: float = 0.001  # 回收不设最小幅度
    holding_min_bars: int = 0  # 穿越后不要求持续
    volume_check_enabled: bool = False  # 初版不检查成交量
    volume_climax_ratio: float = 1.0
    volume_dryup_ratio: float = 999.0
    joc_holdout_bars: int = 1
    msos_window: int = 5
    msos_threshold: float = 0.01
    sow_reaction_max_bars: int = 999
    sow_consolidation_max_range: float = 999.0
    breakout: BreakoutParams = field(default_factory=BreakoutParams)
    supply_demand: SupplyDemandParams = field(default_factory=SupplyDemandParams)


@dataclass
class RuleEngineParams:
    st_confirms_min_confidence: float = 0.0
    spring_confirms_min_confidence: float = 0.0
    b_phase_min_bars: int = 0
    b_phase_timeout_bars: int = 999


@dataclass
class EngineParams:
    version: str = "default"
    range_engine: RangeEngineParams = field(default_factory=RangeEngineParams)
    event_engine: EventEngineParams = field(default_factory=EventEngineParams)
    rule_engine: RuleEngineParams = field(default_factory=RuleEngineParams)


def load_params(path: Path) -> EngineParams:
    """从JSON加载参数，文件不存在则返回默认值

    W5修复：asdict() 将嵌套 dataclass 展平为 dict，但 dataclass 构造函数
    不会自动将嵌套 dict 还原。必须显式反序列化每一层嵌套字段。
    """
    if not path.exists():
        logger.info("参数文件不存在，使用默认值: %s", path)
        return EngineParams()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        params = EngineParams(version=data.get("version", "loaded"))
        if "range_engine" in data:
            params.range_engine = RangeEngineParams(**data["range_engine"])
        if "event_engine" in data:
            ee_data = data["event_engine"]
            # 显式反序列化嵌套字段，避免 dict 残留
            nested_breakout = ee_data.pop("breakout", None)
            nested_supply_demand = ee_data.pop("supply_demand", None)
            params.event_engine = EventEngineParams(**ee_data)
            if nested_breakout is not None:
                params.event_engine.breakout = BreakoutParams(**nested_breakout)
            if nested_supply_demand is not None:
                params.event_engine.supply_demand = SupplyDemandParams(
                    **nested_supply_demand
                )
        if "rule_engine" in data:
            params.rule_engine = RuleEngineParams(**data["rule_engine"])
        return params
    except Exception as e:
        logger.warning("参数加载失败，使用默认值: %s", e)
        return EngineParams()


def save_params(params: EngineParams, path: Path) -> None:
    """保存参数到JSON"""
    path.parent.mkdir(parents=True, exist_ok=True)
    re = params.range_engine or RangeEngineParams()
    ee = params.event_engine or EventEngineParams()
    ru = params.rule_engine or RuleEngineParams()
    data = {
        "version": params.version,
        "range_engine": asdict(re),
        "event_engine": asdict(ee),
        "rule_engine": asdict(ru),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
