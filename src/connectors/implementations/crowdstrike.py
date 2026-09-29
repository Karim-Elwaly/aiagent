"""
CrowdStrike Falcon EDR & XDR Connector

Provides endpoint telemetry, alert triage, and automated network containment
via CrowdStrike Falcon REST APIs and OAuth2 authentication.
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


class CrowdStrikeFalconConnector(BaseSecurityConnector):
    """Connector for CrowdStrike Falcon EDR/XDR platform."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "base_url": "https://api.crowdstrike.com",
            "client_id": "",
            "client_secret": "",
            "verify_ssl": True,
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="crowdstrike",
            name="CrowdStrike Falcon EDR",
            category=ConnectorCategory.EDR,
            description="Manage endpoint containment, query host telemetry, and triage Falcon XDR detections",
            vendor="CrowdStrike",
            default_config=default_config,
            config=config,
        )
        self._token: str | None = None
        self._token_expires: float = 0.0

    async def _get_access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        url = f"{self.config.get('base_url', '').rstrip('/')}/oauth2/token"
        payload = {
            "client_id": self.config.get("client_id", ""),
            "client_secret": self.config.get("client_secret", ""),
        }
        async with httpx.AsyncClient(verify=self.config.get("verify_ssl", True), timeout=10.0) as client:
            res = await client.post(url, data=payload)
            res.raise_for_status()
            data = res.json()
            self._token = data.get("access_token", "")
            expires_in = data.get("expires_in", 1799)
            self._token_expires = time.time() + expires_in
            return self._token

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual CrowdStrike Falcon Cloud (US-1 / CID: 9a4f21)", 2.4

        try:
            token = await self._get_access_token()
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.CONNECTED
            self.last_error = None
            self.last_checked = time.time()
            return True, "Successfully authenticated with CrowdStrike Falcon OAuth2 API", latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Falcon OAuth2 authentication failed: {e}", latency

    async def get_device(self, identifier: str) -> str:
        """Find device details by hostname, IP address, or Falcon Agent ID (AID)."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "device": {
                    "device_id": "4b98fa32ec114889b932c0993081eac1",
                    "hostname": identifier if not identifier.replace(".", "").isdigit() else "wkstn-corp-045.corp.internal",
                    "local_ip": identifier if identifier.startswith("10.") or identifier.startswith("192.") else "10.20.10.45",
                    "external_ip": "198.51.100.220",
                    "os_version": "Windows 11 Enterprise 23H2 (Build 22631)",
                    "agent_version": "7.15.18404.0",
                    "status": "normal",
                    "containment_status": "normal",
                    "last_seen": "2026-09-28T12:20:00Z",
                    "assigned_user": "domain\\johndoe",
                    "mac_address": "00:50:56:b2:33:1a"
                }
            }, indent=2)

        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        base = self.config.get("base_url", "").rstrip("/")
        # Query devices
        filter_str = f"hostname:'{identifier}'" if not identifier.replace(".", "").isdigit() else f"local_ip:'{identifier}'"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", True), timeout=15.0) as client:
                res = await client.get(f"{base}/devices/queries/devices/v1", params={"filter": filter_str}, headers=headers)
                res.raise_for_status()
                ids = res.json().get("resources", [])
                if not ids:
                    return json.dumps({"status": "not_found", "message": f"No Falcon host matched '{identifier}'"})
                
                # Fetch details
                det_res = await client.get(f"{base}/devices/entities/devices/v1", params={"ids": ids[:1]}, headers=headers)
                det_res.raise_for_status()
                return json.dumps({"status": "success", "device": det_res.json().get("resources", [{}])[0]}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"CrowdStrike query failed: {e}"})

    async def contain_host(self, aid: str, justification: str) -> str:
        """Isolate a host from the network while preserving the CrowdStrike management tunnel."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "action": "contain",
                "mode": "simulated",
                "aid": aid,
                "containment_status": "contained",
                "justification": justification,
                "message": f"[EMERGENCY CONTAINMENT] Host {aid} has been network-isolated via Falcon Sensor. All inbound/outbound packets dropped except Falcon C2 telemetry."
            }, indent=2)

        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{self.config.get('base_url', '').rstrip('/')}/devices/entities/devices-actions/v1?action_name=contain"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", True), timeout=15.0) as client:
                res = await client.post(url, json={"ids": [aid]}, headers=headers)
                res.raise_for_status()
                return json.dumps({"status": "success", "aid": aid, "action": "contain", "response": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"CrowdStrike containment failed: {e}"})

    async def lift_containment(self, aid: str, justification: str) -> str:
        """Lift network isolation on an endpoint after remediation."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "action": "lift_containment",
                "mode": "simulated",
                "aid": aid,
                "containment_status": "normal",
                "justification": justification,
                "message": f"Network containment lifted for host {aid}. Host has resumed normal network communications."
            }, indent=2)

        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{self.config.get('base_url', '').rstrip('/')}/devices/entities/devices-actions/v1?action_name=lift_containment"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", True), timeout=15.0) as client:
                res = await client.post(url, json={"ids": [aid]}, headers=headers)
                res.raise_for_status()
                return json.dumps({"status": "success", "aid": aid, "action": "lift_containment", "response": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"CrowdStrike lift containment failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="crowdstrike_get_device",
                name="crowdstrike_get_device",
                description="Query endpoint identity, sensor version, assigned user, and isolation status from CrowdStrike Falcon",
                skills_provided=["edr_telemetry", "host_investigation", "endpoint_lookup"],
                parameters={
                    "type": "object",
                    "properties": {
                        "identifier": {"type": "string", "description": "Hostname, local IP, or Falcon Agent ID (AID)"},
                    },
                    "required": ["identifier"],
                },
                function=self.get_device,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://api.crowdstrike.com"),
            ),
            ToolSpec(
                tool_id="crowdstrike_contain_host",
                name="crowdstrike_contain_host",
                description="[CONTAINMENT ACTION] Isolate compromised host from the network via CrowdStrike Falcon Sensor",
                skills_provided=["host_containment", "endpoint_isolation", "incident_mitigation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "aid": {"type": "string", "description": "Falcon Agent ID (AID) or device ID to isolate"},
                        "justification": {"type": "string", "description": "Operational and security reason for isolating the endpoint"},
                    },
                    "required": ["aid", "justification"],
                },
                function=self.contain_host,
                risk_level=RiskLevel.HIGH,  # Requires human operator approval gate!
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://api.crowdstrike.com"),
            ),
            ToolSpec(
                tool_id="crowdstrike_lift_containment",
                name="crowdstrike_lift_containment",
                description="[REMEDIATION] Restore network access and lift isolation for a remediated host in CrowdStrike Falcon",
                skills_provided=["host_remediation", "lift_isolation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "aid": {"type": "string", "description": "Falcon Agent ID (AID) of the host"},
                        "justification": {"type": "string", "description": "Reason for lifting network isolation"},
                    },
                    "required": ["aid", "justification"],
                },
                function=self.lift_containment,
                risk_level=RiskLevel.HIGH,  # Requires operator confirmation
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://api.crowdstrike.com"),
            ),
        ]
