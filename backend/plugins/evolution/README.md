# Evolution Plugin —设计文档

> **角色定位**：Meridian 的学习系统。从莱恩的标注中提取规律，优化引擎参数，让引擎逐步逼近莱恩的判断标准。

---

## §1 进化插件是什么

进化插件回答一个问题：**莱恩的标注中蕴含了什么规律？如何让引擎逼近莱恩的判断标准？**

核心闭环：**标注 → EventCase → 案例库(SQLite) → 统计优化 → 新参数 → 引擎热加载 → 更精准的候选 → 莱恩确认/修正 → 循环**

进化插件不做的事：

- 不做机器学习/神经网络 — 初版用统计分析（百分位数、中位数）
- 不实时优化 — 莱恩手动触发"运行进化"
- 不修改引擎代码 — 只修改引擎的参数 JSON

---

## §2 核心设计决策

| 编号 | 决策 | 依据 |
|------|------|------|
| EVD-1 | EventCase 由进化插件生成，不由annotation 生成 | annotation 只管存画图，进化插件负责"理解"画图的含义 |
| EVD-2 | SQLite 为案例库主存储 | MD-3 架构决策；案例需要复杂查询（按类型/阶段/结果筛选） |
| EVD-3 | 参数优化用统计方法（百分位数），不用 ML | 标注数据量初期极少（几十到几百条），统计方法更稳健 |
| EVD-4 | 热加载通过事件总线 `evolution.params_updated` | 引擎已实现订阅此事件（engine/plugin.py `_on_params_updated`） |
| EVD-5 | 修正案例权重 ×3 | 莱恩修正引擎错误 = 最高价值的学习信号 |
| EVD-6 | 负样本（REJECTED）参与优化，作为排除边界 | V3：失败/否定同样完整记录，这是进化燃料 |
| EVD-7 | 参数版本化，每次优化产生新版本，可回滚 | 安全网：优化后效果变差可以一键回退 |
| EVD-8 | 最少 3 个成功案例才优化该参数 | 防止1-2 个极端案例扭曲参数 |
| EVD-9 | 安全系数×1.2/×0.8 | 宁可宽松不漏报（RD-55 精神延续） |

---

## §3 与 V3 的关系

| V3 概念 | 进化插件实现 |
|---------|-------------|
| 记忆层四库 | event_cases 表（事件案例库）+ evolution_runs 表（规则日志）+ params_history 表。交易记录库归trading插件 |
| 进化四层分离 | 不变层= 引擎代码不动；参数层 = params.json 优化；变体层/策略层 = P2+ |
| 渐进路径 ①先记录 | 初版：只记录 EventCase，手动触发优化 |
| 渐进路径 ②手动变体 | P2：variant_tag 字段支持莱恩手动标记变体 |
| 渐进路径 ③数据驱动发现 | P3：聚类算法自动发现变体 |
| 渐进路径 ④相似度检索 | P3：新K 线到达时检索最相似历史案例 |
| EventCase 结构 | 完整继承 V3 §4.5：event +区间快照 + K线序列 + 后续结果 |

---

## §4 EventCase 生命周期

### 路径 A：标注驱动（主路径）

```
莱恩在工作台标注事件（callout 气泡标"SC"）│▼
annotation插件保存 Drawing + 自动提取 7 维特征
  │  publish: annotation.created {symbol, timeframe, label, points, ...}
  ▼
evolution 插件订阅 annotation.created
  │
  ├──从datasource 获取 K 线数据
  ├── 定位事件 K 线位置（points[0].time → bar_index）
  ├── 提取 K 线窗口：pre_bars(20根) + sequence_bars + post_bars(20根)
  ├── 提取市场上下文：趋势斜率、均量基准、区间位置
  ├── 从 engine 获取当前状态：phase, direction, active_range
  ├── 组装 EventCase
  └── 写入 SQLite event_cases 表
       source = "annotation", weight = 1.0
```

### 路径 B：修正驱动（高价值）

```
引擎自动检测到事件 → 前端半透明显示
  │
  ▼
莱恩发现引擎标错→ 手动修正（删除/移动/重新标注）
  │  publish: annotation.updated / annotation.deleted
  ▼
evolution 插件检测差异
  │
  ├── 引擎标注 vs 莱恩修正 → 对比
  ├── 引擎的错误标注 → EventCase(result=REJECTED, source="correction")
  ├── 莱恩的正确标注 → EventCase(result=SUCCESS, source="correction")
  └── 两条都写入 SQLite，weight = 3.0（EVD-5）
```

### 路径 C：引擎自动记录（辅助）

