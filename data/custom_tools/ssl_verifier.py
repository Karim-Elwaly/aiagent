"""
Sample Custom Tool: SSL Verifier

Auto-generated and persisted custom tool demonstrating AI Skill Builder capabilities.
"""

from __future__ import annotations

import datetime
import socket
import ssl

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec


async def verify_ssl_cert(hostname: str, port: int = 443) -> str:
    """Check if the SSL certificate for a given hostname is valid and return expiry details."""
    clean_host = hostname.replace("https://", "").replace("http://", "").split("/")[0]
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((clean_host, port), timeout=5.0) as sock:
            with ctx.wrap_socket(sock, server_hostname=clean_host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return f"No certificate found for {clean_host}"

                not_after_str = cert.get("notAfter", "")
                # Format: 'May 10 12:00:00 2026 GMT'
                expire_date = datetime.datetime.strptime(
                    not_after_str, "%b %d %H:%M:%S %Y %Z"
                ).replace(tzinfo=datetime.timezone.utc)
                now = datetime.datetime.now(datetime.timezone.utc)
                days_left = (expire_date - now).days

                return (
                    f"SSL Certificate for {clean_host}:\n"
                    f"- Status: {'EXPIRED' if days_left <= 0 else 'VALID'}\n"
                    f"- Expires: {not_after_str}\n"
                    f"- Days Remaining: {days_left} days"
                )
    except Exception as e:
        return f"SSL Verification failed for {clean_host}: {e}"


VERIFY_SSL_CERT_SPEC = ToolSpec(
    tool_id="verify_ssl_cert_v1",
    name="verify_ssl_cert",
    description="Verify SSL/TLS certificate validity, expiration date, and days remaining for any domain.",
    skills_provided=["ssl_verification", "security_audit"],
    parameters={
        "hostname": {
            "type": "string",
            "description": "The domain name to verify (e.g. 'google.com' or 'github.com')",
            "required": True,
        },
        "port": {
            "type": "integer",
            "description": "Port number (default 443)",
            "required": False,
        },
    },
    function=verify_ssl_cert,
    risk_level=RiskLevel.LOW,
)
