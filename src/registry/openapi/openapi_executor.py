"""Dynamic HTTP Executor for OpenAPI Tools.

Executes HTTP requests for tools dynamically generated from OpenAPI/Swagger
specifications, injecting path parameters, query params, headers, auth tokens,
and JSON request bodies.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import httpx

from src.core.exceptions import ToolExecutionError

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 4000


async def execute_openapi_request(
    base_url: str,
    path: str,
    method: str,
    parameters_meta: dict[str, Any],
    auth_header_name: str | None,
    auth_header_value: str | None,
    tool_name: str,
    call_args: dict[str, Any],
) -> str:
    """Execute dynamic HTTP request for an OpenAPI tool."""
    resolved_path = path
    query_params: dict[str, Any] = {}
    headers: dict[str, str] = {
        "User-Agent": "UAOS-Agent/0.1.0",
        "Accept": "application/json, text/plain, */*",
    }
    body_payload: dict[str, Any] = {}

    if auth_header_name and auth_header_value:
        headers[auth_header_name] = auth_header_value

    # Distribute arguments according to their metadata
    for arg_name, arg_val in call_args.items():
        if arg_val is None:
            continue

        meta = parameters_meta.get(arg_name, {})
        param_in = meta.get("in", "query")

        if param_in == "path":
            resolved_path = resolved_path.replace(f"{{{arg_name}}}", str(arg_val))
        elif param_in == "query":
            query_params[arg_name] = arg_val
        elif param_in == "header":
            headers[arg_name] = str(arg_val)
        elif param_in == "body":
            if arg_name == "request_body" and isinstance(arg_val, dict):
                body_payload.update(arg_val)
            else:
                body_payload[arg_name] = arg_val
        else:
            # Default to query parameter
            query_params[arg_name] = arg_val

    # Ensure any remaining {path_param} was filled
    if "{" in resolved_path and "}" in resolved_path:
        missing = [p.strip("{}") for p in resolved_path.split("/") if "{" in p]
        raise ToolExecutionError(
            tool_name,
            f"Missing required path parameter(s): {', '.join(missing)} in path '{resolved_path}'",
        )

    url = f"{base_url.rstrip('/')}/{resolved_path.lstrip('/')}"
    logger.info("OpenAPI tool '%s' executing %s %s", tool_name, method, url)

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            req_kwargs: dict[str, Any] = {
                "headers": headers,
                "params": query_params or None,
            }
            if body_payload and method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
                req_kwargs["json"] = body_payload

            response = await client.request(method.upper(), url, **req_kwargs)

            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    res_body = json.dumps(response.json(), indent=2)
                except Exception:
                    res_body = response.text
            else:
                res_body = response.text

            # Cap output to avoid context window explosion
            if len(res_body) > MAX_OUTPUT_CHARS:
                res_body = res_body[:MAX_OUTPUT_CHARS] + f"\n... [Truncated: output was {len(res_body)} characters]"

            status_str = f"HTTP {response.status_code} {response.reason_phrase}"
            if response.status_code >= 400:
                return f"[ERROR {status_str}]\n{res_body}"

            return f"[{status_str}]\n{res_body}"

        except httpx.TimeoutException as e:
            raise ToolExecutionError(tool_name, f"Request timed out connecting to {url}: {e}") from e
        except Exception as e:
            raise ToolExecutionError(tool_name, f"HTTP request to {url} failed: {e}") from e


def create_openapi_tool_callable(
    base_url: str,
    path: str,
    method: str,
    parameters_meta: dict[str, Any],
    auth_header_name: str | None,
    auth_header_value: str | None,
    tool_name: str,
    description: str,
) -> Callable[..., Coroutine]:
    """Factory creating an async callable for a specific OpenAPI operation."""

    async def openapi_tool_wrapper(**kwargs: Any) -> str:
        return await execute_openapi_request(
            base_url=base_url,
            path=path,
            method=method,
            parameters_meta=parameters_meta,
            auth_header_name=auth_header_name,
            auth_header_value=auth_header_value,
            tool_name=tool_name,
            call_args=kwargs,
        )

    openapi_tool_wrapper.__name__ = tool_name
    openapi_tool_wrapper.__doc__ = description
    return openapi_tool_wrapper
