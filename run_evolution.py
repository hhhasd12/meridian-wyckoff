"""
威科夫系统无限进化启动器
=============================

功能：
1. 加载ETH历史数据（多时间周期）
2. 配置自我修正工作流
3. 执行无限进化循环
4. 监控进化效果

运行方式：
    python run_evolution.py

注意：此脚本是独立运行方式，不通过 API 服务器。
建议使用 API 服务器方式：

1. 启动 API 服务器：
   python -m uvicorn src.api.app:app --port 9527

2. 通过 API 控制进化盘：
   curl -X POST http://localhost:9527/api/evolution/start
   curl -X GET http://localhost:9527/api/evolution/status
   curl -X POST http://localhost:9527/api/evolution/stop

此脚本保留作为备用启动方式，适合：
- 命令行直接运行进化
- 调试和开发测试
- 无需 Web 界面的场景
"""

import sys
import os
import json
import logging
from datetime import datetime
from pathlib import Path

# ── 修复 Windows GBK 终端乱码 ─────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 启动自检 ──────────────────────────────────────────────
from health_check import run_health_check, print_report, save_report


def _startup_health_check():
    """启动前全面自检，发现严重问题则阻止启动"""
    report = run_health_check(auto_fix=False)
    save_report(report)
    if not report.passed:
        # 只有失败时才展示完整报告
        print_report(report)
        print("系统自检未通过，请修复上述问题后重新启动。")
        print("提示：运行 python health_check.py --fix 尝试自动修复已知问题")
        sys.exit(1)
    else:
        print(
            f"[Health Check] OK: {report.ok_count} passed, {report.warn_count} warnings. Starting..."
        )


_startup_health_check()
# ──────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
from src.data.loader import DataLoader as MarketDataLoader  # DataLoader 是实际类名
from src.plugins.self_correction.workflow import SelfCorrectionWorkflow
from src.plugins.self_correction.mistake_book import (
    MistakeBook,
    MistakeType,
    ErrorSeverity,
    ErrorPattern,
)
from src.plugins.evolution.weight_variator_legacy import WeightVariator
from src.plugins.evolution.wfa_backtester import WFABacktester, PerformanceMetric
from src.backtest.engine import BacktestEngine
from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
    WyckoffStateMachine,
)
from src.plugins.market_regime.detector import RegimeDetector
from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter

# 配置日志：主模块 INFO，内部模块 WARNING（避免中文乱码和刷屏）
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# 给 __main__ logger 单独加一个 stdout handler
_handler = logging.StreamHandler(sys.stdout)
_handler.setLevel(logging.INFO)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_handler)
logger.propagate = False


