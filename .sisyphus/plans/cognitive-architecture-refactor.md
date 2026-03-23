# V4 状态机认知架构重构

## TL;DR

> **目标**: 给V4状态机增加认知层——先判断市场模式再找事件，接入BoundaryManager定义区间，融入威科夫量价约束规则
> 
> **交付物**: 修改 state_machine_v4.py + transition_guard.py + 22个检测器 + 测试
> 
> **预计工作量**: Large（5个Phase, 16个Task）
> **并行执行**: YES — 4 Waves
> **关键路径**: T1→T5→T8→T10→T11→F1-F4

---

## Context

### 原始需求
基于6项设计共识 + 4项已回答待定决策 + 520行威科夫理论约束，重构V4状态机认知架构。

### 核心问题
当前V4从第一根K线就开始找威科夫事件，完全不管"当前是趋势还是区间"。正确认知顺序：**先判断市场状态 → 再假设结构类型 → 再在结构内找事件**。

### 6项设计共识
1. 区间是假设性的，不是确认性的
2. 区间由SC/AR事件定义，不由独立检测器定义
3. 需要结构级假设，不只事件级假设
4. 趋势是独立运行模式（TRENDING/TRANSITIONING/RANGING）
5. 冷启动 = 等第一个停止行为
6. 打分系统服务于概率判断

### Metis审查要点（已整合）
- 需要cross-event volume存储（event_volumes字段）
- 10个检测器缺正向测试覆盖，修改前必须补
- BoundaryManager无数据时fallback到外部TR
- MarketMode震荡需要cooldown/hysteresis
- StructureHypothesis与Hypothesis是两个独立对象

---

## Work Objectives

### 核心目标
在不改变WyckoffStateResult对外接口的前提下，重建状态机内部认知架构。

### 具体交付物
- MarketMode三模式层（TRENDING/TRANSITIONING/RANGING）
- BoundaryManager接入（propose/lock/invalidate生命周期）
- StructureHypothesis结构级假设
- VOL-01~10 + ER-01~05量价验证规则融入检测器
- position_in_tr改用内部边界（fallback外部TR）
- transition_history from==to bug修复

### Must Have
- MarketMode控制检测器调度
- BoundaryManager替代raw dict管理critical_levels
- event_volumes在StructureContext中供检测器做跨事件量比较
- 冷启动=TRENDING直到第一个停止行为
- 所有现有1282+测试继续通过

### Must NOT Have（护栏）
- 不改WyckoffStateResult字段定义
- 不改前端代码
- 不删任何检测器（可修改）
- 不实现Creek/Ice线检测
- 不实现区间斜率（先用水平边界）
- 不实现Hinge/死角检测
- 不实现50%回调规则
- 不实现Spring三分类
- 不在此阶段修plugin.py死壳
- MarketMode不进kernel/types.py（内部实现细节）

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — 全部agent执行验证

### Test Decision
- **Infrastructure exists**: YES（pytest, 1282 tests）
- **Automated tests**: YES (TDD — RED→GREEN→REFACTOR)
- **Framework**: pytest + pytest-asyncio

### QA Policy
每个Task必须包含agent可执行的QA场景。
证据保存到 `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`

---

## Execution Strategy

### 并行执行波次

```
Wave 1 (安全网 — 不改行为，只补测试+修bug):
├── T1: transition_history bug修复 [quick]
├── T2: 共享测试工厂 + 10个检测器正向测试 [unspecified-high]
└── T3: 确定性回归场景（固定bar序列→期望状态链）[unspecified-high]

Wave 2 (认知层 — MarketMode + BoundaryManager):
├── T4: MarketMode枚举 + StructureHypothesis数据类 [quick]
├── T5: MarketMode集成到_run_progression [deep]
├── T6: TransitionGuard增加模式约束 [quick]
├── T7: BoundaryManager接入_confirm_and_advance [deep]
├── T8: position_in_tr切换到内部边界 [unspecified-high]
└── T9: StructureHypothesis生命周期管理 [deep]

Wave 3 (量价约束 — 检测器增强):
├── T10: event_volumes字段 + 确认时填充 [quick]
├── T11: 吸筹检测器增加VOL/ER约束 [unspecified-high]
├── T12: 派发检测器增加VOL/ER约束 [unspecified-high]
└── T13: 冷启动行为实现 [quick]

Wave FINAL (验证):
├── F1: 计划合规审计 (oracle)
├── F2: 代码质量审查 (unspecified-high)
├── F3: 全量QA (unspecified-high)
└── F4: 范围保真检查 (deep)
-> 提交结果 -> 用户确认
```

