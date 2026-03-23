# 状态机 v4 重构计划 — 基于威科夫三大原则

> **状态**: 📋 计划中（待用户审核）
> **优先级**: P0
> **预计工期**: 6-8天
> **核心约束**: `WyckoffEngine.process_bar() → BarSignal` 接口不变，前端不动，进化系统无感
> **审查状态**: 已通过外部威科夫知识库深度审查，整合5项CRITICAL修正 + 8个设计缺口补齐

## 背景

### 当前问题
- 450根K线出现325次状态变化（72%跳变率），正常应每阶段持续10-50根K线
- 22个检测器每根K线并行竞争，谁置信度>0.35就跳
- 无序列化推进、无多K线确认、无三大原则基础
- 吸筹/派发检测器完全独立，但实际结构一样（区分靠测试方向和时间）
- StateConfig只有6个可进化参数，远不够

### 威科夫三大原则（核心理论基础）
1. **供需原则**: 价格由供需力量平衡决定，量价关系是核心表达
2. **因果原则**: 区间是"因"，趋势是"果"，区间:趋势时间比≈2:1
3. **努力与结果原则**: 成交量(努力)与价格变动(结果)应和谐，不和谐预示转向

### 用户核心理念
- 趋势中出现停止行为→假设PS→期待SC→期待AR→区间自然浮现
- 不是"先判断区间再跑检测"，而是"结构推进过程就是区间确认过程"
- 吸筹/派发/再吸筹/再派发走同一套结构，区分靠测试方向+时间比例
- 方向在C阶段才确认（Spring→做多，UTAD→做空），A-B阶段方向中性
- 不做人工硬编码确认，改用参数化的概率式确认（打分+进化优化阈值）
- 吸筹/派发统一结构但检测器内部参数不强行镜像（市场微观行为不完全对称）

### 接口契约（不可变）

**WyckoffStateResult 必须保留的字段：**
```
current_state, phase, direction, confidence, intensity,
evidences, signal, signal_strength, state_changed,
previous_state, heritage_score, critical_levels
```

**BarSignal 是进化系统唯一耦合点**（进化不直接import任何状态机类）

**前端消费12个缩写字段**（p/s/c/ts/tr/tc/mr/d/ss/sc/sig/cl），TR数据来自感知层

## 架构设计

```
数据流:
  K线数据 → 三大原则打分器 → BarFeatures（纯特征，无状态依赖）
              → 状态机主干（维护 StructureContext + 三层语义）
                → 检测器举证（接收 BarFeatures + StructureContext → NodeScore）
                  → 主干综合裁决 → 推进/维持/否定
                    → WyckoffStateResult（对外映射，接口不变）
                      → BarSignal → 前端/进化系统

进化系统优化（分层）:
  全局层（先开放）: 三大原则权重、确认窗口、衰减规则
  结构层（稳定后开放）: A/B/C/D/E 阶段参数
  节点层（最后开放）: 个别检测器阈值
```

### 新增核心类型

#### 架构决策 AD-1：内部三层语义，对外映射一层

内部维护三个独立变量：
- `current_phase`: 阶段 (A/B/C/D/E/IDLE/MARKUP/MARKDOWN) — 宏观进程
- `last_confirmed_event`: 最近确认的结构事件 (PS/SC/AR/ST/Spring/UTAD...) — 已发生的点
- `active_hypothesis`: 当前正在测试的假设 (带 StateStatus) — 进行中的判断

对外输出时：
- `current_state` = 如果 active_hypothesis.status == TESTING 则输出假设名，否则输出 last_confirmed_event
- `phase` = current_phase
- 这样保持 WyckoffStateResult 接口完全不变

#### 架构决策 AD-2：拆分 BarFeatures + StructureContext

