# 引擎插件（WyckoffEngine）

> 设计文档 v1.0 | 2026-04-08
> 基于 SYSTEM_DESIGN_V3.md 理论框架 + 标注驱动进化方法论

---

## 1. 引擎是什么

引擎是 Meridian 的识别层— 它回答一个问题：**市场现在在什么状态？**

但引擎不是自动检测器。引擎的智慧来自莱恩的标注，不来自预设规则。

**角色定位：场域感知器 + 学习框架**

- 场域感知器：追踪价格在区间中的位置、区间的生命周期、阶段的转换
- 学习框架：从莱恩的标注中学习"什么条件下状态A转换到状态B"
- 初版极宽松：标记候选，不做判断。莱恩的标注就是过滤器
- 进化后逐步收紧：标注积累 → 参数优化 → 候选更精准 → 噪音减少

**引擎不做的事：**

- 不预设SC/BC的检测规则（置信度来自案例库检索，不来自评分函数）
- 不假设固定的事件序列（SC→AR→ST不一定按顺序来，序列可以残缺、跳跃）
- 不硬编码参数阈值（所有阈值都是进化参数，初版给极宽松默认值）

---

## 2. 核心原则

### 2.1 标注驱动（最高原则）

系统学习的对象不是"SC长什么样"，而是"在什么场域条件下，状态A转换到状态B"。

-莱恩标注事件 → 系统提取场域特征 → 存入案例库
- 进化系统从案例库中优化引擎参数
- 引擎用优化后的参数运行 → 产生更精准的候选
- 莱恩确认/否定候选 → 反馈进化 → 循环

### 2.2 每个新低都是候选

趋势中每一个新低都是SC候选，每一个新高都是BC候选。不设门槛。

- 候选的置信度来自与历史标注案例的相似度，不来自预设评分
- 初版没有标注数据时，所有候选置信度相同（极低）
- 随着标注积累，高相似度的候选置信度升高

### 2.3 一边预测一边应对

- 预测：引擎基于已学到的参数，在趋势中标记高置信度候选
- 应对：当价格到达候选位置时，引擎准备好后续检测（AR/ST状态机）
- 初版没有预测能力，只有应对（标记所有候选）
- 进化后预测能力逐步增强

### 2.4 宽松初版 + 进化收紧（RD-55）

初版几乎不过滤。引擎产生大量候选，大部分是噪音。这是设计意图，不是缺陷。

莱恩的标注 = 过滤器。进化系统从"莱恩确认了什么、否定了什么"中学习，逐步收紧参数。

### 2.5 V3理论框架有效

V3的威科夫理论框架（区间生命周期、五大阶段、方向开关、供需三级递进）全部有效。

改变的不是理论，是实现路径：从"预设规则检测"变为"标注学习 + 进化优化"。

---

## 3. 与V3设计文档的关系

### 从V3保留的（不变层）

| 内容 | V3章节 | 说明 |
|------|--------|------|
| 三引擎架构 | §3 | 区间/事件/规则的职责划分 |
| 区间生命周期 | §2.1 | SC→AR→ST→B→C→D→E的可能路径 |
| 五大阶段 | §2.2 | A/B/C/D/E的定义和非线性路径 |
| 方向开关 | §2.3 | 阶段C翻转/延续方向 |
| 区间形状 | §2.4 | 水平/上斜/下斜 |
| Creek/Ice | §2.5 | 区间内部结构线|
| 供需三级递进 | §2.6 | mSOS→SOS→MSOS |
| 再吸筹/再派发 | §2.7 | 递归同构 |
| 数据结构 | §4 | Range/Event/EventCase/CandidateExtreme |
| 计算公式 | §4.7 | penetration_depth/effort_vs_result/position_in_range |
| 事件类型全表 | §6| 23种事件类型 |
| 8种检测模板结构 | §6.1 | 模板的状态定义（不含转换条件） |
| 记忆层四库 | §8 | 历史区间库/事件案例库/规则日志/交易记录 |
| 进化四层分离 | §9 | 不变层/参数层/变体层/策略层 |

### 从V3修改的

| V3原文 | 修改为 | 原因 |
|--------|--------|------|
| SC/BC置信度由5个预设因素评分 | 置信度由案例库相似度检索决定 | 标注驱动，不预设评分规则 |
| 8种模板有具体的转换条件 | 转换条件全部为进化参数，初版极宽松 | 条件从标注中学习 |
| 规则引擎有具体的PhaseRule代码 | 规则结构保留，触发条件为进化参数 | 条件从标注中学习 |
| SC→AR→ST固定序列 | 可能路径图，允许残缺/跳跃/非标准 | 实盘证明序列不一定按顺序 |
| 区间强度用时间衰减公式 | 事件驱动的强度变化 | 莱恩纠正：不是时间让支撑变弱，是后续事件 |
| 成交量基准用滑动窗口 | 阶段绑定均量 | RD-56|

### V3新增的（标注驱动补充）

| 新增内容 | 说明 |
|----------|------|
| 特征提取管道 | 莱恩标注事件时，系统提取场域特征 |
| 案例相似度检索 | 新K线到达时，检索最相似的历史标注案例 |
| 进化参数管道 | 案例库 → 统计分析 → 参数优化 → 引擎加载 |
| 候选建议机制 | 引擎用当前参数标记候选，莱恩确认/否定 |
| 修正反馈 | 莱恩在实盘中修正引擎标注→ 高价值进化燃料 |

