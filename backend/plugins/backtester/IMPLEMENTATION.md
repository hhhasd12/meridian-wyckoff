#回测框架施工文档

> 施工前必读：`backtester/README.md`（设计文档）

## 前置阅读（必须先读这些文件理解引擎接口）

1. `backend/plugins/engine/plugin.py` — 看`_on_candle()` 方法，这是K线处理流水线的真实实现
2. `backend/plugins/engine/models.py` — 数据模型：Event,EngineState, RangeContext, EventContext, PhaseTransition, CandidateExtreme, AnchorPoint
3. `backend/plugins/engine/params.py` — 参数结构：EngineParams（统一容器）, load_params()
4. `backend/plugins/engine/range_engine.py` — RangeEngine.process_bar() 签名
5. `backend/plugins/engine/event_engine.py` — EventEngine.process_bar() 签名（注意：接收 rule_engine 参数）
6. `backend/plugins/engine/rule_engine.py` — RuleEngine
7. `backend/core/types.py` — BackendPlugin 基类,PluginContext 接口
8. `backend/plugins/datasource/` — K线数据加载接口
9. `backend/plugins/annotation/` — 标注数据接口

## 引擎K线处理流水线（从 engine/plugin.py._on_candle 精确提取）

runner.py 必须完全复刻这个流程：

```python
#── engine/plugin.py._on_candle 的精确流程 ──

engine_state = self.state[symbol][tf]  # EngineState 实例
engine_state.bar_count = bar_index

# 1. 区间引擎 — 返回 RangeContext
range_ctx = self.range_engine.process_bar(candle, bar_index, engine_state)

# 2. 事件引擎（内部调用规则引擎）— 返回 EventContext
#    注意：event_engine.process_bar 接收 rule_engine 作为参数！
event_ctx = self.event_engine.process_bar(
    candle, range_ctx, bar_index, engine_state, self.rule_engine
)

# 3. 从 EventContext 更新引擎状态
engine_state.current_phase = event_ctx.current_phase
engine_state.direction = event_ctx.current_direction
engine_state.structure_type = event_ctx.structure_type
engine_state.active_range = range_ctx.active_range
engine_state.candidate_extreme = self.range_engine.candidate_extreme

# 4. 处理新检测到的事件
if event_ctx.new_events:
    for event in event_ctx.new_events:
        engine_state.recent_events.append(event)
        if len(engine_state.recent_events) > 20:
            engine_state.recent_events.pop(0)# AR事件 → 存储锚点
        if event.event_type == EventType.AR:
            engine_state.ar_anchor = AnchorPoint(
                bar_index=event.sequence_end_bar,
                extreme_price=event.price_extreme,
                body_price=event.price_body,
                volume=0,
            )
```

**关键接口差异说明：**
- `event_engine.process_bar()` 返回 `EventContext`（不是 `list[Event]`）
- `EventContext` 包含：`new_events`, `current_phase`, `current_direction`, `structure_type`, `phase_transition`
- 规则引擎不是在 plugin.py 中逐个调用的— 它被传入 event_engine，由 event_engine 内部调用
- 参数是统一的 `EngineParams`，内部包含 `range_engine`, `event_engine`, `rule_engine` 三个子参数

## 施工清单（按顺序）

### 文件0: engine/plugin.py 修改

在EnginePlugin 类中新增一个公开方法：

```python
def create_isolated_instance(self, params: EngineParams | None = None) -> dict:
    """创建隔离的引擎实例，用于回测。不注册到 self.state。

    Args:
        params: 可选。如果不传，使用当前加载的参数。

    Returns:
        {
            "range_engine": RangeEngine,
            "event_engine": EventEngine,
            "rule_engine": RuleEngine,
            "params": EngineParams,
        }
    """
    p = params or self.params
    return {
        "range_engine": RangeEngine(p.range_engine),
        "event_engine": EventEngine(p.event_engine),
        "rule_engine": RuleEngine(p.rule_engine),
        "params": p,
    }
```

注意：不返回 EngineState — 每次回测由 runner 自己创建全新的 EngineState。

### 文件 1: manifest.json

```json
{
  "name": "backtester",
  "version": "0.1.0",
  "dependencies": ["datasource", "engine", "annotation"]
}
```

### 文件 2: __init__.py

空文件。

### 文件 3: runner.py — 回测核心

