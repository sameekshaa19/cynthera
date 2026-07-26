"""Knowledge Store — SQLite-backed semantic knowledge base for prior drug repurposing knowledge.

Implements Phase 2 Prior Knowledge Agent storage using SQLite with JSON.
Provides TF-IDF cosine similarity search over known drug-disease pairs
and established mechanistic knowledge.

Reference: Phase 2 — Prior Knowledge Agent
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Seed Knowledge Base
# ─────────────────────────────────────────────

_SEED_KNOWLEDGE: list[dict[str, Any]] = [
    {
        "drug": "sildenafil",
        "disease": "pulmonary arterial hypertension",
        "aliases_drug": ["viagra", "revatio"],
        "aliases_disease": ["pah", "pulmonary hypertension"],
        "mechanism": "PDE5 inhibitor → cGMP elevation → pulmonary vasodilation → reduced vascular resistance",
        "evidence_level": "HIGH",
        "established": True,
        "year": 2005,
        "notes": "FDA-approved repurposing from erectile dysfunction. Strong RCT evidence in PAH.",
    },
    {
        "drug": "metformin",
        "disease": "cancer",
        "aliases_drug": ["glucophage"],
        "aliases_disease": ["tumor", "oncology", "neoplasm", "carcinoma"],
        "mechanism": "AMPK activation → mTOR inhibition → reduced cell proliferation",
        "evidence_level": "MEDIUM",
        "established": False,
        "year": 2010,
        "notes": "Epidemiological evidence of reduced cancer incidence in diabetics. Multiple RCTs ongoing.",
    },
    {
        "drug": "thalidomide",
        "disease": "multiple myeloma",
        "aliases_drug": ["thalomid"],
        "aliases_disease": ["myeloma", "plasma cell"],
        "mechanism": "Anti-angiogenic + immunomodulatory → reduced tumor vasculature + plasma cell death",
        "evidence_level": "HIGH",
        "established": True,
        "year": 2006,
        "notes": "Successful repurposing from morning sickness drug with strict REMS program.",
    },
    {
        "drug": "aspirin",
        "disease": "colorectal cancer",
        "aliases_drug": ["acetylsalicylic acid", "asa"],
        "aliases_disease": ["colon cancer", "rectal cancer", "bowel cancer"],
        "mechanism": "COX inhibition → reduced prostaglandin E2 → decreased tumor cell survival",
        "evidence_level": "MEDIUM",
        "established": False,
        "year": 2012,
        "notes": "Observational studies show 20-40% risk reduction. RCTs ongoing for prevention.",
    },
    {
        "drug": "itraconazole",
        "disease": "non-small cell lung cancer",
        "aliases_drug": ["sporanox"],
        "aliases_disease": ["nsclc", "lung cancer", "lung carcinoma"],
        "mechanism": "Hedgehog pathway inhibition + anti-angiogenic via VEGFR2 inhibition",
        "evidence_level": "LOW",
        "established": False,
        "year": 2015,
        "notes": "Early phase trials show modest activity. Mechanistic rationale established.",
    },
    {
        "drug": "rapamycin",
        "disease": "aging",
        "aliases_drug": ["sirolimus", "rapamune"],
        "aliases_disease": ["ageing", "longevity", "lifespan"],
        "mechanism": "mTOR inhibition → autophagy induction → extended cellular lifespan",
        "evidence_level": "MEDIUM",
        "established": False,
        "year": 2009,
        "notes": "Extended lifespan in multiple model organisms. Human geroscience trials ongoing.",
    },
    {
        "drug": "dextromethorphan",
        "disease": "amyotrophic lateral sclerosis",
        "aliases_drug": ["dxm"],
        "aliases_disease": ["als", "lou gehrig disease", "motor neuron disease"],
        "mechanism": "NMDA receptor antagonism → reduced glutamate excitotoxicity",
        "evidence_level": "LOW",
        "established": False,
        "year": 2022,
        "notes": "FDA-approved for pseudobulbar affect; repurposing rationale for ALS neuroprotection.",
    },
    {
        "drug": "hydroxychloroquine",
        "disease": "rheumatoid arthritis",
        "aliases_drug": ["plaquenil", "hcq"],
        "aliases_disease": ["ra", "arthritis"],
        "mechanism": "Toll-like receptor inhibition → reduced inflammatory cytokine production",
        "evidence_level": "HIGH",
        "established": True,
        "year": 1955,
        "notes": "Classic repurposing from antimalarial. Standard of care in RA.",
    },
    {
        "drug": "minoxidil",
        "disease": "alopecia",
        "aliases_drug": ["rogaine", "loniten"],
        "aliases_disease": ["hair loss", "baldness", "androgenetic alopecia"],
        "mechanism": "KATP channel opener → vasodilation → improved follicle blood supply",
        "evidence_level": "HIGH",
        "established": True,
        "year": 1988,
        "notes": "Repurposed from antihypertensive. FDA-approved topical for hair loss.",
    },
    {
        "drug": "rituximab",
        "disease": "multiple sclerosis",
        "aliases_drug": ["rituxan"],
        "aliases_disease": ["ms", "relapsing ms", "progressive ms"],
        "mechanism": "CD20+ B cell depletion → reduced autoreactive B cell activity in CNS",
        "evidence_level": "MEDIUM",
        "established": False,
        "year": 2008,
        "notes": "Off-label use based on RCT evidence; ocrelizumab (similar) approved for progressive MS.",
    },
]


# ─────────────────────────────────────────────
# DDL
# ─────────────────────────────────────────────

_DDL_KNOWLEDGE = """
CREATE TABLE IF NOT EXISTS prior_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug TEXT NOT NULL,
    disease TEXT NOT NULL,
    aliases_drug_json TEXT NOT NULL DEFAULT '[]',
    aliases_disease_json TEXT NOT NULL DEFAULT '[]',
    mechanism TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    established INTEGER NOT NULL DEFAULT 0,
    year INTEGER,
    notes TEXT,
    tfidf_tokens TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_DDL_KNOWLEDGE_IDX = """
CREATE INDEX IF NOT EXISTS idx_knowledge_drug ON prior_knowledge(drug);
CREATE INDEX IF NOT EXISTS idx_knowledge_disease ON prior_knowledge(disease);
"""