---

## 4. 三个子引擎

### 4.1 区间引擎（RangeEngine）

**职责：场域基础设施**

区间引擎管理区间的生命周期，维护"支撑阻力地图"，计算价格在场域中的位置。

**核心行为：**

```
每根K线到达时：
1. 如果没有活跃区间（趋势运行中）：
   - 每个新低 = SC候选，每个新高 = BC候选（零门槛）
   -旧候选被替换，存入记忆层（标记REPLACED）
   - 检查是否有AR特征（任何反弹都可能是AR，宽松）
   - 检查是否有ST特征（任何回测都可能是ST，宽松）
   - AR+ST确认 → 三点定区间 → 区间创建

2. 如果有活跃区间：
   - 计算价格在区间中的位置（基于趋势线当前值）
   - 阶段B：更新区间形状（拟合高低点趋势线）
   - 阶段B：更新Creek/Ice
   - 检测边界接近/突破
   - 输出RangeContext给事件引擎
```

**历史区间库 =莱恩画的区间自动注册**

莱恩在进化工作台画平行通道 → annotation插件保存Drawing → 引擎加载时读取 → 注册到HistoricalRangeStore。

这就是支撑阻力地图的来源。不需要引擎自己"发现"历史区间。

**输出：RangeContext**

```python
@dataclass
class RangeContext:
    has_active_range: bool
    active_range: Optional[Range]
    position_in_range: float        # 0=下沿, 1=上沿
    distance_to_lower: float        # 距离下边界百分比
    distance_to_upper: float        # 距离上边界百分比
    nearby_support: List[Range]     # 附近历史支撑区间
    nearby_resistance: List[Range]  # 附近历史阻力区间
    range_shape: Optional[RangeShape]
    creek_price: Optional[float]
    ice_price: Optional[float]
    pending_events: List[Event]     # 传递给事件引擎的事件
```

### 4.2 事件引擎（EventEngine）

**职责：特征采集 + 案例匹配 + 状态机骨架**

事件引擎提供8种检测模板的状态机骨架，但转换条件全部是进化参数。

**两种运行模式：**

**模式A：标注辅助（进化工作台）**
- 引擎用当前参数标记候选事件（初版极宽松，几乎所有边界接近都标记）
- 莱恩看到候选后确认/否定/修正
- 确认的事件 → 系统提取场域特征 → 存入EventCaseStore
- 否定的事件 → 同样存入（标记REJECTED），这也是进化燃料

**模式B：自动检测（实盘监控）**
- 引擎用进化后的参数自动检测
- 检测到事件 → 发布engine.event_detected
- 莱恩偶尔修正 → 差异反馈进化

**8种检测模板骨架（从V3 §6.1继承）：**

| 模板 | 状态| 适用事件 | 初版行为 |
|------|------|----------|----------|
| 1.边界测试型 | IDLE→APPROACHING→PENETRATING→RECOVERING→CONFIRMED/FAILED | Spring/UTAD/ST/ST-B/UT/UTA/LPS/LPSY/BU | 任何边界接近都标记 |
| 2.区间突破型 | IDLE→APPROACHING→PENETRATING→HOLDING→CONFIRMED/FAILED | JOC/跌破冰线| 任何突破都标记 |
| 3.极端事件型 | IDLE→CANDIDATE→WAITING_AR→CONFIRMED/REPLACED | SC/BC | 每个新低/新高都标记 |
| 4.反弹回落型 | IDLE→BOUNCING→MEASURING→CONFIRMED | AR | 任何反弹都标记 |
| 5.渐进供需型 | 滑动窗口统计 | mSOS/mSOW | 极低阈值 |
| 6.供需确认型 | IDLE→DIRECTIONAL_MOVE→WEAK_REACTION→NARROW_CONSOLIDATION→CONFIRMED | SOS/SOW | 极宽松条件 |
| 7.回踩确认型 | IDLE→PULLBACK→HOLDING_ABOVE→CONFIRMED/FAILED | MSOS/MSOW | 任何回踩都标记 |
| 8.事后标注型 | SC确认后回扫 | PS/PSY | 回扫窗口宽 |

**每种模板的转换条件都是进化参数。** 比如模板1（边界测试型）：
- "APPROACHING"的触发距离 →进化参数（初版：距边界5%以内）
- "PENETRATING"的深度判定 → 进化参数（初版：任何穿越都算）
- "CONFIRMED"的回收条件 → 进化参数（初版：收回边界内即确认）
- 成交量条件 → 进化参数（初版：不检查成交量）

### 4.3 规则引擎（RuleEngine）

**职责：阶段转换框架 + 方向管理**

规则引擎管理阶段转换的路径图。路径图的结构是固定的（不变层），但转换的触发条件是进化参数。

**阶段转换路径图（从V3 §2.2继承）：**

