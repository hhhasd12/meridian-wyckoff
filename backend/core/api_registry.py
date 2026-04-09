from __future__ import annotations

import logging
from fastapi import FastAPI, APIRouter

logger = logging.getLogger(__name__)


class APIRegistry:
    def __init__(self, app: FastAPI):
        self.app = app

    def register_routes(self, plugin_id: str, router: APIRouter) -> None:
        prefix = f"/api/{plugin_id}"
        self.app.include_router(router, prefix=prefix)
        logger.info(f"路由注册: {prefix}")
