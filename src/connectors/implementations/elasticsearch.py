"""
Elasticsearch SIEM & Security Analytics Connector

Provides full log telemetry, ES|QL search, alert triage, and IoC hunting
across Elasticsearch 7.x/8.x, Elastic Security, and OpenSearch clusters.
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


class ElasticsearchConnector(BaseSecurityConnector):
    """Connector for Elasticsearch / Elastic SIEM."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "url": "https://localhost:9200",
            "api_key": "",
            "username": "elastic",
            "password": "",
            "default_index": "logs-*",
            "verify_ssl": False,
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="elasticsearch",
            name="Elasticsearch SIEM",
            category=ConnectorCategory.SIEM,
            description="Query enterprise telemetry, security event logs, and Elastic Security alerts via Lucene or ES|QL",
            vendor="Elastic",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self.config.get("api_key")
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        return headers

    def _get_auth(self) -> tuple[str, str] | None:
        if not self.config.get("api_key"):
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
            return True, "Simulation Mode: Connected to virtual Elasticsearch cluster v8.14.0 (Health: GREEN)", 1.2

        url = self.config.get("url", "").rstrip("/")
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=self.config.get("timeout_seconds", 10)) as client:
                res = await client.get(url, headers=self._get_headers(), auth=self._get_auth())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code in (200, 201):
                    data = res.json()
                    version = data.get("version", {}).get("number", "unknown")
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, f"Connected to Elasticsearch v{version} (cluster_name: {data.get('cluster_name', 'default')})", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Connection failed: {e}", latency

    async def search_logs(self, query: str, index_pattern: str | None = None, limit: int = 20) -> str:
        """Search logs using Lucene query syntax or query string."""
        idx = index_pattern or self.config.get("default_index", "logs-*")
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "cluster": "corp-siem-prod",
                "index": idx,
                "query": query,
                "total_hits": 4,
                "hits": [
                    {
                        "@timestamp": "2026-09-28T11:18:40.120Z",
                        "host": {"name": "dmz-web-app01", "ip": "172.16.10.80"},
                        "source": {"ip": "203.0.113.88", "port": 49200},
                        "destination": {"ip": "172.16.10.80", "port": 80},
                        "event": {"category": "web", "action": "blocked", "module": "mod_security"},
                        "message": "Apache Log4j RCE attempt detected via JNDI lookup string payload"
                    },
                    {
                        "@timestamp": "2026-09-28T11:33:05.450Z",
                        "host": {"name": "cisco-asa-edge", "ip": "10.10.10.1"},
                        "source": {"ip": "198.51.100.220"},
                        "destination": {"ip": "10.10.10.20", "port": 22},
                        "event": {"action": "drop", "code": "%ASA-4-106023"},
                        "message": "Deny tcp src outside:198.51.100.220 dst dmz:10.10.10.20/22 by access-group OUTSIDE_IN"
                    },
                    {
                        "@timestamp": "2026-09-28T12:10:05.000Z",
                        "host": {"name": "fgt-core01", "ip": "10.10.10.2"},
                        "destination": {"ip": "198.51.100.10", "port": 80},
                        "event": {"action": "clear_session", "dataset": "fortigate.anomaly"},
                        "message": "anomaly: syn_flood, 15240 > threshold 1000, current pps 3810"
                    },
                    {
                        "@timestamp": "2026-09-28T12:15:01.300Z",
                        "host": {"name": "cisco-asa-edge", "ip": "10.10.10.1"},
                        "source": {"ip": "198.51.100.75"},
                        "destination": {"ip": "10.10.10.25", "port": 22},
                        "event": {"action": "teardown", "code": "%ASA-6-302014"},
                        "message": "Teardown TCP connection for outside:198.51.100.75 to dmz:10.10.10.25/22 duration 0:00:01 Reset-I"
                    }
                ]
            }, indent=2)

        url = f"{self.config.get('url', '').rstrip('/')}/{idx}/_search"
        payload = {
            "query": {"query_string": {"query": query}},
            "size": limit,
            "sort": [{"@timestamp": {"order": "desc"}}]
        }
        try:
            async with httpx.AsyncClient(verify=self.config.get("verify_ssl", False), timeout=self.config.get("timeout_seconds", 15)) as client:
                res = await client.post(url, json=payload, headers=self._get_headers(), auth=self._get_auth())
                res.raise_for_status()
                data = res.json()
                hits = [h.get("_source", {}) for h in data.get("hits", {}).get("hits", [])]
                total = data.get("hits", {}).get("total", {}).get("value", len(hits))
                return json.dumps({"status": "success", "total_hits": total, "returned": len(hits), "hits": hits}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Elasticsearch search failed: {e}"})

    async def lookup_ioc(self, ioc_value: str, ioc_type: str = "ip") -> str:
        """Find all logs matching an IP, domain, or file hash across all indices."""
        q = f'"{ioc_value}"'
        if ioc_type.lower() == "ip":
            q = f"source.ip: {ioc_value} OR destination.ip: {ioc_value} OR client.ip: {ioc_value} OR server.ip: {ioc_value} OR \"{ioc_value}\""
        elif ioc_type.lower() in ("hash", "sha256", "md5"):
            q = f"file.hash.sha256: {ioc_value} OR file.hash.md5: {ioc_value} OR process.hash.sha256: {ioc_value} OR \"{ioc_value}\""
        elif ioc_type.lower() == "domain":
            q = f"dns.question.name: {ioc_value} OR url.domain: {ioc_value} OR \"{ioc_value}\""
        return await self.search_logs(query=q, limit=25)

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="elastic_search_logs",
                name="elastic_search_logs",
                description="Search enterprise SIEM logs in Elasticsearch via Lucene or query string syntax",
                skills_provided=["siem_search", "log_query", "telemetry_investigation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Lucene query or query string (e.g., 'event.action: deny AND source.ip: 198.51.100.*')"},
                        "index_pattern": {"type": "string", "description": "Index pattern (defaults to 'logs-*')", "default": "logs-*"},
                        "limit": {"type": "integer", "description": "Max log events to return", "default": 20},
                    },
                    "required": ["query"],
                },
                function=self.search_logs,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("url", "https://localhost:9200"),
            ),
            ToolSpec(
                tool_id="elastic_lookup_ioc",
                name="elastic_lookup_ioc",
                description="Perform cross-index correlation search for a specific IoC (IP address, file hash, domain)",
                skills_provided=["ioc_lookup", "threat_hunting", "telemetry_investigation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "ioc_value": {"type": "string", "description": "The exact indicator (e.g. '198.51.100.75' or 'a9f24e...')"},
                        "ioc_type": {"type": "string", "enum": ["ip", "hash", "domain"], "description": "Type of IoC", "default": "ip"},
                    },
                    "required": ["ioc_value"],
                },
                function=self.lookup_ioc,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("url", "https://localhost:9200"),
            ),
        ]
