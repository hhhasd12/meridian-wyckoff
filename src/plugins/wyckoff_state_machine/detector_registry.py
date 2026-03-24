"""检测器注册中心 + NodeScore + NodeDetector 基类

提供三个核心组件：
- NodeScore: 检测器返回的证据结构（AD-3：检测器只举证，推进权在主干）
- NodeDetector: 检测器抽象基类
- DetectorRegistry: 注册/查询/运行检测器，管理前置条件检查和冷却计时
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.kernel.types import StateEvidence

from .principles.bar_features import BarFeatures, StructureContext

logger = logging.getLogger(__name__)


@dataclass
class ParamSpec:
    """可进化参数规格

    Attributes:
        min: 参数下界
        max: 参数上界
        default: 默认值
        current: 当前值
    """

    min: float
    max: float
    default: float
    current: float


@dataclass
class NodeScore:
    """检测器返回的证据（AD-3：检测器只举证，推进权在主干）

    每个检测器对当前K线评估后返回 NodeScore，
    主干代码根据所有 NodeScore 综合决定是否推进状态。

    Attributes:
        detector_name: 检测器名称
        event_name: 检测到的事件名（PS/SC/AR/ST...）
        confidence: 置信度 0~1
        intensity: 强度 0~1
        evidences: 证据列表
        priority: 优先级（越高越优先），用于冲突裁决
        invalidates: 互斥事件名列表（由主干解释）
        supports: 增强事件名列表（由主干解释）
        cooldown_bars: 触发后冷却期（K线数）
        required_context: 前置条件列表（已确认的事件名）
    """

    detector_name: str
    event_name: str
    confidence: float
    intensity: float
    evidences: List[StateEvidence]
    priority: int = 0
    invalidates: List[str] = field(default_factory=list)
    supports: List[str] = field(default_factory=list)
    cooldown_bars: int = 0
    required_context: List[str] = field(default_factory=list)


class NodeDetector(ABC):
    """检测器抽象基类

    所有威科夫事件检测器（PS/SC/AR/ST/Spring/UTAD等）
    都继承此类，实现 evaluate 方法返回 NodeScore。

    检测器只负责举证，不决定状态推进（AD-3）。
    """

    def __init__(self) -> None:
        self._params: Dict[str, float] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """检测器唯一名称"""
        ...

    @abstractmethod
    def evaluate(
        self,
        candle: dict,
        features: BarFeatures,
        context: StructureContext,
    ) -> Optional[NodeScore]:
        """评估当前K线是否符合该事件模式

        Args:
            candle: K线数据字典，包含 open/high/low/close/volume
            features: 三大原则打分 + 单K线特征
            context: 当前结构上下文（状态机维护）

        Returns:
            NodeScore: 检测到事件时返回证据；未检测到返回 None
        """
        ...

    def get_evolvable_params(self) -> Dict[str, "ParamSpec"]:
        """返回可被进化系统优化的参数

        默认返回空字典。子类可覆盖此方法，
        暴露阈值参数供 GA 进化优化。

        Returns:
            参数名到 ParamSpec 的映射
        """
        return {}

    def set_params(self, params: Dict[str, float]) -> None:
        """设置参数值（进化系统调用）

        Args:
            params: 参数名到新值的映射，只更新已存在的 key
        """
        for key, value in params.items():
            if key in self._params:
                self._params[key] = value


class DetectorRegistry:
    """检测器注册中心 — 管理检测器注册、前置条件检查、冷却计时

    职责（来自 AD-3 + 残留3 决策）：
    - required_context 前置检查：不满足则跳过该检测器
    - cooldown_bars 计时：冷却未到则跳过
    - invalidates / supports 元数据透传给主干裁决逻辑
    """

    def __init__(self) -> None:
        self._detectors: Dict[str, NodeDetector] = {}
        self._cooldowns: Dict[str, int] = {}  # name -> remaining bars

    def register(self, detector: NodeDetector) -> None:
        """注册检测器

        Args:
            detector: 检测器实例，name 属性必须唯一
        """
        if detector.name in self._detectors:
            logger.warning("检测器 '%s' 已存在，将被覆盖", detector.name)
        self._detectors[detector.name] = detector
        logger.debug("注册检测器: %s", detector.name)

    def unregister(self, name: str) -> None:
        """注销检测器

        Args:
            name: 检测器名称
        """
        if name in self._detectors:
            del self._detectors[name]
            self._cooldowns.pop(name, None)
            logger.debug("注销检测器: %s", name)

    def get(self, name: str) -> Optional[NodeDetector]:
        """获取检测器实例

        Args:
            name: 检测器名称

        Returns:
            检测器实例，不存在返回 None
        """
        return self._detectors.get(name)

    def list_names(self) -> List[str]:
        """列出所有已注册检测器名称

        Returns:
            检测器名称列表
        """
        return list(self._detectors.keys())

    def evaluate_expected(
        self,
        expected_events: List[str],
        candle: dict,
        features: BarFeatures,
        context: StructureContext,
    ) -> List[NodeScore]:
        """只运行期待列表中的检测器（AD-3）

        流程：
        1. 过滤：只取 name 在 expected_events 中的检测器
        2. 冷却检查：cooldown 未到则跳过
        3. 前置检查：required_context 不满足则跳过
        4. 运行并收集结果

        Args:
            expected_events: 当前阶段期待的事件名列表
            candle: K线数据字典
            features: 三大原则打分 + 单K线特征
            context: 当前结构上下文

        Returns:
            所有通过筛选并成功检测到事件的 NodeScore 列表
        """
        results: List[NodeScore] = []

        for event_name in expected_events:
            detector = self._detectors.get(event_name)
            if detector is None:
                continue

            # 冷却检查
            remaining = self._cooldowns.get(event_name, 0)
            if remaining > 0:
                logger.debug(
                    "检测器 '%s' 冷却中，剩余 %d 根K线",
                    event_name,
                    remaining,
                )
                continue

            # 运行检测器
            try:
                score = detector.evaluate(candle, features, context)
            except Exception:
                logger.exception("检测器 '%s' 执行异常", event_name)
                continue

            if score is None:
                continue

            # 前置条件检查（在结果上检查 required_context）
            if score.required_context:
                last_event = context.last_confirmed_event
                if last_event not in score.required_context:
                    logger.debug(
                        "检测器 '%s' 前置条件不满足: 需要 %s, 当前 '%s'",
                        event_name,
                        score.required_context,
                        last_event,
                    )
                    continue

            results.append(score)

        return results

    def tick_cooldowns(self) -> None:
        """每根K线调用一次，所有冷却计数器 -1

        到达 0 时从字典中移除。
        """
        expired: List[str] = []
        for name in self._cooldowns:
            self._cooldowns[name] -= 1
            if self._cooldowns[name] <= 0:
                expired.append(name)
        for name in expired:
            del self._cooldowns[name]

    def set_cooldown(self, name: str, bars: int) -> None:
        """设置冷却期

        Args:
            name: 检测器名称
            bars: 冷却K线数
        """
        if bars > 0:
            self._cooldowns[name] = bars
            logger.debug("设置检测器 '%s' 冷却 %d 根K线", name, bars)
