"""
Splunk Enterprise & Cloud SIEM Connector

Provides SPL (Search Processing Language) query execution, index querying,
and event correlation via Splunk REST API (`/services/search/jobs/export`).
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


class SplunkConnector(BaseSecurityConnector):
    """Connector for Splunk Enterprise / Splunk Cloud."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "base_url": "https://localhost:8089",
            "token": "",
            "username": "admin",
            "password": "",
            "verify_ssl": False,
            "timeout_seconds": 20.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="splunk",
            name="Splunk Enterprise SIEM",
            category=ConnectorCategory.SIEM,
            description="Execute SPL search queries, pull SIEM correlations, and inspect raw event data in Splunk",
            vendor="Splunk",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        headers = {}
        token = self.config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_auth(self) -> tuple[str, str] | None:
        if not self.config.get("token"):
            u = self.config.get("username")
            p = self.config.get("password")
            if u and p:
                return (u, p)
        return None

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual Splunk Enterprise cluster v9.2.1", 1.5

        url = f"{self.config.get('base_url', '').rstrip('/')}/services/server/info?output_mode=json"
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=self.config.get("timeout_seconds", 10)) as client:
                res = await client.get(url, headers=self._get_headers(), auth=self._get_auth())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    data = res.json()
                    entry = data.get("entry", [{}])[0].get("content", {})
                    v = entry.get("version", "unknown")
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, f"Connected to Splunk Enterprise v{v} (Server: {entry.get('serverName', 'default')})", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Splunk connection failed: {e}", latency

    async def search_spl(self, spl_query: str, earliest_time: str = "-24h", limit: int = 25) -> str:
        """Execute an SPL (Search Processing Language) search job and stream back results."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "spl": spl_query,
                "earliest_time": earliest_time,
                "total_events": 3,
                "events": [
                    {
                        "_time": "2026-09-28 11:33:05",
                        "host": "cisco-asa-01",
                        "source": "udp:514",
                        "sourcetype": "cisco:asa",
                        "action": "denied",
                        "src_ip": "198.51.100.220",
                        "dest_ip": "10.10.10.20",
                        "dest_port": "22",
                        "_raw": "Sep 14 11:33:05 asa-core-01 %ASA-4-106023: Deny tcp src outside:198.51.100.220/51235 dst dmz:10.10.10.20/22"
                    },
                    {
                        "_time": "2026-09-28 12:10:05",
                        "host": "fgt-core-01",
                        "source": "syslog",
                        "sourcetype": "fortigate:utm",
                        "action": "clear_session",
                        "attack": "syn_flood",
                        "dest_ip": "198.51.100.10",
                        "dest_port": "80",
                        "_raw": "date=2026-09-14 time=12:10:05 type=\"utm\" subtype=\"anomaly\" attack=\"syn_flood\" dstip=\"198.51.100.10\" dstport=80"
                    },
                    {
                        "_time": "2026-09-28 12:15:01",
                        "host": "cisco-asa-01",
                        "source": "udp:514",
                        "sourcetype": "cisco:asa",
                        "user": "root",
                        "src_ip": "198.51.100.75",
                        "dest_ip": "10.10.10.25",
                        "dest_port": "22",
                        "_raw": "Sep 14 12:15:01 asa-core-01 %ASA-6-113015: AAA user authentication Rejected : reason = 'User authentication failed' : user = root : user IP = 198.51.100.75"
                    }
                ]
            }, indent=2)

        # Prepend 'search ' if missing
        q = spl_query.strip()
        if not q.startswith("|") and not q.startswith("search"):
            q = f"search {q}"

        url = f"{self.config.get('base_url', '').rstrip('/')}/services/search/jobs/export"
        payload = {
            "search": q,
            "earliest_time": earliest_time,
            "output_mode": "json",
            "count": limit,
        }
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=self.config.get("timeout_seconds", 20)) as client:
                res = await client.post(url, data=payload, headers=self._get_headers(), auth=self._get_auth())
                res.raise_for_status()
                # Parse JSON stream lines
                events = []
                for line in res.text.strip().splitlines():
                    if line:
                        try:
                            parsed = json.loads(line)
                            if "result" in parsed:
                                events.append(parsed["result"])
                        except Exception:
                            continue
                return json.dumps({"status": "success", "count": len(events), "events": events[:limit]}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Splunk export failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="splunk_search_spl",
                name="splunk_search_spl",
                description="Execute an SPL (Search Processing Language) query against enterprise Splunk indices",
                skills_provided=["siem_search", "splunk_query", "telemetry_investigation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "spl_query": {"type": "string", "description": "Splunk SPL search string (e.g. 'index=security_fw action=blocked | stats count by src_ip')"},
                        "earliest_time": {"type": "string", "description": "Relative earliest time window (e.g. '-24h', '-7d', '-1h')", "default": "-24h"},
                        "limit": {"type": "integer", "description": "Max events to return", "default": 25},
                    },
                    "required": ["spl_query"],
                },
                function=self.search_spl,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("base_url", "https://localhost:8089"),
            ),
        ]
