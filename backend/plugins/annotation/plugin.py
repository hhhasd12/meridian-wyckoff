from __future__ import annotations

from backend.core.types import BackendPlugin
from .routes import create_router


class AnnotationPlugin(BackendPlugin):
    id = "annotation"
    name = "标注"
    version = "0.1.0"

    async def on_init(self, ctx):
        self.ctx = ctx
        self.storage = ctx.storage

    async def on_start(self):
        pass

    async def on_stop(self):
        pass

    def get_router(self):
        return create_router(self)