**BarFeatures**（由三大原则打分器产出）：
- 打分器接收当前K线 + 上一轮 StructureContext（滞后一拍）
- BarFeatures 本身不持有 StructureContext 引用，只持有计算结果
- 这样 BarFeatures 仍然是"值对象"，但打分器的输入不再是"零依赖"
```python
@dataclass
class BarFeatures:
    """三大原则打分 + 单K线/滚动窗口特征"""
    # 三大原则核心分数
    supply_demand: float      # -1(纯供应) ~ +1(纯需求)
    cause_effect: float       # 0~1 因的累积程度
    effort_result: float      # -1(完全背离) ~ +1(完全和谐)
    # 单K线特征
    volume_ratio: float       # 当前量/MA20量
    price_range_ratio: float  # 当前振幅/MA20振幅
    body_ratio: float         # 实体/全长
    is_stopping_action: bool  # 是否为停止行为
    spread_vs_volume_divergence: float  # 努力结果背离强度
```

**StructureContext**（由状态机维护，传入检测器）：
```python
@dataclass
class StructureContext:
    """结构上下文 — 状态机维护的当前结构认知"""
    current_phase: str
    last_confirmed_event: str
    position_in_tr: float     # 0~1
    distance_to_support: float
    distance_to_resistance: float
    test_quality: float
    recovery_speed: float
    swing_context: str        # "impulse" | "test" | "unknown"
    direction_bias: float     # -1 ~ +1, A-B阶段逐步积累
    boundaries: Dict[str, BoundaryInfo]  # 关键价位 + 生命周期状态
```

**BoundaryInfo**（关键价位完整生命周期信息，放在 boundary_manager.py）：
```python
@dataclass
class BoundaryInfo:
    """单个关键价位的完整生命周期信息"""
    name: str                      # "SC_LOW" / "AR_HIGH" / "BC_HIGH" / "AR_LOW"
    price: float
    status: BoundaryStatus         # PROVISIONAL → LOCKED → INVALIDATED
    # 生命周期追踪
    created_at_bar: int            # 在第几根K线首次设定
    locked_at_bar: Optional[int] = None   # 锁定时间
    invalidated_at_bar: Optional[int] = None  # 失效时间
    # 测试历史
    test_count: int = 0
    last_test_bar: Optional[int] = None
    last_test_quality: float = 0.0
    # 更新历史（防止旧bug：无条件覆盖）
    price_history: List[Tuple[float, int]] = field(default_factory=list)
```

**BoundaryManager 核心方法**（根治旧系统 C-02 问题）：
```python
class BoundaryManager:
    def propose(self, name, price, bar_index) -> BoundaryInfo:
        """提议新边界(PROVISIONAL)。LOCKED的不允许propose覆盖，必须先invalidate"""
    def lock(self, name, bar_index, test_quality):
        """锁定(PROVISIONAL→LOCKED)。触发：ST测试不破+反弹确认"""
    def record_test(self, name, bar_index, quality):
        """记录测试（不改状态，只更新历史）"""
    def try_update(self, name, new_price, bar_index) -> bool:
        """PROVISIONAL允许更新，LOCKED/INVALIDATED拒绝"""
    def invalidate(self, name, bar_index):
        """失效(→INVALIDATED)。触发：有效跌破/突破超阈值"""
    def to_critical_levels(self) -> Dict[str, float]:
        """导出为 WyckoffStateResult.critical_levels 兼容格式"""
```

**Hypothesis**（状态机内部假设完整状态，放在 state_machine_v4.py）：
```python
@dataclass
class Hypothesis:
    """状态机对某个威科夫事件的假设"""
    event_name: str            # "PS" / "SC" / "AR" / "ST" / "Spring" ...
    status: StateStatus        # HYPOTHETICAL → TESTING → REJECTED / EXHAUSTED
    confidence: float          # 当前置信度 (0~1)
    # 时间追踪
    proposed_at_bar: int       # 在第几根K线提出假设
    bars_held: int = 0         # 已持续多少根K线
    # 证据累积（AD-3：主干解释，不是检测器直接用）
    supporting_evidence: List[NodeScore] = field(default_factory=list)
    contradicting_evidence: List[NodeScore] = field(default_factory=list)
    # 确认质量追踪（T2.11）
    confirmation_quality: float = 0.0   # 综合确认质量 = bars × quality
    # 生命周期
    rejection_reason: Optional[str] = None
```

