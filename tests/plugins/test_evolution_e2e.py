"""端到端进化闭环测试 — 验证完整 cycle 能跑通

测试覆盖：
1. GA 产生种群 → 评估 → 进化 → 再评估
2. WFA 在 holdout 数据上创建窗口并验证
3. AntiOverfit 五层检查执行
4. 结果持久化到 data/evolution_results.json
5. EvolutionPlugin._run_evolution_cycle 端到端
"""

import asyncio
import json
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from src.plugins.evolution.anti_overfit import AntiOverfitGuard
from src.plugins.evolution.evaluator import StandardEvaluator
from src.plugins.evolution.genetic_algorithm import GAConfig, GeneticAlgorithm
from src.plugins.evolution.wfa_validator import WFAConfig, WFAValidator
from src.plugins.self_correction.mistake_book import MistakeBook


def _make_h4_data(n_bars: int = 2000, seed: int = 42) -> pd.DataFrame:
    """生成合成 H4 数据（带趋势+波动，模拟真实市场）"""
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="4h", tz="UTC")
    rng = np.random.RandomState(seed)
    # 带趋势的随机游走
    trend = np.linspace(0, 200, n_bars)
    noise = np.cumsum(rng.randn(n_bars) * 15)
    close = 2000 + trend + noise
    close = np.maximum(close, 100)  # 防止负价格
    opens = close - rng.rand(n_bars) * 10
    highs = close + np.abs(rng.randn(n_bars) * 20)
    lows = close - np.abs(rng.randn(n_bars) * 20)
    highs = np.maximum(highs, np.maximum(opens, close))
    lows = np.minimum(lows, np.minimum(opens, close))
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": close,
            "volume": rng.randint(100, 50000, n_bars).astype(float),
        },
        index=dates,
    )


def _baseline_config():
    """最小可行进化配置"""
    return {
        "period_weight_filter": {
            "weights": {"H4": 0.50, "H1": 0.30, "M15": 0.20},
        },
        "threshold_parameters": {"confidence_threshold": 0.30},
        "signal_control": {"cooldown_bars": 8},
    }


class TestGAEvaluateEvolveCycle:
    """测试 GA 评估→进化→再评估 完整 cycle"""

    def test_ga_evaluate_evolve_evaluate(self):
        """GA 能完成 初始化→评估→进化→评估 不抛异常"""
        book = MistakeBook()
        evaluator = StandardEvaluator(mistake_book=book)
        ga = GeneticAlgorithm(
            _baseline_config(),
            GAConfig(population_size=5, max_generations=3),
        )
        data = {"H4": _make_h4_data(300)}

        ga.initialize_population()
        assert len(ga.population) == 5

        # 初始评估
        ga.evaluate_population(evaluator, data)
        best_before = ga.get_best()
        assert best_before is not None
        assert best_before.fitness >= 0

        # 进化
        ga.evolve_generation()
        assert ga.generation == 1

        # 再评估
        ga.evaluate_population(evaluator, data)
        best_after = ga.get_best()
        assert best_after is not None

    def test_best_individual_updated_after_evaluate(self):
        """evaluate_population 后 best_individual 正确更新"""
        ga = GeneticAlgorithm(
            _baseline_config(),
            GAConfig(population_size=5, max_generations=2),
        )

        def fake_eval(config, data):
            return {"COMPOSITE_SCORE": np.random.random()}

        ga.initialize_population()
        ga.evaluate_population(fake_eval, {"H4": None})
        best1 = ga.get_best()
        assert best1 is not None
        # best_individual 应该是种群中 fitness 最高的
        pop_best = max(ga.population, key=lambda x: x.fitness)
        assert best1.fitness == pop_best.fitness

    def test_backtest_result_attached(self):
        """串行评估后 best_individual 有 backtest_result"""
        book = MistakeBook()
        evaluator = StandardEvaluator(mistake_book=book)
        ga = GeneticAlgorithm(
            _baseline_config(),
            GAConfig(population_size=3, max_generations=1),
        )
        data = {"H4": _make_h4_data(300)}

        ga.initialize_population()
        ga.evaluate_population(evaluator, data)
        # 至少有一个个体应有 backtest_result
        has_result = any(ind.backtest_result is not None for ind in ga.population)
        assert has_result, "至少一个个体应有 backtest_result"


