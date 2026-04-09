from __future__ import annotations

import json
import importlib
import logging
from pathlib import Path
from typing import Any

from .types import BackendPlugin, PluginContext

logger = logging.getLogger(__name__)

PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


class PluginManager:
    def __init__(self):
        self.plugins: dict[str, BackendPlugin] = {}
        self._manifests: dict[str, dict] = {}

    def discover(self, config: dict) -> list[dict]:
        """扫描 plugins/ 下所有含 manifest.json 的文件夹"""
        manifests = []
        if not PLUGINS_DIR.exists():
            logger.warning(f"插件目录不存在: {PLUGINS_DIR}")
            return []

        for folder in PLUGINS_DIR.iterdir():
            if not folder.is_dir():
                continue
            manifest_path = folder / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text("utf-8"))
                manifest["_folder"] = str(folder)
                plugin_id = manifest["id"]

                # 检查 config 中是否禁用
                plugin_config = config.get("plugins", {}).get(plugin_id, {})
                if not plugin_config.get("enabled", True):
                    logger.info(f"插件已禁用: {plugin_id}")
                    continue

                manifests.append(manifest)
                self._manifests[plugin_id] = manifest
                logger.info(f"发现插件: {plugin_id} v{manifest.get('version', '?')}")
            except Exception as e:
                logger.error(f"读取manifest失败: {manifest_path} — {e}")

        return self._topo_sort(manifests)

    def _topo_sort(self, manifests: list[dict]) -> list[dict]:
        """按dependencies拓扑排序，循环依赖报错"""
        id_map = {m["id"]: m for m in manifests}
        visited = set()
        result = []
        visiting = set()  # 检测循环

        def visit(mid: str):
            if mid in visited:
                return
            if mid in visiting:
                raise ValueError(f"循环依赖: {mid}")
            visiting.add(mid)
            m = id_map.get(mid)
            if m:
                for dep in m.get("dependencies", []):
                    if dep not in id_map:
                        raise ValueError(f"{mid} 依赖 {dep}，但 {dep} 不存在")
                    visit(dep)
            visiting.discard(mid)
            visited.add(mid)
            if m:
                result.append(m)

        for m in manifests:
            visit(m["id"])
        return result

    async def load_and_register(self, manifest: dict, ctx: PluginContext) -> None:
        """动态导入插件模块，实例化，注册"""
        folder = Path(manifest["_folder"])
        entry = manifest.get("entry", "plugin.py")
        module_name = entry.replace(".py", "")

        # 构建模块路径: backend.plugins.{plugin_id}.{module_name}
        plugin_id = manifest["id"]
        import_path = f"backend.plugins.{plugin_id}.{module_name}"

        try:
            module = importlib.import_module(import_path)
        except Exception as e:
            logger.error(f"导入插件失败: {import_path} — {e}")
            return

        # 找到 BackendPlugin 子类
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type)
                and issubclass(attr, BackendPlugin)
                and attr is not BackendPlugin):
                plugin_class = attr
                break

        if not plugin_class:
            logger.error(f"插件 {plugin_id} 中未找到 BackendPlugin 子类")
            return

        # 实例化 + 注册
        plugin = plugin_class()
        self.plugins[plugin.id] = plugin
        await plugin.on_init(ctx)
        logger.info(f"注册插件: {plugin.id} ({plugin.name})")

    def get_plugin(self, pid: str) -> BackendPlugin | None:
        """安全获取插件，不存在返回None"""
        return self.plugins.get(pid)

    async def start_all(self) -> None:
        for p in self.plugins.values():
            try:
                await p.on_start()
                logger.info(f"启动插件: {p.id}")
            except Exception as e:
                logger.error(f"启动失败: {p.id} — {e}")

    async def stop_all(self) -> None:
        """反序停止，一个失败不影响其他"""
        for p in reversed(list(self.plugins.values())):
            try:
                await p.on_stop()
                logger.info(f"停止插件: {p.id}")
            except Exception as e:
                logger.error(f"停止失败: {p.id} — {e}")

    async def health_check(self) -> dict:
        results = {}
        for pid, p in self.plugins.items():
            try:
                results[pid] = await p.on_health_check()
            except Exception as e:
                results[pid] = {"status": "error", "reason": str(e)}
        all_ok = all(v.get("status") == "ok" for v in results.values())
        return {
            "status": "ok" if all_ok else "degraded",
            "plugins": results
        }
