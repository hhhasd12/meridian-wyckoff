"""
威科夫系统全面启动自检
=======================

在 run_evolution.py 启动前自动执行，全面检测：
1. Python 包依赖（numpy/pandas 等）
2. 所有 src/ 模块的导入链路
3. 关键类/函数接口是否存在
4. 数据文件是否就位
5. 核心依赖链端到端连通性

输出：
- 终端彩色仪表盘（立即可读）
- health_report.json（机器可读，方便后续追踪）

用法：
    python health_check.py          # 只检测，不修改任何代码
    python health_check.py --fix    # 检测 + 自动修复已知命名问题
"""

import importlib
import inspect
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────
# 终端颜色（无需 colorama）
# ──────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"

def _ok(msg):   return f"{C.GREEN}[OK]  {msg}{C.RESET}"
def _warn(msg): return f"{C.YELLOW}[!!]  {msg}{C.RESET}"
def _fail(msg): return f"{C.RED}[XX]  {msg}{C.RESET}"
def _info(msg): return f"{C.CYAN}  {msg}{C.RESET}"

# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────
STATUS_OK   = "OK"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"

@dataclass
class CheckResult:
    name: str
    status: str        # OK / WARN / FAIL
    message: str
    detail: str = ""
    fix_applied: bool = False

@dataclass
class HealthReport:
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    results: List[CheckResult] = field(default_factory=list)

    def add(self, r: CheckResult):
        self.results.append(r)

    @property
    def ok_count(self):   return sum(1 for r in self.results if r.status == STATUS_OK)
    @property
    def warn_count(self): return sum(1 for r in self.results if r.status == STATUS_WARN)
    @property
    def fail_count(self): return sum(1 for r in self.results if r.status == STATUS_FAIL)
    @property
    def passed(self):     return self.fail_count == 0

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "summary": {
                "ok": self.ok_count,
                "warn": self.warn_count,
                "fail": self.fail_count,
                "passed": self.passed,
            },
            "results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "message": r.message,
                    "detail": r.detail,
                    "fix_applied": r.fix_applied,
                }
                for r in self.results
            ],
        }


# ══════════════════════════════════════════════
# 检测逻辑
# ══════════════════════════════════════════════

def check_python_version(report: HealthReport):
    v = sys.version_info
    name = "Python 版本"
    if v >= (3, 9):
        report.add(CheckResult(name, STATUS_OK, f"Python {v.major}.{v.minor}.{v.micro}"))
    elif v >= (3, 7):
        report.add(CheckResult(name, STATUS_WARN, f"Python {v.major}.{v.minor} — 建议升级到 3.9+"))
    else:
        report.add(CheckResult(name, STATUS_FAIL, f"Python {v.major}.{v.minor} — 版本过低，可能不兼容"))


def check_third_party_packages(report: HealthReport):
    """检测必需的第三方包"""
    required = [
        ("numpy",  "numpy"),
        ("pandas", "pandas"),
        ("scipy",  "scipy"),
    ]
    optional = [
        ("matplotlib", "matplotlib"),
        ("sklearn",    "scikit-learn"),
        ("plotly",     "plotly"),
    ]

    for mod_name, pkg_name in required:
        try:
            m = importlib.import_module(mod_name)
            ver = getattr(m, "__version__", "?")
            report.add(CheckResult(f"包:{pkg_name}", STATUS_OK, f"v{ver}"))
        except ImportError as e:
            report.add(CheckResult(
                f"包:{pkg_name}", STATUS_FAIL,
                f"缺失！请执行: pip install {pkg_name}",
                detail=str(e)
            ))

    for mod_name, pkg_name in optional:
        try:
            m = importlib.import_module(mod_name)
            ver = getattr(m, "__version__", "?")
            report.add(CheckResult(f"包:{pkg_name}(可选)", STATUS_OK, f"v{ver}"))
        except ImportError:
            report.add(CheckResult(
                f"包:{pkg_name}(可选)", STATUS_WARN,
                f"未安装（部分功能受限），pip install {pkg_name}"
            ))


def _try_import(module_path: str) -> Tuple[Optional[Any], Optional[str]]:
    """尝试导入模块，返回 (模块对象 or None, 错误信息 or None)"""
    try:
        m = importlib.import_module(module_path)
        return m, None
    except Exception as e:
        tb = traceback.format_exc()
        return None, f"{type(e).__name__}: {e}\n{tb}"


