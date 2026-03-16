"""
策略优化器Agent模块
连接到威科夫进化系统 - 负责策略优化和权重变异
使用多周期验证系统进行进化

设计原则:
1. 多周期验证: 同时加载和验证多个时间周期 (W, D, H4, H1, M15, M5)
2. 周期权重: 使用 PeriodWeightFilter 进行加权决策
3. 冲突解决: 使用 ConflictResolver 处理多周期信号冲突
4. 真实数据: 使用真实历史数据进行回测和进化
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
import os
import logging

import pandas as pd
import numpy as np

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class OptimizationResult:
    """优化结果"""

    optimization_id: str
    method: str
    original_weights: Dict[str, float]
    optimized_weights: Dict[str, float]
    improvement: float
    wfa_passed: bool
    metrics: Dict[str, float]
    timestamp: datetime


DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
)

AVAILABLE_DATA = {
    "ETHUSDT_1d": "ETHUSDT_1d.csv",
    "ETHUSDT_8h": "ETHUSDT_8h.csv",
    "ETHUSDT_4h": "ETHUSDT_4h.csv",
    "ETHUSDT_1h": "ETHUSDT_1h.csv",
    "ETHUSDT_15m": "ETHUSDT_15m.csv",
    "ETHUSDT_5m": "ETHUSDT_5m.csv",
}

TIMEFRAME_ORDER = ["1d", "8h", "4h", "1h", "15m", "5m"]

TIMEFRAME_WEIGHTS = {
    "1d": 0.25,
    "8h": 0.20,
    "4h": 0.18,
    "1h": 0.15,
    "15m": 0.12,
    "5m": 0.10,
}

DEFAULT_STATE_CONFIG = {
    "PATH_SELECTION_THRESHOLD": 0.35,
    "STATE_MIN_CONFIDENCE": 0.35,
    "STATE_SWITCH_HYSTERESIS": 0.05,
}

TIMEFRAME_TO_PWF = {
    "1d": "D",
    "8h": "H8",
    "4h": "H4",
    "1h": "H1",
    "15m": "M15",
    "5m": "M5",
}


class MultiTimeframeDataManager:
    """多周期数据管理器"""

    def __init__(self, symbol: str = "ETHUSDT"):
        self.symbol = symbol
        self.data: Dict[str, pd.DataFrame] = {}
        self.logger = logging.getLogger(__name__)

    def load_all_timeframes(self) -> Dict[str, pd.DataFrame]:
        """加载所有时间周期数据"""
        self.logger.info(f"开始加载多周期数据，数据目录: {DATA_DIR}")

        for tf in TIMEFRAME_ORDER:
            key = f"{self.symbol}_{tf}"
            self.logger.info(f"正在加载 {tf} 数据...")

            if key in AVAILABLE_DATA:
                data = self._load_single_timeframe(key)
                if data is not None:
                    self.data[tf] = data
                    self.logger.info(f"加载 {tf} 数据完成: {len(data)} 条记录")
                else:
                    self.logger.warning(f"加载 {tf} 数据失败")
            else:
                self.logger.warning(f"未找到 {key} 数据配置")

        self.logger.info(f"多周期数据加载完成，共 {len(self.data)} 个时间周期")
        return self.data

    def _load_single_timeframe(self, data_key: str) -> Optional[pd.DataFrame]:
        """加载单个时间周期数据"""
        if data_key not in AVAILABLE_DATA:
            return None

        csv_file = os.path.join(DATA_DIR, AVAILABLE_DATA[data_key])

        if not os.path.exists(csv_file):
            self.logger.error(f"数据文件不存在: {csv_file}")
            return None

        try:
            data = pd.read_csv(csv_file)

            time_columns = [
                "timestamp",
                "Timestamp",
                "time",
                "Time",
                "date",
                "Date",
                "Open_time",
                "open_time",
            ]
            time_col = None
            for col in time_columns:
                if col in data.columns:
                    time_col = col
                    break

            if time_col:
                data[time_col] = pd.to_datetime(data[time_col])
                data.set_index(time_col, inplace=True)

            data.columns = [c.lower() for c in data.columns]

            required_cols = ["open", "high", "low", "close", "volume"]
            missing = [c for c in required_cols if c not in data.columns]
            if missing:
                self.logger.error(f"数据缺少必需列: {missing}")
                return None

            data = data.dropna(subset=required_cols)

            return data

        except Exception as e:
            self.logger.error(f"加载数据失败: {e}")
            return None

    def get_aligned_data(
        self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None
    ) -> Dict[str, pd.DataFrame]:
        """获取对齐的多周期数据"""
        aligned_data = {}

        if start_time or end_time:
            for tf, df in self.data.items():
                if start_time:
                    df = df[df.index >= start_time]
                if end_time:
                    df = df[df.index <= end_time]
                if len(df) > 0:
                    aligned_data[tf] = df
        else:
            aligned_data = self.data.copy()

        return aligned_data


class MultiTimeframeStateMachineRunner:
    """多周期状态机运行器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.state_machines: Dict[str, Any] = {}
        self.context_builders: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)

    def initialize_state_machines(self) -> None:
        """初始化所有时间周期的状态机"""
        from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
            EnhancedWyckoffStateMachine,
        )
        from src.kernel.types import StateConfig  # legacy
        from src.plugins.wyckoff_state_machine.context_builder import (
            WyckoffContextBuilder,
        )

        for tf in TIMEFRAME_ORDER:
            sm_config = StateConfig()
            sm_config.PATH_SELECTION_THRESHOLD = self.config.get(
                "PATH_SELECTION_THRESHOLD", 0.35
            )
            sm_config.STATE_MIN_CONFIDENCE = self.config.get(
                "STATE_MIN_CONFIDENCE", 0.35
            )
            sm_config.STATE_SWITCH_HYSTERESIS = self.config.get(
                "STATE_SWITCH_HYSTERESIS", 0.05
            )

            self.state_machines[tf] = EnhancedWyckoffStateMachine(sm_config)
            self.context_builders[tf] = WyckoffContextBuilder()
            self.logger.info(f"初始化 {tf} 状态机和Context构建器")

    def process_candle(
        self, tf: str, candle: pd.Series, data: pd.DataFrame, idx: int
    ) -> str:
        """处理单个K线并返回状态"""
        if tf not in self.state_machines:
            return "UNKNOWN"

        current_state = (
            self.state_machines[tf].current_state
            if hasattr(self.state_machines[tf], "current_state")
            else "IDLE"
        )

        context = self.context_builders[tf].build_context(
            data, candle, idx, current_state
        )

        return self.state_machines[tf].process_candle(candle, context)

    def generate_signals(self, tf: str) -> List[Dict[str, Any]]:
        """生成信号"""
        if tf not in self.state_machines:
            return []

        return self.state_machines[tf].generate_signals()

    def get_all_states(self) -> Dict[str, str]:
        """获取所有时间周期的当前状态"""
        states = {}
        for tf, sm in self.state_machines.items():
            states[tf] = sm.current_state if hasattr(sm, "current_state") else "UNKNOWN"
        return states

    def reset(self) -> None:
        """重置所有状态机和Context构建器"""
        for tf in self.state_machines:
            if hasattr(self.state_machines[tf], "reset"):
                self.state_machines[tf].reset()
            if hasattr(self.context_builders[tf], "reset"):
                self.context_builders[tf].reset()


