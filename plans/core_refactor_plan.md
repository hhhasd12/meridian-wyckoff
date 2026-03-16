# src/core/ 安全重构计划

> **生成日期**: 2026-03-16
> **状态**: 待执行
> **目标**: 将所有 `src.core.*` 引用迁移到 `src.plugins.*`，最终清空 `src/core/`

---

## 一、文件分类清单（35个 .py 文件）

### 1.1 纯 Shim 文件（19个）— 已正确指向 `src.plugins.*`

| # | 文件 | 大小 | 指向插件模块 |
|---|------|------|-------------|
| 1 | `anomaly_validator.py` | 681B | `src.plugins.risk_management.anomaly_validator` |
| 2 | `breakout_validator.py` | 532B | `src.plugins.signal_validation.breakout_validator` |
| 3 | `circuit_breaker.py` | 727B | `src.plugins.risk_management.circuit_breaker` |
| 4 | `config_system.py` | 1.1KB | `src.plugins.orchestrator.config_types` |
| 5 | `conflict_resolver.py` | 579B | `src.plugins.signal_validation.conflict_resolver` |
| 6 | `curve_boundary.py` | 561B | `src.plugins.pattern_detection.curve_boundary` |
| 7 | `data_pipeline.py` | 544B | `src.plugins.data_pipeline.data_pipeline` |
| 8 | `data_sanitizer.py` | 832B | `src.plugins.data_pipeline.data_sanitizer` |
| 9 | `decision_visualizer.py` | 475B | `src.plugins.dashboard.decision_visualizer` |
| 10 | `evolution_archivist.py` | 560B | `src.plugins.evolution.archivist` |
| 11 | `micro_entry_validator.py` | 587B | `src.plugins.signal_validation.micro_entry_validator` |
| 12 | `mistake_book.py` | 732B | `src.plugins.self_correction.mistake_book` |
| 13 | `performance_monitor.py` | 541B | `src.plugins.dashboard.performance_monitor` |
| 14 | `period_weight_filter.py` | 491B | `src.plugins.weight_system.period_weight_filter` |
| 15 | `self_correction_workflow.py` | 692B | `src.plugins.self_correction.workflow` |
| 16 | `tr_detector.py` | 540B | `src.plugins.pattern_detection.tr_detector` |
| 17 | `wfa_backtester.py` | 660B | `src.plugins.evolution.wfa_backtester` |
| 18 | `wyckoff_context_builder.py` | 967B | `src.plugins.wyckoff_state_machine.context_builder` |
| 19 | `wyckoff_phase_detector.py` | 515B | `src.plugins.pattern_detection.wyckoff_phase_detector` |

### 1.2 "伪 Shim" 文件（3个）— 声称是 shim 但实际指向 legacy

| # | 文件 | 大小 | 实际指向 |
|---|------|------|---------|
| 20 | `system_orchestrator.py` | 3.4KB | ⚠️ `system_orchestrator_legacy` + 大量 shim 聚合重导出 |
| 21 | `weight_variator.py` | 467B | ⚠️ `weight_variator_legacy`（不是插件） |
| 22 | `wyckoff_state_machine/__init__.py` | 1.6KB | ⚠️ `wyckoff_state_machine_legacy`（不是插件） |

### 1.3 Legacy 文件（3个）— 包含实际业务逻辑

| # | 文件 | 大小 | 导出的类 |
|---|------|------|---------|
| 23 | `system_orchestrator_legacy.py` | 119KB | `SystemOrchestrator` |
| 24 | `wyckoff_state_machine_legacy.py` | 159KB | `WyckoffStateMachine`, `EnhancedWyckoffStateMachine`, `EvidenceChainManager` |
| 25 | `weight_variator_legacy.py` | 48KB | `MutationOperator`, `ThresholdMutationOperator`, `WeightMutationOperator`, `WeightVariator` |

### 1.4 含实际逻辑的子模块（8个）— 未迁移到插件层