### 依赖矩阵
| Task | Depends On | Blocks |
|------|-----------|--------|
| T1 | — | T5,T7 |
| T2 | — | T11,T12 |
| T3 | — | T5,T9 |
| T4 | — | T5,T6,T9 |
| T5 | T1,T3,T4 | T8,T9 |
| T6 | T4 | T5 |
| T7 | T1,T4 | T8 |
| T8 | T5,T7 | T11,T12 |
| T9 | T3,T4,T5 | T13 |
| T10 | T7 | T11,T12 |
| T11 | T2,T8,T10 | — |
| T12 | T2,T8,T10 | — |
| T13 | T9 | — |

---

## TODOs

- [x] 1. transition_history from==to bug修复

  **What to do**:
  - `_confirm_and_advance()` 第570行：先记录 `old_event = self.last_confirmed_event`，再更新 `self.last_confirmed_event = hyp.event_name`
  - 第592行 transition_history 的 `"from"` 改用 `old_event`
  - 添加回归测试验证 from != to

  **Must NOT do**: 不改其他逻辑，纯bug修复

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 1, 可与T2/T3并行, Blocks T5/T7

  **References**:
  - `src/plugins/wyckoff_state_machine/state_machine_v4.py:564-599` — _confirm_and_advance方法，第570行是bug位置
  - `tests/plugins/test_state_machine_v4.py` — 现有V4测试

  **Acceptance Criteria**:
  - [ ] `_transition_history[-1]["from"] != _transition_history[-1]["to"]` 在所有状态转换中成立
  - [ ] pytest tests/plugins/test_state_machine_v4.py -q → 全PASS

  **QA Scenarios**:
  ```
  Scenario: transition_history记录正确的from/to
    Tool: Bash (pytest)
    Steps:
      1. 新增测试：创建V4实例，喂入触发PS→SC转换的K线序列
      2. 检查 sm._transition_history[-1]["from"] == "PS"
      3. 检查 sm._transition_history[-1]["to"] == "SC"
    Expected Result: from != to, from是旧状态, to是新状态
    Evidence: .sisyphus/evidence/task-1-transition-history-fix.txt
  ```

  **Commit**: YES — `fix(sm): transition_history from==to bug`

---

- [x] 2. 共享测试工厂 + 10个检测器正向测试

  **What to do**:
  - 创建 `tests/fixtures/state_machine_helpers.py`，统一 `make_candle()`, `make_features()`, `make_context()` 工厂函数
  - 为10个无正向测试的检测器添加正向测试：TEST, UTA, SO, mSOS, MSOS, BU（吸筹）+ AR_DIST, ST_DIST, UT, mSOW（派发）
  - 每个检测器至少1个正向测试（返回NodeScore而非None）+ 1个负向测试

  **Must NOT do**: 不修改检测器代码，只补测试

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 1, 可与T1/T3并行, Blocks T11/T12

  **References**:
  - `tests/plugins/test_detectors_v4.py` — 现有检测器测试（只有PS/SC/AR/ST/Spring/LPS/JOC + PSY/BC/UTAD/LPSY/MSOW有正向测试）
  - `src/plugins/wyckoff_state_machine/detectors/accumulation.py` — 13个吸筹检测器
  - `src/plugins/wyckoff_state_machine/detectors/distribution.py` — 9个派发检测器
  - `src/plugins/wyckoff_state_machine/detectors/base_detector.py` — make_score/make_evidence工厂

  **Acceptance Criteria**:
  - [ ] tests/fixtures/state_machine_helpers.py 存在且被3个测试文件导入
  - [ ] 所有22个检测器都有≥1个正向测试
  - [ ] pytest tests/plugins/test_detectors_v4.py -q → ≥40 passed

  **QA Scenarios**:
  ```
  Scenario: 全部22检测器有正向覆盖
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/plugins/test_detectors_v4.py -v
      2. 检查输出包含 test_TEST_positive, test_UTA_positive, test_SO_positive 等
      3. 验证所有 PASSED
    Expected Result: 22个检测器各有≥1个positive test, 全PASSED
    Evidence: .sisyphus/evidence/task-2-detector-coverage.txt
  ```

  **Commit**: YES（与T3合并） — `test(sm): shared factory + detector coverage + regression`

