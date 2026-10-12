"""
Okta Identity Cloud Connector

Enables identity-based incident containment: session termination, MFA factor resets,
and account suspension via Okta REST APIs.
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


class OktaConnector(BaseSecurityConnector):
    """Connector for Okta Identity Management."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "org_url": "https://corp.okta.com",
            "api_token": "",
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="okta",
            name="Okta Identity Cloud",
            category=ConnectorCategory.IAM,
            description="Manage corporate identities, revoke compromised user sessions, and suspend accounts in Okta",
            vendor="Okta",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        token = self.config.get("api_token", "")
        return {"Authorization": f"SSWS {token}", "Content-Type": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual Okta Org tenant (Active Users: 1,420)", 1.7

        url = f"{self.config.get('org_url', '').rstrip('/')}/api/v1/org"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    data = res.json()
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, f"Connected to Okta Org: {data.get('companyName', 'Corp')}", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Okta connection failed: {e}", latency

    async def get_user(self, login_or_id: str) -> str:
        """Find user profile, status, and MFA enrollment in Okta."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "user": {
                    "id": "00u1a2b3c4d5e6f7g8h9",
                    "status": "ACTIVE",
                    "profile": {
                        "firstName": "John",
                        "lastName": "Doe",
                        "email": login_or_id if "@" in login_or_id else f"{login_or_id}@corp.com",
                        "login": login_or_id if "@" in login_or_id else f"{login_or_id}@corp.com",
                        "department": "Engineering",
                        "title": "DevOps Engineer"
                    },
                    "activated": "2024-01-15T08:00:00Z",
                    "lastLogin": "2026-09-28T12:15:00Z"
                }
            }, indent=2)

        url = f"{self.config.get('org_url', '').rstrip('/')}/api/v1/users/{login_or_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "user": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Okta get_user failed: {e}"})

    async def clear_user_sessions(self, user_id: str, justification: str) -> str:
        """Terminate all active SSO and app sessions for a user across the enterprise."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "user_id": user_id,
                "action": "clear_sessions",
                "justification": justification,
                "message": f"[IDENTITY CONTAINMENT] All active Okta SSO and SAML/OIDC app sessions revoked for user {user_id}. Attacker session tokens invalidated immediately."
            }, indent=2)

        url = f"{self.config.get('org_url', '').rstrip('/')}/api/v1/users/{user_id}/sessions"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.delete(url, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "user_id": user_id, "message": "Sessions revoked successfully"}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Okta clear_sessions failed: {e}"})

    async def suspend_user(self, user_id: str, justification: str) -> str:
        """Suspend user account in Okta (disables all sign-ins)."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "user_id": user_id,
                "action": "suspend",
                "justification": justification,
                "message": f"[IDENTITY CONTAINMENT] User {user_id} suspended in Okta. Account state changed to SUSPENDED. All authentications blocked."
            }, indent=2)

        url = f"{self.config.get('org_url', '').rstrip('/')}/api/v1/users/{user_id}/lifecycle/suspend"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "user_id": user_id, "message": "User suspended successfully"}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Okta suspend failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="okta_get_user",
                name="okta_get_user",
                description="Query Okta user profile, department, account state, and last login timestamp",
                skills_provided=["identity_lookup", "iam_investigation", "user_context"],
                parameters={
                    "type": "object",
                    "properties": {
                        "login_or_id": {"type": "string", "description": "User email, username, or Okta User ID"},
                    },
                    "required": ["login_or_id"],
                },
                function=self.get_user,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host=self.config.get("org_url", "https://corp.okta.com"),
            ),
            ToolSpec(
                tool_id="okta_clear_user_sessions",
                name="okta_clear_user_sessions",
                description="[CONTAINMENT ACTION] Revoke all active Okta SSO, OIDC, and application sessions for compromised user",
                skills_provided=["session_revocation", "identity_containment", "credential_invalidation"],
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "Okta User ID or user email"},
                        "justification": {"type": "string", "description": "Operational reason for revoking sessions"},
                    },
                    "required": ["user_id", "justification"],
                },
                function=self.clear_user_sessions,
                risk_level=RiskLevel.HIGH,  # High risk containment
                source_type="connector",
                server_or_host=self.config.get("org_url", "https://corp.okta.com"),
            ),
            ToolSpec(
                tool_id="okta_suspend_user",
                name="okta_suspend_user",
                description="[CONTAINMENT ACTION] Suspend compromised user account in Okta (blocks all logins immediately)",
                skills_provided=["account_suspension", "identity_containment"],
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "Okta User ID or user email"},
                        "justification": {"type": "string", "description": "Reason for account suspension"},
                    },
                    "required": ["user_id", "justification"],
                },
                function=self.suspend_user,
                risk_level=RiskLevel.HIGH,  # High risk containment
                source_type="connector",
                server_or_host=self.config.get("org_url", "https://corp.okta.com"),
            ),
        ]
