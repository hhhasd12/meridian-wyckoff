"""
debug_probe.py — 端到端数据流探针（独立版，不导入 run_evolution）
运行：python debug_probe.py
"""
import sys, os, json, copy, time, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 屏蔽所有内部日志
import logging
logging.basicConfig(level=logging.CRITICAL)
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).setLevel(logging.CRITICAL)

import numpy as np
import pandas as pd

SEP = "=" * 60

def _pp(obj, max_len=300):
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s[:max_len] + "…" if len(s) > max_len else s

# ── 内联：baseline config ──────────────────────────────────────────
def create_baseline_config():
    return {
        "period_weight_filter": {
            "weights": {"D1": 0.25, "H4": 0.30, "H1": 0.25, "M15": 0.12, "M5": 0.08},
            "regime_weights": {},
        },
        "threshold_parameters": {
            "confidence_threshold": 0.70,
            "volume_threshold": 1.5,
            "volatility_threshold": 0.02,
        },
        "state_machine": {
            "transition_confidence": 0.75,
            "min_state_duration": 3,
            "max_state_duration": 20,
        },
    }

# ── 内联：real_performance_evaluator ─────────────────────────────
def real_performance_evaluator(config, data):
    from src.backtest.engine import BacktestEngine
    if data is None or len(data) < 10:
        return {"COMPOSITE_SCORE": 0.0, "WIN_RATE": 0.0, "SHARPE_RATIO": 0.0,
                "MAX_DRAWDOWN": 1.0, "PROFIT_FACTOR": 0.0}
    data = data.iloc[-2000:].copy()
    engine = BacktestEngine(initial_capital=10000.0, commission_rate=0.001)
    tp = config.get("threshold_parameters", {})
    threshold     = float(tp.get("confidence_threshold", 0.70))
    vol_threshold = float(tp.get("volume_threshold", 1.5))
    weights = config.get("period_weight_filter", {}).get("weights", {})
    large_tf_w = weights.get("D1", 0.25) + weights.get("H4", 0.30)
    small_tf_w = weights.get("H1", 0.25) + weights.get("M15", 0.12) + weights.get("M5", 0.08)
    fast_window = max(5, min(100, int(5 + threshold * 50 + small_tf_w * 15)))
    slow_window = max(fast_window + 5, min(300, int(fast_window * 2 + vol_threshold * 20 + large_tf_w * 60)))
    close = data["close"]
    fast_ma = close.rolling(fast_window).mean()
    slow_ma = close.rolling(slow_window).mean()
    valid = fast_ma.notna() & slow_ma.notna()
    above = (fast_ma > slow_ma) & valid
    crossover = above.astype(int).diff()
    buy_idx  = data.index[crossover ==  1]
    sell_idx = data.index[crossover == -1]
    signals = (
        [{"timestamp": t, "signal": "BUY",  "reason": f"MA({fast_window}/{slow_window})"} for t in buy_idx] +
        [{"timestamp": t, "signal": "SELL", "reason": f"MA({fast_window}/{slow_window})"} for t in sell_idx]
    )
    signals.sort(key=lambda x: x["timestamp"])
    result = engine.run(data, state_machine=None, signals=signals)
    sharpe   = result.sharpe_ratio if result.sharpe_ratio and not np.isnan(result.sharpe_ratio) else 0.0
    drawdown = result.max_drawdown if result.max_drawdown else 0.0
    win_rate = result.win_rate     if result.win_rate     else 0.0
    winning_pnls = [t.pnl for t in result.trades if t.pnl > 0]
    losing_pnls  = [abs(t.pnl) for t in result.trades if t.pnl <= 0 and t.pnl != 0]
    profit_factor = sum(winning_pnls) / sum(losing_pnls) if losing_pnls and sum(losing_pnls) > 0 else 1.0
    stability = max(0.0, 1.0 - drawdown)
    composite = (
        max(0.0, sharpe) * 0.25 + (1.0 - drawdown) * 0.20 + win_rate * 0.15
        + min(profit_factor, 3.0) / 3.0 * 0.15 + stability * 0.25
    )
    return {
        "fast_window": fast_window, "slow_window": slow_window,
        "n_signals": len(signals), "n_trades": result.total_trades,
        "SHARPE_RATIO": sharpe, "MAX_DRAWDOWN": drawdown, "WIN_RATE": win_rate,
        "PROFIT_FACTOR": profit_factor, "CALMAR_RATIO": (sharpe/drawdown if drawdown>0 else sharpe),
        "STABILITY_SCORE": stability, "COMPOSITE_SCORE": composite,
    }