```
趋势 ──SC/BC候选──→ A（起点确定）
A ──ST确认──→ B（区间建设）
A ──ST失败──→ 趋势（重新寻找SC/BC）
B ──Spring/UTAD成功──→ D（C确认，跳过独立C阶段）
B ──边界跌破──→ 趋势（区间BROKEN）
B ──持续震荡──→ B（保持）
D ──JOC/跌破冰线──→ E（趋势运行）
D ──突破被打回──→ B（回到区间）
E ──价格回到旧区间──→ B（假突破回归）
E ──新SC/BC──→ A（新区间开始）
```

**方向开关（不变层，从V3 §2.3继承）：**

| 时机 | 方向变化 |
|------|----------|
| SC出现 | → SHORT |
| BC出现 | → LONG |
| Spring/SO成功（C确认） | 如果entry_trend=SHORT →翻转LONG（吸筹） |
| UTAD成功（C确认） | 如果entry_trend=LONG → 翻转SHORT（派发） |

**structure_type推导（不变层，从V3 §2.7.1继承）：**

| entry_trend | C阶段事件 | structure_type |
|-------------|-----------|----------------|
| SHORT (SC进入) | Spring/SO | ACCUMULATION |
| LONG (BC进入) | UTAD | DISTRIBUTION |
| LONG (BC进入) | Spring/SO | RE_ACCUMULATION |
| SHORT (SC进入) | UTAD | RE_DISTRIBUTION |

**规则的触发条件 = 进化参数。** 比如"ST确认"：
- V3写的是"缩量回测边界 = 供应枯竭确认"
- 标注驱动下："什么算缩量"、"什么算回测边界"、"回测到什么程度算确认"全部是进化参数
- 初版：任何回到SC附近的价格运动都可能是ST（极宽松）

---

## 5. 数据结构

从V3 §4继承，不做修改。这些是引擎的词汇表。

### 5.1 核心结构

**Range（区间）** — 完整定义见V3 §4.1
- 通道定义：channel_slope, channel_width, 三个锚点
- 形状：range_shape (HORIZONTAL/ASCENDING/DESCENDING)
- 内部结构线：creek, ice (TrendLine)
- 生命周期：status (CANDIDATE→CONFIRMED→ACTIVE→BROKEN→ARCHIVED/REJECTED)
- 阶段：current_phase, structure_type, direction_confirmed

**Event（事件）** — 完整定义见V3 §4.4
- 序列信息：start_bar, end_bar, sequence_length
- 供需特征：volume_ratio, volume_pattern, effort_vs_result
- 价格特征：price_extreme, penetration_depth, recovery_speed
- 上下文：range_id, phase, position_in_range
- 置信度：confidence（来自案例库检索，不来自预设评分）

**EventCase（事件案例）** — 完整定义见V3 §4.5
- event +区间快照 + K线序列(前/中/后) + 市场环境 + 后续结果
- 这是进化系统的核心数据单位

**CandidateExtreme（SC/BC候选）** — 完整定义见V3 §4.6
- 同一时间只保留一个候选
- 新极值出现时旧候选被替换（旧候选标记REPLACED存入记忆层）

### 5.2 枚举

从V3 §4.3继承：
- RangeStatus: CANDIDATE / CONFIRMED / ACTIVE / BROKEN / ARCHIVED / REJECTED
- Phase: A / B / C / D / E
- StructureType: ACCUMULATION / DISTRIBUTION / RE_ACCUMULATION / RE_DISTRIBUTION / UNKNOWN
- Direction: LONG / SHORT / NEUTRAL
- EventType: 23种（SC/BC/AR/ST/ST_B/UT/UTA/Spring/SO/UTAD/LPS/LPSY/BU/SOS/SOW/JOC/BREAK_ICE/MSOS/MSOW/MSOS_TREND/MSOW_TREND/PS/PSY）
- EventResult: SUCCESS / FAILED / SKIPPED

### 5.3 计算公式

从V3 §4.7继承，这些是特征提取的工具：
- penetration_depth = |price - boundary_price| / channel_width
- effort_vs_result = clamp(efficiency -1.0, -1, +1)
- position_in_range = (price - lower) / (upper - lower)
- recovery_speed = |recovery - penetrate| / penetrate_price / num_bars

---

## 6. 进化参数清单

所有"留空等标注填充"的参数。初版给极宽松默认值。

### 6.1 区间引擎参数

| 参数 | 含义 | 初版默认| 进化方向 |
|------|------|----------|----------|
| ar_min_bounce_pct | AR最小反弹幅度 | 0.01 (1%) | 从标注中学习典型AR幅度 |
| ar_min_bars | AR最少持续K线数 | 1 | 从标注中学习典型AR持续时间 |
| st_max_distance_pct | ST与SC的最大距离 | 0.20 (20%) | 从标注中学习ST的典型位置 |
| st_max_volume_ratio | ST最大成交量比率（相对SC） | 999| 从标注中学习"缩量"的定义 |
| range_min_width_pct | 区间最小宽度 | 0.01 (1%) | 过滤太窄的假区间 |
| reentry_threshold | 假突破回归的价格阈值 | 0.5 | 回到区间多深算回归 |
| confirmation_bars | 假突破回归确认K线数 | 1 | 回到区间多久算确认 |
| max_breakout_age | 假突破回归最大间隔 | 999 | 突破后多久还能回归 |

### 6.2 事件引擎参数

