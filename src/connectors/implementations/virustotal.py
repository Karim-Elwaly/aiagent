"""
VirusTotal v3 Threat Intelligence Connector

Provides automated reputation scoring, malware sandbox analysis, and adversary
attribution for IP addresses, file hashes, and domains via VirusTotal v3 REST API.
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


class VirusTotalConnector(BaseSecurityConnector):
    """Connector for VirusTotal v3 API."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "api_key": "",
            "base_url": "https://www.virustotal.com/api/v3",
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="virustotal",
            name="VirusTotal v3 CTI",
            category=ConnectorCategory.THREAT_INTEL,
            description="Enrich IoCs with global threat intelligence: file hashes, domain reputation, and malicious IP scores",
            vendor="Google / VirusTotal",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        key = self.config.get("api_key", "")
        return {"x-apikey": key, "Accept": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual VirusTotal v3 Intelligence Cloud", 1.1

        url = f"{self.config.get('base_url', '').rstrip('/')}/users/current"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    data = res.json().get("data", {}).get("attributes", {})
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, f"Connected to VirusTotal API (User: {data.get('user_id', 'standard')})", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"VirusTotal connection failed: {e}", latency

    async def lookup_ip(self, ip_address: str) -> str:
        """Query VirusTotal reputation and threat verdicts for an IPv4/IPv6 address."""
        if not self.is_live:
            # Deterministic, realistic simulation based on common test IPs
            is_mal = ip_address in ("198.51.100.220", "198.51.100.75", "198.51.100.50", "203.0.113.88", "185.220.101.45")
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "ip": ip_address,
                "reputation": -85 if is_mal else 10,
                "malicious_votes": 68 if is_mal else 0,
                "harmless_votes": 2 if is_mal else 85,
                "as_owner": "DigitalOcean LLC" if is_mal else "Cloudflare, Inc.",
                "country": "NL" if is_mal else "US",
                "tags": ["scanner", "c2", "tor-exit-node"] if is_mal else ["cdn"],
                "verdict": "MALICIOUS" if is_mal else "BENIGN"
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/ip_addresses/{ip_address}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=self._get_headers())
                res.raise_for_status()
                attr = res.json().get("data", {}).get("attributes", {})
                stats = attr.get("last_analysis_stats", {})
                return json.dumps({
                    "status": "success",
                    "ip": ip_address,
                    "reputation": attr.get("reputation", 0),
                    "analysis_stats": stats,
                    "as_owner": attr.get("as_owner", "unknown"),
                    "country": attr.get("country", "unknown"),
                    "tags": attr.get("tags", []),
                }, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"VirusTotal IP query failed: {e}"})

    async def lookup_hash(self, file_hash: str) -> str:
        """Query malware analysis, signatures, and threat family for a file hash (MD5, SHA1, SHA256)."""
        if not self.is_live:
            is_mal = file_hash.lower() in ("a9f24e12c1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8", "5d41402abc4b2a76b9719d911017c592")
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "hash": file_hash,
                "meaningful_name": "cobaltstrike_beacon.dll" if is_mal else "svchost.exe",
                "malicious_count": 62 if is_mal else 0,
                "total_engines": 72,
                "threat_classification": "Trojan.CobaltStrike/Beacon.Gen" if is_mal else "Clean",
                "magic": "PE32+ executable (DLL) (GUI) x86-64" if is_mal else "PE32 executable",
                "verdict": "MALICIOUS" if is_mal else "BENIGN"
            }, indent=2)

        url = f"{self.config.get('base_url', '').rstrip('/')}/files/{file_hash}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=self._get_headers())
                res.raise_for_status()
                attr = res.json().get("data", {}).get("attributes", {})
                return json.dumps({
                    "status": "success",
                    "hash": file_hash,
                    "stats": attr.get("last_analysis_stats", {}),
                    "meaningful_name": attr.get("meaningful_name", "unknown"),
                    "popular_threat_classification": attr.get("popular_threat_classification", {}),
                }, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"VirusTotal file query failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="virustotal_lookup_ip",
                name="virustotal_lookup_ip",
                description="Query global threat intelligence reputation, ASN, and engine verdicts for an external IP via VirusTotal",
                skills_provided=["threat_intel", "ioc_enrichment", "ip_reputation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "ip_address": {"type": "string", "description": "The external IP address to check"},
                    },
                    "required": ["ip_address"],
                },
                function=self.lookup_ip,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host="https://www.virustotal.com",
            ),
            ToolSpec(
                tool_id="virustotal_lookup_hash",
                name="virustotal_lookup_hash",
                description="Enrich file hash (SHA256, MD5, SHA1) with malware classification, family names, and antivirus detection counts",
                skills_provided=["threat_intel", "ioc_enrichment", "malware_analysis"],
                parameters={
                    "type": "object",
                    "properties": {
                        "file_hash": {"type": "string", "description": "SHA256, SHA1, or MD5 checksum"},
                    },
                    "required": ["file_hash"],
                },
                function=self.lookup_hash,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host="https://www.virustotal.com",
            ),
        ]