---

- [x] 3. 确定性回归场景

  **What to do**:
  - 创建 `tests/plugins/test_sm_regression.py`
  - 编写3个固定bar序列→期望状态链的确定性测试：
    1. 完整吸筹循环：30根预热 + PS→SC→AR→ST→Spring→LPS→mSOS→MSOS→JOC→BU→UPTREND
    2. 完整派发循环：PSY→BC→AR_DIST→ST_DIST→UTAD→LPSY→mSOW→MSOW→DOWNTREND
    3. 结构失败：PS→SC→AR→ST→跌破SC_LOW放量→回IDLE
  - 每个场景使用固定价格/成交量数据（如price=50000, volume=100000）

  **Must NOT do**: 不用随机数据，不改状态机代码

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 1, 可与T1/T2并行, Blocks T5/T9

  **References**:
  - `src/plugins/wyckoff_state_machine/state_machine_v4.py:218-261` — process_candle入口
  - `src/plugins/wyckoff_state_machine/transition_guard.py:23-56` — VALID_TRANSITIONS完整白名单
  - `tests/fixtures/state_machine_helpers.py`（T2创建的工厂）

  **Acceptance Criteria**:
  - [ ] 3个回归测试存在且可运行（当前可能部分FAIL，作为baseline）
  - [ ] 测试使用固定数据，无随机性
  - [ ] pytest tests/plugins/test_sm_regression.py -v → 可运行（PASS或XFAIL标记）

  **QA Scenarios**:
  ```
  Scenario: 回归测试可运行
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/plugins/test_sm_regression.py -v --tb=short
      2. 验证3个测试函数存在且无ERROR（PASS或XFAIL均可）
    Expected Result: 3个测试可运行，无ImportError/SyntaxError
    Evidence: .sisyphus/evidence/task-3-regression-baseline.txt
  ```

  **Commit**: YES（与T2合并）

---

- [x] 4. MarketMode枚举 + StructureHypothesis数据类

  **What to do**:
  - 在 `state_machine_v4.py` 顶部添加 `MarketMode` 枚举（TRENDING/TRANSITIONING/RANGING）
  - 添加 `StructureHypothesis` 数据类：direction(ACCUM/DIST/UNKNOWN), confidence(0-1), created_at_bar, events_confirmed(list), failure_reasons(list)
  - 在 `__init__` 中初始化 `self.market_mode = MarketMode.TRENDING` 和 `self.structure_hypothesis = None`
  - 纯数据类型定义，**不改任何行为逻辑**

  **Must NOT do**: 不改_run_progression, 不改process_candle流程

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2, 无依赖可立即开始, Blocks T5/T6/T9

  **References**:
  - `src/plugins/wyckoff_state_machine/state_machine_v4.py:44-66` — 现有StateStatus/Hypothesis定义
  - `.sisyphus/drafts/cognitive-architecture-decisions.md:52-58` — 共识4：三个运行模式定义

  **Acceptance Criteria**:
  - [ ] MarketMode.TRENDING/TRANSITIONING/RANGING 可导入
  - [ ] StructureHypothesis 有5个指定字段
  - [ ] `sm.market_mode == MarketMode.TRENDING` 初始值正确
  - [ ] pytest tests/plugins/test_state_machine_v4.py -q → 全PASS（行为未改）

  **QA Scenarios**:
  ```
  Scenario: 新类型可实例化且不破坏现有行为
    Tool: Bash (pytest)
    Steps:
      1. pytest tests/plugins/test_state_machine_v4.py -q
      2. 验证全PASS（新增类型不影响现有测试）
    Expected Result: 所有现有测试PASS
    Evidence: .sisyphus/evidence/task-4-types-added.txt
  ```

  **Commit**: NO（与T5合并提交）

---