class KnowledgeEntry:
    """A single prior knowledge record retrieved from the store."""

    def __init__(self, row: sqlite3.Row) -> None:
        self.id: int = row["id"]
        self.drug: str = row["drug"]
        self.disease: str = row["disease"]
        self.aliases_drug: list[str] = json.loads(row["aliases_drug_json"])
        self.aliases_disease: list[str] = json.loads(row["aliases_disease_json"])
        self.mechanism: str = row["mechanism"]
        self.evidence_level: str = row["evidence_level"]
        self.established: bool = bool(row["established"])
        self.year: int | None = row["year"]
        self.notes: str | None = row["notes"]
        self.similarity: float = 0.0  # set after retrieval

    def to_dict(self) -> dict[str, Any]:
        return {
            "drug": self.drug,
            "disease": self.disease,
            "mechanism": self.mechanism,
            "evidence_level": self.evidence_level,
            "established": self.established,
            "year": self.year,
            "notes": self.notes,
            "similarity": round(self.similarity, 4),
        }


class KnowledgeStore:
    """SQLite-backed semantic knowledge store for prior drug repurposing knowledge.

    Uses TF-IDF cosine similarity to retrieve semantically relevant prior
    knowledge entries for a given drug-disease pair. Pre-seeded with known
    repurposing cases from the literature.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str = "data/cynthera.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._ensure_seed_data()

    # ─────────────────────────────────────────────
    # Schema & Seed
    # ─────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_DDL_KNOWLEDGE)
            for stmt in _DDL_KNOWLEDGE_IDX.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError:
                        pass
            conn.commit()

    def _ensure_seed_data(self) -> None:
        """Populate knowledge store with seed data if empty."""
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM prior_knowledge"
            ).fetchone()["cnt"]

        if count == 0:
            self._seed()

    def _seed(self) -> None:
        """Insert seed knowledge entries."""
        with self._connect() as conn:
            for entry in _SEED_KNOWLEDGE:
                tokens = self._tokenize(
                    f"{entry['drug']} {entry['disease']} {entry['mechanism']} "
                    f"{' '.join(entry['aliases_drug'])} {' '.join(entry['aliases_disease'])}"
                )
                conn.execute(
                    """
                    INSERT INTO prior_knowledge
                        (drug, disease, aliases_drug_json, aliases_disease_json,
                         mechanism, evidence_level, established, year, notes, tfidf_tokens)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["drug"],
                        entry["disease"],
                        json.dumps(entry["aliases_drug"]),
                        json.dumps(entry["aliases_disease"]),
                        entry["mechanism"],
                        entry["evidence_level"],
                        1 if entry["established"] else 0,
                        entry["year"],
                        entry["notes"],
                        " ".join(tokens),
                    ),
                )
            conn.commit()
        logger.info("knowledge_store_seeded", extra={"entries": len(_SEED_KNOWLEDGE)})

    # ─────────────────────────────────────────────
    # TF-IDF Utilities
    # ─────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Normalize and tokenize text for TF-IDF."""
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        tokens = [t for t in text.split() if len(t) > 2]
        return tokens

    @staticmethod
    def _tfidf_vector(tokens: list[str]) -> dict[str, float]:
        """Compute TF vector (normalized term frequencies)."""
        if not tokens:
            return {}
        counts = Counter(tokens)
        total = sum(counts.values())
        return {term: count / total for term, count in counts.items()}

    @staticmethod
    def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
        """Compute cosine similarity between two TF vectors."""
        common_terms = set(vec_a) & set(vec_b)
        if not common_terms:
            return 0.0
        dot = sum(vec_a[t] * vec_b[t] for t in common_terms)
        mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
        mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    # ─────────────────────────────────────────────
    # Public Interface
    # ─────────────────────────────────────────────

    def retrieve_prior_knowledge(
        self,
        drug: str,
        disease: str,
        top_k: int = 5,
        min_similarity: float = 0.05,
    ) -> list[KnowledgeEntry]:
        """Retrieve semantically similar prior knowledge entries.

        Args:
            drug: Drug name to query.
            disease: Disease name to query.
            top_k: Maximum number of entries to return.
            min_similarity: Minimum cosine similarity threshold.

        Returns:
            List of KnowledgeEntry objects ranked by similarity.
        """
        query_text = f"{drug} {disease}"
        query_tokens = self._tokenize(query_text)
        query_vec = self._tfidf_vector(query_tokens)

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM prior_knowledge ORDER BY id"
            ).fetchall()

        results: list[KnowledgeEntry] = []
        for row in rows:
            entry = KnowledgeEntry(row)
            doc_tokens = self._tokenize(row["tfidf_tokens"])
            doc_vec = self._tfidf_vector(doc_tokens)
            sim = self._cosine_similarity(query_vec, doc_vec)

            # Boost exact name matches
            if drug.lower() in (entry.drug, *entry.aliases_drug):
                sim = min(1.0, sim + 0.3)
            if disease.lower() in (entry.disease, *entry.aliases_disease):
                sim = min(1.0, sim + 0.2)

            entry.similarity = sim
            if sim >= min_similarity:
                results.append(entry)

        results.sort(key=lambda e: e.similarity, reverse=True)
        return results[:top_k]

    def add_entry(
        self,
        drug: str,
        disease: str,
        mechanism: str,
        evidence_level: str = "LOW",
        established: bool = False,
        year: int | None = None,
        notes: str | None = None,
        aliases_drug: list[str] | None = None,
        aliases_disease: list[str] | None = None,
    ) -> int:
        """Add a new knowledge entry to the store.

        Returns:
            The newly inserted row ID.
        """
        tokens = self._tokenize(
            f"{drug} {disease} {mechanism} "
            f"{' '.join(aliases_drug or [])} {' '.join(aliases_disease or [])}"
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO prior_knowledge
                    (drug, disease, aliases_drug_json, aliases_disease_json,
                     mechanism, evidence_level, established, year, notes, tfidf_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drug.lower(),
                    disease.lower(),
                    json.dumps([a.lower() for a in (aliases_drug or [])]),
                    json.dumps([a.lower() for a in (aliases_disease or [])]),
                    mechanism,
                    evidence_level,
                    1 if established else 0,
                    year,
                    notes,
                    " ".join(tokens),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0