```python
"""回测运行器 —逐根K线驱动引擎"""

from __future__ import annotations

import logging

from backend.plugins.engine.models import (
    AnchorPoint,
    EngineState,
    EventType,
)
from backend.plugins.engine.range_engine import RangeEngine
from backend.plugins.engine.event_engine import EventEngine
from backend.plugins.engine.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class BacktestRunner:
    def __init__(
        self,
        engine_instance: dict,
        candles: list[dict],
        symbol: str = "UNKNOWN",
        timeframe: str = "1d",
    ):
        """
        engine_instance: engine插件的create_isolated_instance() 返回值
        candles: 按时间排序的K线列表，每个 dict 至少包含 open/high/low/close/volume
        """
        self.range_engine: RangeEngine = engine_instance["range_engine"]
        self.event_engine: EventEngine = engine_instance["event_engine"]
        self.rule_engine: RuleEngine = engine_instance["rule_engine"]
        self.candles = candles
        self.symbol = symbol
        self.timeframe = timeframe

    def run(self) -> dict:
        """逐根K线运行引擎，收集所有产出。

        完全复刻 engine/plugin.py._on_candle() 的处理流程。

        Returns:
            dict:
                events: list[dict]       — 所有检测到的事件
                transitions: list[dict]  — 所有阶段转换
                timeline: list[dict]     — 每根K线的状态快照
                total_bars: int"""
        # 创建全新的 EngineState
        engine_state = EngineState(symbol=self.symbol, timeframe=self.timeframe)

        events: list[dict] = []
        transitions: list[dict] = []
        timeline: list[dict] = []

        for bar_index, candle in enumerate(self.candles):
            engine_state.bar_count = bar_index

            # ── 完全复刻 engine/plugin.py._on_candle ──

            # 1. 区间引擎
            range_ctx = self.range_engine.process_bar(
                candle, bar_index, engine_state
            )

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

            # 4. 处理事件
            if event_ctx.new_events:
                for ev in event_ctx.new_events:
                    engine_state.recent_events.append(ev)
                    if len(engine_state.recent_events) > 20:
                        engine_state.recent_events.pop(0)

                    # AR锚点
                    if ev.event_type == EventType.AR:
                        engine_state.ar_anchor = AnchorPoint(
                            bar_index=ev.sequence_end_bar,
                            extreme_price=ev.price_extreme,
                            body_price=ev.price_body,
                            volume=0,
                        )

                    events.append({
                        "event_type": ev.event_type.value,
                        "event_result": ev.event_result.value,
                        "bar_index": ev.sequence_end_bar,
                        "sequence_start_bar": ev.sequence_start_bar,
                        "sequence_length": ev.sequence_length,
                        "position_in_range": ev.position_in_range,
                        "volume_ratio": ev.volume_ratio,
                        "variant_tag": ev.variant_tag,})

            # 阶段转换
            if event_ctx.phase_transition:
                pt = event_ctx.phase_transition
                transitions.append({
                    "from_phase": pt.from_phase.value,
                    "to_phase": pt.to_phase.value,
                    "trigger_rule": pt.trigger_rule,
                    "bar_index": pt.bar_index,
                })

            # 时间线快照
            timeline.append({
                "bar_index": bar_index,
                "phase": engine_state.current_phase.value,
                "direction": (
                    engine_state.direction.value
                    if engine_state.direction else None
                ),
                "has_active_range": engine_state.active_range is not None,
                "events_this_bar": len(event_ctx.new_events) if event_ctx.new_events else 0,
            })

        logger.info(
            "回测完成: %d bars, %d events, %d transitions",
            len(self.candles), len(events), len(transitions),
        )

        return {
            "events": events,
            "transitions": transitions,
            "timeline": timeline,
            "total_bars": len(self.candles),
        }
```

### 文件 4: scorer.py — 评分系统