| 参数 | 含义 | 初版默认 | 进化方向 |
|------|------|----------|----------|
| approach_distance | 边界接近触发距离 | 0.05 (5%) | 收紧到实际触发距离 |
| penetrate_min_depth | 最小穿越深度 | 0.0 | 从标注中学习有效穿越 |
| recovery_min_pct | 回收最小幅度 | 0.001 | 从标注中学习有效回收 |
| holding_min_bars | 穿越后最少持续K线 | 0 | 从标注中学习 |
| volume_check_enabled | 是否检查成交量 | false | 标注足够后开启 |
| volume_climax_ratio | 放量判定倍数 | 1.0 | 从标注中学习 |
| volume_dryup_ratio | 缩量判定倍数 | 999 | 从标注中学习 |
| joc_holdout_bars | JOC确认不回区间的K线数 | 1 | 从标注中学习 |
| msos_window | mSOS/mSOW统计窗口 | 5 | 从标注中学习 |
| msos_threshold | mSOS/mSOW触发阈值 | 0.01 | 从标注中学习 |
| sow_reaction_max_bars | SOW弱反弹最大K线数 | 999 | 从标注中学习 |
| sow_consolidation_max_range | SOW窄幅横盘最大振幅 | 999 | 从标注中学习 |

### 6.3 规则引擎参数

| 参数 | 含义 | 初版默认 | 进化方向 |
|------|------|----------|----------|
| st_confirms_min_confidence | ST确认区间的最低置信度 | 0.0 | 从标注中学习 |
| spring_confirms_min_confidence | Spring确认方向的最低置信度 | 0.0 | 从标注中学习 |
| b_phase_min_bars | B阶段最少K线数（成熟度） | 0 | 从标注中学习 |
| b_phase_timeout_bars | B阶段超时关注| 999 | 从标注中学习 |

---

## 7. 数据流

### 7.1 标注 → 进化 → 引擎（学习期）

```
莱恩在进化工作台标注
  ↓
annotation插件保存Drawing + 提取7维特征
  ↓
annotation插件生成EventCase（标注 + 特征 + K线快照）
  ↓
EventCase存入案例库（meridian.db → event_cases表）
  ↓
莱恩点击[▶ 运行进化]↓
evolution插件读取案例 → 统计分析 → 优化引擎参数
  ↓
新参数存入 evolution/params_v{N}.json
  ↓
发布 evolution.params_updated↓
engine插件订阅 → 加载新参数 → 检测更精准
```

### 7.2 实盘数据流（运行期）

```
candle.new（来自datasource插件）
  ↓
engine.plugin.py接收
  ↓
range_engine.process_bar(candle, bar_index)
  → 输出 RangeContext
  ↓
event_engine.process_bar(candle, range_ctx, bar_index)
  → 内部调用 rule_engine.evaluate() 评估阶段转换
  → 输出 EventContext
  ↓
发布事件：
  - engine.event_detected（检测到事件）
  - engine.phase_changed（阶段转换）
  - engine.signal_generated（交易信号）
  - engine.range_created（新区间创建）
```

### 7.3 修正反馈（高价值进化燃料）

```
实盘中引擎自动标注（半透明显示在图上）
  ↓
莱恩发现引擎标错了 → 手动修正
  ↓
annotation插件对比人工标注 vs 引擎标注
  ↓
差异记录为"修正案例"（标记高权重）
  ↓
进化系统重点学习修正案例 → 减少未来偏差
```

---

## 8. 与其他插件的交互

### 8.1 依赖

| 插件 | 依赖类型 | 用途 |
|------|----------|------|
| datasource | 必须 | K线数据 |
| annotation | 可选 | 读取莱恩标注的区间 → 注册到历史区间库 |

### 8.2 事件总线

**订阅：**
| 事件 | 来源 | 处理 |
|------|------|------|
| candle.new | datasource | 每根K线触发引擎处理 |
| evolution.params_updated | evolution | 加载新的进化参数 |

**发布：**
| 事件 | 数据 | 订阅者 |
|------|------|--------|
| engine.event_detected | Event对象 | annotation, AI |
| engine.phase_changed | symbol, tf, phase, direction | trading, AI |
| engine.signal_generated | Signal对象 | trading |
| engine.range_created | Range对象 | — |

### 8.3 API

```
GET/api/engine/state/{symbol}/{tf}     →EngineState
GET  /api/engine/state/{symbol}/all→ {tf: EngineState}
GET  /api/engine/ranges/{symbol}         → [Range]
GET  /api/engine/events/{symbol}         → [Event]
POST /api/engine/start   → {ok}
POST /api/engine/stop                    → {ok}
WS   ws://host/ws/engine/{symbol}        → 实时状态推送
```

---

## 9. 文件结构

```
backend/plugins/engine/
├── __init__.py
├── plugin.py              # 引擎插件入口（BackendPlugin实现）
├── range_engine.py        # 区间引擎
├── event_engine.py        # 事件引擎
├── rule_engine.py         # 规则引擎
├── models.py              # 数据结构（Range/Event/EventCase等）
├── params.py              # 进化参数定义 + 默认值 + 加载/保存
├── routes.py              # API路由
├── detectors/             # 检测器（按模板组织）
│   ├── __init__.py
│   ├── base_detector.py   # 检测器基类
│   ├── boundary_test.py   # 模板1：边界测试型
│   ├── breakout.py        # 模板2：区间突破型
│   ├── extreme_event.py   # 模板3：极端事件型（SC/BC）
│   ├── bounce.py          # 模板4：反弹回落型（AR）
│   ├── gradual_supply.py  # 模板5：渐进供需型（mSOS/mSOW）
│   ├── supply_confirm.py  # 模板6：供需确认型（SOS/SOW）
│   ├── pullback.py        # 模板7：回踩确认型（MSOS/MSOW）
│   └── retroactive.py    # 模板8：事后标注型（PS/PSY）
├── manifest.json          # 插件元数据
└── README.md              # 本文档
```