- [x] 5. MarketMode集成到_run_progression

  **What to do**:
  - 修改 `_run_progression()` 增加模式层门控：
    - TRENDING模式：只允许PS/SC/PSY/BC检测（停止行为入口）
    - TRANSITIONING模式：允许AR/ST/AR_DIST/ST_DIST检测（区间形成）
    - RANGING模式：允许全部检测器（区间内事件序列）
  - 添加模式转换逻辑：
    - TRENDING→TRANSITIONING：确认PS/SC/PSY/BC时
    - TRANSITIONING→RANGING：确认ST不破+AR存在时
    - RANGING→TRENDING：结构失败（跌破SC_LOW放量）时
    - RANGING→TRENDING：结构完成（UPTREND/DOWNTREND确认）时
  - 增加模式转换hysteresis：TRENDING→TRANSITIONING需最少5根K线在TRENDING

  **Must NOT do**: 不改WyckoffStateResult输出字段

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 2, Depends on T1/T3/T4, Blocks T8/T9

  **References**:
  - `state_machine_v4.py:280-346` — _run_progression当前逻辑
  - `state_machine_v4.py:364-412` — _try_new_hypothesis当前逻辑
  - `transition_guard.py:23-56` — VALID_TRANSITIONS
  - `.sisyphus/drafts/wyckoff-theory-constraints.md:474-481` — TRANSITIONING完整路径
  - `.sisyphus/drafts/cognitive-architecture-decisions.md:52-58` — 共识4

  **Acceptance Criteria**:
  - [ ] TRENDING模式下只有PS/SC/PSY/BC检测器被调用
  - [ ] 确认SC后mode==TRANSITIONING
  - [ ] 确认ST不破后mode==RANGING
  - [ ] 结构失败后mode==TRENDING
  - [ ] pytest tests/ -q → ≥1282 passed

  **QA Scenarios**:
  ```
  Scenario: 模式正确转换
    Tool: Bash (pytest)
    Steps:
      1. 新增测试：喂入趋势K线 → 验证mode==TRENDING
      2. 喂入停止行为K线 → PS确认 → 验证mode==TRANSITIONING
      3. 喂入AR+ST序列 → 验证mode==RANGING
      4. 喂入跌破SC_LOW放量K线 → 验证mode==TRENDING
    Expected Result: 四次模式转换全部正确
    Evidence: .sisyphus/evidence/task-5-mode-transitions.txt

  Scenario: TRENDING模式不触发区间内检测器
    Tool: Bash (pytest)
    Steps:
      1. 创建V4实例(mode=TRENDING)
      2. 喂入满足Spring/LPS/SOS条件的K线
      3. 验证这些检测器不被调用（last_confirmed_event仍为IDLE）
    Expected Result: TRENDING模式下Spring/LPS/SOS检测器被gate掉
    Evidence: .sisyphus/evidence/task-5-mode-gating.txt
  ```

  **Commit**: YES — `feat(sm): MarketMode + StructureHypothesis + mode gating`

---

- [x] 6. TransitionGuard增加模式约束

  **What to do**:
  - `get_valid_targets(from_state)` 增加可选 `mode: MarketMode` 参数
  - TRENDING模式：只返回 {PS, SC, PSY, BC}（无论当前from_state）
  - TRANSITIONING模式：返回 {AR, ST, AR_DIST, ST_DIST}（加上IDLE兜底）
  - RANGING模式：返回原有完整白名单
  - 向后兼容：mode=None时行为不变

  **Must NOT do**: 不删现有VALID_TRANSITIONS条目

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 2, Depends on T4, Blocks T5

  **References**:
  - `transition_guard.py:58-82` — get_valid_targets/is_valid_transition
  - `state_machine_v4.py:372` — 调用点

  **Acceptance Criteria**:
  - [ ] `get_valid_targets("IDLE", mode=TRENDING)` == {"PS","SC","PSY","BC"}
  - [ ] `get_valid_targets("SC", mode=None)` == 原有行为
  - [ ] pytest tests/plugins/test_transition_guard.py -q → 全PASS

  **QA Scenarios**:
  ```
  Scenario: 模式约束生效
    Tool: Bash (pytest)
    Steps:
      1. 新增测试验证TRENDING模式返回有限目标
      2. 验证RANGING模式返回完整白名单
      3. 验证mode=None向后兼容
    Expected Result: 三种模式返回不同目标集合
    Evidence: .sisyphus/evidence/task-6-guard-modes.txt
  ```

  **Commit**: NO（与T5合并提交）

---

