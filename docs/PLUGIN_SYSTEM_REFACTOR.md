# 插件系统完整重构方案

## 1. 当前问题诊断

### 1.1 Manifest 格式不一致

| 插件 | 类型字段 | 事件格式 | 问题 |
|------|---------|---------|------|
| orchestrator | `type` | `events.publishes/subscribes` | 正确 |
| market_regime | `plugin_type` | `events.publishes/subscribes` | 字段名错误 |
| data_pipeline | `plugin_type` | `events.publishes/subscribes` | 字段名错误 |
| evolution | `plugin_type` | `events.publishes/subscribes` | 字段名错误 |
| pattern_detection | `type` | `events` 列表 + `subscriptions` | 格式完全不同 |
| wyckoff_state_machine | `type` | `events.publishes/subscribes` | 正确 |
| perception | `plugin_type` | `events` 列表 + `subscriptions` | 格式完全不同 |
| risk_management | 无 | `events.publishes/subscribes` | 缺少类型字段 |
| signal_validation | 无 | `events.publishes/subscribes` | 缺少类型字段 |
| weight_system | `plugin_type` | `events.publishes/subscribes` | 字段名错误 |
| dashboard | 无 | `events.publishes/subscribes` | 缺少类型字段 |
| position_manager | `plugin_type` | `events.publishes/subscribes` | 字段名错误 |
| exchange_connector | `type` | `events` 列表 + `subscriptions` | 格式完全不同 |

### 1.2 依赖关系混乱

```
orchestrator (core, priority=100)
├── market_regime (core)
├── data_pipeline (synchronous)
├── perception (synchronous)
├── pattern_detection (synchronous) → 依赖 market_regime
├── risk_management (无类型) → 依赖 market_regime
├── signal_validation (无类型) → 依赖 market_regime
├── weight_system (analysis) → 依赖 market_regime
├── evolution (analysis) → 依赖 market_regime
└── dashboard (无类型) → 依赖 market_regime, perception
```

**问题**：
1. `orchestrator` 声明依赖这些插件，但它自己是 `core` 类型，会**最先加载**
2. 依赖的插件还没加载，orchestrator 就已经加载了
3. 这违反了依赖顺序原则

### 1.3 架构问题

当前 `OrchestratorPlugin` 只是一个**包装器**：
```python
from src.core.system_orchestrator_legacy import SystemOrchestrator
self._orchestrator = SystemOrchestrator(orchestrator_config)
```

这意味着：
- 插件系统只是外观层
- 实际逻辑仍在旧的 monolithic 代码中
- 插件间没有真正的事件驱动通信

---

## 2. 重构目标

### 2.1 统一 Manifest 格式

所有插件使用一致的 manifest 格式：

```yaml
name: plugin_name
version: "1.0.0"
description: "插件描述"
author: "Wyckoff Engine Team"
entry_point: plugin

# 统一使用 plugin_type
plugin_type: core | analysis | connector | ui

# 依赖
dependencies:
  - other_plugin

# 事件声明（统一格式）
events:
  publishes:
    - event.name.1
    - event.name.2
  subscribes:
    - event.pattern.*

# 配置 schema
config_schema:
  key:
    type: string | int | float | bool | object | array
    default: value
    description: "描述"
```

### 2.2 正确的依赖顺序

```
Layer 0 (基础设施层):
  - exchange_connector (数据源)
  - data_pipeline (数据处理)

Layer 1 (核心分析层):
  - market_regime (市场体制)
  - perception (K线感知)

Layer 2 (高级分析层):
  - pattern_detection (形态检测) → 依赖 Layer 1
  - wyckoff_state_machine (状态机) → 依赖 Layer 1
  - weight_system (权重系统) → 依赖 Layer 1

Layer 3 (信号验证层):
  - signal_validation (信号验证) → 依赖 Layer 2
  - risk_management (风险管理) → 依赖 Layer 2

Layer 4 (执行层):
  - position_manager (仓位管理) → 依赖 Layer 3
  - evolution (进化系统) → 依赖 Layer 1

Layer 5 (协调层):
  - orchestrator (系统协调) → 依赖所有 Layer 0-4

Layer 6 (UI层):
  - dashboard (仪表盘) → 依赖 Layer 5
```

