# 引擎插件施工提示词

> 给代码agent的施工指南 | 2026-04-08
> 首席架构师：WyckoffInspector

---

## 1. 项目背景

Meridian 是一个插件化威科夫分析框架。当前P0骨架已完成（core/ + datasource/ + annotation/），现在施工引擎插件。

**引擎的角色**：不是自动检测器，是学习框架。引擎的智慧来自用户的标注，不来自预设规则。初版极宽松——标记候选，不做判断。后续通过标注进化收紧参数。

## 2. 必读文档

| 文档 | 路径 | 读什么 |
|------|------|--------|
| 引擎设计 | backend/plugins/engine/README.md | 角色定位、三子引擎职责、进化参数清单 |
| V3理论 | docs/SYSTEM_DESIGN_V3.md §4 | 数据结构定义（Range/Event/EventCase） |
| 核心类型 | backend/core/types.py | BackendPlugin接口、PluginContext |
| 现有插件参考 | backend/plugins/datasource/ | manifest.json格式、插件结构参考 |

## 3. 当前代码状态

```
backend/
├── core/           ✅ 已完成（types/storage/event_bus/plugin_manager/main）
├── plugins/
│   ├── datasource/ ✅ 已完成（CSV加载 + Polars + 二进制传输）
│   ├── annotation/ ✅ 已完成（Drawing CRUD + 7维特征提取）
│   └── engine/     🔧 本次施工
│       ├── detectors/  （空目录，已创建）
│       └── README.md   （设计文档，已写入）
```

## 4. 施工目标

引擎插件能加载、启动、接收K线、输出引擎状态。初版所有检测极宽松。

## 5. 文件清单（14个文件）

```
backend/plugins/engine/
├── manifest.json          # ① 插件元数据
├── __init__.py            # ② 包初始化
├── models.py              # ③ 数据结构（核心，最先写）
├── params.py              # ④ 进化参数定义 + 默认值
├── plugin.py              # ⑤ 插件入口（BackendPlugin实现）
├── range_engine.py        # ⑥ 区间引擎
├── event_engine.py        # ⑦ 事件引擎
├── rule_engine.py         # ⑧ 规则引擎
├── routes.py              # ⑨ API路由
├── detectors/
│   ├── __init__.py        # ⑩
│   ├── base_detector.py   # ⑪ 检测器基类
│   ├── extreme_event.py   # ⑫ SC/BC候选（模板3）
│   ├── bounce.py          # ⑬ AR检测（模板4）
│   └── boundary_test.py   # ⑭ ST/Spring/UTAD等（模板1）
└── README.md              （已有，不用改）
```

## 6. 施工顺序与代码骨架

###① manifest.json

```json
{"id": "engine", "name": "威科夫引擎", "version": "0.1.0", "entry": "plugin.py"}
```

注意：manifest格式参考datasource插件。dependencies在BackendPlugin类中声明，不在manifest中。annotation是可选依赖（运行时通过get_plugin获取）。

### ② __init__.py

空文件。

### ③ models.py — 数据结构

这是最核心的文件，定义引擎的所有数据类型。全部用dataclass + Enum。

```python
"""引擎数据模型 — 从V3设计文档 §4 继承"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


#═══ 枚举 ═══

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
    RE_DISTRIBUTION = "re_distribution"UNKNOWN = "unknown"

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

class EventResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


# ═══ 基础结构 ═══

@dataclass
class AnchorPoint:
    bar_index: int
    extreme_price: float      # 影线极值
    body_price: float         # 实体收盘
    volume: float
    timestamp: int =0        # 毫秒时间戳

@dataclass
class TrendLine:
    slope: float              # 斜率（水平=0）
    intercept: float          # 截距
    anchor_points: list[AnchorPoint] = field(default_factory=list)
    r_squared: float = 0.0def price_at(self, bar_index: int) -> float:
        return self.slope * bar_index + self.intercept


# ═══ 核心结构 ═══

@dataclass
class CandidateExtreme:
    """SC/BC候选 — 同一时间只保留一个"""
    candidate_type: str       # "SC" or "BC"
    bar_index: int
    extreme_price: float
    body_price: float
    volume: float
    volume_ratio: float       # 相对趋势均量
    confidence: float = 0.0   # 初版全部为0（无预设评分）
    replaced_by: Optional[str] = None

@dataclass
class Range:
    range_id: str
    timeframe: str
    channel_slope: float = 0.0
    channel_width: float = 0.0
    primary_anchor_1: Optional[AnchorPoint] = None# SC/BC
    primary_anchor_2: Optional[AnchorPoint] = None  # ST
    opposite_anchor: Optional[AnchorPoint] = None   # AR
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
    recent_events: list[Event] = field(default_factory=list)
    params_version: str = "default"
    bar_count: int = 0
```

