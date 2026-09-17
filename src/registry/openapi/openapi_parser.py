"""OpenAPI 3.0 and Swagger 2.0 Specification Parser.

Parses API specifications into typed ToolSpec instances ready for the
UAOS ToolRegistry and Meta-Planner.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.core.models import RiskLevel
from src.registry.openapi.openapi_executor import create_openapi_tool_callable
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


def _load_spec_data(raw_spec: str | dict[str, Any]) -> dict[str, Any]:
    """Parse raw spec from string (JSON or YAML) or dict."""
    if isinstance(raw_spec, dict):
        return raw_spec

    # Try JSON first
    try:
        return json.loads(raw_spec)
    except json.JSONDecodeError:
        pass

    # Try YAML if available
    try:
        import yaml
        return yaml.safe_load(raw_spec)
    except ImportError:
        raise ValueError(
            "Spec is not valid JSON and PyYAML is not installed to parse YAML. "
            "Please provide a JSON specification or install pyyaml."
        )
    except Exception as e:
        raise ValueError(f"Failed to parse OpenAPI specification: {e}") from e


def _resolve_ref(ref: str, root_spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve an internal #/components/... or #/definitions/... reference."""
    if not ref.startswith("#/"):
        return {}

    parts = ref.lstrip("#/").split("/")
    curr = root_spec
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return {}
    return curr if isinstance(curr, dict) else {}


