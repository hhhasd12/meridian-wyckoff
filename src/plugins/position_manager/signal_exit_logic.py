"""信号反转出场逻辑 - 基于信号变化判断出场"""

import logging
from typing import Any, Dict, Tuple

from src.kernel.types import TradingSignal
from src.plugins.position_manager.types import (
    ExitCheckResult,
    ExitReason,
    Position,
    PositionSide,
)

logger = logging.getLogger(__name__)


class SignalExitLogic:
    """信号反转出场逻辑
    
    功能：
    1. 检测信号反转（持多仓时出现卖出信号）
    2. 基于威科夫状态变化判断出场
    3. 基于置信度变化判断出场
    """

    DISTRIBUTION_STATES = {"LPSY", "UT", "UTAD", "BC", "AR_DIST"}
    ACCUMULATION_STATES = {"PS", "SC", "AR", "SPRING", "TEST", "SOS", "LPS"}

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.signal_reversal_enabled = config.get("signal_reversal_enabled", True)
        self.min_reversal_confidence = config.get("min_reversal_confidence", 0.6)
        self.wyckoff_exit_enabled = config.get("wyckoff_exit_enabled", True)

    def should_exit_on_signal(
        self,
        position: Position,
        new_signal: TradingSignal,
        new_wyckoff_state: str,
        confidence: float,
    ) -> ExitCheckResult:
        """判断是否应该因信号反转而出场
        
        Args:
            position: 当前持仓
            new_signal: 新的交易信号
            new_wyckoff_state: 新的威科夫状态
            confidence: 新信号的置信度
        
        Returns:
            ExitCheckResult: 出场检查结果
        """
        if position.side == PositionSide.LONG:
            return self._check_long_exit(
                position, new_signal, new_wyckoff_state, confidence
            )
        else:
            return self._check_short_exit(
                position, new_signal, new_wyckoff_state, confidence
            )

    def _check_long_exit(
        self,
        position: Position,
        new_signal: TradingSignal,
        new_wyckoff_state: str,
        confidence: float,
    ) -> ExitCheckResult:
        """检查多头出场条件"""
        if self.signal_reversal_enabled:
            if new_signal in [TradingSignal.SELL, TradingSignal.STRONG_SELL]:
                if confidence >= self.min_reversal_confidence:
                    return ExitCheckResult(
                        should_exit=True,
                        reason=ExitReason.SIGNAL_REVERSAL,
                        message=(
                            f"Signal reversal: LONG position with {new_signal.value} "
                            f"signal (confidence: {confidence:.2f})"
                        ),
                    )
        
        if self.wyckoff_exit_enabled:
            if new_wyckoff_state in self.DISTRIBUTION_STATES:
                if new_wyckoff_state in ["LPSY", "UT", "UTAD"]:
                    return ExitCheckResult(
                        should_exit=True,
                        reason=ExitReason.SIGNAL_REVERSAL,
                        message=(
                            f"Wyckoff distribution detected: {new_wyckoff_state} "
                            f"- exiting LONG position"
                        ),
                    )
        
        return ExitCheckResult(should_exit=False)

    def _check_short_exit(
        self,
        position: Position,
        new_signal: TradingSignal,
        new_wyckoff_state: str,
        confidence: float,
    ) -> ExitCheckResult:
        """检查空头出场条件"""
        if self.signal_reversal_enabled:
            if new_signal in [TradingSignal.BUY, TradingSignal.STRONG_BUY]:
                if confidence >= self.min_reversal_confidence:
                    return ExitCheckResult(
                        should_exit=True,
                        reason=ExitReason.SIGNAL_REVERSAL,
                        message=(
                            f"Signal reversal: SHORT position with {new_signal.value} "
                            f"signal (confidence: {confidence:.2f})"
                        ),
                    )
        
        if self.wyckoff_exit_enabled:
            if new_wyckoff_state in self.ACCUMULATION_STATES:
                if new_wyckoff_state in ["SPRING", "TEST", "SOS"]:
                    return ExitCheckResult(
                        should_exit=True,
                        reason=ExitReason.SIGNAL_REVERSAL,
                        message=(
                            f"Wyckoff accumulation detected: {new_wyckoff_state} "
                            f"- exiting SHORT position"
                        ),
                    )
        
        return ExitCheckResult(should_exit=False)

    def check_timeout_exit(
        self,
        position: Position,
        current_time: Any,
    ) -> ExitCheckResult:
        """检查超时出场
        
        Args:
            position: 当前持仓
            current_time: 当前时间
        
        Returns:
            ExitCheckResult: 出场检查结果
        """
        max_hold_hours = self.config.get("max_hold_hours", 72)
        
        if position.entry_time:
            from datetime import datetime
            if isinstance(current_time, datetime):
                hold_duration = current_time - position.entry_time
                hold_hours = hold_duration.total_seconds() / 3600
                
                if hold_hours >= max_hold_hours:
                    return ExitCheckResult(
                        should_exit=True,
                        reason=ExitReason.TIMEOUT,
                        message=(
                            f"Position timeout: held for {hold_hours:.1f} hours "
                            f"(max: {max_hold_hours})"
                        ),
                    )
        
        return ExitCheckResult(should_exit=False)

    def check_confidence_drop(
        self,
        position: Position,
        current_confidence: float,
    ) -> ExitCheckResult:
        """检查置信度下降出场
        
        Args:
            position: 当前持仓
            current_confidence: 当前置信度
        
        Returns:
            ExitCheckResult: 出场检查结果
        """
        confidence_drop_threshold = self.config.get("confidence_drop_threshold", 0.3)
        min_hold_confidence = self.config.get("min_hold_confidence", 0.4)
        
        confidence_drop = position.signal_confidence - current_confidence
        
        if confidence_drop >= confidence_drop_threshold:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.SIGNAL_REVERSAL,
                message=(
                    f"Confidence dropped significantly: "
                    f"{position.signal_confidence:.2f} -> {current_confidence:.2f}"
                ),
            )
        
        if current_confidence < min_hold_confidence:
            return ExitCheckResult(
                should_exit=True,
                reason=ExitReason.SIGNAL_REVERSAL,
                message=(
                    f"Confidence below minimum: {current_confidence:.2f} < {min_hold_confidence}"
                ),
            )
        
        return ExitCheckResult(should_exit=False)