**主干使用 Hypothesis 的推进伪代码**（AD-1 + AD-3 落地）：
```python
# 1. 无活跃假设 → 检查是否产生新假设
if self.active_hypothesis is None:
    best = self._evaluate_expectation_list(features, context)
    if best and best.confidence >= threshold:
        self.active_hypothesis = Hypothesis(event_name=best.event_name, ...)

# 2. 有活跃假设 → 推进/否定/超时
elif self.active_hypothesis is not None:
    hyp = self.active_hypothesis
    hyp.bars_held += 1
    scores = self._evaluate_expectation_list(features, context)
    # 主干综合裁决（AD-3）
    if contradiction_is_fatal:
        hyp.status = StateStatus.REJECTED
        hyp.rejection_reason = "放量跌破SC_LOW"
    elif hyp.bars_held > max_hypothesis_bars:
        hyp.status = StateStatus.EXHAUSTED
    elif hyp.confirmation_quality >= confirmation_threshold:
        self._confirm_and_advance(hyp)  # → 更新 last_confirmed_event

# 3. 对外映射（AD-1）
if self.active_hypothesis and self.active_hypothesis.status == StateStatus.TESTING:
    result.current_state = self.active_hypothesis.event_name
else:
    result.current_state = self.last_confirmed_event
```

#### 数据流依赖说明（解决残留1）

三大原则打分器需要结构信息（如支撑/阻力位置、区间持续时间），
但 StructureContext 由状态机维护。解法：**滞后一拍依赖**。

```
执行顺序（每根K线）：
  1. 打分器接收「上一轮的 StructureContext」+ 当前K线 → 产出 BarFeatures
  2. 状态机主干接收 BarFeatures + 自身维护的 StructureContext → 检测器举证 → 裁决推进
  3. 状态机更新 StructureContext（供下一轮打分器使用）
```

形成 `StructureContext(t-1) → BarFeatures(t) → StructureContext(t)` 的单向循环。
首根K线时 prev_context=None，打分器退化为纯K线特征（位置相关分数默认0/中性）。

**WyckoffPrinciplesScorer 签名**：
```python
class WyckoffPrinciplesScorer:
    def __init__(self):
        self._history: deque = deque(maxlen=50)  # 滑窗历史
    
    def score(self, candle: dict, prev_context: Optional[StructureContext] = None) -> BarFeatures:
        """对当前K线进行三大原则评估。
        prev_context: 上一轮状态机产出的结构上下文。
        首根K线时为 None，位置相关分数默认为 0（中性）。
        """
```

#### NodeScore 元数据执行职责（解决残留3）

- `required_context` 前置检查 → **DetectorRegistry** 负责（不满足则不分发该检测器）
- `cooldown_bars` 计时 → **DetectorRegistry** 维护计数器
- `invalidates` / `supports` 解释 → **状态机主干裁决逻辑**负责

#### 进化分层解冻条件（解决残留4）

分层解冻条件由进化系统侧定义，v4 状态机只需暴露 `frozen_keys` 列表。
状态机不关心何时解冻，只需支持 `StateConfig.update_from_dict()` 更新参数。

检测器签名：`evaluate(candle, features: BarFeatures, context: StructureContext) → NodeScore`

#### 架构决策 AD-3：检测器只举证，推进权在状态机主干

检测器返回 NodeScore（证据），**不直接触发状态转移**。
状态机主干 process_candle() 的推进逻辑：
1. 收集期待列表内所有检测器的 NodeScore
2. 综合 BarFeatures 三大原则分数
3. 检查多K线确认质量
4. 检查边界状态
5. **主干代码决定是否推进**，不是检测器决定

检测器的 invalidates/supports 也由主干解释，检测器之间不互相调用。

#### 架构决策 AD-4：验收用影子运行抽查，逐步积累基准集

Phase 4.5 的抽样复盘结果沉淀为"基准集种子"。
长期目标：积累20-50段人工标注案例，计算关键事件命中率、顺序合理率、方向正确率。
初期不要求完整基准集，但每次抽查结果必须持久化存储。

#### 其他核心类型