### ④ params.py — 进化参数

```python
"""进化参数 — 所有检测条件的阈值，初版极宽松"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RangeEngineParams:
    ar_min_bounce_pct: float = 0.01# AR最小反弹1%
    ar_min_bars: int = 1                   # AR最少1根K线
    st_max_distance_pct: float = 0.20# ST与SC最大距离20%
    st_max_volume_ratio: float = 999.0    # ST成交量不限制
    range_min_width_pct: float = 0.01     # 区间最小宽度1%
    reentry_threshold: float = 0.5
    confirmation_bars: int = 1
    max_breakout_age: int = 999

@dataclass
class EventEngineParams:
    approach_distance: float = 0.05       # 边界接近5%
    penetrate_min_depth: float = 0.0# 穿越不设最小深度
    recovery_min_pct: float = 0.001# 回收不设最小幅度
    holding_min_bars: int = 0             # 穿越后不要求持续
    volume_check_enabled: bool = False# 初版不检查成交量
    volume_climax_ratio: float = 1.0
    volume_dryup_ratio: float = 999.0
    joc_holdout_bars: int = 1
    msos_window: int = 5
    msos_threshold: float = 0.01
    sow_reaction_max_bars: int = 999
    sow_consolidation_max_range: float = 999.0

@dataclass
class RuleEngineParams:
    st_confirms_min_confidence: float = 0.0
    spring_confirms_min_confidence: float = 0.0
    b_phase_min_bars: int = 0
    b_phase_timeout_bars: int = 999

@dataclass
class EngineParams:
    version: str = "default"
    range_engine: RangeEngineParams = None
    event_engine: EventEngineParams = None
    rule_engine: RuleEngineParams = None

    def __post_init__(self):
        if self.range_engine is None:
            self.range_engine = RangeEngineParams()
        if self.event_engine is None:
            self.event_engine = EventEngineParams()
        if self.rule_engine is None:
            self.rule_engine = RuleEngineParams()


def load_params(path: Path) -> EngineParams:
    """从JSON加载参数，文件不存在则返回默认值"""
    if not path.exists():
        logger.info("参数文件不存在，使用默认值: %s", path)
        return EngineParams()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        params = EngineParams(version=data.get("version", "loaded"))
        if "range_engine" in data:
            params.range_engine = RangeEngineParams(**data["range_engine"])
        if "event_engine" in data:
            params.event_engine = EventEngineParams(**data["event_engine"])
        if "rule_engine" in data:
            params.rule_engine = RuleEngineParams(**data["rule_engine"])
        return params
    except Exception as e:
        logger.warning("参数加载失败，使用默认值: %s", e)
        return EngineParams()


def save_params(params: EngineParams, path: Path) -> None:
    """保存参数到JSON"""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": params.version,
        "range_engine": asdict(params.range_engine),
        "event_engine": asdict(params.event_engine),
        "rule_engine": asdict(params.rule_engine),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

这个文件可以直接使用，不需要大改。

### ⑤ plugin.py — 插件入口

```python
"""引擎插件入口"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter

from backend.core.types import BackendPlugin, PluginContext
from .models import (
    EngineState, Direction, Phase, StructureType,
    CandidateExtreme, RangeContext, EventContext,
)
from .params import EngineParams, load_params
from .range_engine import RangeEngine
from .event_engine import EventEngine
from .rule_engine import RuleEngine
from .routes import create_router

logger = logging.getLogger(__name__)


class EnginePlugin(BackendPlugin):
    id = "engine"
    name = "Wyckoff Engine"
    version = "0.1.0"
    dependencies = ("datasource",)

    def __init__(self):
        self.ctx: PluginContext | None = None
        self.params =EngineParams()
        self.range_engine: RangeEngine | None = None
        self.event_engine: EventEngine | None = None
        self.rule_engine: RuleEngine | None = None
        self.state: dict[str, dict[str, EngineState]] = {}
        # state[symbol][timeframe] = EngineState
        self.running = False

    async def on_init(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        # 加载进化参数
        params_path = ctx.storage.base_path / "evolution" / "params_latest.json"
        self.params = load_params(params_path)
        # 初始化三引擎
        self.range_engine = RangeEngine(self.params.range_engine)
        self.event_engine = EventEngine(self.params.event_engine)
        self.rule_engine = RuleEngine(self.params.rule_engine)
        logger.info("引擎插件初始化完成，参数版本: %s", self.params.version)

    async def on_start(self) -> None:
        self.running = True
        logger.info("引擎插件启动")

    async def on_stop(self) -> None:
        self.running = False
        logger.info("引擎插件停止")

    def get_router(self) -> APIRouter:
        return create_router(self)

    def get_subscriptions(self) -> dict:
        return {
            "candle.new": self._on_candle,
            "evolution.params_updated": self._on_params_updated,
        }

    async def _on_candle(self, data: dict) -> None:
        """每根K线到达时触发"""
        if not self.running:
            return
        symbol = data.get("symbol", "")
        tf = data.get("timeframe", "")
        candle = data.get("candle", {})
        bar_index = data.get("bar_index", 0)

        # 确保state存在
        if symbol not in self.state:
            self.state[symbol] = {}
        if tf not in self.state[symbol]:
            self.state[symbol][tf] = EngineState(symbol=symbol, timeframe=tf)

        engine_state = self.state[symbol][tf]
        engine_state.bar_count = bar_index

        # 1. 区间引擎
        range_ctx = self.range_engine.process_bar(candle, bar_index, engine_state)

        # 2. 事件引擎（内部调用规则引擎）
        event_ctx = self.event_engine.process_bar(
            candle, range_ctx, bar_index, engine_state, self.rule_engine
        )

        # 3. 更新引擎状态
        engine_state.current_phase = event_ctx.current_phase
        engine_state.direction = event_ctx.current_direction
        engine_state.structure_type = event_ctx.structure_type
        engine_state.active_range = range_ctx.active_range
        engine_state.candidate_extreme = self.range_engine.candidate_extreme

        # 4. 发布事件
        if event_ctx.new_events:
            for event in event_ctx.new_events:
                engine_state.recent_events.append(event)
                # 保留最近20个事件
                if len(engine_state.recent_events) > 20:
                    engine_state.recent_events.pop(0)
                await self.ctx.event_bus.publish("engine.event_detected", {
                    "symbol": symbol, "timeframe": tf, "event": event
                })

        if event_ctx.phase_transition:
            await self.ctx.event_bus.publish("engine.phase_changed", {
                "symbol": symbol, "timeframe": tf,
                "phase": event_ctx.current_phase.value,
                "direction": event_ctx.current_direction.value,})

    async def _on_params_updated(self, data: dict) -> None:
        """进化参数更新时重新加载"""
        params_path = self.ctx.storage.base_path / "evolution" / "params_latest.json"
        self.params = load_params(params_path)
        self.range_engine.params = self.params.range_engine
        self.event_engine.params = self.params.event_engine
        self.rule_engine.params = self.params.rule_engine
        logger.info("引擎参数已更新: %s", self.params.version)

    def get_state(self, symbol: str, tf: str) -> EngineState:
        """获取指定标的和周期的引擎状态"""
        return self.state.get(symbol, {}).get(tf, EngineState(symbol=symbol, timeframe=tf))

    def get_all_states(self, symbol: str) -> dict[str, EngineState]:
        """获取指定标的所有周期的状态"""
        return self.state.get(symbol, {})
```

### ⑥ range_engine.py — 区间引擎

```python
"""区间引擎 — 场域基础设施"""

from __future__ import annotations

import logging
import uuid

from .models import (
    RangeContext, Range, RangeStatus, Phase, Direction, RangeShape,
    CandidateExtreme, AnchorPoint, Event, EventType, EventResult,
    EngineState,
)
from .params import RangeEngineParams

logger = logging.getLogger(__name__)


class RangeEngine:
    def __init__(self, params: RangeEngineParams):
        self.params = params
        self.candidate_extreme: CandidateExtreme | None = None
        self.archived_ranges: list[Range] = []
        #趋势均量追踪
        self._trend_volume_sum: float = 0.0
        self._trend_volume_count: int = 0

    def process_bar(
        self, candle: dict, bar_index: int, engine_state: EngineState
    ) -> RangeContext:
        """
        每根K线调用一次。

        核心逻辑：
        1. 没有活跃区间 →寻找SC/BC候选 + 检测AR + 检测ST
        2. 有活跃区间 → 更新位置 + 更新形状 + 检测边界事件
        """
        ctx = RangeContext()
        active = engine_state.active_range

        if active is None:
            # ─── 趋势运行中：寻找新区间 ───
            self._update_trend_volume(candle)
            self._seek_candidate(candle, bar_index, engine_state, ctx)
        else:
            # ─── 有活跃区间：更新状态 ───
            ctx.has_active_range = True
            ctx.active_range = active
            active.duration_bars = bar_index - active.created_at_bar
            self._update_position(candle, active, ctx)
            if active.current_phase == Phase.B:
                self._update_range_shape(candle, bar_index, active)self._update_creek_ice(candle, bar_index, active)

        return ctx

    def _seek_candidate(
        self, candle: dict, bar_index: int,
        engine_state: EngineState, ctx: RangeContext
    ) -> None:
        """趋势中寻找SC/BC候选"""
        direction = engine_state.direction
        is_sc = direction in (Direction.SHORT, Direction.NEUTRAL)

        extreme = candle.get("low", 0) if is_sc else candle.get("high", 0)

        # 每个新低/新高都是候选（ED-2：零门槛）
        is_new_extreme = False
        if self.candidate_extreme is None:
            is_new_extreme = True
        elif is_sc and extreme < self.candidate_extreme.extreme_price:
            is_new_extreme = True
        elif not is_sc and extreme > self.candidate_extreme.extreme_price:
            is_new_extreme = True

        if is_new_extreme:
            trend_avg_vol = self._get_trend_avg_volume()
            vol_ratio = candle.get("volume", 0) / trend_avg_vol if trend_avg_vol > 0 else 1.0

            new_candidate = CandidateExtreme(
                candidate_type="SC" if is_sc else "BC",
                bar_index=bar_index,
                extreme_price=extreme,
                body_price=candle.get("close", extreme),
                volume=candle.get("volume", 0),
                volume_ratio=vol_ratio,
                confidence=0.0,  # 初版不评分)

            # 替换旧候选
            if self.candidate_extreme is not None:
                self.candidate_extreme.replaced_by = new_candidate.candidate_type
                # TODO: 旧候选存入记忆层

            self.candidate_extreme = new_candidate# 创建SC/BC事件传递给事件引擎
            event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.SC if is_sc else EventType.BC,
                event_result=EventResult.PENDING,
                sequence_start_bar=bar_index,
                sequence_end_bar=bar_index,
                sequence_length=1,
                price_extreme=extreme,
                price_body=candle.get("close", extreme),
                volume_ratio=vol_ratio,
            )
            ctx.pending_events.append(event)

    def _update_position(self, candle: dict, active: Range, ctx: RangeContext) -> None:
        """计算价格在区间中的位置"""
        if active.channel_width <= 0:
            return
        price = candle.get("close", 0)
        # 简化版：用锚点价格计算（完整版用趋势线）
        lower = active.primary_anchor_1.extreme_price if active.primary_anchor_1 else 0
        upper = active.opposite_anchor.extreme_price if active.opposite_anchor else 0
        if upper <= lower:
            return
        ctx.position_in_range = (price - lower) / (upper - lower)
        ctx.distance_to_lower = abs(price - lower) / lower if lower > 0 else 0
        ctx.distance_to_upper = abs(price - upper) / upper if upper > 0 else 0

    def _update_trend_volume(self, candle: dict) -> None:
        """更新趋势均量"""
        vol = candle.get("volume", 0)
        self._trend_volume_sum += vol
        self._trend_volume_count += 1

    def _get_trend_avg_volume(self) -> float:
        if self._trend_volume_count == 0:
            return 1.0
        return self._trend_volume_sum / self._trend_volume_count

    def _update_range_shape(self, candle: dict, bar_index: int, active: Range) -> None:
        """阶段B：更新区间形状（拟合趋势线）"""
        # TODO: 收集ST-B高低点 →拟合趋势线 → 更新slope
        pass

    def _update_creek_ice(self, candle: dict, bar_index: int, active: Range) -> None:
        """阶段B：更新Creek/Ice"""
        # TODO: 收集反弹高点/回调低点 → 拟合趋势线
        pass

    def create_range(
        self, sc_bc: CandidateExtreme, ar: AnchorPoint, st: AnchorPoint,entry_trend: Direction
    ) -> Range:
        """三点定区间：SC/BC + AR + ST → 创建Range"""
        is_sc = sc_bc.candidate_type == "SC"
        primary1 = AnchorPoint(
            bar_index=sc_bc.bar_index,
            extreme_price=sc_bc.extreme_price,
            body_price=sc_bc.body_price,
            volume=sc_bc.volume,)

        # 计算通道
        slope = (st.extreme_price - primary1.extreme_price) / max(1, st.bar_index - primary1.bar_index)
        width = abs(ar.extreme_price - primary1.extreme_price)

        # 判断形状
        if abs(slope) < 0.0001:
            shape = RangeShape.HORIZONTAL
        elif slope > 0:
            shape = RangeShape.ASCENDING
        else:
            shape = RangeShape.DESCENDING

        return Range(
            range_id=str(uuid.uuid4()),
            timeframe="",# 由plugin设置
            channel_slope=slope,
            channel_width=width,
            primary_anchor_1=primary1,
            primary_anchor_2=st,
            opposite_anchor=ar,
            entry_trend=entry_trend,
            range_shape=shape,
            status=RangeStatus.CONFIRMED,
            created_at_bar=primary1.bar_index,
            confirmed_at_bar=st.bar_index,
            current_phase=Phase.B,)
```

### ⑦ event_engine.py — 事件引擎

```python
"""事件引擎 — 检测器调度+ 规则引擎调用"""

from __future__ import annotations

import logging

from .models import (
    RangeContext, EventContext, Event, EventResult,
    Phase, Direction, StructureType, EngineState,
)
from .params import EventEngineParams
from .rule_engine import RuleEngine
from .detectors.base_detector import BaseDetector
from .detectors.extreme_event import ExtremeEventDetector
from .detectors.bounce import BounceDetector
from .detectors.boundary_test import BoundaryTestDetector

logger = logging.getLogger(__name__)


class EventEngine:
    def __init__(self, params: EventEngineParams):
        self.params = params
        self.detectors: list[BaseDetector] = [
            ExtremeEventDetector(),
            BounceDetector(),
            BoundaryTestDetector(),
        ]

    def process_bar(
        self, candle: dict, range_ctx: RangeContext, bar_index: int,
        engine_state: EngineState, rule_engine: RuleEngine,
    ) -> EventContext:
        """每根K线调用一次"""
        ctx = EventContext(
            current_phase=engine_state.current_phase,
            current_direction=engine_state.direction,
            structure_type=engine_state.structure_type,
        )

        # 收集所有事件（区间引擎传递的 + 检测器发现的）
        all_events = list(range_ctx.pending_events)

        # 运行检测器
        for detector in self.detectors:
            detected = detector.process_bar(
                candle, range_ctx, bar_index, self.params, engine_state
            )
            if detected:
                all_events.extend(detected)

        # 每个事件送规则引擎评估
        for event in all_events:
            transition = rule_engine.evaluate(event, range_ctx, engine_state)
            if transition:
                ctx.phase_transition = transition
                ctx.current_phase = transition.to_phase
                ctx.current_direction = transition.direction_after
                engine_state.current_phase = transition.to_phase
                engine_state.direction = transition.direction_afterctx.new_events.append(event)

        return ctx
```

### ⑧ rule_engine.py — 规则引擎

```python
"""规则引擎 —阶段转换路径图+ 方向管理"""

from __future__ import annotations

import logging

from .models import (
    Event, EventType, EventResult, Phase, Direction,
    StructureType, PhaseTransition, RangeContext, EngineState,
)
from .params import RuleEngineParams

logger = logging.getLogger(__name__)


class RuleEngine:
    def __init__(self, params: RuleEngineParams):
        self.params = params
        self.rule_log: list[dict] = []

    def evaluate(
        self, event: Event, range_ctx: RangeContext,
        engine_state: EngineState,
    ) -> PhaseTransition | None:
        """评估事件是否触发阶段转换"""
        phase = engine_state.current_phase
        direction = engine_state.directionetype = event.event_type

        transition = None

        # ─── SC/BC →设置初始方向 ───
        if etype == EventType.SC:
            engine_state.direction = Direction.SHORT
            engine_state.current_phase = Phase.A
            self._log("SC_sets_direction", event, phase, Phase.A)

        elif etype == EventType.BC:
            engine_state.direction = Direction.LONG
            engine_state.current_phase = Phase.A
            self._log("BC_sets_direction", event, phase, Phase.A)

        # ─── ST确认 → A到B ───
        elif etype == EventType.ST and phase == Phase.A:
            if event.event_result == EventResult.SUCCESS:
                transition = PhaseTransition(
                    from_phase=Phase.A, to_phase=Phase.B,
                    trigger_event_id=event.event_id,
                    trigger_rule="ST_confirms_range",
                    bar_index=event.sequence_end_bar,
                    direction_before=direction,
                    direction_after=direction,
                )
                self._log("ST_confirms_range", event, Phase.A, Phase.B)

        # ─── Spring/SO成功 → C确认 →进入D ───
        elif etype in (EventType.SPRING, EventType.SO) and phase in (Phase.B, Phase.C):
            if event.event_result == EventResult.SUCCESS:
                new_dir = self._apply_direction_switch(engine_state, "spring")
                transition = PhaseTransition(
                    from_phase=phase, to_phase=Phase.D,
                    trigger_event_id=event.event_id,
                    trigger_rule="Spring_confirms_direction",
                    bar_index=event.sequence_end_bar,
                    direction_before=direction,
                    direction_after=new_dir,
                )
                engine_state.direction_confirmed = True
                self._log("Spring_confirms", event, phase, Phase.D)

        # ─── UTAD成功 → C确认 → 进入D ───
        elif etype == EventType.UTAD and phase in (Phase.B, Phase.C):
            if event.event_result == EventResult.SUCCESS:
                new_dir = self._apply_direction_switch(engine_state, "utad")
                transition = PhaseTransition(
                    from_phase=phase, to_phase=Phase.D,
                    trigger_event_id=event.event_id,
                    trigger_rule="UTAD_confirms_direction",
                    bar_index=event.sequence_end_bar,
                    direction_before=direction,
                    direction_after=new_dir,
                )
                engine_state.direction_confirmed = True
                self._log("UTAD_confirms", event, phase, Phase.D)

        # ─── JOC/跌破冰线 → D到E ───
        elif etype in (EventType.JOC, EventType.BREAK_ICE) and phase == Phase.D:
            transition = PhaseTransition(
                from_phase=Phase.D, to_phase=Phase.E,
                trigger_event_id=event.event_id,
                trigger_rule="JOC_starts_trend",
                bar_index=event.sequence_end_bar,
                direction_before=direction,
                direction_after=direction,
            )
            self._log("JOC_starts_trend", event, Phase.D, Phase.E)

        # ───假突破回归 → E退回B ───
        elif etype == EventType.FALSE_BREAKOUT_RETURN and phase == Phase.E:
            transition = PhaseTransition(
                from_phase=Phase.E, to_phase=Phase.B,
                trigger_event_id=event.event_id,
                trigger_rule="false_breakout_recovery",
                bar_index=event.sequence_end_bar,
                direction_before=direction,
                direction_after=direction,notes="JOC标记FAILED，方向不变",
            )
            self._log("false_breakout", event, Phase.E, Phase.B)

        return transition

    def _apply_direction_switch(self, state: EngineState, event_kind: str) -> Direction:
        """阶段C方向开关 — V3§2.3"""
        entry = state.active_range.entry_trend if state.active_range else state.direction

        if event_kind == "spring":
            if entry == Direction.SHORT:
                state.structure_type = StructureType.ACCUMULATION
                return Direction.LONG
            else:
                state.structure_type = StructureType.RE_ACCUMULATION
                return Direction.LONG

        elif event_kind == "utad":
            if entry == Direction.LONG:
                state.structure_type = StructureType.DISTRIBUTION
                return Direction.SHORT
            else:
                state.structure_type = StructureType.RE_DISTRIBUTION
                return Direction.SHORT

        return state.direction

    def _log(self, rule: str, event: Event, from_p: Phase, to_p: Phase) -> None:
        self.rule_log.append({
            "rule": rule,
            "event_type": event.event_type.value,
            "from_phase": from_p.value,
            "to_phase": to_p.value,
            "bar_index": event.sequence_end_bar,
        })
```

### ⑪ detectors/base_detector.py

```python
"""检测器基类"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Event, RangeContext, EngineState
from ..params import EventEngineParams


