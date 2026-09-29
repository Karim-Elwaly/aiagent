"""
SentinelOne Singularity XDR Connector

Provides endpoint visibility, automated threat mitigation, and network quarantine
via SentinelOne Management Console 2.1+ REST APIs.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from src.connectors.base import BaseSecurityConnector, ConnectorCategory, ConnectorStatus
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


class SentinelOneConnector(BaseSecurityConnector):
    """Connector for SentinelOne Singularity platform."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "base_url": "https://usea1-partners.sentinelone.net",
            "api_token": "",
            "verify_ssl": True,
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="sentinelone",
            name="SentinelOne Singularity",
            category=ConnectorCategory.EDR,
            description="Manage Singularity agents, isolate infected endpoints, and execute automated rollback / mitigation",
            vendor="SentinelOne",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        token = self.config.get("api_token", "")
        return {"Authorization": f"APIToken {token}", "Content-Type": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual SentinelOne Management Console v23.4", 1.6

        url = f"{self.config.get('base_url', '').rstrip('/')}/web/api/v2.1/system/status"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", True), timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, "Successfully connected to SentinelOne Console API", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"SentinelOne connection failed: {e}", latency

    async def find_agent(self, query: str) -> str:
        """Find SentinelOne agent by hostname, IP address, or MAC address."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "agent": {
                    "id": "182746194726194",
                    "computerName": query if not query.replace(".", "").isdigit() else "srv-app-dmz01",
                    "osType": "linux",
                    "osName": "Ubuntu 22.04.4 LTS",
                    "agentVersion": "23.3.2.1",
                    "networkStatus": "connected",
                    "isDecommissioned": False,
                    "lastActiveDate": "2026-09-28T12:20:00Z",
                    "networkInterfaces": [{"inet": ["172.16.10.80"], "physical": "00:15:5d:01:23:45"}]
                }
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/web/api/v2.1/agents"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", True), timeout=15.0) as client:
                res = await client.get(url, params={"query": query}, headers=self._get_headers())
                res.raise_for_status()
                data = res.json().get("data", [])
                if not data:
                    return json.dumps({"status": "not_found", "message": f"No agent matched query '{query}'"})
                return json.dumps({"status": "success", "agent": data[0]}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"SentinelOne query failed: {e}"})

    async def quarantine_agent(self, agent_id: str, justification: str) -> str:
        """Disconnect endpoint from network (Quarantine) via SentinelOne Singularity."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "agent_id": agent_id,
                "action": "disconnect",
                "justification": justification,
                "message": f"[CONTAINMENT ACTION] Agent {agent_id} has been quarantined from the network. Only communication with SentinelOne Console is permitted."
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/web/api/v2.1/agents/actions/disconnect"
        payload = {"filter": {"ids": [agent_id]}, "data": {"reason": justification}}
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", True), timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "action": "disconnect", "response": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"SentinelOne quarantine failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="sentinelone_find_agent",
                name="sentinelone_find_agent",
                description="Query Singularity agent metadata, OS platform, and network status from SentinelOne",
                skills_provided=["edr_telemetry", "host_investigation", "endpoint_lookup"],
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Hostname, local IP, or MAC address"},
                    },
                    "required": ["query"],
                },
                function=self.find_agent,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://usea1-partners.sentinelone.net"),
            ),
            ToolSpec(
                tool_id="sentinelone_quarantine_agent",
                name="sentinelone_quarantine_agent",
                description="[CONTAINMENT ACTION] Disconnect endpoint from network via SentinelOne agent quarantine",
                skills_provided=["host_containment", "endpoint_isolation", "incident_mitigation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "SentinelOne Agent ID"},
                        "justification": {"type": "string", "description": "Security operational reason for containment"},
                    },
                    "required": ["agent_id", "justification"],
                },
                function=self.quarantine_agent,
                risk_level=RiskLevel.HIGH,  # High risk containment requires operator confirmation!
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://usea1-partners.sentinelone.net"),
            ),
        ]