```python
class StateStatus(Enum):
    HYPOTHETICAL = "hypothetical"  # 假设中，条件初步满足
    TESTING = "testing"            # 测试中，等待后续K线验证
    REJECTED = "rejected"          # 假设被否定
    EXHAUSTED = "exhausted"        # 假设超时/衰减

class BoundaryStatus(Enum):
    """关键价位生命周期状态"""
    PROVISIONAL = "provisional"    # 候选，初次出现
    LOCKED = "locked"              # 锁定，经过测试确认
    INVALIDATED = "invalidated"    # 失效，结构破坏
```

### 文件结构（重构后）

```
src/plugins/wyckoff_state_machine/
├── plugin.py                    # 插件壳（改为包装V4）
├── plugin-manifest.yaml
├── principles/                  # 新增：三大原则打分器
│   ├── __init__.py
│   ├── bar_features.py          # BarFeatures 类型 + 打分器入口
│   ├── supply_demand.py         # 供需分析
│   ├── cause_effect.py          # 因果分析
│   └── effort_result.py         # 努力vs结果分析
├── state_machine_v4.py          # 新增：状态推进器（替代V2）
├── boundary_manager.py          # 新增：关键价位生命周期管理
├── detector_registry.py         # 新增：检测器注册中心
├── detectors/                   # 新增：插件化检测器目录
│   ├── __init__.py
│   ├── base_detector.py         # 检测器基类
│   ├── accumulation.py          # 吸筹节点检测器（从AccumulationDetectorMixin迁移）
│   └── distribution.py          # 派发节点检测器（从DistributionDetectorMixin迁移）
├── transition_guard.py          # 保留：白名单不变
├── __init__.py
│
├── state_machine_v2.py          # Phase 5 删除
├── accumulation_detectors.py    # Phase 5 删除（迁移到 detectors/）
├── distribution_detectors.py    # Phase 5 删除（迁移到 detectors/）
├── state_machine_core.py        # Phase 5 删除（死代码）
└── enhanced_state_machine.py    # Phase 5 删除（死代码）
```

## TODOs

### Phase 1: 三大原则打分器（新增，不改现有代码）
> 依赖：无
> 文件：新建 `principles/` 目录下4个文件
> 预计：1天

- [ ] T1.1 创建 `principles/bar_features.py` — BarFeatures 数据类 + WyckoffPrinciplesScorer 入口类
  - BarFeatures 为纯特征层，无状态机依赖（AD-2）
  - 包含三大原则分数 + 单K线特征 + 滚动窗口统计
  - WyckoffPrinciplesScorer 内部维护滑窗历史（最近N根K线），供三个分析器使用
- [ ] T1.2 创建 `principles/supply_demand.py` — 供需分析器
  - 量价关系：放量上涨(需求) / 放量下跌(供应) / 缩量回调(枯竭)
  - K线在区间中的位置：接近支撑(需求测试) / 接近阻力(供应测试)
  - 连续性：连续N根K线的供需方向一致性
  - 输出：supply_demand_score (-1 ~ +1)
- [ ] T1.3 创建 `principles/cause_effect.py` — 因果分析器
  - 区间已持续时间（因的大小）
  - 与前一个趋势的时间比例（2:1参考）
  - 区间内价格振幅收敛/发散
  - 输出：cause_effect_score (0 ~ 1)
- [ ] T1.4 创建 `principles/effort_result.py` — 努力vs结果分析器
  - 当前K线：成交量 vs 价格变动幅度的和谐度
  - 与前N根K线对比：量价关系是否出现背离
  - 关键位置的努力结果：如SC低点附近放量但没跌破
  - 输出：effort_result_score (-1 ~ +1)
- [ ] T1.5 编写 Phase 1 单元测试 `tests/plugins/test_principles.py`

### Phase 2: 状态推进器重建（核心，替代 StateMachineV2）
> 依赖：Phase 1
> 文件：新建 `state_machine_v4.py` + `detector_registry.py`
> 预计：2天

