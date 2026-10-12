"""
Microsoft Entra ID (Azure Active Directory) Connector

Enables enterprise identity investigation, refresh token invalidation, and account
lockout via Microsoft Graph REST API v1.0.
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


class EntraIdConnector(BaseSecurityConnector):
    """Connector for Microsoft Entra ID (Azure AD)."""

    def __init__(self, config: dict[str, Any] | None = None):
        default_config = {
            "enabled": True,
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "bearer_token": "",
            "timeout_seconds": 15.0,
            "simulated": False,
        }
        super().__init__(
            connector_id="entra_id",
            name="Microsoft Entra ID",
            category=ConnectorCategory.IAM,
            description="Investigate Entra ID user accounts, revoke active sign-in sessions, and disable compromised identities",
            vendor="Microsoft",
            default_config=default_config,
            config=config,
        )

    def _get_headers(self) -> dict[str, str]:
        token = self.config.get("bearer_token", "")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.perf_counter()
        if not self.is_live:
            self.status = ConnectorStatus.SIMULATED
            self.last_checked = time.time()
            return True, "Simulation Mode: Connected to virtual Microsoft Entra ID tenant (M365 Enterprise)", 1.5

        url = "https://graph.microsoft.com/v1.0/organization"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers())
                latency = (time.perf_counter() - start) * 1000
                if res.status_code == 200:
                    data = res.json().get("value", [{}])[0]
                    self.status = ConnectorStatus.CONNECTED
                    self.last_error = None
                    self.last_checked = time.time()
                    return True, f"Connected to Microsoft Entra tenant: {data.get('displayName', 'Org')}", latency
                else:
                    self.status = ConnectorStatus.ERROR
                    self.last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    return False, self.last_error, latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            return False, f"Entra ID connection failed: {e}", latency

    async def get_user(self, user_principal_name: str) -> str:
        """Find Entra ID user account properties and sign-in status."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "user": {
                    "id": "e9a8b7c6-d5e4-3f2a-1b0c-9d8e7f6a5b4c",
                    "userPrincipalName": user_principal_name if "@" in user_principal_name else f"{user_principal_name}@corp.com",
                    "displayName": "Sarah Connor",
                    "jobTitle": "Security Operations Lead",
                    "department": "IT Security",
                    "accountEnabled": True,
                    "mail": user_principal_name if "@" in user_principal_name else f"{user_principal_name}@corp.com",
                }
            }, indent=2)

        url = f"https://graph.microsoft.com/v1.0/users/{user_principal_name}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "user": res.json()}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Entra ID get_user failed: {e}"})

    async def revoke_sessions(self, user_id: str, justification: str) -> str:
        """Revoke all active refresh tokens and sign-in sessions for a user."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "user_id": user_id,
                "action": "revokeSignInSessions",
                "justification": justification,
                "message": f"[IDENTITY CONTAINMENT] Revoked all refresh tokens and active sign-in sessions for {user_id} via Microsoft Graph. User forced to re-authenticate with MFA."
            }, indent=2)

        url = f"https://graph.microsoft.com/v1.0/users/{user_id}/revokeSignInSessions"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "user_id": user_id, "message": "Sign-in sessions revoked"}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Entra ID session revocation failed: {e}"})

    async def disable_account(self, user_id: str, justification: str) -> str:
        """Disable a compromised user account in Entra ID (accountEnabled = false)."""
        if not self.is_live:
            return json.dumps({
                "status": "success",
                "mode": "simulated",
                "user_id": user_id,
                "action": "disable_account",
                "justification": justification,
                "message": f"[IDENTITY CONTAINMENT] User account {user_id} disabled (accountEnabled=False). Entra ID token issuance halted."
            }, indent=2)

        url = f"https://graph.microsoft.com/v1.0/users/{user_id}"
        payload = {"accountEnabled": False}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.patch(url, json=payload, headers=self._get_headers())
                res.raise_for_status()
                return json.dumps({"status": "success", "user_id": user_id, "accountEnabled": False}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Entra ID disable_account failed: {e}"})

    def export_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                tool_id="entraid_get_user",
                name="entraid_get_user",
                description="Query user account attributes, department, and accountEnabled state in Microsoft Entra ID",
                skills_provided=["identity_lookup", "iam_investigation", "user_context"],
                parameters={
                    "type": "object",
                    "properties": {
                        "user_principal_name": {"type": "string", "description": "User email or User Principal Name (UPN)"},
                    },
                    "required": ["user_principal_name"],
                },
                function=self.get_user,
                risk_level=RiskLevel.LOW,
                source_type="connector",
                server_or_host="https://graph.microsoft.com",
            ),
            ToolSpec(
                tool_id="entraid_revoke_sessions",
                name="entraid_revoke_sessions",
                description="[CONTAINMENT ACTION] Invalidate all active Microsoft 365 and Entra ID refresh tokens for compromised identity",
                skills_provided=["session_revocation", "identity_containment"],
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "User Principal Name (UPN) or Object ID"},
                        "justification": {"type": "string", "description": "Security operational reason for revocation"},
                    },
                    "required": ["user_id", "justification"],
                },
                function=self.revoke_sessions,
                risk_level=RiskLevel.HIGH,  # High risk containment
                source_type="connector",
                server_or_host="https://graph.microsoft.com",
            ),
            ToolSpec(
                tool_id="entraid_disable_account",
                name="entraid_disable_account",
                description="[CONTAINMENT ACTION] Disable compromised user account in Microsoft Entra ID (blocks M365 access)",
                skills_provided=["account_suspension", "identity_containment"],
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "User Principal Name (UPN) or Object ID"},
                        "justification": {"type": "string", "description": "Security reason for disabling account"},
                    },
                    "required": ["user_id", "justification"],
                },
                function=self.disable_account,
                risk_level=RiskLevel.HIGH,  # High risk containment
                source_type="connector",
                server_or_host="https://graph.microsoft.com",
            ),
        ]