- [x] 7. BoundaryManager接入_confirm_and_advance

  **What to do**:
  - `__init__` 中创建 `self._boundary_manager = BoundaryManager()`
  - `_confirm_and_advance()` 中替换 `self.critical_levels[key] = price` 为 `self._boundary_manager.propose(key, price, bar)`
  - ST/TEST确认时调用 `self._boundary_manager.lock("SC_LOW", bar)` 锁定下边界
  - ST_DIST确认时调用 `self._boundary_manager.lock("BC_HIGH", bar)` 锁定上边界
  - 结构失败时调用 `self._boundary_manager.invalidate(key, bar)`
  - `_build_result()` 中 `critical_levels` 改用 `self._boundary_manager.to_critical_levels()`
  - `_reset_to_idle()` 中重置BoundaryManager（新建实例）

  **Must NOT do**: 不改BoundaryManager本身的代码

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 2, Depends on T1/T4, Blocks T8

  **References**:
  - `boundary_manager.py:55-103` — propose方法（PROVISIONAL→LOCKED保护）
  - `boundary_manager.py:104-128` — lock方法
  - `boundary_manager.py:177-199` — invalidate方法
  - `boundary_manager.py:201-213` — to_critical_levels兼容输出
  - `state_machine_v4.py:564-615` — _confirm_and_advance（当前用raw dict）
  - `state_machine_v4.py:136-145` — _BOUNDARY_EVENTS映射表

  **Acceptance Criteria**:
  - [ ] `self.critical_levels` dict不再直接写入，全部通过BoundaryManager
  - [ ] SC确认后 `_boundary_manager.get("SC_LOW").status == PROVISIONAL`
  - [ ] ST确认后 `_boundary_manager.get("SC_LOW").status == LOCKED`
  - [ ] `_build_result().critical_levels` == `_boundary_manager.to_critical_levels()`
  - [ ] pytest tests/ -q → ≥1282 passed

  **QA Scenarios**:
  ```
  Scenario: BoundaryManager生命周期在状态机内正确运行
    Tool: Bash (pytest)
    Steps:
      1. 喂入SC K线 → 验证propose被调用, status==PROVISIONAL
      2. 喂入ST K线（不破SC_LOW）→ 验证lock被调用, status==LOCKED
      3. 验证WyckoffStateResult.critical_levels包含SC_LOW
      4. 触发结构失败 → 验证invalidate被调用
    Expected Result: 完整propose→lock→invalidate生命周期
    Evidence: .sisyphus/evidence/task-7-boundary-lifecycle.txt
  ```

  **Commit**: YES — `feat(sm): BoundaryManager wiring + position_in_tr switch`

---

- [x] 8. position_in_tr切换到内部边界

  **What to do**:
  - `_build_structure_context()` 修改position_in_tr计算逻辑：
    - 优先使用BoundaryManager的SC_LOW/AR_HIGH（内部边界）
    - 无内部边界时fallback到外部 `sm_context["tr_support/resistance"]`
    - 两者都没有时返回0.5（中性）
  - 同步更新 `distance_to_support` 和 `distance_to_resistance` 使用同一组边界
  - `boundaries` 字段改用 `self._boundary_manager.to_critical_levels()`

  **Must NOT do**: 不删除sm_context中的tr_support/tr_resistance（保留fallback）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 2, Depends on T5/T7, Blocks T11/T12

  **References**:
  - `state_machine_v4.py:632-669` — _build_structure_context当前实现
  - `engine.py:902-913` — sm_context构建（tr_support/tr_resistance来源）
  - `bar_features.py:66` — StructureContext.position_in_tr字段

  **Acceptance Criteria**:
  - [ ] 有SC_LOW/AR_HIGH时position_in_tr用内部边界
  - [ ] 无内部边界时fallback到外部TR
  - [ ] 两者都没有时position_in_tr=0.5
  - [ ] pytest tests/ -q → ≥1282 passed

  **QA Scenarios**:
  ```
  Scenario: 内部边界优先于外部TR
    Tool: Bash (pytest)
    Steps:
      1. 设置BoundaryManager有SC_LOW=48000, AR_HIGH=52000
      2. 设置sm_context tr_support=47000, tr_resistance=53000
      3. 喂入close=50000的K线
      4. 验证position_in_tr = (50000-48000)/(52000-48000) = 0.5
    Expected Result: 使用内部边界计算，非外部TR
    Evidence: .sisyphus/evidence/task-8-internal-boundaries.txt
  ```

  **Commit**: NO（与T7合并提交）

