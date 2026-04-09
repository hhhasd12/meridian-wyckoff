#回测框架设计文档

## §1 定位

回测框架是引擎的验证工具。把历史K线逐根喂给引擎，收集产出的事件和阶段转换，和莱恩的标注对比，输出量化评分。

两种使用场景：
1. **手动回测**：莱恩触发，查看引擎在某段历史行情上的检测结果
2. **进化回测**：进化系统自动调用，给定参数→回测→返回评分→参数优化

## §2 核心原则

- **隔离性**：每次回测创建独立的引擎实例，不影响实时引擎状态
- **可重复性**：相同参数 + 相同数据 = 相同结果
- **评分驱动**：回测的最终产出是一个可量化的评分，进化系统用它来优化参数

## §3 数据流

```
历史K线（datasource插件）
│
▼
┌─────────────────────────┐
│  BacktestRunner          │
│                          │
│  for each candle:│
│    range_engine.process()│
│    event_engine.process()│
│    rule_engine.evaluate()│
│    collect events│
│    collect transitions   │
└─────────────────────────┘
│
▼
┌─────────────────────────┐
│  BacktestResult│
│  - events[]│
│  - transitions[]         │
│  - ranges[]              │
│  - timeline[]            │
└─────────────────────────┘
│
▼
┌─────────────────────────┐
│  Scorer（可选）           │
│  BacktestResult          │
│    vs                    │
│  莱恩标注（annotation）   │
│    =                     │
│  量化评分                │
└─────────────────────────┘
```

## §4 设计决策

### BD-1: 回测是独立后端插件
路径：`backend/plugins/backtester/`
依赖：`datasource`（K线数据）、`engine`（引擎类）、`annotation`（标注数据，评分时用）

### BD-2: 引擎实例通过工厂方法创建
回测器不直接 import 引擎内部类。engine 插件暴露一个公开方法：

```python
# engine/plugin.py 新增
def create_isolated_instance(self, params=None) -> dict:
    """创建隔离的引擎实例，用于回测。
    返回 {range_engine, event_engine, rule_engine, engine_state}
    """
```

回测器通过 `ctx.get_plugin("engine").create_isolated_instance(params)` 获取。
好处：回测器不依赖引擎内部结构，引擎重构不影响回测器。

### BD-3: 评分标准（需莱恩确认）

提议的评分维度：

| 维度 | 含义 | 计算方式 |
|------|------|----------|
| 检出率 | 标注的事件，引擎检测到了多少 | 匹配事件数 / 标注事件总数 |
| 误报率 | 引擎产出但标注中没有的事件 | 误报数 / 引擎事件总数 |
| 阶段准确率 | 在每个时间点，引擎的阶段判断是否正确 | 正确阶段K线数 / 总K线数 |
| 时间偏差 | 事件检测的时间和标注的时间差多少根K线 | 平均偏差（越小越好） |

综合评分 = 加权平均（权重也是进化参数）。

**问莱恩**：这四个维度够吗？你觉得"好的检测"应该怎么衡量？

### BD-4: 事件匹配规则（需莱恩确认）

引擎事件和标注事件怎么算"匹配"？提议：
- 事件类型相同
- 时间窗口内（±N根K线，N是参数，初始值=3）
- 一个标注最多匹配一个引擎事件（最近优先）

### BD-5: 单次回测范围
- 单币种 + 单时间框架
- 时间范围：全部可用数据，或指定起止时间
- 多TF回测：分别运行，各自评分

## §5 文件结构

```
backend/plugins/backtester/
├── manifest.json       # 插件元数据
├── plugin.py# BackendPlugin 接口 + 生命周期
├── runner.py           # 回测运行器（核心循环）
├── scorer.py           # 评分系统（vs标注对比）
├── routes.py# REST API 端点
└── __init__.py
```

## §6 核心模块

### runner.py — 回测运行器