---

## 10. 施工顺序

### 第一步：骨架

1. models.py — 数据结构（从V3复制，Python dataclass）
2. params.py — 进化参数定义+ 极宽松默认值
3. plugin.py — 插件入口（生命周期、事件订阅、API注册）
4. manifest.json — 插件元数据

### 第二步：区间引擎

5. range_engine.py — RangeEngine类- process_bar() 主循环
   - 候选管理（每个新低/新高 = 候选）
   - 历史区间库查询
   - RangeContext输出

### 第三步：检测器

6. detectors/base_detector.py — 检测器基类（状态机骨架）
7. detectors/extreme_event.py — SC/BC候选（模板3）
8. detectors/bounce.py — AR检测（模板4）
9. detectors/boundary_test.py — ST/Spring/UTAD等（模板1）
10. 其余检测器按需

### 第四步：事件引擎 + 规则引擎

11. rule_engine.py — 阶段转换路径图+ 方向管理
12. event_engine.py — 检测器调度 + 规则引擎调用

### 第五步：API + 集成

13. routes.py — API路由
14. 集成测试：加载历史数据 → 引擎运行 → 输出候选

---

## 附录：关键设计决策

| 编号 | 决策 | 来源 |
|------|------|------|
| RD-55 | 初版宽松规则 +莱恩标注驱动进化 | V3 |
| RD-56 | 成交量基准改为阶段绑定均量 | 4/6讨论 |
| RD-57 | 删除时间衰减，改为事件驱动强度变化 | 4/6讨论 |
| ED-1 | 引擎是学习框架，不是自动检测器 | 4/8讨论 |
| ED-2 | 每个新低/新高都是候选，零门槛 | V3 §2.9 + 4/8讨论 |
| ED-3 | 检测模板的转换条件全部为进化参数 | 4/8讨论 |
| ED-4 | 三引擎保持一个插件，内部三个模块 | 4/8讨论 |
| ED-5 | 历史区间库 =莱恩标注的区间自动注册 | 4/6讨论 |
| ED-6 | 初版不检查成交量（volume_check_enabled=false） | RD-55宽松原则 |
| ED-7 | 序列允许残缺/跳跃/非标准路径 | 4/7实盘图证明 |

---

> **文档版本**: v1.0
> **作者**: WyckoffInspector
> **理论来源**: SYSTEM_DESIGN_V3.md +莱恩标注驱动方法论
> **日期**: 2026-04-08
> **状态**: 待莱恩审阅---

## 11. 路A施工：区间创建串联

> P2骨架14文件已完成审查。本章定义路A的具体施工方案：
> 修复5处断裂，让SC→AR→ST→create_range 的数据流跑通。
>
> **核心原则提醒**：
> - ED-1：引擎是学习框架，不是自动检测器。初版极宽松，精度来自进化
> - ED-2：每个新低/新高都是候选，零门槛
> - ED-6：初版不检查成交量
> - ED-7：序列允许残缺/跳跃/非标准路径
> - RD-55：初版几乎不过滤，莱恩的标注就是过滤器

---

### 11.1 当前断裂点

P2骨架的区间创建流程有5处断裂，导致区间永远无法创建：

**Gap1：AR锚点丢失**

`bounce.py` 检测到AR后返回 `Event(AR, SUCCESS)`，但没有人把AR的价格/bar_index存为`AnchorPoint`。`create_range()` 需要三个锚点（SC, AR, ST），AR锚点无处可取。

-断裂位置：`plugin.py` 的 `_on_candle` 方法
- 原因：plugin.py只把Event存入recent_events，没有提取AR的锚点信息

**Gap2：Phase.A的ST无法检测**

`boundary_test.py` 第一行就是 `if not range_ctx.has_active_range: return []`。Phase.A没有活跃区间——ST测试的是SC/BC极值位，不是区间边界。Phase.A的ST和Phase.B+的ST-B是两种完全不同的事件：

- Phase.A的ST：价格回到SC/BC极值位附近并撑住→ 区间确认的判定门
- Phase.B+的ST-B：价格测试已确立区间的边界 → 区间内部的供需测试

boundary_test.py只处理后者。前者没有任何代码处理。

- 断裂位置：`range_engine.py` 缺少 `_check_st()` 方法

**Gap3：_seek_candidate与ST冲突**

经典ST形态：价格刺破SC低点后收回（穿越后恢复 = 更强确认）。但`_seek_candidate` 只看`low< candidate.extreme_price` → 替换候选。它不区分"刺破+收回=ST成功"和"刺破+不收回=新SC"。

- 断裂位置：`range_engine.py` 的 `_seek_candidate()` 方法
- 后果：本应被识别为ST的K线被错误归类为新SC候选

