# Meridian 内核 (core/) — 施工文档

## 职责
内核不做任何业务。只提供基础设施，让插件专注自己的事。

## 施工顺序
1. `__init__.py`（空文件）
2. `types.py`
3. `storage.py`
4. `event_bus.py`
5. `api_registry.py`
6. `plugin_manager.py`
7. `../main.py`（backend/ 根目录）

## 完整代码

###1. types.py — 基类+ 上下文

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable
from fastapi import APIRouter


class BackendPlugin(ABC):
    """所有后端插件的基类"""
    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    dependencies: tuple = ()  # 用tuple避免可变默认值

    @abstractmethod
    async def on_init(self, ctx: PluginContext) -> None:
        """初始化：接收上下文，准备资源"""
        ...

    @abstractmethod
    async def on_start(self) -> None:
        """启动：所有插件注册完毕后调用"""
        ...

    @abstractmethod
    async def on_stop(self) -> None:
        """停止：清理资源"""
        ...

    async def on_health_check(self) -> dict:
        """健康检查，默认返回ok"""
        return {"status": "ok"}

    def get_router(self) -> APIRouter | None:
        """返回API路由，自动挂载到/api/{plugin_id}/"""
        return None

    def get_subscriptions(self) -> dict[str, Callable]:
        """声明事件订阅 {事件名: 处理函数}"""
        return {}


@dataclass
class PluginContext:
    """注入给每个插件的上下文"""
    event_bus: Any
    storage: Any
    config: dict = field(default_factory=dict)
    get_plugin: Callable = lambda pid: None
```

### 2. storage.py — JSON持久化（原子写入）

```python
from __future__ import annotations

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(__file__).parent.parent / "storage"


class StorageManager:
    def __init__(self):STORAGE_ROOT.mkdir(exist_ok=True)

    def read_json(self, category: str, name: str) -> Any:
        """读取JSON文件，损坏时返回None而不是崩溃"""
        p = STORAGE_ROOT / category / f"{name}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON损坏: {p} — {e}")
            return None

    def write_json(self, category: str, name: str, data: Any) -> None:
        """原子写入：先写临时文件，再替换。崩溃不丢数据"""
        cat_dir = STORAGE_ROOT / category
        cat_dir.mkdir(exist_ok=True)  # 动态创建分类目录

        p = cat_dir / f"{name}.json"
        tmp = cat_dir / f"{name}.json.tmp"

        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        os.replace(str(tmp), str(p))  # 原子替换
```

### 3. event_bus.py — 事件总线

```python
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subs: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subs[event_type].append(handler)
        logger.debug(f"订阅: {event_type} → {handler.__qualname__}")

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        try:
            self._subs[event_type].remove(handler)
        except ValueError:
            logger.warning(f"取消订阅失败，handler不存在: {event_type}")

    async def publish(self, event_type: str, data: Any = None) -> None:
        """串行执行所有handler，一个失败不影响其他"""
        for handler in self._subs.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"事件处理失败 [{event_type}]: {e}", exc_info=True)
```

### 4. api_registry.py — 路由注册

```python
from __future__ import annotations

import logging
from fastapi import FastAPI, APIRouter

logger = logging.getLogger(__name__)


class APIRegistry:
    def __init__(self, app: FastAPI):
        self.app = appdef register_routes(self, plugin_id: str, router: APIRouter) -> None:
        prefix = f"/api/{plugin_id}"
        self.app.include_router(router, prefix=prefix)
        logger.info(f"路由注册: {prefix}")
```

### 5. plugin_manager.py — 插件自动发现 + 拓扑排序

这是最复杂的文件。核心流程：扫描 → 排序 → 导入 → 注册 → 启动。

```python
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
        """扫描 plugins/ 下所有含manifest.json 的文件夹"""
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
```

### 6. main.py — FastAPI 入口（放在backend/ 根目录）

```python
from __future__ import annotations

import logging
import yaml
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.plugin_manager import PluginManager
from backend.core.event_bus import EventBus
from backend.core.api_registry import APIRegistry
from backend.core.storage import StorageManager
from backend.core.types import PluginContext

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# 读取全局配置
config_path = Path(__file__).parent.parent / "config.yaml"
if config_path.exists():
    config = yaml.safe_load(config_path.read_text("utf-8"))
else:
    config = {}

# 初始化内核
pm = PluginManager()
bus = EventBus()
store = StorageManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动和关闭逻辑"""
    api_reg = APIRegistry(app)

    # 构建上下文
    ctx = PluginContext(
        event_bus=bus,
        storage=store,
        config=config,
        get_plugin=pm.get_plugin
    )

    # 发现→ 排序 → 注册 → 接线→ 启动
    sorted_manifests = pm.discover(config)
    for manifest in sorted_manifests:
        await pm.load_and_register(manifest, ctx)

        plugin = pm.get_plugin(manifest["id"])
        if plugin:
            #挂载API路由
            router = plugin.get_router()
            if router:
                api_reg.register_routes(plugin.id, router)# 注册事件订阅
            for event_type, handler in plugin.get_subscriptions().items():
                bus.subscribe(event_type, handler)

    await pm.start_all()
    logger.info(f"Meridian 启动完成，{len(pm.plugins)} 个插件已加载")

    yield  # 运行中

    await pm.stop_all()
    logger.info("Meridian 已关闭")


# 创建 FastAPI 应用
app = FastAPI(title="Meridian", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/system/health")
async def health():
    return await pm.health_check()


@app.get("/api/system/plugins")
async def plugins():
    return [
        {"id": p.id, "name": p.name, "version": p.version}
        for p in pm.plugins.values()
    ]
```

## 插件自动发现机制

内核启动时扫描 `backend/plugins/` 下所有子文件夹：
1. 找到 `manifest.json` →读取插件元数据
2. 检查 `config.yaml` 中是否 `enabled: false` → 跳过禁用的
3. 按 `dependencies` 拓扑排序 → 循环依赖报错拒绝启动
4. `importlib` 动态导入 `entry` 指定的模块 → 找到 `BackendPlugin` 子类
5. 实例化 → `on_init(ctx)` →挂路由 → 挂事件 → `on_start()`

## manifest.json 规范

每个插件文件夹必须包含 manifest.json：
```json
{
  "id": "my_plugin",
  "name": "显示名称",
  "version": "0.1.0",
  "description": "一句话说明",
  "entry": "plugin.py",
  "dependencies": [],
  "events": {
    "publishes": ["my_plugin.event_name"],
    "subscribes": ["other_plugin.event_name"]
  }
}
```

##PluginContext — 插件能用什么

```python
ctx.event_bus   # 发布/订阅事件
ctx.storage     # 读写 JSON（原子写入）
ctx.config      # 全局配置（来自 config.yaml）
ctx.get_plugin  # 获取其他插件实例（返回 None 如果不存在）
```

## 事件命名规范

`{plugin_id}.{action}`

| 事件 | 发布者 | 含义 |
|------|--------|------|
| candle.loaded | datasource | K线数据加载完成 |
| annotation.created | annotation | 标注创建 |
| annotation.updated | annotation | 标注更新 |
| annotation.deleted | annotation | 标注删除 |

## 施工注意
- 所有日志用 `logging` 模块，不用 `print`
- Python 文件头部统一 `from __future__ import annotations`
- 端口 6100（config.yaml 配置）
- main.py 需要 `pip install pyyaml`（读取config.yaml）
- 启动后零插件应正常运行：GET /api/system/health → 200