"""
UAOS Multi-Tier Tool Call Parser & Validator

Implements a robust 4-tier extraction pipeline:
  Tier 1: Native OpenAI `tool_calls` structures in LLMResponse.
  Tier 2: Hermes XML `<tool_call>{...}</tool_call>` standard tags (with tolerance
          for multiple calls, unclosed tags, and unescaped Windows paths).
  Tier 3: Markdown / JSON code block heuristics (legacy JSON parser).
  Tier 4: ReAct style `Action: <tool>\nAction Input: <json/dict>`.

Also provides:
  - Argument type coercion (string -> int/bool/float/dict/list).
  - Parameter validation against ToolSpec schema.
  - "Did you mean?" suggestions using difflib for hallucinated tool names.
"""

from __future__ import annotations

import ast
import difflib
import json
import logging
import re
from typing import Any

from src.core.messages import ParsedToolCall
from src.core.path_utils import sanitize_json_string_backslashes
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


def parse_tool_calls(
    response_text: str,
    native_tool_calls: list[dict[str, Any]] | None = None,
) -> list[ParsedToolCall]:
    """Extract all tool calls from model output in priority order.

    Returns:
        List of ParsedToolCall objects. Empty if no tool calls found.
    """
    # ── Tier 1: Native OpenAI Tool Calls ────────────────────────
    if native_tool_calls:
        parsed = []
        for tc in native_tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "").strip()
            raw_args = func.get("arguments", "{}")
            call_id = tc.get("id", "")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(sanitize_json_string_backslashes(raw_args))
                except Exception:
                    try:
                        args = ast.literal_eval(raw_args)
                    except Exception:
                        args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}

            if name:
                parsed.append(ParsedToolCall(
                    call_id=call_id or f"native-{len(parsed)}",
                    name=name,
                    args=args if isinstance(args, dict) else {},
                    source="native",
                ))
        if parsed:
            return parsed

    if not response_text or not response_text.strip():
        return []

    # ── Tier 2: Hermes XML <tool_call> Tags ─────────────────────
    hermes_calls = _parse_hermes_tags(response_text)
    if hermes_calls:
        return hermes_calls

    # ── Tier 3: Markdown / Raw JSON Blocks ──────────────────────
    json_call = _parse_json_blocks(response_text)
    if json_call:
        return [json_call]

    # ── Tier 4: ReAct Action Patterns ───────────────────────────
    react_call = _parse_react_action(response_text)
    if react_call:
        return [react_call]

    return []


def _parse_hermes_tags(text: str) -> list[ParsedToolCall]:
    """Parse Hermes standard <tool_call>...</tool_call> tags.

    Tolerant of:
      - Multiple parallel tool calls
      - Unclosed <tool_call> tags from truncated LLM generations
      - Bad escape characters (e.g. unescaped Windows backslashes)
      - Key variants: 'name'/'arguments', 'tool'/'args', 'function'
    """
    if "<tool_call>" not in text:
        return []

    calls: list[ParsedToolCall] = []
    # Match both closed and unclosed tags
    pattern = r"<tool_call>\s*(.*?)(?:</tool_call>|$)"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

    for i, match in enumerate(matches):
        raw_body = match.strip()
        if not raw_body:
            continue

        # Strip markdown code fences if wrapped inside tags
        if raw_body.startswith("```"):
            lines = raw_body.splitlines()
            if len(lines) >= 2 and lines[-1].startswith("```"):
                raw_body = "\n".join(lines[1:-1]).strip()
            elif len(lines) >= 1:
                raw_body = "\n".join(lines[1:]).strip()

        sanitized = sanitize_json_string_backslashes(raw_body)
        parsed_dict = None

        try:
            parsed_dict = json.loads(sanitized)
        except json.JSONDecodeError:
            try:
                parsed_dict = ast.literal_eval(raw_body)
            except Exception:
                # Try finding outermost JSON object
                start = raw_body.find("{")
                end = raw_body.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        parsed_dict = json.loads(sanitize_json_string_backslashes(raw_body[start : end + 1]))
                    except Exception:
                        pass

        if not isinstance(parsed_dict, dict):
            continue

        # Extract tool name and arguments across dialect variants
        name = (
            parsed_dict.get("name")
            or parsed_dict.get("tool")
            or parsed_dict.get("function")
            or ""
        )
        if isinstance(name, dict) and "name" in name:
            name = name["name"]
        name = str(name).strip()

        args = (
            parsed_dict.get("arguments")
            or parsed_dict.get("args")
            or parsed_dict.get("parameters")
            or {}
        )
        if isinstance(args, str):
            try:
                args = json.loads(sanitize_json_string_backslashes(args))
            except Exception:
                args = {}

        if name:
            calls.append(ParsedToolCall(
                call_id=f"tag-{i}",
                name=name,
                args=args if isinstance(args, dict) else {},
                source="tags",
            ))

    return calls


def _parse_json_blocks(text: str) -> ParsedToolCall | None:
    """Parse legacy JSON / Markdown blocks (tool/args or name/arguments)."""
    blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidates = blocks if blocks else [text]

    for block in candidates:
        block_clean = block.strip()
        if not (block_clean.startswith("{") or "{" in block_clean):
            continue

        # Extract innermost or outermost {...}
        start = block_clean.find("{")
        end = block_clean.rfind("}")
        if start == -1 or end == -1 or end <= start:
            continue

        candidate_json = block_clean[start : end + 1]
        sanitized = sanitize_json_string_backslashes(candidate_json)

        parsed = None
        try:
            parsed = json.loads(sanitized)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(candidate_json)
            except Exception:
                continue

        if not isinstance(parsed, dict):
            continue

        name = parsed.get("tool") or parsed.get("name") or parsed.get("function")
        if isinstance(name, dict) and "name" in name:
            name = name["name"]
        if not name or not isinstance(name, str):
            continue

        args = parsed.get("args") or parsed.get("arguments") or parsed.get("parameters") or {}
        if isinstance(args, str):
            try:
                args = json.loads(sanitize_json_string_backslashes(args))
            except Exception:
                args = {}

        return ParsedToolCall(
            call_id="json-0",
            name=name.strip(),
            args=args if isinstance(args, dict) else {},
            source="json",
        )

    return None


