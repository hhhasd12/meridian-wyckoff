"""进化盘数据存储

独立的进化盘持仓和交易历史存储，与实盘数据分离。

功能：
1. 进化盘持仓管理（独立于实盘）
2. 进化盘交易历史记录
3. 数据持久化到 JSON 文件
4. 进化周期结果追踪
"""

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvolutionPosition:
    """进化盘持仓"""
    position_id: str
    symbol: str
    side: str
    size: float
    entry_price: float
    entry_time: str
    stop_loss: float
    take_profit: float
    confidence: float
    wyckoff_state: str
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    current_price: float = 0.0
    evolution_cycle: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionTrade:
    """进化盘交易记录"""
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    entry_time: str
    exit_time: str
    exit_reason: str
    wyckoff_state: str
    confidence: float
    evolution_cycle: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvolutionStorage:
    """进化盘数据存储

    独立的进化盘持仓和交易历史存储，与实盘数据分离。
    支持持久化到 JSON 文件。

    使用方式：
        storage = EvolutionStorage()
        storage.add_position(position_data)
        positions = storage.get_positions()
        trades = storage.get_trades()
    """

    def __init__(self, storage_path: str = "evolution_data"):
        """初始化存储

        Args:
            storage_path: 存储目录路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.positions_file = self.storage_path / "evolution_positions.json"
        self.trades_file = self.storage_path / "evolution_trades.json"
        self.state_file = self.storage_path / "evolution_state.json"

        self._positions: Dict[str, EvolutionPosition] = {}
        self._trades: List[EvolutionTrade] = []
        self._lock = threading.RLock()

        self._load_from_disk()

        logger.info("EvolutionStorage 初始化完成，存储路径: %s", self.storage_path)

    def _load_from_disk(self) -> None:
        """从磁盘加载数据"""
        with self._lock:
            if self.positions_file.exists():
                try:
                    with open(self.positions_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._positions = {
                            k: EvolutionPosition(**v) for k, v in data.items()
                        }
                    logger.info("加载 %d 个进化盘持仓", len(self._positions))
                except Exception as e:
                    logger.error("加载持仓数据失败: %s", e)

            if self.trades_file.exists():
                try:
                    with open(self.trades_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._trades = [EvolutionTrade(**t) for t in data]
                    logger.info("加载 %d 条进化盘交易历史", len(self._trades))
                except Exception as e:
                    logger.error("加载交易历史失败: %s", e)

    def _save_positions(self) -> None:
        """保存持仓到磁盘"""
        try:
            data = {k: v.to_dict() for k, v in self._positions.items()}
            with open(self.positions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("保存持仓数据失败: %s", e)

    def _save_trades(self) -> None:
        """保存交易历史到磁盘"""
        try:
            data = [t.to_dict() for t in self._trades]
            with open(self.trades_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("保存交易历史失败: %s", e)

    def add_position(self, position_data: Dict[str, Any]) -> EvolutionPosition:
        """添加持仓

        Args:
            position_data: 持仓数据

        Returns:
            创建的持仓对象
        """
        with self._lock:
            position_id = position_data.get("position_id") or self._generate_id("pos")

            position = EvolutionPosition(
                position_id=position_id,
                symbol=position_data.get("symbol", ""),
                side=position_data.get("side", "long"),
                size=position_data.get("size", 0.0),
                entry_price=position_data.get("entry_price", 0.0),
                entry_time=position_data.get("entry_time", datetime.now().isoformat()),
                stop_loss=position_data.get("stop_loss", 0.0),
                take_profit=position_data.get("take_profit", 0.0),
                confidence=position_data.get("confidence", 0.0),
                wyckoff_state=position_data.get("wyckoff_state", ""),
                evolution_cycle=position_data.get("evolution_cycle", 0),
                metadata=position_data.get("metadata", {}),
            )

            self._positions[position_id] = position
            self._save_positions()

            logger.info("添加进化盘持仓: %s %s", position.symbol, position.side)
            return position

    def update_position(
        self,
        position_id: str,
        updates: Dict[str, Any]
    ) -> Optional[EvolutionPosition]:
        """更新持仓

        Args:
            position_id: 持仓ID
            updates: 更新数据

        Returns:
            更新后的持仓对象，如果不存在则返回 None
        """
        with self._lock:
            if position_id not in self._positions:
                return None

            position = self._positions[position_id]
            for key, value in updates.items():
                if hasattr(position, key):
                    setattr(position, key, value)

            self._save_positions()
            return position

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: str = "manual",
        evolution_cycle: int = 0,
    ) -> Optional[EvolutionTrade]:
        """平仓

        Args:
            position_id: 持仓ID
            exit_price: 平仓价格
            exit_reason: 平仓原因
            evolution_cycle: 进化周期

        Returns:
            创建的交易记录，如果持仓不存在则返回 None
        """
        with self._lock:
            if position_id not in self._positions:
                return None

            position = self._positions[position_id]

            pnl = (exit_price - position.entry_price) * position.size
            if position.side == "short":
                pnl = -pnl

            pnl_pct = pnl / (position.entry_price * position.size) if position.entry_price > 0 else 0

            trade = EvolutionTrade(
                trade_id=self._generate_id("trade"),
                symbol=position.symbol,
                side=position.side,
                entry_price=position.entry_price,
                exit_price=exit_price,
                size=position.size,
                pnl=pnl,
                pnl_pct=pnl_pct,
                entry_time=position.entry_time,
                exit_time=datetime.now().isoformat(),
                exit_reason=exit_reason,
                wyckoff_state=position.wyckoff_state,
                confidence=position.confidence,
                evolution_cycle=evolution_cycle,
                metadata=position.metadata,
            )

            del self._positions[position_id]
            self._trades.append(trade)

            self._save_positions()
            self._save_trades()

            logger.info(
                "平仓进化盘持仓: %s %s, PnL=%.2f (%.2f%%)",
                position.symbol, position.side, pnl, pnl_pct * 100
            )
            return trade

    def get_positions(self) -> List[EvolutionPosition]:
        """获取所有持仓

        Returns:
            持仓列表
        """
        with self._lock:
            return list(self._positions.values())

    def get_position(self, position_id: str) -> Optional[EvolutionPosition]:
        """获取单个持仓

        Args:
            position_id: 持仓ID

        Returns:
            持仓对象，如果不存在则返回 None
        """
        with self._lock:
            return self._positions.get(position_id)

    def get_trades(self, limit: int = 100) -> List[EvolutionTrade]:
        """获取交易历史

        Args:
            limit: 返回数量限制

        Returns:
            交易历史列表（按时间倒序）
        """
        with self._lock:
            return list(reversed(self._trades[-limit:]))

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            total_trades = len(self._trades)
            winning_trades = [t for t in self._trades if t.pnl > 0]
            losing_trades = [t for t in self._trades if t.pnl <= 0]

            total_pnl = sum(t.pnl for t in self._trades)
            win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0

            avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0

            profit_factor = (
                sum(t.pnl for t in winning_trades) / abs(sum(t.pnl for t in losing_trades))
                if losing_trades and sum(t.pnl for t in losing_trades) != 0
                else float('inf') if winning_trades else 0
            )

            return {
                "total_trades": total_trades,
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "profit_factor": profit_factor,
                "open_positions": len(self._positions),
            }

    def clear_all(self) -> None:
        """清空所有数据"""
        with self._lock:
            self._positions.clear()
            self._trades.clear()
            self._save_positions()
            self._save_trades()
            logger.info("已清空所有进化盘数据")

    def save_state(self, state: Dict[str, Any]) -> None:
        """保存进化状态

        Args:
            state: 进化状态数据
        """
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            logger.error("保存进化状态失败: %s", e)

    def load_state(self) -> Dict[str, Any]:
        """加载进化状态

        Returns:
            进化状态数据
        """
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("加载进化状态失败: %s", e)
        return {}

    def _generate_id(self, prefix: str) -> str:
        """生成唯一ID

        Args:
            prefix: ID前缀

        Returns:
            唯一ID字符串
        """
        import uuid
        return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
