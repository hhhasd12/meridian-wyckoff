"""引擎数据模型 — 从V3设计文档 §4 继承"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ═══ 枚举 ═══


class RangeStatus(Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    BROKEN = "broken"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class Phase(Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class StructureType(Enum):
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    RE_ACCUMULATION = "re_accumulation"
    RE_DISTRIBUTION = "re_distribution"
    UNKNOWN = "unknown"


class Direction(Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class RangeShape(Enum):
    HORIZONTAL = "horizontal"
    ASCENDING = "ascending"
    DESCENDING = "descending"


class EventType(Enum):
    SC = "sc"
    BC = "bc"
    AR = "ar"
    ST = "st"
    ST_B = "st_b"
    UT = "ut"
    UTA = "uta"
    SPRING = "spring"
    SO = "so"
    UTAD = "utad"
    LPS = "lps"
    LPSY = "lpsy"
    BU = "bu"
    SOS = "sos"
    SOW = "sow"
    JOC = "joc"
    BREAK_ICE = "break_ice"
    MSOS = "msos"
    MSOW = "msow"
    MSOS_TREND = "msos_trend"
    MSOW_TREND = "msow_trend"
    PS = "ps"
    PSY = "psy"
    FALSE_BREAKOUT_RETURN = "false_breakout_return"
    BREAKOUT_CANDIDATE = "breakout_candidate"
    BREAKOUT_CONFIRMED = "breakout_confirmed"
    BREAKOUT_FAILED = "breakout_failed"
    SUPPLY_DEMAND_SIGNAL = "supply_demand_signal"


class EventResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


# ═══ 基础结构 ═══


@dataclass
class AnchorPoint:
    bar_index: int
    extreme_price: float  # 影线极值
    body_price: float  # 实体收盘
    volume: float
    timestamp: int = 0  # 毫秒时间戳


@dataclass
class TrendLine:
    slope: float  # 斜率（水平=0）
    intercept: float  # 截距
    anchor_points: list[AnchorPoint] = field(default_factory=list)
    r_squared: float = 0.0

    def price_at(self, bar_index: int) -> float:
        return self.slope * bar_index + self.intercept


# ═══ 核心结构 ═══


@dataclass
class CandidateExtreme:
    """SC/BC候选 — 同一时间只保留一个"""

    candidate_type: str  # "SC" or "BC"
    bar_index: int
    extreme_price: float
    body_price: float
    volume: float
    volume_ratio: float  # 相对趋势均量
    confidence: float = 0.0  # 初版全部为0（无预设评分）
    replaced_by: Optional[str] = None


@dataclass
class Range:
    range_id: str
    timeframe: str
    channel_slope: float = 0.0
    channel_width: float = 0.0
    primary_anchor_1: Optional[AnchorPoint] = None  # SC/BC
    primary_anchor_2: Optional[AnchorPoint] = None  # ST
    opposite_anchor: Optional[AnchorPoint] = None  # AR
    entry_trend: Direction = Direction.NEUTRAL
    range_shape: RangeShape = RangeShape.HORIZONTAL
    creek: Optional[TrendLine] = None
    ice: Optional[TrendLine] = None
    status: RangeStatus = RangeStatus.CANDIDATE
    created_at_bar: int = 0
    confirmed_at_bar: Optional[int] = None
    broken_at_bar: Optional[int] = None
    current_phase: Phase = Phase.A
    structure_type: StructureType = StructureType.UNKNOWN
    direction_confirmed: bool = False
    phase_c_skipped: bool = False
    strength_score: float = 0.0
    duration_bars: int = 0
    test_count: int = 0
    last_test_bar: Optional[int] = None
    parent_range_id: Optional[str] = None
    child_range_ids: list[str] = field(default_factory=list)
    fib_levels: dict[float, float] = field(default_factory=dict)
    fib_reference_price: float = 0.0
    fib_extreme_price: float = 0.0


@dataclass
class Event:
    event_id: str
    event_type: EventType
    event_result: EventResult = EventResult.PENDING
    sequence_start_bar: int = 0
    sequence_end_bar: int = 0
    sequence_length: int = 0
    volume_ratio: float = 0.0
    volume_pattern: str = "normal"
    effort_vs_result: float = 0.0
    price_extreme: float = 0.0
    price_body: float = 0.0
    penetration_depth: float = 0.0
    recovery_speed: float = 0.0
    range_id: str = ""
    phase: Phase = Phase.A
    position_in_range: float = 0.0
    confidence: float = 0.0
    variant_tag: Optional[str] = None
    variant_features: dict = field(default_factory=dict)


# ═══ 上下文与输出 ═══


@dataclass
class RangeContext:
    has_active_range: bool = False
    active_range: Optional[Range] = None
    range_just_created: bool = False  # 本根K线刚创建区间，跳过检测器
    position_in_range: float = 0.0
    distance_to_lower: float = 0.0
    distance_to_upper: float = 0.0
    nearby_support: list[Range] = field(default_factory=list)
    nearby_resistance: list[Range] = field(default_factory=list)
    range_shape: Optional[RangeShape] = None
    creek_price: Optional[float] = None
    ice_price: Optional[float] = None
    pending_events: list[Event] = field(default_factory=list)


@dataclass
class PhaseTransition:
    from_phase: Phase
    to_phase: Phase
    trigger_event_id: str
    trigger_rule: str
    bar_index: int
    direction_before: Direction = Direction.NEUTRAL
    direction_after: Direction = Direction.NEUTRAL
    notes: str = ""


@dataclass
class EventContext:
    new_events: list[Event] = field(default_factory=list)
    phase_transition: Optional[PhaseTransition] = None
    current_phase: Phase = Phase.A
    current_direction: Direction = Direction.NEUTRAL
    structure_type: StructureType = StructureType.UNKNOWN


@dataclass
class EngineState:
    """引擎对外输出的完整状态"""

    symbol: str = ""
    timeframe: str = ""
    current_phase: Phase = Phase.A
    structure_type: StructureType = StructureType.UNKNOWN
    direction: Direction = Direction.NEUTRAL
    confidence: float = 0.0
    active_range: Optional[Range] = None
    candidate_extreme: Optional[CandidateExtreme] = None
    ar_anchor: Optional[AnchorPoint] = None
    recent_events: list[Event] = field(default_factory=list)
    params_version: str = "default"
    direction_confirmed: bool = False
    bar_count: int = 0
