"""
trace_evolution.py — 全链路追踪脚本
每一步都打印输入/输出，确认系统真正在运行

运行方法：python trace_evolution.py
"""
import sys, os, time, copy, pickle, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 屏蔽内部日志，只看trace输出
import logging
logging.basicConfig(level=logging.CRITICAL)
for name in list(logging.root.manager.loggerDict):
    logging.getLogger(name).setLevel(logging.CRITICAL)

import numpy as np
import pandas as pd

SEP  = "=" * 70
SEP2 = "-" * 70

def hdr(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

def sub(title):
    print(f"\n{SEP2}\n  {title}\n{SEP2}")

def pp(obj, maxlen=200):
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False, indent=None)
    except Exception:
        s = str(obj)
    return s[:maxlen] + "…" if len(s) > maxlen else s

# ══════════════════════════════════════════════════════════════════════════
hdr("STEP-1  加载H4数据")
# ══════════════════════════════════════════════════════════════════════════
h4 = None
for path in ["data/binance_ETH_USDT_4h_730d.pkl", "data/ETHUSDT_4h.csv"]:
    if os.path.exists(path):
        if path.endswith(".pkl"):
            with open(path,"rb") as f: h4 = pickle.load(f)
            src = "pkl"
        else:
            h4 = pd.read_csv(path, index_col=0, parse_dates=True)
            h4.columns = [c.lower() for c in h4.columns]
            src = "csv"
        break

if h4 is None:
    print("ERROR: 找不到数据文件，请先运行 scripts/generate_eth_data.py")
    sys.exit(1)

print(f"  来源={src}  原始行数={len(h4)}")
h4 = h4.iloc[-2000:].copy()
print(f"  截取2000根  索引类型={type(h4.index[0]).__name__}  close均值={h4['close'].mean():.1f}")

# ══════════════════════════════════════════════════════════════════════════
hdr("STEP-2  初始化所有组件")
# ══════════════════════════════════════════════════════════════════════════

sub("2a. 导入模块")
t0 = time.time()
from src.core.wyckoff_state_machine import WyckoffStateMachine
from src.core.market_regime import RegimeDetector
from src.core.period_weight_filter import PeriodWeightFilter
from src.core.weight_variator import WeightVariator
from src.core.wfa_backtester import WFABacktester, ValidationResult
from src.core.mistake_book import MistakeBook, MistakeType, ErrorSeverity, ErrorPattern
from src.core.self_correction_workflow import SelfCorrectionWorkflow
from src.backtest.engine import BacktestEngine
print(f"  导入耗时={time.time()-t0:.2f}s  (全部成功)")

sub("2b. 创建 baseline config")
baseline_config = {
    "period_weight_filter": {
        "weights": {"D1": 0.25, "H4": 0.30, "H1": 0.25, "M15": 0.12, "M5": 0.08},
        "regime_weights": {},
    },
    "threshold_parameters": {
        "confidence_threshold": 0.40,
        "volume_threshold": 1.5,
        "volatility_threshold": 0.02,
    },
    "state_machine": {
        "transition_confidence": 0.75,
        "min_state_duration": 3,
        "max_state_duration": 20,
    },
}
print(f"  config keys: {list(baseline_config.keys())}")
print(f"  confidence_threshold={baseline_config['threshold_parameters']['confidence_threshold']}")

# ══════════════════════════════════════════════════════════════════════════
hdr("STEP-3  performance_evaluator 逐行测试")
# ══════════════════════════════════════════════════════════════════════════

sub("3a. RegimeDetector")
t0 = time.time()
rd = RegimeDetector()
regime_result = rd.detect_regime(h4)
regime = regime_result.get("regime")
regime_name = regime.value if regime else "UNKNOWN"
print(f"  耗时={time.time()-t0:.3f}s  体制={regime_name}  confidence={regime_result.get('confidence', '?'):.3f}")

sub("3b. WyckoffStateMachine — 逐K线运行（只跑前200根）")
t0 = time.time()
sm = WyckoffStateMachine()
sm.config.STATE_SWITCH_HYSTERESIS = 0.75
vol_mean = h4["volume"].rolling(20).mean()