- [ ] T2.1 创建 `detector_registry.py` — 检测器注册中心
  - DetectorRegistry 类：注册/注销/按名称获取检测器
  - 检测器基类 NodeDetector：name, evaluate(candle, features: BarFeatures, context: StructureContext) → NodeScore
  - 检测器只返回证据(NodeScore)，不直接触发状态转移（AD-3）
  - DetectorRegistry 负责 required_context 前置检查（不满足则跳过）和 cooldown_bars 计时（冷却期内不运行）
  - invalidates/supports 元数据随 NodeScore 传递给主干，由主干裁决逻辑解释
  - 支持运行时动态增删检测器
- [ ] T2.2 创建 `state_machine_v4.py` — WyckoffStateMachineV4 核心类
  - 替代 WyckoffStateMachineV2 的 process_candle() 逻辑
  - 保持 WyckoffStateResult 输出格式完全不变
  - 内部三层语义（AD-1）：current_phase, last_confirmed_event, active_hypothesis
  - 对外 current_state 通过映射规则生成
  - 维护 StructureContext（AD-2），传入检测器
  - 主干代码掌握推进权（AD-3），综合检测器证据+打分+确认质量后决定
- [ ] T2.3 实现序列化推进逻辑（主干裁决模式 AD-3）
  - 当前状态决定期待列表（基于TransitionGuard白名单）
  - 只运行期待列表中的检测器，不跑全部22个
  - 检测器返回 NodeScore（证据），主干收集后综合裁决：
    · 检查 BarFeatures 三大原则分数
    · 检查多K线确认质量（T2.11）
    · 检查边界状态（T2.7）
    · 主干决定：推进 / 维持等待 / 否定假设
  - 检测器的 invalidates/supports 由主干解释，检测器之间不互相调用
- [ ] T2.4 实现两级状态机制（HYPOTHETICAL → TESTING）
  - HYPOTHETICAL：检测器初步匹配，分数达到阈值（可进化参数）
  - TESTING：后续K线持续验证，多根K线不否定则维持
  - 不做硬性CONFIRMED，置信度由打分系统持续更新
- [ ] T2.5 实现多K线确认机制
  - 停止行为需要 min_bars_for_hypothesis 根K线确认（可进化参数）
  - 状态推进需要 confirmation_bars 根K线验证（可进化参数）
  - bars_in_hypothesis 跟踪假设持续时间
- [ ] T2.6 实现区间自然浮现机制
  - PS→SC 时记录下边界（SC_LOW）
  - SC→AR 时记录上边界（AR_HIGH）
  - AR→ST 测试下边界成功 → 区间雏形确立
  - 区间边界存入 critical_levels（与现有格式兼容）
- [ ] T2.7 实现关键边界生命周期管理（boundary_manager.py）
  - BoundaryStatus 三态：PROVISIONAL → LOCKED → INVALIDATED
  - 候选边界：初次出现时为 PROVISIONAL（如首次SC记录的SC_LOW）
  - 锁定条件：ST测试不破+反弹确认 → PROVISIONAL 变 LOCKED
  - 更新条件：更极端的测试点出现时允许更新（如二次SC更低→更新SC_LOW）
  - 失效条件：有效跌破/突破超过阈值 → INVALIDATED，结构重建
  - 防止旧bug：SC_LOW/BC_HIGH 不再被每根K线无条件覆盖
- [ ] T2.8 实现异常越级事件通道
  - 正常推进走期待列表，但以下极端情况允许越级：
    · Climax/Panic 级停止行为（巨量+巨幅K线，分数超过climax_threshold）
    · 区间彻底破坏（有效跌破/突破 LOCKED 边界）
    · 趋势恢复导致整个假设作废
  - 越级事件触发时重置假设，不卡在"期待列表"中僵死
- [ ] T2.9 实现统一结构处理（吸筹/派发/再吸筹/再派发）
  - A-B阶段走同一套推进逻辑，不区分方向
  - 方向在C阶段由测试方向决定：
    · 向下测试(Spring) → 吸筹方向
    · 向上测试(UTAD) → 派发方向
  - 时间比例辅助判断（区间:趋势≈2:1，可进化参数）