def check_src_modules(report: HealthReport):
    """检测 src/ 下所有关键模块的导入"""

    # (模块路径, 必须能导入, 必须存在的类/函数)
    MODULE_CHECKS = [
        # ── data ──
        ("src.data.loader",          True,  ["DataLoader"]),
        ("src.data.cleaner",         True,  []),
        ("src.data.feature_factory", True,  []),
        ("src.data.binance_fetcher", False, []),   # 可选（需要网络）

        # ── backtest ──
        ("src.backtest.engine",      True,  ["BacktestEngine", "BacktestResult", "Trade"]),
        ("src.backtest.reporter",    True,  ["BacktestReporter"]),

        # ── core ──
        ("src.core.mistake_book",    True,  ["MistakeBook", "MistakeType", "ErrorSeverity", "ErrorPattern"]),
        ("src.core.weight_variator", True,  ["WeightVariator", "MutationType"]),
        ("src.core.weight_variator_legacy", True, ["WeightVariator"]),
        ("src.core.wfa_backtester",  True,  ["WFABacktester", "PerformanceMetric"]),
        ("src.core.self_correction_workflow", True, ["SelfCorrectionWorkflow"]),
        ("src.core.system_orchestrator",     True,  ["SystemOrchestrator"]),
        ("src.core.market_regime",           True,  []),
        ("src.core.period_weight_filter",    True,  ["PeriodWeightFilter"]),
        ("src.core.conflict_resolver",       True,  ["ConflictResolutionManager"]),
        ("src.core.breakout_validator",      True,  []),
        ("src.core.micro_entry_validator",   True,  []),
        ("src.core.performance_monitor",     True,  []),
        ("src.core.evolution_archivist",     True,  ["EvolutionArchivist"]),
        ("src.core.circuit_breaker",         True,  []),
        ("src.core.data_sanitizer",          True,  []),
        ("src.core.data_pipeline",           True,  []),
        ("src.core.config_system",           True,  []),
        ("src.core.curve_boundary",          False, []),

        # wyckoff state machine 子包
        ("src.core.wyckoff_state_machine.state_definitions", True, []),
        ("src.core.wyckoff_state_machine.evidence_chain",    True, []),

        # evolution 子包
        ("src.core.evolution.operators",  False, []),

        # orchestrator 子包
        ("src.core.orchestrator.config",   True, []),
        ("src.core.orchestrator.health",   True, []),
        ("src.core.orchestrator.registry", True, []),
        ("src.core.orchestrator.flow",     True, []),

        # ── perception ──
        ("src.perception.candle_physical",  False, []),
        ("src.perception.fvg_detector",     False, []),
        ("src.perception.pin_body_analyzer",False, []),

        # ── utils ──
        ("src.utils.error_handler",  True,  ["error_handler"]),
        ("src.utils.config_loader",  True,  []),
        ("src.utils.visualizer",     False, []),

        # ── visualization ──
        ("src.visualization.heritage_panel", False, []),
    ]

    for mod_path, required, symbols in MODULE_CHECKS:
        mod, err = _try_import(mod_path)
        short = mod_path.replace("src.", "")
        if mod is None:
            level = STATUS_FAIL if required else STATUS_WARN
            report.add(CheckResult(
                f"模块:{short}", level,
                f"导入失败",
                detail=err or ""
            ))
        else:
            # 检查必需符号
            missing = [s for s in symbols if not hasattr(mod, s)]
            if missing:
                report.add(CheckResult(
                    f"模块:{short}", STATUS_FAIL,
                    f"缺少符号: {', '.join(missing)}",
                    detail=f"模块可导入，但缺失以下名称: {missing}"
                ))
            else:
                report.add(CheckResult(
                    f"模块:{short}", STATUS_OK,
                    f"导入 OK" + (f"，含: {', '.join(symbols)}" if symbols else "")
                ))