# ── 内联：_extract_metrics（与 run_evolution.py 完全一致）────────
def _extract_metrics(result):
    KEYS = ("COMPOSITE_SCORE","SHARPE_RATIO","MAX_DRAWDOWN","WIN_RATE",
            "PROFIT_FACTOR","CALMAR_RATIO","STABILITY_SCORE")
    def _pick(d):
        return {k: d[k] for k in KEYS if isinstance((d or {}).get(k), (int, float))}
    cycle = result.get("cycle_results", {})
    wfa_report = (cycle.get("wfa_validation") or {}).get("details", {}).get("validation_report", {})
    best_perf, best_score = {}, -1.0
    for detail in wfa_report.get("validation_details", []):
        perf = _pick(detail.get("performance") or {})
        score = perf.get("COMPOSITE_SCORE", -1.0)
        if perf and score > best_score:
            best_score, best_perf = score, perf
    if best_perf:
        return "branch=validation_details", best_perf
    m = _pick(wfa_report.get("current_accepted_performance") or {})
    if m:
        return "branch=current_accepted", m
    m = _pick(wfa_report.get("current_baseline_performance") or {})
    if m:
        return "branch=baseline(FALLBACK)", m
    return "branch=EMPTY", {}


# ══════════════════════════════════════════════════════════════════
print(SEP)
print("PROBE-1: H4 数据层")
print(SEP)

h4 = None
for path in ["data/binance_ETH_USDT_4h_730d.pkl", "data/ETHUSDT_4h.csv"]:
    if os.path.exists(path):
        if path.endswith(".pkl"):
            with open(path, "rb") as f:
                h4 = pickle.load(f)
            src = "pkl"
        else:
            h4 = pd.read_csv(path, index_col=0, parse_dates=True)
            h4.columns = [c.lower() for c in h4.columns]
            src = "csv"
        break

if h4 is None:
    print("ERROR: H4数据文件不存在！请先运行 scripts/generate_eth_data.py")
    sys.exit(1)

idx0 = h4.index[0]
print(f"  来源={src}  行数={len(h4)}")
print(f"  index类型={type(idx0).__name__}  tz-aware={getattr(idx0,'tzinfo',None) is not None}")
print(f"  close范围={h4['close'].min():.1f}~{h4['close'].max():.1f}  NaN={h4['close'].isna().sum()}")
h4 = h4.iloc[-2000:].copy()
print(f"  截取后行数={len(h4)}")


# ══════════════════════════════════════════════════════════════════
print()
print(SEP)
print("PROBE-2: BacktestEngine 信号执行（手工3对BUY/SELL）")
print(SEP)

from src.backtest.engine import BacktestEngine
engine = BacktestEngine(initial_capital=10000.0, commission_rate=0.001)
idx = h4.index
manual_signals = [
    {"timestamp": idx[50],  "signal": "BUY",  "reason": "probe"},
    {"timestamp": idx[100], "signal": "SELL", "reason": "probe"},
    {"timestamp": idx[200], "signal": "BUY",  "reason": "probe"},
    {"timestamp": idx[250], "signal": "SELL", "reason": "probe"},
    {"timestamp": idx[400], "signal": "BUY",  "reason": "probe"},
    {"timestamp": idx[450], "signal": "SELL", "reason": "probe"},
]
t0 = time.time()
result = engine.run(h4, state_machine=None, signals=manual_signals)
print(f"  耗时={time.time()-t0:.3f}s  total_trades={result.total_trades}  win_rate={result.win_rate:.2%}")
if result.trades:
    for i, tr in enumerate(result.trades):
        print(f"  trade[{i}]: {tr.direction} price={tr.price:.2f} pnl={tr.pnl:.4f}")
else:
    print("  !! 0笔交易 — engine.run 信号全部没执行，时间戳匹配失败")


# ══════════════════════════════════════════════════════════════════
print()
print(SEP)
print("PROBE-3: real_performance_evaluator 敏感性（两个不同config）")
print(SEP)

cfg_a = create_baseline_config()   # threshold=0.70
cfg_b = create_baseline_config()
cfg_b["threshold_parameters"]["confidence_threshold"] = 0.90

t0 = time.time(); res_a = real_performance_evaluator(copy.deepcopy(cfg_a), h4); ta = time.time()-t0
t0 = time.time(); res_b = real_performance_evaluator(copy.deepcopy(cfg_b), h4); tb = time.time()-t0

print(f"  cfg_a(threshold=0.70): fast={res_a['fast_window']} slow={res_a['slow_window']}  "
      f"n_signals={res_a['n_signals']} n_trades={res_a['n_trades']}  "
      f"SCORE={res_a['COMPOSITE_SCORE']:.4f}  耗时={ta:.2f}s")
print(f"  cfg_b(threshold=0.90): fast={res_b['fast_window']} slow={res_b['slow_window']}  "
      f"n_signals={res_b['n_signals']} n_trades={res_b['n_trades']}  "
      f"SCORE={res_b['COMPOSITE_SCORE']:.4f}  耗时={tb:.2f}s")
