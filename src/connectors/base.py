"""
Base Security Connector Interface

Defines the contract and lifecycle for all enterprise security tool connectors
(SIEM, EDR, Firewall, IAM, Threat Intelligence, and ITSM/SOAR).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


class ConnectorCategory(str, Enum):
    """Functional category of enterprise security tooling."""

    SIEM = "siem"
    EDR = "edr"
    FIREWALL = "firewall"
    IAM = "iam"
    THREAT_INTEL = "threat_intel"
    ITSM = "itsm"


class ConnectorStatus(str, Enum):
    """Runtime status of an integration."""

    CONNECTED = "connected"        # Live connection verified via API
    SIMULATED = "simulated"        # Operating in realistic sandbox/mock mode
    DISCONNECTED = "disconnected"  # Missing credentials or disabled
    ERROR = "error"                # Health check failed / auth error


class BaseSecurityConnector(ABC):
    """Abstract Base Class for all Enterprise Security Connectors."""

    def __init__(
        self,
        connector_id: str,
        name: str,
        category: ConnectorCategory,
        description: str,
        vendor: str,
        default_config: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.connector_id = connector_id
        self.name = name
        self.category = category
        self.description = description
        self.vendor = vendor
        self.default_config = default_config or {}
        self.config: dict[str, Any] = {**self.default_config, **(config or {})}
        self.enabled: bool = bool(self.config.get("enabled", True))
        self.status: ConnectorStatus = ConnectorStatus.SIMULATED
        self.last_error: str | None = None
        self.last_checked: float = 0.0

    @property
    def is_live(self) -> bool:
        """Return True if connector has live credentials and is configured for real API calls."""
        # By default, if credentials (api_key/token/secret) are set and simulated=False, run live
        if self.config.get("simulated") is True:
            return False
        # Check standard credential fields
        for cred_key in ("api_key", "token", "client_secret", "password"):
            val = self.config.get(cred_key, "")
            if val and not str(val).startswith("dummy") and not str(val).startswith("mock"):
                return True
        return False

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str, float]:
        """Test authentication and endpoint connectivity.

        Returns:
            tuple of (is_successful, message, latency_ms)
        """
        pass

    @abstractmethod
    def export_tools(self) -> list[ToolSpec]:
        """Export connector capabilities as executable ToolSpecs for LLM agents."""
        pass

    def update_config(self, new_config: dict[str, Any]) -> None:
        """Update connector configuration dictionary."""
        self.config.update(new_config)
        self.enabled = bool(self.config.get("enabled", True))

    def to_dict(self, mask_secrets: bool = True) -> dict[str, Any]:
        """Serialize connector metadata and status for API/UI display."""
        safe_config = dict(self.config)
        if mask_secrets:
            for k in list(safe_config.keys()):
                kl = k.lower()
                if any(sec in kl for sec in ("key", "secret", "token", "password", "auth")):
                    val = str(safe_config[k])
                    if len(val) > 8:
                        safe_config[k] = val[:3] + "..." + val[-3:]
                    else:
                        safe_config[k] = "******"

        return {
            "connector_id": self.connector_id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "vendor": self.vendor,
            "enabled": self.enabled,
            "status": self.status.value,
            "is_live": self.is_live,
            "last_error": self.last_error,
            "last_checked": self.last_checked,
            "config": safe_config,
            "supported_tools": [tool.name for tool in self.export_tools()],
        }