class BaseDetector(ABC):
    @abstractmethod
    def process_bar(
        self, candle: dict, range_ctx: RangeContext,
        bar_index: int, params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        """返回本根K线检测到的事件列表（可为空）"""
        ...
```

### ⑫ detectors/extreme_event.py — SC/BC候选

```python
"""模板3：极端事件型— SC/BC候选检测"""

from __future__ import annotations

from ..models import Event, RangeContext, EngineState
from ..params import EventEngineParams
from .base_detector import BaseDetector


class ExtremeEventDetector(BaseDetector):
    """
    SC/BC候选由区间引擎直接处理（range_engine._seek_candidate）。
    本检测器作为扩展点保留，初版不额外处理。
    """

    def process_bar(
        self, candle: dict, range_ctx: RangeContext,
        bar_index: int, params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        # SC/BC候选已由区间引擎通过pending_events传递
        return []
```

### ⑬ detectors/bounce.py — AR检测

```python
"""模板4：反弹回落型 — AR检测"""

from __future__ import annotations

import uuid

from ..models import (
    Event, EventType, EventResult, RangeContext,EngineState, Phase, Direction,
)
from ..params import EventEngineParams
from .base_detector import BaseDetector


class BounceDetector(BaseDetector):
    """
    AR检测：SC/BC之后的反弹。
    初版极宽松：任何方向相反的价格运动都可能是AR。
    """

    def __init__(self):
        self._tracking = False
        self._bounce_start_bar: int =0
        self._bounce_start_price: float = 0.0
        self._bounce_peak: float = 0.0
        self._bounce_bars: int = 0

    def process_bar(
        self, candle: dict, range_ctx: RangeContext,
        bar_index: int, params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        # 只在有候选SC/BC且无活跃区间时检测AR
        if range_ctx.has_active_range:
            return []

        candidate = engine_state.candidate_extreme
        if candidate is None:
            return []

        # 已经有AR了就不重复检测
        if engine_state.current_phase != Phase.A:
            return []

        is_sc = candidate.candidate_type == "SC"
        close = candle.get("close", 0)
        high = candle.get("high", 0)
        low = candle.get("low", 0)

        if not self._tracking:
            # 开始追踪反弹
            if is_sc and close > candidate.extreme_price:
                self._tracking = True
                self._bounce_start_bar = bar_index
                self._bounce_start_price = candidate.extreme_price
                self._bounce_peak = high
                self._bounce_bars = 1
            elif not is_sc and close < candidate.extreme_price:
                self._tracking = True
                self._bounce_start_bar = bar_index
                self._bounce_start_price = candidate.extreme_price
                self._bounce_peak = low
                self._bounce_bars = 1
            return []

        # 追踪中
        self._bounce_bars += 1

        if is_sc:
            if high > self._bounce_peak:
                self._bounce_peak = high
            # 反弹结束检测：价格开始回落
            if close < self._bounce_peak * 0.98:  # 从峰值回落2%视为AR结束
                bounce_pct = abs(self._bounce_peak - self._bounce_start_price) / self._bounce_start_price
                if (bounce_pct >= params.ar_min_bounce_pct and
                    self._bounce_bars >= params.ar_min_bars):
                    self._tracking = False
                    return [Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.AR,
                        event_result=EventResult.SUCCESS,
                        sequence_start_bar=self._bounce_start_bar,
                        sequence_end_bar=bar_index,
                        sequence_length=self._bounce_bars,
                        price_extreme=self._bounce_peak,
                        price_body=close,
                    )]
        else:
            if low < self._bounce_peak:
                self._bounce_peak = low
            if close > self._bounce_peak * 1.02:
                bounce_pct = abs(self._bounce_peak - self._bounce_start_price) / self._bounce_start_price
                if (bounce_pct >= params.ar_min_bounce_pct and
                    self._bounce_bars >= params.ar_min_bars):
                    self._tracking = False
                    return [Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.AR,
                        event_result=EventResult.SUCCESS,
                        sequence_start_bar=self._bounce_start_bar,
                        sequence_end_bar=bar_index,
                        sequence_length=self._bounce_bars,
                        price_extreme=self._bounce_peak,
                        price_body=close,
                    )]

        return []
```

### ⑭ detectors/boundary_test.py — 边界测试型

```python
"""模板1：边界测试型 — ST/Spring/UTAD/ST-B等"""

from __future__ import annotations

import uuid

from ..models import (
    Event, EventType, EventResult, RangeContext,
    EngineState, Phase, Direction,
)
from ..params import EventEngineParams
from .base_detector import BaseDetector


class BoundaryTestDetector(BaseDetector):
    """
    边界测试检测：价格接近/穿越区间边界后回收。
    初版极宽松：任何边界接近都标记。

    状态机：IDLE → APPROACHING → PENETRATING → RECOVERING → CONFIRMED/FAILED
    """

    def __init__(self):
        self._state = "IDLE"
        self._test_type: EventType | None = None
        self._start_bar: int = 0
        self._penetrate_price: float = 0.0

    def process_bar(
        self, candle: dict, range_ctx: RangeContext,
        bar_index: int, params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        if not range_ctx.has_active_range:
            return []

        active = range_ctx.active_range
        if active is None:
            return []

        close = candle.get("close", 0)
        low = candle.get("low", 0)
        high = candle.get("high", 0)

        lower = active.primary_anchor_1.extreme_price if active.primary_anchor_1 else 0
        upper = active.opposite_anchor.extreme_price if active.opposite_anchor else 0

        if lower <= 0 or upper <= 0 or upper <= lower:
            return []

        events = []

        # ─── 下边界测试（ST/Spring/SO） ───
        if range_ctx.distance_to_lower <= params.approach_distance:
            if low <= lower:  # 穿越下边界
                if close > lower:  # 收回= 成功
                    test_type = self._classify_lower_test(active, engine_state)
                    events.append(Event(
                        event_id=str(uuid.uuid4()),
                        event_type=test_type,
                        event_result=EventResult.SUCCESS,
                        sequence_start_bar=bar_index,
                        sequence_end_bar=bar_index,
                        sequence_length=1,
                        price_extreme=low,
                        price_body=close,
                        penetration_depth=abs(low - lower) / (upper - lower) if upper > lower else 0,
                        position_in_range=range_ctx.position_in_range,
                        range_id=active.range_id,
                        phase=active.current_phase,
                    ))

        # ─── 上边界测试（UT/UTA/UTAD） ───
        if range_ctx.distance_to_upper <= params.approach_distance:
            if high >= upper:  # 穿越上边界
                if close < upper:  # 收回 = 成功
                    test_type = self._classify_upper_test(active, engine_state)
                    events.append(Event(
                        event_id=str(uuid.uuid4()),
                        event_type=test_type,
                        event_result=EventResult.SUCCESS,
                        sequence_start_bar=bar_index,
                        sequence_end_bar=bar_index,
                        sequence_length=1,
                        price_extreme=high,
                        price_body=close,
                        penetration_depth=abs(high - upper) / (upper - lower) if upper > lower else 0,
                        position_in_range=range_ctx.position_in_range,
                        range_id=active.range_id,
                        phase=active.current_phase,
                    ))

        return events

    def _classify_lower_test(self, active, engine_state) -> EventType:
        """根据阶段分类下边界测试类型"""
        phase = active.current_phase
        if phase == Phase.A:
            return EventType.ST
        elif phase == Phase.B:
            return EventType.ST_B  # 简化：B阶段前期用ST_B
        elif phase in (Phase.B, Phase.C):
            return EventType.SPRING
        elif phase == Phase.D:
            return EventType.LPS
        return EventType.ST_B

    def _classify_upper_test(self, active, engine_state) -> EventType:
        """根据阶段分类上边界测试类型"""
        phase = active.current_phase
        if phase == Phase.B:
            return EventType.UTA
        elif phase in (Phase.B, Phase.C):
            return EventType.UTAD
        elif phase == Phase.D:
            return EventType.LPSY
        return EventType.UT
```

### ⑨ routes.py — API路由

```python
"""引擎API路由"""

from __future__ import annotations

from fastapi import APIRouter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin importEnginePlugin


def create_router(engine: EnginePlugin) -> APIRouter:
    router = APIRouter()

    @router.get("/state/{symbol}/{tf}")
    async def get_state(symbol: str, tf: str):
        state = engine.get_state(symbol, tf)
        return _serialize_state(state)

    @router.get("/state/{symbol}/all")
    async def get_all_states(symbol: str):
        states = engine.get_all_states(symbol)
        return {tf: _serialize_state(s) for tf, s in states.items()}

    @router.get("/ranges/{symbol}")
    async def get_ranges(symbol: str):
        # TODO: 从记忆层读取
        return []

    @router.get("/events/{symbol}")
    async def get_events(symbol: str):
        states = engine.get_all_states(symbol)
        all_events = []
        for s in states.values():
            all_events.extend(s.recent_events)
        return [_serialize_event(e) for e in all_events]

    return router


def _serialize_state(state) -> dict:
    return {
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "current_phase": state.current_phase.value,
        "structure_type": state.structure_type.value,
        "direction": state.direction.value,
        "confidence": state.confidence,
        "active_range": None,  # TODO: 序列化Range
        "bar_count": state.bar_count,
        "params_version": state.params_version,
        "recent_events": [_serialize_event(e) for e in state.recent_events[-10:]],
    }

def _serialize_event(event) -> dict:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "event_result": event.event_result.value,
        "start_bar": event.sequence_start_bar,
        "end_bar": event.sequence_end_bar,
        "price_extreme": event.price_extreme,
        "confidence": event.confidence,
    }
```

## 7. 设计约束

1. **所有文件头部**：`from __future__ import annotations`
2. **日志**：用`logging`，不用 `print`
3. **ID生成**：`uuid.uuid4()`
4. **参数**：所有检测条件的阈值从 `params` 读取，不硬编码
5. **初版不检查成交量**：`volume_check_enabled` 默认 `False`
6. **import路径**：`from backend.core.types import ...`，`from .models import ...`
7. **异步**：plugin.py的事件处理器是async，引擎内部是同步
8. **storage路径**：通过 `ctx.storage.base_path` 获取

## 8. 验收标准

1. ✅ 后端启动，engine插件自动发现并注册（日志可见）
2. ✅ `GET /api/system/plugins` 返回engine插件信息
3. ✅ `GET /api/engine/state/ETHUSDT/1d` 返回EngineState JSON
4. ✅ 参数文件不存在时使用默认值，不报错
5. ✅ 参数文件存在时正确加载
6. ✅ models.py中所有dataclass可正常实例化
7. ✅ 引擎接收candle.new事件后处理不报错
8. ✅ 零标注数据时引擎正常运行（极宽松模式）

---

> 施工完成后通知WyckoffInspector审查。