print(f"  两SCORE是否不同: {res_a['COMPOSITE_SCORE'] != res_b['COMPOSITE_SCORE']}")
print(f"  WinRate a={res_a['WIN_RATE']:.2%}  b={res_b['WIN_RATE']:.2%}")


# ══════════════════════════════════════════════════════════════════
print()
print(SEP)
print("PROBE-4: WFABacktester.validate_mutations 输出结构")
print(SEP)

from src.core.wfa_backtester import WFABacktester

wfa = WFABacktester({
    "train_days": 300, "test_days": 100, "step_days": 200,
    "min_window_count": 2, "max_windows": 2,   # 只跑2窗口，快
    "min_performance_improvement": 0.01,
    "max_weight_change": 0.05, "smooth_factor": 0.3,
})
print(f"  wfa.min_window_count={wfa.min_window_count}  (期望2，若=5说明key未读入)")

def peval(cfg, data):
    r = real_performance_evaluator(cfg, data)
    # 只返回 WFABacktester 需要的 key（不含 fast_window 等探针字段）
    return {k: v for k, v in r.items() if k not in ("fast_window","slow_window","n_signals","n_trades")}

wfa.initialize_with_baseline(create_baseline_config(), h4, peval)
print(f"  baseline_performance keys: {list(wfa.baseline_performance.keys()) if wfa.baseline_performance else 'EMPTY'}")
has_cs_baseline = "COMPOSITE_SCORE" in (wfa.baseline_performance or {})
print(f"  baseline 含 COMPOSITE_SCORE: {has_cs_baseline}")

mut_cfg = copy.deepcopy(create_baseline_config())
mut_cfg["threshold_parameters"]["confidence_threshold"] = 0.50  # 明显不同

t0 = time.time()
accepted, rejected, report = wfa.validate_mutations([mut_cfg], h4, peval)
elapsed = time.time() - t0
print(f"  validate_mutations 耗时={elapsed:.2f}s  accepted={len(accepted)}  rejected={len(rejected)}")

details = report.get("validation_details", [])
print(f"  validation_details 数量: {len(details)}")
if details:
    d0 = details[0]
    print(f"  details[0] keys: {list(d0.keys())}")
    perf = d0.get("performance", {})
    print(f"  details[0]['performance'] 类型: {type(perf).__name__}")
    print(f"  details[0]['performance'] keys: {list(perf.keys()) if isinstance(perf, dict) else '非dict'}")
    has_cs = "COMPOSITE_SCORE" in (perf or {})
    print(f"  !! 含COMPOSITE_SCORE: {has_cs}  ← False则_extract_metrics永远走兜底")
    if not has_cs and isinstance(perf, dict):
        print(f"  performance 实际内容: {_pp(perf)}")
else:
    print("  !! validation_details 为空 — validate_mutations 没有执行任何config")
    print(f"  report: {_pp(report)}")


# ══════════════════════════════════════════════════════════════════
print()
print(SEP)
print("PROBE-5: _extract_metrics 走哪条分支")
print(SEP)

mock_result = {
    "success": True,
    "cycle_results": {
        "wfa_validation": {
            "details": {"validation_report": report}
        }
    }
}
branch, metrics = _extract_metrics(mock_result)
print(f"  分支: {branch}")
print(f"  返回内容: {_pp(metrics)}")
bp = report.get("current_baseline_performance", {})
ap = report.get("current_accepted_performance")
print(f"  current_baseline_performance keys: {list(bp.keys()) if bp else 'EMPTY'}")
print(f"  current_accepted_performance: {'None' if ap is None else list(ap.keys()) if ap else 'EMPTY'}")


# ══════════════════════════════════════════════════════════════════
print()
print(SEP)
print("PROBE-6: WeightVariator 变异差异性")
print(SEP)

from src.core.weight_variator import WeightVariator
wv = WeightVariator({"mutation_rate": 0.9, "max_mutation_percent": 0.20})
pop = wv.generate_initial_population(create_baseline_config())
print(f"  种群大小: {len(pop)}")
if len(pop) >= 2:
    p0 = pop[0]["config"].get("threshold_parameters", {})
    p1 = pop[1]["config"].get("threshold_parameters", {})
    w0 = pop[0]["config"].get("period_weight_filter", {}).get("weights", {})
    w1 = pop[1]["config"].get("period_weight_filter", {}).get("weights", {})
    print(f"  pop[0] threshold_parameters: {p0}")
    print(f"  pop[1] threshold_parameters: {p1}")
    print(f"  pop[0] weights: {w0}")
    print(f"  pop[1] weights: {w1}")
    full_same = pop[0]["config"] == pop[1]["config"]
    print(f"  pop[0] full config == pop[1]: {full_same}  ← True说明变异完全没生效")
else:
    print("  !! 种群大小<2")

print()
print(SEP)
print("PROBE 完成 — 请将输出贴回分析")
print(SEP)