| # | 文件 | 大小 | 包含的逻辑 |
|---|------|------|-----------|
| 26 | `orchestrator/__init__.py` | 1.9KB | 聚合重导出（从 legacy + 子模块） |
| 27 | `orchestrator/config.py` | 5.7KB | `SystemMode`, `DecisionContext`, `TradingSignal` 等数据类 |
| 28 | `orchestrator/flow.py` | 7.2KB | `DataFlowPipeline`, `DecisionPipeline` |
| 29 | `orchestrator/health.py` | 5.2KB | `HealthStatus`, `AlertLevel`, `HealthChecker` |
| 30 | `orchestrator/registry.py` | 5.6KB | `ModuleRegistry` |
| 31 | `wyckoff_state_machine/evidence_chain.py` | 5.2KB | `EvidenceChainManager` |
| 32 | `wyckoff_state_machine/state_definitions.py` | 4.1KB | 状态枚举和数据类 |
| 33 | `evolution/__init__.py` | 954B | 聚合导出（从 `weight_variator_legacy`） |
| 34 | `evolution/operators.py` | 7.4KB | `MutationOperator` 系列类 |

### 1.5 空文件

| # | 文件 |
|---|------|
| 35 | `__init__.py`（0B） |

---

## 二、Shim 引用关系矩阵

标注说明：🧪=测试 📜=生产脚本 📦=src生产代码 📚=示例

### 2.1 每个 shim 的引用者

**`anomaly_validator`**
- 🧪 `tests/test_fixes_validation.py`, `tests/integration_test.py`, `tests/system_integration_e2e.py`, `tests/integration_test_system_logic.py`, `tests/core/test_anomaly_validator.py`
- 📦 `src/core/system_orchestrator.py`
- 📦 `src/plugins/data_pipeline/data_sanitizer.py` ← 插件反向依赖!

**`breakout_validator`**
- 🧪 `tests/integration_test.py`, `tests/system_integration_e2e.py`, `tests/integration_test_system_logic.py`, `tests/core/test_breakout_validator.py`
- 📚 4个示例文件
- 📦 `src/core/system_orchestrator.py`

**`circuit_breaker`**
- 🧪 `tests/test_fixes_validation.py`, `tests/integration_test.py`, `tests/system_integration_e2e.py`, `tests/integration_test_system_logic.py`, `tests/core/test_circuit_breaker.py`
- 📦 `src/core/system_orchestrator.py`
- 📦 `src/plugins/data_pipeline/data_sanitizer.py` ← 插件反向依赖!

**`config_system`**
- 🧪 `tests/core/test_config_system.py`, `tests/core/test_config_system_simple.py`, `tests/integration_test_system_logic.py`

**`conflict_resolver`**
- 🧪 `tests/core/test_conflict_resolver.py`
- 📚 4个示例文件
- 📦 `src/core/system_orchestrator.py`, `src/agents/strategy_optimizer_agent.py`

**`curve_boundary`**
- 🧪 `tests/test_geometry_simple.py`, `tests/test_geometry_fix.py`, `tests/integration_test.py`, `tests/system_integration_e2e.py`, `tests/core/test_curve_boundary.py`
- 📚 3个示例文件
- 📦 `src/core/system_orchestrator.py`

**`data_pipeline`**
- 🧪 `tests/test_data_pipeline_validation.py`, `tests/test_custom_api.py`, `tests/system_integration_e2e.py`, `tests/integration_test.py`, `tests/core/test_data_pipeline.py`
- 📚 3个示例文件
- 📦 `src/core/system_orchestrator.py`

**`data_sanitizer`**
- 🧪 `tests/test_timestamp_simple.py`, `tests/system_integration_e2e.py`, `tests/integration_test_system_logic.py`, `tests/core/test_data_sanitizer.py`
- 📦 `src/core/system_orchestrator.py`