state_counts = {}
conf_history = []
for i in range(50, 250):
    bar = h4.iloc[i]
    vm = vol_mean.iloc[i] if not np.isnan(vol_mean.iloc[i]) else bar["volume"]
    ctx = {
        "volume_mean": float(vm),
        "volume_threshold": 1.5,
        "recent_low": float(h4["low"].iloc[max(0,i-20):i+1].min()),
        "recent_high": float(h4["high"].iloc[max(0,i-20):i+1].max()),
        "bars_in_downtrend": int(i - h4["close"].iloc[max(0,i-20):i+1].values.argmax()),
        "trend_strength": 0.5,
        "market_regime": regime_name,
        "critical_price_levels": sm.critical_price_levels,
    }
    state = sm.process_candle(bar, ctx)
    state_str = str(state) if state else "None"
    state_counts[state_str] = state_counts.get(state_str, 0) + 1

    accum = ["PS","SC","AR","ST","TEST","SPRING","SO","LPS","MSOS","JOC","BU"]
    dist  = ["PSY","BC","AR_DIST","ST_DIST","UT","UTAD","LPSY"]
    bull = max((sm.state_confidences.get(s,0.0) for s in accum), default=0.0)
    bear = max((sm.state_confidences.get(s,0.0) for s in dist),  default=0.0)
    conf_history.append((bull, bear))

elapsed_sm = time.time()-t0
print(f"  200根耗时={elapsed_sm:.2f}s  (预期: 完整2000根≈{elapsed_sm/200*2000:.1f}s)")
print(f"  状态分布: {dict(list(state_counts.items())[:5])}")
bull_vals = [c[0] for c in conf_history]
bear_vals = [c[1] for c in conf_history]
print(f"  bull_conf: min={min(bull_vals):.3f} max={max(bull_vals):.3f} mean={np.mean(bull_vals):.3f}")
print(f"  bear_conf: min={min(bear_vals):.3f} max={max(bear_vals):.3f} mean={np.mean(bear_vals):.3f}")

sub("3c. PeriodWeightFilter.get_weighted_decision")
pwf = PeriodWeightFilter({"weights": {"D": 0.25, "H4": 0.30, "H1": 0.25, "M15": 0.12, "M5": 0.08}})
# 用上面最后一根bar的置信度测试
last_bull, last_bear = conf_history[-1]
tf_dec = {"H4": {"state": "BULLISH" if last_bull > last_bear else "BEARISH", "confidence": max(last_bull, last_bear)}}
weighted = pwf.get_weighted_decision(tf_dec, regime=regime_name)
print(f"  输入: {pp(tf_dec)}")
print(f"  输出: primary_bias={weighted.get('primary_bias')}  confidence={weighted.get('confidence'):.4f}")

sub("3d. 信号生成 — 完整2000根bar（记录threshold触发情况）")
t0 = time.time()
sm2 = WyckoffStateMachine()
sm2.config.STATE_SWITCH_HYSTERESIS = 0.75
vol_mean = h4["volume"].rolling(20).mean()
threshold = 0.40

signals_detailed = []
prev_bias = "NEUTRAL"
signal_moments = []  # 记录每次信号：(i, bias, conf)

