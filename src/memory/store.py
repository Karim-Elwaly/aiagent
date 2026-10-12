"""
UAOS SQLite + FTS5 Long-Term Memory Store (Gap 3)

Provides schema management, transactional writes, secret masking,
grounding verification, and web-content quarantine.

Tables:
  - episodes: Past workflow execution DAGs, outcomes, and tool traces.
  - facts: Environment, project, and system facts with grounding evidence.
  - lessons: Operational lessons learned from successful / failed executions.
  - FTS5 virtual tables for BM25 text retrieval.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

MEMORY_DIR = ROOT_DIR / "data" / "memory"
DB_PATH = MEMORY_DIR / "uaos_memory.db"
HERMES_MEMORY_JSON = ROOT_DIR / "data" / "hermes_memory.json"

VOLATILE_KEYWORDS = frozenset({
    "ip", "ip_address", "hostname", "host", "disk", "disk_space",
    "ram", "memory_free", "uptime", "pid", "process", "port", "timestamp",
})

# Secret detection regex
SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+[a-zA-Z0-9_\-\.]{20,})"),
    re.compile(r"(?i)(api[_\-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?)"),
    re.compile(r"(?i)(password\s*[:=]\s*['\"]?[^\s'\"]{6,}['\"]?)"),
    re.compile(r"(sk-[a-zA-Z0-9]{20,})"),
]


def mask_secrets(text: str) -> str:
    """Mask credentials, tokens, and passwords before persisting to memory."""
    masked = text
    for pat in SECRET_PATTERNS:
        masked = pat.sub("[REDACTED_SECRET]", masked)
    return masked


@dataclass
class Fact:
    key: str
    value: str
    scope: str = "project"  # 'global' | 'project' | 'host'
    source_run: str = ""
    evidence: str = ""
    confidence: float = 1.0
    ttl: int = 0  # 0 = infinite
    volatile: bool = False
    provenance: str = "tool"  # 'tool' | 'user' | 'web' | 'system'
    quarantined: bool = False
    last_used: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Episode:
    run_id: str
    query: str
    goal: str
    dag_json: str
    outcome: str = "accurate"  # 'accurate' | 'needs_retry' | 'failed'
    score: float = 1.0
    tool_trace: str = "[]"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Lesson:
    trigger: str
    lesson: str
    evidence_runs: str = "[]"
    success_n: int = 1
    fail_n: int = 0


class MemoryStore:
    """Persistent SQLite database with FTS5 search indexing."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_legacy_hermes_memory()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Create tables and FTS5 full-text search indexes."""
        with self._get_connection() as conn:
            # 1. Episodes table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                run_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                goal TEXT NOT NULL,
                dag_json TEXT NOT NULL,
                outcome TEXT NOT NULL,
                score REAL DEFAULT 1.0,
                tool_trace TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            """)

            # 2. Facts table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                scope TEXT DEFAULT 'project',
                source_run TEXT DEFAULT '',
                evidence TEXT DEFAULT '',
                confidence REAL DEFAULT 1.0,
                ttl INTEGER DEFAULT 0,
                volatile INTEGER DEFAULT 0,
                provenance TEXT DEFAULT 'tool',
                quarantined INTEGER DEFAULT 0,
                last_used TEXT NOT NULL
            );
            """)

            # 3. Lessons table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger TEXT NOT NULL,
                lesson TEXT NOT NULL,
                evidence_runs TEXT DEFAULT '[]',
                success_n INTEGER DEFAULT 1,
                fail_n INTEGER DEFAULT 0
            );
            """)

            # 4. FTS5 Virtual Tables
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                key,
                value,
                evidence,
                content=facts,
                content_rowid=id
            );
            """)

            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                query,
                goal,
                content=episodes,
                content_rowid=rowid
            );
            """)

            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(
                trigger,
                lesson,
                content=lessons,
                content_rowid=id
            );
            """)

            conn.commit()

    def _migrate_legacy_hermes_memory(self) -> None:
        """Idempotently import entries from legacy hermes_memory.json if present."""
        if not HERMES_MEMORY_JSON.exists():
            return
        try:
            with open(HERMES_MEMORY_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return

            imported = 0
            for k, v in data.items():
                val_str = str(v)
                # Volatility check
                is_vol = any(vk in k.lower() for vk in VOLATILE_KEYWORDS)
                fact = Fact(
                    key=str(k).strip(),
                    value=mask_secrets(val_str),
                    scope="global",
                    provenance="user",
                    volatile=is_vol,
                )
                if self.save_fact(fact, verified_grounding=True):
                    imported += 1
            if imported > 0:
                logger.info("Migrated %d facts from hermes_memory.json to SQLite store", imported)
        except Exception as e:
            logger.warning("Failed to migrate legacy hermes_memory.json: %s", e)

    # ── Write Path with Grounding and Safety ─────────────────────────

    def save_fact(
        self,
        fact: Fact,
        verified_grounding: bool = False,
        tool_outputs: list[str] | None = None,
    ) -> bool:
        """Save or update a fact with grounding verification and secret masking.

        Rejects unverified facts that fail the grounding check against tool_outputs.
        """
        # Grounding check: A fact must cite evidence from actual tool output unless explicitly verified
        if not verified_grounding:
            if not fact.evidence or not tool_outputs:
                logger.warning("Fact '%s' rejected: Missing grounding evidence", fact.key)
                return False
            clean_ev = fact.evidence.strip().lower()
            grounded = any(clean_ev in out.lower() for out in tool_outputs if out)
            if not grounded:
                logger.warning("Fact '%s' rejected: Evidence not found in tool outputs", fact.key)
                return False

        # Quarantine check: Web-sourced facts are flagged
        quarantined = 1 if fact.provenance == "web" else 0
        volatile_int = 1 if (fact.volatile or any(vk in fact.key.lower() for vk in VOLATILE_KEYWORDS)) else 0

        clean_val = mask_secrets(fact.value)
        clean_ev = mask_secrets(fact.evidence)

        with self._get_connection() as conn:
            # Upsert into facts table
            conn.execute("""
            INSERT INTO facts (key, value, scope, source_run, evidence, confidence, ttl, volatile, provenance, quarantined, last_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                evidence=excluded.evidence,
                confidence=excluded.confidence,
                volatile=excluded.volatile,
                last_used=excluded.last_used;
            """, (
                fact.key, clean_val, fact.scope, fact.source_run, clean_ev,
                fact.confidence, fact.ttl, volatile_int, fact.provenance,
                quarantined, datetime.now(timezone.utc).isoformat()
            ))

            # Sync FTS
            row_id = conn.execute("SELECT id FROM facts WHERE key = ?", (fact.key,)).fetchone()[0]
            conn.execute("DELETE FROM facts_fts WHERE rowid = ?", (row_id,))
            conn.execute("""
            INSERT INTO facts_fts (rowid, key, value, evidence)
            VALUES (?, ?, ?, ?);
            """, (row_id, fact.key, clean_val, clean_ev))

            conn.commit()
            return True

    def record_episode(self, episode: Episode) -> None:
        """Store a completed workflow execution record."""
        clean_query = mask_secrets(episode.query)
        clean_goal = mask_secrets(episode.goal)

        with self._get_connection() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO episodes (run_id, query, goal, dag_json, outcome, score, tool_trace, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                episode.run_id, clean_query, clean_goal, episode.dag_json,
                episode.outcome, episode.score, episode.tool_trace, episode.created_at
            ))

            row_id = conn.execute("SELECT rowid FROM episodes WHERE run_id = ?", (episode.run_id,)).fetchone()[0]
            conn.execute("DELETE FROM episodes_fts WHERE rowid = ?", (row_id,))
            conn.execute("""
            INSERT INTO episodes_fts (rowid, query, goal)
            VALUES (?, ?, ?);
            """, (row_id, clean_query, clean_goal))

            conn.commit()

    def record_lesson(self, lesson: Lesson) -> None:
        """Store a distilled operational lesson."""
        clean_trigger = mask_secrets(lesson.trigger)
        clean_lesson = mask_secrets(lesson.lesson)

        with self._get_connection() as conn:
            cur = conn.execute("""
            INSERT INTO lessons (trigger, lesson, evidence_runs, success_n, fail_n)
            VALUES (?, ?, ?, ?, ?);
            """, (clean_trigger, clean_lesson, lesson.evidence_runs, lesson.success_n, lesson.fail_n))
            row_id = cur.lastrowid
            conn.execute("""
            INSERT INTO lessons_fts (rowid, trigger, lesson)
            VALUES (?, ?, ?);
            """, (row_id, clean_trigger, clean_lesson))
            conn.commit()

    # ── Read Path ───────────────────────────────────────────────────

    def search_facts(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search trusted facts using FTS5 BM25 ranking (skips quarantined items)."""
        safe_query = re.sub(r"[^\w\s]", " ", query).strip()
        if not safe_query:
            return []

        # Convert words into prefix match query
        terms = [f'"{t}"*' for t in safe_query.split() if len(t) > 2]
        if not terms:
            terms = [f'"{safe_query}"*']
        fts_match = " OR ".join(terms[:5])

        with self._get_connection() as conn:
            try:
                rows = conn.execute("""
                SELECT f.key, f.value, f.volatile, f.provenance, f.evidence
                FROM facts_fts fts
                JOIN facts f ON f.id = fts.rowid
                WHERE f.quarantined = 0 AND facts_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
                """, (fts_match, limit)).fetchall()
                return [dict(r) for r in rows]
            except Exception as e:
                logger.debug("FTS fact search fallback on error: %s", e)
                # Fallback to LIKE
                rows = conn.execute("""
                SELECT key, value, volatile, provenance, evidence
                FROM facts
                WHERE quarantined = 0 AND (key LIKE ? OR value LIKE ?)
                LIMIT ?;
                """, (f"%{safe_query[:20]}%", f"%{safe_query[:20]}%", limit)).fetchall()
                return [dict(r) for r in rows]

    def search_episodes(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Search similar past workflow runs using FTS5."""
        safe_query = re.sub(r"[^\w\s]", " ", query).strip()
        if not safe_query:
            return []
        terms = [f'"{t}"*' for t in safe_query.split() if len(t) > 2]
        if not terms:
            return []
        fts_match = " OR ".join(terms[:5])

        with self._get_connection() as conn:
            try:
                rows = conn.execute("""
                SELECT e.run_id, e.query, e.goal, e.outcome, e.dag_json
                FROM episodes_fts fts
                JOIN episodes e ON e.rowid = fts.rowid
                WHERE episodes_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
                """, (fts_match, limit)).fetchall()
                return [dict(r) for r in rows]
            except Exception as e:
                logger.debug("FTS episode search fallback: %s", e)
                return []

    def get_all_facts(self) -> list[dict[str, Any]]:
        """Return all stored facts."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT key, value, volatile, provenance, last_used FROM facts ORDER BY id DESC;").fetchall()
            return [dict(r) for r in rows]

    def delete_fact(self, key: str) -> bool:
        """Delete a fact by key."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM facts WHERE key = ?", (key,)).fetchone()
            if not row:
                return False
            row_id = row[0]
            conn.execute("DELETE FROM facts WHERE id = ?", (row_id,))
            conn.execute("DELETE FROM facts_fts WHERE rowid = ?", (row_id,))
            conn.commit()
            return True


# Global singleton instance
_MEMORY_STORE: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _MEMORY_STORE
    if _MEMORY_STORE is None:
        _MEMORY_STORE = MemoryStore()
    return _MEMORY_STORE
