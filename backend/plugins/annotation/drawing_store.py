from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DrawingStore:
    def __init__(self, storage):
        self.storage = storage

    def get_all(self, symbol: str) -> list:
        """获取某标的的所有标注"""
        return self.storage.read_json("drawings", symbol) or []

    def save_all(self, symbol: str, drawings: list) -> None:
        """保存所有标注（原子写入）"""
        self.storage.write_json("drawings", symbol, drawings)

    def create(self, symbol: str, drawing: dict) -> dict:
        """创建标注。W3: 检查ID唯一性，重复则覆盖"""
        ds = self.get_all(symbol)
        existing_idx = next((i for i, d in enumerate(ds) if d["id"] == drawing["id"]), None)
        if existing_idx is not None:
            logger.warning(f"重复ID，覆盖已有标注: {drawing['id']}")
            ds[existing_idx] = {**ds[existing_idx], **drawing}
        else:
            ds.append(drawing)
        self.save_all(symbol, ds)
        logger.info(f"创建标注: {symbol} / {drawing.get('id', '?')}")
        return drawing

    def update(self, symbol: str, drawing_id: str, updates: dict) -> dict | None:
        """更新标注，返回更新后的标注，不存在返回None"""
        ds = self.get_all(symbol)
        for i, d in enumerate(ds):
            if d["id"] == drawing_id:
                ds[i] = {**d, **updates}
                self.save_all(symbol, ds)
                logger.info(f"更新标注: {symbol} / {drawing_id}")
                return ds[i]
        return None

    def delete(self, symbol: str, drawing_id: str) -> bool:
        """删除标注，返回是否成功"""
        ds = self.get_all(symbol)
        new = [d for d in ds if d["id"] != drawing_id]
        if len(new) < len(ds):
            self.save_all(symbol, new)
            logger.info(f"删除标注: {symbol} / {drawing_id}")
            return True
        return False
