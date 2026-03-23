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


def _evaluate_single(
    config: Dict[str, Any],
    data_dict: Dict[str, Any],
    fitness_key: str,
) -> float:
    """在子进程中评估单个个体（模块级函数，可 pickle）"""
    import os
    import warnings

    # 限制每个子进程的线程数，避免 6 个进程各开 12 线程互相争抢
    os.environ.setdefault("NUMEXPR_MAX_THREADS", "2")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")

    warnings.filterwarnings("ignore")
    from src.plugins.evolution.evaluator import StandardEvaluator
    from src.plugins.self_correction.mistake_book import MistakeBook

    try:
        evaluator = StandardEvaluator(mistake_book=MistakeBook())
        metrics = evaluator(config, data_dict)
        return metrics.get(fitness_key, 0.0)
    except Exception as e:
        logger.debug("适应度评估失败: %s", e)
        return 0.0


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

    population_size: int = 50
    elite_count: int = 5
    tournament_size: int = 3
    crossover_rate: float = 0.7
    mutation_rate: float = 0.25
    mutation_strength: float = 0.10
    max_generations: int = 50
    fitness_key: str = "COMPOSITE_SCORE"
    convergence_threshold: float = 0.001
    convergence_patience: int = 15
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
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """评估种群中所有个体的适应度（支持多进程并行）

        Args:
            evaluator_fn: 评估函数 (config, data) -> metrics
            data_dict: 多时间周期数据字典
            progress_callback: 进度回调，每完成一个个体调用一次
                               参数: {"completed": int, "total": int, "generation": int,
                                      "elapsed": float, "eta": float, "workers": int}
            data_dict: 多TF数据
        """
        import os
        import pickle
        import sys
        import time
        from concurrent.futures import ProcessPoolExecutor, as_completed

        total = len(self.population)
        t0 = time.time()

        # 多进程并行评估
        # pickle 序列化 DataFrame 的开销（~1s）远小于单个体回测时间（~80-350s），
        # 因此即使数据量大也值得并行。
        # Worker 数限制为 4，留出 CPU 余量给系统和其他程序。
        use_parallel = True

        try:
            max_workers = min(6, total)  # 6核并行，12490F留6线程给系统
            max_workers = max(max_workers, 1)
            if max_workers >= 2 and use_parallel:
                # 先测试 evaluator_fn 是否可 pickle（lambda/闭包不行）
                pickle.dumps(evaluator_fn)
                self._evaluate_parallel(
                    evaluator_fn, data_dict, max_workers, t0, total, progress_callback
                )
                return
        except (TypeError, pickle.PicklingError, AttributeError):
            # evaluator_fn 不可序列化（如测试中的 lambda），回退串行
            pass
        except Exception as e:
            logger.info("多进程评估失败，回退到串行: %s", e)

        # 串行回退
        self._evaluate_serial(evaluator_fn, data_dict, t0, total, progress_callback)

    def _evaluate_serial(
        self,
        evaluator_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, float]],
        data_dict: Dict[str, Any],
        t0: float,
        total: int,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """串行评估（回退方案）"""
        import sys
        import time

        for idx, ind in enumerate(self.population):
            try:
                metrics = evaluator_fn(ind.config, data_dict)
                ind.fitness = metrics.get(self.config.fitness_key, 0.0)
                # 根因7修复：存储 BacktestResult 供 AntiOverfit 使用
                if hasattr(evaluator_fn, "last_backtest_result"):
                    ind.backtest_result = evaluator_fn.last_backtest_result  # type: ignore[union-attr]
            except Exception as e:
                logger.warning("评估个体失败: %s", e)
                ind.fitness = 0.0

            elapsed = time.time() - t0
            avg_per = elapsed / (idx + 1)
            eta = avg_per * (total - idx - 1)
            filled = int(25 * (idx + 1) / total)
            bar = "█" * filled + "░" * (25 - filled)
            sys.stderr.write(
                f"\r  Gen{self.generation} [{bar}] {idx + 1}/{total} "
                f"fitness={ind.fitness:.4f} "
                f"({elapsed:.0f}s, ~{eta:.0f}s left)  "
            )
            sys.stderr.flush()

            # 进度回调（供前端实时显示）
            if progress_callback is not None:
                try:
                    progress_callback(
                        {
                            "completed": idx + 1,
                            "total": total,
                            "generation": self.generation,
                            "elapsed": round(elapsed, 1),
                            "eta": round(eta, 1),
                            "workers": 1,
                            "best_fitness": self.best_individual.fitness
                            if self.best_individual
                            else 0.0,
                        }
                    )
                except Exception:
                    pass
        sys.stderr.write("\n")
        sys.stderr.flush()

        # 更新 best_individual（评估后种群 fitness 已更新）
        self._update_best_individual()

    def _evaluate_parallel(
        self,
        evaluator_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, float]],
        data_dict: Dict[str, Any],
        max_workers: int,
        t0: float,
        total: int,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """多进程并行评估"""
        import sys
        import time
        from concurrent.futures import ProcessPoolExecutor, as_completed

        configs = [ind.config for ind in self.population]
        fitness_key = self.config.fitness_key

        completed = 0
        results: Dict[int, float] = {}

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_evaluate_single, cfg, data_dict, fitness_key): i
                for i, cfg in enumerate(configs)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result(timeout=600)
                except Exception as e:
                    logger.warning("并行评估个体 %d 失败: %s", idx, e)
                    results[idx] = 0.0

                completed += 1
                elapsed = time.time() - t0
                avg_per = elapsed / completed
                eta = avg_per * (total - completed)
                filled = int(25 * completed / total)
                bar = "█" * filled + "░" * (25 - filled)
                sys.stderr.write(
                    f"\r  Gen{self.generation} [{bar}] {completed}/{total} "
                    f"[{max_workers}P] "
                    f"({elapsed:.0f}s, ~{eta:.0f}s left)  "
                )
                sys.stderr.flush()

                # 进度回调（供前端实时显示）
                if progress_callback is not None:
                    try:
                        progress_callback(
                            {
                                "completed": completed,
                                "total": total,
                                "generation": self.generation,
                                "elapsed": round(elapsed, 1),
                                "eta": round(eta, 1),
                                "workers": max_workers,
                            }
                        )
                    except Exception:
                        pass

        # 写回结果
        for i, ind in enumerate(self.population):
            ind.fitness = results.get(i, 0.0)

        # 根因7修复：并行评估后，对最佳个体再做一次串行评估以获取 backtest_result
        best_ind = max(self.population, key=lambda x: x.fitness)
        if hasattr(evaluator_fn, "last_backtest_result"):
            try:
                evaluator_fn(best_ind.config, data_dict)
                best_ind.backtest_result = evaluator_fn.last_backtest_result  # type: ignore[union-attr]
            except Exception:
                pass

        # 更新 best_individual（评估后种群 fitness 已更新）
        self._update_best_individual()

        sys.stderr.write("\n")
        sys.stderr.flush()

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
        self._update_best_individual()

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

    def _update_best_individual(self) -> None:
        """更新全局最佳个体（在 evaluate_population 和 evolve_generation 后调用）"""
        if not self.population:
            return
        current_best = max(self.population, key=lambda x: x.fitness)
        if (
            self.best_individual is None
            or current_best.fitness > self.best_individual.fitness
        ):
            self.best_individual = GAIndividual(
                config=copy.deepcopy(current_best.config),
                fitness=current_best.fitness,
                generation=current_best.generation,
                config_hash=current_best.config_hash,
                backtest_result=current_best.backtest_result,
            )

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

    # ================================================================
    # Checkpoint — 断点续传
    # ================================================================

    def to_checkpoint(self) -> Dict[str, Any]:
        """将 GA 运行时状态序列化为可 JSON 持久化的字典

        保存最小状态集：population、generation、best_individual、history。
        BacktestResult 省略（resume 后重新评估获取），节省存储。

        Returns:
            可直接 json.dump 的字典
        """

        def _serialize_individual(ind: GAIndividual) -> Dict[str, Any]:
            return {
                "config": ind.config,
                "fitness": ind.fitness,
                "generation": ind.generation,
                "config_hash": ind.config_hash,
                # backtest_result 故意不保存 — 太大且可重新评估
            }

        data: Dict[str, Any] = {
            "version": 1,
            "generation": self.generation,
            "baseline": self.baseline,
            "ga_config": {
                "population_size": self.config.population_size,
                "elite_count": self.config.elite_count,
                "tournament_size": self.config.tournament_size,
                "crossover_rate": self.config.crossover_rate,
                "mutation_rate": self.config.mutation_rate,
                "mutation_strength": self.config.mutation_strength,
                "max_generations": self.config.max_generations,
                "fitness_key": self.config.fitness_key,
                "convergence_threshold": self.config.convergence_threshold,
                "convergence_patience": self.config.convergence_patience,
                "diversity_penalty": self.config.diversity_penalty,
                "frozen_keys": self.config.frozen_keys,
            },
            "population": [_serialize_individual(ind) for ind in self.population],
            "best_individual": (
                _serialize_individual(self.best_individual)
                if self.best_individual
                else None
            ),
            "history": self.history,
        }
        return data

    @classmethod
    def from_checkpoint(cls, data: Dict[str, Any]) -> "GeneticAlgorithm":
        """从 checkpoint 字典恢复 GA 状态

        Args:
            data: to_checkpoint() 产出的字典

        Returns:
            恢复状态的 GeneticAlgorithm 实例
        """
        ga_cfg_data = data.get("ga_config", {})
        ga_config = GAConfig(
            population_size=ga_cfg_data.get("population_size", 50),
            elite_count=ga_cfg_data.get("elite_count", 5),
            tournament_size=ga_cfg_data.get("tournament_size", 3),
            crossover_rate=ga_cfg_data.get("crossover_rate", 0.7),
            mutation_rate=ga_cfg_data.get("mutation_rate", 0.25),
            mutation_strength=ga_cfg_data.get("mutation_strength", 0.10),
            max_generations=ga_cfg_data.get("max_generations", 50),
            fitness_key=ga_cfg_data.get("fitness_key", "COMPOSITE_SCORE"),
            convergence_threshold=ga_cfg_data.get("convergence_threshold", 0.001),
            convergence_patience=ga_cfg_data.get("convergence_patience", 15),
            diversity_penalty=ga_cfg_data.get("diversity_penalty", 0.05),
            frozen_keys=ga_cfg_data.get("frozen_keys", []),
        )

        ga = cls(baseline_config=data["baseline"], config=ga_config)
        ga.generation = data["generation"]
        ga.history = data.get("history", [])

        # 恢复种群
        for ind_data in data.get("population", []):
            ga.population.append(
                GAIndividual(
                    config=ind_data["config"],
                    fitness=ind_data["fitness"],
                    generation=ind_data["generation"],
                    config_hash=ind_data["config_hash"],
                )
            )

        # 恢复全局最佳
        best_data = data.get("best_individual")
        if best_data:
            ga.best_individual = GAIndividual(
                config=best_data["config"],
                fitness=best_data["fitness"],
                generation=best_data["generation"],
                config_hash=best_data["config_hash"],
            )

        logger.info(
            "GA 从 checkpoint 恢复: generation=%d, population=%d, best_fitness=%.4f",
            ga.generation,
            len(ga.population),
            ga.best_individual.fitness if ga.best_individual else 0.0,
        )
        return ga