```
engine.event_detected 事件到达
  │
  ▼
evolution 插件订阅 engine.event_detected
  │
  ├── 如果该事件已有对应的莱恩标注 → 跳过（避免重复）
  ├── 如果没有莱恩标注 → 记录为PENDING 案例
  └── 写入 SQLite，source = "engine", weight = 0.5
```

---

## §5 SQLite Schema

文件位置：`storage/evolution/meridian.db`

```sql
CREATE TABLE event_cases (
    id                TEXT PRIMARY KEY,
    event_type          TEXT NOT NULL,       -- sc/bc/ar/st/spring/...
    event_result        TEXT NOT NULL,       -- success/failed/rejected/pending
    symbol              TEXT NOT NULL,
    timeframe           TEXT NOT NULL,

    -- 时序定位
    sequence_start_barINTEGER,
    sequence_end_bar    INTEGER,
    sequence_length     INTEGER,

    -- 价格特征（7维）
    price_extremeREAL,
    price_body          REAL,
    penetration_depth   REAL,               -- |price - boundary| / channel_width
    recovery_speed      REAL,
    position_in_range   REAL,               -- 0=下沿, 1=上沿
    volume_ratio        REAL,               -- 当根量/ 基准均量
    effort_vs_result    REAL,               -- clamp(efficiency-1, -1, +1)

    -- 上下文特征
    trend_slope         REAL,               -- 前序趋势斜率
    trend_length        INTEGER,            -- 前序趋势长度(根)
    support_distance    REAL,               -- 距最近支撑%wick_ratio          REAL,               -- 下影线占比
    body_position       REAL,               -- 实体在K线中的位置

    -- 区间上下文
    range_id            TEXT,
    phase               TEXT,
    direction           TEXT,
    structure_type      TEXT,
    range_width         REAL,               -- 区间宽度%

    -- K线快照（JSON数组）
    pre_bars            TEXT,               -- 事件前20根 [{t,o,h,l,c,v}, ...]
    sequence_bars       TEXT,               -- 事件本身K线序列
    post_bars           TEXT,               -- 事件后20根

    -- 后续结果
    result_5barREAL,               -- 5根后价格变动%
    result_10bar        REAL,
    result_20bar        REAL,

    -- 来源与权重
    source              TEXT NOT NULL,       -- annotation / engine / correction
    drawing_id          TEXT,               -- 关联的标注 ID
    annotation_label    TEXT,               -- 莱恩标注的文本
    weight              REAL DEFAULT 1.0,
    params_version      TEXT,               -- 产生此案例时的参数版本

    -- 变体（P2）
    variant_tag         TEXT,               -- 莱恩手动标记的变体名

    -- 元数据
    created_at          TEXT NOT NULL,
    notesTEXT
);

CREATE INDEX idx_cases_type ON event_cases(event_type);
CREATE INDEX idx_cases_result ON event_cases(event_result);
CREATE INDEX idx_cases_symbol_tf ON event_cases(symbol, timeframe);

CREATE TABLE evolution_runs (
    id                      TEXT PRIMARY KEY,
    started_at              TEXT NOT NULL,
    completed_at            TEXT,
    status                  TEXT DEFAULT 'running',  -- running/completed/failed
    cases_used              INTEGER,
    params_version_before   TEXT,
    params_version_after    TEXT,
    params_diffTEXT,               -- JSON: {param: {before, after, cases_count}}
    notes                   TEXT
);

CREATE TABLE params_history (
    versionTEXT PRIMARY KEY,
    params_jsonTEXT NOT NULL,           -- 完整 EngineParams JSON
    created_at      TEXT NOT NULL,
    source          TEXT,-- default / evolution_run_id / manual
    notes           TEXT
);
```

---

## §6 参数优化算法

核心思路：**从莱恩确认的案例中，统计"什么参数值能捕获所有成功案例、同时排除尽量多的失败案例"。**

### 6.1 优化流程

```python
def optimize(cases: list[dict], current_params: EngineParams) -> EngineParams:
    new_params = copy(current_params)

    # 按事件类型分组
    grouped = group_by(cases, key="event_type")

    for event_type, type_cases in grouped.items():
        success = [c for c in type_cases if c["event_result"] == "success"]
        rejected = [c for c in type_cases if c["event_result"] == "rejected"]

        if len(success) < 3:
            continue  # EVD-8: 样本太少，不优化

        # 提取特征分布→ 计算参数阈值
        mapping = PARAM_MAPPINGS.get(event_type, [])
        for param_name, feature_name, direction, percentile in mapping:
            values = weighted_values(success, feature_name)

            if direction == "upper_bound":
                # 参数是上限（如 st_max_distance_pct）
                # 取成功案例的高百分位 × 安全系数
                threshold = np.percentile(values, percentile) * 1.2  # EVD-9
            elif direction == "lower_bound":
                # 参数是下限（如 bounce_min_move_pct）
                # 取成功案例的低百分位 × 安全系数
                threshold = np.percentile(values, 100 - percentile) * 0.8  # EVD-9

            # EVD-6: 负样本排除检查
            if rejected:rej_values = [c[feature_name] for c in rejected if c.get(feature_name) is not None]
                if rej_values:
                    false_positive_rate = count_within(rej_values, threshold, direction) / len(rejected)
                    if false_positive_rate > 0.3:
                        # 在success 和 rejected 之间找分界点
                        threshold = find_separation_point(values, rej_values, direction)

            set_param(new_params, param_name, threshold)

    return new_params
```