---

- [x] 9. StructureHypothesis生命周期管理

  **What to do**:
  - 在 `_confirm_and_advance()` 中：
    - PS/SC/PSY/BC确认时创建StructureHypothesis（confidence=0.2, direction=UNKNOWN）
    - AR/AR_DIST确认时设置direction（ACCUM/DIST）, confidence+=0.15
    - ST/ST_DIST确认时confidence+=0.15
    - Spring/UTAD确认时confidence+=0.2（C阶段方向确认）
    - SOS/SOW确认时confidence+=0.2
    - UPTREND/DOWNTREND确认时structure_hypothesis设为None（结构完成）
  - 结构失败时：设 `structure_hypothesis = None`, mode = TRENDING
  - `_build_result()` 中：如果structure_hypothesis存在，用其confidence影响输出confidence（取max）
  - `_reset_to_idle()` 中清除structure_hypothesis

  **Must NOT do**: 不改WyckoffStateResult字段定义

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**: Wave 2, Depends on T3/T4/T5, Blocks T13

  **References**:
  - `.sisyphus/drafts/cognitive-architecture-decisions.md:43-51` — 共识3：结构级假设
  - `.sisyphus/drafts/wyckoff-theory-constraints.md:435-472` — 待定1+2回答
  - `state_machine_v4.py:564-615` — _confirm_and_advance

  **Acceptance Criteria**:
  - [ ] PS确认后structure_hypothesis非None
  - [ ] SC→AR→ST序列后confidence递增
  - [ ] 结构失败后structure_hypothesis==None
  - [ ] UPTREND确认后structure_hypothesis==None
  - [ ] pytest tests/ -q → ≥1282 passed

  **QA Scenarios**:
  ```
  Scenario: 结构假设随事件序列成长
    Tool: Bash (pytest)
    Steps:
      1. 喂入PS K线 → structure_hypothesis.confidence ≈ 0.2
      2. 喂入SC→AR → confidence > 0.35
      3. 喂入ST → confidence > 0.5
      4. 喂入Spring → confidence > 0.7
    Expected Result: 置信度随事件推进单调递增
    Evidence: .sisyphus/evidence/task-9-structure-hypothesis.txt

  Scenario: 结构失败销毁假设
    Tool: Bash (pytest)
    Steps:
      1. 建立SC_LOW=48000的结构
      2. 喂入close=46000+高volume K线
      3. 验证structure_hypothesis==None且mode==TRENDING
    Expected Result: 跌破SC_LOW放量后假设被销毁
    Evidence: .sisyphus/evidence/task-9-structure-failure.txt
  ```

  **Commit**: NO（与T5合并提交）

---

- [x] 10. event_volumes字段 + 确认时填充

  **What to do**:
  - `StructureContext` 新增字段 `event_volumes: Dict[str, float]`（默认空dict）
  - `_confirm_and_advance()` 中：事件确认时记录该K线成交量到 `self._event_volumes[event_name] = candle["volume"]`
  - `_build_structure_context()` 中：将 `self._event_volumes` 传入 StructureContext
  - `_reset_to_idle()` 中清空 `self._event_volumes`
  - 这样检测器可通过 `context.event_volumes.get("SC", 0)` 获取SC确认时的成交量

  **Must NOT do**: 不改检测器接口，不改BarFeatures

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 3, Depends on T7, Blocks T11/T12

  **References**:
  - `bar_features.py:55-80` — StructureContext dataclass定义
  - `state_machine_v4.py:564-615` — _confirm_and_advance
  - `.sisyphus/drafts/wyckoff-theory-constraints.md:242-268` — VOL-01~10 + ER-01~05规则

  **Acceptance Criteria**:
  - [ ] StructureContext有event_volumes字段
  - [ ] SC确认后context.event_volumes["SC"] > 0
  - [ ] _reset_to_idle后event_volumes为空
  - [ ] pytest tests/ -q → ≥1282 passed

  **QA Scenarios**:
  ```
  Scenario: 事件成交量被正确记录
    Tool: Bash (pytest)
    Steps:
      1. 喂入volume=200000的SC K线
      2. 下一轮检查StructureContext.event_volumes["SC"] == 200000
    Expected Result: 事件成交量在StructureContext中可访问
    Evidence: .sisyphus/evidence/task-10-event-volumes.txt
  ```

  **Commit**: NO（与T11/T12合并提交）

