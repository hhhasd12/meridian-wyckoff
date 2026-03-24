# Handoff: 认知架构重构完成 → 标注驱动进化系统

> Session: ses_2e6a385b8ffeQ7tWBICeO6qjRa
> Date: 2026-03-23
> Commit: 48e4f0e

## 本次完成

### 认知架构重构 (T1-T13 全部完成)
- MarketMode 三模式门控 (TRENDING/TRANSITIONING/RANGING)
- BoundaryManager 接入 _confirm_and_advance (propose→lock→invalidate)
- StructureHypothesis 结构假设生命周期
- position_in_tr 优先内部边界, fallback外部TR
- event_volumes 在 StructureContext 中供检测器跨事件量比较
- 10个检测器 VOL-01~09 量价约束
- 冷启动 = TRENDING 模式自然门控
- transition_history from==to bug 修复
- 结构完成(UPTREND/DOWNTREND)时清理BoundaryManager修复
- **测试**: 95 V4 + 236 广域测试通过

### AGENTS.md 更新
- 核心设计哲学写入：进化核心是状态机进化

### 计划定稿
- `.sisyphus/plans/annotation-driven-evolution.md` — 5 Wave 标注驱动进化系统

## 真实数据诊断结果

ETH/USDT H4 最近2000根：
- 244次状态变化，31个完整结构，平均55根/结构(9天)
- 仍然太频繁（真实市场一年2-3个结构）
- 根因：检测器只看单根K线特征，不看K线组合/宏观位置
- SPRING↔TEST 反复弹跳（46根跳6次）

## 下一步执行计划

### Wave 1: 基础设施 (2-3天)
- T1.1: Hypothesis 加 bar_range 字段
- T1.2: 22个检测器暴露 get_evolvable_params()
- T1.3: 标注数据模型 + 存储 (annotation 插件)
- T1.4: 标注 CRUD API

### Wave 2: 前端标注工具 (3-4天)
- T2.1: AnnotationLayer.ts (基于 TRBoundaryBox.ts 模式)
- T2.2: 标注模式交互 (范围选择 + 水平线)
- T2.3: 前后端联通

### Wave 3: 对比引擎 (2天)
- T3.1: AnnotationMatcher
- T3.2: 差异可视化
- T3.3: 标注匹配度接入 fitness

### Wave 4: AI诊断对话 (3-4天)
- T4.1-4.3: 对话式诊断 + 图表联动
- T4.4: 结构化修改建议输出
- T4.5: 检测器知识库（AI学习层）
- **待验证**: VCP Agent 接入替代自建AI层

### Wave 5: 闭环 (2天)
- T5.1-5.3: GA优化 + 回归守护 + 增量标注

## VCP 衔接方案（待验证）

用户本地有 VCP 系统 (F:\VCPToolBox\VCP)，拥有：
- TagMemo V6 LIF 脉冲记忆系统
- 元思考系统
- 79个插件生态
- Rust 向量引擎

**接法设想**：VCP Agent 通过 HTTP API 调用 Wyckoff 系统，
结合 VCP 记忆系统替代自建的简陋 JSONL 规则库。
**但两个系统的衔接可行性待下个session验证。**

## 关键文件

| 文件 | 说明 |
|------|------|
| `.sisyphus/plans/annotation-driven-evolution.md` | 标注进化计划（定稿） |
| `.sisyphus/drafts/wyckoff-theory-constraints.md` | 威科夫理论约束 (520行) |
| `.sisyphus/drafts/cognitive-architecture-decisions.md` | 认知架构设计决策 |
| `src/plugins/wyckoff_state_machine/state_machine_v4.py` | V4 状态机（1080行） |
| `src/plugins/wyckoff_state_machine/detectors/accumulation.py` | 13个吸筹检测器 |
| `src/plugins/wyckoff_state_machine/detectors/distribution.py` | 9个派发检测器 |
| `tests/plugins/test_state_machine_v4.py` | 49个V4测试 |
| `tests/plugins/test_detectors_v4.py` | 46个检测器测试 |

## 用户核心诉求

1. 状态机识别不准，需要通过标注→学习闭环来修正
2. 系统应该是无限进化的
3. AI不直接改代码，AI输出诊断→coding agent执行
4. 威科夫主观变体多，需要弹性处理
5. 标注是上帝视角，但学到的是事件特征（实时可观测）
6. VCP系统可能提供AI记忆层，但衔接可行性待验证
