# Issues — Full System Cleanup

## 2026-03-21 18插件深度审计

### 插件结构验证 (18/18 通过)
所有18个插件: manifest OK (name/version/entry_point), on_load OK, on_unload OK

### 事件链完整性审计

#### 正常连接的事件链 (5条)
1. `data_pipeline.ohlcv_ready`: data_pipeline → market_regime, orchestrator
2. `evolution.cycle_complete`: evolution → evolution_advisor, self_correction
3. `position.closed`: position_manager → audit_logger, orchestrator, telegram_notifier
4. `position.opened`: position_manager → audit_logger, orchestrator, telegram_notifier
5. `trading.signal`: orchestrator → audit_logger, position_manager

#### 断裂的订阅 (6个 — 订阅了但没人发)
| 事件名 | 订阅者 | 问题 |
|--------|--------|------|
| `market.price_update` | position_manager | 无插件emit此事件(需exchange_connector或data_pipeline发) |
| `orchestrator.data_refresh_requested` | data_pipeline | 无插件emit(orchestrator未发此事件) |
| `risk_management.circuit_breaker_tripped` | audit_logger,orchestrator,position_manager,telegram_notifier | risk_management 只emit了anomaly_validated,没emit tripped |
| `risk_management.circuit_breaker_recovered` | orchestrator,position_manager | 同上,risk_management没emit recovered |
| `system.config_update` | signal_validation | 无插件emit(系统级事件缺失) |
| `system.shutdown` | position_manager,telegram_notifier | 无插件emit(应由app.py或orchestrator发) |

#### 无人订阅的emit (48个 — 发了但没人听)
大部分是信息广播类事件(dashboard状态、感知结果等),属于设计如此。
但以下值得关注:
- `risk_management.anomaly_validated` — risk_management唯一的emit,但无人订阅
- `state_machine.signal_generated` — 状态机产生信号,但无人消费
- `market_regime.detected/changed` — 体制变化通知,orchestrator不订阅

### 关键发现

**最严重: 风控链断裂**
risk_management 插件的 `circuit_breaker_tripped` 事件没有在 plugin.py 中被 emit,
但 4 个插件订阅了它。这意味着即使风控触发熔断,其他插件也收不到通知。

**次要: 优雅关闭链断裂**
`system.shutdown` 事件没有被任何插件 emit。position_manager 订阅了它用来市价平仓,
telegram_notifier 订阅了它用来发关机通知。实际关机时这些都不会触发。

**设计注意: 大量单向emit**
大多数插件只 emit 不 subscribe,说明它们更多是被 orchestrator 直接调用(方法调用),
而非通过事件总线通信。这是当前架构的实际工作方式。