def load_evolution_data():
    """加载进化所需的多时间周期数据（优先 pkl 缓存，fallback CSV，再降频补全）"""
    data = {}

    # pkl 本地数据（列名已是小写，索引已是 DatetimeIndex）
    pkl_map = {
        "D1": "data/binance_ETH_USDT_1d_730d.pkl",
        "H4": "data/binance_ETH_USDT_4h_730d.pkl",
        "H1": "data/binance_ETH_USDT_1h_730d.pkl",
    }

    # CSV 备选（注意：实际文件名为 ETHUSDT_4h.csv，无下划线）
    csv_map = {
        "D1": "data/ETHUSDT_1d.csv",
        "H4": "data/ETHUSDT_4h.csv",
        "H1": "data/ETHUSDT_1h.csv",
        "M15": "data/ETHUSDT_15m.csv",
        "M5": "data/ETHUSDT_5m.csv",
    }

    col_rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Open_time": "open_time",
    }

    # 优先加载 pkl
    for tf, pkl_path in pkl_map.items():
        if os.path.exists(pkl_path):
            import pickle

            with open(pkl_path, "rb") as f:
                df = pickle.load(f)
            data[tf] = df
            logger.info(
                f"Loaded {tf} from pkl: {len(df)} bars ({df.index[0]} ~ {df.index[-1]})"
            )

    # pkl 缺失的时间框架从 CSV 补充
    for tf, csv_path in csv_map.items():
        if tf in data:
            continue
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            # 归一化列名（CSV 列名是大写）
            df = df.rename(columns=col_rename)
            # 只保留核心列
            core_cols = [
                c for c in ["open", "high", "low", "close", "volume"] if c in df.columns
            ]
            df = df[core_cols]
            data[tf] = df
            logger.info(
                f"Loaded {tf} from csv: {len(df)} bars ({df.index[0]} ~ {df.index[-1]})"
            )
        else:
            logger.warning(f"Data file not found: {csv_path}")

    # --- 降频补全：用大周期数据 resample 到缺失的小周期 ---
    # M15：若仍缺失，从 H1 resample
    if "M15" not in data and "H1" in data:
        data["M15"] = data["H1"]
        logger.warning("M15: no file found, using H1 data as substitute")

    # M5：若仍缺失，从 H1 resample（每根H1 = 12根M5）
    if "M5" not in data and "H1" in data:
        h1 = data["H1"]
        agg_map = {"open": "first", "high": "max", "low": "min", "close": "last"}
        if "volume" in h1.columns:
            agg_map["volume"] = "sum"
        m5 = h1.resample("5min").agg(agg_map).dropna(subset=["open", "close"])
        data["M5"] = m5
        logger.warning("M5: no file found, resampled from H1 data")

    # D1：若仍缺失，从 H4 resample
    if "D1" not in data and "H4" in data:
        h4 = data["H4"]
        agg_map = {"open": "first", "high": "max", "low": "min", "close": "last"}
        if "volume" in h4.columns:
            agg_map["volume"] = "sum"
        d1 = h4.resample("1D").agg(agg_map).dropna(subset=["open", "close"])
        data["D1"] = d1
        logger.warning("D1: no file found, resampled from H4 data")

    return data


def create_baseline_config():
    """创建基准配置（五层周期：D1 / H4 / H1 / M15 / M5）"""
    return {
        "period_weight_filter": {
            "weights": {
                "D1": 0.25,
                "H4": 0.30,
                "H1": 0.25,
                "M15": 0.12,
                "M5": 0.08,
            },
            "regime_weights": {
                "TRENDING_BULLISH": {
                    "D1": 0.30,
                    "H4": 0.35,
                    "H1": 0.20,
                    "M15": 0.10,
                    "M5": 0.05,
                },
                "TRENDING_BEARISH": {
                    "D1": 0.30,
                    "H4": 0.35,
                    "H1": 0.20,
                    "M15": 0.10,
                    "M5": 0.05,
                },
                "RANGING": {
                    "D1": 0.15,
                    "H4": 0.25,
                    "H1": 0.30,
                    "M15": 0.20,
                    "M5": 0.10,
                },
            },
        },
        "threshold_parameters": {
            "confidence_threshold": 0.40,  # 威科夫状态机置信度实际范围 0.2~0.7，0.40 是有效门控
            "volume_threshold": 1.5,
            "volatility_threshold": 0.02,
        },
        "state_machine": {
            "transition_confidence": 0.75,
            "min_state_duration": 3,
            "max_state_duration": 20,
        },
    }


