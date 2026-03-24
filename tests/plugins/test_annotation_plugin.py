"""标注插件测试 — 验证 CRUD 操作和 JSONL 持久化"""

import json
import os

import pytest

from src.kernel.types import HealthStatus
from src.plugins.annotation.plugin import (
    AnnotationPlugin,
    WyckoffAnnotation,
)


@pytest.fixture
def plugin(tmp_path):
    """创建使用临时目录的标注插件实例"""
    p = AnnotationPlugin(name="annotation")
    p._config = {"data_dir": str(tmp_path / "annotations")}
    p.on_load()
    return p


@pytest.fixture
def event_data():
    """事件标注测试数据"""
    return {
        "type": "event",
        "symbol": "ETH/USDT",
        "timeframe": "H4",
        "event_type": "SC",
        "start_time": 1700000000000,
        "end_time": 1700003600000,
        "start_bar_index": 100,
        "end_bar_index": 102,
        "confidence": 0.9,
        "notes": "明显的卖出高潮",
    }


class TestCreateAnnotation:
    """测试创建标注"""

    def test_create_event_annotation(self, plugin, event_data):
        """创建事件标注，验证 id 和 created_at 非空"""
        result = plugin.create_annotation(event_data)
        assert isinstance(result, WyckoffAnnotation)
        assert result.id != ""
        assert result.created_at != ""
        assert result.type == "event"
        assert result.event_type == "SC"
        assert result.symbol == "ETH/USDT"
        assert result.confidence == 0.9

    def test_create_level_annotation(self, plugin):
        """创建水平线标注"""
        data = {
            "type": "level",
            "symbol": "BTC/USDT",
            "timeframe": "H1",
            "price": 42000.0,
            "level_label": "SC_LOW",
            "confidence": 0.85,
        }
        result = plugin.create_annotation(data)
        assert result.type == "level"
        assert result.price == 42000.0
        assert result.level_label == "SC_LOW"

    def test_create_structure_annotation(self, plugin):
        """创建结构标注"""
        data = {
            "type": "structure",
            "symbol": "ETH/USDT",
            "timeframe": "H4",
            "structure_type": "ACCUMULATION",
            "start_bar_index": 0,
            "end_bar_index": 200,
        }
        result = plugin.create_annotation(data)
        assert result.type == "structure"
        assert result.structure_type == "ACCUMULATION"

    def test_create_missing_required_field(self, plugin):
        """缺少必需字段应抛出 ValueError"""
        with pytest.raises(ValueError, match="缺少必需字段"):
            plugin.create_annotation({"type": "event"})


class TestGetAnnotations:
    """测试获取标注"""

    def test_get_empty(self, plugin):
        """无标注时返回空列表"""
        result = plugin.get_annotations("ETH/USDT", "H4")
        assert result == []

    def test_get_multiple(self, plugin, event_data):
        """创建多个标注后验证列表长度"""
        plugin.create_annotation(event_data)
        event_data2 = event_data.copy()
        event_data2["event_type"] = "AR"
        plugin.create_annotation(event_data2)

        result = plugin.get_annotations("ETH/USDT", "H4")
        assert len(result) == 2
        types = [a["event_type"] for a in result]
        assert "SC" in types
        assert "AR" in types


class TestDeleteAnnotation:
    """测试删除标注"""

    def test_delete_existing(self, plugin, event_data):
        """创建→删除→验证列表为空"""
        annotation = plugin.create_annotation(event_data)
        deleted = plugin.delete_annotation(annotation.id, "ETH/USDT", "H4")
        assert deleted is True
        remaining = plugin.get_annotations("ETH/USDT", "H4")
        assert len(remaining) == 0

    def test_delete_nonexistent(self, plugin):
        """删除不存在的标注返回 False"""
        result = plugin.delete_annotation("nonexistent-id", "ETH/USDT", "H4")
        assert result is False

    def test_delete_preserves_others(self, plugin, event_data):
        """删除一个标注不影响其他标注"""
        a1 = plugin.create_annotation(event_data)
        data2 = event_data.copy()
        data2["event_type"] = "AR"
        a2 = plugin.create_annotation(data2)

        plugin.delete_annotation(a1.id, "ETH/USDT", "H4")
        remaining = plugin.get_annotations("ETH/USDT", "H4")
        assert len(remaining) == 1
        assert remaining[0]["id"] == a2.id


class TestFilePersistence:
    """测试文件持久化"""

    def test_persistence_across_instances(self, tmp_path):
        """创建→重新实例化→验证数据仍在"""
        data_dir = str(tmp_path / "annotations")

        # 第一个实例写入
        p1 = AnnotationPlugin(name="annotation")
        p1._config = {"data_dir": data_dir}
        p1.on_load()
        p1.create_annotation(
            {
                "type": "event",
                "symbol": "ETH/USDT",
                "timeframe": "H4",
                "event_type": "SPRING",
            }
        )
        p1.on_unload()

        # 第二个实例读取
        p2 = AnnotationPlugin(name="annotation")
        p2._config = {"data_dir": data_dir}
        p2.on_load()
        result = p2.get_annotations("ETH/USDT", "H4")
        assert len(result) == 1
        assert result[0]["event_type"] == "SPRING"

    def test_jsonl_file_format(self, plugin, event_data):
        """验证 JSONL 文件每行一个 JSON 对象"""
        plugin.create_annotation(event_data)
        file_path = plugin._get_file_path("ETH/USDT", "H4")
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["type"] == "event"
        assert obj["event_type"] == "SC"


class TestAnnotationCount:
    """测试标注计数"""

    def test_count_empty(self, plugin):
        """无标注时返回空字典"""
        counts = plugin.get_annotation_count()
        assert counts == {}

    def test_count_multiple_files(self, plugin):
        """多个文件的计数"""
        plugin.create_annotation(
            {
                "type": "event",
                "symbol": "ETH/USDT",
                "timeframe": "H4",
                "event_type": "SC",
            }
        )
        plugin.create_annotation(
            {
                "type": "event",
                "symbol": "ETH/USDT",
                "timeframe": "H4",
                "event_type": "AR",
            }
        )
        plugin.create_annotation(
            {
                "type": "level",
                "symbol": "BTC/USDT",
                "timeframe": "H1",
                "price": 42000.0,
                "level_label": "SC_LOW",
            }
        )

        counts = plugin.get_annotation_count()
        assert counts.get("ETH_USDT_H4") == 2
        assert counts.get("BTC_USDT_H1") == 1


class TestHealthCheck:
    """测试健康检查"""

    def test_healthy_after_load(self, plugin):
        """加载后健康检查正常"""
        result = plugin.health_check()
        assert result.status == HealthStatus.HEALTHY

    def test_unhealthy_before_load(self):
        """未加载时健康检查不健康"""
        p = AnnotationPlugin(name="annotation")
        result = p.health_check()
        assert result.status == HealthStatus.UNHEALTHY