---

- [x] 11. 吸筹检测器增加VOL/ER约束

  **What to do**:
  - STDetector: 增加VOL-01约束 — `context.event_volumes.get("SC")` 存在时，当前volume必须< SC volume，否则conf降低0.2
  - SpringDetector: 增加VOL-05约束 — 跌破时volume < SC volume，否则返回None（FAIL-SP-01）
  - SpringDetector: 增加幅度约束 — 跌破幅度 ≤ 区间高度10%
  - LPSDetector: 增加VOL-03约束 — volume < Spring volume
  - MSOSDetector/JOCDetector: 增加VOL-07/08 — 必须放量（volume_ratio > 1.5）
  - TestDetector: 增加VOL-06 — 连续测试量应递减
  - 所有修改通过StructureContext.event_volumes获取历史量，不改接口

  **Must NOT do**: 不删检测器，不改evaluate签名

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 3, Depends on T2/T8/T10, 可与T12并行

  **References**:
  - `detectors/accumulation.py` — 13个吸筹检测器完整代码
  - `.sisyphus/drafts/wyckoff-theory-constraints.md:242-268` — VOL/ER规则表
  - `.sisyphus/drafts/wyckoff-theory-constraints.md:289-319` — 失败条件

  **Acceptance Criteria**:
  - [ ] ST + volume > SC volume → conf降低
  - [ ] Spring + volume ≥ SC volume → 返回None
  - [ ] SOS/JOC + volume_ratio < 1.5 → 返回None
  - [ ] pytest tests/plugins/test_detectors_v4.py -q → 全PASS（含新增VOL测试）

  **QA Scenarios**:
  ```
  Scenario: VOL-01 ST量必须<SC量
    Tool: Bash (pytest)
    Steps:
      1. 设置event_volumes={"SC": 200000}
      2. 传入volume_ratio=1.5(对应volume>200000)的K线给STDetector
      3. 验证conf降低或返回None
    Expected Result: 高于SC量的ST得到惩罚
    Evidence: .sisyphus/evidence/task-11-vol01-st.txt

  Scenario: FAIL-SP-01 Spring高量被拒绝
    Tool: Bash (pytest)
    Steps:
      1. 设置event_volumes={"SC": 200000}
      2. 传入volume≥200000的跌破K线给SpringDetector
      3. 验证返回None
    Expected Result: 高量Spring被VOL-05过滤
    Evidence: .sisyphus/evidence/task-11-spring-reject.txt
  ```

  **Commit**: YES — `feat(sm): volume constraints VOL/ER + cold start`

---

- [x] 12. 派发检测器增加VOL/ER约束

  **What to do**:
  - STDistDetector: 增加VOL-02 — volume < BC volume
  - UTADDetector: 增加突破+放量+回落三要素验证
  - UTADDetector: 增加幅度约束 — 突破幅度 ≤ 区间高度10%
  - LPSYDetector: 增加VOL-04 — volume < SOW volume
  - MSOWDetector: 增加VOL-09 — 必须放量
  - 所有修改通过context.event_volumes获取历史量

  **Must NOT do**: 不删检测器，不改evaluate签名

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**: Wave 3, Depends on T2/T8/T10, 可与T11并行

  **References**:
  - `detectors/distribution.py` — 9个派发检测器完整代码
  - `.sisyphus/drafts/wyckoff-theory-constraints.md:115-180` — 派发事件定义+量价约束
  - `.sisyphus/drafts/wyckoff-theory-constraints.md:306-309` — UTAD失败条件

  **Acceptance Criteria**:
  - [ ] ST_DIST + volume > BC volume → conf降低
  - [ ] SOW + volume_ratio < 1.5 → 返回None
  - [ ] pytest tests/plugins/test_detectors_v4.py -q → 全PASS

  **QA Scenarios**:
  ```
  Scenario: VOL-02 ST_DIST量必须<BC量
    Tool: Bash (pytest)
    Steps:
      1. 设置event_volumes={"BC": 300000}
      2. 传入volume>300000的K线给STDistDetector
      3. 验证conf降低
    Expected Result: 高于BC量的ST_DIST得到惩罚
    Evidence: .sisyphus/evidence/task-12-vol02-st-dist.txt
  ```

  **Commit**: NO（与T11合并提交）

