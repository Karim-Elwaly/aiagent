"""
Security Connector Manager

Orchestrates lifecycle, credential persistence, health monitoring,
and dynamic ToolRegistry registration for all enterprise security connectors.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.connectors.base import BaseSecurityConnector, ConnectorStatus
from src.connectors.implementations import ALL_CONNECTOR_CLASSES
from src.core.config import ROOT_DIR
from src.registry.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

CONFIG_PATH = ROOT_DIR / "data" / "connectors.json"


class ConnectorManager:
    """Central lifecycle and registration manager for security connectors."""

    _instance: ConnectorManager | None = None

    def __init__(self):
        self._connectors: dict[str, BaseSecurityConnector] = {}
        self._registry: ToolRegistry | None = None
        self._initialized: bool = False

    @classmethod
    def get_instance(cls) -> ConnectorManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_stored_configs(self) -> dict[str, dict[str, Any]]:
        if not CONFIG_PATH.exists():
            return {}
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not read connector config from %s: %s", CONFIG_PATH, e)
            return {}

    def _save_configs(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for cid, conn in self._connectors.items():
                data[cid] = conn.config
            CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save connector configs to %s: %s", CONFIG_PATH, e)

    async def initialize(self, registry: ToolRegistry | None = None) -> None:
        """Initialize all connector classes and register active tools into ToolRegistry."""
        self._registry = registry
        stored_configs = self._load_stored_configs()

        for cls_factory in ALL_CONNECTOR_CLASSES:
            try:
                # Instantiate with default configuration
                temp_inst = cls_factory()
                cid = temp_inst.connector_id
                stored = stored_configs.get(cid, {})
                
                # Re-instantiate with merged stored config
                conn = cls_factory(config=stored)
                self._connectors[cid] = conn

                # Quick initial status assessment
                if not conn.enabled:
                    conn.status = ConnectorStatus.DISCONNECTED
                elif conn.is_live:
                    conn.status = ConnectorStatus.CONNECTED
                else:
                    conn.status = ConnectorStatus.SIMULATED

                logger.info(
                    "Initialized Security Connector [%s] (%s) - Status: %s",
                    conn.name,
                    conn.category.value,
                    conn.status.value,
                )
            except Exception as e:
                logger.error("Failed to initialize connector class %s: %s", cls_factory, e)

        # Register tools in ToolRegistry if registry provided
        if self._registry:
            self.register_tools_to(self._registry)

        self._save_configs()
        self._initialized = True

    def register_tools_to(self, registry: ToolRegistry) -> int:
        """Register all exported ToolSpecs from enabled connectors into the ToolRegistry."""
        count = 0
        for conn in self._connectors.values():
            if not conn.enabled:
                continue
            for tool_spec in conn.export_tools():
                try:
                    registry.register(tool_spec)
                    count += 1
                except Exception as e:
                    logger.error(
                        "Error registering tool '%s' from connector '%s': %s",
                        tool_spec.name,
                        conn.connector_id,
                        e,
                    )
        logger.info("Registered %d tools from enterprise security connectors", count)
        return count

    def list_connectors(self, mask_secrets: bool = True) -> list[dict[str, Any]]:
        """Return serialized list of all connectors for UI and API."""
        return [c.to_dict(mask_secrets=mask_secrets) for c in self._connectors.values()]

    def get_connector(self, connector_id: str) -> BaseSecurityConnector | None:
        return self._connectors.get(connector_id)

    async def test_connector(self, connector_id: str) -> tuple[bool, str, float]:
        """Test connection for a specific connector."""
        conn = self.get_connector(connector_id)
        if not conn:
            return False, f"Connector '{connector_id}' not found", 0.0

        success, message, latency = await conn.test_connection()
        return success, message, latency

    async def configure_connector(
        self,
        connector_id: str,
        new_config: dict[str, Any],
        registry: ToolRegistry | None = None,
    ) -> dict[str, Any]:
        """Update connector settings, persist, and update registered tools."""
        conn = self.get_connector(connector_id)
        if not conn:
            raise ValueError(f"Connector '{connector_id}' not found")

        # Unregister previous tools if registry present
        reg = registry or self._registry
        if reg:
            for tool in conn.export_tools():
                reg.unregister(tool.tool_id)

        # Update config
        conn.update_config(new_config)

        # Re-register tools if enabled
        if conn.enabled and reg:
            for tool in conn.export_tools():
                reg.register(tool)

        # Run test connection
        await conn.test_connection()

        # Persist changes
        self._save_configs()

        return conn.to_dict(mask_secrets=True)


def get_connector_manager() -> ConnectorManager:
    """Return the global ConnectorManager singleton."""
    return ConnectorManager.get_instance()