for i in range(50, len(h4)):
    bar = h4.iloc[i]
    vm = vol_mean.iloc[i] if not np.isnan(vol_mean.iloc[i]) else bar["volume"]
    ctx = {
        "volume_mean": float(vm), "volume_threshold": 1.5,
        "recent_low": float(h4["low"].iloc[max(0,i-20):i+1].min()),
        "recent_high": float(h4["high"].iloc[max(0,i-20):i+1].max()),
        "bars_in_downtrend": int(i - h4["close"].iloc[max(0,i-20):i+1].values.argmax()),
        "trend_strength": 0.5, "market_regime": regime_name,
        "critical_price_levels": sm2.critical_price_levels,
    }
    state = sm2.process_candle(bar, ctx)
    accum = ["PS","SC","AR","ST","TEST","SPRING","SO","LPS","MSOS","JOC","BU"]
    dist  = ["PSY","BC","AR_DIST","ST_DIST","UT","UTAD","LPSY"]
    bull = max((sm2.state_confidences.get(s,0.0) for s in accum), default=0.0)
    bear = max((sm2.state_confidences.get(s,0.0) for s in dist),  default=0.0)

    tf_dec2 = {"H4": {"state": "BULLISH" if bull > bear else ("BEARISH" if bear > bull else "NEUTRAL"), "confidence": max(bull,bear)}}
    w2 = pwf.get_weighted_decision(tf_dec2, regime=regime_name)
    wconf = w2.get("confidence", 0.0)
    pbias = w2.get("primary_bias", "NEUTRAL")

    if wconf >= threshold and pbias != prev_bias and pbias != "NEUTRAL":
        sig_type = "BUY" if pbias == "BULLISH" else "SELL"
        signals_detailed.append({"timestamp": bar.name, "signal": sig_type,
                                  "reason": f"conf={wconf:.3f} state={state}"})
        signal_moments.append((i, pbias, wconf))
        prev_bias = pbias

elapsed_sig = time.time()-t0
print(f"  2000根耗时={elapsed_sig:.2f}s  信号总数={len(signals_detailed)}")
if signal_moments:
    print(f"  前5个信号: {[(s[0], s[1], f'{s[2]:.3f}') for s in signal_moments[:5]]}")
    buys  = sum(1 for s in signals_detailed if s["signal"]=="BUY")
    sells = sum(1 for s in signals_detailed if s["signal"]=="SELL")
    print(f"  BUY={buys}  SELL={sells}")
else:
    print("  !! 0个信号 — threshold或逻辑有问题！")

sub("3e. BacktestEngine 执行")
t0 = time.time()
engine = BacktestEngine(initial_capital=10000.0, commission_rate=0.001)
result = engine.run(h4, state_machine=None, signals=signals_detailed)
elapsed_bt = time.time()-t0
print(f"  耗时={elapsed_bt:.3f}s  total_trades={result.total_trades}")
print(f"  win_rate={result.win_rate:.2%}  sharpe={result.sharpe_ratio:.4f}  drawdown={result.max_drawdown:.4f}")
if result.trades:
    print(f"  前3笔交易: {[(t.direction, f'{t.price:.1f}', f'{t.pnl:.2f}') for t in result.trades[:3]]}")
else:
    print("  !! 0笔交易！时间戳匹配失败？")

# ══════════════════════════════════════════════════════════════════════════
hdr("STEP-4  WeightVariator 生成变异体")
# ══════════════════════════════════════════════════════════════════════════

wv = WeightVariator({"mutation_rate": 0.9, "max_mutation_percent": 0.20})
t0 = time.time()
pop = wv.generate_initial_population(baseline_config)
elapsed_wv = time.time()-t0
print(f"  耗时={elapsed_wv:.3f}s  种群返回类型={type(pop).__name__}  种群大小={len(pop) if pop else 'None/0'}")

if pop and len(pop) >= 2:
    cfg0 = pop[0]["config"]
    cfg1 = pop[1]["config"]
    t0_thresh = cfg0.get("threshold_parameters",{}).get("confidence_threshold","?")
    t1_thresh = cfg1.get("threshold_parameters",{}).get("confidence_threshold","?")
    print(f"  pop[0].confidence_threshold = {t0_thresh}")
    print(f"  pop[1].confidence_threshold = {t1_thresh}")
    identical = cfg0 == cfg1
    print(f"  pop[0] == pop[1]: {identical}  ← True则变异没有生效")
else:
    print("  !! 种群为空或<2，generate_initial_population 有问题")

# ══════════════════════════════════════════════════════════════════════════
hdr("STEP-5  WFABacktester 完整验证")
# ══════════════════════════════════════════════════════════════════════════

sub("5a. 准备 performance_evaluator（真实版）")