**Gap4：create_range()孤立**

方法存在，逻辑正确，但无任何代码路径调用它。

- 断裂位置：`range_engine.py`

**Gap5：标注→引擎路径缺失**

莱恩在工作台标注SC/AR/ST或画平行通道时，引擎无法接收。引擎没有订阅 `annotation.created` 事件。

- 断裂位置：`plugin.py` 的 `get_subscriptions()`
- 注意：此修复依赖annotation插件发布事件。如果annotation插件尚未实现事件发布，先在plugin.py中添加订阅和处理逻辑，等annotation实现后路径自然打通

---

### 11.2 新增设计决策

| 编号 | 决策 | 依据 |
|------|------|------|
| ED-8 | Phase.A的ST由区间引擎检测（`_check_st`），Phase.B+的ST-B由事件引擎的`boundary_test.py` 检测。两者是不同的事件 | V3：区间引擎负责SC/BC/AR/ST |
| ED-9 | 有AR锚点时，刺破SC/BC位+ close收回 = ST候选，不是新SC/BC。`_seek_candidate` 不替换候选 | V3模板1：穿越后恢复 = 确认 |
| ED-10 | 区间在ST确认时由 `range_engine.create_range()` 直接创建。`rule_engine` 的 A→B 转换是阶段推进 | V3：三点定区间 |
| ED-11 | AR检测保留在 `bounce.py`（事件引擎调度），AR锚点通过 `plugin.py` 中转存入 `engine_state`。初版不迁移AR逻辑到区间引擎 | 减少改动，bounce.py逻辑已工作 |

---

### 11.3 修复方案

#### 11.3.1 models.py — EngineState新增字段

在`EngineState` dataclass 中新增一个字段：

```python
ar_anchor: Optional[AnchorPoint] = None
```

用途：存储AR检测后的锚点，供 `range_engine._check_st()` 和 `create_range()` 使用。

改动量：1行。

#### 11.3.2 range_engine.py — 主要改造

**改动1：重构 `process_bar()` 的无活跃区间分支**

当前代码：
```python
if active is None:
    self._update_trend_volume(candle)
    self._seek_candidate(candle, bar_index, engine_state, ctx)
```

改为：
```python
if active is None:
    self._update_trend_volume(candle)
    # 1. 先检查ST（如果候选+AR都就位）
    #    ST检查必须在_seek_candidate之前，否则刺破+收回会被错误识别为新SC
    if self.candidate_extreme is not None and engine_state.ar_anchor is not None:
        if self._check_st(candle, bar_index, engine_state, ctx):
            return ctx# 区间已创建，本轮结束
    # 2. 再检查新极值（可能创建/替换SC/BC候选）
    self._seek_candidate(candle, bar_index, engine_state, ctx)
```

**改动2：新增 `_check_st()` 方法**

```python
def _check_st(self, candle: dict, bar_index: int, engine_state: EngineState, ctx: RangeContext) -> bool:
    """
    Phase.A的ST检测：价格回到SC/BC极值位附近。
    判断逻辑（极宽松，符合ED-2/RD-55）：
    - SC情况：low接近或穿越SC极值 + close收回到SC上方 → ST成功
    - BC情况：high接近或穿越BC极值 + close收回到BC下方 → ST成功
    
    ST成功 → 创建ST Event + 调用create_range() + 设置ctx.active_range
    
    返回True表示区间已创建，False表示未触发ST。
    """
```

核心逻辑：

```
candidate = self.candidate_extreme
ar = engine_state.ar_anchor
threshold = self.params.st_max_distance_pct  # 初版0.20，极宽松

如果是SC候选：
    sc_level = candidate.extreme_price
    如果 low <= sc_level × (1 + threshold)：  # 价格接近或穿越SC位
        如果 close > sc_level：  # 收回 = ST成功
            创建 st_anchor = AnchorPoint(bar_index, low, close, volume)
            创建 st_event = Event(ST, SUCCESS,...)
            ctx.pending_events.append(st_event)
            new_range = self.create_range(candidate, ar, st_anchor, engine_state.direction)
            new_range.timeframe = engine_state.timeframe
            ctx.has_active_range = True
            ctx.active_range = new_range
            
            # 清理区间形成状态
            self.candidate_extreme = None
            engine_state.ar_anchor = None
            #重置趋势均量追踪
            self._trend_volume_sum = 0.0
            self._trend_volume_count = 0
            
            return True否则：  # close没收回 = 不是ST，是新低。让_seek_candidate处理
            return False

如果是BC候选：
    bc_level = candidate.extreme_price
    如果 high >= bc_level × (1 - threshold)：
        如果 close < bc_level：  # 收回 = ST成功
            （镜像逻辑）
            return True
    return False
```

**改动3：修改 `_seek_candidate()` 防止ST冲突**

在 `_seek_candidate` 的 `is_new_extreme` 判断后、替换候选之前，添加ST保护：