### 6.2 参数 ↔ 特征映射表（PARAM_MAPPINGS）

```python
PARAM_MAPPINGS = {
    "st": [
        # (参数名, 特征名, 方向, 百分位)
        ("range_engine.st_max_distance_pct", "penetration_depth", "upper_bound", 95),
        ("event_engine.volume_dryup_ratio", "volume_ratio", "upper_bound", 90),
    ],
    "ar": [
        ("range_engine.ar_min_bounce_pct", "bounce_magnitude", "lower_bound", 95),
        ("range_engine.ar_min_bars", "sequence_length", "lower_bound", 90),
    ],
    "spring": [
        ("event_engine.approach_distance", "approach_distance", "upper_bound", 90),
        ("event_engine.penetrate_min_depth", "penetration_depth", "lower_bound", 90),
        ("event_engine.recovery_min_pct", "recovery_speed", "lower_bound", 90),],
    "sc": [
        ("event_engine.volume_climax_ratio", "volume_ratio", "lower_bound", 85),
    ],
    "bc": [
        ("event_engine.volume_climax_ratio", "volume_ratio", "lower_bound", 85),
    ],
}
```

### 6.3 加权值计算

```python
def weighted_values(cases: list[dict], feature_name: str) -> list[float]:
    """提取特征值，按权重重复（weight=3的案例重复3次）"""
    result = []
    for case in cases:
        val = case.get(feature_name)
        if val is not None:
            weight = int(case.get("weight", 1))
            result.extend([val] * max(1, weight))
    return result
```

---

## §7 数据流

### 7.1 学习期（进化工作台）

```
annotation.created ──→ evolution._on_annotation_created
                │
                          ├─ datasource.get_candles_df()
                          ├─ engine.get_state()
                          ├─ case_builder.build_case()
                          └─ case_store.insert(case)

POST /api/evolution/run ──→ evolution.run_optimization()
                              │
                              ├─ case_store.query(min_cases=3)
                              ├─ optimizer.optimize(cases, current_params)
                              ├─ params_manager.save_version(new_params)
                              ├─ case_store.insert_run(run_record)
                              └─ event_bus.publish("evolution.params_updated")│
                                    ▼
                              engine._on_params_updated()
                                    └─ 热加载新参数
```

### 7.2 运行期（实盘）

```
engine.event_detected ──→ evolution._on_engine_event│
                              ├─检查是否已有对应标注
                              ├─ 无标注 → 记录 PENDING 案例
                              └─ case_store.insert(case)

annotation.updated ──→ evolution._on_annotation_updated
                          │
                          ├─ 查找对应的engine案例
                          ├─ 对比差异 → 生成 correction 案例
                          └─ case_store.insert(correction_case, weight=3.0)
```

---

## §8 插件交互

### 订阅事件

| 事件 | 来源 | 处理 |
|------|------|------|
| `annotation.created` | annotation | 构建 EventCase →存入案例库 |
| `annotation.updated` | annotation | 更新案例 / 生成修正案例 |
| `annotation.deleted` | annotation | 标记案例为 REJECTED |
| `engine.event_detected` | engine | 记录引擎自动检测的候选案例 |
| `engine.range_created` | engine | 注册到历史区间索引 |

### 发布事件

| 事件 | 数据 | 消费者 |
|------|------|--------|
| `evolution.params_updated` | `{version, path}` | engine（热加载） |
| `evolution.case_created` | `{case_id, event_type}` | dashboard（统计更新） |
| `evolution.run_completed` | `{run_id, improvements}` | dashboard（进度通知） |

### 依赖插件

| 插件 | 类型 | 用途 |
|------|------|------|
| datasource | 必须 | `get_candles_df()` 获取 K 线数据构建案例 |
| annotation | 必须 | 标注事件驱动案例生成 |
| engine | 必须 | `get_state()` 获取引擎状态上下文 +参数热加载 |

---

## §9 API 端点