- [ ] T2.10 实现假设撤销与超时机制
  - REJECTED：后续K线直接否定假设（如放量跌破SC_LOW）
  - EXHAUSTED：假设持续时间超过 max_hypothesis_bars 且无进展
  - 被更高优先级结构覆盖时的处理逻辑
  - 假设撤销后的证据回收/降权机制
- [ ] T2.11 实现多K线确认质量因子
  - 确认不只数根数，还要看质量：
    · 是否回踩关键位不破
    · 量能是否衰减/放大符合预期
    · 收盘位置是否支持判断
    · 是否有反向大阴/大阳直接否定
  - 确认机制 = bars_count × quality_score
  - 吸筹/派发检测器参数独立，不强行镜像（市场微观行为不对称）
- [ ] T2.12 编写 Phase 2 单元测试 `tests/plugins/test_state_machine_v4.py`
  - 序列化推进：PS→SC→AR→ST 正确推进
  - 跳变防止：不再出现每1-2根K线就跳一次
  - 两级状态：假设→测试 正确切换
  - 区间浮现：critical_levels 正确记录
  - WyckoffStateResult 输出格式兼容

### Phase 3: 检测器迁移（改造现有检测器为插件化）
> 依赖：Phase 1 + Phase 2
> 文件：新建 `detectors/` 目录
> 预计：1.5天

- [ ] T3.1 创建 `detectors/base_detector.py` — 检测器基类
  - NodeDetector 抽象类
  - evaluate(candle, features: BarFeatures, context: StructureContext) → NodeScore（AD-2/AD-3）
  - 检测器只返回证据，不做推进决策
  - 每个检测器定义可进化参数字典
  - NodeScore 输出格式包含冲突裁决元数据（供主干解释）：
    · priority: 检测器优先级
    · invalidates: 与哪些其他检测器互斥
    · supports: 增强哪些其他检测器
    · cooldown_bars: 触发后冷却期
    · required_context: 运行此检测器需要什么前提条件
- [ ] T3.2 创建 `detectors/accumulation.py` — 迁移吸筹检测器
  - 从 AccumulationDetectorMixin 迁移13个检测器
  - 改为基于 BarFeatures + StructureContext 评分（AD-2）
  - PS/SC/AR/ST/TEST/UTA/SPRING/SO/LPS/mSOS/MSOS/JOC/BU
- [ ] T3.3 创建 `detectors/distribution.py` — 迁移派发检测器
  - 从 DistributionDetectorMixin 迁移9个检测器
  - 同样基于 BarFeatures + StructureContext 评分（AD-2）
  - PSY/BC/AR_DIST/ST_DIST/UT/UTAD/LPSY/mSOW/MSOW
- [ ] T3.4 注册所有检测器到 DetectorRegistry
- [ ] T3.5 编写 Phase 3 单元测试 `tests/plugins/test_detectors_v4.py`

### Phase 4: 集成接线 + 进化系统扩展
> 依赖：Phase 2 + Phase 3
> 文件：修改 `engine.py`, `types.py`, `config.yaml`, `plugin.py`
> 预计：1天

- [ ] T4.1 修改 `engine.py` — WyckoffEngine 切换到 V4
  - `_ensure_state_machine()` 改为创建 WyckoffStateMachineV4
  - `_run_state_machine()` 中先通过打分器产出 BarFeatures，再传入 V4
  - 从 DataFrame 计算 avg_volume_20 传入上下文
  - 保持 process_bar() → BarSignal 输出不变
- [ ] T4.2 扩展 `types.py` — StateConfig 参数空间（分层进化）
  - **全局层**（先开放进化）：三大原则权重、确认窗口、衰减规则
  - **结构层**（稳定后开放）：A/B/C/D/E 阶段参数
  - **节点层**（最后开放）：个别检测器阈值
  - 初始只进化全局层，节点层冻结，避免参数空间膨胀失控
  - 新增推进逻辑参数（min_bars_for_hypothesis, confirmation_bars, cause_effect_ratio, max_hypothesis_bars）
  - 全部加入 _evolution_params 列表，冻结参数加入 frozen_keys
  - 分层解冻条件由进化系统侧定义，状态机只通过 StateConfig.frozen_keys 暴露冻结列表
  - 初始 frozen_keys 包含所有结构层和节点层参数
