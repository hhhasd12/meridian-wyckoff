# Learnings — Full System Cleanup

## 2026-03-21 初始化
- 计划包含 18 个任务，5 个 Wave，7 个 Final Verification
- 基线：1189 passed, 0 failed, 571 warnings
- 平台：Windows (Python 3.11, Node 18+)

## 2026-03-21 OHLC数据生成器修复 (571 warnings → 0)
- `make_ohlcv()` 在 `ohlcv_generator.py` 本身逻辑正确，但缺少 `lows = np.minimum(lows, np.minimum(opens, closes))` 最终保障
- 571个UserWarning的真正来源是6个测试文件中的**内联OHLCV生成器**，它们独立生成open/high/low/close但没有确保 `low <= open <= high`
- 修复的文件: ohlcv_generator.py, test_evolution_pipeline.py, test_wfa_validator.py, test_data_pipeline.py, test_breakout_validation.py, test_event_schema_fix.py, test_market_regime.py
- 修复模式: 在所有价格生成后添加 `highs = np.maximum(highs, np.maximum(opens, close))` 和 `lows = np.minimum(lows, np.minimum(opens, close))`
- test_numba_accelerator.py 已有正确的OHLC验证（lines 124-125），可作为参考
- 结果：1189 passed, 0 warnings

## 2026-03-21 Task 4: 删除8个死代码文件 (~5700行)
- 删除了 8 个源文件 + 1 个测试文件 + 3 个示例文件 = 12 个文件
- `wyckoff_state_machine_legacy.py` (37行) 虽被标记为"死代码"，实际是兼容 shim，被 plugin.py 的 on_load() 直接 import
- 修复方法：将 plugin.py 的 import 从 `wyckoff_state_machine_legacy` 改为 `enhanced_state_machine`（实际实现所在模块）
- 同步修复了 setup.py 中的模块验证路径、test_wyckoff_state_machine.py 中 3 处 @patch 路径
- `performance_monitor.py` 的 WeightVariator/WFABacktester 导入在 try/except 中且未被使用，直接删除
- 结果：1143 passed, 0 failed（减少 46 个测试来自 test_numba_accelerator.py 的删除）

## 2026-03-21 Task 4+5: 17个 except Exception: 添加日志
- 4个 `except Exception: pass` 改为捕获 `as e` + logger.warning/debug
- 13个 `except Exception:` + fallback return 改为捕获 `as e` + logger.debug/warning
- 2个文件需要新增 `import logging` + `logger = logging.getLogger(__name__)`：curve_boundary.py, fvg_detector.py
- 3个文件已有日志调用但缺少 `as e`（engine.py:530 logger.exception, state_machine_v2.py:499 logger.debug, error_handler.py:196 func_logger.error）
- logger 级别选择：production-critical 路径（dashboard, position_manager, api）用 warning，内部计算路径用 debug
- 使用 `%s` 格式化（lazy evaluation），不用 f-string
- 结果：1143 passed, 0 failed，grep 确认 src/ 中 0 个裸 `except Exception:`

## Tasks 14+15: 过拟合修复 + EvolutionPlugin驱动 (2026-03-21)

### 过拟合修复（5个根因）:
1. **根因1 (GA/WFA同数据)**: `run_evolution.py` 中 trimmed_data 分割为 ga_train_data(前70%) 和 wfa_holdout_data(后30%)。EvolutionPlugin._run_evolution_cycle() 中同样实现了分割。
2. **根因3 (0-trade高分)**: `evaluator.py._compute_metrics()` 开头添加 `if result.total_trades < 5: return empty_metrics`。注意改 `@staticmethod` 为 `@classmethod` 因为需要调用 `cls._empty_metrics()`。
3. **根因5 (GA超参数)**: GAConfig 默认值改为 population_size=50, elite_count=5, mutation_rate=0.25, mutation_strength=0.10, convergence_patience=15。同步更新 run_evolution.py。
4. **根因6 (WFA窗口重叠)**: WFAConfig 改为 train_bars=300, test_bars=300, step_bars=300(=test_bars，消除重叠), min_windows=3。
5. **根因7 (AntiOverfit不执行)**: 在 `StandardEvaluator` 增加 `last_backtest_result` 缓存属性；GA `_evaluate_serial` 中通过 `hasattr` 检查并存入 `individual.backtest_result`；并行评估后对最佳个体做一次串行评估获取 BacktestResult。

### EvolutionPlugin驱动:
- `start_evolution()` 改为创建 `asyncio.Task` 执行 `_run_evolution_cycle()`
- `_run_evolution_cycle()` 封装完整 GA+WFA+AntiOverfit 循环，CPU密集操作通过 `run_in_executor` 避免阻塞事件循环
- `run.py` 的 `run_evolution_system()` 改为通过 WyckoffApp 加载插件后调用 EvolutionPlugin
- 保留 `run_evolution.py` 作为独立运行选项，并保留 `_run_evolution_standalone()` 作为回退

### 测试注意:
- GA测试fixture需显式设置 `mutation_rate=0.9`（默认已改为0.25，低变异率可能导致测试不稳定）
- WFA测试均使用自定义 WFAConfig，不受默认值变更影响
- 1143 tests all passed

## 2026-03-21 事件链断裂修复 (6个断裂订阅)

### 修复的断裂:
1. **`risk_management.circuit_breaker_tripped`**: 已存在emit(line 184-195)，但recovery场景未覆盖
2. **`risk_management.circuit_breaker_recovered`**: 新增 — 在`update_data_quality`中检测状态从TRIPPED/RECOVERY→NORMAL时emit
3. **`system.shutdown`**: 已存在于app.py line 222-226，无需修复
4. **`market.price_update`**: 新增 — 在orchestrator的`_process_market_data`中从主TF提取最新close价格
5. **`orchestrator.data_refresh_requested`**: 新增 — 在orchestrator的`run_loop`中每次拉取前emit
6. **`system.config_update`**: 新增 — 在app.py注册ConfigSystem变更监听器，变更时通过event_bus发布

### 关键经验:
- `circuit_breaker.update_data_quality()` 返回True有两种含义: 熔断触发 OR 恢复。需检查实际status区分
- 测试用MagicMock模拟circuit_breaker.status，不能用enum==比较，必须用`.value`字符串比较
- `market.price_update`放在data_pipeline会导致`emit_event.assert_called_once()`测试失败，改放orchestrator
- `capital_guard.py`已有独立的circuit_breaker_tripped emit（含reason字段），是第二条触发路径
- 1143 tests all passed