def check_critical_interface(report: HealthReport, auto_fix: bool):
    """
    检测 run_evolution.py 中已知的接口断链并尝试修复。

    已知问题 #1: run_evolution.py line 28
        from src.data.loader import MarketDataLoader
        → 实际类名是 DataLoader，MarketDataLoader 不存在
    """
    evo_path = Path(__file__).parent / "run_evolution.py"
    if not evo_path.exists():
        report.add(CheckResult(
            "接口:run_evolution.py", STATUS_WARN,
            "文件不存在，跳过接口检测"
        ))
        return

    content = evo_path.read_text(encoding="utf-8")

    # 检测已知问题
    issues = []
    fixes_applied = []

    # 问题1: MarketDataLoader → DataLoader
    # 如果已经是别名写法 "DataLoader as MarketDataLoader" 则视为已修复
    if "MarketDataLoader" in content and "DataLoader as MarketDataLoader" not in content:
        issues.append("run_evolution.py 使用了不存在的类 MarketDataLoader（应为 DataLoader）")
        if auto_fix:
            new_content = content.replace(
                "from src.data.loader import MarketDataLoader",
                "from src.data.loader import DataLoader as MarketDataLoader  # fixed by health_check"
            )
            if new_content != content:
                evo_path.write_text(new_content, encoding="utf-8")
                fixes_applied.append("MarketDataLoader → DataLoader (别名修复)")
                content = new_content

    if issues and not fixes_applied:
        report.add(CheckResult(
            "接口:MarketDataLoader", STATUS_FAIL,
            "run_evolution.py 引用了不存在的类 MarketDataLoader",
            detail="src/data/loader.py 中实际类名为 DataLoader。\n"
                   "修复方法：运行 python health_check.py --fix\n"
                   "或手动将第28行改为:\n"
                   "  from src.data.loader import DataLoader as MarketDataLoader"
        ))
    elif issues and fixes_applied:
        report.add(CheckResult(
            "接口:MarketDataLoader", STATUS_OK,
            f"已自动修复: {'; '.join(fixes_applied)}",
            fix_applied=True
        ))
    else:
        report.add(CheckResult(
            "接口:MarketDataLoader", STATUS_OK,
            "MarketDataLoader 导入写法正常"
        ))


def check_data_files(report: HealthReport):
    """检测数据文件是否存在"""
    base = Path(__file__).parent / "data"

    files = {
        "data/binance_ETH_USDT_1d_730d.pkl": ("PKL D1 日线数据", True),
        "data/binance_ETH_USDT_4h_730d.pkl": ("PKL H4 四小时数据", True),
        "data/binance_ETH_USDT_1h_730d.pkl": ("PKL H1 小时数据", False),
        "data/ETHUSDT_1d.csv":  ("CSV D1", False),
        "data/ETHUSDT_4h.csv":  ("CSV H4", False),
        "data/ETHUSDT_1h.csv":  ("CSV H1", False),
        "data/ETHUSDT_15m.csv": ("CSV M15", False),
        "data/ETHUSDT_5m.csv":  ("CSV M5", False),
    }

    any_data = False
    for rel_path, (label, preferred) in files.items():
        full = Path(__file__).parent / rel_path
        if full.exists():
            size_mb = full.stat().st_size / 1024 / 1024
            report.add(CheckResult(
                f"数据:{label}", STATUS_OK,
                f"{full.name} ({size_mb:.1f} MB)"
            ))
            any_data = True
        else:
            level = STATUS_WARN if not preferred else STATUS_WARN
            report.add(CheckResult(
                f"数据:{label}", STATUS_WARN,
                f"不存在: {rel_path}"
            ))

    if not any_data:
        report.add(CheckResult(
            "数据:总体", STATUS_FAIL,
            "data/ 目录中没有任何数据文件！\n"
            "请运行: python scripts/generate_eth_data.py 或 python scripts/download_eth_data.py"
        ))
    else:
        report.add(CheckResult(
            "数据:总体", STATUS_OK,
            f"至少存在部分数据文件"
        ))


def check_e2e_import_chain(report: HealthReport):
    """
    端到端依赖链烟雾测试：
    模拟 run_evolution.py 的完整 import 链，捕获任何运行时错误
    """
    chain = [
        ("src.data.loader",                  "DataLoader"),
        ("src.core.self_correction_workflow","SelfCorrectionWorkflow"),
        ("src.core.mistake_book",            "MistakeBook"),
        ("src.core.weight_variator",         "WeightVariator"),
        ("src.core.wfa_backtester",          "WFABacktester"),
        ("src.backtest.engine",              "BacktestEngine"),
    ]

    all_ok = True
    broken_at = None
    for mod_path, cls_name in chain:
        mod, err = _try_import(mod_path)
        if mod is None:
            all_ok = False
            broken_at = (mod_path, cls_name, err)
            break
        if not hasattr(mod, cls_name):
            all_ok = False
            broken_at = (mod_path, cls_name, f"模块可导入，但 {cls_name} 不存在")
            break

    if all_ok:
        report.add(CheckResult(
            "链路:end-to-end", STATUS_OK,
            "run_evolution.py 核心导入链路全部连通"
        ))
    else:
        mod_path, cls_name, err = broken_at
        report.add(CheckResult(
            "链路:end-to-end", STATUS_FAIL,
            f"链路在 {mod_path}::{cls_name} 断裂",
            detail=err or ""
        ))