```python
if is_new_extreme:
    # ED-9：如果有AR锚点，检查是否可能是ST（刺破+收回）
    # 如果是ST情况，不替换候选，由_check_st在下一轮处理
    if engine_state.ar_anchor is not None and self.candidate_extreme is not None:
        is_sc = self.candidate_extreme.candidate_type == "SC"
        close = candle.get("close", 0)
        if is_sc and close > self.candidate_extreme.extreme_price:
            return  # 刺破SC但收回 = 可能是ST，不替换
        elif not is_sc and close < self.candidate_extreme.extreme_price:
            return  # 刺破BC但收回 = 可能是ST，不替换
    
    # 真正的新极值 → 替换候选 + 重置AR锚点
    engine_state.ar_anchor = None# 新候选意味着新的区间形成序列
    
    # ... 原有的候选替换逻辑 ...
```

注意：`engine_state.ar_anchor = None` 这一行是关键——新SC/BC候选出现意味着之前的AR失效，区间形成序列重新开始。

改动量：约60行新增/修改。

#### 11.3.3 plugin.py — AR锚点中转 + 标注订阅

**改动1：AR锚点存储**

在 `_on_candle` 方法中，`event_engine.process_bar` 返回后，检查是否有AR事件并存储锚点：

```python
# 在event_ctx处理循环中
for event in event_ctx.new_events:
    engine_state.recent_events.append(event)
    # ... 现有逻辑 ...
    
    # 新增：AR事件 → 存储锚点
    if event.event_type == EventType.AR:
        engine_state.ar_anchor = AnchorPoint(
            bar_index=event.sequence_end_bar,
            extreme_price=event.price_extreme,
            body_price=event.price_body,
            volume=0,# bounce.py当前不传volume，后续进化补充
        )
```

**改动2：标注事件订阅**

在 `get_subscriptions` 中新增：

```python
def get_subscriptions(self) -> dict:
    return {
        "candle.new": self._on_candle,
        "evolution.params_updated": self._on_params_updated,
        "annotation.created": self._on_annotation,# 新增
    }
```

新增 `_on_annotation` 方法：

```python
async def _on_annotation(self, data: dict) -> None:
    """
    莱恩标注事件时，引擎接收并处理。
    两种标注方式创建区间：
    1. 莱恩分别标注SC/AR/ST → 三点就位时自动创建区间
    2. 莱恩直接画平行通道 → 从通道坐标直接创建区间
    
    annotation.created 事件的期望数据格式：
    {
        "drawing_id": "uuid",
        "drawing_type": "callout" | "parallel_channel" | ...,
        "symbol": "ETHUSDT",
        "timeframe": "1D",
        "label": "SC",           # callout的文本标注
        "points": [              # 锚点坐标
            {"time": 1234567890, "bar_index": 100, "price": 1500.0},
            ...
        ],
        "metadata": {}# 附加数据
    }
    """
    symbol = data.get("symbol", "")
    tf = data.get("timeframe", "")
    drawing_type = data.get("drawing_type", "")
    
    # 确保state存在
    if symbol not in self.state:
        self.state[symbol] = {}
    if tf not in self.state[symbol]:
        self.state[symbol][tf] = EngineState(symbol=symbol, timeframe=tf)
    engine_state = self.state[symbol][tf]
    
    if drawing_type == "parallel_channel":
        # 莱恩画了平行通道 = 直接创建区间
        # 从通道的两条平行线提取上下边界和斜率
        points = data.get("points", [])
        if len(points) >= 4:  # 平行通道需要4个点（两条线各2个点）
            # 提取锚点，创建Range
            # 具体的坐标解析取决于annotation插件的Drawing数据结构
            pass# TODO: 实现通道→区间的转换
    
    elif drawing_type == "callout":
        label = data.get("label", "").upper().strip()
        points = data.get("points", [])
        if not points:
            return
        point = points[0]
        bar_idx = point.get("bar_index", 0)
        price = point.get("price", 0)
        
        if label in ("SC", "BC"):
            #莱恩标注了SC/BC → 存为候选
            is_sc = label == "SC"
            self.range_engine.candidate_extreme = CandidateExtreme(
                candidate_type=label,
                bar_index=bar_idx,
                extreme_price=price,
                body_price=price,
                volume=0,
                volume_ratio=1.0,
            )
            engine_state.candidate_extreme = self.range_engine.candidate_extreme
            engine_state.direction = Direction.SHORT if is_sc else Direction.LONG
            engine_state.current_phase = Phase.Aelif label == "AR":
            # 莱恩标注了AR → 存为AR锚点
            engine_state.ar_anchor = AnchorPoint(
                bar_index=bar_idx,
                extreme_price=price,
                body_price=price,
                volume=0,
            )
            
        elif label == "ST":
            # 莱恩标注了ST → 如果有候选+AR →创建区间
            candidate = self.range_engine.candidate_extreme
            ar = engine_state.ar_anchor
            if candidate is not None and ar is not None:
                st_anchor = AnchorPoint(
                    bar_index=bar_idx,
                    extreme_price=price,
                    body_price=price,
                    volume=0,
                )
                new_range = self.range_engine.create_range(
                    candidate, ar, st_anchor, engine_state.direction
                )
                new_range.timeframe = tf
                engine_state.active_range = new_range
                engine_state.current_phase = Phase.B
                # 清理
                self.range_engine.candidate_extreme = None
                engine_state.ar_anchor = None
                engine_state.candidate_extreme = None
                if self.ctx:
                    await self.ctx.event_bus.publish(
                        "engine.range_created",
                        {"symbol": symbol, "timeframe": tf, "range": new_range},
                    )
```