def real_perf_eval(config, data):
    """真实性能评估器"""
    if data is None or len(data) < 50:
        return {"COMPOSITE_SCORE": 0.0, "SHARPE_RATIO": 0.0, "MAX_DRAWDOWN": 1.0,
                "WIN_RATE": 0.0, "PROFIT_FACTOR": 0.0, "CALMAR_RATIO": 0.0, "STABILITY_SCORE": 0.0}
    data = data.iloc[-2000:].copy()
    tp = config.get("threshold_parameters", {})
    threshold_ = float(tp.get("confidence_threshold", 0.40))
    vol_thr = float(tp.get("volume_threshold", 1.5))
    sm_cfg = config.get("state_machine", {})
    trans_conf = float(sm_cfg.get("transition_confidence", 0.75))

    pw_cfg = config.get("period_weight_filter", {})
    wmap = pw_cfg.get("weights", {})
    pwf_w = {"D": wmap.get("D1",0.20), "H4": wmap.get("H4",0.18),
              "H1": wmap.get("H1",0.15), "M15": wmap.get("M15",0.12), "M5": wmap.get("M5",0.10)}

    rd_ = RegimeDetector()
    rr = rd_.detect_regime(data)
    reg = rr.get("regime")
    reg_name = reg.value if reg else "UNKNOWN"

    sm_ = WyckoffStateMachine()
    sm_.config.STATE_SWITCH_HYSTERESIS = trans_conf
    pf_ = PeriodWeightFilter({"weights": pwf_w})
    vm_ = data["volume"].rolling(20).mean()

    sigs = []
    pbias_ = "NEUTRAL"
    for ii in range(50, len(data)):
        bar_ = data.iloc[ii]
        vm_i = vm_.iloc[ii] if not np.isnan(vm_.iloc[ii]) else bar_["volume"]
        ctx_ = {
            "volume_mean": float(vm_i), "volume_threshold": float(vol_thr),
            "recent_low": float(data["low"].iloc[max(0,ii-20):ii+1].min()),
            "recent_high": float(data["high"].iloc[max(0,ii-20):ii+1].max()),
            "bars_in_downtrend": int(ii - data["close"].iloc[max(0,ii-20):ii+1].values.argmax()),
            "trend_strength": 0.5, "market_regime": reg_name,
            "critical_price_levels": sm_.critical_price_levels,
        }
        st_ = sm_.process_candle(bar_, ctx_)
        acc_ = ["PS","SC","AR","ST","TEST","SPRING","SO","LPS","MSOS","JOC","BU"]
        dis_ = ["PSY","BC","AR_DIST","ST_DIST","UT","UTAD","LPSY"]
        bull_ = max((sm_.state_confidences.get(s,0.0) for s in acc_), default=0.0)
        bear_ = max((sm_.state_confidences.get(s,0.0) for s in dis_),  default=0.0)
        tfd_ = {"H4": {"state": "BULLISH" if bull_ > bear_ else ("BEARISH" if bear_ > bull_ else "NEUTRAL"),
                        "confidence": max(bull_, bear_)}}
        wd_ = pf_.get_weighted_decision(tfd_, regime=reg_name)
        wc_ = wd_.get("confidence", 0.0)
        pb_ = wd_.get("primary_bias", "NEUTRAL")
        if wc_ >= threshold_ and pb_ != pbias_ and pb_ != "NEUTRAL":
            sig_t_ = "BUY" if pb_ == "BULLISH" else "SELL"
            sigs.append({"timestamp": bar_.name, "signal": sig_t_, "reason": f"state={st_}"})
            pbias_ = pb_

    eng_ = BacktestEngine(initial_capital=10000.0, commission_rate=0.001)
    res_ = eng_.run(data, state_machine=None, signals=sigs)
    sharpe_  = res_.sharpe_ratio if res_.sharpe_ratio and not np.isnan(res_.sharpe_ratio) else 0.0
    dd_      = res_.max_drawdown if res_.max_drawdown else 0.0
    wr_      = res_.win_rate if res_.win_rate else 0.0
    wp_ = [t.pnl for t in res_.trades if t.pnl > 0]
    lp_ = [abs(t.pnl) for t in res_.trades if t.pnl <= 0 and t.pnl != 0]
    pf_ = sum(wp_)/sum(lp_) if lp_ and sum(lp_) > 0 else 1.0
    stab_ = max(0.0, 1.0 - dd_)
    comp_ = max(0.0,sharpe_)*0.25 + (1.0-dd_)*0.20 + wr_*0.15 + min(pf_,3.0)/3.0*0.15 + stab_*0.25
    return {"COMPOSITE_SCORE": comp_, "SHARPE_RATIO": sharpe_, "MAX_DRAWDOWN": dd_,
            "WIN_RATE": wr_, "PROFIT_FACTOR": pf_, "CALMAR_RATIO": (sharpe_/dd_ if dd_>0 else sharpe_),
            "STABILITY_SCORE": stab_,
            "_debug_signals": len(sigs), "_debug_trades": res_.total_trades}