```python
"""回测评分 — 对比引擎输出与莱恩标注"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class BacktestScorer:
    def __init__(self, match_window: int = 3):
        """
        match_window: 事件匹配的K线容差（±N根K线内算匹配）
        """
        self.match_window = match_window

    def score(self, result: dict, annotations: list[dict]) -> dict:
        """对比回测结果和标注。

        Args:
            result: BacktestRunner.run() 的返回值
            annotations: 标注事件列表，每个 dict 至少包含:
                - event_type: str (如 "SC", "AR", "ST", "SPRING" 等)
                - bar_index: int (标注的K线位置)
                可选:
                - phase: str (标注时的阶段)

        Returns:
            dict: 评分结果
        """
        if not annotations:
            return {
                "detection_rate": 0,
                "false_positive_rate": 0,
                "phase_accuracy": 0,
                "avg_time_offset": 0,
                "matched_count": 0,
                "missed_count": 0,
                "false_positive_count": len(result.get("events", [])),
                "total_annotations": 0,
                "total_engine_events": len(result.get("events", [])),
                "matched": [],
                "missed": [],
                "false_positives": result.get("events", []),
                "note": "无标注数据，仅输出引擎原始结果",
            }

        engine_events = result.get("events", [])

        # 事件匹配
        matched, missed, false_positives = self._match_events(
            engine_events, annotations
        )

        # 各维度评分
        detection_rate = len(matched) / len(annotations) if annotations else 0
        false_positive_rate = (
            len(false_positives) / len(engine_events) if engine_events else 0
        )
        avg_offset = self._calc_avg_offset(matched)
        phase_accuracy = self._calc_phase_accuracy(
            result.get("timeline", []), annotations
        )

        return {
            "detection_rate": round(detection_rate, 4),
            "false_positive_rate": round(false_positive_rate, 4),
            "phase_accuracy": round(phase_accuracy, 4),
            "avg_time_offset": round(avg_offset, 2),
            "matched_count": len(matched),
            "missed_count": len(missed),
            "false_positive_count": len(false_positives),
            "total_annotations": len(annotations),
            "total_engine_events": len(engine_events),
            "matched": matched,
            "missed": missed,
            "false_positives": false_positives,
        }

    def _match_events(
        self,
        engine_events: list[dict],
        annotations: list[dict],
    ) -> tuple[list, list, list]:
        """匹配引擎事件和标注事件。

        匹配规则：
        - 事件类型相同
        - 时间窗口内（|ann.bar_index - eng.bar_index| <= match_window）
        - 一个标注最多匹配一个引擎事件（最近优先）
        - 一个引擎事件最多匹配一个标注
        """
        matched = []
        used_engine = set()
        used_annotation = set()

        for ai, ann in enumerate(annotations):
            best_ei = None
            best_offset = self.match_window + 1

            for ei, eng in enumerate(engine_events):
                if ei in used_engine:
                    continue
                if eng.get("event_type", "") != ann.get("event_type", ""):
                    continue
                offset = abs(
                    eng.get("bar_index", 0) - ann.get("bar_index", 0)
                )
                if offset <= self.match_window and offset < best_offset:
                    best_ei = ei
                    best_offset = offset

            if best_ei is not None:
                matched.append({
                    "annotation": ann,
                    "engine_event": engine_events[best_ei],
                    "offset": best_offset,
                })
                used_engine.add(best_ei)
                used_annotation.add(ai)

        missed = [
            ann for ai, ann in enumerate(annotations)
            if ai not in used_annotation
        ]
        false_positives = [
            eng for ei, eng in enumerate(engine_events)
            if ei not in used_engine
        ]

        return matched, missed, false_positives

    def _calc_avg_offset(self, matched: list) -> float:
        if not matched:
            return 0.0
        return sum(m["offset"] for m in matched) / len(matched)

    def _calc_phase_accuracy(
        self, timeline: list[dict], annotations: list[dict]
    ) -> float:
        """阶段准确率：标注中有phase 字段的，对比引擎在该时间点的阶段。"""
        phase_anns = [a for a in annotations if "phase" in a]
        if not phase_anns:
            return 0.0

        correct = 0
        for ann in phase_anns:
            bar = ann.get("bar_index", 0)
            if0 <= bar < len(timeline):
                if timeline[bar].get("phase", "") == ann.get("phase", ""):
                    correct += 1

        return correct / len(phase_anns)
```

### 文件 5: plugin.py — 插件入口

