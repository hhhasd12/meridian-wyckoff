HANDOFF CONTEXT - 进化系统诊断与修复
======================================

GOAL
----
修复进化系统的 13 个 bug，让 run_evolution.py 能真正进化（当前跑了 6394 轮，COMPOSITE_SCORE 始终为 0.0，所有变异全被拒绝）。

WORK COMPLETED (本次会话)
--------------------------
- 完成 v2.1 架构清理：删除 src/state, src/logs, src/storage, src/data, scripts/, specs/
- 入口统一：run_live.py 合并进 run.py，删除 run_live.py
- Perception 迁移：src/perception/ 迁入 src/plugins/perception/
- Agent 框架整合：src/agents/ + src/communication/ + src/visualization/ + src/backtest/ 迁入 src/plugins/agent_teams/
- 测试重组：tests/core/ 清理，散乱测试归类
- 文档同步：README.md、AGENTS.md 更新为 v2.1
- 验证通过：540 passed, 0 failed
- 完成进化系统深度诊断（以下为诊断结果）

CURRENT STATE
-------------
- 测试：540 passed, 0 failed
- 大量未提交的更改（架构清理 + 文档更新）
- run_evolution.py 第 72 行有一个已失效的 import: from src.data.loader import DataLoader（src/data/ 已删除）
- 进化系统跑了 6394 轮，evolution_results/ 下有 11862 个 JSON 文件，全部 COMPOSITE_SCORE=0.0

EVOLUTION SYSTEM DIAGNOSIS (13 BUGS)
-------------------------------------

P0 — FATAL BUGS (不修这些，进化永远不可能工作)

BUG-1: WeightVariator 从未连接到 MistakeBook
  文件: src/plugins/self_correction/workflow.py 第 126-134 行
  问题: SelfCorrectionWorkflow.__init__() 创建了 weight_variator 和 mistake_book，但从未调用 weight_variator.set_mistake_book(mistake_book)
  影响: weight_variator._mutate_configuration() 中 self.mistake_book 始终为 None，所有变异都走 _random_mutate()
  修复: 在 __init__() 第 134 行后添加 self.weight_variator.set_mistake_book(self.mistake_book)

BUG-2: _mutate_configuration() 忽略传入的 weight_adjustments
  文件: src/plugins/evolution/weight_variator_legacy.py 第 813-854 行
  问题: evolve_from_existing() 传入 weight_adjustments 参数，但 _mutate_configuration() 不接受该参数，而是自己调用 self.mistake_book.generate_weight_adjustments()（而 self.mistake_book 是 None）
  影响: pattern_based_mutations 永远为 0
  修复: 修改 _mutate_configuration 签名接受 weight_adjustments 参数并使用它

BUG-3: confidence_threshold 从未应用到状态机
  文件: run_evolution.py 第 250-253 行 vs 第 264 行
  问题: confidence_threshold 从 config 中读取了，但只用在 line 362 的信号门控比较中，从未设置到 wyckoff_sm.config.STATE_MIN_CONFIDENCE
  影响: 变异 confidence_threshold 参数对信号生成零效果
  修复: 在 line 265 添加 wyckoff_sm.config.STATE_MIN_CONFIDENCE = confidence_threshold

P1 — HIGH SEVERITY (导致反馈循环和错误污染)

BUG-4: WFA 拒绝被记录为交易错误（致命反馈循环）
  文件: src/plugins/evolution/wfa_backtester.py 第 809-839 行 _record_validation_failure()
  问题: 每次 WFA 拒绝一个变异，就向 mistake_book 记录一条 WEIGHT_ASSIGNMENT_ERROR + VOLATILITY_ADAPTATION_ERROR
  影响: 6394 轮后错题本有 9639 条假错误，全部来自 WFA 拒绝而非真实交易失误。错题本被自己的噪音淹没
  修复: 删除 _record_validation_failure() 中的 mistake_book.record_mistake() 调用，或用独立的 validation_log 替代

BUG-5: pattern_detection_threshold = 0.7 太高
  文件: src/plugins/self_correction/mistake_book.py 第 259-261 行
  问题: 错误模式必须在 70% 以上的错误记录中出现才能被识别
  影响: 15 个种子错误中，任何模式最多出现 5 次（33%），远低于 70% 阈值，所以 analyze_patterns() 永远返回空
  修复: 降低到 0.1 或 0.15