sub("5b. evaluate baseline config")
t0 = time.time()
baseline_perf = real_perf_eval(baseline_config, h4)
bt_elapsed = time.time()-t0
print(f"  耗时={bt_elapsed:.2f}s")
print(f"  信号数={baseline_perf.get('_debug_signals')}  交易数={baseline_perf.get('_debug_trades')}")
print(f"  COMPOSITE_SCORE={baseline_perf.get('COMPOSITE_SCORE'):.4f}")
print(f"  SHARPE={baseline_perf.get('SHARPE_RATIO'):.4f}  WINRATE={baseline_perf.get('WIN_RATE'):.2%}  DRAWDOWN={baseline_perf.get('MAX_DRAWDOWN'):.4f}")

sub("5c. 制造明显不同的变异config并评估")
mut_cfg = copy.deepcopy(baseline_config)
mut_cfg["threshold_parameters"]["confidence_threshold"] = 0.60   # 明显不同
mut_cfg["threshold_parameters"]["volume_threshold"] = 2.0
t0 = time.time()
mut_perf = real_perf_eval(mut_cfg, h4)
mut_elapsed = time.time()-t0
print(f"  (threshold=0.60, vol=2.0) 耗时={mut_elapsed:.2f}s")
print(f"  信号数={mut_perf.get('_debug_signals')}  交易数={mut_perf.get('_debug_trades')}")
print(f"  COMPOSITE_SCORE={mut_perf.get('COMPOSITE_SCORE'):.4f}")
diff_score = abs(baseline_perf.get("COMPOSITE_SCORE",0) - mut_perf.get("COMPOSITE_SCORE",0))
print(f"  >> 与baseline的分数差={diff_score:.4f}  (>0则config确实影响结果)")

sub("5d. 构建 WFABacktester 并运行 validate_mutations")
wfa_config = {
    "train_days": 300, "test_days": 100, "step_days": 200,
    "min_window_count": 2, "max_windows": 3,
    "min_performance_improvement": 0.01,
    "max_weight_change": 0.50,
    "smooth_factor": 0.3,
}
wfa = WFABacktester(wfa_config)
print(f"  min_window_count={wfa.min_window_count}  max_weight_change={wfa.max_weight_change}")

# 初始化baseline
def peval_clean(cfg, data):
    r = real_perf_eval(cfg, data)
    return {k: v for k, v in r.items() if not k.startswith("_debug")}

t0 = time.time()
bp = wfa.initialize_with_baseline(baseline_config, h4, peval_clean)
init_elapsed = time.time()-t0
print(f"  initialize_with_baseline 耗时={init_elapsed:.2f}s")
print(f"  baseline_performance keys={list((bp or {}).keys())[:5]}")
print(f"  COMPOSITE_SCORE={bp.get('COMPOSITE_SCORE','MISSING'):.4f}" if bp and "COMPOSITE_SCORE" in bp else f"  COMPOSITE_SCORE=MISSING  bp={bp}")

# 准备2个变异体
mutations = [mut_cfg, copy.deepcopy(baseline_config)]
mutations[1]["threshold_parameters"]["confidence_threshold"] = 0.25  # 更低threshold

print(f"\n  开始 validate_mutations ({len(mutations)} 个变异体)...")
t0 = time.time()
accepted, rejected, report = wfa.validate_mutations(mutations, h4, peval_clean)
wfa_elapsed = time.time()-t0

print(f"\n  [OK] validate_mutations 完成！耗时={wfa_elapsed:.2f}s")
print(f"  accepted={len(accepted)}  rejected={len(rejected)}")
print(f"  acceptance_rate={report.get('acceptance_rate',0):.2%}")
print(f"  average_improvement={report.get('average_improvement',0):.4f}")

