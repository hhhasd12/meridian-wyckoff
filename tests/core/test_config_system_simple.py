"""
ConfigSystem简化单元测试
测试src/core/config_system.py模块的核心功能

2026-03-02 更新：根据源码同步测试接口，修复所有 skipped 测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
import tempfile

try:
    from src.plugins.orchestrator.config_types import (
        TRConfig,
        DataSanitizerConfig,
        PinBodyAnalyzerConfig,
        MarketRegimeConfig,
        FVGConfig,
        WyckoffStateMachineConfig,
        SystemOrchestratorConfig,
        MarketType,
        create_default_config,
        load_config,
    )
except ImportError:
    from core.config_system import (
        TRConfig,
        DataSanitizerConfig,
        PinBodyAnalyzerConfig,
        MarketRegimeConfig,
        FVGConfig,
        WyckoffStateMachineConfig,
        SystemOrchestratorConfig,
        MarketType,
        create_default_config,
        load_config,
    )


class TestTRConfig(unittest.TestCase):
    def setUp(self):
        self.config = TRConfig()

    def test_initialization(self):
        self.assertIsNotNone(self.config)
        self.assertEqual(self.config.TR_BREAKOUT_PERCENT, 1.5)


class TestDataSanitizerConfig(unittest.TestCase):
    def setUp(self):
        self.config = DataSanitizerConfig()

    def test_initialization(self):
        self.assertIsNotNone(self.config)
        self.assertEqual(self.config.MARKET_TYPE, MarketType.CRYPTO)
        self.assertTrue(hasattr(self.config, "ANOMALY_THRESHOLD"))

    def test_to_dict(self):
        d = self.config.to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("MARKET_TYPE", d)


class TestSystemOrchestratorConfig(unittest.TestCase):
    def setUp(self):
        self.config = SystemOrchestratorConfig()

    def test_initialization(self):
        self.assertIsNotNone(self.config)
        self.assertEqual(self.config.MODE, "paper")
        self.assertIsNotNone(self.config.tr_config)


class TestConfigFunctions(unittest.TestCase):
    def test_create_default_config(self):
        config = create_default_config()
        self.assertIsInstance(config, SystemOrchestratorConfig)

    def test_load_config_invalid_file(self):
        config = load_config(config_path="nonexistent_file_xyz.json")
        self.assertIsInstance(config, SystemOrchestratorConfig)

    def test_load_config_with_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            original = create_default_config()
            original.save_to_file(tmp_path)
            loaded = load_config(config_path=tmp_path)
            self.assertIsInstance(loaded, SystemOrchestratorConfig)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_load_config_without_file(self):
        config = load_config(config_path=None)
        self.assertIsInstance(config, SystemOrchestratorConfig)


if __name__ == "__main__":
    unittest.main()
