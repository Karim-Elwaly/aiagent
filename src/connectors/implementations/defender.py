"""
Microsoft Defender for Endpoint (MDE) Connector

Provides device health, alert investigation, and live host isolation
via Microsoft Defender XDR and Microsoft Graph Security APIs.
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


class MicrosoftDefenderConnector(BaseSecurityConnector):
    """Connector for Microsoft Defender for Endpoint."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "bearer_token": "",
            "base_url": "https://api.securitycenter.microsoft.com",
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="defender",
            name="Microsoft Defender for Endpoint",
            category=ConnectorCategory.EDR,
            description="Manage endpoint containment, retrieve machine telemetry, and triage Defender for Endpoint alerts",
            vendor="Microsoft",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        token = self.config.get("bearer_token", "")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual Microsoft Defender XDR tenant", 1.4

        url = f"{self.config.get('base_url', '').rstrip('/')}/api/machines?$top=1"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, "Successfully connected to Defender for Endpoint API", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Defender connection failed: {e}", latency

    async def get_machine(self, machine_id_or_name: str) -> str:
        """Find device telemetry and isolation status by hostname or machine ID."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "machine": {
                    "id": "7f8a9b1c2d3e4f5061728394a5b6c7d8",
                    "computerDnsName": machine_id_or_name if "." in machine_id_or_name else f"{machine_id_or_name}.corp.internal",
                    "osPlatform": "Windows11",
                    "osVersion": "10.0.22631.3007",
                    "lastSeen": "2026-09-28T12:20:00Z",
                    "lastIpAddress": "10.20.10.45",
                    "healthStatus": "Active",
                    "riskScore": "Medium",
                    "exposureLevel": "Low",
                    "isAadJoined": True
                }
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/api/machines"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, params={"$filter": f"computerDnsName eq '{machine_id_or_name}'"}, headers=self._get_headers())
                res.raise_for_status()
                machines = res.json().get("value", [])
                if not machines:
                    return json.dumps({"status": "not_found", "message": f"No machine found matching '{machine_id_or_name}'"})
                return json.dumps({"status": "success", "machine": machines[0]}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Defender query failed: {e}"})

    async def isolate_machine(self, machine_id: str, comment: str, isolation_type: str = "Full") -> str:
        """Isolate a compromised device from the network via Defender for Endpoint."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "machine_id": machine_id,
                "action": "isolate",
                "isolation_type": isolation_type,
                "comment": comment,
                "message": f"[CONTAINMENT ACTION] Device {machine_id} has been isolated by Microsoft Defender. Traffic restricted to Outlook/Teams/Defender cloud."
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/api/machines/{machine_id}/isolate"
        payload = {"Comment": comment, "IsolationType": isolation_type}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "action": "isolate", "response": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Defender isolation failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="defender_get_machine",
                name="defender_get_machine",
                description="Query device telemetry, OS version, risk score, and health from Microsoft Defender for Endpoint",
                skills_provided=["edr_telemetry", "host_investigation", "endpoint_lookup"],
                parameters={
                    "type": "object",
                    "properties": {
                        "machine_id_or_name": {"type": "string", "description": "Hostname, DNS name, or Defender machine ID"},
                    },
                    "required": ["machine_id_or_name"],
                },
                function=self.get_machine,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://api.securitycenter.microsoft.com"),
            ),
            ToolSpec(
                tool_id="defender_isolate_machine",
                name="defender_isolate_machine",
                description="[CONTAINMENT ACTION] Isolate compromised endpoint from the corporate network via Microsoft Defender",
                skills_provided=["host_containment", "endpoint_isolation", "incident_mitigation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "machine_id": {"type": "string", "description": "Defender Machine ID to isolate"},
                        "comment": {"type": "string", "description": "Operational justification for isolation"},
                        "isolation_type": {"type": "string", "enum": ["Full", "Selective"], "default": "Full"},
                    },
                    "required": ["machine_id", "comment"],
                },
                function=self.isolate_machine,
                risk_level=RiskLevel.HIGH,  # High risk containment requires human confirmation!
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://api.securitycenter.microsoft.com"),
            ),
        ]