**`decision_visualizer`**
- 🧪 `tests/test_integration_simple.py`, `tests/core/test_decision_visualizer.py`
- 📦 `src/core/system_orchestrator.py`

**`evolution_archivist`**
- 🧪 `tests/verify_archivist.py`, `tests/test_archivist_fix.py`, `tests/test_archivist_complete.py`, `tests/debug_archivist.py`, `tests/core/test_evolution_archivist.py`
- 📚 `examples/automated_evolution_integration.py`
- 📦 `src/core/system_orchestrator.py`

**`micro_entry_validator`**
- 🧪 `tests/system_integration_e2e.py`, `tests/core/test_micro_entry_validator.py`
- 📚 4个示例文件
- 📦 `src/core/system_orchestrator.py`

**`mistake_book`**（引用最多）
- 🧪 5个测试文件
- 📜 `run_evolution.py`
- 📚 3个示例文件
- 📦 `src/core/system_orchestrator.py`, `src/core/evolution/operators.py`
- 📦 `src/plugins/evolution/wfa_backtester.py`, `src/plugins/evolution/plugin.py` ← 插件反向依赖!
- 📦 `src/agents/strategy_optimizer_agent.py`

**`performance_monitor`**
- 🧪 `tests/core/test_performance_monitor.py`
- 📚 3个示例文件
- 📦 `src/core/system_orchestrator.py`

**`period_weight_filter`**
- 🧪 `tests/core/test_period_weight_filter.py`, `tests/system_integration_e2e.py`
- 📜 `run_evolution.py`
- 📚 4个示例文件
- 📦 `src/core/system_orchestrator.py`, `src/agents/strategy_optimizer_agent.py`

**`self_correction_workflow`**
- 🧪 `tests/test_simple_backtest.py`, `tests/core/test_self_correction_workflow.py`
- 📜 `run_evolution.py`
- 📦 `src/plugins/evolution/plugin.py` ← 插件反向依赖!
- 📦 `src/agents/strategy_optimizer_agent.py`

**`tr_detector`**
- 🧪 `tests/test_geometry_fix.py`, `tests/integration_test.py`, `tests/system_integration_e2e.py`, `tests/integration_test_system_logic.py`, `tests/core/test_tr_detector.py`
- 📚 3个示例文件
- 📦 `src/core/system_orchestrator.py`

**`wfa_backtester`**
- 🧪 `tests/test_simple_backtest.py`, `tests/test_automated_backtest_framework.py`, `tests/core/test_wfa_backtester.py`
- 📜 `run_evolution.py`
- 📚 2个示例文件
- 📦 `src/core/system_orchestrator.py`
- 📦 `src/plugins/evolution/plugin.py` ← 插件反向依赖!
- 📦 `src/agents/strategy_optimizer_agent.py`

**`wyckoff_context_builder`**
- 📦 `src/agents/strategy_optimizer_agent.py`（3处）

**`wyckoff_phase_detector`**
- ✅ **无任何引用** — 可直接删除

**`weight_variator`**（伪shim → legacy）
- 🧪 3个测试文件
- 📜 `run_evolution.py`
- 📚 2个示例文件
- 📦 `src/core/system_orchestrator.py`
- 📦 `src/plugins/evolution/plugin.py` ← 插件反向依赖!
- 📦 `src/agents/strategy_optimizer_agent.py`

**`wyckoff_state_machine/`**（伪shim → legacy）
- 🧪 3个测试文件
- 📜 `run_evolution.py`
- 📚 5个示例文件
- 📦 `src/core/system_orchestrator.py`
- 📦 `src/agents/strategy_optimizer_agent.py`(3处), `src/agents/backtest_validator_agent.py`(2处)

**`system_orchestrator`**（伪shim → legacy 的聚合器）
- 🧪 `tests/test_timestamp_simple.py`, `tests/test_timestamp_fix.py`, `tests/test_integration.py`, `tests/system_integration_e2e.py`, `tests/integration_test_system_logic.py`, `tests/kernel/test_types.py`, `tests/core/test_system_orchestrator.py`