def _clean_identifier(text: str) -> str:
    """Turn text into a clean Python function identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", text).strip("_")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.lower() or "api_call"


def _derive_skills(
    path: str, method: str, tags: list[str], operation_id: str
) -> list[str]:
    """Derive abstract skill tags for Meta-Planner from OpenAPI metadata."""
    skills = set()

    # 1. Tags
    for tag in tags:
        clean = _clean_identifier(tag)
        if clean:
            skills.add(clean)

    # 2. Path segments
    segments = [s.strip("{}") for s in path.split("/") if s and not s.startswith("{")]
    for seg in segments:
        clean = _clean_identifier(seg)
        if len(clean) > 2 and clean not in ("api", "v1", "v2", "v3"):
            skills.add(clean)

    # 3. Operation ID tokens
    if operation_id:
        clean_op = _clean_identifier(operation_id)
        skills.add(clean_op)
        for token in clean_op.split("_"):
            if len(token) > 2 and token not in ("the", "and", "for", "with", "from"):
                skills.add(token)

    # 4. Method skill
    skills.add(f"http_{method.lower()}")

    return sorted(skills)


def _determine_risk_level(method: str, path: str, description: str) -> RiskLevel:
    """Determine risk level from HTTP method and path semantics."""
    method_upper = method.upper()
    if method_upper in ("DELETE",):
        return RiskLevel.CRITICAL
    if method_upper in ("POST", "PUT", "PATCH"):
        # Check if it's destructive or critical
        if any(k in path.lower() or k in description.lower() for k in ("destroy", "drop", "terminate", "kill")):
            return RiskLevel.CRITICAL
        return RiskLevel.HIGH
    return RiskLevel.LOW


def _extract_parameters(
    endpoint_params: list[dict[str, Any]],
    request_body: dict[str, Any] | None,
    root_spec: dict[str, Any],
) -> dict[str, Any]:
    """Flatten path, query, header parameters, and JSON requestBody into a unified parameters dict."""
    params: dict[str, Any] = {}

    # 1. Path, Query, Header parameters
    for param in endpoint_params:
        if "$ref" in param:
            param = _resolve_ref(param["$ref"], root_spec)

        p_name = param.get("name")
        if not p_name:
            continue

        p_in = param.get("in", "query")
        p_desc = param.get("description", f"Parameter passed via {p_in}")
        p_req = param.get("required", p_in == "path")
        schema = param.get("schema", {})
        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], root_spec)
        p_type = schema.get("type", "string")

        params[p_name] = {
            "type": p_type,
            "description": f"[{p_in.upper()}] {p_desc}",
            "required": p_req,
            "in": p_in,
        }

    # 2. Request body (OpenAPI 3.0)
    if request_body:
        if "$ref" in request_body:
            request_body = _resolve_ref(request_body["$ref"], root_spec)

        content = request_body.get("content", {})
        json_schema = content.get("application/json", {}).get("schema", {})
        if "$ref" in json_schema:
            json_schema = _resolve_ref(json_schema["$ref"], root_spec)

        if json_schema.get("type") == "object":
            body_props = json_schema.get("properties", {})
            body_req = set(json_schema.get("required", []))
            for prop_name, prop_schema in body_props.items():
                if "$ref" in prop_schema:
                    prop_schema = _resolve_ref(prop_schema["$ref"], root_spec)
                params[prop_name] = {
                    "type": prop_schema.get("type", "string"),
                    "description": f"[BODY] {prop_schema.get('description', '')}",
                    "required": prop_name in body_req,
                    "in": "body",
                }
        elif json_schema:
            params["request_body"] = {
                "type": json_schema.get("type", "object"),
                "description": "[BODY] JSON payload",
                "required": request_body.get("required", False),
                "in": "body",
            }

    return params


def parse_openapi_spec(
    raw_spec: str | dict[str, Any],
    base_url: str | None = None,
    auth_header_name: str | None = None,
    auth_header_value: str | None = None,
    api_prefix: str = "api",
) -> list[ToolSpec]:
    """Parse an OpenAPI specification into a list of registered UAOS ToolSpec objects.

    Args:
        raw_spec: JSON or YAML string or loaded dict.
        base_url: Base URL to send requests to (e.g. 'https://api.github.com').
                  If None, inferred from spec servers.
        auth_header_name: Optional header name for authentication (e.g. 'Authorization').
        auth_header_value: Optional header value (e.g. 'Bearer ghp_xxx').
        api_prefix: Prefix used for tool_id and tool names.

    Returns:
        List of ToolSpec instances.
    """
    spec = _load_spec_data(raw_spec)

    # Determine base URL
    if not base_url:
        servers = spec.get("servers", [])
        if servers and isinstance(servers[0], dict):
            base_url = servers[0].get("url", "")
        elif "host" in spec:
            # Swagger 2.0
            scheme = spec.get("schemes", ["https"])[0]
            base_path = spec.get("basePath", "").rstrip("/")
            base_url = f"{scheme}://{spec['host']}{base_path}"
        else:
            base_url = "http://localhost"

    base_url = base_url.rstrip("/")
    paths = spec.get("paths", {})
    tools: list[ToolSpec] = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        common_params = path_item.get("parameters", [])

        for method in ("get", "post", "put", "delete", "patch"):
            if method not in path_item:
                continue

            op = path_item[method]
            if not isinstance(op, dict):
                continue

            op_id = op.get("operationId")
            if not op_id:
                # Synthesize operationId from method + path
                clean_p = _clean_identifier(path)
                op_id = f"{method}_{clean_p}"

            tool_name = _clean_identifier(f"{api_prefix}_{op_id}")
            tool_id = f"openapi_{api_prefix}_{op_id}"
            description = op.get("summary") or op.get("description") or f"{method.upper()} {path}"
            tags = op.get("tags", [])

            # Combine common path parameters and operation parameters
            op_params = list(common_params) + op.get("parameters", [])
            request_body = op.get("requestBody")

            parameters = _extract_parameters(op_params, request_body, spec)
            skills = _derive_skills(path, method, tags, op_id)
            risk = _determine_risk_level(method, path, description)

            # Create the dynamic async function
            func = create_openapi_tool_callable(
                base_url=base_url,
                path=path,
                method=method.upper(),
                parameters_meta=parameters,
                auth_header_name=auth_header_name,
                auth_header_value=auth_header_value,
                tool_name=tool_name,
                description=description,
            )

            tools.append(
                ToolSpec(
                    tool_id=tool_id,
                    name=tool_name,
                    description=f"{description} ({method.upper()} {path})",
                    skills_provided=skills,
                    parameters=parameters,
                    function=func,
                    risk_level=risk,
                    source_type="openapi",
                    server_or_host=base_url,
                )
            )

    logger.info("Parsed %d tools from OpenAPI spec for base URL '%s'", len(tools), base_url)
    return tools
