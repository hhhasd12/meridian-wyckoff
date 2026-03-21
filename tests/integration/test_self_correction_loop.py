"""自我纠错闭环测试 — MistakeBook → GA → WFA → 配置更新

验证自我纠错链路的各组件可独立运行并衔接。
"""

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.ohlcv_generator import make_ohlcv


class TestMistakeBookRealData:
    """MistakeBook 错题本真实数据测试"""

    def test_mistake_book_instantiation(self) -> None:
        """MistakeBook 可实例化"""
        from src.plugins.self_correction.mistake_book import MistakeBook

        book = MistakeBook()
        assert book is not None

    def test_mistake_book_record(self) -> None:
        """记录错误"""
        from src.plugins.self_correction.mistake_book import (
            MistakeBook,
            MistakeType,
            ErrorSeverity,
        )

        book = MistakeBook()
        book.record_mistake(
            mistake_type=MistakeType.STATE_MISJUDGMENT,
            severity=ErrorSeverity.MEDIUM,
            context={
                "symbol": "BTC/USDT",
                "state": "SOS",
                "signal": "buy",
            },
            module_name="orchestrator",
        )

        assert len(book.record_history) >= 1

    def test_mistake_book_pattern_analysis(self) -> None:
        """错题本模式分析"""
        from src.plugins.self_correction.mistake_book import (
            MistakeBook,
            MistakeType,
            ErrorSeverity,
        )

        book = MistakeBook()
        for i in range(5):
            book.record_mistake(
                mistake_type=MistakeType.STATE_MISJUDGMENT,
                severity=ErrorSeverity.MEDIUM,
                context={"symbol": "ETH/USDT", "state": "ST"},
                module_name="orchestrator",
            )

        patterns = book.analyze_patterns()
        assert patterns is not None
        assert isinstance(patterns, dict)


class TestGeneticAlgorithmIntegration:
    """遗传算法集成测试"""

    def test_ga_initialization(self) -> None:
        """GA 可初始化"""
        from src.plugins.evolution.genetic_algorithm import GeneticAlgorithm

        baseline = {
            "weight_system": {
                "volatility": 0.15,
                "momentum": 0.20,
                "volume": 0.15,
                "pattern": 0.25,
                "fvg": 0.10,
                "pin_body": 0.15,
            }
        }
        ga = GeneticAlgorithm(baseline_config=baseline)
        assert ga is not None

    def test_ga_initialize_population(self) -> None:
        """GA 初始化种群"""
        from src.plugins.evolution.genetic_algorithm import GeneticAlgorithm

        baseline = {
            "weight_system": {
                "volatility": 0.15,
                "momentum": 0.20,
                "volume": 0.15,
                "pattern": 0.25,
                "fvg": 0.10,
                "pin_body": 0.15,
            }
        }
        ga = GeneticAlgorithm(baseline_config=baseline)
        population = ga.initialize_population()

        assert len(population) > 0
        for ind in population:
            assert ind.config is not None

    def test_ga_evolve_generation(self) -> None:
        """运行一代进化"""
        from src.plugins.evolution.genetic_algorithm import GeneticAlgorithm

        baseline = {
            "weight_system": {
                "volatility": 0.15,
                "momentum": 0.20,
                "volume": 0.15,
                "pattern": 0.25,
                "fvg": 0.10,
                "pin_body": 0.15,
            }
        }
        ga = GeneticAlgorithm(baseline_config=baseline)
        ga.initialize_population()

        rng = np.random.RandomState(42)
        for ind in ga.population:
            ind.fitness = rng.random()

        new_pop = ga.evolve_generation()
        assert len(new_pop) > 0


class TestWFAValidatorIntegration:
    """WFA 验证器集成测试"""

    def test_wfa_instantiation(self) -> None:
        """WFAValidator 可实例化"""
        from src.plugins.evolution.wfa_validator import WFAValidator

        validator = WFAValidator()
        assert validator is not None

    def test_wfa_creates_windows(self) -> None:
        """WFA 创建训练/验证窗口"""
        from src.plugins.evolution.wfa_validator import WFAValidator

        validator = WFAValidator()
        df = make_ohlcv(n=500, trend="flat")
        windows = validator.create_windows(n_bars=500)

        assert windows is not None
        assert isinstance(windows, list)


class TestAntiOverfitIntegration:
    """过拟合防护集成测试"""

    def test_guard_instantiation(self) -> None:
        """AntiOverfitGuard 可实例化"""
        from src.plugins.evolution.anti_overfit import AntiOverfitGuard

        guard = AntiOverfitGuard()
        assert guard is not None
