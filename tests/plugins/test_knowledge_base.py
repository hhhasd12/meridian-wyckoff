"""检测器知识库单元测试"""

import os

import pytest

from src.plugins.annotation.knowledge import (
    DetectorKnowledgeBase,
    KnowledgeRule,
    SimpleVectorizer,
)


@pytest.fixture
def kb(tmp_path):
    """创建临时知识库"""
    db_path = str(tmp_path / "test_knowledge.db")
    _kb = DetectorKnowledgeBase(db_path)
    yield _kb
    _kb.close()


class TestSimpleVectorizer:
    """SimpleVectorizer 测试"""

    def test_tokenize_chinese_english_mixed(self):
        v = SimpleVectorizer()
        tokens = v._tokenize("SC检测器 threshold=0.35 逻辑")
        assert "sc" in tokens  # 英文小写化
        assert "threshold" in tokens
        assert "0.35" in tokens
        assert any("\u4e00" <= c <= "\u9fff" for t in tokens for c in t)

    def test_fit_and_transform(self):
        v = SimpleVectorizer()
        v.fit(["SC volume spike", "SPRING low volume test"])
        vec = v.transform("SC volume spike")
        assert vec.shape[0] > 0
        assert float(vec.sum()) != 0.0  # 非零向量

    def test_empty_vocabulary(self):
        v = SimpleVectorizer()
        vec = v.transform("some text")
        assert vec.shape == (1,)  # fallback 大小


class TestAddRule:
    """add_rule 测试"""

    def test_add_rule_returns_correct_fields(self, kb):
        rule = kb.add_rule(
            detector_name="SC",
            rule_text="SC需要放量突破支撑位",
            source="用户标注 2026-03-23",
            confidence=0.9,
            category="logic",
        )
        assert isinstance(rule, KnowledgeRule)
        assert rule.id > 0
        assert rule.detector_name == "SC"
        assert rule.rule_text == "SC需要放量突破支撑位"
        assert rule.source == "用户标注 2026-03-23"
        assert rule.confidence == 0.9
        assert rule.category == "logic"
        assert rule.created_at.endswith("Z")
        assert rule.times_used == 0


class TestGetDetectorRules:
    """get_detector_rules 测试"""

    def test_filter_by_detector(self, kb):
        kb.add_rule("SC", "SC放量规则")
        kb.add_rule("SPRING", "SPRING低量测试")
        kb.add_rule("SC", "SC价格跌破支撑")

        sc_rules = kb.get_detector_rules("SC")
        assert len(sc_rules) == 2
        assert all(r.detector_name == "SC" for r in sc_rules)

        spring_rules = kb.get_detector_rules("SPRING")
        assert len(spring_rules) == 1


class TestSearchRulesSemantic:
    """语义检索测试"""

    def test_search_returns_relevant_results(self, kb):
        kb.add_rule("SC", "SC需要明显放量，volume_ratio > 1.5")
        kb.add_rule("SC", "SC价格应跌破前期支撑位")
        kb.add_rule("SPRING", "SPRING测试需要低量回踩")
        kb.add_rule("AR", "AR自动反弹后价格快速恢复")

        results = kb.search_rules("放量突破", k=3)
        assert len(results) > 0
        # "放量"应优先匹配含"放量"的规则
        texts = [r.rule_text for r in results]
        assert any("放量" in t for t in texts)


class TestSearchByDetector:
    """限定检测器语义检索"""

    def test_search_filtered_by_detector(self, kb):
        kb.add_rule("SC", "SC需要放量")
        kb.add_rule("SPRING", "SPRING需要放量测试")

        results = kb.search_rules("放量", detector_name="SC", k=5)
        assert all(r.detector_name == "SC" for r in results)


class TestDeleteRule:
    """删除规则测试"""

    def test_delete_removes_from_db(self, kb):
        rule = kb.add_rule("SC", "临时规则")
        assert len(kb.get_all_rules()) == 1

        kb.delete_rule(rule.id)
        assert len(kb.get_all_rules()) == 0


class TestIncrementUsage:
    """引用计数测试"""

    def test_usage_increments(self, kb):
        rule = kb.add_rule("SC", "测试规则")
        assert rule.times_used == 0

        kb.increment_usage(rule.id)
        kb.increment_usage(rule.id)
        updated = kb._get_rule_by_id(rule.id)
        assert updated is not None
        assert updated.times_used == 2


class TestGetStats:
    """统计信息测试"""

    def test_stats_structure(self, kb):
        kb.add_rule("SC", "规则1")
        kb.add_rule("SC", "规则2")
        kb.add_rule("SPRING", "规则3")

        stats = kb.get_stats()
        assert stats["total_rules"] == 3
        assert stats["by_detector"]["SC"] == 2
        assert stats["by_detector"]["SPRING"] == 1
        assert stats["vocabulary_size"] > 0


class TestEmptyDB:
    """空数据库测试"""

    def test_empty_search(self, kb):
        results = kb.search_rules("任何查询")
        assert results == []

    def test_empty_stats(self, kb):
        stats = kb.get_stats()
        assert stats["total_rules"] == 0
        assert stats["by_detector"] == {}

    def test_empty_get_detector(self, kb):
        assert kb.get_detector_rules("SC") == []

    def test_empty_get_all(self, kb):
        assert kb.get_all_rules() == []


class TestPersistence:
    """持久化测试 — 关闭重开后数据仍在"""

    def test_data_survives_restart(self, tmp_path):
        db_path = str(tmp_path / "persist_test.db")

        # 第一次打开写入
        kb1 = DetectorKnowledgeBase(db_path)
        kb1.add_rule("SC", "持久化测试规则", confidence=0.95)
        kb1.close()

        # 第二次打开读取
        kb2 = DetectorKnowledgeBase(db_path)
        rules = kb2.get_all_rules()
        assert len(rules) == 1
        assert rules[0].rule_text == "持久化测试规则"
        assert rules[0].confidence == 0.95
        kb2.close()
