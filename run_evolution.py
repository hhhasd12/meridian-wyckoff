"""
威科夫系统无限进化启动器（v3.0 — GA + WFA + AntiOverfit）
=============================

功能：
1. 加载ETH历史数据（多时间周期）
2. 使用 StandardEvaluator（逐bar回测）替代旧 real_performance_evaluator
3. GA 遗传算法搜索最优配置
4. WFA 滚动窗口验证
5. AntiOverfit 五层防过拟合

运行方式：
    python run_evolution.py

注意：此脚本是独立运行方式，不通过 API 服务器。
"""

import json
import logging
import os
import sys
from datetime import datetime

# ── 修复 Windows GBK 终端乱码 ─────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 启动自检 ──────────────────────────────────────────────
from health_check import run_health_check, print_report, save_report


def _startup_health_check():
    """启动前全面自检，发现严重问题则阻止启动"""
    report = run_health_check(auto_fix=False)
    save_report(report)
    if not report.passed:
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

import numpy as np
import pandas as pd

from src.plugins.evolution.evaluator import StandardEvaluator
from src.plugins.evolution.genetic_algorithm import GAConfig, GeneticAlgorithm
from src.plugins.evolution.wfa_validator import WFAValidator
from src.plugins.evolution.anti_overfit import AntiOverfitGuard
from src.plugins.self_correction.mistake_book import MistakeBook

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setLevel(logging.INFO)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_handler)
logger.propagate = False


def load_evolution_data():
    """加载进化所需的多时间周期数据（CSV，再降频补全）"""
    data = {}

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

    for tf, csv_path in csv_map.items():
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            df = df.rename(columns=col_rename)
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

    # 降频补全
    if "M15" not in data and "H1" in data:
        data["M15"] = data["H1"]
        logger.warning("M15: no file found, using H1 data as substitute")
    if "M5" not in data and "H1" in data:
        h1 = data["H1"]
        agg_map = {"open": "first", "high": "max", "low": "min", "close": "last"}
        if "volume" in h1.columns:
            agg_map["volume"] = "sum"
        m5 = h1.resample("5min").agg(agg_map).dropna(subset=["open", "close"])
        data["M5"] = m5
        logger.warning("M5: no file found, resampled from H1 data")
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
            "confidence_threshold": 0.30,
            "volume_threshold": 1.0,
            "volatility_threshold": 0.02,
        },
        "state_machine": {
            "transition_confidence": 0.75,
            "min_state_duration": 3,
            "max_state_duration": 20,
        },
        "signal_control": {
            "cooldown_bars": 8,
            "min_agreement": 3,
        },
    }


def main():
    """主函数 — GA驱动的无限进化"""
    print("\n" + "=" * 60)
    print("  WYCKOFF EVOLUTION v3.0 — GA + WFA + AntiOverfit")
    print("=" * 60 + "\n")

    # 1. 加载数据
    print("Loading historical data...")
    data = load_evolution_data()
    if not data:
        print("ERROR: No data loaded! Please run fetch_data.py first")
        return

    for tf in sorted(data.keys()):
        df = data[tf]
        print(f"  {tf}: {len(df)} bars  ({df.index[0].date()} ~ {df.index[-1].date()})")
    print()

    # 2. 裁剪数据（以H4为锚点）
    h4_raw = data.get("H4")
    if h4_raw is None or len(h4_raw) < 50:
        print("ERROR: H4 data not available or too short!")
        return

    h4_trimmed = h4_raw.iloc[-2000:]
    h4_start, h4_end = h4_trimmed.index[0], h4_trimmed.index[-1]
    trimmed_data: dict[str, pd.DataFrame] = {"H4": h4_trimmed}
    for tf_key, tf_df in data.items():
        if tf_key == "H4":
            continue
        mask = (tf_df.index >= h4_start) & (tf_df.index <= h4_end)
        sliced = tf_df.loc[mask]
        if len(sliced) > 0:
            trimmed_data[tf_key] = sliced

    for tf_key in sorted(trimmed_data.keys()):
        print(f"  [trimmed] {tf_key}: {len(trimmed_data[tf_key])} bars")
    print()

    # 3. 初始化组件
    baseline_config = create_baseline_config()
    mistake_book = MistakeBook()
    evaluator = StandardEvaluator(mistake_book=mistake_book)
    anti_overfit = AntiOverfitGuard()

    ga_config = GAConfig(
        population_size=20,
        elite_count=2,
        tournament_size=3,
        crossover_rate=0.7,
        mutation_rate=0.9,
        mutation_strength=0.15,
        max_generations=50,
        convergence_patience=5,
    )
    ga = GeneticAlgorithm(baseline_config, ga_config)
    wfa = WFAValidator(evaluator_fn=evaluator)

    # 4. 无限进化循环
    print("Infinite GA evolution running. Press Ctrl+C to stop.\n")
    cycle_count = 0

    while True:
        cycle_count += 1
        try:
            # GA一代进化
            if cycle_count == 1:
                ga.initialize_population()

            ga.evaluate_population(evaluator, trimmed_data)
            ga.evolve_generation()
            ga.evaluate_population(evaluator, trimmed_data)

            best = ga.get_best()
            if best is None:
                print(f"Cycle #{cycle_count} FAILED: no best individual")
                continue

            stats = ga.get_population_stats()

            # WFA验证最佳个体
            wfa_report = wfa.validate(best.config, trimmed_data)

            # AntiOverfit 检查
            verdict_info = ""
            if best.backtest_result is not None:
                verdict = anti_overfit.check(
                    best.backtest_result,
                    train_sharpes=wfa_report.train_sharpes
                    if wfa_report.train_sharpes
                    else None,
                    test_sharpes=wfa_report.test_sharpes
                    if wfa_report.test_sharpes
                    else None,
                    n_trials=cycle_count,
                )
                verdict_info = f" AOF={'PASS' if verdict.passed else 'FAIL'}"

            # 打印进度
            wfa_status = "PASS" if wfa_report.passed else "FAIL"
            print(
                f"Cycle #{cycle_count} Gen={ga.generation} | "
                f"best={best.fitness:.4f} avg={stats['avg_fitness']:.4f} | "
                f"WFA={wfa_status} OOS-DR={wfa_report.oos_degradation_ratio:.2f}"
                f"{verdict_info}"
            )

            # 保存结果
            os.makedirs("evolution_results", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_data = {
                "cycle": cycle_count,
                "generation": ga.generation,
                "best_fitness": best.fitness,
                "avg_fitness": stats["avg_fitness"],
                "wfa_passed": wfa_report.passed,
                "oos_dr": wfa_report.oos_degradation_ratio,
                "config": best.config,
            }
            with open(
                f"evolution_results/cycle_{cycle_count}_{timestamp}.json",
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(result_data, f, indent=2, default=str, ensure_ascii=False)

        except KeyboardInterrupt:
            print("\n\nEvolution stopped by user.")
            break
        except Exception as e:
            logger.error(f"Cycle #{cycle_count} exception: {e}")
            print(f"Cycle #{cycle_count} FAILED: {e}")

    print("\n" + "=" * 60)
    print("EVOLUTION COMPLETE!")
    print(f"Total cycles: {cycle_count}")
    print("Results saved to: evolution_results/")
    print("=" * 60)


if __name__ == "__main__":
    main()
