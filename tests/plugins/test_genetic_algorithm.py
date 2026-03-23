"""GA 单元测试"""

import copy

import pytest

from src.plugins.evolution.genetic_algorithm import GAConfig, GeneticAlgorithm


@pytest.fixture
def baseline_config():
    return {
        "period_weight_filter": {
            "weights": {"D1": 0.25, "H4": 0.30, "H1": 0.25, "M15": 0.12, "M5": 0.08},
        },
        "threshold_parameters": {
            "confidence_threshold": 0.30,
            "volume_threshold": 1.0,
        },
        "signal_control": {
            "cooldown_bars": 8,
        },
    }


@pytest.fixture
def ga(baseline_config):
    cfg = GAConfig(
        population_size=10,
        max_generations=3,
        elite_count=2,
        tournament_size=3,
        mutation_rate=0.9,  # 测试中使用高变异率确保确定性
    )
    return GeneticAlgorithm(baseline_config, cfg)


class TestGAInitialization:
    def test_init_population_size(self, ga):
        pop = ga.initialize_population()
        assert len(pop) == ga.config.population_size

    def test_baseline_in_population(self, ga, baseline_config):
        ga.initialize_population()
        hashes = {ind.config_hash for ind in ga.population}
        baseline_hash = ga._hash_config(baseline_config)
        assert baseline_hash in hashes

    def test_population_diversity(self, ga):
        ga.initialize_population()
        hashes = {ind.config_hash for ind in ga.population}
        assert len(hashes) == len(ga.population), "All individuals should be unique"


class TestGAOperators:
    def test_tournament_select(self, ga):
        ga.initialize_population()
        # Give different fitness
        for i, ind in enumerate(ga.population):
            ind.fitness = float(i)
        winner = ga.tournament_select()
        assert winner is not None
        assert winner.fitness >= 0

    def test_crossover_produces_valid_config(self, ga):
        ga.initialize_population()
        a = ga.population[0]
        b = ga.population[1]
        child = ga.crossover(a, b)
        assert "period_weight_filter" in child
        assert "threshold_parameters" in child

    def test_mutate_changes_config(self, ga, baseline_config):
        original = copy.deepcopy(baseline_config)
        mutated = ga.mutate(baseline_config)
        # At least something should differ (with high mutation rate)
        assert mutated != original or ga.config.mutation_rate < 0.01

    def test_normalize_weights_sum_to_one(self, ga, baseline_config):
        config = copy.deepcopy(baseline_config)
        config["period_weight_filter"]["weights"]["D1"] = 0.5
        config["period_weight_filter"]["weights"]["H4"] = 0.5
        ga._normalize_weights(config)
        total = sum(config["period_weight_filter"]["weights"].values())
        assert abs(total - 1.0) < 1e-6


class TestGAEvolution:
    def test_evolve_generation(self, ga):
        ga.initialize_population()
        for ind in ga.population:
            ind.fitness = float(hash(ind.config_hash) % 100) / 100.0
        new_pop = ga.evolve_generation()
        assert len(new_pop) > 0
        assert ga.generation == 1

    def test_evaluate_population(self, ga):
        ga.initialize_population()

        def dummy_evaluator(config, data):
            return {"COMPOSITE_SCORE": 0.5}

        ga.evaluate_population(dummy_evaluator, {"H4": None})
        for ind in ga.population:
            assert ind.fitness == 0.5

    def test_run_convergence(self, ga):
        def dummy_evaluator(config, data):
            # Always return same score -> should converge
            return {"COMPOSITE_SCORE": 0.42}

        best = ga.run(dummy_evaluator, {"H4": None})
        assert best is not None
        assert best.fitness == pytest.approx(0.42)

    def test_hash_deterministic(self, ga, baseline_config):
        h1 = ga._hash_config(baseline_config)
        h2 = ga._hash_config(baseline_config)
        assert h1 == h2

    def test_get_population_stats(self, ga):
        ga.initialize_population()
        for i, ind in enumerate(ga.population):
            ind.fitness = i * 0.1
        stats = ga.get_population_stats()
        assert stats["size"] == len(ga.population)
        assert stats["best_fitness"] == pytest.approx(0.9)