```python
class BacktestRunner:
    def __init__(self, engine_instance: dict, candles: list[dict]):
        """
        engine_instance: engine插件的create_isolated_instance()返回值
        candles: 按时间排序的K线列表
        """
        self.range_engine = engine_instance["range_engine"]
        self.event_engine = engine_instance["event_engine"]
        self.rule_engine = engine_instance["rule_engine"]
        self.engine_state = engine_instance["engine_state"]
        self.candles = candles

    def run(self) -> BacktestResult:
        """逐根K线运行引擎，收集所有产出"""
        events = []
        transitions = []

        for i, candle in enumerate(self.candles):
            # 1. 区间引擎处理
            range_events = self.range_engine.process_bar(candle, i,...)

            # 2. 事件引擎处理
            detected_events = self.event_engine.process_bar(candle, i, ...)

            # 3. 规则引擎评估
            all_events = range_events + detected_events
            for event in all_events:
                transition = self.rule_engine.evaluate(event,...)
                if transition:
                    transitions.append(transition)

            events.extend(all_events)return BacktestResult(
            events=events,
            transitions=transitions,
            ranges=self.range_engine.get_all_ranges(),
            engine_state=self.engine_state,
        )
```

### scorer.py — 评分系统

```python
class BacktestScorer:
    def __init__(self, match_window: int = 3):
        self.match_window = match_window# 事件匹配的K线容差

    def score(
        self,
        result: BacktestResult,
        annotations: list[dict],
    ) -> BacktestScore:
        """对比回测结果和标注，计算评分"""

        # 1. 事件匹配
        matched, missed, false_positives = self._match_events(
            result.events, annotations
        )

        # 2. 计算各维度分数
        detection_rate = len(matched) / len(annotations) if annotations else 0
        false_positive_rate = (
            len(false_positives) / len(result.events) if result.events else 0
        )
        avg_time_offset = self._calc_avg_offset(matched)

        # 3. 阶段准确率（需要标注中有阶段信息）
        phase_accuracy = self._calc_phase_accuracy(result, annotations)

        return BacktestScore(
            detection_rate=detection_rate,
            false_positive_rate=false_positive_rate,
            phase_accuracy=phase_accuracy,
            avg_time_offset=avg_time_offset,
            matched_events=matched,
            missed_events=missed,
            false_positives=false_positives,
        )
```

## §7 API 端点

```
POST /api/backtester/run
  body: { symbol, timeframe, params?, start_time?, end_time? }
  返回: { run_id, status }

GET /api/backtester/result/{run_id}
  返回: BacktestResult + BacktestScore

GET /api/backtester/history
  返回: 历史回测列表（run_id, 时间, 币种, 评分摘要）
```

## §8 进化系统集成

进化系统调用回测的接口：

```python
# evolution/optimizer.py 中
def _evaluate_params(self, params: dict) -> float:
    """用回测评分作为参数优化的适应度函数"""
    backtester = self.ctx.get_plugin("backtester")

    # 用候选参数创建引擎实例
    engine = self.ctx.get_plugin("engine")
    instance = engine.create_isolated_instance(params)

    # 运行回测
    result = backtester.run_backtest(
        engine_instance=instance,
        symbol=self.symbol,
        timeframe=self.timeframe,
    )

    # 评分
    score = backtester.score_result(result, self.annotations)

    # 返回综合评分作为适应度
    return score.composite_score
```

## §9 施工顺序

1. **manifest.json** — 插件元数据（依赖 datasource, engine, annotation）
2. **engine/plugin.py 修改** — 新增 `create_isolated_instance()` 工厂方法
3. **runner.py** — 回测核心循环（最重要的文件）
4. **scorer.py** — 评分系统
5. **plugin.py** — 插件入口 + 生命周期
6. **routes.py** — API 端点
7. **验证** — 用现有K线数据跑一次，确认事件产出

## §10 注意事项

- runner.py 的K线循环必须和 engine/plugin.py 的 `_on_candle()` 逻辑保持一致。如果 plugin.py 的处理流程变了，runner.py 也要同步更新。
- 评分系统在没有标注数据时也能运行——只是不计算对比分数，只输出引擎的原始检测结果。
- 回测结果存储用JSON 文件（和标注一样），路径：`data/backtester/results/{run_id}.json`
- 初版不做并行优化。单次回测是同步的，进化系统串行调用。