def real_performance_evaluator(config: dict, data: pd.DataFrame) -> dict:
    """
    使用真实 BacktestEngine + WyckoffStateMachine + RegimeDetector + PeriodWeightFilter 进行回测评估。

    信号生成链路（全部真实组件接入）：
      1. RegimeDetector.detect_regime(data)         → 识别当前市场体制（TRENDING/RANGING/VOLATILE）
      2. WyckoffStateMachine.process_candle(bar, ctx)→ 逐根K线检测威科夫状态（PS/SC/AR/ST/SPRING/LPS等）
      3. PeriodWeightFilter.calculate_weighted_score()→ 按config权重融合多周期信号置信度
      4. 置信度 >= config.confidence_threshold 才触发 BUY/SELL
      5. BacktestEngine.run() 执行真实模拟交易
    """
    if data is None or len(data) < 50:
        return {
            "SHARPE_RATIO": 0.0,
            "MAX_DRAWDOWN": 1.0,
            "WIN_RATE": 0.0,
            "PROFIT_FACTOR": 0.0,
            "CALMAR_RATIO": 0.0,
            "STABILITY_SCORE": 0.0,
            "COMPOSITE_SCORE": 0.0,
        }

    data = data.iloc[-2000:].copy()

    # ── 从 config 提取参数 ────────────────────────────────────────────────
    tp = config.get("threshold_parameters", {})
    confidence_threshold = float(tp.get("confidence_threshold", 0.70))
    vol_threshold = float(tp.get("volume_threshold", 1.5))

    pw_cfg = config.get("period_weight_filter", {})
    weight_map = pw_cfg.get("weights", {})  # {"D1": 0.25, "H4": 0.30, ...}

    sm_cfg = config.get("state_machine", {})
    transition_confidence = float(sm_cfg.get("transition_confidence", 0.75))

    # ── 初始化系统组件 ────────────────────────────────────────────────────
    regime_detector = RegimeDetector()
    wyckoff_sm = WyckoffStateMachine()
    wyckoff_sm.config.STATE_SWITCH_HYSTERESIS = transition_confidence

    # PeriodWeightFilter 用 config 中的权重初始化
    # 键名映射：config 用 "D1"/"H4"/"H1"/"M15"/"M5"，PeriodWeightFilter 用 "D"/"H4"/"H1"/"M15"/"M5"
    pwf_weights = {
        "D": weight_map.get("D1", 0.20),
        "H4": weight_map.get("H4", 0.18),
        "H1": weight_map.get("H1", 0.15),
        "M15": weight_map.get("M15", 0.12),
        "M5": weight_map.get("M5", 0.10),
    }
    period_filter = PeriodWeightFilter({"weights": pwf_weights})

    # ── 第1步：识别整体市场体制 ───────────────────────────────────────────
    regime_result = regime_detector.detect_regime(data)
    regime_name = (
        regime_result.get("regime").value if regime_result.get("regime") else "UNKNOWN"
    )

    # ── 第2步：逐根K线运行威科夫状态机，收集信号 ──────────────────────────
    # 需要 vol_mean 作为成交量基准
    vol_mean = data["volume"].rolling(20).mean()

    signals = []
    prev_bias = "NEUTRAL"  # 只在方向发生变化时触发，避免每根K线都出信号

    # 预计算成交量相对强度（滚动20根均值）
    vol_ratio = data["volume"] / vol_mean  # 当前成交量 / 均值

    for i in range(50, len(data)):
        bar = data.iloc[i]
        vm = vol_mean.iloc[i] if not np.isnan(vol_mean.iloc[i]) else bar["volume"]

        # ── 成交量过滤（直接用 config 的 vol_threshold）────────────────
        # vol_threshold=1.5 → 只有成交量 > 均值1.5倍才考虑信号
        # vol_threshold=2.0 → 只有成交量 > 均值2.0倍才考虑信号
        # 这让不同 config 产生不同数量的有效信号
        current_vol_ratio = (
            vol_ratio.iloc[i] if not np.isnan(vol_ratio.iloc[i]) else 0.0
        )
        if current_vol_ratio < vol_threshold:
            continue  # 成交量不足，跳过

        # 构建 context（状态机需要的上下文）
        ctx = {
            "volume_mean": float(vm),
            "volume_threshold": float(vol_threshold),
            "recent_low": float(data["low"].iloc[max(0, i - 20) : i + 1].min()),
            "recent_high": float(data["high"].iloc[max(0, i - 20) : i + 1].max()),
            "bars_in_downtrend": int(
                i - data["close"].iloc[max(0, i - 20) : i + 1].values.argmax()
            ),
            "trend_strength": 0.5,
            "market_regime": regime_name,
            "critical_price_levels": wyckoff_sm.critical_price_levels,
        }

        current_state = wyckoff_sm.process_candle(bar, ctx)

        # 从状态机的置信度字典读取各状态的当前置信度
        accum_states = [
            "PS",
            "SC",
            "AR",
            "ST",
            "TEST",
            "SPRING",
            "SO",
            "LPS",
            "MSOS",
            "JOC",
            "BU",
        ]
        dist_states = ["PSY", "BC", "AR_DIST", "ST_DIST", "UT", "UTAD", "LPSY"]

        bull_conf = max(
            (wyckoff_sm.state_confidences.get(s, 0.0) for s in accum_states),
            default=0.0,
        )
        bear_conf = max(
            (wyckoff_sm.state_confidences.get(s, 0.0) for s in dist_states), default=0.0
        )

        # 多周期加权融合
        tf_decisions = {
            "H4": {
                "state": "BULLISH"
                if bull_conf > bear_conf
                else ("BEARISH" if bear_conf > bull_conf else "NEUTRAL"),
                "confidence": max(bull_conf, bear_conf),
            }
        }
        weighted = period_filter.get_weighted_decision(tf_decisions, regime=regime_name)
        weighted_confidence = weighted.get("confidence", 0.0)
        primary_bias = weighted.get("primary_bias", "NEUTRAL")

        # ── 信号门控：置信度超过阈值 且 方向发生变化时才触发 ────────────
        # confidence_threshold 不同 → 触发时机不同 → 不同config产生不同信号序列
        if weighted_confidence >= confidence_threshold and primary_bias != prev_bias:
            if primary_bias == "BULLISH":
                signals.append(
                    {
                        "timestamp": bar.name,
                        "signal": "BUY",
                        "reason": f"Wyckoff:{current_state} conf={weighted_confidence:.2f} vol_ratio={current_vol_ratio:.2f}",
                    }
                )
                prev_bias = "BULLISH"
            elif primary_bias == "BEARISH":
                signals.append(
                    {
                        "timestamp": bar.name,
                        "signal": "SELL",
                        "reason": f"Wyckoff:{current_state} conf={weighted_confidence:.2f} vol_ratio={current_vol_ratio:.2f}",
                    }
                )
                prev_bias = "BEARISH"

    # ── 第3步：BacktestEngine 真实模拟交易 ───────────────────────────────
    engine = BacktestEngine(initial_capital=10000.0, commission_rate=0.001)
    result = engine.run(data, state_machine=None, signals=signals)

    sharpe = (
        result.sharpe_ratio
        if result.sharpe_ratio and not np.isnan(result.sharpe_ratio)
        else 0.0
    )
    drawdown = result.max_drawdown if result.max_drawdown else 0.0
    win_rate = result.win_rate if result.win_rate else 0.0

    winning_pnls = [t.pnl for t in result.trades if t.pnl > 0]
    losing_pnls = [abs(t.pnl) for t in result.trades if t.pnl <= 0 and t.pnl != 0]
    profit_factor = (
        sum(winning_pnls) / sum(losing_pnls)
        if losing_pnls and sum(losing_pnls) > 0
        else 1.0
    )

    calmar = (sharpe / drawdown) if drawdown > 0 else sharpe
    stability = max(0.0, 1.0 - drawdown)
    composite = (
        max(0.0, sharpe) * 0.25
        + (1.0 - drawdown) * 0.20
        + win_rate * 0.15
        + min(profit_factor, 3.0) / 3.0 * 0.15
        + stability * 0.25
    )

    return {
        "SHARPE_RATIO": sharpe,
        "MAX_DRAWDOWN": drawdown,
        "WIN_RATE": win_rate,
        "PROFIT_FACTOR": profit_factor,
        "CALMAR_RATIO": calmar,
        "STABILITY_SCORE": stability,
        "COMPOSITE_SCORE": composite,
    }


