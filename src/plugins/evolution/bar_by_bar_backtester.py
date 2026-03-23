"""逐Bar回测器 — 使用 WyckoffEngine.process_bar() + SignalControl 节流

职责：
1. 逐根H4 K线驱动 WyckoffEngine.process_bar()
2. SignalControl 冷却期节流（防止过度交易）
3. 模拟开平仓（止损/止盈/超时退出）
4. 输出 BacktestResult 供 StandardEvaluator/WFA 消费
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.kernel.types import (
    BacktestResult,
    BacktestTrade,
    BarDetail,
    BarSignal,
    TradingSignal,
)

logger = logging.getLogger(__name__)


# ================================================================
# SignalControl — 信号节流器
# ================================================================


@dataclass
class SignalControl:
    """信号冷却期控制器

    防止同方向信号过度触发。每次触发后进入冷却期。

    Attributes:
        cooldown_bars: 冷却K线数
        min_confidence: 最低置信度阈值
        _last_signal_bar: 上次触发信号的bar索引
        _last_direction: 上次信号方向
    """

    cooldown_bars: int = 8
    min_confidence: float = 0.30
    _last_signal_bar: int = -999
    _last_direction: str = ""

    def should_trigger(
        self,
        bar_index: int,
        signal: TradingSignal,
        confidence: float,
    ) -> bool:
        """判断当前bar是否应触发信号

        Args:
            bar_index: 当前bar索引
            signal: 交易信号
            confidence: 置信度

        Returns:
            True=触发, False=冷却中或置信度不足
        """
        if signal in (TradingSignal.NEUTRAL, TradingSignal.WAIT):
            return False
        if confidence < self.min_confidence:
            return False

        direction = self._signal_direction(signal)

        # 同方向冷却期检查
        if direction == self._last_direction:
            if bar_index - self._last_signal_bar < self.cooldown_bars:
                return False

        return True

    def record_trigger(self, bar_index: int, signal: TradingSignal) -> None:
        """记录信号触发"""
        self._last_signal_bar = bar_index
        self._last_direction = self._signal_direction(signal)

    @staticmethod
    def _signal_direction(signal: TradingSignal) -> str:
        """信号方向"""
        if signal in (TradingSignal.BUY, TradingSignal.STRONG_BUY):
            return "LONG"
        if signal in (TradingSignal.SELL, TradingSignal.STRONG_SELL):
            return "SHORT"
        return "NONE"


# ================================================================
# BarByBarBacktester — 逐Bar回测器
# ================================================================


class BarByBarBacktester:
    """逐Bar回测器

    核心流程：
    1. 创建 WyckoffEngine 实例（注入进化配置）
    2. 逐根H4 K线调用 engine.process_bar()
    3. SignalControl 节流后模拟开仓
    4. 每根bar检查止损/止盈/超时退出
    5. 汇总为 BacktestResult
    """

    def __init__(
        self,
        config: Dict[str, Any],
        warmup_bars: int = 50,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0005,
    ) -> None:
        self.config = config
        self.warmup_bars = warmup_bars
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate

        # 从 config 提取信号控制参数
        sc_cfg = config.get("signal_control", {})
        self.signal_control = SignalControl(
            cooldown_bars=sc_cfg.get("cooldown_bars", 8),
            min_confidence=config.get("threshold_parameters", {}).get(
                "confidence_threshold", 0.30
            ),
        )

        # 回测状态
        self._trades: List[BacktestTrade] = []
        self._position: Optional[Dict[str, Any]] = None
        self._equity = initial_capital
        self._peak_equity = initial_capital
        self._max_drawdown = 0.0
        self._equity_curve: List[float] = []
        self._bar_phases: List[str] = []  # 逐bar威科夫阶段 (A/B/C/D/E/IDLE)
        self._bar_states: List[str] = []  # 逐bar威科夫状态 (SC/SPRING/JOC/...)
        self._bar_details: List[BarDetail] = []  # 逐bar完整状态机快照

        # 退出参数
        self._atr_sl_mult = 2.0  # 止损 = 2x ATR
        self._atr_tp_mult = 3.0  # 止盈 = 3x ATR
        self._max_hold_bars = 50  # 最大持仓K线数

    def run(
        self,
        symbol: str,
        data_dict: Dict[str, pd.DataFrame],
        test_start_idx: Optional[int] = None,
    ) -> BacktestResult:
        """执行逐bar回测

        Args:
            symbol: 交易对
            data_dict: 多TF数据 {"H4": df, "H1": df, ...}
            test_start_idx: 测试段起始索引（WFA用）。
                           若指定，warmup从0到此索引，只统计此后的交易。

        Returns:
            BacktestResult
        """
        from src.plugins.wyckoff_engine.engine import WyckoffEngine

        engine = WyckoffEngine(dict(self.config))
        h4 = data_dict.get("H4")
        if h4 is None or not isinstance(h4, pd.DataFrame):
            return self._empty_result()

        n_bars = len(h4)
        if n_bars < self.warmup_bars + 10:
            return self._empty_result()

        # 确定评估起始位置
        eval_start = test_start_idx if test_start_idx else self.warmup_bars

        # 逐bar遍历
        for i in range(n_bars):
            # 构建截止当前bar的数据快照
            bar_data = self._slice_to_bar(data_dict, h4, i)
            if not bar_data:
                continue

            # 调用引擎
            bar_signal = engine.process_bar(symbol, bar_data)

            # 记录逐bar威科夫阶段和状态
            self._bar_phases.append(bar_signal.phase)
            self._bar_states.append(bar_signal.wyckoff_state)
            self._bar_details.append(
                BarDetail(
                    phase=bar_signal.phase,
                    state=bar_signal.wyckoff_state,
                    confidence=bar_signal.confidence,
                    tr_support=bar_signal.tr_support,
                    tr_resistance=bar_signal.tr_resistance,
                    tr_confidence=bar_signal.tr_confidence,
                    market_regime=bar_signal.market_regime,
                    direction=bar_signal.direction,
                    signal_strength=bar_signal.signal_strength,
                    state_changed=bar_signal.state_changed,
                    previous_state=bar_signal.previous_state,
                    heritage_score=bar_signal.heritage_score,
                    critical_levels=dict(bar_signal.critical_levels),
                )
            )

            # 当前bar的 OHLC
            candle = h4.iloc[i]
            close = float(candle["close"])
            high = float(candle["high"])
            low = float(candle["low"])

            # 持仓中：检查退出条件
            if self._position is not None:
                self._check_exit(i, close, high, low)

            # 预热期不开新仓
            if i < eval_start:
                continue

            # 无持仓时：检查开仓信号
            if self._position is None:
                self._process_signal(i, bar_signal, close, h4)

            # 更新权益曲线
            self._update_equity(close)

        # 强制平仓剩余持仓
        if self._position is not None and n_bars > 0:
            last_close = float(h4.iloc[-1]["close"])
            self._close_position(n_bars - 1, last_close, "END_OF_DATA")

        # 只保留测试段内的交易
        if test_start_idx is not None:
            self._trades = [t for t in self._trades if t.entry_bar >= test_start_idx]

        return self._build_result()

    # 各TF最大保留bar数（引擎不需要全部历史，只需近期数据做技术分析）
    _TF_MAX_BARS = {"D1": 200, "H4": 500, "H1": 500, "M15": 500, "M5": 500}

    def _slice_to_bar(
        self,
        data_dict: Dict[str, pd.DataFrame],
        h4: pd.DataFrame,
        bar_idx: int,
    ) -> Dict[str, pd.DataFrame]:
        """截取到第 bar_idx 根K线为止的多TF数据（限制窗口大小）"""
        if bar_idx < 10:
            return {}

        h4_time = h4.index[bar_idx]
        result: Dict[str, pd.DataFrame] = {}

        for tf_name, tf_df in data_dict.items():
            if not isinstance(tf_df, pd.DataFrame):
                continue
            # 用 searchsorted 快速定位，比 .loc 更高效
            pos = tf_df.index.searchsorted(h4_time, side="right")
            if pos < 10:
                continue
            # 限制窗口大小，避免传入过多数据
            max_bars = self._TF_MAX_BARS.get(tf_name, 500)
            start = max(0, pos - max_bars)
            result[tf_name] = tf_df.iloc[start:pos]

        return result if "H4" in result else {}

    def _process_signal(
        self,
        bar_idx: int,
        bar_signal: BarSignal,
        close: float,
        h4: pd.DataFrame,
    ) -> None:
        """处理引擎信号，决定是否开仓"""
        if not self.signal_control.should_trigger(
            bar_idx, bar_signal.signal, bar_signal.confidence
        ):
            return

        direction = SignalControl._signal_direction(bar_signal.signal)
        if direction == "NONE":
            return

        # 计算ATR止损/止盈
        atr = self._compute_atr(h4, bar_idx)
        if direction == "LONG":
            sl = close - self._atr_sl_mult * atr
            tp = close + self._atr_tp_mult * atr
        else:
            sl = close + self._atr_sl_mult * atr
            tp = close - self._atr_tp_mult * atr

        # 开仓
        self._open_position(
            bar_idx=bar_idx,
            side=direction,
            entry_price=close,
            stop_loss=sl,
            take_profit=tp,
            state=bar_signal.wyckoff_state,
        )
        self.signal_control.record_trigger(bar_idx, bar_signal.signal)

    def _open_position(
        self,
        bar_idx: int,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        state: str,
    ) -> None:
        """模拟开仓"""
        # 考虑滑点
        slippage = entry_price * self.slippage_rate
        if side == "LONG":
            entry_price += slippage
        else:
            entry_price -= slippage

        # 仓位大小：使用全部权益
        position_value = self._equity * 0.95  # 留5%余量
        size = position_value / entry_price if entry_price > 0 else 0.0

        self._position = {
            "entry_bar": bar_idx,
            "side": side,
            "entry_price": entry_price,
            "size": size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_state": state,
            "max_favorable": 0.0,
            "max_adverse": 0.0,
        }

    def _check_exit(self, bar_idx: int, close: float, high: float, low: float) -> None:
        """检查退出条件：止损/止盈/超时"""
        pos = self._position
        if pos is None:
            return

        side = pos["side"]
        sl = pos["stop_loss"]
        tp = pos["take_profit"]
        hold = bar_idx - pos["entry_bar"]

        # 更新最大偏移
        if side == "LONG":
            pos["max_favorable"] = max(pos["max_favorable"], high - pos["entry_price"])
            pos["max_adverse"] = max(pos["max_adverse"], pos["entry_price"] - low)
        else:
            pos["max_favorable"] = max(pos["max_favorable"], pos["entry_price"] - low)
            pos["max_adverse"] = max(pos["max_adverse"], high - pos["entry_price"])

        # 止损检查
        if side == "LONG" and low <= sl:
            self._close_position(bar_idx, sl, "STOP_LOSS")
            return
        if side == "SHORT" and high >= sl:
            self._close_position(bar_idx, sl, "STOP_LOSS")
            return

        # 止盈检查
        if side == "LONG" and high >= tp:
            self._close_position(bar_idx, tp, "TAKE_PROFIT")
            return
        if side == "SHORT" and low <= tp:
            self._close_position(bar_idx, tp, "TAKE_PROFIT")
            return

        # 超时退出
        if hold >= self._max_hold_bars:
            self._close_position(bar_idx, close, "TIMEOUT")

    def _close_position(self, bar_idx: int, exit_price: float, reason: str) -> None:
        """平仓并记录交易"""
        pos = self._position
        if pos is None:
            return

        # 滑点
        slippage = exit_price * self.slippage_rate
        if pos["side"] == "LONG":
            exit_price -= slippage
        else:
            exit_price += slippage

        # 计算PnL
        if pos["side"] == "LONG":
            pnl = (exit_price - pos["entry_price"]) * pos["size"]
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["size"]

        # 佣金
        commission = (
            (pos["entry_price"] + exit_price) * pos["size"] * self.commission_rate
        )
        pnl -= commission

        pnl_pct = (
            pnl / (pos["entry_price"] * pos["size"]) if pos["entry_price"] > 0 else 0.0
        )

        trade = BacktestTrade(
            entry_bar=pos["entry_bar"],
            exit_bar=bar_idx,
            entry_price=pos["entry_price"],
            exit_price=exit_price,
            side=pos["side"],
            size=pos["size"],
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason,
            hold_bars=bar_idx - pos["entry_bar"],
            entry_state=pos["entry_state"],
            max_favorable=pos["max_favorable"],
            max_adverse=pos["max_adverse"],
        )
        self._trades.append(trade)
        self._equity += pnl
        self._position = None

    # ================================================================
    # 辅助方法
    # ================================================================

    def _compute_atr(self, h4: pd.DataFrame, bar_idx: int, period: int = 14) -> float:
        """计算ATR（Average True Range）"""
        start = max(0, bar_idx - period)
        window = h4.iloc[start : bar_idx + 1]
        if len(window) < 2:
            return (
                float(window["high"].iloc[-1] - window["low"].iloc[-1])
                if len(window) > 0
                else 0.001
            )

        high = window["high"].values
        low = window["low"].values
        close = window["close"].values

        tr_list = []
        for j in range(1, len(window)):
            tr = max(
                high[j] - low[j],
                abs(high[j] - close[j - 1]),
                abs(low[j] - close[j - 1]),
            )
            tr_list.append(tr)

        return float(np.mean(tr_list)) if tr_list else 0.001

    def _update_equity(self, close: float) -> None:
        """更新权益曲线和最大回撤"""
        # 当前权益 = 现金 + 持仓市值
        current_equity = self._equity
        if self._position is not None:
            pos = self._position
            if pos["side"] == "LONG":
                unrealized = (close - pos["entry_price"]) * pos["size"]
            else:
                unrealized = (pos["entry_price"] - close) * pos["size"]
            current_equity += unrealized

        self._equity_curve.append(current_equity)

        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        if self._peak_equity > 0:
            dd = (self._peak_equity - current_equity) / self._peak_equity
            self._max_drawdown = max(self._max_drawdown, dd)

    def _build_result(self) -> BacktestResult:
        """构建 BacktestResult"""
        trades = self._trades
        n_trades = len(trades)

        if n_trades == 0:
            return BacktestResult(
                trades=[],
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=self._max_drawdown,
                win_rate=0.0,
                profit_factor=0.0,
                total_trades=0,
                avg_hold_bars=0.0,
                config_hash=self._hash_config(),
                equity_curve=list(self._equity_curve),
                bar_phases=list(self._bar_phases),
                bar_states=list(self._bar_states),
                bar_details=list(self._bar_details),
            )

        # 基础统计
        total_return = (self._equity - self.initial_capital) / self.initial_capital
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        win_rate = len(winning) / n_trades

        total_win = sum(t.pnl for t in winning)
        total_loss = abs(sum(t.pnl for t in losing))
        profit_factor = (
            total_win / total_loss
            if total_loss > 0
            else (2.0 if total_win > 0 else 0.0)
        )

        avg_hold = float(np.mean([t.hold_bars for t in trades]))

        # Sharpe Ratio（基于逐bar权益曲线收益率）
        sharpe = self._compute_sharpe_from_equity()

        return BacktestResult(
            trades=trades,
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=self._max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=n_trades,
            avg_hold_bars=avg_hold,
            config_hash=self._hash_config(),
            equity_curve=list(self._equity_curve),
            bar_phases=list(self._bar_phases),
            bar_states=list(self._bar_states),
            bar_details=list(self._bar_details),
        )

    def _compute_sharpe_from_equity(self) -> float:
        """基于逐bar权益曲线计算 Sharpe Ratio

        使用 per-bar equity returns 而非 per-trade returns，
        更准确反映策略的真实风险调整收益。

        年化因子：H4 bars/year = 6 bars/day * 365 days = 2190
        Sharpe_annual = mean(bar_returns) / std(bar_returns) * sqrt(2190)

        Returns:
            年化 Sharpe Ratio
        """
        if len(self._equity_curve) < 10:
            return 0.0

        equity = np.array(self._equity_curve)
        # 计算 bar-to-bar 收益率
        bar_returns = np.diff(equity) / equity[:-1]

        # 过滤掉 inf/nan
        bar_returns = bar_returns[np.isfinite(bar_returns)]
        if len(bar_returns) < 5:
            return 0.0

        mean_r = np.mean(bar_returns)
        std_r = np.std(bar_returns, ddof=1)

        if std_r < 1e-10:
            return 0.0

        # H4 年化: 6 bars/day * 365 = 2190 bars/year
        annual_factor = 2190.0
        return float(mean_r / std_r * np.sqrt(annual_factor))

    def _hash_config(self) -> str:
        """配置指纹"""
        return hashlib.md5(str(sorted(str(self.config).encode())).encode()).hexdigest()[
            :12
        ]

    def _empty_result(self) -> BacktestResult:
        """空结果（数据不足时返回）"""
        return BacktestResult(
            trades=[],
            total_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=1.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            avg_hold_bars=0.0,
            config_hash=self._hash_config(),
            equity_curve=[],
            bar_phases=[],
            bar_states=[],
            bar_details=[],
        )
