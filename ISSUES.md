# 系统问题清单

**分析日期**: 2026-03-02
**测试状态**: 305 passed, 51 skipped ✅
**整体健康**: 功能正常，但存在结构性问题和技术债务

---

## 一、架构与导入问题 🔴 高优先级

### 1.1 Legacy/New 双层结构混乱
当前三个核心模块都存在 "shim文件 + legacy文件 + 新包" 的三层结构，导致导入链极其混乱：

| 模块 | Shim文件 | Legacy文件 | 新包 | 问题 |
|------|----------|------------|------|------|
| 系统协调器 | `system_orchestrator.py` | `system_orchestrator_legacy.py` | `orchestrator/` | shim同时从legacy和orchestrator包导入 |
| 权重变异器 | `weight_variator.py` | `weight_variator_legacy.py` | `evolution/` | shim从legacy导入，evolution包也从legacy导入 |
| 状态机 | `wyckoff_state_machine/` | `wyckoff_state_machine_legacy.py` | 包内部 | 包的`__init__.py`直接从legacy导入 |

**导入链示例**:
```
system_orchestrator.py (shim)
  → system_orchestrator_legacy.py (实际代码)  ←
  → orchestrator/__init__.py → system_orchestrator_legacy.py (循环!)
```

**建议修复**: 选择一种结构，要么删除legacy文件，要么删除新包结构，保持一致。

### 1.2 混用绝对路径和相对导入
`system_orchestrator_legacy.py` 使用相对导入 (`from .data_pipeline import ...`)，但 `orchestrator/__init__.py` 使用绝对路径 (`from src.core.system_orchestrator_legacy import ...`)。两种风格混用会在不同运行方式下产生问题。

### 1.3 FVGDetector 的 try/except 导入
在 `system_orchestrator.py` 和 `system_orchestrator_legacy.py` 中，`FVGDetector` 用 try/except 进行双路径导入，且 None 作为 fallback，导致运行时静默失败。

---

## 二、实际代码 Bug 🔴 高优先级

### 2.1 tr_detector.py 类型错误
```
src/core/tr_detector.py:619:23: E1136 Value 'pending' is unsubscriptable
```
变量 `pending` 被当作下标访问但类型不支持，需要修复。

### 2.2 51 个测试被跳过
pytest 输出显示 **51个测试被跳过** (skipped)，需要检查原因，排除以下可能：
- 缺少外部依赖（Redis、真实API等）
- 被 `@pytest.mark.skip` 标记的测试是否为遗留问题
- 某些测试条件永远不满足

---

## 三、重复入口点问题 🟡 中优先级

### 3.1 多个功能重叠的启动脚本
| 文件 | 功能 | 和谁重叠 |
|------|------|----------|
| `run_live.py` | 生产环境启动（守护进程）| `run_system.py` |
| `run_system.py` | 持续运行系统协调器 | `run_live.py` |
| `run_evolution.py` | 无限进化循环 | `run_evolution_demo.py` |
| `run_evolution_demo.py` | 进化演示（简化版） | `run_evolution.py` |

**建议**: 合并 `run_live.py` 和 `run_system.py` 为单一入口，保留一个 `run_evolution.py`。

### 3.2 数据获取脚本大量重复
`scripts/` 目录下存在过多功能相近的脚本：
- `fetch_all.py` 和 `fetch_all2.py`（后者是"修复版"）
- `fetch_real.py` 和 `fetch_real2.py`（后者是"修复版"）
- `fetch_eth_history.py`, `fetch_full.py`, `fetch_max.py`, `fetch_multi.py`, `fetch_strong.py`

**建议**: 只保留 1-2 个功能完整的数据获取脚本。

---

## 四、模块职责冲突 🟡 中优先级

### 4.1 DataPipeline 命名冲突
- `src/core/data_pipeline.py` — 核心数据管道（多周期同步、缓存）
- `src/core/orchestrator/flow.py` 中的 `DataPipeline` 类 — 同名但不同功能

外部代码 `from src.core.orchestrator import DataPipeline` 获取的是 flow.py 中的类，不是 core/data_pipeline.py 中的类，容易混淆。

### 4.2 data/ 目录与 src/data/ 混存
- `data/binance.py` — 根目录下的独立脚本（下载数据用）
- `src/data/binance_fetcher.py` — 项目正式的 Binance 数据获取模块

两个文件功能重叠，根目录的 `data/binance.py` 应该删除或移入 scripts/。