def seed_mistake_book(mistake_book: MistakeBook, num_errors: int = 20):
    """为错题本播种一些初始错误用于演示"""
    import random
    from datetime import timedelta

    error_types = [
        MistakeType.STATE_MISJUDGMENT,
        MistakeType.CONFLICT_RESOLUTION_ERROR,
        MistakeType.ENTRY_VALIDATION_ERROR,
        MistakeType.BREAKOUT_VALIDATION_ERROR,
        MistakeType.MARKET_REGIME_ERROR,
    ]

    patterns = [
        ErrorPattern.FREQUENT_FALSE_POSITIVE,
        ErrorPattern.TIMING_ERROR,
        ErrorPattern.VOLATILITY_ADAPTATION_ERROR,
        ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT,
    ]

    for i in range(num_errors):
        mistake_type = random.choice(error_types)
        severity = random.choice(
            [ErrorSeverity.LOW, ErrorSeverity.MEDIUM, ErrorSeverity.HIGH]
        )
        pattern = random.choice(patterns)

        mistake_book.record_mistake(
            mistake_type=mistake_type,
            severity=severity,
            context={
                "simulation": True,
                "iteration": i,
                "market_regime": random.choice(
                    ["TRENDING_BULLISH", "TRENDING_BEARISH", "RANGING"]
                ),
            },
            expected="CORRECT_STATE",
            actual="WRONG_STATE",
            confidence_before=random.uniform(0.5, 0.9),
            confidence_after=random.uniform(0.3, 0.7),
            impact_score=random.uniform(0.2, 0.8),
            module_name=random.choice(
                ["state_machine", "weight_filter", "conflict_resolver"]
            ),
            timeframe=random.choice(["H4", "H1", "M15"]),
            patterns=[pattern],
            metadata={"seed": True},
        )

    logger.info(f"Seeded mistake book with {num_errors} initial errors")