---

- [x] 13. 冷启动行为实现

  **What to do**:
  - `process_candle()` 开头增加冷启动逻辑：
    - 统计数据（_recent_closes/highs/lows, _scorer的MA20等）始终积累
    - 但在 `market_mode == TRENDING` 且 `structure_hypothesis is None` 时，仅允许停止行为检测
    - 这与T5的TRENDING模式gate自然一致，无需额外代码
  - 验证：前20根平稳K线不产生任何事件假设

  **Must NOT do**: 不加固定N根K线预热，用模式机制自然实现

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**: Wave 3, Depends on T9

  **References**:
  - `.sisyphus/drafts/cognitive-architecture-decisions.md:59-65` — 共识5：冷启动定义
  - `state_machine_v4.py:218-261` — process_candle

  **Acceptance Criteria**:
  - [ ] 前20根平稳K线后 last_confirmed_event == "IDLE"
  - [ ] mode == TRENDING
  - [ ] 统计数据（_recent_closes）正常积累
  - [ ] pytest tests/ -q → ≥1282 passed

  **QA Scenarios**:
  ```
  Scenario: 冷启动不产生虚假事件
    Tool: Bash (pytest)
    Steps:
      1. 创建V4实例
      2. 喂入20根平稳K线(close=50000±0.1%, volume=100000±10%)
      3. 验证last_confirmed_event=="IDLE", mode==TRENDING
      4. 验证_recent_closes长度==20
    Expected Result: 无虚假检测，统计正常积累
    Evidence: .sisyphus/evidence/task-13-cold-start.txt
  ```

  **Commit**: NO（与T11合并提交）

---

## Final Verification Wave

> 4个审查agent并行运行。全部APPROVE后提交给用户确认。

- [x] F1. **计划合规审计** — `oracle`
  逐项检查Must Have/Must NOT Have。验证evidence文件存在。
  Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT`

- [x] F2. **代码质量审查** — `unspecified-high`
  运行 pytest tests/ -q + pylint。检查 as any、空catch、console.log等。
  Output: `Tests [N pass] | Lint [PASS/FAIL] | VERDICT`

- [x] F3. **全量QA** — `unspecified-high`
  执行每个Task的QA场景，截图/输出到 `.sisyphus/evidence/final-qa/`。
  Output: `Scenarios [N/N pass] | VERDICT`

- [x] F4. **范围保真检查** — `deep`
  对比git diff与计划spec，验证1:1实现无遗漏无越界。
  Output: `Tasks [N/N compliant] | VERDICT`

---

## Commit Strategy

| Wave | Commit | Files | Pre-commit |
|------|--------|-------|------------|
| 1 | `fix(sm): transition_history from==to bug` | state_machine_v4.py, test_state_machine_v4.py | pytest tests/plugins/test_state_machine_v4.py -q |
| 1 | `test(sm): shared factory + 10 detector positive tests + regression scenarios` | tests/fixtures/*, test_detectors_v4.py, test_sm_regression.py | pytest tests/plugins/ -q |
| 2 | `feat(sm): MarketMode + BoundaryManager + StructureHypothesis` | state_machine_v4.py, transition_guard.py, boundary_manager.py, test_*.py | pytest tests/ -q |
| 3 | `feat(sm): volume constraints VOL/ER + cold start` | accumulation.py, distribution.py, test_detectors_v4.py | pytest tests/ -q |

---

## Success Criteria

### 验证命令
```bash
pytest tests/ -q  # Expected: ≥1282 passed, 0 failed
pytest tests/plugins/test_state_machine_v4.py -v  # Expected: ≥50 passed
pytest tests/plugins/test_detectors_v4.py -v  # Expected: ≥40 passed
```

### 最终检查清单
- [ ] MarketMode三模式正确切换
- [ ] BoundaryManager管理所有critical_levels
- [ ] position_in_tr使用内部边界（无边界时fallback外部TR）
- [ ] VOL-01~06量递减规则在检测器中强制执行
- [ ] StructureHypothesis在停止行为时创建，结构失败时销毁
- [ ] 冷启动=TRENDING直到第一个停止行为
- [ ] WyckoffStateResult接口零变化
- [ ] 全部1282+测试通过