def _parse_react_action(text: str) -> ParsedToolCall | None:
    """Parse ReAct action format: Action: <name>\nAction Input: <args>."""
    action_match = re.search(r"Action:\s*([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
    if not action_match:
        return None

    name = action_match.group(1).strip()
    args: dict[str, Any] = {}

    input_match = re.search(
        r"Action\s*Input:\s*([\s\S]*?)(?:\n\s*(?:Observation|Thought|Action|$))",
        text,
        re.IGNORECASE,
    )
    if input_match:
        raw_input = input_match.group(1).strip()
        if raw_input.startswith("```"):
            raw_input = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_input).strip()
        sanitized = sanitize_json_string_backslashes(raw_input)
        try:
            parsed_args = json.loads(sanitized)
            if isinstance(parsed_args, dict):
                args = parsed_args
        except Exception:
            try:
                parsed_args = ast.literal_eval(raw_input)
                if isinstance(parsed_args, dict):
                    args = parsed_args
            except Exception:
                # If a single bare string argument was provided, treat as 'command' or 'arg'
                if raw_input and not raw_input.startswith("{"):
                    args = {"command": raw_input}

    return ParsedToolCall(
        call_id="react-0",
        name=name,
        args=args,
        source="react",
    )


# ── Argument Coercion & Validation ──────────────────────────────


def coerce_and_validate_args(
    tool_spec: ToolSpec,
    raw_args: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Validate and coerce raw arguments against ToolSpec parameter definitions.

    Returns:
        (coerced_args, error_message). If error_message is None, validation succeeded.
    """
    coerced = dict(raw_args)
    spec_params = tool_spec.parameters

    # Handle standard schema format vs property dict
    properties: dict[str, Any] = {}
    required_names: list[str] = []

    if "properties" in spec_params and isinstance(spec_params["properties"], dict):
        properties = spec_params["properties"]
        required_names = spec_params.get("required", [])
    else:
        properties = spec_params
        for pname, pinfo in spec_params.items():
            if isinstance(pinfo, dict) and pinfo.get("required", False):
                required_names.append(pname)

    # 1. Check required parameters
    missing = [req for req in required_names if req not in coerced or coerced[req] is None]
    if missing:
        return coerced, (
            f"Missing required parameter(s) for tool '{tool_spec.name}': {missing}. "
            f"Expected schema: {list(properties.keys())}."
        )

    # 2. Type coercion
    for param_name, val in list(coerced.items()):
        if param_name not in properties or not isinstance(properties[param_name], dict):
            continue
        expected_type = str(properties[param_name].get("type", "")).lower()

        # String to int / number
        if expected_type in ("integer", "int", "number") and isinstance(val, str):
            val_clean = val.strip().replace(",", "")
            try:
                if "." in val_clean:
                    coerced[param_name] = float(val_clean)
                else:
                    coerced[param_name] = int(val_clean)
            except ValueError:
                pass

        # String to boolean
        elif expected_type in ("boolean", "bool") and isinstance(val, str):
            if val.strip().lower() in ("true", "1", "yes"):
                coerced[param_name] = True
            elif val.strip().lower() in ("false", "0", "no"):
                coerced[param_name] = False

        # String to array / list
        elif expected_type in ("array", "list") and isinstance(val, str):
            try:
                parsed_list = json.loads(val)
                if isinstance(parsed_list, list):
                    coerced[param_name] = parsed_list
            except Exception:
                pass

        # String to object / dict
        elif expected_type in ("object", "dict") and isinstance(val, str):
            try:
                parsed_dict = json.loads(val)
                if isinstance(parsed_dict, dict):
                    coerced[param_name] = parsed_dict
            except Exception:
                pass

    return coerced, None


def suggest_closest_tool(attempted_name: str, available_tools: list[str]) -> str | None:
    """Find the closest matching registered tool name using difflib."""
    if not available_tools:
        return None
    matches = difflib.get_close_matches(attempted_name, available_tools, n=1, cutoff=0.4)
    return matches[0] if matches else None


# ── Format Tools into OpenAI / Hermes Specifications ─────────────


def format_tools_to_openai_schema(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert ToolSpec instances to official OpenAI tools schema."""
    schemas = []
    for t in tools:
        properties = {}
        required = []

        if "properties" in t.parameters and isinstance(t.parameters["properties"], dict):
            properties = t.parameters["properties"]
            required = t.parameters.get("required", [])
        else:
            for pname, pinfo in t.parameters.items():
                if isinstance(pinfo, dict):
                    properties[pname] = {
                        "type": pinfo.get("type", "string"),
                        "description": pinfo.get("description", ""),
                    }
                    if pinfo.get("required", False):
                        required.append(pname)
                else:
                    properties[pname] = {"type": "string"}

        schemas.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return schemas


def format_tools_to_hermes_xml(tools: list[ToolSpec]) -> str:
    """Format tools as Hermes official <tools>[...]</tools> system prompt block."""
    schemas = format_tools_to_openai_schema(tools)
    tools_json = json.dumps(schemas, indent=2)
    return (
        f"<tools>\n{tools_json}\n</tools>\n\n"
        "To invoke a tool, respond with one or more <tool_call> blocks:\n"
        '<tool_call>\n{"name": "tool_name", "arguments": {"arg1": "value"}}\n</tool_call>'
    )