### 2.3 事件驱动架构

```
数据流向:
exchange_connector → data_pipeline → market_regime → perception
                                            ↓
                                    pattern_detection
                                            ↓
                                    wyckoff_state_machine
                                            ↓
                                    weight_system
                                            ↓
                                    signal_validation
                                            ↓
                                    risk_management
                                            ↓
                                    position_manager
                                            ↓
                                    orchestrator (汇总决策)
```

---

## 3. 实施步骤

### Phase 1: 统一 Manifest 格式

修改所有 `plugin-manifest.yaml` 文件，使用统一格式。

### Phase 2: 重构 Orchestrator

将 `OrchestratorPlugin` 从包装器重构为真正的事件协调器：
1. 移除对 `SystemOrchestrator` 的依赖
2. 通过事件总线订阅其他插件的输出
3. 汇总各插件结果，生成最终决策

### Phase 3: 实现事件驱动通信

为每个插件添加：
1. 事件订阅逻辑（在 `on_load` 中）
2. 事件发布逻辑（在业务方法中）

### Phase 4: 测试验证

1. 单元测试每个插件
2. 集成测试插件间通信
3. 端到端测试完整流程

---

## 4. 详细实施计划

### 4.1 Manifest 统一

| 插件 | 当前类型 | 目标类型 | 需要修改 |
|------|---------|---------|---------|
| market_regime | core | core | 字段名 |
| data_pipeline | synchronous | core | 类型值 |
| exchange_connector | connector | connector | 事件格式 |
| perception | synchronous | analysis | 类型值 |
| pattern_detection | synchronous | analysis | 全部 |
| wyckoff_state_machine | analysis | analysis | 字段名 |
| weight_system | analysis | analysis | 字段名 |
| signal_validation | 无 | analysis | 添加类型 |
| risk_management | 无 | analysis | 添加类型 |
| position_manager | core | executor | 类型值 |
| evolution | analysis | analysis | 字段名 |
| orchestrator | core | core | 依赖调整 |
| dashboard | 无 | ui | 添加类型 |

### 4.2 Orchestrator 重构

新的 `OrchestratorPlugin` 职责：
1. **不直接调用其他插件**
2. 订阅所有决策相关事件
3. 汇总事件数据，生成最终决策
4. 发布决策事件

```python
class OrchestratorPlugin(BasePlugin):
    def on_load(self):
        # 订阅所有决策输入事件
        self.subscribe_event("market_regime.detected", self._on_regime)
        self.subscribe_event("pattern_detection.tr_detected", self._on_tr)
        self.subscribe_event("state_machine.signal_generated", self._on_signal)
        self.subscribe_event("signal_validation.entry_validated", self._on_validation)
        self.subscribe_event("risk_management.*", self._on_risk)
        
    def _make_decision(self):
        # 汇总所有输入，生成决策
        decision = self._aggregate_inputs()
        self.emit_event("orchestrator.decision_made", decision)
```

### 4.3 事件流设计

```
# 数据就绪事件
data_pipeline.ohlcv_ready → 触发后续分析

# 分析事件链
market_regime.detected → perception.candle_analyzed
                       → pattern_detection.tr_detected
                       → wyckoff_state_machine.signal_generated

# 验证事件链
signal_validation.entry_validated → risk_management.anomaly_validated

# 决策事件
orchestrator.decision_made → position_manager.execute
```

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 重构期间系统不可用 | 高 | 分阶段实施，每阶段独立测试 |
| 事件顺序错误 | 中 | 使用事件优先级机制 |
| 插件间循环依赖 | 高 | 严格依赖检查，使用DAG验证 |
| 性能下降 | 中 | 异步事件处理，批量处理 |

---

## 6. 验收标准

1. ✅ 所有插件使用统一的 manifest 格式
2. ✅ 插件按正确依赖顺序加载
3. ✅ 插件间通过事件总线通信
4. ✅ Orchestrator 不再依赖 legacy 代码
5. ✅ 系统可以正常启动并运行
6. ✅ 进化日志正常显示
7. ✅ 决策流程完整执行

---

*文档版本: 1.0*
*创建日期: 2026-03-11*
*作者: Wyckoff Engine Team*