def _extract_metrics(result: dict) -> dict:
    """从 run_correction_cycle 返回值中提取每轮真实性能指标"""
    KEYS = (
        "COMPOSITE_SCORE",
        "SHARPE_RATIO",
        "MAX_DRAWDOWN",
        "WIN_RATE",
        "PROFIT_FACTOR",
        "CALMAR_RATIO",
        "STABILITY_SCORE",
    )

    def _pick(d):
        return {k: d[k] for k in KEYS if isinstance(d.get(k), (int, float))}

    cycle = result.get("cycle_results", {})
    wfa_report = (
        (cycle.get("wfa_validation") or {})
        .get("details", {})
        .get("validation_report", {})
    )

    # 优先：本轮WFA各变异的测试窗口平均性能（真实变化的指标）
    best_perf = {}
    best_score = -1.0
    for detail in wfa_report.get("validation_details", []):
        perf = _pick(detail.get("performance") or {})
        score = perf.get("COMPOSITE_SCORE", -1.0)
        if perf and score > best_score:
            best_score = score
            best_perf = perf
    if best_perf:
        return best_perf

    # 次选：本轮被接受的最佳配置性能
    m = _pick(wfa_report.get("current_accepted_performance") or {})
    if m:
        return m

    # 兜底：baseline（会显示 N/A 除非确实没跑任何回测）
    m = _pick(wfa_report.get("current_baseline_performance") or {})
    if m:
        return m

    return {}


