"""
AbuseIPDB Threat Intelligence Connector

Provides IP abuse confidence scoring, ISP attribution, and malicious activity
reporting via AbuseIPDB v2 REST API.
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


class AbuseIPDBConnector(BaseSecurityConnector):
    """Connector for AbuseIPDB IP reputation database."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "api_key": "",
            "base_url": "https://api.abuseipdb.com/api/v2",
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="abuseipdb",
            name="AbuseIPDB Threat Intel",
            category=ConnectorCategory.THREAT_INTEL,
            description="Query community abuse confidence scores, domain names, and ISP reputation for external IP addresses",
            vendor="AbuseIPDB",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        key = self.config.get("api_key", "")
        return {"Key": key, "Accept": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual AbuseIPDB API v2", 1.0

        url = f"{self.config.get('base_url', '').rstrip('/')}/check"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, params={"ipAddress": "1.1.1.1", "maxAgeInDays": 1}, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, "Successfully connected to AbuseIPDB API", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"AbuseIPDB connection failed: {e}", latency

    async def check_ip(self, ip_address: str, max_age_days: int = 90) -> str:
        """Check the community abuse confidence score and malicious history of an IP."""
        if not self.is_live:
            is_mal = ip_address in ("198.51.100.220", "198.51.100.75", "198.51.100.50", "203.0.113.88", "185.220.101.45")
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "ipAddress": ip_address,
                "abuseConfidenceScore": 100 if is_mal else 0,
                "isPublic": True,
                "countryCode": "NL" if is_mal else "US",
                "usageType": "Data Center/Web Hosting/Transit" if is_mal else "Content Delivery Network",
                "isp": "HostEurope GmbH" if is_mal else "Cloudflare",
                "domain": "hosteurope.de" if is_mal else "cloudflare.com",
                "totalReports": 412 if is_mal else 0,
                "numDistinctUsers": 128 if is_mal else 0,
                "lastReportedAt": "2026-09-28T12:00:00Z" if is_mal else None
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/check"
        params = {"ipAddress": ip_address, "maxAgeInDays": max_age_days, "verbose": True}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, params=params, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "data": res.json().get("data", {})}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"AbuseIPDB check failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="abuseipdb_check_ip",
                name="abuseipdb_check_ip",
                description="Query AbuseIPDB confidence score, report count, and ISP ownership for external IPv4/IPv6",
                skills_provided=["threat_intel", "ioc_enrichment", "ip_reputation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "ip_address": {"type": "string", "description": "The external IP address to check"},
                        "max_age_days": {"type": "integer", "description": "Lookback window in days (default: 90)", "default": 90},
                    },
                    "required": ["ip_address"],
                },
                function=self.check_ip,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host="https://api.abuseipdb.com",
            ),
        ]
