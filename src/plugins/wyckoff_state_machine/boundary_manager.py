"""关键价位生命周期管理器

根治旧系统 C-02 问题：SC_LOW/BC_HIGH 不再被每根K线无条件覆盖。
三态生命周期：PROVISIONAL → LOCKED → INVALIDATED
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BoundaryStatus(Enum):
    """关键价位状态"""

    PROVISIONAL = "provisional"  # 候选，初次出现
    LOCKED = "locked"  # 锁定，经过测试确认
    INVALIDATED = "invalidated"  # 失效，结构破坏


@dataclass
class BoundaryInfo:
    """单个关键价位的完整生命周期信息"""

    name: str  # "SC_LOW" / "AR_HIGH" / "BC_HIGH" / "AR_LOW"
    price: float
    status: BoundaryStatus  # PROVISIONAL → LOCKED → INVALIDATED
    # 生命周期追踪
    created_at_bar: int  # 在第几根K线首次设定
    locked_at_bar: Optional[int] = None
    invalidated_at_bar: Optional[int] = None
    # 测试历史
    test_count: int = 0
    last_test_bar: Optional[int] = None
    last_test_quality: float = 0.0
    # 更新历史（防止旧bug：无条件覆盖）
    price_history: List[Tuple[float, int]] = field(default_factory=list)


class BoundaryManager:
    """关键价位生命周期管理器

    根治旧系统 C-02 问题：SC_LOW/BC_HIGH 不再被每根K线无条件覆盖。
    三态生命周期确保边界只在合适时机被修改：
    - PROVISIONAL: 候选价位，可自由更新
    - LOCKED: 经测试确认的价位，拒绝更新，需先 invalidate
    - INVALIDATED: 失效价位，不再参与导出
    """

    def __init__(self) -> None:
        self._boundaries: Dict[str, BoundaryInfo] = {}

    def propose(self, name: str, price: float, bar_index: int) -> BoundaryInfo:
        """提议新边界(PROVISIONAL)

        LOCKED 的不允许 propose 覆盖，必须先 invalidate。
        如果同名边界已存在且为 PROVISIONAL，则更新价格。

        Args:
            name: 边界名称，如 "SC_LOW", "AR_HIGH"
            price: 价格
            bar_index: 当前K线索引

        Returns:
            创建或更新后的 BoundaryInfo
        """
        existing = self._boundaries.get(name)

        if existing is not None and existing.status == BoundaryStatus.LOCKED:
            logger.warning(
                "边界 %s 已锁定(bar=%d)，拒绝 propose 覆盖。需先 invalidate",
                name,
                existing.locked_at_bar,
            )
            return existing

        if existing is not None and existing.status == BoundaryStatus.PROVISIONAL:
            # 更新已有的 PROVISIONAL 边界
            existing.price_history.append((existing.price, bar_index))
            existing.price = price
            logger.debug(
                "更新 PROVISIONAL 边界 %s: %.6f → %.6f (bar=%d)",
                name,
                existing.price_history[-1][0],
                price,
                bar_index,
            )
            return existing

        # 新建或替换 INVALIDATED
        boundary = BoundaryInfo(
            name=name,
            price=price,
            status=BoundaryStatus.PROVISIONAL,
            created_at_bar=bar_index,
            price_history=[(price, bar_index)],
        )
        self._boundaries[name] = boundary
        logger.debug("提议新边界 %s=%.6f (bar=%d)", name, price, bar_index)
        return boundary

    def lock(self, name: str, bar_index: int, test_quality: float = 1.0) -> None:
        """锁定边界(PROVISIONAL→LOCKED)

        触发条件：ST 测试不破 + 反弹确认。

        Args:
            name: 边界名称
            bar_index: 锁定时的K线索引
            test_quality: 测试质量 [0, 1]

        Raises:
            KeyError: 边界不存在
            ValueError: 边界不是 PROVISIONAL 状态
        """
        boundary = self._boundaries.get(name)
        if boundary is None:
            raise KeyError(f"边界 {name} 不存在，无法锁定")
        if boundary.status != BoundaryStatus.PROVISIONAL:
            raise ValueError(
                f"边界 {name} 状态为 {boundary.status.value}，只有 PROVISIONAL 可锁定"
            )
        boundary.status = BoundaryStatus.LOCKED
        boundary.locked_at_bar = bar_index
        boundary.last_test_quality = test_quality
        logger.info("锁定边界 %s=%.6f (bar=%d)", name, boundary.price, bar_index)

    def record_test(self, name: str, bar_index: int, quality: float) -> None:
        """记录测试（不改状态，只更新测试历史）

        Args:
            name: 边界名称
            bar_index: 测试发生的K线索引
            quality: 测试质量 [0, 1]

        Raises:
            KeyError: 边界不存在
        """
        boundary = self._boundaries.get(name)
        if boundary is None:
            raise KeyError(f"边界 {name} 不存在，无法记录测试")
        boundary.test_count += 1
        boundary.last_test_bar = bar_index
        boundary.last_test_quality = quality
        logger.debug(
            "记录边界 %s 第%d次测试 (bar=%d, quality=%.2f)",
            name,
            boundary.test_count,
            bar_index,
            quality,
        )

    def try_update(self, name: str, new_price: float, bar_index: int) -> bool:
        """尝试更新边界价格

        PROVISIONAL 允许更新，LOCKED/INVALIDATED 拒绝。

        Args:
            name: 边界名称
            new_price: 新价格
            bar_index: 更新时的K线索引

        Returns:
            是否成功更新
        """
        boundary = self._boundaries.get(name)
        if boundary is None:
            return False
        if boundary.status != BoundaryStatus.PROVISIONAL:
            return False
        boundary.price_history.append((boundary.price, bar_index))
        boundary.price = new_price
        return True

    def invalidate(self, name: str, bar_index: int) -> None:
        """失效边界(→INVALIDATED)

        触发条件：有效跌破/突破超阈值。

        Args:
            name: 边界名称
            bar_index: 失效时的K线索引

        Raises:
            KeyError: 边界不存在
        """
        boundary = self._boundaries.get(name)
        if boundary is None:
            raise KeyError(f"边界 {name} 不存在，无法失效")
        boundary.status = BoundaryStatus.INVALIDATED
        boundary.invalidated_at_bar = bar_index
        logger.info(
            "边界 %s 失效 (bar=%d, 原价=%.6f)",
            name,
            bar_index,
            boundary.price,
        )

    def to_critical_levels(self) -> Dict[str, float]:
        """导出为 WyckoffStateResult.critical_levels 兼容格式

        只导出非 INVALIDATED 的边界。

        Returns:
            {边界名称: 价格} 字典
        """
        return {
            name: info.price
            for name, info in self._boundaries.items()
            if info.status != BoundaryStatus.INVALIDATED
        }

    def get(self, name: str) -> Optional[BoundaryInfo]:
        """获取指定边界信息

        Args:
            name: 边界名称

        Returns:
            BoundaryInfo 或 None
        """
        return self._boundaries.get(name)

    def get_all(self) -> Dict[str, BoundaryInfo]:
        """获取所有边界信息

        Returns:
            所有边界的字典副本
        """
        return dict(self._boundaries)
