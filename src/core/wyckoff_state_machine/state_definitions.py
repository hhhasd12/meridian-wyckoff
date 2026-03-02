"""
威科夫状态机 - 状态定义模块

包含所有枚举、数据类和配置类定义。

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
from typing import Any, Optional

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
