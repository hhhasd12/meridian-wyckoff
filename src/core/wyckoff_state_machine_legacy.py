"""
威科夫状态机模块
实现13个吸筹节点和9个派发节点的辩证状态转换逻辑

设计原则：
1. 状态证据链加权而非硬编码规则
2. 支持非线性跳转和状态重置
3. 强度遗产传递机制（heritage_score）
4. 并行路径跟踪与概率剪枝
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class StateDirection(Enum):
    """状态方向枚举"""

    ACCUMULATION = "ACCUMULATION"  # 吸筹阶段
    DISTRIBUTION = "DISTRIBUTION"  # 派发阶段
    TRENDING = "TRENDING"  # 趋势阶段
    IDLE = "IDLE"  # 空闲状态


class StateTransitionType(Enum):
    """状态转换类型枚举"""

    LINEAR = "LINEAR"  # 线性转换（按标准顺序）
    NONLINEAR = "NONLINEAR"  # 非线性跳转
    RESET = "RESET"  # 状态重置
    PARALLEL = "PARALLEL"  # 并行路径


@dataclass
class StateEvidence:
    """状态证据"""

    evidence_type: str  # 证据类型，如'volume_ratio', 'pin_strength', 'bounce_percent'等
    value: float  # 证据值
    confidence: float  # 证据置信度 0-1
    weight: float  # 证据权重 0-1
    description: str  # 证据描述


@dataclass
class StateDetectionResult:
    """状态检测结果"""

    state_name: str
    confidence: float  # 总体置信度 0-1
    intensity: float  # 状态强度 0-1
    evidences: list[StateEvidence]  # 证据列表
    heritage_score: float = 0.0  # 遗产分数
    timestamp: Optional[datetime] = None  # 检测时间戳

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class StateTransition:
    """状态转换记录"""

    from_state: str
    to_state: str
    timestamp: datetime
    confidence: float  # 转换置信度
    transition_type: StateTransitionType
    evidences: list[StateEvidence]  # 触发转换的证据
    heritage_transfer: float = 0.0  # 遗产传递量


@dataclass
class StatePath:
    """并行状态路径"""

    path_id: str
    states: list[str]  # 路径上的状态序列
    current_state: str
    confidence: float  # 路径置信度
    age_bars: int = 0  # 路径年龄（K线数）
    evidence_strength: float = 0.0  # 证据强度总和
    heritage_score: float = 0.0  # 路径遗产分数

    def add_state(self, state_name: str, confidence: float):
        """添加状态到路径"""
        self.states.append(state_name)
        self.current_state = state_name
        self.confidence = confidence

    def increment_age(self):
        """增加路径年龄"""
        self.age_bars += 1


class StateConfig:
    """状态机配置"""

    def __init__(self):
        # 状态重置参数
        self.SPRING_FAILURE_BARS = 5  # Spring失败判定所需K线数
        self.STATE_TIMEOUT_BARS = 20  # 状态超时判定所需K线数

        # 非线性检测参数
        self.STATE_MIN_CONFIDENCE = 0.6  # 状态最小置信度
        self.PATH_MAX_AGE_BARS = 10  # 路径最大年龄（K线数）
        self.PATH_SELECTION_THRESHOLD = 0.65  # 路径选择阈值

        # 状态切换滞后性参数（防止"精神分裂"）
        self.STATE_SWITCH_HYSTERESIS = 0.15  # 15%相对优势才切换
        self.DIRECTION_SWITCH_PENALTY = 0.3  # 吸筹←→派发方向切换惩罚

        # 自动进化标识
        self._evolution_params = [
            "SPRING_FAILURE_BARS",
            "STATE_TIMEOUT_BARS",
            "STATE_MIN_CONFIDENCE",
            "PATH_SELECTION_THRESHOLD",
            "STATE_SWITCH_HYSTERESIS",
            "DIRECTION_SWITCH_PENALTY",
        ]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def update_from_dict(self, config_dict: dict[str, Any]):
        """从字典更新配置"""
        for key, value in config_dict.items():
            if hasattr(self, key) and key in self._evolution_params:
                setattr(self, key, value)


class WyckoffStateMachine:
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
                "detection_method": "detect_msos",
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

        # 更新状态方向
        if reset_info["new_base_state"] == "TREND_UP" or reset_info["new_base_state"] == "DOWNTREND":
            self.state_direction = StateDirection.TRENDING
        else:
            self.state_direction = StateDirection.IDLE

    def _detect_nonlinear_states(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> list[dict]:
        """
        非线性状态检测：允许从任何状态跳转到任何其他状态

        Returns:
            潜在状态列表
        """
        potential_states = []

        # 独立检测每个状态的可能性（不依赖前驱状态）
        for state_name, state_info in self.all_states.items():
            # 获取检测方法名称
            detection_method_name = state_info.get("detection_method")
            if not detection_method_name:
                continue

            # 尝试调用检测方法
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
                    # 检测方法可能未完全实现，跳过
                    continue

        return potential_states

    def _update_alternative_paths(
        self, potential_states: list[dict], candle: pd.Series
    ):
        """更新并行路径跟踪"""
        datetime.now()

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

    # ===== 状态检测方法（占位符，需要后续实现） =====

    # ===== SC检测辅助方法 =====

    def _analyze_volume_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析成交量特征以检测SC

        SC成交量特征：
        1. 成交量显著高于平均水平（恐慌性抛售）
        2. 可能伴随成交量尖峰

        Returns:
            成交量证据，或None（如果无法分析）
        """
        if "volume" not in candle:
            return None

        volume = float(candle["volume"])

        # 获取历史成交量上下文
        avg_volume = context.get("avg_volume_20", volume * 1.5)  # 默认值
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

        # 计算成交量置信度
        confidence = min(1.0, volume_ratio / 3.0)  # 3倍成交量达到最大置信度

        return StateEvidence(
            evidence_type="volume_ratio",
            value=volume_ratio,
            confidence=confidence,
            weight=0.8,  # 成交量在SC检测中权重较高
            description=f"成交量比率: {volume_ratio:.2f}x (当前: {volume:.0f}, 平均: {avg_volume:.0f})",
        )


    def _analyze_price_action_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析价格行为特征以检测SC

        SC价格特征：
        1. 长阴线或长下影线
        2. 大幅下跌
        3. 可能的针形K线

        Returns:
            价格行为证据，或None（如果无法分析）
        """
        required_fields = ["open", "high", "low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # 1. 计算价格变动幅度
        price_range = high - low
        if price_range == 0:
            return None

        # 计算下跌幅度（如果是阴线）
        is_bearish = close < open_price
        bearish_strength = (open_price - close) / price_range if is_bearish else 0.0

        # 2. 计算下影线比例（针形特征）
        lower_shadow_ratio = (
            (min(open_price, close) - low) / price_range if price_range > 0 else 0.0
        )

        # 3. 计算整体波动率（相对于ATR）
        atr = context.get("atr_14", price_range * 2)  # 默认值
        volatility_ratio = price_range / atr if atr > 0 else 1.0

        # 综合评分：SC通常有较强的下跌和长下影线
        price_score = (
            bearish_strength * 0.4 + lower_shadow_ratio * 0.4 + volatility_ratio * 0.2
        )

        return StateEvidence(
            evidence_type="price_action",
            value=price_score,
            confidence=min(1.0, price_score * 1.5),  # 调整置信度范围
            weight=0.7,
            description=f"价格行为评分: {price_score:.2f} (下跌强度: {bearish_strength:.2f}, 下影线: {lower_shadow_ratio:.2f}, 波动率: {volatility_ratio:.2f}x)",
        )


    def _analyze_context_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析市场上下文以检测SC

        SC上下文特征：
        1. 出现在下跌趋势后
        2. 可能接近支撑位
        3. 市场体制可能是下跌或盘整

        Returns:
            上下文证据，或None（如果无法分析）
        """
        # 检查市场体制
        market_regime = context.get("market_regime", "UNKNOWN")

        # SC通常在下跌趋势或盘整底部出现
        regime_score = 0.5  # 默认

        if market_regime in ["DOWNTREND", "BEARISH", "ACCUMULATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.2

        # 检查是否接近支撑位
        support_level = context.get("support_level")
        current_price = float(candle["close"])

        support_score = 0.5
        if support_level is not None:
            distance_pct = abs(current_price - support_level) / support_level * 100
            if distance_pct < 2.0:  # 接近支撑位
                support_score = 0.8

        # 综合上下文评分
        context_score = regime_score * 0.6 + support_score * 0.4

        return StateEvidence(
            evidence_type="market_context",
            value=context_score,
            confidence=context_score,
            weight=0.5,
            description=f"市场上下文评分: {context_score:.2f} (体制: {market_regime}, 接近支撑: {support_score:.2f})",
        )


    def _analyze_trend_for_sc(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析趋势特征以检测SC

        SC趋势特征：
        1. 出现在下跌趋势后
        2. 可能伴随趋势加速

        Returns:
            趋势证据，或None（如果无法分析）
        """
        # 获取趋势信息
        trend_direction = context.get("trend_direction", "UNKNOWN")
        trend_strength = context.get("trend_strength", 0.5)

        # SC通常出现在下跌趋势中
        trend_score = 0.5  # 默认

        if trend_direction == "DOWN":
            trend_score = 0.7 + trend_strength * 0.3  # 下跌趋势越强，SC可能性越高
        elif trend_direction == "UP":
            trend_score = 0.3 - trend_strength * 0.2  # 上涨趋势中SC可能性低

        return StateEvidence(
            evidence_type="trend_alignment",
            value=trend_score,
            confidence=trend_score,
            weight=0.4,
            description=f"趋势对齐评分: {trend_score:.2f} (方向: {trend_direction}, 强度: {trend_strength:.2f})",
        )


    def detect_ps(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测初步支撑

        PS特征：
        1. 下跌趋势中首次出现支撑
        2. 成交量可能放大（初期买盘进入）
        3. 价格出现反弹迹象
        4. 可能形成锤子线或刺透形态

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：40%）
        # 检查是否为支撑形态（如锤子线、刺透形态等）
        is_bullish_reversal = False
        # 简单判断：收盘价高于开盘价，且下影线较长
        body_size = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)

        if body_size > 0:
            shadow_ratio = lower_shadow / body_size
            # 锤子线特征：下影线至少是实体的2倍，上影线很短
            if shadow_ratio > 2.0 and upper_shadow < body_size * 0.3:
                is_bullish_reversal = True

        price_score = 0.7 if is_bullish_reversal else 0.3
        confidence_factors.append(("price_action", price_score, 0.40))

        # 2. 成交量分析（权重：30%）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：30%）
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.8  # 下跌趋势中PS可能性高
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.2

        confidence_factors.append(("context", regime_score, 0.30))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.3 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_sc(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测抛售高潮

        SC特征：
        1. 高成交量（恐慌性抛售）
        2. 大幅下跌（长阴线或长下影线）
        3. 针形K线特征（下影线长）
        4. 出现在下跌趋势后

        Args:
            candle: 单根K线数据，需包含open, high, low, close, volume
            context: 上下文信息，可包含市场体制、TR边界等

        Returns:
            检测结果字典，包含置信度、强度和证据列表
        """
        evidences = []
        confidence_factors = []

        # 检查必需的数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        # 1. 成交量分析（权重：35%）
        volume_evidence = self._analyze_volume_for_sc(candle, context)
        if volume_evidence:
            evidences.append(volume_evidence)
            confidence_factors.append(("volume", volume_evidence.confidence, 0.35))

        # 2. 价格行为分析（权重：30%）
        price_evidence = self._analyze_price_action_for_sc(candle, context)
        if price_evidence:
            evidences.append(price_evidence)
            confidence_factors.append(("price_action", price_evidence.confidence, 0.30))

        # 3. 市场上下文分析（权重：20%）
        context_evidence = self._analyze_context_for_sc(candle, context)
        if context_evidence:
            evidences.append(context_evidence)
            confidence_factors.append(("context", context_evidence.confidence, 0.20))

        # 4. 趋势分析（权重：15%）
        trend_evidence = self._analyze_trend_for_sc(candle, context)
        if trend_evidence:
            evidences.append(trend_evidence)
            confidence_factors.append(("trend", trend_evidence.confidence, 0.15))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度（基于成交量比例和价格波动）
        volume_intensity = volume_evidence.value if volume_evidence else 1.0
        price_intensity = price_evidence.value if price_evidence else 0.5
        overall_intensity = volume_intensity * 0.6 + price_intensity * 0.4

        # 记录关键价格水平（SC低点）
        sc_low = float(candle["low"])
        self.critical_price_levels["SC_LOW"] = sc_low

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    # ===== AR检测辅助方法 =====

    def _analyze_volume_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR成交量特征

        AR成交量特征：
        1. 成交量收缩（相对于SC的恐慌性抛售）
        2. 买盘温和恢复

        Returns:
            成交量证据
        """
        if "volume" not in candle:
            return None

        current_volume = float(candle["volume"])

        # 获取SC成交量（如果可用）
        sc_volume = context.get(
            "sc_volume", current_volume * 2.0
        )  # 默认SC成交量是当前2倍
        sc_volume_ratio = sc_volume / current_volume if current_volume > 0 else 1.0

        # AR成交量应小于SC成交量（收缩）
        volume_contraction = min(
            1.0, sc_volume_ratio / 3.0
        )  # SC成交量是AR3倍时达到最大置信度

        # 计算成交量置信度
        confidence = volume_contraction

        return StateEvidence(
            evidence_type="volume_contraction",
            value=volume_contraction,
            confidence=confidence,
            weight=0.7,
            description=f"成交量收缩比率: {sc_volume_ratio:.2f}x (SC成交量: {sc_volume:.0f}, AR成交量: {current_volume:.0f})",
        )


    def _analyze_bounce_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR价格反弹特征

        AR价格特征：
        1. 从SC低点反弹
        2. 反弹幅度适中（20%-50%回撤）
        3. 通常为阳线

        Returns:
            反弹证据
        """
        required_fields = ["open", "high", "low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # 获取SC低点
        sc_low = context.get("sc_low", low * 0.95)  # 默认SC低点比当前低点低5%

        # 计算反弹幅度（从SC低点到当前收盘价）
        bounce_height = close - sc_low
        sc_range = context.get("sc_range", high - low)  # SC价格范围

        if sc_range <= 0:
            return None

        bounce_ratio = bounce_height / sc_range

        # AR反弹幅度通常在20%-50%之间
        optimal_bounce_min = 0.2
        optimal_bounce_max = 0.5

        if bounce_ratio < optimal_bounce_min:
            bounce_score = bounce_ratio / optimal_bounce_min
        elif bounce_ratio > optimal_bounce_max:
            bounce_score = max(
                0, 1.0 - (bounce_ratio - optimal_bounce_max) / optimal_bounce_max
            )
        else:
            bounce_score = 1.0

        # 检查是否为阳线（AR通常为阳线）
        is_bullish = close > open_price
        bullish_score = 0.8 if is_bullish else 0.3

        # 综合反弹评分
        bounce_score_final = bounce_score * 0.7 + bullish_score * 0.3

        return StateEvidence(
            evidence_type="bounce_strength",
            value=bounce_score_final,
            confidence=bounce_score_final,
            weight=0.8,
            description=f"反弹强度: {bounce_score_final:.2f} (反弹幅度: {bounce_ratio:.1%}, SC低点: {sc_low:.2f}, 阳线: {is_bullish})",
        )


    def _analyze_context_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR市场上下文

        AR上下文特征：
        1. 出现在SC之后
        2. 市场体制可能从下跌转为盘整

        Returns:
            上下文证据
        """
        # 检查是否检测到SC
        has_sc = context.get("has_sc", False)
        sc_confidence = context.get("sc_confidence", 0.0)

        # SC存在且置信度高时，AR可能性高
        sc_score = sc_confidence if has_sc else 0.2

        # 检查市场体制
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5  # 默认

        if market_regime in ["ACCUMULATION", "CONSOLIDATION", "TRANSITION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.4  # 仍在下跌趋势中，但可能出现AR

        # 综合上下文评分
        context_score = sc_score * 0.6 + regime_score * 0.4

        return StateEvidence(
            evidence_type="ar_context",
            value=context_score,
            confidence=context_score,
            weight=0.5,
            description=f"AR上下文评分: {context_score:.2f} (有SC: {has_sc}, SC置信度: {sc_confidence:.2f}, 市场体制: {market_regime})",
        )


    def _analyze_trend_for_ar(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析AR趋势特征

        AR趋势特征：
        1. 下跌趋势缓解
        2. 可能转为横盘或微幅上涨

        Returns:
            趋势证据
        """
        # 获取趋势信息
        trend_direction = context.get("trend_direction", "UNKNOWN")
        trend_strength = context.get("trend_strength", 0.5)

        # AR出现在下跌趋势缓解时
        trend_score = 0.5  # 默认

        if trend_direction == "DOWN":
            # 下跌趋势中，但强度减弱有利于AR
            trend_score = 0.6 - (trend_strength * 0.3)  # 下跌趋势越弱，AR可能性越高
        elif trend_direction == "SIDEWAYS":
            trend_score = 0.7  # 横盘有利于AR
        elif trend_direction == "UP":
            trend_score = 0.3  # 上涨趋势中AR可能性低

        return StateEvidence(
            evidence_type="trend_for_ar",
            value=trend_score,
            confidence=trend_score,
            weight=0.4,
            description=f"AR趋势评分: {trend_score:.2f} (趋势方向: {trend_direction}, 趋势强度: {trend_strength:.2f})",
        )


    def detect_ar(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测自动反弹

        AR特征：
        1. 成交量收缩（相对于SC的恐慌性抛售）
        2. 价格从SC低点反弹
        3. 反弹幅度适中（不是V型反转）
        4. 通常伴随买盘温和恢复

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        # 1. 成交量分析（权重：30%）：AR成交量应收缩
        volume_evidence = self._analyze_volume_for_ar(candle, context)
        if volume_evidence:
            evidences.append(volume_evidence)
            confidence_factors.append(("volume", volume_evidence.confidence, 0.30))

        # 2. 价格反弹分析（权重：35%）：从SC低点反弹
        bounce_evidence = self._analyze_bounce_for_ar(candle, context)
        if bounce_evidence:
            evidences.append(bounce_evidence)
            confidence_factors.append(("bounce", bounce_evidence.confidence, 0.35))

        # 3. 市场上下文分析（权重：20%）：是否在SC之后
        context_evidence = self._analyze_context_for_ar(candle, context)
        if context_evidence:
            evidences.append(context_evidence)
            confidence_factors.append(("context", context_evidence.confidence, 0.20))

        # 4. 趋势缓和分析（权重：15%）：下跌趋势缓解
        trend_evidence = self._analyze_trend_for_ar(candle, context)
        if trend_evidence:
            evidences.append(trend_evidence)
            confidence_factors.append(("trend", trend_evidence.confidence, 0.15))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度（基于反弹幅度和成交量收缩程度）
        bounce_intensity = bounce_evidence.value if bounce_evidence else 0.5
        volume_intensity = volume_evidence.value if volume_evidence else 0.5
        overall_intensity = bounce_intensity * 0.6 + volume_intensity * 0.4

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    # ===== ST检测辅助方法 =====

    def _analyze_volume_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST成交量特征

        ST成交量特征：
        1. 成交量进一步收缩（相对于AR）
        2. 买盘犹豫，卖盘枯竭

        Returns:
            成交量证据
        """
        if "volume" not in candle:
            return None

        current_volume = float(candle["volume"])

        # 获取AR成交量（如果可用）
        ar_volume = context.get(
            "ar_volume", current_volume * 1.5
        )  # 默认AR成交量是当前1.5倍
        ar_volume_ratio = ar_volume / current_volume if current_volume > 0 else 1.0

        # ST成交量应小于AR成交量（进一步收缩）
        volume_contraction = min(
            1.0, ar_volume_ratio / 2.0
        )  # AR成交量是ST2倍时达到最大置信度

        # 计算成交量置信度
        confidence = volume_contraction

        return StateEvidence(
            evidence_type="volume_contraction_st",
            value=volume_contraction,
            confidence=confidence,
            weight=0.7,
            description=f"ST成交量收缩比率: {ar_volume_ratio:.2f}x (AR成交量: {ar_volume:.0f}, ST成交量: {current_volume:.0f})",
        )


    def _analyze_retracement_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST价格回撤特征

        ST价格特征：
        1. 回调测试SC低点区域
        2. 回调幅度有限（AR反弹幅度的30%-70%）
        3. 不跌破SC低点

        Returns:
            回撤证据
        """
        required_fields = ["open", "high", "low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # 获取SC低点和AR高点
        sc_low = context.get("sc_low", low * 0.98)  # 默认SC低点比当前低点低2%
        ar_high = context.get("ar_high", high * 1.02)  # 默认AR高点比当前高点高2%

        # 计算AR反弹幅度
        ar_bounce = ar_high - sc_low
        if ar_bounce <= 0:
            return None

        # 计算当前价格从AR高点的回撤幅度
        current_price = close
        retracement = ar_high - current_price
        retracement_ratio = retracement / ar_bounce if ar_bounce > 0 else 0.0

        # ST回撤幅度通常在30%-70%之间
        optimal_retracement_min = 0.3
        optimal_retracement_max = 0.7

        if retracement_ratio < optimal_retracement_min:
            retracement_score = retracement_ratio / optimal_retracement_min
        elif retracement_ratio > optimal_retracement_max:
            retracement_score = max(
                0,
                1.0
                - (retracement_ratio - optimal_retracement_max)
                / optimal_retracement_max,
            )
        else:
            retracement_score = 1.0

        # 检查是否跌破SC低点（不应跌破）
        above_sc = current_price > sc_low
        sc_penalty = 0.2 if not above_sc else 0.0

        # 综合回撤评分
        retracement_score_final = max(0, retracement_score - sc_penalty)

        return StateEvidence(
            evidence_type="retracement_strength",
            value=retracement_score_final,
            confidence=retracement_score_final,
            weight=0.8,
            description=f"ST回撤强度: {retracement_score_final:.2f} (回撤幅度: {retracement_ratio:.1%}, SC低点: {sc_low:.2f}, AR高点: {ar_high:.2f}, 高于SC: {above_sc})",
        )


    def _analyze_context_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST市场上下文

        ST上下文特征：
        1. 出现在AR之后
        2. 市场体制可能为盘整或吸筹

        Returns:
            上下文证据
        """
        # 检查是否检测到AR
        has_ar = context.get("has_ar", False)
        ar_confidence = context.get("ar_confidence", 0.0)

        # AR存在且置信度高时，ST可能性高
        ar_score = ar_confidence if has_ar else 0.2

        # 检查市场体制
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5  # 默认

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3  # 仍在下跌趋势中，ST可能性较低

        # 综合上下文评分
        context_score = ar_score * 0.7 + regime_score * 0.3

        return StateEvidence(
            evidence_type="st_context",
            value=context_score,
            confidence=context_score,
            weight=0.5,
            description=f"ST上下文评分: {context_score:.2f} (有AR: {has_ar}, AR置信度: {ar_confidence:.2f}, 市场体制: {market_regime})",
        )


    def _analyze_support_for_st(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> Optional[StateEvidence]:
        """分析ST支撑测试特征

        ST支撑特征：
        1. SC低点支撑有效
        2. 价格在SC区域获得支撑

        Returns:
            支撑证据
        """
        required_fields = ["low", "close"]
        if not all(field in candle for field in required_fields):
            return None

        low = float(candle["low"])
        close = float(candle["close"])

        # 获取SC低点
        sc_low = context.get("sc_low", low * 0.98)

        # 计算价格与SC低点的距离
        distance_to_sc = close - sc_low
        sc_range = context.get("sc_range", distance_to_sc * 2)  # 默认SC范围

        if sc_range <= 0:
            return None

        # 价格在SC低点上方附近获得支撑
        proximity_ratio = distance_to_sc / sc_range if sc_range > 0 else 0.0

        # 理想情况：价格在SC低点上方5%-20%范围内
        optimal_proximity_min = 0.05
        optimal_proximity_max = 0.20

        if proximity_ratio < optimal_proximity_min:
            proximity_score = proximity_ratio / optimal_proximity_min
        elif proximity_ratio > optimal_proximity_max:
            proximity_score = max(
                0,
                1.0 - (proximity_ratio - optimal_proximity_max) / optimal_proximity_max,
            )
        else:
            proximity_score = 1.0

        # 检查是否跌破SC低点
        above_sc = close > sc_low
        sc_penalty = 0.3 if not above_sc else 0.0

        # 综合支撑评分
        support_score = max(0, proximity_score - sc_penalty)

        return StateEvidence(
            evidence_type="support_strength",
            value=support_score,
            confidence=support_score,
            weight=0.6,
            description=f"ST支撑强度: {support_score:.2f} (距离SC: {proximity_ratio:.1%}, SC低点: {sc_low:.2f}, 高于SC: {above_sc})",
        )


    def detect_st(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测二次测试

        ST特征：
        1. 成交量进一步收缩（相对于AR）
        2. 价格回调测试SC低点区域，但不跌破SC低点
        3. 回调幅度有限（通常为AR反弹幅度的50%左右）
        4. 可能出现缩量小阴线或十字星

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        # 1. 成交量分析（权重：30%）：ST成交量应进一步收缩
        volume_evidence = self._analyze_volume_for_st(candle, context)
        if volume_evidence:
            evidences.append(volume_evidence)
            confidence_factors.append(("volume", volume_evidence.confidence, 0.30))

        # 2. 价格回调分析（权重：35%）：测试SC区域但不跌破
        retracement_evidence = self._analyze_retracement_for_st(candle, context)
        if retracement_evidence:
            evidences.append(retracement_evidence)
            confidence_factors.append(
                ("retracement", retracement_evidence.confidence, 0.35)
            )

        # 3. 市场上下文分析（权重：20%）：是否在AR之后
        context_evidence = self._analyze_context_for_st(candle, context)
        if context_evidence:
            evidences.append(context_evidence)
            confidence_factors.append(("context", context_evidence.confidence, 0.20))

        # 4. 支撑测试分析（权重：15%）：SC低点支撑有效性
        support_evidence = self._analyze_support_for_st(candle, context)
        if support_evidence:
            evidences.append(support_evidence)
            confidence_factors.append(("support", support_evidence.confidence, 0.15))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度（基于成交量收缩程度和支撑强度）
        volume_intensity = volume_evidence.value if volume_evidence else 0.5
        support_intensity = support_evidence.value if support_evidence else 0.5
        overall_intensity = volume_intensity * 0.5 + support_intensity * 0.5

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_test(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测测试状态

        TEST特征：
        1. 价格测试前支撑位（如SC低点、SPRING低点）
        2. 成交量收缩（供应不足）
        3. 价格反弹迹象（测试成功）
        4. 通常在SC/AR/ST之后出现

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：40%）
        # 检查是否测试关键支撑位
        test_success = False
        # 获取关键支撑位（SC低点、SPRING低点等）
        sc_low = self.critical_price_levels.get("SC_LOW")
        spring_low = self.critical_price_levels.get("SPRING_LOW")
        support_levels = [level for level in [sc_low, spring_low] if level is not None]

        if support_levels:
            # 计算价格与最近支撑位的距离
            nearest_support = min(support_levels, key=lambda x: abs(x - low))
            distance_pct = abs(low - nearest_support) / nearest_support * 100
            # 测试成功：价格接近支撑位并反弹（收盘高于开盘）
            if distance_pct < 1.0 and close > open_price:
                test_success = True

        price_score = 0.8 if test_success else 0.3
        confidence_factors.append(("price_action", price_score, 0.40))

        # 2. 成交量分析（权重：30%）
        # TEST成交量应收缩（供应不足）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：30%）
        # TEST通常在吸筹阶段出现（SC/AR/ST之后）
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.6  # 下跌趋势中也可能出现测试

        # 检查前驱状态（如果有状态历史）
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SC", "AR", "ST"]:
                regime_score = min(1.0, regime_score + 0.2)

        confidence_factors.append(("context", regime_score, 0.30))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.3 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_spring(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """检测弹簧状态

        SPRING特征：
        1. 价格跌破关键支撑位（如SC低点）
        2. 快速反弹回支撑位上方（假突破）
        3. 成交量相对较低（缺乏跟进卖盘）
        4. 通常出现在吸筹后期（SC/AR/ST之后）

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否跌破关键支撑位并反弹
        spring_detected = False
        # 获取关键支撑位（SC低点）
        sc_low = self.critical_price_levels.get("SC_LOW")
        spring_low = self.critical_price_levels.get("SPRING_LOW")
        support_levels = [level for level in [sc_low, spring_low] if level is not None]

        if support_levels:
            nearest_support = min(support_levels, key=lambda x: abs(x - low))
            # 检查是否跌破支撑位（最低价低于支撑位）
            if low < nearest_support:
                # 检查是否反弹回支撑位上方（收盘价高于支撑位）
                if close > nearest_support:
                    spring_detected = True
                    # 记录弹簧低点
                    self.critical_price_levels["SPRING_LOW"] = low

        price_score = 0.9 if spring_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # SPRING成交量应较低（缺乏跟进卖盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量越低，置信度越高（小于1倍平均成交量）
        volume_score = max(0.0, 1.0 - volume_ratio * 0.8)  # 0倍得1分，1.25倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # SPRING通常在吸筹阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.6

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SC", "AR", "ST", "TEST"]:
                regime_score = min(1.0, regime_score + 0.2)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_so(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测震仓状态

        SO（震仓）特征：
        1. 价格快速跌破支撑位，引发恐慌
        2. 成交量放大（恐慌性抛售）
        3. 快速反弹回支撑位上方
        4. 通常出现在吸筹阶段，清洗弱手

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否跌破支撑并快速反弹
        shakeout_detected = False
        # 获取关键支撑位
        sc_low = self.critical_price_levels.get("SC_LOW")
        support_levels = [level for level in [sc_low] if level is not None]

        if support_levels:
            nearest_support = min(support_levels, key=lambda x: abs(x - low))
            # 检查是否跌破支撑位（最低价明显低于支撑位）
            if low < nearest_support * 0.99:  # 至少跌破1%
                # 检查是否反弹回支撑位附近（收盘价接近或高于支撑位）
                if close > nearest_support * 0.995:
                    shakeout_detected = True

        price_score = 0.9 if shakeout_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # SO成交量应放大（恐慌性抛售）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1.5倍）
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # SO通常在吸筹阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.6

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SC", "AR", "ST", "TEST"]:
                regime_score = min(1.0, regime_score + 0.2)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.3 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_lps(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测最后支撑点

        LPS（最后支撑点）特征：
        1. 价格形成更高的低点（相对于SC或SPRING低点）
        2. 成交量收缩（供应枯竭）
        3. 价格反弹迹象（需求进入）
        4. 通常出现在SPRING或TEST之后

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        float(candle["high"])
        low = float(candle["low"])
        float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否形成更高的低点
        higher_low_detected = False
        # 获取前期低点（SC低点、SPRING低点）
        sc_low = self.critical_price_levels.get("SC_LOW")
        spring_low = self.critical_price_levels.get("SPRING_LOW")
        previous_lows = [level for level in [sc_low, spring_low] if level is not None]

        if previous_lows:
            lowest_previous = min(previous_lows)
            # 当前低点高于前期低点（形成更高的低点）
            if low > lowest_previous:
                higher_low_detected = True

        price_score = 0.9 if higher_low_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # LPS成交量应收缩（供应枯竭）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # LPS通常在吸筹后期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.4  # 下跌趋势中LPS可能性较低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["SPRING", "TEST", "SO"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_msos(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测整体强势状态

        mSOS/MSOS（强势信号）特征：
        1. 价格创新高或接近前期高点
        2. 成交量放大（需求进入）
        3. 价格回调幅度小（供应薄弱）
        4. 通常出现在LPS之后，JOC之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否创新高或接近前期高点
        strength_detected = False
        # 获取前期高点（SC高点、AR高点等）
        sc_high = self.critical_price_levels.get("SC_HIGH")
        ar_high = self.critical_price_levels.get("AR_HIGH")
        previous_highs = [level for level in [sc_high, ar_high] if level is not None]

        if previous_highs:
            highest_previous = max(previous_highs)
            # 当前高点接近或超过前期高点
            if high >= highest_previous * 0.98:  # 至少达到98%
                strength_detected = True

        price_score = 0.9 if strength_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # 强势信号成交量应放大（需求进入）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # 强势信号通常在吸筹后期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3  # 下跌趋势中强势信号可能性低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["LPS", "mSOS"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.3 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_joc(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测突破溪流

        JOC（突破溪流）特征：
        1. 价格突破关键阻力位（如交易区间上沿）
        2. 成交量显著放大（需求强劲）
        3. 突破幅度较大（显示力度）
        4. 通常出现在MSOS之后，BU之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否突破关键阻力位
        breakout_detected = False
        # 获取关键阻力位（交易区间上沿、前期高点）
        tr_resistance = context.get("tr_resistance")
        previous_highs = [level for level in [tr_resistance] if level is not None]

        if previous_highs:
            resistance_level = max(previous_highs)
            # 价格突破阻力位（收盘价高于阻力位）
            if close > resistance_level:
                breakout_detected = True
                # 记录JOC高点
                self.critical_price_levels["JOC_HIGH"] = high

        price_score = 0.9 if breakout_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # JOC成交量应显著放大（需求强劲）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于2倍）
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # JOC通常在吸筹末期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3  # 下跌趋势中JOC可能性低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["MSOS", "mSOS"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.3 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_bu(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测回踩确认

        BU（回踩确认）特征：
        1. 价格回踩突破位（JOC高点或阻力转支撑）
        2. 成交量收缩（供应缺乏）
        3. 价格在支撑位反弹（确认支撑有效）
        4. 通常出现在JOC之后，确认突破有效

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否回踩突破位并反弹
        backup_confirmed = False
        # 获取JOC高点或突破位
        joc_high = self.critical_price_levels.get("JOC_HIGH")
        tr_resistance = context.get("tr_resistance")
        breakout_levels = [
            level for level in [joc_high, tr_resistance] if level is not None
        ]

        if breakout_levels:
            breakout_level = max(breakout_levels)  # 突破位作为支撑
            # 价格回踩突破位（最低价接近突破位）
            if abs(low - breakout_level) / breakout_level < 0.02:  # 2%以内
                # 收盘价高于开盘价（反弹迹象）
                if close > open_price:
                    backup_confirmed = True

        price_score = 0.9 if backup_confirmed else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # BU成交量应收缩（缺乏供应）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # BU通常在突破后出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION", "UPTREND"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "JOC":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_uta(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测上冲行为

        UTA（上冲行为）特征：
        1. 价格上冲突破阻力位但未能站稳
        2. 收盘价回落至阻力位下方（假突破）
        3. 成交量相对较低（缺乏跟进买盘）
        4. 通常出现在AR之后，TEST之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否上冲突破但回落
        upthrust_detected = False
        # 获取关键阻力位（AR高点、前期高点）
        ar_high = self.critical_price_levels.get("AR_HIGH")
        tr_resistance = context.get("tr_resistance")
        resistance_levels = [
            level for level in [ar_high, tr_resistance] if level is not None
        ]

        if resistance_levels:
            resistance_level = max(resistance_levels)
            # 检查是否上冲突破（最高价高于阻力位）
            if high > resistance_level:
                # 检查是否回落（收盘价低于阻力位）
                if close < resistance_level:
                    upthrust_detected = True

        price_score = 0.9 if upthrust_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # UTA成交量应较低（缺乏跟进买盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量越低，置信度越高（小于1倍平均成交量）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # UTA通常在吸筹阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["ACCUMULATION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "AR":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_psy(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测初步供应

        PSY（初步供应）特征：
        1. 价格上涨至阻力位遇阻
        2. 成交量放大（供应进入）
        3. 可能出现上影线或阴线（供应压力）
        4. 通常出现在上涨趋势后，派发阶段开始

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否在阻力位出现供应迹象
        supply_detected = False
        # 获取关键阻力位（交易区间上沿、前期高点）
        tr_resistance = context.get("tr_resistance")
        previous_highs = [level for level in [tr_resistance] if level is not None]

        if previous_highs:
            resistance_level = max(previous_highs)
            # 价格接近阻力位（最高价达到阻力位附近）
            if high >= resistance_level * 0.98:
                # 检查是否有供应迹象（上影线长、阴线）
                upper_shadow = high - max(open_price, close)
                body_size = abs(close - open_price)
                if body_size > 0:
                    shadow_ratio = upper_shadow / body_size
                    # 长上影线或阴线表示供应
                    if shadow_ratio > 1.5 or close < open_price:
                        supply_detected = True

        price_score = 0.9 if supply_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # PSY成交量应放大（供应进入）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1.5倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # PSY通常在上涨趋势后出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["UPTREND", "BULLISH", "DISTRIBUTION"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3

        # 检查前驱状态（如果有状态历史）
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["BU", "JOC"]:
                regime_score = min(1.0, regime_score + 0.2)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.3 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_bc(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测买入高潮

        BC（买入高潮）特征：
        1. 价格大幅上涨至新高（高潮性买盘）
        2. 成交量极高（散户狂热）
        3. 长上影线或反转形态（供应突然出现）
        4. 通常出现在派发初期，PSY之后

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否出现高潮性上涨和反转迹象
        climax_detected = False
        # 计算价格范围和影线
        abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        min(open_price, close) - low
        total_range = high - low

        if total_range > 0:
            # 长上影线比例（供应迹象）
            upper_shadow_ratio = upper_shadow / total_range
            # 价格创新高（相对于上下文）
            price_high_context = context.get("price_high_20", high * 0.9)
            if high >= price_high_context:
                # 反转特征：长上影线或收盘接近最低价
                if upper_shadow_ratio > 0.3 or close < open_price * 0.99:
                    climax_detected = True
                    # 记录BC高点
                    self.critical_price_levels["BC_HIGH"] = high

        price_score = 0.9 if climax_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # BC成交量应极高（狂热买盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于2倍）
        volume_score = min(1.0, volume_ratio / 2.0)  # 2倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # BC通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "UPTREND", "BULLISH"]:
            regime_score = 0.8
        elif market_regime in ["DOWNTREND", "BEARISH"]:
            regime_score = 0.3

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "PSY":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.4 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_ar_dist(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """检测派发阶段自动回落

        AR_DIST（自动回落）特征：
        1. 价格从BC高点快速回落
        2. 成交量收缩（买盘枯竭）
        3. 回落幅度适中（20%-50%回撤）
        4. 通常出现在BC之后，ST_DIST之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否从BC高点回落
        ar_detected = False
        # 获取BC高点
        bc_high = self.critical_price_levels.get("BC_HIGH")

        if bc_high:
            # 计算回落幅度
            decline_height = bc_high - low
            bc_range = context.get("bc_range", high - low)  # BC价格范围
            if bc_range > 0:
                decline_ratio = decline_height / bc_range
                # AR回落幅度通常在20%-50%之间
                optimal_decline_min = 0.2
                optimal_decline_max = 0.5

                if optimal_decline_min <= decline_ratio <= optimal_decline_max:
                    ar_detected = True

        price_score = 0.9 if ar_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # AR_DIST成交量应收缩（买盘枯竭）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # AR_DIST通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "BC":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_st_dist(
        self, candle: pd.Series, context: dict[str, Any]
    ) -> dict[str, Any]:
        """检测派发阶段二次测试

        ST_DIST（二次测试）特征：
        1. 价格反弹至BC或AR_DIST高点附近但未能突破
        2. 成交量收缩（买盘乏力）
        3. 可能形成上影线或阴线（供应压力）
        4. 通常出现在AR_DIST之后，UT之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否测试前期高点但失败
        st_dist_detected = False
        # 获取BC高点和AR_DIST高点
        bc_high = self.critical_price_levels.get("BC_HIGH")
        ar_dist_high = context.get("ar_dist_high")
        resistance_levels = [
            level for level in [bc_high, ar_dist_high] if level is not None
        ]

        if resistance_levels:
            resistance_level = max(resistance_levels)
            # 价格接近阻力位但未突破（最高价接近阻力位）
            if abs(high - resistance_level) / resistance_level < 0.02:  # 2%以内
                # 收盘价低于阻力位（测试失败）
                if close < resistance_level:
                    st_dist_detected = True

        price_score = 0.9 if st_dist_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # ST_DIST成交量应收缩（买盘乏力）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # ST_DIST通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["BC", "AR_DIST"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_ut(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测上冲测试

        UT（上冲测试）特征：
        1. 价格上冲突破前期高点（如BC高点）但未能站稳
        2. 收盘价回落至高点下方（假突破）
        3. 成交量较低（缺乏跟进买盘）
        4. 通常出现在ST_DIST之后，UTAD之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        float(candle["open"])
        high = float(candle["high"])
        float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否上冲突破但回落
        upthrust_detected = False
        # 获取BC高点或前期阻力位
        bc_high = self.critical_price_levels.get("BC_HIGH")
        resistance_levels = [level for level in [bc_high] if level is not None]

        if resistance_levels:
            resistance_level = max(resistance_levels)
            # 检查是否上冲突破（最高价高于阻力位）
            if high > resistance_level:
                # 检查是否回落（收盘价低于阻力位）
                if close < resistance_level:
                    upthrust_detected = True

        price_score = 0.9 if upthrust_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # UT成交量应较低（缺乏跟进买盘）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量越低，置信度越高（小于1倍平均成交量）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # UT通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "ST_DIST":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.6 + volume_score * 0.2 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_utad(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测上冲后的派发

        UTAD（上冲后的派发）特征：
        1. 价格上冲突破后出现派发迹象（供应增加）
        2. 成交量放大（派发活动）
        3. 价格未能维持高位，收盘价接近低点
        4. 通常出现在UT之后，LPSY之前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否上冲后派发（长上影线或阴线）
        utad_detected = False
        # 计算上影线比例
        upper_shadow = high - max(open_price, close)
        abs(close - open_price)
        total_range = high - low

        if total_range > 0:
            upper_shadow_ratio = upper_shadow / total_range
            # 长上影线或阴线表示派发
            if upper_shadow_ratio > 0.3 or close < open_price:
                utad_detected = True

        price_score = 0.9 if utad_detected else 0.3
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # UTAD成交量应放大（派发活动）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1.5倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # UTAD通常在派发阶段出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state == "UT":
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.4 + regime_score * 0.1

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_lpsy(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测最后供应点

        LPSY（最后供应点）特征：
        1. 价格形成更低的高点（相对于BC或UT高点）
        2. 成交量收缩（买盘枯竭）
        3. 价格下跌迹象（供应进入）
        4. 通常出现在UT或UTAD之后

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否形成更低的高点
        lower_high_detected = False
        # 获取前期高点（BC高点、UT高点）
        bc_high = self.critical_price_levels.get("BC_HIGH")
        ut_high = context.get("ut_high")
        previous_highs = [level for level in [bc_high, ut_high] if level is not None]

        if previous_highs:
            highest_previous = max(previous_highs)
            # 当前高点低于前期高点（形成更低的高点）
            if high < highest_previous:
                lower_high_detected = True

        # 检查是否为阴线或上影线较长（供应压力）
        is_bearish = close < open_price
        upper_shadow = high - max(open_price, close)
        total_range = high - low
        upper_shadow_ratio = upper_shadow / total_range if total_range > 0 else 0.0

        bearish_score = 0.7 if is_bearish or upper_shadow_ratio > 0.3 else 0.3

        price_score = 0.9 if lower_high_detected else 0.3
        price_score = price_score * 0.7 + bearish_score * 0.3  # 结合高低点和K线形态
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # LPSY成交量应收缩（买盘枯竭）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量收缩得越好，置信度越高（比率小于1）
        volume_score = max(0.0, 1.0 - volume_ratio)  # 0倍成交量得1分，1倍得0分
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # LPSY通常在派发后期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "CONSOLIDATION"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.4  # 上涨趋势中LPSY可能性较低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["UT", "UTAD", "ST_DIST"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.3 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    def detect_msow(self, candle: pd.Series, context: dict[str, Any]) -> dict[str, Any]:
        """检测整体弱势

        MSOW（整体弱势）特征：
        1. 价格创新低或接近前期低点
        2. 成交量放大（供应增加）
        3. 价格下跌延续（需求薄弱）
        4. 通常出现在LPSY或mSOW之后，下跌趋势开始前

        Args:
            candle: 单根K线数据
            context: 上下文信息

        Returns:
            检测结果字典
        """
        evidences = []
        confidence_factors = []

        # 检查必需数据字段
        required_fields = ["open", "high", "low", "close", "volume"]
        if not all(field in candle for field in required_fields):
            return {"confidence": 0.0, "intensity": 0.0, "evidences": []}

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        volume = float(candle["volume"])

        # 1. 价格行为分析（权重：50%）
        # 检查是否创新低或接近前期低点
        weakness_detected = False
        # 获取前期低点（BC低点、AR_DIST低点等）
        bc_low = self.critical_price_levels.get("BC_LOW")
        ar_dist_low = context.get("ar_dist_low")
        previous_lows = [level for level in [bc_low, ar_dist_low] if level is not None]

        if previous_lows:
            lowest_previous = min(previous_lows)
            # 当前低点接近或低于前期低点
            if low <= lowest_previous * 1.02:  # 至少达到98% (允许2%误差)
                weakness_detected = True

        # 检查是否为阴线或下影线较短（弱势特征）
        is_bearish = close < open_price
        lower_shadow = min(open_price, close) - low
        total_range = high - low
        lower_shadow_ratio = lower_shadow / total_range if total_range > 0 else 0.0

        # 弱势特征：阴线且下影线短（缺乏买盘支撑）
        weakness_score = 0.8 if is_bearish and lower_shadow_ratio < 0.2 else 0.3

        price_score = 0.9 if weakness_detected else 0.3
        price_score = price_score * 0.7 + weakness_score * 0.3  # 结合低点和K线形态
        confidence_factors.append(("price_action", price_score, 0.50))

        # 2. 成交量分析（权重：30%）
        # MSOW成交量应放大（供应增加）
        avg_volume = context.get("avg_volume_20", volume * 1.5)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        # 成交量放大得越好，置信度越高（大于1倍）
        volume_score = min(1.0, volume_ratio / 1.5)  # 1.5倍成交量达到最大置信度
        confidence_factors.append(("volume", volume_score, 0.30))

        # 3. 市场上下文分析（权重：20%）
        # MSOW通常在派发末期出现
        market_regime = context.get("market_regime", "UNKNOWN")
        regime_score = 0.5

        if market_regime in ["DISTRIBUTION", "DOWNTREND"]:
            regime_score = 0.8
        elif market_regime in ["UPTREND", "BULLISH"]:
            regime_score = 0.2  # 上涨趋势中MSOW可能性很低

        # 检查前驱状态
        if self.state_history:
            last_state = (
                self.state_history[-1].to_state
                if hasattr(self.state_history[-1], "to_state")
                else self.state_history[-1]
            )
            if last_state in ["LPSY", "mSOW"]:
                regime_score = min(1.0, regime_score + 0.3)

        confidence_factors.append(("context", regime_score, 0.20))

        # 计算加权置信度
        total_confidence = 0.0
        total_weight = 0.0

        for factor_name, confidence, weight in confidence_factors:
            total_confidence += confidence * weight
            total_weight += weight

        overall_confidence = (
            total_confidence / total_weight if total_weight > 0 else 0.0
        )

        # 计算强度
        overall_intensity = price_score * 0.5 + volume_score * 0.3 + regime_score * 0.2

        return {
            "confidence": min(1.0, max(0.0, overall_confidence)),
            "intensity": min(1.0, max(0.0, overall_intensity)),
            "evidences": evidences,
        }

    # 其他检测方法类似，需要后续实现...

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


# ===== 增强状态机类 =====


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
            f"Baseline performance ({target_metric}): {baseline_performance:.4f}"
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
                        logger.info(f"Reached max iterations ({max_iterations})")
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
                            f"Iteration {iteration}: New best performance: {performance:.4f}"
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
                f"Applying optimized configuration (improvement: {improvement:.2%})"
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
                    f"Insufficient signals for evaluation: {len(signals)} < {min_trades}"
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

            # 更新状态机内部参数
            self.SPRING_FAILURE_BARS = optimized_config.get(
                "SPRING_FAILURE_BARS", self.SPRING_FAILURE_BARS
            )
            self.STATE_TIMEOUT_BARS = optimized_config.get(
                "STATE_TIMEOUT_BARS", self.STATE_TIMEOUT_BARS
            )
            self.STATE_MIN_CONFIDENCE = optimized_config.get(
                "STATE_MIN_CONFIDENCE", self.STATE_MIN_CONFIDENCE
            )
            self.PATH_SELECTION_THRESHOLD = optimized_config.get(
                "PATH_SELECTION_THRESHOLD", self.PATH_SELECTION_THRESHOLD
            )
            self.STATE_SWITCH_HYSTERESIS = optimized_config.get(
                "STATE_SWITCH_HYSTERESIS", self.STATE_SWITCH_HYSTERESIS
            )
            self.DIRECTION_SWITCH_PENALTY = optimized_config.get(
                "DIRECTION_SWITCH_PENALTY", self.DIRECTION_SWITCH_PENALTY
            )

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


class EvidenceChainManager:
    """
    状态证据链管理器

    功能：
    1. 证据收集与加权
    2. 证据链构建与验证
    3. 证据强度计算
    4. 证据链可视化
    """

    def __init__(self):
        self.evidence_chains: dict[str, list[StateEvidence]] = {}
        self.evidence_weights: dict[str, float] = {}
        self.chain_validation_rules: dict[str, Callable] = {}

        # 初始化默认证据权重
        self._initialize_default_weights()

    def _initialize_default_weights(self):
        """初始化默认证据权重"""
        self.evidence_weights = {
            "volume_ratio": 0.25,  # 成交量比率
            "pin_strength": 0.20,  # 针强度
            "effort_result_score": 0.15,  # 努力结果评分
            "bounce_percent": 0.15,  # 反弹百分比
            "volume_contraction": 0.10,  # 成交量收缩
            "retracement_depth": 0.10,  # 回撤深度
            "spring_strength": 0.05,  # 弹簧强度
        }

    def add_evidence(self, state_name: str, evidence: StateEvidence):
        """为状态添加证据"""
        if state_name not in self.evidence_chains:
            self.evidence_chains[state_name] = []

        self.evidence_chains[state_name].append(evidence)

        # 限制证据链长度
        if len(self.evidence_chains[state_name]) > 20:
            self.evidence_chains[state_name] = self.evidence_chains[state_name][-20:]

    def calculate_state_confidence(self, state_name: str) -> float:
        """计算状态置信度"""
        if state_name not in self.evidence_chains:
            return 0.0

        evidences = self.evidence_chains[state_name]
        if not evidences:
            return 0.0

        # 加权平均计算置信度
        total_weight = 0.0
        weighted_sum = 0.0

        for evidence in evidences[-5:]:  # 只考虑最近5个证据
            weight = self.evidence_weights.get(evidence.evidence_type, 0.1)
            weighted_sum += evidence.confidence * evidence.weight * weight
            total_weight += weight

        confidence = weighted_sum / total_weight if total_weight > 0 else 0.0

        return min(1.0, max(0.0, confidence))

    def validate_evidence_chain(self, state_name: str) -> dict[str, Any]:
        """验证证据链有效性"""
        if state_name not in self.evidence_chains:
            return {"valid": False, "reason": "无证据链"}

        evidences = self.evidence_chains[state_name]
        if len(evidences) < 3:
            return {"valid": False, "reason": "证据不足"}

        # 检查证据一致性
        recent_confidences = [e.confidence for e in evidences[-3:]]
        avg_confidence = np.mean(recent_confidences)
        confidence_std = np.std(recent_confidences)

        # 检查证据类型分布
        evidence_types = [e.evidence_type for e in evidences]
        unique_types = set(evidence_types)

        return {
            "valid": avg_confidence > 0.6 and confidence_std < 0.3,
            "avg_confidence": avg_confidence,
            "confidence_std": confidence_std,
            "evidence_count": len(evidences),
            "unique_evidence_types": len(unique_types),
            "recent_evidences": [
                {"type": e.evidence_type, "confidence": e.confidence, "value": e.value}
                for e in evidences[-3:]
            ],
        }


    def get_evidence_report(self, state_name: str) -> dict[str, Any]:
        """获取证据报告"""
        if state_name not in self.evidence_chains:
            return {"state": state_name, "evidence_count": 0, "evidences": []}

        evidences = self.evidence_chains[state_name]

        # 按证据类型分组
        evidence_by_type = {}
        for evidence in evidences:
            if evidence.evidence_type not in evidence_by_type:
                evidence_by_type[evidence.evidence_type] = []
            evidence_by_type[evidence.evidence_type].append(evidence)

        # 计算各类型证据的平均置信度
        type_confidence = {}
        for evidence_type, type_evidences in evidence_by_type.items():
            avg_confidence = np.mean([e.confidence for e in type_evidences])
            type_confidence[evidence_type] = avg_confidence

        return {
            "state": state_name,
            "evidence_count": len(evidences),
            "unique_evidence_types": len(evidence_by_type),
            "overall_confidence": self.calculate_state_confidence(state_name),
            "type_confidence": type_confidence,
            "recent_evidences": [
                {
                    "type": e.evidence_type,
                    "confidence": e.confidence,
                    "value": e.value,
                    "description": e.description,
                }
                for e in evidences[-5:]
            ],
        }



# ===== 使用示例 =====

if __name__ == "__main__":
    # 创建状态机实例
    config = StateConfig()
    state_machine = EnhancedWyckoffStateMachine(config)

    # 创建证据链管理器
    evidence_manager = EvidenceChainManager()


    # 测试状态机报告
    report = state_machine.get_state_report()
    for key, value in report.items():
        if key not in ["critical_price_levels", "timeout_counters"]:
            pass
