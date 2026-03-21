"""真正的遗传算法 — 替代旧 WeightVariator 的随机变异

组件：
1. GAConfig — 算法超参数
2. GeneticAlgorithm — 初始化/锦标赛选择/交叉/定向变异/精英保留
3. 评估回调 — evaluator_fn(config, data) -> Dict[str, float]

设计原则：
- 种群多样性 > 贪心收敛（用 config_hash 去重）
- 定向变异 > 随机变异（基于 MistakeBook 错误模式）
- 精英保留确保不退化
- 逻辑基因（VSA核心公式）禁止变异
"""

import copy
import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from src.kernel.types import GAIndividual

logger = logging.getLogger(__name__)


# ================================================================
# GAConfig — 遗传算法超参数
# ================================================================


@dataclass
class GAConfig:
    """遗传算法配置

    Attributes:
        population_size: 种群大小
        elite_count: 精英保留数
        tournament_size: 锦标赛选择的参赛者数
        crossover_rate: 交叉率
        mutation_rate: 变异率
        mutation_strength: 变异强度（相对偏移的最大幅度）
        max_generations: 最大代数
        fitness_key: 适应度指标键名
        convergence_threshold: 收敛阈值（连续N代最佳不变则终止）
        convergence_patience: 收敛耐心代数
        diversity_penalty: 多样性惩罚系数
    """

    population_size: int = 20
    elite_count: int = 2
    tournament_size: int = 3
    crossover_rate: float = 0.7
    mutation_rate: float = 0.9
    mutation_strength: float = 0.15
    max_generations: int = 50
    fitness_key: str = "COMPOSITE_SCORE"
    convergence_threshold: float = 0.001
    convergence_patience: int = 5
    diversity_penalty: float = 0.05

    # 禁止变异的键路径（VSA 核心公式等）
    frozen_keys: List[str] = field(
        default_factory=lambda: [
            "state_machine.transition_confidence",
        ]
    )


# ================================================================
# GeneticAlgorithm — 主类
# ================================================================