- [ ] T4.3 更新 `config.yaml` — 新增参数默认值
  - state_machine 节下增加 principles_weights, progression, detector_params
- [ ] T4.4 修改 `plugin.py` — WyckoffStateMachinePlugin 切换到 V4
  - on_load() 改为实例化 WyckoffStateMachineV4（不再用 EnhancedWyckoffStateMachine）
  - process_candle() 代理到 V4
- [ ] T4.5 单实例接线审计
  - 确保 engine/plugin/signal 统一只持有一个状态机真相源
  - 杜绝旧系统双实例状态断裂问题（C-05）
  - process_candle 返回对象类型契约明确
- [ ] T4.6 运行全量测试 `pytest tests/ -q` 确保不破坏现有功能
- [ ] T4.7 运行 POST /api/analyze 端到端验证
  - 跳变率应从72%显著下降
  - 前端 AnalysisPage 正常渲染

### Phase 4.5: 影子运行验证（V2/V4 并行对比）
> 依赖：Phase 4
> 文件：临时脚本
> 预计：0.5天

- [ ] T4.5.1 创建影子运行脚本
  - 同一批数据同时跑 V2 和 V4
  - 记录状态序列差异
  - 统计跳变率、状态平均持续长度
  - 关键边界(SC_LOW/BC_HIGH/AR_HIGH)重写次数对比
- [ ] T4.5.2 抽样人工复盘（AD-4）
  - 对 Spring/UTAD/SOS/LPSY 等关键事件抽样对比
  - V4 的识别是否比 V2 更合理
  - **抽查结果持久化存储为"基准集种子"**，后续逐步积累为完整标注基准集
- [ ] T4.5.3 输出对比报告，确认 V4 优于 V2 后再进入 Phase 5

### Phase 5: 清理死代码
> 依赖：Phase 4 全部通过
> 文件：删除5个文件
> 预计：0.5天

- [ ] T5.1 删除 `state_machine_core.py` (964行) — 死代码
- [ ] T5.2 删除 `enhanced_state_machine.py` (614行) — 死代码
- [ ] T5.3 删除 `wyckoff_phase_detector.py` (1011行) — 仅被链路A使用
- [ ] T5.4 删除 `state_machine_v2.py` (801行) — 被V4替代
- [ ] T5.5 删除 `accumulation_detectors.py` + `distribution_detectors.py` — 已迁移到 detectors/
- [ ] T5.6 清理所有对已删文件的import引用
- [ ] T5.7 运行全量测试确认无破坏

## 风险与注意事项

### 低风险
- 前端不需要改动（接口契约不变）
- 进化系统接口不变（通过WyckoffEngine间接使用）
- TransitionGuard白名单保留不变

### 中风险
- 现有1271个测试中状态机相关测试需要大量调整
- StateConfig参数空间扩大后，进化系统的搜索空间变大，可能需要调GA参数

### 高风险
- 三大原则打分器的初始参数设定（需要进化系统帮助调优）
- 序列化推进逻辑的边界情况（趋势突变、数据缺失等）

### C阶段止损后的处理
> **暂不实现**，用户尚未确定策略，预留接口。
> 需要用户定义：止损后是否自动反手、失败后结构如何重标注。

## 验收标准

1. **跳变率**: 450根K线的状态变化次数 < 50（跳变率 < 11%）
2. **状态持续长度**: 平均状态持续 > 8根K线（H4即32小时+）
3. **关键边界稳定性**: SC_LOW/BC_HIGH 重写次数较V2显著下降
4. **接口兼容**: BarSignal 所有字段保持不变，前端无需修改
5. **测试通过**: `pytest tests/ -q` 全部通过
6. **进化兼容**: 进化系统可以正常优化新参数空间（分层进化）
7. **检测器可插拔**: 可以通过 DetectorRegistry 动态增删检测器
8. **影子运行通过**: V4 在抽样关键事件上的识别不劣于 V2

