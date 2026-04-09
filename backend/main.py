from __future__ import annotations

import logging
import yaml
import warnings
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.plugin_manager import PluginManager
from backend.core.event_bus import EventBus
from backend.core.api_registry import APIRegistry
from backend.core.storage import StorageManager
from backend.core.types import PluginContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

config_path = Path(__file__).parent.parent / "config.yaml"
if config_path.exists():
    try:
        config = yaml.safe_load(config_path.read_text("utf-8"))
    except Exception as e:
        logger.warning(f"config.yaml 解析失败: {e} — 使用空配置")
        config = {}
else:
    config = {}

pm = PluginManager()
bus = EventBus()
store = StorageManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_reg = APIRegistry(app)

    ctx = PluginContext(
        event_bus=bus,
        storage=store,
        config=config,
        get_plugin=pm.get_plugin
    )

    sorted_manifests = pm.discover(config)
    for manifest in sorted_manifests:
        await pm.load_and_register(manifest, ctx)

        plugin = pm.get_plugin(manifest["id"])
        if plugin:
            router = plugin.get_router()
            if router:
                api_reg.register_routes(plugin.id, router)
            for event_type, handler in plugin.get_subscriptions().items():
                bus.subscribe(event_type, handler)

    await pm.start_all()
    logger.info(f"Meridian 启动完成，{len(pm.plugins)} 个插件已加载")

    yield

    await pm.stop_all()
    logger.info("Meridian 已关闭")


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