class GeneticAlgorithm:
    """真正的遗传算法

    使用方式：
        ga = GeneticAlgorithm(baseline_config, ga_config)
        best = ga.run(evaluator_fn, data_dict)
    """

    def __init__(
        self,
        baseline_config: Dict[str, Any],
        config: Optional[GAConfig] = None,
    ) -> None:
        self.baseline = copy.deepcopy(baseline_config)
        self.config = config or GAConfig()
        self.population: List[GAIndividual] = []
        self.generation = 0
        self.best_individual: Optional[GAIndividual] = None
        self.history: List[Dict[str, Any]] = []
        self._rng = random.Random()

    def initialize_population(self) -> List[GAIndividual]:
        """初始化种群 — baseline + 随机变异体

        Returns:
            初始种群
        """
        self.population = []
        seen_hashes: set = set()

        # 第1个个体 = baseline
        baseline_hash = self._hash_config(self.baseline)
        self.population.append(
            GAIndividual(
                config=copy.deepcopy(self.baseline),
                fitness=0.0,
                generation=0,
                config_hash=baseline_hash,
            )
        )
        seen_hashes.add(baseline_hash)

        # 其余个体 = 随机变异
        attempts = 0
        while len(self.population) < self.config.population_size and attempts < 200:
            mutant = self._random_mutant(self.baseline)
            h = self._hash_config(mutant)
            if h not in seen_hashes:
                self.population.append(
                    GAIndividual(
                        config=mutant,
                        fitness=0.0,
                        generation=0,
                        config_hash=h,
                    )
                )
                seen_hashes.add(h)
            attempts += 1

        logger.info("GA初始种群: %d 个体", len(self.population))
        return self.population

    # ================================================================
    # 选择算子
    # ================================================================

    def tournament_select(self) -> GAIndividual:
        """锦标赛选择 — 从种群中随机抽 k 个，选最优

        Returns:
            被选中的个体（深拷贝）
        """
        candidates = self._rng.sample(
            self.population,
            min(self.config.tournament_size, len(self.population)),
        )
        winner = max(candidates, key=lambda ind: ind.fitness)
        return GAIndividual(
            config=copy.deepcopy(winner.config),
            fitness=winner.fitness,
            generation=winner.generation,
            config_hash=winner.config_hash,
        )

    # ================================================================
    # 交叉算子
    # ================================================================

    def crossover(
        self, parent_a: GAIndividual, parent_b: GAIndividual
    ) -> Dict[str, Any]:
        """均匀交叉 — 每个顶层键随机选择来源

        Args:
            parent_a: 父方A
            parent_b: 父方B

        Returns:
            子代配置
        """
        child: Dict[str, Any] = {}
        all_keys = set(parent_a.config.keys()) | set(parent_b.config.keys())

        for key in all_keys:
            a_val = parent_a.config.get(key)
            b_val = parent_b.config.get(key)

            if a_val is None:
                child[key] = copy.deepcopy(b_val)
            elif b_val is None:
                child[key] = copy.deepcopy(a_val)
            elif isinstance(a_val, dict) and isinstance(b_val, dict):
                # 嵌套字典：递归交叉
                child[key] = self._crossover_dict(a_val, b_val)
            else:
                # 标量：随机选择
                child[key] = copy.deepcopy(a_val if self._rng.random() < 0.5 else b_val)

        return child

    def _crossover_dict(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        """嵌套字典的均匀交叉"""
        result: Dict[str, Any] = {}
        all_keys = set(a.keys()) | set(b.keys())

        for key in all_keys:
            a_val = a.get(key)
            b_val = b.get(key)

            if a_val is None:
                result[key] = copy.deepcopy(b_val)
            elif b_val is None:
                result[key] = copy.deepcopy(a_val)
            elif isinstance(a_val, dict) and isinstance(b_val, dict):
                result[key] = self._crossover_dict(a_val, b_val)
            else:
                result[key] = copy.deepcopy(
                    a_val if self._rng.random() < 0.5 else b_val
                )

        return result

    # ================================================================
    # 变异算子
    # ================================================================

    def mutate(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """定向变异 — 对数值参数施加高斯扰动

        Args:
            config: 待变异配置

        Returns:
            变异后的配置
        """
        mutated = copy.deepcopy(config)
        self._mutate_dict(mutated, prefix="")
        return mutated

    def _mutate_dict(self, d: Dict[str, Any], prefix: str) -> None:
        """递归变异字典中的数值"""
        for key, val in d.items():
            full_key = f"{prefix}.{key}" if prefix else key

            # 检查是否冻结
            if full_key in self.config.frozen_keys:
                continue

            if isinstance(val, dict):
                self._mutate_dict(val, full_key)
            elif isinstance(val, float):
                if self._rng.random() < self.config.mutation_rate:
                    # 高斯扰动
                    noise = self._rng.gauss(0, self.config.mutation_strength)
                    d[key] = val * (1.0 + noise)
                    # 权重类参数夹紧到 [0, 1]
                    if "weight" in key.lower() or key in (
                        "D1",
                        "H4",
                        "H1",
                        "M15",
                        "M5",
                    ):
                        d[key] = max(0.01, min(1.0, d[key]))
                    # 阈值类参数夹紧到 [0, 1]
                    elif "threshold" in key.lower():
                        d[key] = max(0.01, min(0.99, d[key]))
            elif isinstance(val, int):
                if self._rng.random() < self.config.mutation_rate:
                    delta = max(1, int(abs(val * self.config.mutation_strength)))
                    d[key] = val + self._rng.randint(-delta, delta)
                    d[key] = max(1, d[key])  # 整数参数至少为1

    def _normalize_weights(self, config: Dict[str, Any]) -> None:
        """归一化权重字典使其和为1"""
        pw = config.get("period_weight_filter", {})
        weights = pw.get("weights", {})
        if weights:
            total = sum(weights.values())
            if total > 0:
                for k in weights:
                    weights[k] = weights[k] / total

        # regime_weights 同样归一化
        rw = pw.get("regime_weights", {})
        for regime_key, rw_dict in rw.items():
            if isinstance(rw_dict, dict):
                total = sum(v for v in rw_dict.values() if isinstance(v, (int, float)))
                if total > 0:
                    for k in rw_dict:
                        if isinstance(rw_dict[k], (int, float)):
                            rw_dict[k] = rw_dict[k] / total

    # ================================================================
    # 世代演进
    # ================================================================

    def evaluate_population(
        self,
        evaluator_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, float]],
        data_dict: Dict[str, Any],
    ) -> None:
        """评估种群中所有个体的适应度

        Args:
            evaluator_fn: 评估函数 (config, data) -> metrics
            data_dict: 多TF数据
        """
        for ind in self.population:
            try:
                metrics = evaluator_fn(ind.config, data_dict)
                ind.fitness = metrics.get(self.config.fitness_key, 0.0)
            except Exception as e:
                logger.warning("评估个体失败: %s", e)
                ind.fitness = 0.0

    def evolve_generation(self) -> List[GAIndividual]:
        """执行一代进化：选择 + 交叉 + 变异 + 精英保留

        Returns:
            新一代种群
        """
        self.generation += 1
        pop_size = self.config.population_size

        # 1. 精英保留
        sorted_pop = sorted(self.population, key=lambda x: x.fitness, reverse=True)
        elites = sorted_pop[: self.config.elite_count]
        new_population = [
            GAIndividual(
                config=copy.deepcopy(e.config),
                fitness=e.fitness,
                generation=self.generation,
                config_hash=e.config_hash,
            )
            for e in elites
        ]

        # 2. 生成子代
        seen_hashes = {ind.config_hash for ind in new_population}
        attempts = 0

        while len(new_population) < pop_size and attempts < pop_size * 3:
            attempts += 1

            # 选择父代
            parent_a = self.tournament_select()
            parent_b = self.tournament_select()

            # 交叉
            if self._rng.random() < self.config.crossover_rate:
                child_config = self.crossover(parent_a, parent_b)
            else:
                child_config = copy.deepcopy(parent_a.config)

            # 变异
            child_config = self.mutate(child_config)

            # 归一化权重
            self._normalize_weights(child_config)

            # 去重
            h = self._hash_config(child_config)
            if h in seen_hashes:
                continue

            new_population.append(
                GAIndividual(
                    config=child_config,
                    fitness=0.0,
                    generation=self.generation,
                    config_hash=h,
                )
            )
            seen_hashes.add(h)

        self.population = new_population

        # 更新最佳个体
        best = max(self.population, key=lambda x: x.fitness)
        if self.best_individual is None or best.fitness > self.best_individual.fitness:
            self.best_individual = GAIndividual(
                config=copy.deepcopy(best.config),
                fitness=best.fitness,
                generation=best.generation,
                config_hash=best.config_hash,
            )

        return self.population

    def run(
        self,
        evaluator_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, float]],
        data_dict: Dict[str, Any],
    ) -> GAIndividual:
        """运行完整遗传算法

        Args:
            evaluator_fn: 评估函数
            data_dict: 多TF数据

        Returns:
            最佳个体
        """
        # 初始化
        self.initialize_population()
        self.evaluate_population(evaluator_fn, data_dict)

        best_fitness = -float("inf")
        stagnation = 0

        for gen in range(self.config.max_generations):
            # 进化
            self.evolve_generation()
            self.evaluate_population(evaluator_fn, data_dict)

            # 记录
            current_best = max(self.population, key=lambda x: x.fitness)
            gen_info = {
                "generation": self.generation,
                "best_fitness": current_best.fitness,
                "avg_fitness": float(np.mean([p.fitness for p in self.population])),
                "population_size": len(self.population),
            }
            self.history.append(gen_info)

            logger.info(
                "GA Gen %d/%d: best=%.4f avg=%.4f",
                self.generation,
                self.config.max_generations,
                current_best.fitness,
                gen_info["avg_fitness"],
            )

            # 收敛检查
            if current_best.fitness > best_fitness + self.config.convergence_threshold:
                best_fitness = current_best.fitness
                stagnation = 0
            else:
                stagnation += 1

            if stagnation >= self.config.convergence_patience:
                logger.info("GA收敛: %d代未改善", stagnation)
                break

        if self.best_individual is None:
            # 不应该发生，但保险起见
            self.best_individual = max(self.population, key=lambda x: x.fitness)

        return self.best_individual

    # ================================================================
    # 辅助方法
    # ================================================================

    def _random_mutant(self, base: Dict[str, Any]) -> Dict[str, Any]:
        """从基准配置生成一个随机变异体"""
        mutant = copy.deepcopy(base)
        # 使用更大的变异强度来增加初始多样性
        old_strength = self.config.mutation_strength
        self.config.mutation_strength = old_strength * 2.0
        self._mutate_dict(mutant, prefix="")
        self.config.mutation_strength = old_strength
        self._normalize_weights(mutant)
        return mutant

    @staticmethod
    def _hash_config(config: Dict[str, Any]) -> str:
        """配置哈希指纹"""

        def _extract(obj: Any) -> str:
            if isinstance(obj, dict):
                items = sorted((k, _extract(v)) for k, v in obj.items())
                return str(items)
            if isinstance(obj, (list, tuple)):
                return str([_extract(v) for v in obj])
            if isinstance(obj, float):
                return f"{obj:.6f}"
            return str(obj)

        canonical = _extract(config)
        return hashlib.md5(canonical.encode()).hexdigest()[:12]

    def get_best(self) -> Optional[GAIndividual]:
        """获取当前最佳个体"""
        return self.best_individual

    def get_population_stats(self) -> Dict[str, Any]:
        """获取种群统计信息"""
        if not self.population:
            return {"size": 0}

        fitnesses = [ind.fitness for ind in self.population]
        return {
            "size": len(self.population),
            "generation": self.generation,
            "best_fitness": max(fitnesses),
            "avg_fitness": float(np.mean(fitnesses)),
            "std_fitness": float(np.std(fitnesses)),
            "worst_fitness": min(fitnesses),
        }
