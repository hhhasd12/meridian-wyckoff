"""集成测试共享 fixture

提供 session-scoped WyckoffApp 实例，避免每个测试文件重复创建。
所有集成测试共享同一个 WyckoffApp + TestClient。

使用方法：
    def test_xxx(loaded_app, api_client, sample_ohlcv):
        ...
"""

import os
import pathlib
import time
from typing import Any, Dict, Generator

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.app import app, app_state
from src.app import WyckoffApp
from tests.fixtures.ohlcv_generator import make_multi_tf_data, make_ohlcv


@pytest.fixture(scope="session")
def loaded_app(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[WyckoffApp, None, None]:
    """Session-scoped WyckoffApp — 真实加载所有插件（整个测试会话只创建一次）

    - 使用临时目录存放 journal，避免恢复旧持仓
    - 清理 position_manager 可能恢复的旧持仓
    - 注入多时间框架 OHLCV 数据到 data_pipeline 缓存
    """
    # 备份旧 journal 避免干扰
    old_journal = pathlib.Path("./data/position_journal.jsonl")
    old_journal_bak = pathlib.Path("./data/position_journal.jsonl.bak.integration")
    if old_journal.exists():
        if old_journal_bak.exists():
            old_journal_bak.unlink()
        old_journal.rename(old_journal_bak)

    wa = WyckoffApp(config_path="config.yaml", plugins_dir="src/plugins")
    wa.discover_and_load()

    # 清理 position_manager 恢复的旧持仓
    pm = wa.plugin_manager.get_plugin("position_manager")
    if pm is not None and hasattr(pm, "_manager") and pm._manager is not None:  # type: ignore[attr-defined]
        pm._manager.positions.clear()  # type: ignore[attr-defined]

    # 注入多TF数据到 data_pipeline 缓存
    dp = wa.plugin_manager.get_plugin("data_pipeline")
    if dp is not None and hasattr(dp, "_cache"):
        multi_tf = make_multi_tf_data(h4_bars=200, trend="up", seed=42)
        for tf, df in multi_tf.items():
            dp._cache[("BTC/USDT", tf)] = df  # type: ignore[attr-defined]

    yield wa

    wa.plugin_manager.unload_all()

    # 恢复旧 journal
    if old_journal_bak.exists():
        if old_journal.exists():
            old_journal.unlink()
        old_journal_bak.rename(old_journal)


@pytest.fixture(scope="session")
def api_client(loaded_app: WyckoffApp) -> Generator[TestClient, None, None]:
    """Session-scoped FastAPI TestClient — 注入真实 WyckoffApp"""
    original_app_ref = app_state.wyckoff_app
    original_time = app_state.start_time

    app_state.wyckoff_app = loaded_app
    app_state.start_time = time.time() - 120.0  # 模拟已运行 2 分钟

    tc = TestClient(app, raise_server_exceptions=False)
    yield tc

    app_state.wyckoff_app = original_app_ref
    app_state.start_time = original_time


@pytest.fixture(scope="session")
def sample_ohlcv() -> Dict[str, pd.DataFrame]:
    """Session-scoped 多时间框架 OHLCV 测试数据"""
    return make_multi_tf_data(h4_bars=200, trend="up", seed=42)


@pytest.fixture(scope="session")
def sample_ohlcv_single() -> pd.DataFrame:
    """Session-scoped 单时间框架 OHLCV 测试数据（H4, 100 bars, 上升趋势）"""
    return make_ohlcv(n=100, start_price=50000.0, trend="up", seed=42)
