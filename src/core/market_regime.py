"""
市场体制（Regime）独立检测模块
解决循环依赖问题：仅基于ATR、ADX、历史波动率判断市场体制，不依赖K线形态识别
"""

from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class MarketRegime(Enum):
    """市场体制枚举"""

    TRENDING = "TRENDING"  # 趋势市
    RANGING = "RANGING"  # 盘整市
    VOLATILE = "VOLATILE"  # 高波动市（无明确趋势）
    UNKNOWN = "UNKNOWN"  # 未知（数据不足）


class RegimeDetector:
    """
    市场体制检测器 - 独立模块，打破循环依赖

    设计原则：
    1. 无状态启动：初始化时不需要历史K线形态信息
    2. 仅基于技术指标：ATR、ADX、历史波动率
    3. 不与K线形态识别相互依赖
    4. 输出稳定的市场体制判断
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化Regime检测器

        Args:
            config: 配置字典，包含以下参数：
                - atr_period: ATR计算周期（默认14）
                - adx_period: ADX计算周期（默认14）
                - volatility_lookback: 波动率回看周期（默认20）
                - trending_threshold: 趋势阈值（ADX > 25）
                - volatility_threshold: 高波动阈值（ATR/均值 > 1.5）
        """
        self.config = config or {}
        self.atr_period = self.config.get("atr_period", 14)
        self.adx_period = self.config.get("adx_period", 14)
        self.volatility_lookback = self.config.get("volatility_lookback", 20)
        self.trending_threshold = self.config.get("trending_threshold", 25.0)
        self.volatility_threshold = self.config.get("volatility_threshold", 1.5)

        # 状态跟踪
        self.regime_history: list[tuple[pd.Timestamp, MarketRegime, float]] = []
        self.current_regime = MarketRegime.UNKNOWN
        self.confidence = 0.0

    def detect_regime(self, df: pd.DataFrame) -> dict:
        """
        检测市场体制

        Args:
            df: 包含OHLCV数据的DataFrame，必须包含以下列：
                - 'open', 'high', 'low', 'close', 'volume'

        Returns:
            Dict包含：
                - regime: MarketRegime枚举
                - confidence: 置信度 [0, 1]
                - metrics: 各项指标值
                - reasons: 判断理由
        """
        if len(df) < max(self.atr_period, self.adx_period, self.volatility_lookback):
            return {
                "regime": MarketRegime.UNKNOWN,
                "confidence": 0.0,
                "metrics": {},
                "reasons": ["数据不足，无法判断体制"],
            }

        # 计算技术指标
        metrics = self._calculate_metrics(df)

        # 判断市场体制
        regime, confidence, reasons = self._judge_regime(metrics)

        # 更新状态
        self.current_regime = regime
        self.confidence = confidence
        self.regime_history.append((df.index[-1], regime, confidence))  # type: ignore[arg-type]

        # 限制历史记录长度
        if len(self.regime_history) > 1000:
            self.regime_history = self.regime_history[-1000:]

        return {
            "regime": regime,
            "confidence": confidence,
            "metrics": metrics,
            "reasons": reasons,
            "timestamp": df.index[-1],
        }

    def _calculate_metrics(self, df: pd.DataFrame) -> dict:
        """计算所有技术指标"""
        metrics = {}

        # 1. 计算ATR（平均真实波幅）
        metrics["atr"] = self._calculate_atr(df)
        metrics["atr_mean"] = metrics["atr"].mean()
        metrics["atr_current"] = metrics["atr"].iloc[-1]

        # 2. 计算ADX（平均趋向指数）
        metrics["adx"] = self._calculate_adx(df)
        metrics["adx_current"] = metrics["adx"].iloc[-1]

        # 3. 计算历史波动率
        metrics["volatility"] = self._calculate_volatility(df)
        metrics["volatility_current"] = metrics["volatility"].iloc[-1]
        metrics["volatility_mean"] = metrics["volatility"].mean()

        # 4. 计算ATR相对比率（当前ATR / 平均ATR）
        if metrics["atr_mean"] > 0:
            metrics["atr_ratio"] = metrics["atr_current"] / metrics["atr_mean"]
        else:
            metrics["atr_ratio"] = 1.0

        # 5. 计算波动率相对比率
        if metrics["volatility_mean"] > 0:
            metrics["volatility_ratio"] = (
                metrics["volatility_current"] / metrics["volatility_mean"]
            )
        else:
            metrics["volatility_ratio"] = 1.0

        return metrics

    def _calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """计算ATR（简化版，实际项目应使用TA-Lib）"""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # 真实波幅
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR（简单移动平均）
        return tr.rolling(window=self.atr_period).mean()


    def _calculate_adx(self, df: pd.DataFrame) -> pd.Series:
        """计算ADX（简化版，实际项目应使用TA-Lib）"""
        high = df["high"]
        low = df["low"]
        df["close"]

        # 计算+DI和-DI（简化）
        up_move = high.diff()
        down_move = low.diff().abs() * -1

        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)

        tr = self._calculate_atr(df) * np.sqrt(self.atr_period)  # 简化

        plus_di = 100 * plus_dm.rolling(window=self.adx_period).mean() / tr
        minus_di = 100 * minus_dm.rolling(window=self.adx_period).mean() / tr

        # DX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)

        # ADX
        return dx.rolling(window=self.adx_period).mean()


    def _calculate_volatility(self, df: pd.DataFrame) -> pd.Series:
        """计算历史波动率（收盘价对数收益率的标准差）"""
        returns = np.log(df["close"] / df["close"].shift(1))
        return returns.rolling(window=self.volatility_lookback).std() * np.sqrt(
            252
        )  # 年化


    def _judge_regime(self, metrics: dict) -> tuple[MarketRegime, float, list[str]]:
        """根据指标判断市场体制"""
        reasons = []
        scores = {
            MarketRegime.TRENDING: 0.0,
            MarketRegime.RANGING: 0.0,
            MarketRegime.VOLATILE: 0.0,
        }

        # 1. 趋势市判断
        if metrics["adx_current"] > self.trending_threshold:
            trend_score = min(
                metrics["adx_current"] / 50.0, 1.0
            )  # ADX 25-50为中等趋势，>50为强趋势
            scores[MarketRegime.TRENDING] += trend_score * 0.7
            reasons.append(
                f"ADX={metrics['adx_current']:.1f}>={self.trending_threshold}，趋势明显"
            )

        # 2. 高波动市判断
        if metrics["atr_ratio"] > self.volatility_threshold:
            volatility_score = min((metrics["atr_ratio"] - 1.0) / 2.0, 1.0)  # 1.5-3.5倍
            scores[MarketRegime.VOLATILE] += volatility_score * 0.8
            reasons.append(
                f"ATR比率={metrics['atr_ratio']:.2f}>={self.volatility_threshold}，波动剧烈"
            )

        # 3. 盘整市判断（默认情况）
        # 如果既不是强趋势也不是高波动，则可能是盘整
        if scores[MarketRegime.TRENDING] < 0.3 and scores[MarketRegime.VOLATILE] < 0.3:
            # ADX低且波动率正常
            if metrics["adx_current"] < 20 and 0.8 < metrics["atr_ratio"] < 1.2:
                ranging_score = (
                    20 - metrics["adx_current"]
                ) / 20.0  # ADX越低，盘整可能性越高
                scores[MarketRegime.RANGING] += ranging_score * 0.9
                reasons.append(
                    f"ADX={metrics['adx_current']:.1f}<20且ATR比率正常，可能盘整"
                )

        # 4. 特殊情况：高波动趋势市
        if scores[MarketRegime.TRENDING] > 0.5 and scores[MarketRegime.VOLATILE] > 0.5:
            # 既是趋势又是高波动，优先标记为趋势市（但记录高波动特征）
            reasons.append("高波动趋势市")

        # 确定最高分的体制
        if not any(scores.values()):
            return MarketRegime.UNKNOWN, 0.0, ["指标不足，无法判断"]

        best_regime = max(scores, key=lambda k: scores.get(k, 0))  # type: ignore[arg-type]
        best_score = scores[best_regime]

        # 计算置信度
        total_score = sum(scores.values())
        confidence = best_score / total_score if total_score > 0 else 0.0

        # 如果置信度过低，返回UNKNOWN
        if confidence < 0.4:
            return MarketRegime.UNKNOWN, confidence, ["置信度过低", *reasons]

        return best_regime, confidence, reasons

    def get_regime_history(
        self, n: int = 50
    ) -> list[tuple[pd.Timestamp, MarketRegime, float]]:
        """获取最近N次体制判断历史"""
        return self.regime_history[-n:] if n > 0 else self.regime_history

    def get_current_regime(self) -> dict:
        """获取当前体制"""
        return {
            "regime": self.current_regime,
            "confidence": self.confidence,
            "timestamp": self.regime_history[-1][0] if self.regime_history else None,
        }


# 简单使用示例
if __name__ == "__main__":
    # 创建模拟数据
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    high = close + np.random.rand(100) * 2
    low = close - np.random.rand(100) * 2
    open_price = np.roll(close, 1) + np.random.randn(100) * 0.1  # type: ignore[attr-defined]
    volume = np.random.rand(100) * 1000 + 500

    df = pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )

    # 检测市场体制
    detector = RegimeDetector()
    result = detector.detect_regime(df)

