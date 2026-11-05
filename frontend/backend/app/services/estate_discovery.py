from urllib.parse import urlsplit

from app.core.config import settings
from app.schemas.domain import (
    AvailableModel,
    HermesEstateInventory,
    InstalledSkill,
    RegisteredTool,
    RiskLevel,
)
from app.services.hermes_gateway import HermesGatewayError, connected_hermes


def _safe_node_id(base_url: str) -> str:
    host = urlsplit(base_url).hostname or "unknown"
    return f"hermes-{host.lower().replace('.', '-')}"


def _tool_risk(tool_id: str, mcp_server: str | None) -> tuple[RiskLevel, bool, str, bool]:
    override = settings.hermes_tool_risk_overrides.get(tool_id)
    if override is not None:
        return override, override is not RiskLevel.READ_ONLY, "operator-override", True
    if mcp_server:
        return RiskLevel.EXTERNAL_EGRESS, True, "mcp-server-boundary", False
    return RiskLevel.STATE_MUTATING, True, "conservative-unclassified-default", False


async def estate_summary() -> HermesEstateInventory:
    """Discover only capabilities returned by the connected Hermes gateway."""
    node_id = _safe_node_id(settings.hermes_base_url)
    try:
        async with connected_hermes() as hermes:
            toolsets = await hermes.call("tools.list")
            tool_details = await hermes.call("tools.show")
            skills_result = await hermes.call("skills.manage", {"action": "list"})
            model_result = await hermes.call("model.options")
            mcp_result = await hermes.call("mcp.servers.list")
            setup_result = await hermes.call("setup.status")
    except HermesGatewayError as error:
        return HermesEstateInventory(connected=False, connection_error=str(error))

    enabled_toolsets = [row for row in toolsets.get("toolsets", []) if row.get("enabled")]
    descriptions: dict[str, str] = {}
    for section in tool_details.get("sections", []):
        for tool in section.get("tools", []):
            if tool.get("name"):
                descriptions[tool["name"]] = tool.get("description", "")

    mcp_by_tool: dict[str, tuple[str, dict]] = {}
    for server in mcp_result.get("servers", []):
        server_name = server.get("name", "")
        for tool in server.get("tools", []) or []:
            tool_name = tool.get("name") if isinstance(tool, dict) else str(tool)
            if tool_name:
                mcp_by_tool[tool_name] = (server_name, tool if isinstance(tool, dict) else {})

    registered_tools = []
    for toolset in enabled_toolsets:
        for tool_id in toolset.get("tools") or []:
            server_info = mcp_by_tool.get(tool_id)
            mcp_server, tool_detail = server_info if server_info else (None, {})
            risk, requires_approval, risk_source, risk_assessed = _tool_risk(tool_id, mcp_server)
            schema = tool_detail.get("inputSchema") or tool_detail.get("input_schema") or {}
            registered_tools.append(
                RegisteredTool(
                    tool_id=tool_id,
                    mcp_server=mcp_server,
                    parameter_schema=schema,
                    risk_level=risk,
                    requires_hitl_approval=requires_approval,
                    risk_classification_source=risk_source,
                    risk_assessed=risk_assessed,
                    description=descriptions.get(tool_id, tool_detail.get("description", "")),
                )
            )

    registered_ids = {tool.tool_id for tool in registered_tools}
    for tool_id, (mcp_server, tool_detail) in mcp_by_tool.items():
        if tool_id in registered_ids:
            continue
        registered_tools.append(
            RegisteredTool(
                tool_id=tool_id,
                mcp_server=mcp_server,
                parameter_schema=tool_detail.get("inputSchema") or tool_detail.get("input_schema") or {},
                risk_level=RiskLevel.EXTERNAL_EGRESS,
                requires_hitl_approval=True,
                risk_classification_source="mcp-server-boundary",
                risk_assessed=False,
                description=tool_detail.get("description", ""),
            )
        )

    installed_skills = []
    skill_groups = skills_result.get("skills") or {}
    for category, names in skill_groups.items():
        for skill_id in names:
            installed_skills.append(
                InstalledSkill(
                    skill_id=skill_id,
                    version="unknown",
                    description=(
                        f"Hermes skill in category '{category}'. The gateway list method does not expose "
                        "the skill description or version."
                    ),
                    host_node_ids=[node_id],
                )
            )

    available_models = []
    for provider in model_result.get("providers", []):
        provider_id = provider.get("slug", "unknown")
        is_local = provider_id.lower() in {"gpu", "local"}
        for model_id in provider.get("models", []) or []:
            if not isinstance(model_id, str) or not model_id:
                continue
            available_models.append(
                AvailableModel(
                    family=provider_id,
                    version=model_id,
                    cloud=not is_local,
                    data_residencies=["local"] if is_local else [],
                    reasoning_tier=None,
                    estimated_daily_cost_usd=0 if is_local else None,
                    residency_verified=is_local,
                    cost_basis=("local provider; vendor inference charge not reported by Hermes" if is_local else None),
                )
            )

    # setup.status.provider_configured is false for custom OpenAI-compatible
    # providers (for example the local "gpu" provider).  Derive readiness from
    # the provider Hermes actually marks as current instead.
    providers = [row for row in model_result.get("providers", []) if isinstance(row, dict)]
    current_provider = next((row for row in providers if row.get("is_current")), None)
    if current_provider is None and len(providers) == 1:
        current_provider = providers[0]
    current_provider_id = (current_provider or {}).get("slug")
    current_models = (current_provider or {}).get("models") or []
    provider_configured = bool(
        current_provider
        and current_models
        and current_provider.get("authenticated", True) is not False
    )
    if not provider_configured:
        provider_configured = bool(
            setup_result.get("provider_configured") or setup_result.get("ready")
        )

    return HermesEstateInventory(
        connected=True,
        runtime_hooks_enabled=settings.hermes_hooks_enabled,
        hermes_version=None,
        profile=setup_result.get("profile"),
        inference_provider=(
            current_provider_id
            or setup_result.get("inference_provider")
            or ("local" if available_models else None)
        ),
        provider_configured=provider_configured,
        installed_skills=installed_skills,
        registered_tools=registered_tools,
        available_models=available_models,
    )