details = report.get("validation_details", [])
print(f"  validation_details 数量={len(details)}")
for di, det in enumerate(details):
    result_val = det.get("result","?")
    perf = det.get("performance") or {}
    imp = det.get("improvement", 0)
    print(f"  detail[{di}]: result={result_val}  improvement={imp:.4f}")
    if perf:
        cs = perf.get("COMPOSITE_SCORE", "MISSING")
        print(f"    performance COMPOSITE_SCORE={cs:.4f}" if isinstance(cs, float) else f"    performance={pp(perf)}")
    else:
        print(f"    !! performance=None/空 ← 说明被check拒绝或WFA没运行")

# ══════════════════════════════════════════════════════════════════════════
hdr("STEP-6  _extract_metrics 追踪")
# ══════════════════════════════════════════════════════════════════════════

KEYS = ("COMPOSITE_SCORE","SHARPE_RATIO","MAX_DRAWDOWN","WIN_RATE","PROFIT_FACTOR","CALMAR_RATIO","STABILITY_SCORE")
def _pick(d):
    return {k: d[k] for k in KEYS if isinstance((d or {}).get(k), (int, float))}

mock_result = {"success": True, "cycle_results": {
    "wfa_validation": {"details": {"validation_report": report}}
}}
wfa_report = (mock_result.get("cycle_results",{}).get("wfa_validation") or {}).get("details",{}).get("validation_report",{})

best_perf, best_score = {}, -1.0
for det in wfa_report.get("validation_details", []):
    perf = _pick(det.get("performance") or {})
    score = perf.get("COMPOSITE_SCORE", -1.0)
    if perf and score > best_score:
        best_score, best_perf = score, perf

if best_perf:
    print(f"  [OK] 走 validation_details 分支  COMPOSITE_SCORE={best_perf.get('COMPOSITE_SCORE'):.4f}")
else:
    m = _pick(wfa_report.get("current_accepted_performance") or {})
    if m:
        print(f"  → 走 current_accepted 分支  COMPOSITE_SCORE={m.get('COMPOSITE_SCORE'):.4f}")
    else:
        m = _pick(wfa_report.get("current_baseline_performance") or {})
        if m:
            print(f"  !! 走 baseline兜底  COMPOSITE_SCORE={m.get('COMPOSITE_SCORE'):.4f}  ← 这就是每轮数字相同的原因")
        else:
            print("  !! 所有分支都空 → 返回 {}")

# ══════════════════════════════════════════════════════════════════════════
hdr("STEP-7  完整 SelfCorrectionWorkflow 一次 cycle")
# ══════════════════════════════════════════════════════════════════════════

from src.core.mistake_book import MistakeBook, MistakeType, ErrorSeverity, ErrorPattern
import random

mb = MistakeBook({})
patterns = [ErrorPattern.FREQUENT_FALSE_POSITIVE, ErrorPattern.TIMING_ERROR,
            ErrorPattern.VOLATILITY_ADAPTATION_ERROR, ErrorPattern.MULTI_TIMEFRAME_MISALIGNMENT]
for i in range(15):
    mb.record_mistake(
        mistake_type=MistakeType.STATE_MISJUDGMENT,
        severity=random.choice([ErrorSeverity.LOW, ErrorSeverity.MEDIUM, ErrorSeverity.HIGH]),
        context={"sim": True, "i": i},
        expected="CORRECT", actual="WRONG",
        confidence_before=random.uniform(0.5,0.9), confidence_after=random.uniform(0.3,0.7),
        impact_score=random.uniform(0.2,0.8),
        module_name=random.choice(["state_machine","weight_filter"]),
        timeframe=random.choice(["H4","H1","M15"]),
        patterns=[random.choice(patterns)], metadata={"seed": True},
    )
print(f"  错题本已植入 {mb.get_statistics().get('total_errors',0)} 条错误")