### 2.2 缺失的 Shim

**`src.core.market_regime`** 被6个文件导入但文件不存在：
- 📜 `run_evolution.py`
- 📚 5个示例文件
- 正确路径应为 `src.plugins.market_regime.detector`

### 2.3 插件层反向依赖 core（架构违规）

以下插件文件导入了 `src.core`，违反"插件只依赖 kernel"原则：

| 插件文件 | 导入的 src.core 模块 |
|---------|---------------------|
| `src/plugins/wyckoff_state_machine/plugin.py` | `src.core.wyckoff_state_machine_legacy` |
| `src/plugins/evolution/plugin.py` | `src.core.weight_variator`, `src.core.self_correction_workflow`, `src.core.mistake_book`, `src.core.wfa_backtester` |
| `src/plugins/evolution/wfa_backtester.py` | `src.core.mistake_book` |
| `src/plugins/data_pipeline/data_sanitizer.py` | `src.core.anomaly_validator`, `src.core.circuit_breaker` |

---

## 三、Legacy 文件迁移状态

| Legacy 文件 | 导出类 | 插件对应 | 状态 |
|------------|--------|---------|------|
| `system_orchestrator_legacy.py` (119KB) | `SystemOrchestrator` | `src/plugins/orchestrator/plugin.py` 有新 `OrchestratorPlugin` | ⚠️ 并行共存 |
| `wyckoff_state_machine_legacy.py` (159KB) | `WyckoffStateMachine`, `EnhancedWyckoffStateMachine`, `EvidenceChainManager` | 插件只是包装壳 | ❌ 未迁移 |
| `weight_variator_legacy.py` (48KB) | `MutationOperator`系列, `WeightVariator` | 无对应插件实现 | ❌ 未迁移 |

---

## 四、`run_evolution.py` 导入分析

```python
# 可直接改为插件导入的（4个）：
from src.core.self_correction_workflow import SelfCorrectionWorkflow
  # → from src.plugins.self_correction.workflow import SelfCorrectionWorkflow
from src.core.mistake_book import MistakeBook, MistakeType, ErrorSeverity, ErrorPattern
  # → from src.plugins.self_correction.mistake_book import ...
from src.core.wfa_backtester import WFABacktester, PerformanceMetric
  # → from src.plugins.evolution.wfa_backtester import ...
from src.core.period_weight_filter import PeriodWeightFilter
  # → from src.plugins.weight_system.period_weight_filter import ...

# 需保留 shim 或直接引 legacy 的（2个）：
from src.core.weight_variator import WeightVariator
  # → 暂无插件版本，保留
from src.core.wyckoff_state_machine import WyckoffStateMachine
  # → 插件只是壳，保留

# 需修复的（1个）：
from src.core.market_regime import RegimeDetector
  # → 文件不存在！改为 from src.plugins.market_regime.detector import RegimeDetector
```

---

## 五、安全重构计划（7个阶段）

### 阶段 0：立即修复（零风险，5分钟）✅ 已完成 2026-03-16

- [x] 创建 `src/core/market_regime.py` shim → 指向 `src.plugins.market_regime.detector`
- [x] 删除 `src/core/wyckoff_phase_detector.py`（无任何引用）
- [x] 修复 `wyckoff_state_machine_legacy.py:580` 延迟导入指向已删文件的问题

### 阶段 1：插件层去 core 依赖（中低风险，30分钟）✅ 已完成 2026-03-16

修改插件文件，将 `from src.core.xxx` 改为直接导入对应插件：

