"""
UAOS Real-Time Fleet Telemetry & Metrics Engine (Phase 6)

Tracks operational metrics across missions, fleets, specialist units, and tools.
Persists metrics to SQLite and broadcasts live updates over the SSE Event Bus.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR
from src.orchestrator.event_bus import get_event_bus

logger = logging.getLogger(__name__)

DB_PATH = ROOT_DIR / "data" / "memory" / "uaos_memory.db"


@dataclass
class MissionTelemetry:
    session_id: str
    total_elapsed_ms: float = 0.0
    active_specialist_units: int = 0
    total_spawned_units: int = 0
    discovered_tools_count: int = 0
    invoked_tools_count: int = 0
    step_challenges_issued: int = 0
    supervisor_self_corrections: int = 0
    hitl_approvals_count: int = 0
    fleet_efficiency_score: float = 100.0
    status: str = "running"
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FleetTelemetryTracker:
    """Manages real-time and historical telemetry across missions and fleets."""

    _instance: FleetTelemetryTracker | None = None

    def __init__(self):
        self._in_memory: dict[str, MissionTelemetry] = {}
        self._init_db()

    @classmethod
    def get_instance(cls) -> FleetTelemetryTracker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_db(self) -> None:
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mission_telemetry (
                        session_id TEXT PRIMARY KEY,
                        total_elapsed_ms REAL,
                        active_specialist_units INTEGER,
                        total_spawned_units INTEGER,
                        discovered_tools_count INTEGER,
                        invoked_tools_count INTEGER,
                        step_challenges_issued INTEGER,
                        supervisor_self_corrections INTEGER,
                        hitl_approvals_count INTEGER,
                        fleet_efficiency_score REAL,
                        status TEXT,
                        created_at REAL,
                        updated_at REAL
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.warning("Could not initialize telemetry database table: %s", e)

    def start_mission(
        self,
        session_id: str,
        total_units: int = 0,
        discovered_tools: int = 0,
    ) -> MissionTelemetry:
        now = time.time()
        telem = MissionTelemetry(
            session_id=session_id,
            active_specialist_units=0,
            total_spawned_units=total_units,
            discovered_tools_count=discovered_tools,
            created_at=now,
            updated_at=now,
        )
        self._in_memory[session_id] = telem
        self._persist(telem)
        self._broadcast(telem)
        return telem

    def record_step_started(self, session_id: str) -> None:
        telem = self._get_or_create(session_id)
        telem.active_specialist_units = max(1, telem.active_specialist_units + 1)
        telem.updated_at = time.time()
        self._broadcast(telem)

    def record_step_completed(
        self,
        session_id: str,
        tools_used_count: int = 0,
        execution_time_ms: float = 0.0,
    ) -> None:
        telem = self._get_or_create(session_id)
        telem.active_specialist_units = max(0, telem.active_specialist_units - 1)
        telem.invoked_tools_count += tools_used_count
        telem.total_elapsed_ms += execution_time_ms
        telem.updated_at = time.time()
        self._persist(telem)
        self._broadcast(telem)

    def record_challenge(self, session_id: str) -> None:
        telem = self._get_or_create(session_id)
        telem.step_challenges_issued += 1
        total_steps = max(1, telem.total_spawned_units + telem.step_challenges_issued)
        passes = max(0, total_steps - telem.step_challenges_issued)
        telem.fleet_efficiency_score = round((passes / total_steps) * 100.0, 1)
        telem.updated_at = time.time()
        self._persist(telem)
        self._broadcast(telem)

    def record_supervisor_retry(self, session_id: str) -> None:
        telem = self._get_or_create(session_id)
        telem.supervisor_self_corrections += 1
        telem.updated_at = time.time()
        self._persist(telem)
        self._broadcast(telem)

    def record_hitl_approval(self, session_id: str) -> None:
        telem = self._get_or_create(session_id)
        telem.hitl_approvals_count += 1
        telem.updated_at = time.time()
        self._persist(telem)
        self._broadcast(telem)

    def finish_mission(self, session_id: str, status: str = "completed") -> None:
        telem = self._get_or_create(session_id)
        telem.status = status
        telem.active_specialist_units = 0
        if telem.created_at:
            telem.total_elapsed_ms = round((time.time() - telem.created_at) * 1000.0, 1)
        telem.updated_at = time.time()
        self._persist(telem)
        self._broadcast(telem)

    def get_mission_telemetry(self, session_id: str) -> dict[str, Any]:
        if session_id in self._in_memory:
            return self._in_memory[session_id].to_dict()
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                row = cur.execute(
                    "SELECT * FROM mission_telemetry WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row:
                    return dict(row)
        except Exception:
            pass
        return MissionTelemetry(session_id=session_id).to_dict()

    def get_global_summary(self) -> dict[str, Any]:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                rows = cur.execute("SELECT * FROM mission_telemetry ORDER BY updated_at DESC LIMIT 100").fetchall()
                total_missions = len(rows)
                if not total_missions:
                    return {
                        "total_missions": 0,
                        "avg_efficiency_score": 100.0,
                        "total_units_deployed": 0,
                        "total_challenges": 0,
                        "total_tools_invoked": 0,
                    }
                total_units = sum(r["total_spawned_units"] for r in rows)
                total_challenges = sum(r["step_challenges_issued"] for r in rows)
                total_tools = sum(r["invoked_tools_count"] for r in rows)
                avg_score = round(sum(r["fleet_efficiency_score"] for r in rows) / total_missions, 1)
                return {
                    "total_missions": total_missions,
                    "avg_efficiency_score": avg_score,
                    "total_units_deployed": total_units,
                    "total_challenges": total_challenges,
                    "total_tools_invoked": total_tools,
                }
        except Exception as e:
            logger.warning("Could not query global telemetry summary: %s", e)
            return {
                "total_missions": 0,
                "avg_efficiency_score": 100.0,
                "total_units_deployed": 0,
                "total_challenges": 0,
                "total_tools_invoked": 0,
            }

    def _get_or_create(self, session_id: str) -> MissionTelemetry:
        if session_id not in self._in_memory:
            now = time.time()
            self._in_memory[session_id] = MissionTelemetry(
                session_id=session_id, created_at=now, updated_at=now
            )
        return self._in_memory[session_id]

    def _persist(self, telem: MissionTelemetry) -> None:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mission_telemetry (
                        session_id, total_elapsed_ms, active_specialist_units,
                        total_spawned_units, discovered_tools_count, invoked_tools_count,
                        step_challenges_issued, supervisor_self_corrections,
                        hitl_approvals_count, fleet_efficiency_score, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telem.session_id,
                        telem.total_elapsed_ms,
                        telem.active_specialist_units,
                        telem.total_spawned_units,
                        telem.discovered_tools_count,
                        telem.invoked_tools_count,
                        telem.step_challenges_issued,
                        telem.supervisor_self_corrections,
                        telem.hitl_approvals_count,
                        telem.fleet_efficiency_score,
                        telem.status,
                        telem.created_at,
                        telem.updated_at,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.debug("Failed to persist telemetry for session %s: %s", telem.session_id, e)

    def _broadcast(self, telem: MissionTelemetry) -> None:
        bus = get_event_bus()
        bus.publish(
            telem.session_id,
            {
                "type": "telemetry.update",
                "session_id": telem.session_id,
                **telem.to_dict(),
            },
        )
