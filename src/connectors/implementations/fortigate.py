"""
Fortinet FortiGate FortiOS Firewall & UTM Connector

Enables perimeter quarantine, IP banning, and firewall address object creation
via FortiOS REST API v2.
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


class FortiGateConnector(BaseSecurityConnector):
    """Connector for Fortinet FortiGate Next-Generation Firewalls."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "host": "https://10.10.10.2",
            "api_token": "",
            "verify_ssl": False,
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="fortigate",
            name="Fortinet FortiGate Firewall",
            category=ConnectorCategory.FIREWALL,
            description="Manage perimeter quarantine, banned IP tables, and UTM policy objects in FortiOS",
            vendor="Fortinet",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        token = self.config.get("api_token", "")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual FortiGate 200E FortiOS v7.4.3", 1.9

        url = f"{self.config.get('host', '').rstrip('/')}/api/v2/monitor/system/status"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    data = res.json().get("results", {})
                    v = data.get("version", "unknown")
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, f"Connected to FortiGate FortiOS v{v} (Model: {data.get('model_name', 'FGT')})", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"FortiGate connection failed: {e}", latency

    async def ban_ip(self, ip_address: str, expiry_minutes: int = 1440) -> str:
        """Add an attacking external IP to the FortiGate quarantine banned table."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "action": "ban_ip",
                "ip": ip_address,
                "expiry_minutes": expiry_minutes,
                "message": f"[PERIMETER ENFORCEMENT] IP {ip_address} added to FortiGate Quarantine Banned Table for {expiry_minutes} minutes. Ingress packets dropped at kernel layer."
            }, indent=2)

        url = f"{self.config.get('host', '').rstrip('/')}/api/v2/monitor/user/banned/add_user"
        payload = {"ip_addresses": [ip_address], "expiry": expiry_minutes * 60}
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "ip": ip_address, "response": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"FortiGate ban failed: {e}"})

    async def unban_ip(self, ip_address: str) -> str:
        """Remove an IP address from the FortiGate quarantine banned table."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "action": "unban_ip",
                "ip": ip_address,
                "message": f"IP {ip_address} unbanned from FortiGate Quarantine table."
            }, indent=2)

        url = f"{self.config.get('host', '').rstrip('/')}/api/v2/monitor/user/banned/clear_users"
        payload = {"ip_addresses": [ip_address]}
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "ip": ip_address, "response": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"FortiGate unban failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="fortigate_ban_ip",
                name="fortigate_ban_ip",
                description="[CONTAINMENT ACTION] Add external adversary IP to FortiGate quarantine banned list (kernel-level packet drop)",
                skills_provided=["firewall_blocking", "ip_containment", "perimeter_defense"],
                parameters={
                    "type": "object",
                    "properties": {
                        "ip_address": {"type": "string", "description": "The IPv4 address to ban at perimeter"},
                        "expiry_minutes": {"type": "integer", "description": "Quarantine duration in minutes (default: 1440 = 24h)", "default": 1440},
                    },
                    "required": ["ip_address"],
                },
                function=self.ban_ip,
                risk_level=RiskLevel.HIGH,  # High risk containment
                source_type="connector",
                server_or_host=self.config.get("host", "https://10.10.10.2"),
            ),
            ToolSpec(
                tool_id="fortigate_unban_ip",
                name="fortigate_unban_ip",
                description="[REMEDIATION] Remove IP from FortiGate quarantine banned list",
                skills_provided=["firewall_remediation", "unblock_ip"],
                parameters={
                    "type": "object",
                    "properties": {
                        "ip_address": {"type": "string", "description": "The IPv4 address to unban"},
                    },
                    "required": ["ip_address"],
                },
                function=self.unban_ip,
                risk_level=RiskLevel.HIGH,
                source_type="connector",
                server_or_host=self.config.get("host", "https://10.10.10.2"),
            ),
        ]