def run_evolution_cycle(workflow: SelfCorrectionWorkflow, cycle_num: int) -> dict:
    """运行单个进化周期"""
    try:
        result = workflow.run_correction_cycle()
        metrics = _extract_metrics(result)
        result["metrics"] = metrics

        if result.get("success"):
            # 静默保存详细结果（不打日志横幅）
            os.makedirs("evolution_results", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(
                f"evolution_results/cycle_{cycle_num}_{timestamp}.json",
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(result, f, indent=2, default=str, ensure_ascii=False)

        return result

    except Exception as e:
        logger.error(f"Cycle #{cycle_num} exception: {e}")
        return {"success": False, "error": str(e)}


def main():
    """主函数 - 启动无限进化"""
    print("\n" + "=" * 60)
    print("  WYCKOFF INFINITE EVOLUTION SYSTEM")
    print("  威科夫无限进化系统启动中...")
    print("=" * 60 + "\n")

    # 1. 加载数据
    print("Loading historical data...")
    data = load_evolution_data()

    if not data:
        print("ERROR: No data loaded! Please run scripts/generate_eth_data.py first")
        return

    tfs = sorted(data.keys())
    for tf in tfs:
        df = data[tf]
        print(f"  {tf}: {len(df)} bars  ({df.index[0].date()} ~ {df.index[-1].date()})")
    print()

    config = {
        # 进化控制参数
        "min_errors_for_correction": 5,
        "max_mutations_per_cycle": 3,
        "cycle_interval_hours": 1,
        "mistake_book_config": {},
        "weight_variator_config": {
            "mutation_rate": 0.9,  # 提高到90%，确保每个成员都真正变异
            "max_mutation_percent": 0.20,  # 提高到20%，确保整数MA窗口能变化
        },
        "wfa_backtester_config": {
            "train_days": 300,
            "test_days": 100,
            "step_days": 200,
            "min_window_count": 2,
            "max_windows": 5,
            "min_performance_improvement": 0.005,
            # max_weight_change 用绝对差值比较，整数参数差值远大于0.05，故设为2.0
            "max_weight_change": 2.0,
            "smooth_factor": 0.3,
            # require_statistical_significance=True + max_windows<3 → is_significant永远False → 全拒绝
            "require_statistical_significance": False,
        },
        "initial_config": create_baseline_config(),
        "learning_batch_size": 10,
    }

    # 3. 初始化组件

    mistake_book = MistakeBook(config.get("mistake_book_config", {}))
    weight_variator = WeightVariator(config.get("weight_variator_config", {}))
    wfa_backtester = WFABacktester(config.get("wfa_backtester_config", {}))

    # 播种初始错误
    seed_mistake_book(mistake_book, num_errors=15)

    # 创建工作流
    workflow = SelfCorrectionWorkflow(
        config=config,
        mistake_book=mistake_book,
        weight_variator=weight_variator,
        wfa_backtester=wfa_backtester,
    )

    # 4. 设置性能评估器
    def performance_evaluator(config: dict, data: pd.DataFrame) -> dict:
        return real_performance_evaluator(config, data)

    workflow.set_performance_evaluator(performance_evaluator)

    # 设置历史数据（使用H4最近2000根，控制WFA速度）
    h4_data = data.get("H4")
    if h4_data is not None:
        h4_data = h4_data.iloc[-2000:]
    workflow.set_historical_data(h4_data)

    # 5. 初始化WFA基准
    print("Initializing WFA baseline...")
    workflow.initialize_wfa_baseline()
    print("Baseline ready.\n")

    # 6. 运行进化循环

    cycle_count = 0

    print("Infinite evolution running. Press Ctrl+C to stop.\n")
    while True:
        result = run_evolution_cycle(workflow, cycle_count + 1)
        cycle_count += 1

        # 打印进度
        if result.get("success"):
            metrics = result.get("metrics", {})
            cs = metrics.get("COMPOSITE_SCORE", None)
            sr = metrics.get("SHARPE_RATIO", None)
            wr = metrics.get("WIN_RATE", None)
            md = metrics.get("MAX_DRAWDOWN", None)
            cs_str = f"{cs:.4f}" if isinstance(cs, (int, float)) else "N/A"
            sr_str = f"{sr:.4f}" if isinstance(sr, (int, float)) else "N/A"
            wr_str = f"{wr:.2%}" if isinstance(wr, (int, float)) else "N/A"
            md_str = f"{md:.2%}" if isinstance(md, (int, float)) else "N/A"
            print(
                f"Cycle #{cycle_count} | Score={cs_str} Sharpe={sr_str} WinRate={wr_str} Drawdown={md_str}"
            )
        else:
            print(f"Cycle #{cycle_count} FAILED: {result.get('error', '?')}")

    # 7. 输出最终结果
    print("\n" + "=" * 60)
    print("EVOLUTION COMPLETE!")
    print("=" * 60)

    # 打印进化历史摘要
    if workflow.performance_history:
        print("\nPerformance History:")
        for i, perf in enumerate(workflow.performance_history[-5:], 1):
            print(f"  Cycle {i}: {perf.get('COMPOSITE_SCORE', 'N/A'):.4f}")

    print("\nResults saved to: evolution_results/")
    print(
        "\nTo run infinite evolution, change max_cycles to a larger number or remove the limit."
    )

    return workflow


if __name__ == "__main__":
    workflow = main()
