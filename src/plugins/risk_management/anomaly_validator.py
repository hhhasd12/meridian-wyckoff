"""
异常数据验证模块
解决异常数据语义误判问题：多源互证（BTC/ETH相关性验证），区分机构异常vs交易所宕机

设计目标：
1. 验证异常数据的真实性，区分真实市场事件和技术问题
2. 使用多源互证：跨市场相关性、多交易所价格一致性
3. 输出异常类型和置信度，供状态机决策使用
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd


class AnomalyType(Enum):
    """异常类型枚举"""

    REAL_MARKET_EVENT = "REAL_MARKET_EVENT"  # 真实市场事件（机构大单、重大新闻等）
    EXCHANGE_OUTAGE = "EXCHANGE_OUTAGE"  # 交易所宕机或技术问题
    DATA_FEED_ISSUE = "DATA_FEED_ISSUE"  # 数据源问题（延迟、丢失）
    CORRELATION_BREAK = "CORRELATION_BREAK"  # 相关性断裂（需进一步分析）
    UNKNOWN = "UNKNOWN"  # 未知类型


class ValidationResult(Enum):
    """验证结果枚举"""

    CONFIRMED = "CONFIRMED"  # 异常确认（真实市场事件）
    REJECTED = "REJECTED"  # 异常驳回（技术问题）
    INCONCLUSIVE = "INCONCLUSIVE"  # 无法确定
    NEED_MANUAL_REVIEW = "NEED_MANUAL_REVIEW"  # 需要人工审核


@dataclass
class AnomalyEvent:
    """异常事件数据结构"""

    anomaly_id: str
    timestamp: datetime
    symbol: str  # 交易对，如"BTC/USDT"
    exchange: str  # 交易所，如"binance"

    # 异常特征
    price_change: Optional[float] = None  # 价格变化百分比
    volume_change: Optional[float] = None  # 成交量变化百分比
    spread_change: Optional[float] = None  # 买卖价差变化
    order_book_imbalance: Optional[float] = None  # 订单簿不平衡度

    # 原始数据
    price: Optional[float] = None
    volume: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None

    # 验证结果
    anomaly_type: AnomalyType = AnomalyType.UNKNOWN
    validation_result: ValidationResult = ValidationResult.INCONCLUSIVE
    confidence: float = 0.0  # 置信度 0-1
    validation_details: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.validation_details is None:
            self.validation_details = {}


@dataclass
class CorrelationData:
    """相关性数据"""

    symbol_pair: str  # 交易对，如"BTC-ETH"
    correlation_30d: float  # 30天相关性
    correlation_7d: float  # 7天相关性
    correlation_1d: float  # 1天相关性
    current_deviation: float  # 当前偏离度（标准差）
    is_breaking: bool  # 是否断裂（偏离超过阈值）
    timestamp: datetime  # 数据时间戳


class AnomalyValidator:
    """
    异常数据验证器

    主要功能：
    1. 多源互证：检查同一资产在不同交易所的价格一致性
    2. 跨市场相关性验证：检查相关资产（如BTC/ETH）的相关性是否断裂
    3. 异常类型判断：区分机构异常vs交易所宕机
    4. 置信度评估：基于证据强度评估异常真实性

    设计原则：
    1. 保守原则：不确定时标记为需要人工审核，避免误判
    2. 实时性：快速验证，不影响交易决策
    3. 可扩展性：支持多种异常类型和数据源
    """

    def __init__(
        self,
        correlation_threshold: float = 2.0,
        price_deviation_threshold: float = 0.02,
        min_confidence: float = 0.7,
    ):
        """
        初始化异常验证器

        Args:
            correlation_threshold: 相关性断裂阈值（标准差倍数）
            price_deviation_threshold: 价格偏离阈值（百分比）
            min_confidence: 最小置信度阈值
        """
        self.correlation_threshold = correlation_threshold
        self.price_deviation_threshold = price_deviation_threshold
        self.min_confidence = min_confidence

        # 相关资产对（可配置）
        self.correlation_pairs = [
            ("BTC/USDT", "ETH/USDT"),  # BTC-ETH相关性
            ("BTC/USDT", "BNB/USDT"),  # BTC-BNB相关性
            ("ETH/USDT", "BNB/USDT"),  # ETH-BNB相关性
        ]

        # 主要交易所列表
        self.major_exchanges = ["binance", "coinbase", "kraken", "okx", "bybit"]

        # 历史数据缓存（用于相关性计算）
        self.historical_data: dict[str, Any] = {}

    def validate_anomaly(
        self,
        anomaly: AnomalyEvent,
        multi_exchange_data: Optional[dict[str, pd.DataFrame]] = None,
        correlation_data: Optional[dict[str, CorrelationData]] = None,
    ) -> AnomalyEvent:
        """
        验证异常事件

        Args:
            anomaly: 异常事件
            multi_exchange_data: 多交易所数据（交易所名称 -> DataFrame）
            correlation_data: 相关性数据

        Returns:
            更新后的异常事件（包含验证结果）
        """
        # 初始化验证详情
        anomaly.validation_details = {}

        # 检查是否有足够数据
        if multi_exchange_data is None and correlation_data is None:
            anomaly.validation_result = ValidationResult.NEED_MANUAL_REVIEW
            anomaly.validation_details["reason"] = "缺乏验证数据"
            return anomaly

        # 执行多源验证
        validation_scores = []
        validation_evidence = []

        # 1. 多交易所价格一致性检查
        if multi_exchange_data:
            exchange_score, exchange_evidence = self._check_multi_exchange_consistency(
                anomaly, multi_exchange_data
            )
            validation_scores.append(exchange_score)
            validation_evidence.extend(exchange_evidence)

        # 2. 跨市场相关性检查
        if correlation_data:
            correlation_score, correlation_evidence = (
                self._check_correlation_consistency(anomaly, correlation_data)
            )
            validation_scores.append(correlation_score)
            validation_evidence.extend(correlation_evidence)

        # 3. 异常特征分析
        feature_score, feature_evidence = self._analyze_anomaly_features(anomaly)
        validation_scores.append(feature_score)
        validation_evidence.extend(feature_evidence)

        # 计算综合置信度
        if validation_scores:
            confidence = float(np.mean(validation_scores))
            anomaly.confidence = confidence

            # 判断验证结果
            if confidence >= self.min_confidence:
                # 高置信度：确认真实市场事件
                anomaly.validation_result = ValidationResult.CONFIRMED
                anomaly.anomaly_type = AnomalyType.REAL_MARKET_EVENT
            elif confidence <= 0.3:
                # 低置信度：驳回（技术问题）
                anomaly.validation_result = ValidationResult.REJECTED
                anomaly.anomaly_type = AnomalyType.EXCHANGE_OUTAGE
            else:
                # 中等置信度：无法确定
                anomaly.validation_result = ValidationResult.INCONCLUSIVE

        # 记录验证证据
        anomaly.validation_details["scores"] = validation_scores
        anomaly.validation_details["evidence"] = validation_evidence
        anomaly.validation_details["threshold"] = self.min_confidence

        return anomaly

    def _check_multi_exchange_consistency(
        self, anomaly: AnomalyEvent, multi_exchange_data: dict[str, pd.DataFrame]
    ) -> tuple[float, list[str]]:
        """
        检查多交易所价格一致性

        Args:
            anomaly: 异常事件
            multi_exchange_data: 多交易所数据

        Returns:
            一致性得分 (0-1) 和证据列表
        """
        scores = []
        evidence = []

        target_exchange = anomaly.exchange
        target_price = anomaly.price

        if target_price is None:
            return 0.5, ["无法检查价格一致性：目标价格缺失"]

        # 收集其他交易所的同期价格
        other_prices = []
        for exchange, df in multi_exchange_data.items():
            if exchange == target_exchange:
                continue

            # 查找最近的时间戳
            try:
                # 简单实现：取最新价格
                latest_price = df["close"].iloc[-1]
                other_prices.append(latest_price)
            except (KeyError, IndexError):
                continue

        if not other_prices:
            return 0.5, ["无其他交易所数据用于对比"]

        # 计算价格偏离度
        other_mean = np.mean(other_prices)
        price_deviation = abs(target_price - other_mean) / other_mean

        # 判断一致性
        if price_deviation <= self.price_deviation_threshold:
            # 价格一致：可能是真实市场事件（所有交易所都反映相同变化）
            score = 0.8
            evidence.append(
                f"价格一致性高：偏离度{price_deviation:.2%} ≤ 阈值{self.price_deviation_threshold:.2%}"
            )
        else:
            # 价格不一致：可能是单个交易所问题
            score = 0.2
            evidence.append(
                f"价格不一致：偏离度{price_deviation:.2%} > 阈值{self.price_deviation_threshold:.2%}"
            )

        scores.append(score)

        # 检查是否有交易所数据缺失
        available_exchanges = len(multi_exchange_data)
        if available_exchanges < 3:
            score = 0.6
            evidence.append(f"数据源不足：仅{available_exchanges}个交易所数据")
            scores.append(score)

        final_score = float(np.mean(scores)) if scores else 0.5
        return final_score, evidence

    def _check_correlation_consistency(
        self, anomaly: AnomalyEvent, correlation_data: dict[str, CorrelationData]
    ) -> tuple[float, list[str]]:
        """
        检查跨市场相关性

        Args:
            anomaly: 异常事件
            correlation_data: 相关性数据

        Returns:
            相关性得分 (0-1) 和证据列表
        """
        scores = []
        evidence = []

        target_symbol = anomaly.symbol
        target_timestamp = anomaly.timestamp

        # 查找相关资产对
        for pair in self.correlation_pairs:
            if target_symbol in pair:
                # 找到相关资产
                pair_key = f"{pair[0]}-{pair[1]}"

                if pair_key in correlation_data:
                    corr_data = correlation_data[pair_key]

                    # 检查时间对齐：确保相关性数据与异常事件时间匹配
                    if hasattr(corr_data, "timestamp"):
                        time_diff = abs(
                            (target_timestamp - corr_data.timestamp).total_seconds()
                            / 3600
                        )
                        if time_diff > 24:
                            evidence.append(
                                f"相关性数据过时：{pair_key} 时间差{time_diff:.1f}小时"
                            )
                            scores.append(0.3)
                            continue

                    # 检查相关性是否断裂
                    if corr_data.is_breaking:
                        # 相关性断裂：可能是系统性风险或真实市场事件
                        score = 0.8
                        evidence.append(
                            f"相关性断裂：{pair_key} 偏离度{corr_data.current_deviation:.1f}σ "
                            f"(30d相关性:{corr_data.correlation_30d:.2f})"
                        )
                    else:
                        # 相关性正常：异常可能是个别资产问题
                        score = 0.3
                        evidence.append(
                            f"相关性正常：{pair_key} 偏离度{corr_data.current_deviation:.1f}σ "
                            f"(30d相关性:{corr_data.correlation_30d:.2f})"
                        )

                    # 根据相关性强度调整分数
                    if corr_data.correlation_30d > 0.7:
                        score *= 1.2  # 强相关性，增加权重
                        evidence.append(
                            f"强相关性：30天相关性{corr_data.correlation_30d:.2f}"
                        )
                    elif corr_data.correlation_30d < 0.3:
                        score *= 0.8  # 弱相关性，降低权重
                        evidence.append(
                            f"弱相关性：30天相关性{corr_data.correlation_30d:.2f}"
                        )

                    # 限制分数在0-1范围内
                    score = max(0.0, min(1.0, score))
                    scores.append(score)

        if not scores:
            return 0.5, ["无相关资产数据用于验证"]

        final_score = float(np.mean(scores)) if scores else 0.5
        return final_score, evidence

    def _analyze_anomaly_features(
        self, anomaly: AnomalyEvent
    ) -> tuple[float, list[str]]:
        """
        分析异常特征

        Args:
            anomaly: 异常事件

        Returns:
            特征分析得分 (0-1) 和证据列表
        """
        scores = []
        evidence = []

        # 1. 价格变化分析
        if anomaly.price_change is not None:
            abs_price_change = abs(anomaly.price_change)
            if abs_price_change > 0.05:  # 5%以上大幅波动
                score = 0.8
                evidence.append(f"大幅价格波动：{anomaly.price_change:.2%}")
            elif abs_price_change > 0.02:  # 2-5%中度波动
                score = 0.6
                evidence.append(f"中度价格波动：{anomaly.price_change:.2%}")
            else:
                score = 0.4
                evidence.append(f"小幅价格波动：{anomaly.price_change:.2%}")
            scores.append(score)

        # 2. 成交量分析
        if anomaly.volume_change is not None:
            if anomaly.volume_change > 3.0:  # 成交量增长3倍以上
                score = 0.9
                evidence.append(f"成交量激增：{anomaly.volume_change:.1f}倍")
            elif anomaly.volume_change > 1.5:  # 成交量增长1.5倍以上
                score = 0.7
                evidence.append(f"成交量增加：{anomaly.volume_change:.1f}倍")
            else:
                score = 0.5
                evidence.append(f"成交量正常：{anomaly.volume_change:.1f}倍")
            scores.append(score)

        # 3. 订单簿不平衡度分析
        if anomaly.order_book_imbalance is not None:
            abs_imbalance = abs(anomaly.order_book_imbalance)
            if abs_imbalance > 0.3:  # 严重不平衡
                score = 0.8
                evidence.append(f"订单簿严重不平衡：{anomaly.order_book_imbalance:.2f}")
            elif abs_imbalance > 0.1:  # 中等不平衡
                score = 0.6
                evidence.append(f"订单簿不平衡：{anomaly.order_book_imbalance:.2f}")
            else:
                score = 0.4
                evidence.append(f"订单簿相对平衡：{anomaly.order_book_imbalance:.2f}")
            scores.append(score)

        if not scores:
            return 0.5, ["异常特征数据不足"]

        final_score = float(np.mean(scores)) if scores else 0.5
        return final_score, evidence

    def calculate_correlation(
        self,
        symbol1_data: pd.DataFrame,
        symbol2_data: pd.DataFrame,
        window_days: int = 30,
    ) -> CorrelationData:
        """
        计算两个资产的相关性

        Args:
            symbol1_data: 资产1数据（需包含'close'列）
            symbol2_data: 资产2数据（需包含'close'列）
            window_days: 计算窗口（天）

        Returns:
            相关性数据对象
        """
        # 确保时间对齐
        merged_data = pd.merge(
            symbol1_data[["close"]],
            symbol2_data[["close"]],
            left_index=True,
            right_index=True,
            suffixes=("_1", "_2"),
        )

        if len(merged_data) < window_days:
            # 数据不足
            return CorrelationData(
                symbol_pair=f"{symbol1_data.name}-{symbol2_data.name}",
                correlation_30d=0.0,
                correlation_7d=0.0,
                correlation_1d=0.0,
                current_deviation=0.0,
                is_breaking=False,
                timestamp=datetime.now(),
            )

        # 计算收益率
        returns_1 = merged_data["close_1"].pct_change().dropna()
        returns_2 = merged_data["close_2"].pct_change().dropna()

        # 对齐收益率数据
        aligned_returns = pd.concat([returns_1, returns_2], axis=1).dropna()
        returns_1_aligned = aligned_returns.iloc[:, 0]
        returns_2_aligned = aligned_returns.iloc[:, 1]

        # 计算不同时间窗口的相关性
        min_len = len(returns_1_aligned)
        window_30d = min(30, min_len)
        window_7d = min(7, min_len)
        window_1d = min(1, min_len)

        corr_30d = returns_1_aligned.iloc[-window_30d:].corr(
            returns_2_aligned.iloc[-window_30d:]
        )
        corr_7d = returns_1_aligned.iloc[-window_7d:].corr(
            returns_2_aligned.iloc[-window_7d:]
        )
        corr_1d = returns_1_aligned.iloc[-window_1d:].corr(
            returns_2_aligned.iloc[-window_1d:]
        )

        # 计算当前偏离度（Z-score）
        if window_30d >= 10:
            # 计算历史相关性均值和标准差
            rolling_corr = returns_1_aligned.rolling(window=30).corr(returns_2_aligned)
            historical_mean = rolling_corr.mean()
            historical_std = rolling_corr.std()

            if historical_std > 0:
                current_deviation = (corr_30d - historical_mean) / historical_std
            else:
                current_deviation = 0.0
        else:
            current_deviation = 0.0

        is_breaking = abs(current_deviation) > self.correlation_threshold

        # 获取最新时间戳
        latest_timestamp = merged_data.index[-1]
        if isinstance(latest_timestamp, pd.Timestamp):
            timestamp = latest_timestamp.to_pydatetime()
        else:
            timestamp = datetime.now()

        return CorrelationData(
            symbol_pair=f"{symbol1_data.name}-{symbol2_data.name}",
            correlation_30d=corr_30d,
            correlation_7d=corr_7d,
            correlation_1d=corr_1d,
            current_deviation=current_deviation,
            is_breaking=is_breaking,
            timestamp=timestamp,
        )

    def validate_with_btc_eth_cross(
        self,
        anomaly: AnomalyEvent,
        btc_data: pd.DataFrame,
        eth_data: pd.DataFrame,
    ) -> AnomalyEvent:
        """
        使用 BTC/ETH 跨品种互证验证异常事件。

        计算 BTC-ETH 实时相关性，注入 validate_anomaly 进行完整验证。

        Args:
            anomaly: 待验证的异常事件
            btc_data: BTC/USDT 的 OHLCV DataFrame（含 'close' 列）
            eth_data: ETH/USDT 的 OHLCV DataFrame（含 'close' 列）

        Returns:
            填充了 validation_result / anomaly_type / confidence 的异常事件
        """
        btc_named = btc_data["close"].rename("BTC/USDT")
        eth_named = eth_data["close"].rename("ETH/USDT")

        btc_df = btc_data.copy()
        btc_df.name = "BTC/USDT"  # type: ignore[attr-defined]
        eth_df = eth_data.copy()
        eth_df.name = "ETH/USDT"  # type: ignore[attr-defined]

        # 复用现有 calculate_correlation 方法
        btc_df_for_corr = pd.DataFrame({"close": btc_named})
        eth_df_for_corr = pd.DataFrame({"close": eth_named})
        btc_df_for_corr.name = "BTC/USDT"  # type: ignore[attr-defined]
        eth_df_for_corr.name = "ETH/USDT"  # type: ignore[attr-defined]

        corr = self.calculate_correlation(btc_df_for_corr, eth_df_for_corr)
        correlation_data = {"BTC/USDT-ETH/USDT": corr}

        return self.validate_anomaly(anomaly, correlation_data=correlation_data)
if __name__ == "__main__":
    # 创建验证器实例
    validator = AnomalyValidator()

    # 创建模拟异常事件
    anomaly = AnomalyEvent(
        anomaly_id="test_001",
        timestamp=datetime.now(),
        symbol="BTC/USDT",
        exchange="binance",
        price_change=0.08,  # 8%价格上涨
        volume_change=4.2,  # 成交量增加4.2倍
        price=45000.0,
        volume=1200.0,
    )

    # 模拟多交易所数据
    multi_exchange_data = {
        "binance": pd.DataFrame(
            {"close": [44800, 44900, 45000]},
            index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
        ),
        "coinbase": pd.DataFrame(
            {"close": [44750, 44850, 44950]},
            index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
        ),
        "kraken": pd.DataFrame(
            {"close": [44820, 44920, 45020]},
            index=pd.date_range(end=datetime.now(), periods=3, freq="1h"),
        ),
    }

    # 模拟相关性数据
    correlation_data = {
        "BTC/USDT-ETH/USDT": CorrelationData(
            symbol_pair="BTC/USDT-ETH/USDT",
            correlation_30d=0.85,
            correlation_7d=0.82,
            correlation_1d=0.78,
            current_deviation=1.2,
            is_breaking=False,
            timestamp=datetime.now(),
        )
    }

    # 验证异常
    validated_anomaly = validator.validate_anomaly(
        anomaly, multi_exchange_data, correlation_data
    )

