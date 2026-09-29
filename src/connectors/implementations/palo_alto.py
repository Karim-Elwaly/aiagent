"""
Palo Alto Networks PAN-OS & Panorama Firewall Connector

Enables dynamic automated IP blacklisting via Dynamic Address Groups (DAG)
and XML/REST API policy enforcement.
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


class PaloAltoConnector(BaseSecurityConnector):
    """Connector for Palo Alto Networks Next-Generation Firewalls."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "host": "https://panorama.corp.internal",
            "api_key": "",
            "default_tag": "block_adversary_ioc",
            "verify_ssl": False,
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="paloalto",
            name="Palo Alto NGFW / Panorama",
            category=ConnectorCategory.FIREWALL,
            description="Dynamic IP blacklisting via Dynamic Address Groups (DAG) and PAN-OS security policy management",
            vendor="Palo Alto Networks",
            default_config=default_config,
            config=config,
        )

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual Palo Alto Panorama v11.1.2 (HA State: ACTIVE)", 2.1

        url = f"{self.config.get('host', '').rstrip('/')}/api/?type=op&cmd=<show><system><info></info></system></show>&key={self.config.get('api_key', '')}"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=10.0) as client:
                res = await client.get(url)
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200 and "status=\"success\"" in res.text:
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, "Successfully connected to Palo Alto PAN-OS XML API", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Palo Alto connection failed: {e}", latency

    async def register_ip_dag(self, ip_address: str, tag: str | None = None) -> str:
        """Register an adversary IP to a Dynamic Address Group (DAG) for instant perimeter drop."""
        t = tag or self.config.get("default_tag", "block_adversary_ioc")
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "action": "register_dag",
                "ip": ip_address,
                "tag": t,
                "message": f"[PERIMETER ENFORCEMENT] IP {ip_address} registered to Dynamic Address Group '{t}'. Perimeter NGFW rules will drop all traffic immediately without committing full policy."
            }, indent=2)

        xml_cmd = f"<uid-message><version>1.0</version><type>update</type><payload><register><entry ip=\"{ip_address}\"><tag><member>{t}</member></tag></entry></register></payload></uid-message>"
        url = f"{self.config.get('host', '').rstrip('/')}/api/?type=user-id&cmd={xml_cmd}&key={self.config.get('api_key', '')}"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=15.0) as client:
                res = await client.post(url)
                res.raise_for_status()
                return json.dumps({"status": "success", "ip": ip_address, "tag": t, "response": res.text}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Palo Alto DAG registration failed: {e}"})

    async def unregister_ip_dag(self, ip_address: str, tag: str | None = None) -> str:
        """Remove an IP address from a Dynamic Address Group (DAG)."""
        t = tag or self.config.get("default_tag", "block_adversary_ioc")
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "action": "unregister_dag",
                "ip": ip_address,
                "tag": t,
                "message": f"IP {ip_address} unregistered from Dynamic Address Group '{t}'."
            }, indent=2)

        xml_cmd = f"<uid-message><version>1.0</version><type>update</type><payload><unregister><entry ip=\"{ip_address}\"><tag><member>{t}</member></tag></entry></unregister></payload></uid-message>"
        url = f"{self.config.get('host', '').rstrip('/')}/api/?type=user-id&cmd={xml_cmd}&key={self.config.get('api_key', '')}"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=15.0) as client:
                res = await client.post(url)
                res.raise_for_status()
                return json.dumps({"status": "success", "ip": ip_address, "tag": t, "response": res.text}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Palo Alto DAG unregistration failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="paloalto_register_ip_dag",
                name="paloalto_register_ip_dag",
                description="[CONTAINMENT ACTION] Blacklist an external adversary IP by pushing it to a Dynamic Address Group (DAG) in Palo Alto NGFW",
                skills_provided=["firewall_blocking", "ip_containment", "perimeter_defense"],
                parameters={
                    "type": "object",
                    "properties": {
                        "ip_address": {"type": "string", "description": "The IPv4 or IPv6 address of the adversary to block"},
                        "tag": {"type": "string", "description": "Dynamic tag name (defaults to 'block_adversary_ioc')", "default": "block_adversary_ioc"},
                    },
                    "required": ["ip_address"],
                },
                function=self.register_ip_dag,
                risk_level=RiskLevel.HIGH,  # High-risk containment
                source_type="connector",
                server_or_host=self.config.get("host", "https://panorama.corp.internal"),
            ),
            ToolSpec(
                tool_id="paloalto_unregister_ip_dag",
                name="paloalto_unregister_ip_dag",
                description="[REMEDIATION] Unblock an IP address from Palo Alto Dynamic Address Group",
                skills_provided=["firewall_remediation", "unblock_ip"],
                parameters={
                    "type": "object",
                    "properties": {
                        "ip_address": {"type": "string", "description": "The IP address to unblock"},
                        "tag": {"type": "string", "description": "Dynamic tag name", "default": "block_adversary_ioc"},
                    },
                    "required": ["ip_address"],
                },
                function=self.unregister_ip_dag,
                risk_level=RiskLevel.HIGH,
                source_type="connector",
                server_or_host=self.config.get("host", "https://panorama.corp.internal"),
            ),
        ]