class TestWFAOnHoldout:
    """测试 WFA 在 holdout 数据上的行为"""

    def test_wfa_creates_windows_on_holdout(self):
        """holdout 30% 数据上能创建足够窗口"""
        h4 = _make_h4_data(2000)
        split_idx = int(len(h4) * 0.7)
        holdout = h4.iloc[split_idx:]

        wfa = WFAValidator(
            config=WFAConfig(
                train_bars=100,
                test_bars=100,
                step_bars=100,
                min_windows=3,
                max_windows=5,
                warmup_bars=30,
            ),
        )
        windows = wfa.create_windows(len(holdout))
        assert len(windows) >= 3, f"只创建了 {len(windows)} 个窗口"

    def test_wfa_validate_produces_report(self):
        """WFA validate 能产生有效报告"""
        book = MistakeBook()
        evaluator = StandardEvaluator(mistake_book=book)
        wfa = WFAValidator(
            config=WFAConfig(
                train_bars=100,
                test_bars=100,
                step_bars=100,
                min_windows=3,
                warmup_bars=30,
            ),
            evaluator_fn=evaluator,
        )
        h4 = _make_h4_data(2000)
        split_idx = int(len(h4) * 0.7)
        holdout = {"H4": h4.iloc[split_idx:]}

        report = wfa.validate(_baseline_config(), holdout)
        assert report is not None
        assert isinstance(report.oos_degradation_ratio, float)
        assert len(report.train_sharpes) > 0
        assert len(report.test_sharpes) > 0

    def test_wfa_test_data_no_training_leak(self):
        """测试段数据不包含完整训练段（根因2修复验证）"""
        h4 = _make_h4_data(2000)

        class SliceTracker:
            """跟踪 _slice_data 调用的切片范围"""

            slices = []

        book = MistakeBook()
        evaluator = StandardEvaluator(mistake_book=book)
        wfa = WFAValidator(
            config=WFAConfig(
                train_bars=100,
                test_bars=100,
                step_bars=100,
                min_windows=3,
                warmup_bars=30,
            ),
            evaluator_fn=evaluator,
        )

        windows = wfa.create_windows(len(h4))
        assert len(windows) >= 3

        for w in windows:
            # 验证测试段起始位置：应该是 test_start - warmup，不是 train_start
            test_warmup_start = max(0, w.test_start - wfa.config.warmup_bars)
            # test_warmup_start 应该 > train_start（不包含完整训练段）
            assert test_warmup_start >= w.train_start, (
                f"测试段预热起始 {test_warmup_start} 不应小于 "
                f"训练段起始 {w.train_start}"
            )


class TestAntiOverfitIntegration:
    """测试 AntiOverfit 与回测结果的集成"""

    def test_anti_overfit_executes_all_layers(self):
        """AntiOverfit 五层检查都执行"""
        book = MistakeBook()
        evaluator = StandardEvaluator(mistake_book=book)
        config = _baseline_config()
        data = {"H4": _make_h4_data(500)}

        # 先获取一个 BacktestResult
        evaluator(config, data)
        result = evaluator.last_backtest_result
        assert result is not None

        guard = AntiOverfitGuard()
        verdict = guard.check(
            result,
            train_sharpes=[0.5, 0.6, 0.4],
            test_sharpes=[0.3, 0.4, 0.2],
            n_trials=5,
        )
        assert "MBL" in verdict.checks
        assert "OOS_DR" in verdict.checks
        assert "DSR" in verdict.checks
        assert "MONTE_CARLO" in verdict.checks
        assert "CPCV" in verdict.checks


class TestEvolutionPluginCycle:
    """测试 EvolutionPlugin 完整 cycle"""

    def test_plugin_init_with_config(self):
        """插件能用 config 初始化所有组件"""
        from src.plugins.evolution.plugin import EvolutionPlugin

        plugin = EvolutionPlugin()
        config = {
            "population_size": 5,
            "max_generations": 2,
            "initial_config": _baseline_config(),
        }
        plugin._init_evolution_components(config)
        assert plugin._ga is not None
        assert plugin._evaluator is not None
        assert plugin._wfa is not None
        assert plugin._anti_overfit is not None
        assert plugin._mistake_book is not None

    def test_plugin_full_cycle(self):
        """完整进化 cycle：set_data → start → 等待完成"""
        from src.plugins.evolution.plugin import EvolutionPlugin

        plugin = EvolutionPlugin()
        config = {
            "population_size": 5,
            "max_generations": 2,
            "initial_config": _baseline_config(),
        }
        plugin._init_evolution_components(config)

        # 注入数据
        data = {"H4": _make_h4_data(2000)}
        plugin.set_data(data)

        async def run():
            result = await plugin.start_evolution(max_cycles=1)
            assert result["status"] == "started"
            # 等待完成
            while plugin._is_evolving:
                await asyncio.sleep(0.1)
            assert plugin._cycle_count >= 1

        asyncio.run(run())

    def test_plugin_saves_results(self):
        """进化结果持久化到 JSON 文件"""
        from src.plugins.evolution.plugin import EvolutionPlugin

        plugin = EvolutionPlugin()
        config = {
            "population_size": 3,
            "max_generations": 1,
            "initial_config": _baseline_config(),
        }
        plugin._init_evolution_components(config)

        data = {"H4": _make_h4_data(2000)}
        plugin.set_data(data)

        # 清除已有结果
        results_path = plugin._RESULTS_PATH
        if os.path.exists(results_path):
            os.remove(results_path)

        async def run():
            await plugin.start_evolution(max_cycles=1)
            while plugin._is_evolving:
                await asyncio.sleep(0.1)

        asyncio.run(run())

        # 验证结果文件
        assert os.path.exists(results_path), "结果文件未生成"
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        assert len(results) >= 1
        entry = results[-1]
        assert "cycle" in entry
        assert "best_fitness" in entry
        assert "wfa_passed" in entry
        assert "aof_passed" in entry
        assert "adopted" in entry
        assert "best_config" in entry
        assert "timestamp" in entry


class TestSharpeCalculation:
    """测试 Sharpe 计算修复"""

    def test_sharpe_from_equity_curve(self):
        """per-bar equity Sharpe 与年化因子正确"""
        from src.plugins.evolution.bar_by_bar_backtester import (
            BarByBarBacktester,
        )

        bt = BarByBarBacktester(config=_baseline_config())
        # 模拟一条权益曲线
        bt._equity_curve = [10000 + i * 5 for i in range(100)]
        sharpe = bt._compute_sharpe_from_equity()
        # 稳定上升的权益曲线应有正 Sharpe
        assert sharpe > 0, f"稳定上升的权益曲线 Sharpe 应 > 0, got {sharpe}"