```python
"""回测插件 — 引擎验证与进化评分"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.core.types import BackendPlugin, PluginContext
from .runner import BacktestRunner
from .scorer import BacktestScorer
from .routes import create_router

logger = logging.getLogger(__name__)


class BacktesterPlugin(BackendPlugin):
    id = "backtester"
    name = "Backtester"
    version = "0.1.0"
    dependencies = ("datasource", "engine", "annotation")

    def __init__(self):
        self.ctx: PluginContext | None = None

    async def on_init(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        logger.info("回测插件初始化完成")

    async def on_start(self) -> None:
        logger.info("回测插件启动")

    async def on_stop(self) -> None:
        logger.info("回测插件停止")

    def get_router(self) -> APIRouter:
        return create_router(self)

    def get_subscriptions(self) -> dict:
        return {}  # 回测插件不订阅事件

    async def health_check(self) -> dict:
        return {"status": "healthy"}

    async def run_backtest(
        self,
        symbol: str,
        timeframe: str,
        params=None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict:
        """运行一次回测。

        步骤：
        1. 从 datasource 插件获取K线数据
        2. 从 engine 插件创建隔离引擎实例
        3.逐根K线运行引擎
        4. 返回回测结果

        注意：datasource 和 annotation 插件的实际接口需要确认。
        施工时先读取这两个插件的代码，确认公开方法。
        如果没有合适的公开方法，需要新增。
        """
        # 获取K线数据
        # TODO: 确认 datasource 插件的实际接口
        #可能的方式：
        #   datasource = self.ctx.get_plugin("datasource")
        #   candles = datasource.load_candles(symbol, timeframe)
        # 或者直接从文件加载

        # 创建隔离引擎实例
        engine_plugin = self.ctx.get_plugin("engine")
        instance = engine_plugin.create_isolated_instance(params)

        # 运行回测
        runner = BacktestRunner(instance, candles, symbol, timeframe)
        result = runner.run()

        return result

    async def score_result(
        self,
        result: dict,
        symbol: str,
        timeframe: str,
    ) -> dict:
        """对回测结果评分（vs标注）。"""
        # TODO: 确认 annotation 插件的实际接口
        # 可能的方式：
        #   annotation = self.ctx.get_plugin("annotation")
        #   annotations = annotation.get_drawings(symbol, timeframe)
        # 然后转换为 scorer 期望的格式

        annotations = []# TODO: 从 annotation 插件获取

        scorer = BacktestScorer()
        return scorer.score(result, annotations)
```

### 文件 6: routes.py — API 端点

```python
"""回测API 端点"""

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
        run_id = str(uuid.uuid4())[:8]
        results_dir = Path(plugin.ctx.storage.base_path) / "backtester" / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        output = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "result": result,
            "score": score,
        }

        result_file = results_dir / f"{run_id}.json"
        result_file.write_text(
            json.dumps(output, indent=2, ensure_ascii=False)
        )

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
        results_dir = Path(plugin.ctx.storage.base_path) / "backtester" / "results"
        result_file = results_dir / f"{run_id}.json"

        if not result_file.exists():
            return {"error": f"Result {run_id} not found"}

        return json.loads(result_file.read_text())

    @router.get("/history")
    async def list_history():
        """历史回测列表"""
        results_dir = Path(plugin.ctx.storage.base_path) / "backtester" / "results"
        if not results_dir.exists():
            return {"runs": []}

        runs = []
        for f in sorted(results_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                runs.append({
                    "run_id": data.get("run_id"),
                    "symbol": data.get("symbol"),
                    "timeframe": data.get("timeframe"),
                    "total_bars": data.get("result", {}).get("total_bars", 0),
                    "total_events": len(data.get("result", {}).get("events", [])),
                    "score_summary": {
                        "detection_rate": data.get("score", {}).get("detection_rate", 0),
                        "false_positive_rate": data.get("score", {}).get("false_positive_rate", 0),
                    },
                })
            except Exception:
                continue

        return {"runs": runs}

    return router
```

## 关键约束

1. **runner.py 的K线循环必须和 engine/plugin.py._on_candle() 完全一致**。特别注意：
   - `event_engine.process_bar()` 接收 5 个参数（candle, range_ctx, bar_index, engine_state, rule_engine）
   - 返回 `EventContext`，不是 `list[Event]`
   - 状态更新从 `event_ctx` 读取，不是手动 apply transition

2. **import 路径**：参照其他插件的 import 方式。当前引擎插件用 `from backend.core.types import BackendPlugin, PluginContext`。

3. **datasource 和 annotation 的实际接口**：plugin.py 中标了 TODO。施工前必须先读取这两个插件的代码确认。

4. **K线数据格式**：引擎期望 dict 至少包含 `open, high, low, close, volume`。

5. **路由注册**：参照 engine 插件，用 `get_router()` 返回 `APIRouter`，内核会自动注册到 `/api/backtester/` 前缀下。

6. **EngineState 由 runner创建**：`create_isolated_instance()` 不返回 EngineState。runner 在 `run()` 方法中创建全新的 `EngineState(symbol=..., timeframe=...)`。