"""
Microsoft Sentinel & Azure Log Analytics Connector

Provides KQL (Kusto Query Language) analytics, incident triage, and cloud threat
investigation via Microsoft Graph Security and Azure Monitor REST APIs.
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


class MicrosoftSentinelConnector(BaseSecurityConnector):
    """Connector for Microsoft Sentinel and Azure Log Analytics."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "workspace_id": "8b3f9104-e3c2-4912-8700-112233445566",
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "bearer_token": "",
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="sentinel",
            name="Microsoft Sentinel",
            category=ConnectorCategory.SIEM,
            description="Query Azure Log Analytics workspaces with KQL, triage Sentinel cloud incidents, and hunt across M365",
            vendor="Microsoft",
            default_config=default_config,
            config=config,
        )

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual Microsoft Sentinel Workspace (Azure East US)", 1.8

        wid = self.config.get("workspace_id", "")
        token = self.config.get("bearer_token", "")
        url = f"https://api.loganalytics.io/v1/workspaces/{wid}/query"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json={"query": "print 'ping'"}, headers=headers)
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, "Successfully connected to Microsoft Sentinel workspace", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Sentinel connection failed: {e}", latency

    async def query_kql(self, kql_query: str, timespan: str = "P1D") -> str:
        """Execute a KQL (Kusto Query Language) query against Microsoft Sentinel tables."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "workspace": self.config.get("workspace_id", "demo-workspace"),
                "kql": kql_query,
                "timespan": timespan,
                "rows_returned": 2,
                "tables": [
                    {
                        "name": "SecurityEvent",
                        "columns": ["TimeGenerated", "Account", "Computer", "EventID", "Activity"],
                        "rows": [
                            ["2026-09-28T12:15:01Z", "root", "DMZ-JUMP01", 4625, "An account failed to log on."],
                            ["2026-09-28T12:15:03Z", "admin", "DMZ-JUMP01", 4625, "An account failed to log on."]
                        ]
                    }
                ]
            }, indent=2)

        wid = self.config.get("workspace_id", "")
        token = self.config.get("bearer_token", "")
        url = f"https://api.loganalytics.io/v1/workspaces/{wid}/query"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json={"query": kql_query, "timespan": timespan}, headers=headers)
                res.raise_for_status()
                return json.dumps({"status": "success", "data": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"KQL query failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="sentinel_query_kql",
                name="sentinel_query_kql",
                description="Run KQL (Kusto Query Language) queries across Microsoft Sentinel, Defender XDR, and Azure Activity tables",
                skills_provided=["siem_search", "kql_query", "cloud_threat_hunting"],
                parameters={
                    "type": "object",
                    "properties": {
                        "kql_query": {"type": "string", "description": "KQL query (e.g. 'SecurityAlert | where Severity == \"High\" | take 10')"},
                        "timespan": {"type": "string", "description": "ISO 8601 duration (e.g. 'P1D' for 1 day, 'PT1H' for 1 hour)", "default": "P1D"},
                    },
                    "required": ["kql_query"],
                },
                function=self.query_kql,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("workspace_id", "https://api.loganalytics.io"),
            ),
        ]
