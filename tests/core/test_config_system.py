"""
ConfigSystem单元测试
测试src/core/config_system.py模块的所有功能

2026-03-02 更新：根据源码完整重写，修复所有 skipped 测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
import json
import tempfile

try:
    from src.core.config_system import (
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
    """TRConfig单元测试类"""

    def setUp(self):
        self.config = TRConfig()

    def test_initialization(self):
        self.assertEqual(self.config.TR_LOCK_MIN_QUALITY, 0.7)
        self.assertEqual(self.config.TR_BREAKOUT_PERCENT, 1.5)
        self.assertEqual(self.config.TR_CONFIRMATION_BARS, 3)
        self.assertEqual(self.config.TR_MIN_BARS, 20)
        self.assertEqual(self.config.SLOPE_STABILITY_THRESHOLD, 0.8)
        self.assertEqual(self.config.BOUNDARY_STABILITY_THRESHOLD, 0.75)

    def test_to_dict(self):
        config_dict = self.config.to_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertIn("TR_LOCK_MIN_QUALITY", config_dict)
        self.assertIn("TR_BREAKOUT_PERCENT", config_dict)
        self.assertIn("TR_CONFIRMATION_BARS", config_dict)
        self.assertIn("TR_MIN_BARS", config_dict)
        self.assertNotIn("_evolution_params", config_dict)

    def test_get_evolution_params(self):
        evolution_params = self.config.get_evolution_params()
        self.assertIsInstance(evolution_params, dict)
        self.assertIn("TR_BREAKOUT_PERCENT", evolution_params)
        self.assertIn("TR_CONFIRMATION_BARS", evolution_params)
        self.assertIn("SLOPE_STABILITY_THRESHOLD", evolution_params)
        self.assertIn("BOUNDARY_STABILITY_THRESHOLD", evolution_params)
        self.assertNotIn("TR_LOCK_MIN_QUALITY", evolution_params)
        self.assertNotIn("TR_MIN_BARS", evolution_params)

    def test_update_from_dict(self):
        self.config.update_from_dict({"TR_BREAKOUT_PERCENT": 2.0, "TR_CONFIRMATION_BARS": 5})
        self.assertEqual(self.config.TR_BREAKOUT_PERCENT, 2.0)
        self.assertEqual(self.config.TR_CONFIRMATION_BARS, 5)
        self.assertEqual(self.config.TR_LOCK_MIN_QUALITY, 0.7)  # 未更新的不变

    def test_update_from_dict_invalid_param(self):
        self.config.update_from_dict({"INVALID_PARAM": 999, "TR_BREAKOUT_PERCENT": 2.0})
        self.assertEqual(self.config.TR_BREAKOUT_PERCENT, 2.0)
        self.assertFalse(hasattr(self.config, "INVALID_PARAM"))

    def test_calculate_dynamic_thresholds(self):
        """TRConfig 本身无此方法；PinBodyAnalyzerConfig 才有"""
        pin_config = PinBodyAnalyzerConfig()
        thresholds = pin_config.calculate_dynamic_thresholds(
            volatility_index=1.0, market_regime="RANGING"
        )
        self.assertIsInstance(thresholds, dict)
        self.assertIn("pin_threshold", thresholds)
        self.assertIn("body_threshold", thresholds)


class TestDataSanitizerConfig(unittest.TestCase):
    """DataSanitizerConfig单元测试类"""

    def setUp(self):
        self.config = DataSanitizerConfig()

    def test_initialization(self):
        self.assertEqual(self.config.MARKET_TYPE, MarketType.CRYPTO)
        self.assertTrue(hasattr(self.config, "ANOMALY_THRESHOLD"))
        self.assertTrue(hasattr(self.config, "MAX_VOLUME_RATIO"))

    def test_market_type_specific_config(self):
        config_stock = DataSanitizerConfig()
        config_stock.MARKET_TYPE = MarketType.STOCK
        self.assertEqual(config_stock.MARKET_TYPE, MarketType.STOCK)

        config_forex = DataSanitizerConfig()
        config_forex.MARKET_TYPE = MarketType.FOREX
        self.assertEqual(config_forex.MARKET_TYPE, MarketType.FOREX)

    def test_to_dict(self):
        config_dict = self.config.to_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertIn("MARKET_TYPE", config_dict)
        self.assertIn("ANOMALY_THRESHOLD", config_dict)

    def test_get_evolution_params(self):
        evolution_params = self.config.get_evolution_params()
        self.assertIsInstance(evolution_params, dict)
        self.assertGreater(len(evolution_params), 0)


class TestPinBodyAnalyzerConfig(unittest.TestCase):
    """PinBodyAnalyzerConfig单元测试类"""

    def setUp(self):
        self.config = PinBodyAnalyzerConfig()

    def test_initialization(self):
        self.assertIsNotNone(self.config)
        self.assertTrue(hasattr(self.config, "BASE_PIN_THRESHOLD"))
        self.assertTrue(hasattr(self.config, "BASE_BODY_THRESHOLD"))

    def test_to_dict(self):
        from dataclasses import asdict
        config_dict = asdict(self.config)
        self.assertIsInstance(config_dict, dict)
        self.assertIn("BASE_PIN_THRESHOLD", config_dict)

    def test_get_evolution_params(self):
        evolution_params = self.config._evolution_params
        self.assertIsInstance(evolution_params, list)
        self.assertIn("BASE_PIN_THRESHOLD", evolution_params)
        self.assertIn("BASE_BODY_THRESHOLD", evolution_params)

    def test_calculate_dynamic_thresholds_ranging(self):
        thresholds = self.config.calculate_dynamic_thresholds(
            volatility_index=1.0, market_regime="RANGING"
        )
        self.assertIn("pin_threshold", thresholds)
        self.assertIn("body_threshold", thresholds)
        self.assertIn("volume_spike_threshold", thresholds)

    def test_calculate_dynamic_thresholds_trending(self):
        thresholds = self.config.calculate_dynamic_thresholds(
            volatility_index=1.5, market_regime="TRENDING"
        )
        self.assertIn("pin_threshold", thresholds)
        self.assertEqual(thresholds["market_regime"], "TRENDING")
        self.assertAlmostEqual(thresholds["volatility_factor"], 1.5)


class TestSystemOrchestratorConfig(unittest.TestCase):
    """SystemOrchestratorConfig单元测试类"""

    def setUp(self):
        self.config = SystemOrchestratorConfig()

    def test_initialization(self):
        self.assertIsNotNone(self.config)
        self.assertEqual(self.config.MODE, "paper")
        self.assertIsInstance(self.config.TIMEFRAME_WEIGHTS, dict)
        self.assertIsNotNone(self.config.tr_config)
        self.assertIsNotNone(self.config.data_sanitizer_config)

    def test_to_dict(self):
        config_dict = self.config.to_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertIn("MODE", config_dict)
        self.assertIn("TIMEFRAME_WEIGHTS", config_dict)

    def test_save_and_load_from_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            self.config.save_to_file(tmp_path)
            self.assertTrue(os.path.exists(tmp_path))
            loaded = SystemOrchestratorConfig.load_from_file(tmp_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.MODE, self.config.MODE)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestConfigFunctions(unittest.TestCase):
    """配置函数测试类"""

    def test_create_default_config(self):
        config = create_default_config()
        self.assertIsInstance(config, SystemOrchestratorConfig)
        self.assertEqual(config.tr_config.TR_BREAKOUT_PERCENT, 1.5)

    def test_load_config_without_file(self):
        config = load_config(config_path=None)
        self.assertIsInstance(config, SystemOrchestratorConfig)

    def test_load_config_with_file(self):
        """ 保存后重新加载 """
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

    def test_load_config_invalid_file(self):
        """加载无效路径时应回退到默认配置（不抛出异常）"""
        config = load_config(config_path="nonexistent_file_xyz.json")
        self.assertIsInstance(config, SystemOrchestratorConfig)


class TestMarketTypeEnum(unittest.TestCase):
    """MarketType枚举测试类"""

    def test_market_type_values(self):
        self.assertEqual(MarketType.STOCK.value, "STOCK")
        self.assertEqual(MarketType.CRYPTO.value, "CRYPTO")
        self.assertEqual(MarketType.FOREX.value, "FOREX")
        self.assertEqual(MarketType.FUTURES.value, "FUTURES")

    def test_market_type_from_string(self):
        self.assertEqual(MarketType("STOCK"), MarketType.STOCK)
        self.assertEqual(MarketType("CRYPTO"), MarketType.CRYPTO)
        with self.assertRaises(ValueError):
            MarketType("INVALID")


if __name__ == "__main__":
    unittest.main()
