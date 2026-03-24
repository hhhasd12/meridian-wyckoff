"""检测器知识库 — Python原生向量记忆系统

仿VCP TagMemo概念，但用纯Python实现。
存储层: SQLite
向量化: TF-IDF (词频-逆文档频率)
检索: numpy余弦相似度
"""

import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeRule:
    """检测器知识规则"""

    id: int = 0
    detector_name: str = ""  # e.g. "SC", "SPRING"
    rule_text: str = ""  # 规则描述
    source: str = ""  # 来源 e.g. "用户标注 2026-03-23"
    confidence: float = 0.0  # 0-1
    category: str = "threshold"  # threshold/logic/pattern
    created_at: str = ""
    times_used: int = 0  # 被引用次数


class SimpleVectorizer:
    """简单 TF-IDF 向量化器（无外部依赖，支持中英文混合）"""

    def __init__(self) -> None:
        self._vocabulary: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}

    def _tokenize(self, text: str) -> List[str]:
        """分词：中文拆为单字+双字组合，英文按单词，数字保留"""
        raw = re.findall(
            r"[\u4e00-\u9fff]+|[a-zA-Z_][a-zA-Z0-9_]*|[\d.]+",
            text.lower(),
        )
        tokens: List[str] = []
        for token in raw:
            if "\u4e00" <= token[0] <= "\u9fff":
                # 中文：拆为单字 + 相邻双字组合
                for ch in token:
                    tokens.append(ch)
                for i in range(len(token) - 1):
                    tokens.append(token[i : i + 2])
            else:
                tokens.append(token)
        return tokens

    def fit(self, texts: List[str]) -> None:
        """从文本集合建立词汇表 + IDF"""
        doc_freq: Dict[str, int] = {}
        for text in texts:
            unique_tokens = set(self._tokenize(text))
            for token in unique_tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1
                if token not in self._vocabulary:
                    self._vocabulary[token] = len(self._vocabulary)

        n_docs = max(len(texts), 1)
        self._idf = {
            token: np.log(n_docs / (1 + freq)) for token, freq in doc_freq.items()
        }

    def transform(self, text: str) -> np.ndarray:
        """文本→TF-IDF向量（L2归一化）"""
        if not self._vocabulary:
            return np.zeros(1)
        tokens = self._tokenize(text)
        vec = np.zeros(len(self._vocabulary))
        counts: Dict[str, int] = {}
        for t in tokens:
            counts[t] = counts.get(t, 0) + 1
        total = max(len(tokens), 1)
        for token, count in counts.items():
            if token in self._vocabulary:
                idx = self._vocabulary[token]
                tf = count / total
                idf = self._idf.get(token, 0.0)
                vec[idx] = tf * idf
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec


