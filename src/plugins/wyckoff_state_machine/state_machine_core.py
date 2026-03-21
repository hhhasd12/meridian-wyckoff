"""
威科夫状态机 - 核心基类模块

包含 StateMachineCore 基类的核心逻辑：
- 状态定义（吸筹13节点 + 派发9节点）
- K线处理主循环
- 状态转换引擎
- 并行路径跟踪
- 遗产传递机制

从 wyckoff_state_machine_legacy.py 拆分而来。
"""

import logging
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.kernel.types import (
    StateConfig,
    StateDirection,
    StateEvidence,
    StatePath,
    StateTransition,
    StateTransitionType,
)

logger = logging.getLogger(__name__)

class StateMachineCore:
    """
    威科夫状态机基类

    包含13个吸筹节点和9个派发节点：
    吸筹节点：PS, SC, AR, ST, TEST, UTA, SPRING, SO, LPS, mSOS, MSOS, JOC, BU
    派发节点：PSY, BC, AR, ST, UT, UTAD, LPSY, mSOW, MSOW

    设计特点：
    1. 证据链加权而非硬编码规则
    2. 强度遗产传递机制
    3. 支持非线性状态跳转
    4. 并行路径跟踪与剪枝
    """

    def __init__(self, config: Optional[StateConfig] = None):
        self.config = config or StateConfig()

        # 当前状态
        self.current_state = "IDLE"
        self.state_direction = StateDirection.IDLE

        # 状态历史记录
        self.state_history: list[StateTransition] = []
        self.transition_history: list[StateTransition] = []

        # 状态强度遗产链
        self.heritage_chain: list[dict] = []

        # 并行路径跟踪
        self.alternative_paths: list[StatePath] = []
        self.max_alternative_paths = 3

        # 状态超时计数器
        self.state_timeout_counters: dict[str, int] = {}

        # 关键价格水平记录
        self.critical_price_levels: dict[str, float] = {}

        # 状态定义 - 吸筹阶段（13个节点）
        self.accumulation_states = self._define_accumulation_states()

        # 状态定义 - 派发阶段（9个节点）
        self.distribution_states = self._define_distribution_states()

        # 合并所有状态
        self.all_states = {**self.accumulation_states, **self.distribution_states}

        # 状态置信度记录
        self.state_confidences: dict[str, float] = {}
        for state_name in self.all_states:
            self.state_confidences[state_name] = 0.0

        # 状态强度记录
        self.state_intensities: dict[str, float] = {}
        for state_name in self.all_states:
            self.state_intensities[state_name] = 0.0

    def _define_accumulation_states(self) -> dict[str, dict]:
        """定义吸筹阶段13个节点"""
        return {
            "PS": {
                "description": "初步支撑",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": [],
                "child_states": ["SC", "AR"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_ps",
                "intensity_metrics": ["volume_ratio", "support_bounce"],
            },
            "SC": {
                "description": "抛售高潮",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["PS"],
                "child_states": ["AR", "ST", "TEST"],
                "heritage_rules": {
                    "to_AR": lambda intensity: intensity * 0.8,  # SC强度80%传递给AR
                    "to_ST": lambda intensity: intensity
                    * 1.2,  # SC强度120%传递给ST（强SC需要更严格ST）
                },
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_sc",
                "intensity_metrics": [
                    "volume_ratio",
                    "pin_strength",
                    "effort_result_score",
                ],
            },
            "AR": {
                "description": "自动反弹",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["SC"],
                "child_states": ["ST", "TEST", "UTA"],
                "heritage_rules": {
                    "to_ST": lambda intensity: intensity * 0.7,
                    "to_TEST": lambda intensity: intensity * 0.9,
                },
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_ar",
                "intensity_metrics": ["bounce_percent", "volume_contraction"],
            },
            "ST": {
                "description": "二次测试",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["SC", "AR"],
                "child_states": ["TEST", "SPRING", "SO", "LPS"],
                "heritage_rules": {
                    "required_volume_ratio": lambda heritage: 0.3
                    if heritage > 0.8
                    else 0.6,
                },
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_st",
                "intensity_metrics": ["volume_contraction", "retracement_depth"],
            },
            "TEST": {
                "description": "测试",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["SC", "AR", "ST"],
                "child_states": ["LPS", "mSOS", "SPRING", "SO"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_test",
                "intensity_metrics": ["test_strength", "volume_profile"],
            },
            "UTA": {
                "description": "上冲行为",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["AR"],
                "child_states": ["TEST", "LPS"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_uta",
                "intensity_metrics": ["upthrust_strength", "volume"],
            },
            "SPRING": {
                "description": "弹簧",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["ST", "TEST"],
                "child_states": ["LPS", "mSOS"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_spring",
                "intensity_metrics": ["spring_strength", "recovery_speed"],
            },
            "SO": {
                "description": "震仓",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["ST", "TEST"],
                "child_states": ["LPS", "mSOS"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_so",
                "intensity_metrics": ["shakeout_strength", "recovery"],
            },
            "LPS": {
                "description": "最后支撑点",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["ST", "TEST", "SPRING", "SO"],
                "child_states": ["mSOS", "MSOS"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_lps",
                "intensity_metrics": ["support_strength", "volume_contraction"],
            },
            "mSOS": {
                "description": "局部强势",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["LPS", "TEST"],
                "child_states": ["MSOS", "JOC"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_minor_sos",
                "intensity_metrics": ["strength_indicator", "continuation"],
            },
            "MSOS": {
                "description": "整体强势",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["mSOS", "LPS"],
                "child_states": ["JOC", "BU"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_msos",
                "intensity_metrics": ["strength_indicator", "continuation"],
            },
            "JOC": {
                "description": "突破溪流",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["MSOS", "mSOS"],
                "child_states": ["BU"],
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_joc",
                "intensity_metrics": ["breakout_strength", "volume_expansion"],
            },
            "BU": {
                "description": "回踩确认",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["JOC"],
                "child_states": [],  # 趋势开始，吸筹完成
                "heritage_rules": {},
                "direction": StateDirection.ACCUMULATION,
                "detection_method": "detect_bu",
                "intensity_metrics": ["pullback_strength", "support_hold"],
            },
        }

    def _define_distribution_states(self) -> dict[str, dict]:
        """定义派发阶段9个节点"""
        return {
            "PSY": {
                "description": "初步供应",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": [],
                "child_states": ["BC", "AR_DIST"],
                "heritage_rules": {},
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_psy",
                "intensity_metrics": ["volume_ratio", "resistance_rejection"],
            },
            "BC": {
                "description": "买入高潮",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["PSY"],
                "child_states": ["AR_DIST", "ST_DIST", "UT"],
                "heritage_rules": {
                    "to_AR_DIST": lambda intensity: intensity * 0.8,
                    "to_ST_DIST": lambda intensity: intensity * 1.2,
                },
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_bc",
                "intensity_metrics": [
                    "volume_ratio",
                    "pin_strength",
                    "effort_result_score",
                ],
            },
            "AR_DIST": {
                "description": "自动回落",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["BC"],
                "child_states": ["ST_DIST", "UT", "UTAD"],
                "heritage_rules": {
                    "to_ST_DIST": lambda intensity: intensity * 0.7,
                    "to_UT": lambda intensity: intensity * 0.9,
                },
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_ar_dist",
                "intensity_metrics": ["decline_percent", "volume_contraction"],
            },
            "ST_DIST": {
                "description": "二次测试",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["BC", "AR_DIST"],
                "child_states": ["UT", "UTAD", "LPSY"],
                "heritage_rules": {
                    "required_volume_ratio": lambda heritage: 0.3
                    if heritage > 0.8
                    else 0.6,
                },
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_st_dist",
                "intensity_metrics": ["volume_contraction", "retracement_depth"],
            },
            "UT": {
                "description": "上冲测试",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["BC", "AR_DIST", "ST_DIST"],
                "child_states": ["UTAD", "LPSY"],
                "heritage_rules": {},
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_ut",
                "intensity_metrics": ["upthrust_strength", "volume"],
            },
            "UTAD": {
                "description": "上冲后的派发",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["UT", "AR_DIST"],
                "child_states": ["LPSY"],
                "heritage_rules": {},
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_utad",
                "intensity_metrics": ["distribution_strength", "volume"],
            },
            "LPSY": {
                "description": "最后供应点",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["ST_DIST", "UT", "UTAD"],
                "child_states": ["mSOW", "MSOW"],
                "heritage_rules": {},
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_lpsy",
                "intensity_metrics": ["resistance_strength", "volume_contraction"],
            },
            "mSOW": {
                "description": "局部弱势",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["LPSY"],
                "child_states": ["MSOW"],
                "heritage_rules": {},
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_msow",
                "intensity_metrics": ["weakness_indicator", "continuation"],
            },
            "MSOW": {
                "description": "整体弱势",
                "confidence": 0.0,
                "heritage_score": 0.0,
                "intensity": 0.0,
                "parent_states": ["mSOW", "LPSY"],
                "child_states": [],  # 下跌趋势开始，派发完成
                "heritage_rules": {},
                "direction": StateDirection.DISTRIBUTION,
                "detection_method": "detect_msow",
                "intensity_metrics": ["weakness_indicator", "continuation"],
            },
        }

    def process_candle(self, candle: pd.Series, context: dict[str, Any]) -> str:
        """
        处理单根K线，更新状态机

        Args:
            candle: 单根K线数据（需包含open, high, low, close, volume）
            context: 上下文信息（TR边界、市场体制等）

        Returns:
            更新后的当前状态
        """
        # 1. 检查状态重置条件
        reset_result = self._check_state_reset_conditions(candle, context)
        if reset_result:
            self._perform_state_reset(reset_result)

        # 2. 非线性状态检测
        potential_states = self._detect_nonlinear_states(candle, context)

        # 将所有检测到的置信度/强度写回到 state_confidences/state_intensities
        # 修复：这两个字典从未更新，导致 orchestrator 读出永远是 0.0
        # 先将所有状态的置信度以衰减因子降低（时间衰减）
        _decay = 0.98
        for sn in list(self.state_confidences.keys()):
            self.state_confidences[sn] = self.state_confidences[sn] * _decay
            self.state_intensities[sn] = self.state_intensities[sn] * _decay
        # 再将本轮检测结果写入（取历史与当前的最大值，防止抖动）
        for ps in potential_states:
            sn = ps["state"]
            self.state_confidences[sn] = max(
                self.state_confidences.get(sn, 0.0), ps["confidence"]
            )
            self.state_intensities[sn] = max(
                self.state_intensities.get(sn, 0.0), ps["intensity"]
            )

        # 3. 更新并行路径
        self._update_alternative_paths(potential_states, candle)

        # 4. 选择最佳路径
        best_state = self._select_best_path()

        # 5. 执行状态转换（如果需要）
        if best_state and best_state != self.current_state:
            transition_confidence = self._calculate_transition_confidence(
                self.current_state, best_state, potential_states
            )

            if transition_confidence > self.config.STATE_SWITCH_HYSTERESIS:
                self._execute_state_transition(
                    best_state, transition_confidence, candle
                )

        # 6. 更新状态超时计数器
        self._update_timeout_counters()

        return self.current_state

    def _check_state_reset_conditions(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[dict]:
        """
        检查状态重置条件

        Returns:
            None 或重置信息字典
        """
        reset_conditions = [
            # === 吸筹阶段重置条件 ===
            # 条件1: 价格跌破SC低点 → 所有吸筹状态归零
            {
                "condition": (
                    self.current_state in ["SC", "AR", "ST", "TEST", "SPRING", "SO"]
                    and "SC_LOW" in self.critical_price_levels
                    and candle["close"] < self.critical_price_levels["SC_LOW"]
                ),
                "reason": "PRICE_BREAKS_SC_LOW",
                "new_base_state": "IDLE",
                "reset_scope": "ACCUMULATION",
            },
            # 条件2: 价格突破JOC高点 → 吸筹完成，转为趋势
            {
                "condition": (
                    self.current_state in ["JOC", "BU"]
                    and "JOC_HIGH" in self.critical_price_levels
                    and candle["close"] > self.critical_price_levels["JOC_HIGH"]
                ),
                "reason": "PRICE_CONFIRMS_JOC",
                "new_base_state": "TREND_UP",
                "reset_scope": "ACCUMULATION",
            },
            # 条件3: Spring失败（价格未弹回区间）
            {
                "condition": (
                    self.current_state == "SPRING"
                    and context.get("bars_since_spring", 0)
                    > self.config.SPRING_FAILURE_BARS
                    and "SPRING_LOW" in self.critical_price_levels
                    and candle["close"] < self.critical_price_levels["SPRING_LOW"]
                ),
                "reason": "SPRING_FAILURE",
                "new_base_state": "DOWNTREND",
                "reset_scope": "ACCUMULATION",
            },
            # === 派发阶段重置条件 ===
            # 条件5: 价格突破BC高点上方 → 派发失败，重置派发状态
            {
                "condition": (
                    self.current_state
                    in [
                        "BC",
                        "AR_DIST",
                        "ST_DIST",
                        "UT",
                        "UTAD",
                        "LPSY",
                    ]
                    and "BC_HIGH" in self.critical_price_levels
                    and candle["close"]
                    > self.critical_price_levels["BC_HIGH"] * 1.02
                ),
                "reason": "PRICE_BREAKS_BC_HIGH",
                "new_base_state": "IDLE",
                "reset_scope": "DISTRIBUTION",
            },
            # 条件6: MSOW 确认 → 派发完成，转为下跌趋势
            {
                "condition": (
                    self.current_state in ["MSOW", "mSOW"]
                    and self.state_confidences.get("MSOW", 0.0)
                    > self.config.STATE_MIN_CONFIDENCE * 1.5
                ),
                "reason": "DISTRIBUTION_COMPLETE",
                "new_base_state": "DOWNTREND",
                "reset_scope": "DISTRIBUTION",
            },
            # === 通用重置条件 ===
            # 条件4: 超时强制重置
            {
                "condition": (
                    self.current_state != "IDLE"
                    and self.state_timeout_counters.get(self.current_state, 0)
                    > self.config.STATE_TIMEOUT_BARS
                ),
                "reason": "STATE_TIMEOUT",
                "new_base_state": "IDLE",
                "reset_scope": "ALL",
            },
        ]

        for condition in reset_conditions:
            if condition["condition"]:
                return {
                    "reason": condition["reason"],
                    "new_base_state": condition["new_base_state"],
                    "reset_scope": condition["reset_scope"],
                }

        return None

    def _perform_state_reset(self, reset_info: dict):
        """执行状态重置"""

        # 记录状态转换
        transition = StateTransition(
            from_state=self.current_state,
            to_state=reset_info["new_base_state"],
            timestamp=datetime.now(),
            confidence=1.0,  # 重置具有最高置信度
            transition_type=StateTransitionType.RESET,
            evidences=[],
            heritage_transfer=0.0,
        )

        self.transition_history.append(transition)

        # 更新当前状态
        self.current_state = reset_info["new_base_state"]

        # 根据重置范围清理相关状态
        reset_scope = reset_info["reset_scope"]
        if reset_scope == "ACCUMULATION":
            # 清除所有吸筹相关状态的置信度
            for state_name in self.accumulation_states:
                self.state_confidences[state_name] = 0.0
                self.state_intensities[state_name] = 0.0
        elif reset_scope == "DISTRIBUTION":
            # 清除所有派发相关状态的置信度，保留吸筹侧不受影响
            for state_name in self.distribution_states:
                self.state_confidences[state_name] = 0.0
                self.state_intensities[state_name] = 0.0
        elif reset_scope == "ALL":
            # 清除所有状态
            for state_name in self.all_states:
                self.state_confidences[state_name] = 0.0
                self.state_intensities[state_name] = 0.0

        # 重置超时计数器
        self.state_timeout_counters = {}

        # 清理部分关键价格水平
        if reset_info["reason"] == "PRICE_BREAKS_SC_LOW":
            self.critical_price_levels.pop("SC_LOW", None)
        elif reset_info["reason"] == "PRICE_BREAKS_BC_HIGH":
            self.critical_price_levels.pop("BC_HIGH", None)

        # 更新状态方向
        if (
            reset_info["new_base_state"] == "TREND_UP"
            or reset_info["new_base_state"] == "DOWNTREND"
        ):
            self.state_direction = StateDirection.TRENDING
        else:
            self.state_direction = StateDirection.IDLE

    # PhaseDetector 状态名 → 状态机 all_states 状态名映射
    # PhaseDetector 输出的状态名可能与状态机内部定义不一致，需要对齐
    PHASE_DETECTOR_STATE_MAP: dict[str, str] = {
        "SOS": "mSOS",  # PhaseDetector 的 SOS → 状态机的 mSOS（局部强势信号）
        # AR, ST 保持不变（用于吸筹侧），但不应阻止 AR_DIST, ST_DIST
    }

    # PhaseDetector 检测的吸筹侧状态，不应阻止对应派发侧 Mixin 检测
    _ACCUM_ONLY_STATES: set[str] = {"AR", "ST"}
    _DIST_COUNTERPARTS: dict[str, str] = {
        "AR": "AR_DIST",
        "ST": "ST_DIST",
    }

    def _detect_nonlinear_states(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> list[dict]:
        """
        非线性状态检测：使用新的WyckoffPhaseDetector

        PhaseDetector 与 Mixin 检测器协同工作：
        1. PhaseDetector 先检测，结果经状态名映射后写入
        2. Mixin 检测器补充 PhaseDetector 未覆盖的状态
        3. AR/ST 的 PhaseDetector 结果不阻止 AR_DIST/ST_DIST 的 Mixin 检测

        Returns:
            潜在状态列表
        """
        from src.plugins.pattern_detection.wyckoff_phase_detector import (
            WyckoffPhaseDetector,
        )

        if not hasattr(self, "_phase_detector"):
            self._phase_detector = WyckoffPhaseDetector()

        detection_results = self._phase_detector.detect(
            candle, context, self.current_state
        )

        potential_states = []

        # 记录 PhaseDetector 已检测的状态（映射后的名称）
        phase_detected_states: set[str] = set()

        for raw_state_name, result in detection_results.items():
            if result["confidence"] > self.config.STATE_MIN_CONFIDENCE:
                # 应用状态名映射
                mapped_name = self.PHASE_DETECTOR_STATE_MAP.get(
                    raw_state_name, raw_state_name
                )

                # 跳过映射后在 all_states 中不存在的状态
                state_info = self.all_states.get(mapped_name, {})
                if not state_info:
                    logger.debug(
                        "PhaseDetector 状态 '%s'（映射为 '%s'）"
                        "不在 all_states 中，跳过",
                        raw_state_name,
                        mapped_name,
                    )
                    continue

                potential_states.append(
                    {
                        "state": mapped_name,
                        "confidence": result["confidence"],
                        "intensity": result["intensity"],
                        "evidences": result.get("evidences", []),
                        "direct_jump": True,
                        "direction": state_info.get(
                            "direction", StateDirection.IDLE
                        ),
                    }
                )
                phase_detected_states.add(mapped_name)

        # Mixin 检测器补充检测
        for state_name, state_info in self.all_states.items():
            # 已被 PhaseDetector 检测的状态跳过
            if state_name in phase_detected_states:
                continue

            # 关键修复：AR_DIST/ST_DIST 不应因为 PhaseDetector 检测了
            # AR/ST 而被跳过。只有当 state_name 本身在
            # phase_detected_states 中时才跳过。
            # 原逻辑 `if state_name in detection_results` 会导致
            # PhaseDetector 的 AR 阻止 Mixin 的 AR（正确），
            # 但不会阻止 AR_DIST（也正确，因为 AR_DIST != AR）。
            # 映射后的逻辑同样保持这一行为。

            detection_method_name = state_info.get("detection_method")
            if not detection_method_name:
                continue

            detection_method = getattr(self, detection_method_name, None)
            if detection_method:
                try:
                    result = detection_method(candle, context)
                    if result["confidence"] > self.config.STATE_MIN_CONFIDENCE:
                        potential_states.append(
                            {
                                "state": state_name,
                                "confidence": result["confidence"],
                                "intensity": result["intensity"],
                                "evidences": result.get("evidences", []),
                                "direct_jump": True,
                                "direction": state_info["direction"],
                            }
                        )
                except Exception:
                    continue

        return potential_states

    def _update_alternative_paths(
        self, potential_states: list[dict], candle: pd.Series
    ):
        """更新并行路径跟踪"""
        # 1. 为每个潜在状态创建或更新路径
        for state_info in potential_states:
            state_name = state_info["state"]

            # 查找是否已存在包含该状态的路径
            existing_path = None
            for path in self.alternative_paths:
                if path.current_state == state_name:
                    existing_path = path
                    break

            if existing_path:
                # 更新现有路径
                existing_path.confidence = max(
                    existing_path.confidence, state_info["confidence"]
                )
                existing_path.evidence_strength += len(state_info["evidences"])
                existing_path.age_bars = 0  # 重置年龄
            else:
                # 创建新路径
                if len(self.alternative_paths) >= self.max_alternative_paths:
                    # 移除最旧的路径
                    self.alternative_paths.sort(key=lambda p: p.confidence)
                    self.alternative_paths.pop(0)

                new_path = StatePath(
                    path_id=f"path_{len(self.alternative_paths) + 1:03d}",
                    states=[state_name],
                    current_state=state_name,
                    confidence=state_info["confidence"],
                    age_bars=0,
                    evidence_strength=len(state_info["evidences"]),
                    heritage_score=0.0,
                )
                self.alternative_paths.append(new_path)

        # 2. 更新所有路径的年龄并清理过旧路径
        updated_paths = []
        for path in self.alternative_paths:
            path.increment_age()

            # 保留未过期的路径
            if path.age_bars <= self.config.PATH_MAX_AGE_BARS:
                updated_paths.append(path)

        self.alternative_paths = updated_paths

        # 3. 按置信度排序
        self.alternative_paths.sort(key=lambda p: p.confidence, reverse=True)

    def _select_best_path(self) -> Optional[str]:
        """选择最佳路径"""
        if not self.alternative_paths:
            return None

        # 获取最佳路径
        best_path = self.alternative_paths[0]

        # 检查置信度是否达到阈值
        if best_path.confidence < self.config.PATH_SELECTION_THRESHOLD:
            return None

        # 检查是否有明显优势
        if len(self.alternative_paths) > 1:
            second_best = self.alternative_paths[1]
            advantage = best_path.confidence - second_best.confidence

            if advantage < self.config.STATE_SWITCH_HYSTERESIS:
                # 优势不足，保持当前状态
                return None

        return best_path.current_state

    def _calculate_transition_confidence(
        self, from_state: str, to_state: str, potential_states: list[dict]
    ) -> float:
        """计算状态转换置信度"""
        # 查找目标状态的置信度
        target_state_info = None
        for state_info in potential_states:
            if state_info["state"] == to_state:
                target_state_info = state_info
                break

        if not target_state_info:
            return 0.0

        base_confidence = target_state_info["confidence"]

        # 应用方向切换惩罚
        direction_penalty = self._calculate_direction_penalty(from_state, to_state)

        # 应用遗产传递增益
        heritage_bonus = self._calculate_heritage_bonus(from_state, to_state)

        # 计算最终置信度
        final_confidence = base_confidence * (1 - direction_penalty) + heritage_bonus

        return max(0.0, min(1.0, final_confidence))

    def _calculate_direction_penalty(self, from_state: str, to_state: str) -> float:
        """计算方向切换惩罚"""
        # 状态方向分类
        accumulation_states = list(self.accumulation_states.keys())
        distribution_states = list(self.distribution_states.keys())

        from_is_accum = from_state in accumulation_states
        to_is_accum = to_state in accumulation_states
        from_is_dist = from_state in distribution_states
        to_is_dist = to_state in distribution_states

        # 吸筹←→派发的方向切换（代价最高）
        if (from_is_accum and to_is_dist) or (from_is_dist and to_is_accum):
            return self.config.DIRECTION_SWITCH_PENALTY

        # 同方向内部切换（代价中等）
        if (from_is_accum and to_is_accum) or (from_is_dist and to_is_dist):
            return 0.1  # 10%惩罚

        # 其他情况（如IDLE到任何状态）
        return 0.05

    def _calculate_heritage_bonus(self, from_state: str, to_state: str) -> float:
        """计算遗产传递增益"""
        if from_state not in self.all_states or to_state not in self.all_states:
            return 0.0

        # 检查是否有遗产传递规则
        from_state_info = self.all_states[from_state]
        heritage_rules = from_state_info.get("heritage_rules", {})

        # 查找从from_state到to_state的遗产规则
        rule_key = f"to_{to_state}"
        if rule_key in heritage_rules:
            rule_func = heritage_rules[rule_key]
            from_intensity = self.state_intensities.get(from_state, 0.0)
            return rule_func(from_intensity) * 0.1  # 转换为0-0.1范围的增益

        return 0.0

    def _execute_state_transition(
        self, to_state: str, confidence: float, candle: pd.Series
    ):
        """执行状态转换"""
        from_state = self.current_state

        # 创建转换记录
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(),
            confidence=confidence,
            transition_type=StateTransitionType.NONLINEAR,
            evidences=[],  # 可以添加具体证据
            heritage_transfer=self._calculate_heritage_bonus(from_state, to_state),
        )

        self.transition_history.append(transition)

        # 同步写入 state_history（供检测器查询前驱状态）
        self.state_history.append(transition)
        # 限制 state_history 长度，避免内存泄漏
        _max_state_history = 100
        if len(self.state_history) > _max_state_history:
            self.state_history = self.state_history[-_max_state_history:]

        # 更新当前状态
        self.current_state = to_state

        # 更新状态方向
        if to_state in self.accumulation_states:
            self.state_direction = StateDirection.ACCUMULATION
        elif to_state in self.distribution_states:
            self.state_direction = StateDirection.DISTRIBUTION

        # 记录关键价格水平
        self._record_critical_price_levels(to_state, candle)

        # 重置当前状态的超时计数器
        self.state_timeout_counters[to_state] = 0

    def _record_critical_price_levels(self, state: str, candle: pd.Series):
        """记录关键价格水平"""
        if state == "SC":
            self.critical_price_levels["SC_LOW"] = float(candle["low"])
        elif state == "JOC":
            self.critical_price_levels["JOC_HIGH"] = float(candle["high"])
        elif state == "SPRING":
            self.critical_price_levels["SPRING_LOW"] = float(candle["low"])
        elif state == "BC":
            self.critical_price_levels["BC_HIGH"] = float(candle["high"])

    def _update_timeout_counters(self):
        """更新状态超时计数器"""
        # 增加当前状态的超时计数器
        if self.current_state != "IDLE":
            self.state_timeout_counters[self.current_state] = (
                self.state_timeout_counters.get(self.current_state, 0) + 1
            )

        # 清理长时间未访问的状态
        for state in list(self.state_timeout_counters.keys()):
            if self.state_timeout_counters[state] > self.config.STATE_TIMEOUT_BARS * 2:
                self.state_timeout_counters.pop(state, None)

    def get_state_report(self) -> dict[str, Any]:
        """获取状态机报告"""
        return {
            "current_state": self.current_state,
            "state_direction": self.state_direction.value,
            "state_confidence": self.state_confidences.get(self.current_state, 0.0),
            "state_intensity": self.state_intensities.get(self.current_state, 0.0),
            "alternative_paths_count": len(self.alternative_paths),
            "transition_history_count": len(self.transition_history),
            "critical_price_levels": self.critical_price_levels,
            "timeout_counters": self.state_timeout_counters,
        }



# 延迟导入避免循环依赖，在模块底部组合最终类
def _build_wyckoff_state_machine():
    """构建组合了所有 Mixin 的 WyckoffStateMachine 类"""
    from src.plugins.wyckoff_state_machine.accumulation_detectors import AccumulationDetectorMixin
    from src.plugins.wyckoff_state_machine.distribution_detectors import DistributionDetectorMixin

    class WyckoffStateMachine(AccumulationDetectorMixin, DistributionDetectorMixin, StateMachineCore):
        """威科夫状态机（组合类）

        通过多继承将核心逻辑、吸筹检测、派发检测组合在一起。
        MRO: AccumulationDetectorMixin -> DistributionDetectorMixin -> StateMachineCore
        """
        pass

    return WyckoffStateMachine


# 模块级别的 WyckoffStateMachine 类
WyckoffStateMachine = _build_wyckoff_state_machine()