```
# 案例管理
GET/api/evolution/cases                → 案例列表（支持 ?event_type=sc&result=success 筛选）
GET    /api/evolution/cases/{case_id}           → 案例详情
GET    /api/evolution/cases/stats               → 按类型统计（数量/成功率/平均特征）
DELETE /api/evolution/cases/{case_id}           → 删除案例

# 进化运行
POST   /api/evolution/run                → 触发参数优化
GET    /api/evolution/runs→ 历史运行记录
GET    /api/evolution/runs/{run_id}             → 运行详情（含params_diff）

# 参数管理
GET    /api/evolution/params/current→ 当前参数
GET    /api/evolution/params/history            → 参数版本历史
POST   /api/evolution/params/rollback/{version} → 回滚到指定版本
POST   /api/evolution/params/manual→ 手动修改参数
```

---

## §10 文件结构

```
backend/plugins/evolution/
├── __init__.py
├── manifest.json           # 插件元数据 + dependencies
├── plugin.py               # EvolutionPlugin 入口（事件订阅 + 生命周期）
├── case_builder.py         # annotation → EventCase 转换（特征提取 + K线窗口）
├── case_store.py           # SQLite CRUD（event_cases + evolution_runs + params_history）
├── optimizer.py            # 统计优化算法（百分位数 + 负样本排除）
├── params_manager.py       # 参数版本管理（save/load/rollback/publish）
├── routes.py               # API 路由
└── README.md               # 本设计文档
```

---

## §11 施工顺序

```
1. case_store.py— SQLite 初始化 + 三表创建 + CRUD
                init_db() / insert_case / query_cases / get_stats             insert_run / update_run
                             insert_params / get_latest_params

2. case_builder.py         — build_case(annotation_event, candles_df, engine_state) → dict
                             K线窗口切割（前20根 / 序列 / 后20根）
                             特征提取（复用 annotation/feature_extractor 的逻辑）
                             后续结果填充（5/10/20 bar）

3. optimizer.py            — optimize(cases, current_params) → new_params
                             PARAM_MAPPINGS 配置表
                             百分位数计算 + 安全系数
                             负样本排除检查
                             生成 params_diff 报告

4. params_manager.py       — save_version(params, source) → version_id
                             load_latest() → EngineParams
                             rollback(version) → EngineParams
                             复用 engine/params.py 的 save_params/load_params

5. plugin.py               — EvolutionPlugin(BackendPlugin)
                             on_init: 初始化 SQLite
                             get_subscriptions: 5个事件
                             _on_annotation_created: 调用 case_builder → case_store
                             _on_annotation_updated: 修正案例检测
                             _on_annotation_deleted: 标记 REJECTED
                             _on_engine_event: 记录 PENDING 案例
                             run_optimization: 调用 optimizer → params_manager → publish

6. routes.py               — 12 个 API 端点

7. manifest.json           — dependencies: ["datasource", "annotation", "engine"]

8. __init__.py             — 空文件
```

---

## §12 验收标准

1. **案例写入**：标注一个 SC → evolution自动生成 EventCase → SQLite 中可查到
2. **特征完整**：EventCase 的 7 维价格特征 + K线快照 + 后续结果全部填充
3. **优化运行**：3+ 个 SC 案例后运行优化 → 生成新参数版本 → params_diff 非空
4. **引擎热加载**：优化完成后 engine 收到 `evolution.params_updated` → 参数版本更新
5. **版本回滚**：回滚到旧版本 → engine 加载旧参数 → 验证参数值
6. **修正权重**：修正案例 weight=3.0 → 优化时特征值重复 3 次
7. **负样本排除**：有REJECTED 案例时→ 优化结果不同于无 REJECTED 时
8. **API 可用**：12 个端点全部返回正确JSON

---

## 附录：设计决策汇总

| 编号 | 决策 | 来源 |
|------|------|------|
| EVD-1 | EventCase 由 evolution 生成 | 职责分离原则 |
| EVD-2 | SQLite 主存储 | MD-3 |
| EVD-3 | 统计优化（非ML） | 数据量约束 |
| EVD-4 | 事件总线热加载 | 引擎已实现 |
| EVD-5 | 修正案例 weight=3.0 | V3 §7.3 |
| EVD-6 | 负样本参与优化 | V3 §9|
| EVD-7 | 参数版本化 + 可回滚 | 安全网|
| EVD-8 | 最少 3 个成功案例 | 防过拟合 |
| EVD-9 | 安全系数 ×1.2/×0.8 | RD-55 |

---

> **文档版本**: v1.0
> **作者**: WyckoffInspector
> **日期**: 2026-04-08
> **状态**: 待莱恩审阅 → 确认后写施工提示词