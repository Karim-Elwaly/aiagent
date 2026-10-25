"""
UAOS Mission-Scoped Environment & Tool Discovery Engine

Probes live enterprise connectors, tool registries, files, and environment
capabilities before workflow planning to generate a verified MissionEnvironmentManifest.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from src.connectors.base import ConnectorStatus
from src.connectors.manager import ConnectorManager
from src.core.config import ROOT_DIR
from src.core.models import (
    ConnectorReadiness,
    DiscoveredCapability,
    MissionEnvironmentManifest,
)
from src.orchestrator.event_bus import get_event_bus
from src.registry.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class EnvironmentDiscoveryEngine:
    """Discovers, validates, and ranks tools, enterprise connectors, and files for a mission."""

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry

    def _probe_connectors(self, prompt: str) -> list[DiscoveredCapability]:
        """Inspect all enterprise connectors and evaluate readiness and mission relevance."""
        manager = ConnectorManager.get_instance()
        connectors_data = manager.list_connectors(mask_secrets=True)
        results: list[DiscoveredCapability] = []
        prompt_lower = prompt.lower()
        terms = set(re.findall(r"\w+", prompt_lower))

        for conn in connectors_data:
            cid = conn.get("id", "")
            cname = conn.get("name", cid)
            status_val = conn.get("status", "disconnected")
            enabled = conn.get("enabled", False)

            # Determine readiness
            if not enabled or status_val == ConnectorStatus.DISCONNECTED.value:
                readiness = ConnectorReadiness.UNAVAILABLE
            elif status_val == ConnectorStatus.CONNECTED.value:
                readiness = ConnectorReadiness.READY
            else:
                readiness = ConnectorReadiness.CONFIGURED_OFFLINE

            # Calculate semantic relevance
            relevance = 0.1
            conn_keywords = {cid.lower(), cname.lower(), conn.get("category", "").lower()}
            tools_exported = conn.get("exported_tools", [])
            for t in tools_exported:
                conn_keywords.update(t.lower().split("_"))

            matches = conn_keywords.intersection(terms)
            if matches:
                relevance = min(1.0, 0.4 + (0.2 * len(matches)))

            rationale = (
                f"Connector is active ({status_val}) with {len(tools_exported)} specialized actions"
                if readiness == ConnectorReadiness.READY
                else f"Connector is configured in offline/simulated mode ({status_val})"
            )

            results.append(
                DiscoveredCapability(
                    name=cname,
                    source_type="connector",
                    readiness=readiness,
                    relevance_score=round(relevance, 2),
                    rationale=rationale,
                    skills_provided=tools_exported,
                )
            )

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results

    def _probe_tools(self, prompt: str) -> list[DiscoveredCapability]:
        """Rank registered tools by semantic relevance to the prompt."""
        if not self.registry:
            return []

        matched_specs = self.registry.discover_mission_tools(prompt, top_k=20)
        discovered: list[DiscoveredCapability] = []

        for spec in matched_specs:
            discovered.append(
                DiscoveredCapability(
                    name=spec.name,
                    source_type=spec.source_type,
                    readiness=ConnectorReadiness.READY,
                    relevance_score=1.0,
                    rationale=spec.description[:140],
                    skills_provided=list(spec.skills_provided),
                )
            )
        return discovered

    def _probe_workspace_files(self, session_id: str, attachments: list[dict[str, Any]] | None = None) -> list[str]:
        """Collect all active files available to the mission."""
        files: list[str] = []
        if attachments:
            for att in attachments:
                fname = att.get("filename") or att.get("file_path") or ""
                if fname:
                    files.append(str(fname))

        if session_id:
            upload_dir = ROOT_DIR / "data" / "uploads" / session_id
            if upload_dir.is_dir():
                for p in upload_dir.iterdir():
                    if p.is_file():
                        files.append(p.name)

        return sorted(set(files))

    def discover_for_mission(
        self,
        prompt: str,
        attachments: list[dict[str, Any]] | None = None,
        session_id: str = "",
    ) -> MissionEnvironmentManifest:
        """Execute full environment discovery for the mission."""
        logger.info("Executing environment discovery for mission (session: %s)...", session_id or "default")

        connectors = self._probe_connectors(prompt)
        tools = self._probe_tools(prompt)
        files = self._probe_workspace_files(session_id, attachments)

        ready_connectors = sum(1 for c in connectors if c.readiness == ConnectorReadiness.READY)
        total_eval = max(1, len(connectors))
        readiness_score = round(min(1.0, 0.5 + (0.5 * (ready_connectors / total_eval))), 2)

        manifest = MissionEnvironmentManifest(
            session_id=session_id or "default",
            readiness_score=readiness_score,
            active_connectors=connectors,
            matched_tools=tools,
            available_files=files,
            timestamp=time.time(),
        )

        # Broadcast SSE event
        bus = get_event_bus()
        bus.publish(
            session_id or "default",
            {
                "type": "environment.discovered",
                "session_id": session_id or "default",
                "readiness_score": readiness_score,
                "matched_tools_count": len(tools),
                "active_connectors_count": ready_connectors,
                "available_files_count": len(files),
                "matched_tools": [t.model_dump() for t in tools[:8]],
                "active_connectors": [c.model_dump() for c in connectors[:6]],
            },
        )

        return manifest