改动量：约50行新增。

#### 11.3.4 不改动的文件

| 文件 | 原因 |
|------|------|
| bounce.py | AR检测逻辑已工作，保持现状（ED-11） |
| boundary_test.py | Phase.B+的ST-B检测逻辑正确，Phase.A的ST由range_engine处理（ED-8） |
| event_engine.py | 检测器调度和规则引擎调用逻辑无需改动 |
| rule_engine.py | 阶段转换路径图无需改动。ST Event → A→B转换已实现 |
| params.py | `st_max_distance_pct=0.20` 已存在，可直接用于_check_st |
| models.py其他部分 | Range/Event/EventCase等数据结构无需改动 |

---

### 11.4 修复后的数据流

#### 路径1：引擎自动候选（辅助路径）

```
Bar N:新低→ _seek_candidate → SC候选创建 → Event(SC, PENDING)
        → event_engine → rule_engine → Phase.A + Direction.SHORT

Bar N+1~M:  反弹
        → bounce.py追踪反弹（_tracking=True,记录_bounce_peak）

Bar M:  反弹结束（从峰值回落）
        → bounce.py → Event(AR, SUCCESS)
        → plugin.py存储AR锚点到engine_state.ar_anchor

Bar M+1~K:  价格回落

Bar K:  价格回到SC附近（low <= SC ×1.20）+ close收回（close > SC）
        → range_engine._check_st → ST成功
        → Event(ST, SUCCESS) + create_range(SC, AR, ST)
        → ctx.active_range =新区间
        → event_engine → rule_engine → Phase.A → Phase.B
        → plugin.py → engine_state.active_range = 新区间
        → 发布 engine.range_created

Bar K+1:  boundary_test.py接管
        → has_active_range = True → 正常检测Spring/UTAD/ST-B/...
```

#### 路径2：莱恩标注（主路径）

```
莱恩标注SC（气泡箭头指向极值K线）
  → annotation.created事件 → plugin._on_annotation
  → 存入candidate_extreme + Phase.A + Direction

莱恩标注AR
  → annotation.created事件 → plugin._on_annotation
  → 存入engine_state.ar_anchor

莱恩标注ST
  → annotation.created事件 → plugin._on_annotation
  → 三点就位 → create_range(SC, AR, ST)
  → engine_state.active_range = 新区间 + Phase.B
  → 发布 engine.range_created

或：莱恩直接画平行通道
  → annotation.created事件 → plugin._on_annotation
  → 从通道坐标创建区间（跳过SC/AR/ST标注）
```

---

### 11.5 验收标准

1. **单元测试**：构造一组K线序列（持续下跌→新低=SC→反弹=AR→回测SC位+收回=ST），引擎运行后 `engine_state.active_range` 不为None
2. **阶段正确**：区间创建后`engine_state.current_phase` 为 `Phase.B`
3. **方向正确**：SC进入的区间 `direction` 为 `SHORT`，BC进入的为 `LONG`
4. **区间三锚点完整**：创建的Range的`primary_anchor_1`（SC）、`opposite_anchor`（AR）、`primary_anchor_2`（ST）三个锚点都不为None
5. **后续检测器工作**：区间创建后，`boundary_test.py` 能正常检测边界事件（`has_active_range=True`）
6. **候选替换重置AR**：新SC候选出现时，`engine_state.ar_anchor` 被重置为 None
7. **ST保护生效**：有AR锚点时，刺破SC+收回不触发候选替换
8. **标注路径**：`plugin.py` 能订阅 `annotation.created` 事件（即使annotation插件尚未发布事件，订阅代码本身不报错）

---

### 11.6 已知遗留（非阻塞，不在本次修复范围）

| 编号 | 问题 | 影响 | 计划 |
|------|------|------|------|
| W3 | bounce.py硬编码0.98/1.02回落阈值，未用params | AR检测精度 | 路B进化插件时统一处理 |
| W4 | 检测器状态共享：SC候选被替换时bounce.py内部状态不重置 | 多TF时可能误检 | 路B或后续迭代 |
| W7 | `_update_position` 不处理派发区间（upper< lower） | 派发区间位置计算错误 | 后续迭代 |
| — | `_on_annotation` 的平行通道→区间转换（TODO） | 标注路径2不完整 | 等annotation插件数据结构确定后实现 |
| — | bounce.py的AR volume未传递 | AR锚点volume=0 | 后续迭代 |
| — | 初版不区分区间CANDIDATE/CONFIRMED状态 | 所有区间直接CONFIRMED | 进化系统加入确认流程后区分 |

---

### 11.7 施工顺序

```
1. models.py     →EngineState新增ar_anchor字段（1行）
2. range_engine.py → 新增_check_st()方法（~30行）
3. range_engine.py → 修改process_bar()无活跃区间分支（~10行）
4. range_engine.py → 修改_seek_candidate()添加ST保护（~10行）
5. plugin.py→ _on_candle中添加AR锚点存储（~8行）
6. plugin.py      → get_subscriptions新增annotation.created（1行）
7. plugin.py      → 新增_on_annotation方法（~50行）
8. 验证→ 构造测试K线 → 运行 → 检查验收标准
```

总改动量：约110行新增/修改，涉及3个文件。