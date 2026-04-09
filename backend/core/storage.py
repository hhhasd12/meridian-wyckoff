from __future__ import annotations

from typing import Any
import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(__file__).parent.parent / "storage"


class StorageManager:
    def __init__(self):
        STORAGE_ROOT.mkdir(exist_ok=True)

    @property
    def base_path(self) -> Path:
        return STORAGE_ROOT

    def read_json(self, category: str, name: str) -> Any:
        p = STORAGE_ROOT / category / f"{name}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON损坏: {p} — {e}")
            return None

    def write_json(self, category: str, name: str, data: Any) -> None:
        cat_dir = STORAGE_ROOT / category
        cat_dir.mkdir(exist_ok=True)

        p = cat_dir / f"{name}.json"
        tmp = cat_dir / f"{name}.json.tmp"

        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(p))
