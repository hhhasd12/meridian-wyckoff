"""持仓日志 — 崩溃恢复与交易记录持久化

通过 JSONL 文件记录每一次仓位变化（open/update/close），
系统重启时从日志重建所有未平仓持仓。
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List

from src.kernel.types import TradingSignal
from src.plugins.position_manager.types import (
    ExitReason,
    Position,
    PositionSide,
    PositionStatus,
    TradeResult,
)

logger = logging.getLogger(__name__)


class PositionJournal:
    """持仓日志 — 每次仓位变化写盘，崩溃后可恢复

    设计:
    1. 每次 open/update/close 操作都追加写入 JSONL 文件
    2. 启动时读取日志，重建当前 open positions
    3. 定期压缩（compact）日志文件，移除已关闭的持仓

    Attributes:
        journal_path: JSONL 日志文件路径
    """

    def __init__(self, journal_path: str = "./data/position_journal.jsonl") -> None:
        """初始化持仓日志

        Args:
            journal_path: JSONL 日志文件路径，默认 ./data/position_journal.jsonl
        """
        self.journal_path = journal_path
        self._lock = threading.Lock()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """确保日志文件所在目录存在"""
        directory = os.path.dirname(self.journal_path)
        if directory:
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                logger.error("无法创建日志目录 %s: %s", directory, e)

    def _append_entry(self, entry: Dict[str, Any]) -> None:
        """追加一条日志记录到 JSONL 文件（线程安全）

        Args:
            entry: 日志条目字典，将被序列化为 JSON 行
        """
        with self._lock:
            try:
                with open(self.journal_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                logger.error("写入日志失败: %s", e)

    def _read_all_entries(self) -> List[Dict[str, Any]]:
        """读取所有日志条目

        Returns:
            日志条目列表，每个条目为字典。文件不存在或为空返回空列表。
        """
        if not os.path.exists(self.journal_path):
            return []

        entries: List[Dict[str, Any]] = []
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        entries.append(json.loads(stripped))
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "日志第 %d 行 JSON 解析失败，跳过: %s", line_num, e
                        )
        except OSError as e:
            logger.error("读取日志失败: %s", e)
        return entries

    def record_open(self, position: Position) -> None:
        """记录开仓事件

        Args:
            position: 新开仓的持仓对象
        """
        entry: Dict[str, Any] = {
            "event": "open",
            "timestamp": datetime.now().isoformat(),
            "symbol": position.symbol,
            "position": position.to_dict(),
        }
        # to_dict() 不含 original_size 和 entry_atr，补充写入
        entry["position"]["original_size"] = position.original_size
        entry["position"]["entry_atr"] = position.entry_atr
        self._append_entry(entry)
        logger.info("日志记录: 开仓 %s %s", position.symbol, position.side.value)

    def record_update(self, symbol: str, updates: Dict[str, Any]) -> None:
        """记录仓位更新事件

        Args:
            symbol: 交易对标识，如 "BTC/USDT"
            updates: 更新的字段字典，如 {"stop_loss": 29000, "size": 0.5}
        """
        entry: Dict[str, Any] = {
            "event": "update",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "updates": updates,
        }
        self._append_entry(entry)
        logger.debug("日志记录: 更新 %s %s", symbol, list(updates.keys()))

    def record_close(self, symbol: str, trade_result: TradeResult) -> None:
        """记录平仓事件

        Args:
            symbol: 交易对标识
            trade_result: 交易结果对象
        """
        entry: Dict[str, Any] = {
            "event": "close",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "result": trade_result.to_dict(),
        }
        self._append_entry(entry)
        logger.info(
            "日志记录: 平仓 %s PnL=%.4f (%s)",
            symbol,
            trade_result.pnl,
            trade_result.exit_reason.value,
        )

    def recover_positions(self) -> Dict[str, Position]:
        """从日志恢复所有 open positions

        重播全部日志事件，重建当前仍处于 OPEN 状态的持仓。

        Returns:
            以 symbol 为键、Position 为值的字典
        """
        entries = self._read_all_entries()
        if not entries:
            logger.info("无日志文件或日志为空，无需恢复")
            return {}

        positions: Dict[str, Position] = {}

        for entry in entries:
            event = entry.get("event")
            symbol = entry.get("symbol", "")

            try:
                if event == "open":
                    pos_data = entry.get("position", {})
                    position = self._dict_to_position(pos_data)
                    positions[symbol] = position
                elif event == "update":
                    if symbol in positions:
                        updates = entry.get("updates", {})
                        self._apply_updates(positions[symbol], updates)
                elif event == "close":
                    positions.pop(symbol, None)
                else:
                    logger.warning("未知日志事件类型: %s", event)
            except (KeyError, ValueError, TypeError) as e:
                logger.error(
                    "恢复日志条目失败 (event=%s, symbol=%s): %s", event, symbol, e
                )

        logger.info("日志恢复完成: 找到 %d 个 open positions", len(positions))
        return positions

    def compact(self) -> None:
        """压缩日志文件，只保留当前 open positions 的最新状态

        流程:
        1. 恢复当前 open positions
        2. 将 open positions 作为 open 事件重写日志
        3. 原子替换旧日志文件
        """
        positions = self.recover_positions()

        with self._lock:
            try:
                tmp_path = self.journal_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    for position in positions.values():
                        entry: Dict[str, Any] = {
                            "event": "open",
                            "timestamp": datetime.now().isoformat(),
                            "symbol": position.symbol,
                            "position": position.to_dict(),
                        }
                        entry["position"]["original_size"] = position.original_size
                        entry["position"]["entry_atr"] = position.entry_atr
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())

                # 原子替换（os.replace 在 Windows 上也可覆盖已存在文件）
                os.replace(tmp_path, self.journal_path)

                logger.info("日志压缩完成: 保留 %d 个 open positions", len(positions))
            except OSError as e:
                logger.error("日志压缩失败: %s", e)

    def get_trade_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的交易日志（close 事件）

        Args:
            limit: 最多返回的记录数量，默认 100

        Returns:
            最近的平仓交易记录列表，按时间倒序排列
        """
        entries = self._read_all_entries()
        close_entries = [e for e in entries if e.get("event") == "close"]
        # 倒序返回最近的记录
        return close_entries[-limit:][::-1]

    def _dict_to_position(self, data: Dict[str, Any]) -> Position:
        """从字典数据重建 Position 对象

        处理枚举和日期时间的反序列化。

        Args:
            data: Position.to_dict() 产生的字典（含补充字段）

        Returns:
            重建的 Position 对象

        Raises:
            KeyError: 当必需字段缺失时
            ValueError: 当枚举值无效时
        """
        side = PositionSide(data["side"])
        status = PositionStatus(data.get("status", "open"))
        entry_signal = TradingSignal(data["entry_signal"])
        entry_time = datetime.fromisoformat(data["entry_time"])

        partial_profits: List[float] = data.get("partial_profits_taken", [])
        metadata: Dict[str, Any] = data.get("metadata", {})

        position = Position(
            symbol=data["symbol"],
            side=side,
            size=float(data["size"]),
            entry_price=float(data["entry_price"]),
            entry_time=entry_time,
            stop_loss=float(data["stop_loss"]),
            take_profit=float(data["take_profit"]),
            signal_confidence=float(data["signal_confidence"]),
            wyckoff_state=str(data["wyckoff_state"]),
            entry_signal=entry_signal,
            original_size=float(data.get("original_size", data["size"])),
            entry_atr=float(data.get("entry_atr", 0.0)),
            leverage=float(data.get("leverage", 1.0)),
            status=status,
            trailing_stop_activated=bool(data.get("trailing_stop_activated", False)),
            partial_profits_taken=partial_profits,
            highest_price=float(data.get("highest_price", data["entry_price"])),
            lowest_price=float(data.get("lowest_price", data["entry_price"])),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            unrealized_pnl_pct=float(data.get("unrealized_pnl_pct", 0.0)),
            metadata=metadata,
        )
        return position

    def _apply_updates(self, position: Position, updates: Dict[str, Any]) -> None:
        """将更新字典应用到 Position 对象

        处理特殊字段（枚举、列表）的类型转换。

        Args:
            position: 要更新的持仓对象
            updates: 字段更新字典
        """
        for key, value in updates.items():
            if key == "side":
                position.side = PositionSide(value)
            elif key == "status":
                position.status = PositionStatus(value)
            elif key == "entry_signal":
                position.entry_signal = TradingSignal(value)
            elif key == "entry_time":
                position.entry_time = datetime.fromisoformat(str(value))
            elif hasattr(position, key):
                setattr(position, key, value)
            else:
                logger.warning("未知的仓位字段更新: %s", key)