class MultiTimeframePerformanceEvaluator:
    """多周期性能评估器"""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or TIMEFRAME_WEIGHTS.copy()
        self.logger = logging.getLogger(__name__)

    def _evaluate_single_tf(
        self, config: Dict[str, Any], tf: str, data: pd.DataFrame, eval_bars: int = 0
    ) -> Dict[str, Any]:
        """评估单个时间周期

        Args:
            config: 配置参数
            tf: 时间周期
            data: K线数据
            eval_bars: 评估K线数量，0表示使用全部数据
        """
        from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
            EnhancedWyckoffStateMachine,
        )
        from src.kernel.types import StateConfig
        from src.plugins.wyckoff_state_machine.context_builder import (
            WyckoffContextBuilder,
        )
        from src.backtest.engine import BacktestEngine

        sm_config = StateConfig()
        sm_config.PATH_SELECTION_THRESHOLD = config.get(
            "PATH_SELECTION_THRESHOLD", 0.35
        )
        sm_config.STATE_MIN_CONFIDENCE = config.get("STATE_MIN_CONFIDENCE", 0.35)
        sm_config.STATE_SWITCH_HYSTERESIS = config.get("STATE_SWITCH_HYSTERESIS", 0.05)

        for key, value in config.items():
            if hasattr(sm_config, key):
                setattr(sm_config, key, value)

        sm = EnhancedWyckoffStateMachine(sm_config)
        context_builder = WyckoffContextBuilder()
        engine = BacktestEngine(initial_capital=10000, commission_rate=0.001)

        signals = []
        state_history = []

        eval_data = data
        if eval_bars > 0 and len(data) > eval_bars:
            eval_data = data.iloc[-eval_bars:]
            self.logger.info(f"评估最近 {eval_bars} 条K线")

        total_bars = len(eval_data)
        self.logger.info(f"开始评估 {tf} 周期，共 {total_bars} 条K线")

        for i, (idx, row) in enumerate(eval_data.iterrows()):
            if i % 10000 == 0 and i > 0:
                self.logger.info(
                    f"  {tf} 进度: {i}/{total_bars} ({i * 100 / total_bars:.1f}%)"
                )

            candle = pd.Series(
                {
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
            )

            current_state = sm.current_state if hasattr(sm, "current_state") else "IDLE"

            context = context_builder.build_context(eval_data, candle, i, current_state)

            state = sm.process_candle(candle, context)
            state_history.append(state)

            current_signals = sm.generate_signals()
            if current_signals:
                for sig in current_signals:
                    sig_type = sig.get("type", "")
                    if "buy" in sig_type.lower():
                        action = "BUY"
                    elif "sell" in sig_type.lower():
                        action = "SELL"
                    else:
                        continue

                    confidence = sig.get("confidence", 0)
                    if confidence < 0.3:
                        continue

                    signals.append(
                        {
                            "timestamp": idx,
                            "signal": action,
                            "confidence": confidence,
                            "reason": sig.get("description", ""),
                            "state": state,
                            "tr_high": context.get("tr_high"),
                            "tr_low": context.get("tr_low"),
                            "trend_direction": context.get("trend_direction"),
                        }
                    )

        result = engine.run(eval_data, sm, signals)

        bullish_count = sum(1 for s in signals if s["signal"] == "BUY")
        bearish_count = sum(1 for s in signals if s["signal"] == "SELL")

        if bullish_count > bearish_count:
            overall_state = "BULLISH"
            score = bullish_count / max(len(signals), 1)
        elif bearish_count > bullish_count:
            overall_state = "BEARISH"
            score = bearish_count / max(len(signals), 1)
        else:
            overall_state = "NEUTRAL"
            score = 0.5

        return {
            "state": overall_state,
            "score": score,
            "confidence": score,
            "signals": signals,
            "trades": result.total_trades,
            "sharpe": result.sharpe_ratio,
            "win_rate": result.win_rate,
            "max_drawdown": result.max_drawdown,
            "state_changes": len(set(state_history)),
        }

    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算ATR"""
        high = data["high"]
        low = data["low"]
        close = data["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()

        return atr

    def _detect_simple_regime(
        self, data: pd.DataFrame, idx: int, lookback: int = 50
    ) -> str:
        """简单市场体制检测"""
        if idx < lookback:
            return "UNKNOWN"

        recent_data = data.iloc[idx - lookback : idx]

        if len(recent_data) < lookback:
            return "UNKNOWN"

        start_close = recent_data["close"].iloc[0]
        end_close = recent_data["close"].iloc[-1]

        change = (end_close - start_close) / start_close

        if change > 0.1:
            return "UPTREND"
        elif change < -0.1:
            return "DOWNTREND"
        else:
            return "RANGING"

    def evaluate(
        self,
        config: Dict[str, Any],
        multi_tf_data: Dict[str, pd.DataFrame],
        market_regime: str = "UNKNOWN",
        eval_bars: int = 0,
    ) -> Dict[str, float]:
        """评估多周期配置性能

        Args:
            config: 配置参数
            multi_tf_data: 多周期数据
            market_regime: 市场体制
            eval_bars: 评估K线数量，0表示使用全部数据
        """
        from src.plugins.weight_system.period_weight_filter import (
            PeriodWeightFilter,
            Timeframe,
        )
        from src.plugins.signal_validation.conflict_resolver import (
            ConflictResolutionManager,
        )
        from src.backtest.engine import BacktestEngine

        pwf_weights = {}
        for tf, weight in self.weights.items():
            pwf_key = TIMEFRAME_TO_PWF.get(tf, tf.upper())
            pwf_weights[pwf_key] = weight

        weight_filter = PeriodWeightFilter({"weights": pwf_weights})

        conflict_resolver = ConflictResolutionManager()

        tf_results = {}
        all_signals = []

        self.logger.info(f"开始评估 {len(multi_tf_data)} 个时间周期")

        for tf_idx, (tf, data) in enumerate(multi_tf_data.items()):
            self.logger.info(
                f"评估时间周期 {tf_idx + 1}/{len(multi_tf_data)}: {tf} ({len(data)} 条K线)"
            )
            tf_result = self._evaluate_single_tf(config, tf, data, eval_bars)
            tf_results[tf] = tf_result
            self.logger.info(
                f"  {tf} 评估完成: state={tf_result.get('state')}, trades={tf_result.get('trades', 0)}"
            )

            for signal in tf_result.get("signals", []):
                signal["timeframe"] = tf
                all_signals.append(signal)

        self.logger.info("所有时间周期评估完成，开始计算加权分数")

        weighted_score = weight_filter.calculate_weighted_score(
            {tf: r.get("score", 0.5) for tf, r in tf_results.items()}, market_regime
        )

        tf_states = {}
        for tf, result in tf_results.items():
            state = result.get("state", "NEUTRAL")
            if "BULLISH" in state.upper() or "ACCUMULATION" in state.upper():
                tf_states[tf] = {
                    "state": "BULLISH",
                    "confidence": result.get("confidence", 0.5),
                }
            elif "BEARISH" in state.upper() or "DISTRIBUTION" in state.upper():
                tf_states[tf] = {
                    "state": "BEARISH",
                    "confidence": result.get("confidence", 0.5),
                }
            else:
                tf_states[tf] = {
                    "state": "NEUTRAL",
                    "confidence": result.get("confidence", 0.5),
                }

        resolution = conflict_resolver.resolve_conflict(
            tf_states, {"regime": market_regime}
        )

        primary_tf = list(multi_tf_data.keys())[0] if multi_tf_data else "4h"
        primary_data = multi_tf_data.get(
            primary_tf,
            list(multi_tf_data.values())[0] if multi_tf_data else pd.DataFrame(),
        )

        engine = BacktestEngine(initial_capital=10000, commission_rate=0.001)

        sm_runner = MultiTimeframeStateMachineRunner(config)
        sm_runner.initialize_state_machines()

        primary_sm = sm_runner.state_machines.get(primary_tf)

        backtest_signals = []
        if primary_sm and len(primary_data) > 0:
            eval_data = primary_data
            if eval_bars > 0 and len(primary_data) > eval_bars:
                eval_data = primary_data.iloc[-eval_bars:]

            primary_data_copy = eval_data.copy()
            primary_data_copy["avg_volume_20"] = (
                primary_data_copy["volume"].rolling(20).mean()
            )
            primary_data_copy["avg_close_20"] = (
                primary_data_copy["close"].rolling(20).mean()
            )

            for i, (idx, row) in enumerate(primary_data_copy.iterrows()):
                candle = pd.Series(
                    {
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                    }
                )

                context = {
                    "avg_volume_20": row.get("avg_volume_20", row["volume"]),
                    "avg_close_20": row.get("avg_close_20", row["close"]),
                    "market_regime": "UNKNOWN",
                    "bar_index": i,
                }

                primary_sm.process_candle(candle, context)
                current_signals = primary_sm.generate_signals()

                if current_signals:
                    for sig in current_signals:
                        sig_type = sig.get("type", "")
                        if "buy" in sig_type.lower():
                            action = "BUY"
                        elif "sell" in sig_type.lower():
                            action = "SELL"
                        else:
                            continue

                        confidence = sig.get("confidence", 0)
                        if confidence < 0.3:
                            continue

                        backtest_signals.append(
                            {
                                "timestamp": idx,
                                "signal": action,
                                "confidence": confidence,
                                "reason": sig.get("description", ""),
                            }
                        )

            result = engine.run(eval_data, primary_sm, backtest_signals)

            return {
                "SHARPE_RATIO": result.sharpe_ratio,
                "MAX_DRAWDOWN": result.max_drawdown,
                "WIN_RATE": result.win_rate,
                "PROFIT_FACTOR": result.total_pnl / abs(result.total_pnl)
                if result.total_pnl != 0
                else 1.0,
                "TOTAL_RETURN": (engine.capital - 10000) / 10000,
                "TRADE_COUNT": result.total_trades,
                "WEIGHTED_SCORE": weighted_score,
                "CONFLICT_RESOLUTION": resolution.get("conflict_resolution", "UNKNOWN"),
                "PRIMARY_BIAS": resolution.get("primary_bias", "NEUTRAL"),
                "TF_RESULTS": {
                    tf: {"state": r.get("state"), "trades": r.get("trades", 0)}
                    for tf, r in tf_results.items()
                },
            }

        return {
            "SHARPE_RATIO": 0.0,
            "MAX_DRAWDOWN": 1.0,
            "WIN_RATE": 0.0,
            "PROFIT_FACTOR": 1.0,
            "TOTAL_RETURN": -1.0,
            "TRADE_COUNT": 0,
            "WEIGHTED_SCORE": weighted_score,
            "CONFLICT_RESOLUTION": resolution.get("conflict_resolution", "UNKNOWN"),
            "PRIMARY_BIAS": resolution.get("primary_bias", "NEUTRAL"),
        }

    def _evaluate_single_timeframe(
        self,
        config: Dict[str, Any],
        tf: str,
        data: pd.DataFrame,
        fast_mode: bool = True,
    ) -> Dict[str, Any]:
        """评估单个时间周期 - 使用完整的Context系统

        Args:
            config: 配置参数
            tf: 时间周期
            data: K线数据
            fast_mode: 快速模式，只评估最近的数据
        """
        from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
            EnhancedWyckoffStateMachine,
        )
        from src.kernel.types import StateConfig
        from src.plugins.wyckoff_state_machine.context_builder import (
            WyckoffContextBuilder,
        )
        from src.backtest.engine import BacktestEngine

        sm_config = StateConfig()
        sm_config.PATH_SELECTION_THRESHOLD = config.get(
            "PATH_SELECTION_THRESHOLD", 0.35
        )
        sm_config.STATE_MIN_CONFIDENCE = config.get("STATE_MIN_CONFIDENCE", 0.35)
        sm_config.STATE_SWITCH_HYSTERESIS = config.get("STATE_SWITCH_HYSTERESIS", 0.05)

        for key, value in config.items():
            if hasattr(sm_config, key):
                setattr(sm_config, key, value)

        sm = EnhancedWyckoffStateMachine(sm_config)
        context_builder = WyckoffContextBuilder()
        engine = BacktestEngine(initial_capital=10000, commission_rate=0.001)

        signals = []
        state_history = []

        eval_data = data
        if fast_mode and len(data) > 500:
            eval_data = data.iloc[-500:]
            self.logger.info(f"快速模式: 只评估最近500条K线")

        for i, (idx, row) in enumerate(eval_data.iterrows()):
            candle = pd.Series(
                {
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
            )

            current_state = sm.current_state if hasattr(sm, "current_state") else "IDLE"

            context = context_builder.build_context(eval_data, candle, i, current_state)

            state = sm.process_candle(candle, context)
            state_history.append(state)

            current_signals = sm.generate_signals()
            if current_signals:
                for sig in current_signals:
                    sig_type = sig.get("type", "")
                    if "buy" in sig_type.lower():
                        action = "BUY"
                    elif "sell" in sig_type.lower():
                        action = "SELL"
                    else:
                        continue

                    confidence = sig.get("confidence", 0)
                    if confidence < 0.3:
                        continue

                    signals.append(
                        {
                            "timestamp": idx,
                            "signal": action,
                            "confidence": confidence,
                            "reason": sig.get("description", ""),
                            "state": state,
                            "tr_high": context.get("tr_high"),
                            "tr_low": context.get("tr_low"),
                            "trend_direction": context.get("trend_direction"),
                        }
                    )

        result = engine.run(eval_data, sm, signals)

        bullish_count = sum(1 for s in signals if s["signal"] == "BUY")
        bearish_count = sum(1 for s in signals if s["signal"] == "SELL")

        if bullish_count > bearish_count:
            overall_state = "BULLISH"
            score = bullish_count / max(len(signals), 1)
        elif bearish_count > bullish_count:
            overall_state = "BEARISH"
            score = bearish_count / max(len(signals), 1)
        else:
            overall_state = "NEUTRAL"
            score = 0.5

        return {
            "state": overall_state,
            "score": score,
            "confidence": score,
            "signals": signals,
            "trades": result.total_trades,
            "sharpe": result.sharpe_ratio,
            "win_rate": result.win_rate,
            "max_drawdown": result.max_drawdown,
            "state_changes": len(set(state_history)),
        }

    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算ATR"""
        high = data["high"]
        low = data["low"]
        close = data["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()

        return atr

    def _detect_simple_regime(
        self, data: pd.DataFrame, idx: int, lookback: int = 50
    ) -> str:
        """简单市场体制检测"""
        if idx < lookback:
            return "UNKNOWN"

        recent_data = data.iloc[idx - lookback : idx]

        if len(recent_data) < lookback:
            return "UNKNOWN"

        start_close = recent_data["close"].iloc[0]
        end_close = recent_data["close"].iloc[-1]

        change = (end_close - start_close) / start_close

        if change > 0.1:
            return "UPTREND"
        elif change < -0.1:
            return "DOWNTREND"
        else:
            return "RANGING"


class StrategyOptimizerAgent(BaseAgent):
    """策略优化器Agent - 连接到威科夫进化系统（多周期验证）"""

    def __init__(
        self,
        agent_id: str = "strategy_optimizer",
        name: str = "策略优化器",
        description: str = "负责策略优化和权重变异（多周期验证）",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.project_root = config.get("project_root", ".") if config else "."
        self.optimization_history: List[OptimizationResult] = []

        self.mistake_book = None
        self.weight_variator = None
        self.wfa_backtester = None
        self.correction_workflow = None
        self.system_config = {}

        self.multi_tf_data_manager: Optional[MultiTimeframeDataManager] = None
        self.multi_tf_sm_runner: Optional[MultiTimeframeStateMachineRunner] = None
        self.multi_tf_evaluator: Optional[MultiTimeframePerformanceEvaluator] = None

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(
            AgentCapability(
                name="run_evolution",
                description="运行进化周期（多周期验证）",
                input_schema={"cycles": "int", "auto_apply": "bool"},
                output_schema={"result": "OptimizationResult"},
            )
        )

        self.add_capability(
            AgentCapability(
                name="optimize_weights",
                description="优化权重参数",
                input_schema={"target": "string", "method": "string"},
                output_schema={"optimized": "dict", "improvement": "float"},
            )
        )

        self.add_capability(
            AgentCapability(
                name="analyze_mistakes",
                description="分析错题本",
                input_schema={"limit": "int"},
                output_schema={"patterns": "list", "suggestions": "list"},
            )
        )

        self.add_capability(
            AgentCapability(
                name="run_wfa_validation",
                description="运行WFA验证",
                input_schema={"config": "dict"},
                output_schema={"passed": "bool", "score": "float"},
            )
        )

        self.add_capability(
            AgentCapability(
                name="get_multi_timeframe_status",
                description="获取多周期状态",
                input_schema={},
                output_schema={"states": "dict", "conflicts": "list"},
            )
        )

    def _register_handlers(self) -> None:
        """注册消息处理器"""
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)
        self.register_handler(MessageType.REQUEST, self._handle_request)
        self.register_handler(MessageType.TASK_STATUS, self._handle_task_status)

    def _handle_task_status(self, message: AgentMessage) -> AgentMessage:
        """处理任务状态查询"""
        task_id = message.content.get("task_id")

        for result in self.task_history:
            if hasattr(result, "task_id") and result.task_id == task_id:
                return message.create_response(
                    {
                        "task_id": task_id,
                        "status": "completed" if result.success else "failed",
                        "result": result.output if result.success else None,
                        "error": result.error_message if not result.success else None,
                    }
                )

        return message.create_response(
            {
                "task_id": task_id,
                "status": "not_found",
            }
        )

    def _broadcast_progress(self, progress_data: Dict[str, Any]) -> None:
        """广播进度更新到WebSocket客户端"""
        try:
            from src.visualization.web_dashboard import manager
            import asyncio

            self.logger.info(f"尝试广播进度: {progress_data.get('type', 'unknown')}")

            if manager and manager.active:
                self.logger.info(f"WebSocket客户端数量: {len(manager.active)}")

                loop = getattr(self, "_main_loop", None)
                if loop is None:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        pass

                if loop and loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        manager.broadcast(progress_data), loop
                    )
                    future.result(timeout=5)
                    self.logger.info("进度广播成功")
                else:
                    self.logger.warning(f"事件循环未运行: loop={loop}")
            else:
                self.logger.warning(
                    f"manager或manager.active为空: manager={manager}, active={manager.active if manager else None}"
                )
        except Exception as e:
            self.logger.error(f"广播进度失败: {e}")

    def set_main_loop(self, loop) -> None:
        """设置主事件循环（用于子线程广播进度）"""
        self._main_loop = loop

    def initialize(self) -> None:
        """初始化 - 连接到进化系统，加载多周期数据"""
        super().initialize()

        from src.plugins.self_correction.mistake_book import MistakeBook
        from src.plugins.evolution.weight_variator_legacy import WeightVariator
        from src.plugins.evolution.wfa_backtester import WFABacktester
        from src.plugins.self_correction.workflow import SelfCorrectionWorkflow

        import yaml

        config_path = os.path.join(self.project_root, "config.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.system_config = yaml.safe_load(f) or {}

        self.mistake_book = MistakeBook()
        self.weight_variator = WeightVariator()
        self.wfa_backtester = WFABacktester(
            {
                "train_days": 300,
                "test_days": 100,
                "step_days": 200,
                "max_windows": 10,
                "min_window_count": 3,
                "min_performance_improvement": 0.001,
                "stability_threshold": 0.3,
                "require_statistical_significance": False,
            }
        )

        self.logger.info("加载多周期历史数据...")
        self.multi_tf_data_manager = MultiTimeframeDataManager("ETHUSDT")
        multi_tf_data = self.multi_tf_data_manager.load_all_timeframes()

        if multi_tf_data:
            total_bars = sum(len(df) for df in multi_tf_data.values())
            self.logger.info(
                f"成功加载 {len(multi_tf_data)} 个时间周期，共 {total_bars} 条K线数据"
            )

            for tf, df in multi_tf_data.items():
                self.logger.info(
                    f"  {tf}: {len(df)} 条记录, 时间范围: {df.index[0]} 到 {df.index[-1]}"
                )

            self.multi_tf_evaluator = MultiTimeframePerformanceEvaluator()

            self.correction_workflow = SelfCorrectionWorkflow(
                config={
                    "initial_config": {
                        "PATH_SELECTION_THRESHOLD": 0.35,
                        "STATE_MIN_CONFIDENCE": 0.35,
                        "STATE_SWITCH_HYSTERESIS": 0.05,
                    },
                    "min_errors_for_correction": 0,
                    "max_mutations_per_cycle": 3,
                },
                mistake_book=self.mistake_book,
                weight_variator=self.weight_variator,
                wfa_backtester=self.wfa_backtester,
            )

            primary_tf = list(multi_tf_data.keys())[0] if multi_tf_data else "4h"
            primary_data = multi_tf_data.get(
                primary_tf,
                list(multi_tf_data.values())[0] if multi_tf_data else pd.DataFrame(),
            )

            def multi_tf_evaluator_func(config: dict, data: pd.DataFrame) -> dict:
                return self.multi_tf_evaluator.evaluate(
                    config, multi_tf_data, "UNKNOWN", eval_bars=1000
                )

            self.correction_workflow.set_historical_data(primary_data)
            self.correction_workflow.set_performance_evaluator(multi_tf_evaluator_func)

            self.logger.info("已连接到威科夫进化系统（多周期验证模式）")
            self.logger.info("WFA基准将在第一次进化时初始化")
        else:
            self.logger.warning("无法加载多周期数据")

    def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """执行任务"""
        start_time = datetime.now()
        self.update_state(AgentState.WORKING)

        try:
            task_type = task.get("type", "run_evolution")

            if task_type == "run_evolution":
                result = self._run_evolution(task)
            elif task_type == "optimize_weights":
                result = self._optimize_weights(task)
            elif task_type == "analyze_mistakes":
                result = self._analyze_mistakes(task)
            elif task_type == "run_wfa_validation":
                result = self._run_wfa_validation(task)
            elif task_type == "get_multi_timeframe_status":
                result = self._get_multi_timeframe_status(task)
            else:
                result = {"error": f"未知任务类型: {task_type}"}

            duration = (datetime.now() - start_time).total_seconds()

            task_result = TaskResult(
                success="error" not in result,
                output=result,
                duration_seconds=duration,
            )
            self.record_task_result(task_result)
            return task_result

        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            return TaskResult(
                success=False,
                output={},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )
        finally:
            self.update_state(AgentState.IDLE)

    def _handle_task_assign(self, message: AgentMessage) -> AgentMessage:
        """处理任务分配"""
        task = message.content
        result = self.execute_task(task)

        return message.create_response(
            {
                "task_type": task.get("type"),
                "success": result.success,
                "output": result.output,
                "error": result.error_message,
            }
        )

    def _handle_request(self, message: AgentMessage) -> AgentMessage:
        """处理请求"""
        request_type = message.content.get("request_type")

        if request_type == "get_status":
            return message.create_response(self.get_status())
        elif request_type == "get_history":
            return message.create_response(
                {
                    "history": [
                        self._result_to_dict(r) for r in self.optimization_history
                    ]
                }
            )
        elif request_type == "get_multi_timeframe_data":
            return message.create_response(self._get_multi_timeframe_data_summary())
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _run_evolution(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """运行进化周期 - 使用多周期验证"""
        cycles = task.get("cycles", 1)
        auto_apply = task.get("auto_apply", False)

        if self.correction_workflow is None:
            return {"error": "进化工作流未初始化，请先调用 initialize()"}

        if self.multi_tf_data_manager is None or not self.multi_tf_data_manager.data:
            return {"error": "多周期数据未加载"}

        results = []
        self.logger.info(f"开始运行 {cycles} 个进化周期（多周期验证模式）...")

        multi_tf_data = self.multi_tf_data_manager.data

        def multi_tf_evaluator(config: dict, data: pd.DataFrame) -> dict:
            return self.multi_tf_evaluator.evaluate(
                config, multi_tf_data, "UNKNOWN", eval_bars=1000
            )

        primary_tf = list(multi_tf_data.keys())[0] if multi_tf_data else "4h"
        primary_data = multi_tf_data.get(
            primary_tf,
            list(multi_tf_data.values())[0] if multi_tf_data else pd.DataFrame(),
        )

        self.correction_workflow.set_historical_data(primary_data)
        self.correction_workflow.set_performance_evaluator(multi_tf_evaluator)

        if not self.correction_workflow.wfa_backtester.is_initialized:
            self.logger.info("初始化WFA基准...")
            self.logger.info("注意：评估所有多周期数据可能需要几分钟，请耐心等待...")
            self._broadcast_progress(
                {
                    "type": "evolution_progress",
                    "current_cycle": 0,
                    "total_cycles": cycles,
                    "status": "initializing_wfa",
                    "message": "正在初始化WFA基准，评估多周期数据（可能需要几分钟）...",
                }
            )
            init_success = self.correction_workflow.initialize_wfa_baseline()
            if not init_success:
                self.logger.error("WFA基准初始化失败！")
                return {"error": "WFA基准初始化失败"}
            self.logger.info("WFA基准初始化完成！")

        for i in range(cycles):
            self.logger.info(f"运行进化周期 {i + 1}/{cycles}")

            # 推送进度更新
            self._broadcast_progress(
                {
                    "type": "evolution_progress",
                    "current_cycle": i + 1,
                    "total_cycles": cycles,
                    "status": "running",
                    "message": f"正在运行进化周期 {i + 1}/{cycles}",
                }
            )

            cycle_start = datetime.now()
            cycle_result = self.correction_workflow.run_correction_cycle()
            cycle_duration = (datetime.now() - cycle_start).total_seconds()

            success = cycle_result.get("success", False)
            improvement = cycle_result.get("improvement", 0)
            wfa_passed = cycle_result.get("wfa_passed", False)

            results.append(
                {
                    "cycle": i + 1,
                    "success": success,
                    "improvement": improvement,
                    "wfa_passed": wfa_passed,
                    "duration_seconds": cycle_duration,
                    "details": cycle_result,
                }
            )

            self.logger.info(
                f"进化周期 {i + 1} 完成: 成功={success}, 耗时={cycle_duration:.2f}秒"
            )

            # 推送周期完成更新
            self._broadcast_progress(
                {
                    "type": "evolution_cycle_complete",
                    "cycle": i + 1,
                    "success": success,
                    "improvement": improvement,
                    "wfa_passed": wfa_passed,
                    "duration": cycle_duration,
                }
            )

            if not success:
                self.logger.warning(
                    f"进化周期 {i + 1} 失败: {cycle_result.get('error_message', '未知错误')}"
                )

        success_count = sum(1 for r in results if r.get("success", False))
        total_duration = sum(r.get("duration_seconds", 0) for r in results)

        return {
            "cycles_completed": cycles,
            "results": results,
            "success_count": success_count,
            "total_duration_seconds": total_duration,
            "data_source": "多周期数据 (1d, 8h, 4h, 1h, 15m, 5m)",
            "timeframes_loaded": list(multi_tf_data.keys()),
            "total_bars": sum(len(df) for df in multi_tf_data.values()),
            "auto_applied": auto_apply,
        }

    def _optimize_weights(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """优化权重参数"""
        target = task.get("target", "all")
        method = task.get("method", "genetic")

        from src.plugins.evolution.weight_variator_legacy import (
            WeightVariator,
            MutationType,
        )

        current_weights = self._get_current_weights()

        if self.weight_variator:
            mutation_result = self.weight_variator.generate_mutation(
                current_weights,
                mutation_type=MutationType.WEIGHT_ADJUSTMENT,
            )

            optimized_weights = mutation_result.get("mutated_weights", current_weights)
            improvement = mutation_result.get("expected_improvement", 0)
        else:
            return {"error": "权重变异器未初始化"}

        result = OptimizationResult(
            optimization_id=f"opt_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            method=method,
            original_weights=current_weights,
            optimized_weights=optimized_weights,
            improvement=improvement,
            wfa_passed=False,
            metrics={},
            timestamp=datetime.now(),
        )

        self.optimization_history.append(result)

        return {
            "optimization_id": result.optimization_id,
            "original_weights": current_weights,
            "optimized_weights": optimized_weights,
            "improvement": improvement,
        }

    def _analyze_mistakes(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """分析错题本"""
        limit = task.get("limit", 10)

        if self.mistake_book:
            mistakes = self.mistake_book.get_recent_mistakes(limit=limit)
            patterns = self.mistake_book.analyze_patterns()
            suggestions = self.mistake_book.generate_suggestions()

            return {
                "mistake_count": len(mistakes),
                "mistakes": mistakes[:limit],
                "patterns": patterns,
                "suggestions": suggestions,
            }
        else:
            return {"error": "错题本未初始化"}

    def _run_wfa_validation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """运行WFA验证"""
        config = task.get("config", {})

        if self.wfa_backtester:
            wfa_result = self.wfa_backtester.run_validation(
                train_days=config.get("train_days", 300),
                test_days=config.get("test_days", 100),
                step_days=config.get("step_days", 200),
            )

            return {
                "passed": wfa_result.get("passed", False),
                "stability_score": wfa_result.get("stability_score", 0),
                "window_results": wfa_result.get("window_results", []),
                "overfitting_detected": wfa_result.get("overfitting_detected", False),
                "details": wfa_result,
            }
        else:
            return {"error": "WFA回测器未初始化"}

    def _get_multi_timeframe_status(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """获取多周期状态"""
        if self.multi_tf_data_manager is None:
            return {"error": "多周期数据管理器未初始化"}

        status = {
            "timeframes_loaded": list(self.multi_tf_data_manager.data.keys()),
            "data_summary": {},
        }

        for tf, df in self.multi_tf_data_manager.data.items():
            status["data_summary"][tf] = {
                "bars": len(df),
                "start": str(df.index[0]) if len(df) > 0 else None,
                "end": str(df.index[-1]) if len(df) > 0 else None,
            }

        return status

    def _get_multi_timeframe_data_summary(self) -> Dict[str, Any]:
        """获取多周期数据摘要"""
        if self.multi_tf_data_manager is None:
            return {"error": "多周期数据管理器未初始化"}

        return {
            "timeframes": list(self.multi_tf_data_manager.data.keys()),
            "total_bars": sum(
                len(df) for df in self.multi_tf_data_manager.data.values()
            ),
            "weights": TIMEFRAME_WEIGHTS,
        }

    def _get_current_weights(self) -> Dict[str, float]:
        """获取当前权重"""
        if self.system_config:
            return self.system_config.get("wyckoff", {}).get("weights", {})
        return TIMEFRAME_WEIGHTS

    def _result_to_dict(self, result: OptimizationResult) -> Dict[str, Any]:
        """将结果转换为字典"""
        return {
            "optimization_id": result.optimization_id,
            "method": result.method,
            "improvement": result.improvement,
            "wfa_passed": result.wfa_passed,
            "timestamp": result.timestamp.isoformat(),
        }