wf_config = {
    "min_errors_for_correction": 5, "max_mutations_per_cycle": 3,
    "cycle_interval_hours": 1, "mistake_book_config": {},
    "weight_variator_config": {"mutation_rate": 0.9, "max_mutation_percent": 0.20},
    "wfa_backtester_config": {
        "train_days": 300, "test_days": 100, "step_days": 200,
        "min_window_count": 2, "max_windows": 2,
        "min_performance_improvement": 0.01,
        "max_weight_change": 0.50,
        "smooth_factor": 0.3,
    },
    "initial_config": baseline_config,
    "learning_batch_size": 10,
}
wv2 = WeightVariator(wf_config["weight_variator_config"])
wfa2 = WFABacktester(wf_config["wfa_backtester_config"])
workflow = SelfCorrectionWorkflow(config=wf_config, mistake_book=mb, weight_variator=wv2, wfa_backtester=wfa2)
workflow.set_performance_evaluator(peval_clean)
workflow.set_historical_data(h4)

sub("7a. initialize_wfa_baseline")
t0 = time.time()
workflow.initialize_wfa_baseline()
print(f"  耗时={time.time()-t0:.2f}s")

sub("7b. run_correction_cycle (max_windows=2, 应耗时 ≥10秒)")
t0 = time.time()
cycle_result = workflow.run_correction_cycle()
cycle_elapsed = time.time()-t0

print(f"\n  cycle 耗时={cycle_elapsed:.2f}s")
print(f"  success={cycle_result.get('success')}  stages={list(cycle_result.get('cycle_results',{}).keys())}")

# 追踪每个阶段
cr = cycle_result.get("cycle_results", {})
for stage_name, stage_data in cr.items():
    succ = stage_data.get("success","?")
    dur  = stage_data.get("duration_seconds","?")
    err  = stage_data.get("error_message","")
    print(f"\n  [{stage_name}] success={succ} dur={dur:.2f}s" if isinstance(dur, float) else f"\n  [{stage_name}] success={succ}")
    if err:
        print(f"    !! error={err}")

    if stage_name == "wfa_validation":
        vr = stage_data.get("details", {}).get("validation_report", {})
        vd = vr.get("validation_details", [])
        print(f"    validation_details数量={len(vd)}")
        for di, det in enumerate(vd):
            r_  = det.get("result","?")
            p_  = det.get("performance") or {}
            cs_ = p_.get("COMPOSITE_SCORE","MISSING")
            print(f"    detail[{di}]: result={r_}  COMPOSITE_SCORE={cs_:.4f}" if isinstance(cs_, float) else f"    detail[{di}]: result={r_}  COMPOSITE_SCORE=MISSING  perf={pp(p_)}")

# 最终指标提取
sub("7c. _extract_metrics 最终结果")
wfa_report_final = cr.get("wfa_validation", {}).get("details", {}).get("validation_report", {})
best_perf2, best_score2 = {}, -1.0
for det in wfa_report_final.get("validation_details", []):
    perf = _pick(det.get("performance") or {})
    score = perf.get("COMPOSITE_SCORE", -1.0)
    if perf and score > best_score2:
        best_score2, best_perf2 = score, perf

if best_perf2:
    print(f"  [OK] validation_details 分支  COMPOSITE_SCORE={best_perf2.get('COMPOSITE_SCORE'):.4f}")
    for k in ("SHARPE_RATIO","WIN_RATE","MAX_DRAWDOWN","PROFIT_FACTOR"):
        v = best_perf2.get(k)
        if isinstance(v, float): print(f"    {k}={v:.4f}")
elif wfa_report_final.get("current_accepted_performance"):
    m = _pick(wfa_report_final.get("current_accepted_performance"))
    print(f"  → current_accepted 分支  COMPOSITE_SCORE={m.get('COMPOSITE_SCORE'):.4f}")
else:
    m = _pick(wfa_report_final.get("current_baseline_performance") or {})
    if m:
        print(f"  !! baseline兜底 COMPOSITE_SCORE={m.get('COMPOSITE_SCORE'):.4f}  ← 还是旧问题！")
    else:
        print("  !! 所有分支空，返回 {}")

print(f"\n{SEP}")
print("TRACE 完成 — 请贴回此输出，我们根据结果决定下一步")
print(SEP)
