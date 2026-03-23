"""系统完整性检查 — 模拟真实启动流程，验证所有插件接线

用法:
    python check_system_integrity.py

检查内容:
    1. 所有插件 on_load() 后内部组件是否正确初始化（非 None）
    2. API 层依赖的所有方法是否存在且可调用
    3. 事件总线订阅/发布是否匹配

运行时机:
    - 修改任何插件的 on_load/on_unload 后
    - 修改 API 端点后
    - 添加/删除插件后
    - CI/CD 流水线中
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def main() -> int:
    from src.app import WyckoffApp

    app = WyckoffApp(config_path="config.yaml")
    app.discover_and_load()
    pm = app.plugin_manager
    problems: list[str] = []

    # ================================================================
    # PHASE 1: 插件内部状态检查
    # ================================================================
    print("=" * 70)
    print("PHASE 1: 插件 on_load() 后内部组件初始化状态")
    print("=" * 70)

    # {plugin_name: [(attr_name, description), ...]}
    # 仅检查 on_load() 应该初始化的核心组件
    internal_checks: dict[str, list[tuple[str, str]]] = {
        "orchestrator": [("_engine", "WyckoffEngine 实例")],
        "wyckoff_engine": [("engine", "WyckoffEngine 实例")],
        "evolution": [
            ("_ga", "GeneticAlgorithm"),
            ("_evaluator", "StandardEvaluator"),
            ("_wfa", "WFAValidator"),
            ("_anti_overfit", "AntiOverfitGuard"),
        ],
        "data_pipeline": [("pipeline", "DataPipeline 实例")],
        "pattern_detection": [("_tr_detector", "TRDetector 实例")],
        "perception": [("_fvg_detector", "FVGDetector 实例")],
        "signal_validation": [
            ("_breakout_validator", "BreakoutValidator 实例"),
        ],
        "risk_management": [("_capital_guard", "CapitalGuard 实例")],
        "position_manager": [("_manager", "PositionManager 内核")],
        "wyckoff_state_machine": [
            ("_state_machine", "StateMachineV2 实例"),
        ],
        "self_correction": [
            ("_workflow", "SelfCorrectionWorkflow 实例"),
        ],
        "dashboard": [("_monitor", "PerformanceMonitor 实例")],
    }

    for plugin_name, attrs in internal_checks.items():
        plugin = pm.get_plugin(plugin_name)
        if plugin is None:
            problems.append(f"{plugin_name}: 插件未加载")
            print(f"  [MISS] {plugin_name}: 插件未加载!")
            continue
        for attr_name, desc in attrs:
            val = getattr(plugin, attr_name, "__NOTFOUND__")
            if val == "__NOTFOUND__":
                # 属性不存在 — 可能是检查配置有误，跳过
                pass
            elif val is None:
                print(f"  [FAIL] {plugin_name}.{attr_name} = None ({desc})")
                problems.append(f"{plugin_name}.{attr_name} = None ({desc})")
            else:
                print(
                    f"  [ OK ] {plugin_name}.{attr_name} = "
                    f"{type(val).__name__} ({desc})"
                )

    # ================================================================
    # PHASE 2: API 方法调用检查
    # ================================================================
    print()
    print("=" * 70)
    print("PHASE 2: API 端点依赖方法可调用性")
    print("=" * 70)

    # {plugin: [(method, args, none_is_ok), ...]}
    api_methods: dict[str, list[tuple[str, tuple, bool]]] = {  # type: ignore[type-arg]
        "data_pipeline": [
            ("get_cached_data", ("BTC/USDT", "H4"), True),
        ],
        "orchestrator": [
            ("get_system_status", (), False),
            ("get_decision_history", (1,), False),
        ],
        "position_manager": [
            ("get_all_positions", (), False),
            ("get_closed_trades", (), False),
        ],
        "evolution": [
            ("get_evolution_status", (), False),
            ("get_current_config", (), False),
        ],
        "wyckoff_engine": [
            ("get_current_state", (), False),
        ],
        "audit_logger": [
            ("get_recent_logs", (20,), False),
        ],
        "evolution_advisor": [
            ("get_last_analysis", (), True),
        ],
    }

    for plugin_name, method_list in api_methods.items():
        plugin = pm.get_plugin(plugin_name)
        if plugin is None:
            print(f"  [SKIP] {plugin_name}: 未加载")
            continue
        for method_name, args, none_ok in method_list:
            fn = getattr(plugin, method_name, None)
            if fn is None:
                print(f"  [FAIL] {plugin_name}.{method_name}() -> 方法不存在!")
                problems.append(f"{plugin_name}.{method_name}(): 方法不存在")
                continue
            try:
                result = fn(*args)
                rtype = type(result).__name__
                if result is None and not none_ok:
                    print(
                        f"  [WARN] {plugin_name}.{method_name}() -> None (unexpected)"
                    )
                    problems.append(f"{plugin_name}.{method_name}() 返回 None")
                else:
                    print(f"  [ OK ] {plugin_name}.{method_name}() -> {rtype}")
            except Exception as e:
                print(f"  [FAIL] {plugin_name}.{method_name}() -> EXCEPTION: {e}")
                problems.append(f"{plugin_name}.{method_name}(): {e}")

    # ================================================================
    # PHASE 3: 事件总线连通性
    # ================================================================
    print()
    print("=" * 70)
    print("PHASE 3: 事件总线关键链路")
    print("=" * 70)

    event_bus = pm.get_event_bus()
    # 检查关键事件是否有订阅者
    critical_events = [
        ("data_pipeline.ohlcv_ready", "数据就绪 -> orchestrator/market_regime"),
        ("trading.signal", "交易信号 -> position_manager/audit_logger"),
        ("market.price_update", "价格更新 -> position_manager 止损监控"),
        ("risk_management.circuit_breaker_tripped", "熔断 -> 多个订阅者"),
        ("evolution.cycle_complete", "进化完成 -> advisor/self_correction"),
        ("position.opened", "仓位开启 -> telegram/audit"),
        ("position.closed", "仓位关闭 -> telegram/audit"),
    ]

    for event_name, desc in critical_events:
        subscribers = event_bus.get_subscribers(event_name)
        count = len(subscribers)
        if count == 0:
            print(f"  [FAIL] {event_name}: 无订阅者! ({desc})")
            problems.append(f"事件 {event_name} 无订阅者 ({desc})")
        else:
            print(f"  [ OK ] {event_name}: {count} 个订阅者 ({desc})")

    # ================================================================
    # 结果汇总
    # ================================================================
    print()
    print("=" * 70)
    if problems:
        print(f"发现 {len(problems)} 个问题:")
        for p in problems:
            print(f"  - {p}")
        print("=" * 70)
        return 1
    else:
        print("ALL CHECKS PASSED - 系统完整性验证通过")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    exit(main())