- [x] `src/plugins/data_pipeline/data_sanitizer.py`: 删除 src.core fallback
- [x] `src/plugins/evolution/wfa_backtester.py`: 删除 src.core fallback
- [x] `src/plugins/evolution/plugin.py`: 删除 src.core fallback，主路径改为插件
- [x] `src/plugins/self_correction/workflow.py`: 删除 3 个 src.core fallback（计划外发现）
- [x] `src/plugins/wyckoff_state_machine/plugin.py`: 改为通过 shim 包导入
- [x] `tests/plugins/test_wyckoff_state_machine.py`: mock 路径同步更新
- [x] 验证：886 passed

> **注**: 插件层仍有 3 处不可消除的 `src.core` 引用（`weight_variator` ×2, `wyckoff_state_machine` ×1），
> 因 legacy 未迁移到插件层，需阶段6处理。

### 阶段 2+3：生产脚本 + agents 层去 core 依赖 ✅ 已完成 2026-03-16

- [x] `run_evolution.py`: 5/7 导入迁移到插件路径（2处 legacy 保留）
- [x] `health_check.py`: 新增 `src.core.market_regime` shim 验证条目
- [x] `src/agents/strategy_optimizer_agent.py`: 7/12 导入迁移到插件路径（5处 legacy 保留）
- [x] `src/agents/backtest_validator_agent.py`: 2处均为 legacy，保留
- [x] 验证：886 passed

### 阶段 4：测试和示例文件批量迁移（低风险，2小时）✅ 已完成 2026-03-16

- [x] `tests/core/` 下17个测试文件 — 27处替换
- [x] `tests/` 根目录下的集成测试 — 41处替换
- [x] `examples/` 下6个示例文件 — 42处替换
- [x] 总计 110 处 `src.core.*` 导入迁移到 `src.plugins.*`
- [x] 验证：886 passed，warnings 从 23 降为 21

> **注**: 剩余 20 处 `src.core` 引用无法消除（`system_orchestrator` ×6, `wyckoff_state_machine` ×8, `weight_variator` ×6），
> 全部因 legacy 未迁移到插件层。

### 阶段 5：删除不再被引用的 shim（低风险，30分钟）

阶段 1-4 完成后，逐个检查并删除不再有引用者的 shim 文件。每删一个跑全量测试。

### 阶段 6：Legacy 文件物理迁移（高风险，1天+）

建议将 legacy 文件移入插件目录（而非重写）：

- [ ] `wyckoff_state_machine_legacy.py` → `src/plugins/wyckoff_state_machine/legacy_core.py`
- [ ] `weight_variator_legacy.py` → `src/plugins/evolution/weight_variator.py`
- [ ] `system_orchestrator_legacy.py` → `src/plugins/orchestrator/legacy_core.py`
- [ ] 更新所有 shim 和引用指向新位置
- [ ] 验证：全量测试通过

### 阶段 7：清理子模块（中风险）

`src/core/orchestrator/`, `src/core/wyckoff_state_machine/`, `src/core/evolution/` 中的逻辑代码迁移到对应插件，或确认已在 `src/kernel/types.py` 有对应定义。

---

## 六、执行优先级总结

```
安全 ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ → 危险

[阶段0]     [阶段1]   [阶段2-3]   [阶段4]   [阶段5]   [阶段6-7]
补shim      插件去    生产/agent   测试批量   删shim    Legacy
删无引用    core依赖  去core依赖   迁移      文件      物理迁移
零风险      中低风险   中风险      低风险     低风险    高风险
5分钟       30分钟    1小时       2小时      30分钟    1天+
```

---

## 七、验证检查点

每个阶段完成后必须通过的检查：

1. `pytest tests/ -v` — 全量测试通过
2. `python run_live.py` — 生产入口可启动
3. `python run_evolution.py` — 进化脚本可启动
4. `grep -r "from src.core" src/plugins/` — 插件层无 core 依赖（阶段1后）
5. `grep -r "from src.core" src/agents/` — agents 层无 core 依赖（阶段3后）
6. `grep -r "from src.core" tests/ examples/` — 测试/示例无 core 依赖（阶段4后）