def check_output_dirs(report: HealthReport):
    """检测输出目录是否可写"""
    dirs = [
        "evolution_results",
        "logs",
    ]
    for d in dirs:
        p = Path(__file__).parent / d
        try:
            p.mkdir(exist_ok=True)
            test_file = p / ".healthcheck_write_test"
            test_file.write_text("ok")
            test_file.unlink()
            report.add(CheckResult(f"目录:{d}", STATUS_OK, "存在且可写"))
        except Exception as e:
            report.add(CheckResult(
                f"目录:{d}", STATUS_WARN,
                f"无法创建或写入: {e}"
            ))


# ══════════════════════════════════════════════
# 报告输出
# ══════════════════════════════════════════════

def _section(title: str):
    print(f"\n{C.BOLD}{C.BLUE}{'-' * 55}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}  {title}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'-' * 55}{C.RESET}")


def print_report(report: HealthReport):
    print(f"\n{C.BOLD}{C.WHITE}{'=' * 55}{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}  Wyckoff Health Check  (startuo self-check){C.RESET}")
    print(f"{C.BOLD}{C.WHITE}  {report.timestamp}{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}{'=' * 55}{C.RESET}")

    # 按分组展示
    groups = {}
    for r in report.results:
        prefix = r.name.split(":")[0] if ":" in r.name else "其他"
        groups.setdefault(prefix, []).append(r)

    group_order = ["Python", "包", "模块", "接口", "链路", "数据", "目录", "其他"]
    ordered_groups = []
    for g in group_order:
        if g in groups:
            ordered_groups.append((g, groups.pop(g)))
    for g, items in groups.items():
        ordered_groups.append((g, items))

    for group_name, items in ordered_groups:
        _section(group_name)
        for r in items:
            if r.status == STATUS_OK:
                icon = _ok
            elif r.status == STATUS_WARN:
                icon = _warn
            else:
                icon = _fail

            print(f"  {icon(r.name)}")
            print(f"    {C.GRAY}{r.message}{C.RESET}")
            if r.detail:
                for line in r.detail.strip().splitlines()[:6]:  # 最多6行detail
                    print(f"    {C.GRAY}  | {line}{C.RESET}")
            if r.fix_applied:
                print(f"    {C.GREEN}  -> [Auto-fixed]{C.RESET}")

    # 总结
    print(f"\n{C.BOLD}{C.WHITE}{'=' * 55}{C.RESET}")
    print(f"{C.BOLD}  Summary: "
          f"{C.GREEN}{report.ok_count} OK{C.RESET} | "
          f"{C.YELLOW}{report.warn_count} WARN{C.RESET} | "
          f"{C.RED}{report.fail_count} FAIL{C.RESET}")

    if report.passed:
        print(f"\n  {C.BOLD}{C.GREEN}[PASS] All checks passed, ready to start!{C.RESET}")
    else:
        print(f"\n  {C.BOLD}{C.RED}[FAIL] {report.fail_count} critical issue(s) found, please fix before starting.{C.RESET}")
        print(f"  {C.YELLOW}Tip: run  python health_check.py --fix  to auto-fix known issues{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}{'=' * 55}{C.RESET}\n")


def save_report(report: HealthReport):
    report_path = Path(__file__).parent / "health_report.json"
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"{C.GRAY}  详细报告已保存: {report_path}{C.RESET}\n")


# ══════════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════════

def run_health_check(auto_fix: bool = False) -> HealthReport:
    """
    执行全面自检，返回 HealthReport。

    Args:
        auto_fix: 若为 True，自动修复已知的命名/接口错误
    """
    # 确保项目根目录在 sys.path
    project_root = str(Path(__file__).parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    report = HealthReport()

    check_python_version(report)
    check_third_party_packages(report)
    check_src_modules(report)
    check_critical_interface(report, auto_fix=auto_fix)
    check_data_files(report)
    check_e2e_import_chain(report)
    check_output_dirs(report)

    return report


def main():
    auto_fix = "--fix" in sys.argv

    if auto_fix:
        print(f"\n{C.YELLOW}[自动修复模式] 将尝试修复已知问题...{C.RESET}")

    report = run_health_check(auto_fix=auto_fix)
    print_report(report)
    save_report(report)

    # 退出码：有严重失败则返回 1
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