BUG-6: 种子错误是随机生成的假数据
  文件: run_evolution.py 第 423-473 行 seed_mistake_book()
  问题: 用 random.choice 生成 15 个假错误，不对应任何真实交易场景
  影响: 模式分析无法从随机数据中提取有意义的方向
  修复: 改为从首次回测结果中记录真实交易错误

BUG-7: 没有真实错误录入机制
  文件: run_evolution.py 第 226-420 行 real_performance_evaluator()
  问题: 回测产生的亏损交易从未调用 mistake_book.record_mistake()
  影响: 错题本完全脱离真实交易结果
  修复: 在回测后遍历亏损交易，调用 mistake_book.record_mistake() 记录真实错误

P2 — MEDIUM SEVERITY (影响收敛速度和结果质量)

BUG-8: WFA 传入 train+test 完整窗口而非仅 test 窗口
  文件: src/plugins/evolution/wfa_backtester.py 第 489-495 行
  问题: 注释说"必须传入完整窗口否则 MA 全为 NaN"，但这导致评估器看到训练数据（数据泄漏）
  修复: 传入 test 窗口但预留足够的 warmup 期（如前 50 根 K 线）

BUG-9: StateConfig.STATE_MIN_CONFIDENCE 硬编码为 0.35
  文件: src/kernel/types.py 第 575-587 行
  问题: STATE_MIN_CONFIDENCE = 0.35 从未被 config 修改
  影响: 如果 PhaseDetector 的置信度低于 0.35，不会产生任何信号
  修复: 让 real_performance_evaluator 从 config 设置此参数

BUG-10: 错误标记为"已学习"即使 WFA 全部拒绝
  文件: src/plugins/self_correction/workflow.py 第 639-645 行
  问题: _update_configuration() 中即使 WFA 拒绝所有变异，仍然 mark_batch_as_learned()
  修复: 仅在有变异被接受时才标记为已学习

BUG-11: Auto-cleanup 30 天后清空错题本
  文件: src/plugins/self_correction/mistake_book.py 第 341-358 行
  问题: 30 天后所有错误被删除，错题本变空，系统回退到纯随机模式
  修复: 保留最近 N 条错误而非按时间清理

BUG-12: COMPOSITE_SCORE 计算有 max(0.0) 截断
  文件: wfa_backtester.py 第 629 行
  问题: Sharpe 为负时 max(0.0, sharpe) * 0.25 = 0，导致 COMPOSITE_SCORE 被截到 0
  修复: 允许负数参与计算，或使用 sigmoid 映射

BUG-13: run_evolution.py 第 72 行 import 已失效
  文件: run_evolution.py 第 72 行
  问题: from src.data.loader import DataLoader — src/data/ 已在本次清理中删除
  修复: 删除该 import（实际未使用，数据通过 CSV 直接加载）

KEY FILES
---------
- src/plugins/self_correction/workflow.py — SelfCorrectionWorkflow 主循环
- src/plugins/self_correction/mistake_book.py — 错题本
- src/plugins/evolution/weight_variator_legacy.py — 权重变异器
- src/plugins/evolution/wfa_backtester.py — WFA 回测验证
- run_evolution.py — 进化启动脚本
- src/plugins/agent_teams/backtest/engine.py — 回测引擎
- src/kernel/types.py — StateConfig 定义
- src/plugins/wyckoff_state_machine/state_machine_core.py — 状态机核心

RECOMMENDED FIX ORDER
---------------------
1. 先修 BUG-13（import 失效，否则 run_evolution.py 无法启动）
2. 修 BUG-1 + BUG-2（连接 WeightVariator 到 MistakeBook，让定向变异生效）
3. 修 BUG-3 + BUG-9（让 config 参数真正影响信号生成）
4. 修 BUG-4（打破 WFA 拒绝 → 假错误 → 更多拒绝的死循环）
5. 修 BUG-5 + BUG-6 + BUG-7（让错题本有真实、可用的错误数据）
6. 修 BUG-8 + BUG-10 + BUG-11 + BUG-12（提升收敛质量）
7. 跑一轮进化验证：Score 应该不再是 0.0，应该有变异被接受

EXPLICIT CONSTRAINTS
--------------------
- 进化盘用本地 CSV 数据，不依赖实时数据
- 进化盘和实盘完全分离，互不影响
- 策略必须经过进化验证后才能进入实盘
- 代码风格遵循 AGENTS.md（Black 格式化，Google docstring，类型注解）