---

## 五、测试文件放置问题 🟡 中优先级

以下文件位于根目录，但 `tests/` 目录已有对应的正式测试版本：

| 根目录文件 | tests/ 中的对应文件 |
|-----------|---------------------|
| `test_decision_visualizer.py` | `tests/core/test_decision_visualizer.py` |
| `test_system_orchestrator.py` | `tests/core/test_system_orchestrator.py` |
| `test_weight_variator.py` | `tests/core/test_weight_variator.py` |

这3个根目录文件是早期调试文件，现在是冗余的。

---

## 六、self_correction_workflow.py 未测试 🟡 中优先级

`src/core/self_correction_workflow.py` 是核心进化模块（错题本→权重变异→WFA→配置更新的闭环），但在 `tests/` 中只有 `tests/core/test_self_correction_workflow.py` 覆盖。需确认该测试是否在 51 个 skipped 中。

---

## 七、文档冗余问题 🟢 低优先级

根目录存在大量过时的文档和报告文件（已在本次清理中删除），详见下方清理记录。

---

## 八、已完成清理记录

本次清理删除的文件：

### 根目录冗余文件
- `core_logic_verification.txt` — 乱码验证日志，已过时
- `performance_test.log` — 旧性能测试日志
- `performance_test_real_data.log` — 旧性能测试日志
- `performance_test_real_data_report.txt` — 旧报告
- `performance_test_report.txt` — 旧报告
- `simple_test_result.txt` — 旧测试结果
- `test_results.json` — 旧测试结果
- `test_system_state.json` — 旧系统状态
- `system_run.log` — 旧运行日志
- `performance_optimization_completed.md` — 旧文档
- `performance_optimization_task_final_report.md` — 旧文档
- `测试接口变更报告.md` — 旧报告
- `SYSTEM_ERRORS.md` — 只含一行 pylint 分数
- `Pending_Tasks.md` — 内容为空（无待完成任务）
- `AUTOMATED_BACKTEST_FRAMEWORK_REPORT.md` — 旧报告
- `DATA_PIPELINE_TEST_SUMMARY.md` — 旧报告
- `GAP_ANALYSIS_REPORT.md` — 旧报告
- `PLAN_INDEX.md` — 旧规划文档
- `PROJECT_COMPLETION_REPORT.md` — 旧报告
- `AUTOMATION.md` — 内容已包含在 README 和 AGENTS.md 中

### 根目录重复测试文件（tests/ 已有对应版本）
- `test_decision_visualizer.py`
- `test_system_orchestrator.py`
- `test_weight_variator.py`

### 整个目录删除
- `archive_2026/` — 旧历史存档
- `deprecated/` — 已标记废弃的调试和验证脚本
- `evolution_results/` — 运行时生成的演示数据
- `htmlcov/` — 覆盖率报告（可用 pytest --cov 重新生成）
- `status/` — 运行时状态 JSON 文件
- `reports/` — 运行时健康报告文件
- `logs/snapshots/` — 大量运行时截图
- `logs/snapshots/system_test/` — 系统测试截图

### docs/ 内旧规划文档
- `docs/REFACTORING_PLAN.md` — 旧重构计划（重构已完成）
- `docs/REFACTORING_STATUS.md` — 旧重构状态
- `docs/TODO_CLEANUP.md` — 旧待办
- `docs/SYSTEM_DIAGNOSIS.md` — 旧诊断报告

### scripts/ 重复脚本
- `scripts/fetch_all.py` — 被 fetch_all2.py 替代
- `scripts/fetch_real.py` — 被 fetch_real2.py 替代

---

## 九、建议的下一步修复顺序

### 第一步（必须修复）
1. **修复 `tr_detector.py:619` 的 unsubscriptable 错误**
2. **检查并修复 51 个 skipped 测试** — 确认哪些是正当 skip，哪些是被遗忘的 bug

### 第二步（强烈建议）
3. **统一 legacy 结构** — 选择保留 legacy 文件 OR 新包结构，删除另一个，消除双层导入混乱
4. **合并 run_live.py 和 run_system.py** — 统一为单一生产入口

### 第三步（有条件时）
5. **清理 scripts/ 重复数据脚本** — 保留最终版本，删除迭代草稿
6. **解决 DataPipeline 命名冲突** — `orchestrator/flow.py` 中的类重命名
7. **删除 `data/binance.py`** — 功能已被 `src/data/binance_fetcher.py` 覆盖