class DetectorKnowledgeBase:
    """检测器知识库 — 带向量检索的规则存储"""

    def __init__(self, db_path: str = "./data/detector_knowledge.db") -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._vectorizer = SimpleVectorizer()
        self._vectors: Dict[int, np.ndarray] = {}  # rule_id -> vector
        self._init_db()
        self._rebuild_vectors()

    def _init_db(self) -> None:
        """初始化SQLite表"""
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detector_name TEXT NOT NULL,
                rule_text TEXT NOT NULL,
                source TEXT DEFAULT '',
                confidence REAL DEFAULT 0.0,
                category TEXT DEFAULT 'threshold',
                created_at TEXT DEFAULT '',
                times_used INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_detector_name
            ON rules(detector_name)
        """)
        self._conn.commit()

    def _rebuild_vectors(self) -> None:
        """重建所有规则的向量索引"""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT id, rule_text FROM rules")
        rows = cursor.fetchall()
        if not rows:
            return
        texts = [r[1] for r in rows]
        ids = [r[0] for r in rows]
        self._vectorizer = SimpleVectorizer()
        self._vectorizer.fit(texts)
        self._vectors = {}
        for rule_id, text in zip(ids, texts):
            self._vectors[rule_id] = self._vectorizer.transform(text)

    def add_rule(
        self,
        detector_name: str,
        rule_text: str,
        source: str = "",
        confidence: float = 0.8,
        category: str = "threshold",
    ) -> KnowledgeRule:
        """添加知识规则"""
        assert self._conn is not None
        created_at = datetime.utcnow().isoformat() + "Z"
        cursor = self._conn.execute(
            "INSERT INTO rules (detector_name, rule_text, source, "
            "confidence, category, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (detector_name, rule_text, source, confidence, category, created_at),
        )
        self._conn.commit()
        rule_id = cursor.lastrowid
        assert rule_id is not None
        self._rebuild_vectors()
        rule = KnowledgeRule(
            id=rule_id,
            detector_name=detector_name,
            rule_text=rule_text,
            source=source,
            confidence=confidence,
            category=category,
            created_at=created_at,
        )
        logger.info(
            "Added knowledge rule: %s for detector %s",
            rule_text[:50],
            detector_name,
        )
        return rule

    def search_rules(
        self,
        query: str,
        detector_name: str = "",
        k: int = 5,
    ) -> List[KnowledgeRule]:
        """语义检索规则

        Args:
            query: 查询文本
            detector_name: 可选，限定检测器
            k: 返回最多k条

        Returns:
            按相似度排序的规则列表
        """
        if not self._vectors:
            return self.get_detector_rules(detector_name) if detector_name else []
        query_vec = self._vectorizer.transform(query)
        similarities: List[Tuple[int, float]] = []
        for rule_id, rule_vec in self._vectors.items():
            if len(query_vec) != len(rule_vec):
                continue
            sim = float(np.dot(query_vec, rule_vec))
            similarities.append((rule_id, sim))
        similarities.sort(key=lambda x: x[1], reverse=True)
        results: List[KnowledgeRule] = []
        for rule_id, sim in similarities[: k * 2]:
            if sim < 0.01:
                continue
            rule = self._get_rule_by_id(rule_id)
            if rule is None:
                continue
            if detector_name and rule.detector_name != detector_name:
                continue
            results.append(rule)
            if len(results) >= k:
                break
        return results

    def get_detector_rules(self, detector_name: str) -> List[KnowledgeRule]:
        """获取指定检测器的所有规则"""
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT * FROM rules WHERE detector_name = ? ORDER BY confidence DESC",
            (detector_name,),
        )
        return [self._row_to_rule(r) for r in cursor.fetchall()]

    def get_all_rules(self) -> List[KnowledgeRule]:
        """获取所有规则"""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT * FROM rules ORDER BY created_at DESC")
        return [self._row_to_rule(r) for r in cursor.fetchall()]

    def delete_rule(self, rule_id: int) -> bool:
        """删除规则"""
        assert self._conn is not None
        self._conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        self._conn.commit()
        self._vectors.pop(rule_id, None)
        return True

    def increment_usage(self, rule_id: int) -> None:
        """增加引用计数"""
        assert self._conn is not None
        self._conn.execute(
            "UPDATE rules SET times_used = times_used + 1 WHERE id = ?",
            (rule_id,),
        )
        self._conn.commit()

    def get_stats(self) -> Dict:
        """获取知识库统计"""
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT detector_name, COUNT(*) as cnt FROM rules GROUP BY detector_name"
        )
        by_detector = {r[0]: r[1] for r in cursor.fetchall()}
        total = sum(by_detector.values())
        return {
            "total_rules": total,
            "by_detector": by_detector,
            "vocabulary_size": len(self._vectorizer._vocabulary),
        }

    def _get_rule_by_id(self, rule_id: int) -> Optional[KnowledgeRule]:
        """按ID获取单条规则"""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        return self._row_to_rule(row) if row else None

    @staticmethod
    def _row_to_rule(row: tuple) -> KnowledgeRule:
        """SQLite行→KnowledgeRule"""
        return KnowledgeRule(
            id=row[0],
            detector_name=row[1],
            rule_text=row[2],
            source=row[3],
            confidence=row[4],
            category=row[5],
            created_at=row[6],
            times_used=row[7],
        )

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
