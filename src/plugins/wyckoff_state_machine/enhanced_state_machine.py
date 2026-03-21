"""
威科夫状态机 - 增强版状态机

包含 EnhancedWyckoffStateMachine 类：
- 多时间框架处理
- 参数优化
- 信号生成
- 状态信息查询

从 wyckoff_state_machine_legacy.py 拆分而来。
"""

import logging
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.kernel.types import StateConfig, StateDirection, StateTransition, StateTransitionType
from src.plugins.wyckoff_state_machine.state_machine_core import WyckoffStateMachine

logger = logging.getLogger(__name__)

class EnhancedWyckoffStateMachine(WyckoffStateMachine):
    """
    增强威科夫状态机

    扩展功能：
    1. 更复杂的证据链管理
    2. 高级遗产传递机制
    3. 多时间框架状态同步
    4. 自动参数优化
    """

    def __init__(self, config: Optional[StateConfig] = None):
        super().__init__(config)

        # 增强的证据链管理
        self.evidence_chain: list[dict] = []
        self.evidence_weight_adjustments: dict[str, float] = {}

        # 多时间框架状态跟踪
        self.multi_timeframe_states: dict[str, dict] = {}  # timeframe -> state_info

        # 自动优化记录
        self.optimization_history: list[dict] = []
        self.config_updates: list[dict] = []

    def process_multi_timeframe(
        self, candles_dict: dict[str, pd.DataFrame], context_dict: dict[str, dict]
    ) -> dict[str, str]:
        """
        处理多时间框架数据

        Args:
            candles_dict: 时间框架 -> DataFrame
            context_dict: 时间框架 -> 上下文信息

        Returns:
            各时间框架状态字典
        """
        results = {}

        for timeframe, candles in candles_dict.items():
            if len(candles) == 0:
                continue

            # 取最新一根K线
            latest_candle = candles.iloc[-1]
            context = context_dict.get(timeframe, {})

            # 处理单根K线
            state = self.process_candle(latest_candle, context)
            results[timeframe] = state

            # 记录多时间框架状态
            self.multi_timeframe_states[timeframe] = {
                "state": state,
                "confidence": self.state_confidences.get(state, 0.0),
                "timestamp": datetime.now(),
                "candle_info": {
                    "open": latest_candle["open"],
                    "high": latest_candle["high"],
                    "low": latest_candle["low"],
                    "close": latest_candle["close"],
                    "volume": latest_candle["volume"],
                },
            }

        # 同步多时间框架状态
        self._sync_multi_timeframe_states()

        return results

    def _sync_multi_timeframe_states(self):
        """同步多时间框架状态"""
        if not self.multi_timeframe_states:
            return

        # 按时间框架权重聚合状态
        timeframe_weights = {
            "1d": 0.35,  # 日线权重最高
            "4h": 0.25,  # 4小时
            "1h": 0.20,  # 1小时
            "15m": 0.15,  # 15分钟
            "5m": 0.05,  # 5分钟
        }

        # 计算加权状态置信度
        state_scores = {}
        for timeframe, state_info in self.multi_timeframe_states.items():
            weight = timeframe_weights.get(timeframe, 0.1)
            state = state_info["state"]
            confidence = state_info["confidence"]

            if state not in state_scores:
                state_scores[state] = 0.0

            state_scores[state] += confidence * weight

        # 选择最佳状态
        if state_scores:
            best_state = max(state_scores.items(), key=lambda x: x[1])[0]

            # 检查是否需要更新主状态机状态
            if best_state != self.current_state and state_scores[best_state] > 0.5:
                # 创建多时间框架确认的转换
                transition = StateTransition(
                    from_state=self.current_state,
                    to_state=best_state,
                    timestamp=datetime.now(),
                    confidence=state_scores[best_state],
                    transition_type=StateTransitionType.PARALLEL,
                    evidences=[],
                    heritage_transfer=0.0,
                )

                self.transition_history.append(transition)
                self.current_state = best_state

    def optimize_parameters(
        self, historical_data: pd.DataFrame, optimization_criteria: dict[str, Any]
    ) -> dict[str, Any]:
        """
        自动优化状态机参数

        Args:
            historical_data: 历史数据用于回测
            optimization_criteria: 优化标准

        Returns:
            优化结果
        """
        logger.info("Starting parameter optimization...")

        # 获取当前配置作为基准
        current_config = self.config.to_dict()

        # 定义参数搜索空间
        param_grid = {
            "SPRING_FAILURE_BARS": [3, 5, 7, 10],
            "STATE_TIMEOUT_BARS": [15, 20, 25, 30],
            "STATE_MIN_CONFIDENCE": [0.5, 0.6, 0.7, 0.8],
            "PATH_SELECTION_THRESHOLD": [0.6, 0.65, 0.7, 0.75],
            "STATE_SWITCH_HYSTERESIS": [0.1, 0.15, 0.2, 0.25],
            "DIRECTION_SWITCH_PENALTY": [0.2, 0.3, 0.4, 0.5],
        }

        # 获取优化标准
        target_metric = optimization_criteria.get("target_metric", "win_rate")
        min_trades = optimization_criteria.get("min_trades", 10)
        max_iterations = optimization_criteria.get("max_iterations", 50)

        # 评估当前配置的性能
        baseline_performance = self._evaluate_config_performance(
            current_config, historical_data, target_metric, min_trades
        )

        logger.info(
            "Baseline performance (%s): %.4f", target_metric, baseline_performance
        )

        # 执行网格搜索
        best_config = current_config.copy()
        best_performance = baseline_performance
        tested_configs = []

        iteration = 0
        for spring_bars in param_grid["SPRING_FAILURE_BARS"]:
            for timeout_bars in param_grid["STATE_TIMEOUT_BARS"]:
                for min_confidence in param_grid["STATE_MIN_CONFIDENCE"]:
                    # 限制迭代次数
                    if iteration >= max_iterations:
                        logger.info("Reached max iterations (%d)", max_iterations)
                        break

                    # 创建测试配置
                    test_config = current_config.copy()
                    test_config.update(
                        {
                            "SPRING_FAILURE_BARS": spring_bars,
                            "STATE_TIMEOUT_BARS": timeout_bars,
                            "STATE_MIN_CONFIDENCE": min_confidence,
                            "PATH_SELECTION_THRESHOLD": param_grid[
                                "PATH_SELECTION_THRESHOLD"
                            ][iteration % len(param_grid["PATH_SELECTION_THRESHOLD"])],
                            "STATE_SWITCH_HYSTERESIS": param_grid[
                                "STATE_SWITCH_HYSTERESIS"
                            ][iteration % len(param_grid["STATE_SWITCH_HYSTERESIS"])],
                            "DIRECTION_SWITCH_PENALTY": param_grid[
                                "DIRECTION_SWITCH_PENALTY"
                            ][iteration % len(param_grid["DIRECTION_SWITCH_PENALTY"])],
                        }
                    )

                    # 评估配置性能
                    performance = self._evaluate_config_performance(
                        test_config, historical_data, target_metric, min_trades
                    )

                    tested_configs.append(
                        {
                            "config": test_config,
                            "performance": performance,
                            "iteration": iteration,
                        }
                    )

                    # 更新最佳配置
                    if performance > best_performance:
                        best_performance = performance
                        best_config = test_config.copy()
                        logger.info(
                            "Iteration %d: New best performance: %.4f", iteration, performance
                        )

                    iteration += 1

        # 计算改进幅度
        improvement = 0.0
        if baseline_performance > 0:
            improvement = (
                best_performance - baseline_performance
            ) / baseline_performance

        # 准备优化结果
        optimization_result = {
            "success": True,
            "message": f"Parameter optimization completed. Best {target_metric}: {best_performance:.4f} (improvement: {improvement:.2%})",
            "optimal_params": best_config,
            "improvement": improvement,
            "baseline_performance": baseline_performance,
            "best_performance": best_performance,
            "iterations_completed": iteration,
            "configs_tested": len(tested_configs),
        }

        # 应用最佳配置
        if improvement > 0.01:  # 至少1%的改进才应用
            logger.info(
                "Applying optimized configuration (improvement: %.2f%%)", improvement * 100
            )
            self._apply_optimized_config(best_config)
        else:
            logger.info(
                "Optimization didn't provide significant improvement, keeping current configuration"
            )

        # 记录优化历史
        self.optimization_history.append(
            {
                "timestamp": datetime.now(),
                "criteria": optimization_criteria,
                "result": optimization_result,
            }
        )

        logger.info("Parameter optimization completed successfully")
        return optimization_result

    def _evaluate_config_performance(
        self,
        config: dict[str, Any],
        historical_data: pd.DataFrame,
        target_metric: str,
        min_trades: int,
    ) -> float:
        """
        评估配置在历史数据上的性能

        Args:
            config: 配置字典
            historical_data: 历史数据
            target_metric: 目标指标
            min_trades: 最小交易次数要求

        Returns:
            性能分数
        """
        try:
            # 创建临时状态机实例用于评估
            temp_config = StateConfig()

            # 应用配置
            for key, value in config.items():
                if hasattr(temp_config, key):
                    setattr(temp_config, key, value)

            temp_state_machine = EnhancedWyckoffStateMachine(temp_config)

            # 模拟状态机运行
            signals = []
            chunk_size = 100  # 分批处理

            for i in range(0, len(historical_data), chunk_size):
                chunk = historical_data.iloc[i : i + chunk_size]

                # 更新状态机
                for idx, row in chunk.iterrows():
                    candle_data = pd.Series(
                        {
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "volume": float(row.get("volume", 0)),
                            "timestamp": idx,
                        }
                    )

                    temp_state_machine.process_candle(candle_data, {})

                # 收集信号（使用最新K线的时间戳）
                current_signals = temp_state_machine.generate_signals()
                if current_signals:
                    for signal in current_signals:
                        signal["timestamp"] = (
                            chunk.index[-1] if len(chunk) > 0 else datetime.now()
                        )
                        signals.append(signal)

            # 计算性能指标
            if len(signals) < min_trades:
                logger.warning(
                    "Insufficient signals for evaluation: %d < %d", len(signals), min_trades
                )
                return 0.0

            # 简化性能计算：基于信号质量和一致性
            performance_score = 0.0

            if target_metric == "win_rate":
                # 模拟胜率计算（简化版）
                # 在实际应用中，这里应该根据实际交易结果计算
                winning_signals = sum(
                    1 for s in signals if s.get("confidence", 0) > 0.7
                )
                performance_score = (
                    float(winning_signals / len(signals)) if signals else 0.0
                )

            elif target_metric == "signal_quality":
                # 信号质量：基于置信度和状态一致性
                confidences = [float(s.get("confidence", 0)) for s in signals]
                avg_confidence = (
                    float(np.mean(confidences).item()) if confidences else 0.0
                )
                state_changes = len({s.get("state", "") for s in signals})
                consistency = 1.0 / (1.0 + state_changes)  # 状态变化越少，一致性越高
                performance_score = float(avg_confidence * 0.7 + consistency * 0.3)

            elif target_metric == "risk_adjusted_return":
                # 风险调整收益（简化版）
                # 假设每个信号都有固定的收益/风险比
                confidences = [float(s.get("confidence", 0)) for s in signals]
                total_return = float(sum(confidences) * 0.01)  # 简化计算
                risk = (
                    float(np.std(confidences).item()) if len(confidences) > 1 else 0.0
                )
                performance_score = (
                    float(total_return / (1.0 + risk)) if risk > 0 else total_return
                )

            else:
                # 默认使用综合分数
                confidences = [float(s.get("confidence", 0)) for s in signals]
                avg_confidence = (
                    float(np.mean(confidences).item()) if confidences else 0.0
                )
                signal_count = len(signals)
                diversity = len({s.get("signal_type", "") for s in signals})
                performance_score = float(
                    avg_confidence * 0.5
                    + (signal_count / 100) * 0.3
                    + (diversity / 5) * 0.2
                )

            return float(max(0.0, min(1.0, performance_score)))

        except Exception:
            logger.exception("Error evaluating config performance")
            return 0.0

    def _apply_optimized_config(self, optimized_config: dict[str, Any]) -> None:
        """
        应用优化后的配置

        Args:
            optimized_config: 优化后的配置字典
        """
        try:
            # 更新配置对象
            for key, value in optimized_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

            logger.info("Optimized configuration applied successfully")

            # 记录配置更新
            self.config_updates.append(
                {
                    "timestamp": datetime.now(),
                    "old_config": self.config.to_dict(),
                    "new_config": optimized_config,
                    "reason": "parameter_optimization",
                }
            )

        except Exception:
            logger.exception("Error applying optimized config")
            raise

    def generate_signals(self) -> list[dict[str, Any]]:
        """
        生成基于当前状态的交易信号

        Returns:
            信号列表，每个信号包含类型、置信度、状态等信息
        """
        signals = []

        # 根据当前状态生成相应的信号
        if self.current_state in [
            "SC",
            "AR",
            "ST",
            "TEST",
            "SPRING",
            "SO",
            "LPS",
            "mSOS",
            "MSOS",
            "JOC",
            "BU",
        ]:
            # 吸筹阶段的买入信号
            if self.current_state in ["SC", "AR", "ST", "TEST"]:
                # 早期吸筹阶段 - 谨慎买入信号
                signal = {
                    "type": "buy_signal",
                    "confidence": self.state_confidences.get(self.current_state, 0.0)
                    * 0.7,
                    "state": self.current_state,
                    "description": f"吸筹早期阶段 {self.current_state} - 谨慎买入",
                    "strength": "weak",
                    "action": "monitor",
                }
                signals.append(signal)

            elif self.current_state in ["SPRING", "SO", "LPS"]:
                # 中期吸筹阶段 - 中等强度买入信号
                signal = {
                    "type": "buy_signal",
                    "confidence": self.state_confidences.get(self.current_state, 0.0)
                    * 0.8,
                    "state": self.current_state,
                    "description": f"吸筹中期阶段 {self.current_state} - 中等买入",
                    "strength": "medium",
                    "action": "consider_entry",
                }
                signals.append(signal)

            elif self.current_state in ["mSOS", "MSOS", "JOC", "BU"]:
                # 后期吸筹阶段 - 强买入信号
                signal = {
                    "type": "buy_signal",
                    "confidence": self.state_confidences.get(self.current_state, 0.0)
                    * 0.9,
                    "state": self.current_state,
                    "description": f"吸筹后期阶段 {self.current_state} - 强买入",
                    "strength": "strong",
                    "action": "enter",
                }
                signals.append(signal)

        elif self.current_state in [
            "PSY",
            "BC",
            "AR_DIST",
            "ST_DIST",
            "UT",
            "UTAD",
            "LPSY",
            "mSOW",
            "MSOW",
        ]:
            # 派发阶段的卖出信号
            if self.current_state in ["PSY", "BC", "AR_DIST", "ST_DIST"]:
                # 早期派发阶段 - 谨慎卖出信号
                signal = {
                    "type": "sell_signal",
                    "confidence": self.state_confidences.get(self.current_state, 0.0)
                    * 0.7,
                    "state": self.current_state,
                    "description": f"派发早期阶段 {self.current_state} - 谨慎卖出",
                    "strength": "weak",
                    "action": "monitor",
                }
                signals.append(signal)

            elif self.current_state in ["UT", "UTAD", "LPSY"]:
                # 中期派发阶段 - 中等强度卖出信号
                signal = {
                    "type": "sell_signal",
                    "confidence": self.state_confidences.get(self.current_state, 0.0)
                    * 0.8,
                    "state": self.current_state,
                    "description": f"派发中期阶段 {self.current_state} - 中等卖出",
                    "strength": "medium",
                    "action": "consider_exit",
                }
                signals.append(signal)

            elif self.current_state in ["mSOW", "MSOW"]:
                # 后期派发阶段 - 强卖出信号
                signal = {
                    "type": "sell_signal",
                    "confidence": self.state_confidences.get(self.current_state, 0.0)
                    * 0.9,
                    "state": self.current_state,
                    "description": f"派发后期阶段 {self.current_state} - 强卖出",
                    "strength": "strong",
                    "action": "exit",
                }
                signals.append(signal)

        elif self.current_state in ["TREND_UP", "UPTREND"]:
            # 上涨趋势中的买入信号
            signal = {
                "type": "buy_signal",
                "confidence": 0.6,
                "state": self.current_state,
                "description": "上涨趋势中 - 趋势跟随买入",
                "strength": "medium",
                "action": "trend_follow",
            }
            signals.append(signal)

        elif self.current_state in ["DOWNTREND", "TREND_DOWN"]:
            # 下跌趋势中的卖出信号
            signal = {
                "type": "sell_signal",
                "confidence": 0.6,
                "state": self.current_state,
                "description": "下跌趋势中 - 趋势跟随卖出",
                "strength": "medium",
                "action": "trend_follow",
            }
            signals.append(signal)

        # 如果没有特定信号，但状态置信度高，生成中性信号
        if not signals and self.current_state != "IDLE":
            state_confidence = self.state_confidences.get(self.current_state, 0.0)
            if state_confidence > 0.6:
                signal = {
                    "type": "no_signal",
                    "confidence": state_confidence,
                    "state": self.current_state,
                    "description": f"状态 {self.current_state} 置信度高，但无明确交易信号",
                    "strength": "neutral",
                    "action": "wait",
                }
                signals.append(signal)

        return signals

    def get_current_state_info(self) -> dict[str, Any]:
        """
        获取当前状态的详细信息

        Returns:
            包含状态信息、置信度、信号等的字典
        """
        signals = self.generate_signals()

        return {
            "current_state": self.current_state,
            "state_direction": self.state_direction.value
            if self.state_direction
            else "UNKNOWN",
            "state_confidence": self.state_confidences.get(self.current_state, 0.0),
            "state_intensity": self.state_intensities.get(self.current_state, 0.0),
            "signals": signals,
            "evidence_chain": {},
            "critical_price_levels": self.critical_price_levels,
            "alternative_paths_count": len(self.alternative_paths),
            "heritage_chain_length": len(self.heritage_chain),
        }


# ===== 证据链管理器 =====


