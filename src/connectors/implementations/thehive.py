"""
TheHive / Cortex SOAR & Security Case Management Connector

Enables automated security case creation, incident tracking, and IoC observable
management via TheHive 5.x REST API.
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


class TheHiveConnector(BaseSecurityConnector):
    """Connector for TheHive 5.x Security Incident Response platform."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "base_url": "https://thehive.corp.internal:9000",
            "api_key": "",
            "verify_ssl": False,
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="thehive",
            name="TheHive SOAR & Case Management",
            category=ConnectorCategory.ITSM,
            description="Create security incident cases, attach correlated forensic observables, and manage SOC triage workflows",
            vendor="TheHive Project",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        key = self.config.get("api_key", "")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual TheHive 5.2 Instance", 1.3

        url = f"{self.config.get('base_url', '').rstrip('/')}/api/v1/organisation"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, "Successfully connected to TheHive 5.x API", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"TheHive connection failed: {e}", latency

    async def create_case(self, title: str, description: str, severity: int = 3, tags: list[str] | None = None) -> str:
        """Create a new security incident case in TheHive."""
        t = tags or ["incident-response", "auto-generated", "aiagent"]
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "case": {
                    "_id": "~4210984",
                    "number": 1042,
                    "title": title,
                    "description": description[:200] + "...",
                    "severity": severity,
                    "severity_label": "High" if severity == 3 else "Critical" if severity == 4 else "Medium",
                    "status": "New",
                    "tags": t,
                    "createdAt": "2026-09-28T12:30:00Z",
                },
                "message": f"Security case #{1042} created successfully in TheHive."
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/api/v1/case"
        payload = {
            "title": title,
            "description": description,
            "severity": severity,
            "tags": t,
            "flag": True if severity >= 3 else False,
        }
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "case": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"TheHive create_case failed: {e}"})

    async def add_observable(self, case_id: str, data_type: str, data: str, message: str = "Correlated IoC") -> str:
        """Attach an indicator / observable (IP, hash, domain) to an existing case."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "case_id": case_id,
                "data_type": data_type,
                "data": data,
                "message": f"Observable '{data}' ({data_type}) attached to case {case_id}."
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/api/v1/case/{case_id}/observable"
        payload = {
            "dataType": data_type,
            "data": [data],
            "message": message,
            "ioc": True,
            "tlp": 2,
        }
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "observable": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"TheHive add_observable failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="thehive_create_case",
                name="thehive_create_case",
                description="Create a formal security incident response case in TheHive / SOAR platform",
                skills_provided=["case_management", "soar_incident", "incident_ticketing"],
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Clear incident title"},
                        "description": {"type": "string", "description": "Detailed incident executive summary and findings"},
                        "severity": {"type": "integer", "enum": [1, 2, 3, 4], "description": "1=Low, 2=Medium, 3=High, 4=Critical", "default": 3},
                    },
                    "required": ["title", "description"],
                },
                function=self.create_case,
                risk_level=RiskLevel.MEDIUM,
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://thehive.corp.internal:9000"),
            ),
            ToolSpec(
                tool_id="thehive_add_observable",
                name="thehive_add_observable",
                description="Attach an IoC observable (IP, domain, hash, URL) to a TheHive security incident case",
                skills_provided=["case_management", "soar_incident", "attach_ioc"],
                parameters={
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string", "description": "TheHive Case ID or Number"},
                        "data_type": {"type": "string", "enum": ["ip", "domain", "hash", "url", "user"], "description": "Type of observable"},
                        "data": {"type": "string", "description": "The exact indicator value"},
                    },
                    "required": ["case_id", "data_type", "data"],
                },
                function=self.add_observable,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://thehive.corp.internal:9000"),
            ),
        ]
