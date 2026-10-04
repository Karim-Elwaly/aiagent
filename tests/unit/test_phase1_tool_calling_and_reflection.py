"""
Unit tests for Phase 1:
- Native OpenAI tool calling & Hermes XML tags tool-call parser
- Channel separation (reasoning vs content extraction)
- Argument type coercion & schema validation
- "Did you mean?" tool suggestions
- In-loop reflection, error classification, and RepeatGuard
- Supervisor feedback exclusion in path extraction
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from src.core.llm_client import LLMResponse, extract_thinking_and_content
from src.core.models import Task, RiskLevel
from src.core.reflection import (
    ErrorCategory,
    RepeatGuard,
    classify_tool_error,
    generate_reflection_prompt,
)
from src.core.tool_call_parser import (
    coerce_and_validate_args,
    format_tools_to_hermes_xml,
    format_tools_to_openai_schema,
    parse_tool_calls,
    suggest_closest_tool,
)
from src.registry.tool_registry import ToolSpec


# ── 1. Channel Separation (<think> Tags) ─────────────────────────


def test_extract_thinking_and_content():
    """Verify that <think> reasoning blocks are stripped from content and returned as reasoning."""
    # Standard closed think tags
    raw = "<think>Let me plan this step carefully.\nFirst check files.</think>Here is the final answer."
    content, reasoning = extract_thinking_and_content(raw)
    assert content == "Here is the final answer."
    assert "Let me plan this step carefully." in reasoning
    assert "<think>" not in content

    # Unclosed think tag (e.g. truncated generation)
    raw_unclosed = "<think>Thinking about the problem... still going"
    content_unclosed, reasoning_unclosed = extract_thinking_and_content(raw_unclosed)
    assert content_unclosed == ""
    assert "Thinking about the problem" in reasoning_unclosed

    # No think tags
    raw_plain = "Direct answer without thinking tags."
    content_plain, reasoning_plain = extract_thinking_and_content(raw_plain)
    assert content_plain == "Direct answer without thinking tags."
    assert reasoning_plain == ""


# ── 2. Multi-Tier Tool Call Parsing ──────────────────────────────


def test_parse_tool_calls_native():
    """Verify parsing of OpenAI native tool_calls list."""
    native_calls = [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "read_file",
                "arguments": '{"file_path": "README.md"}',
            },
        }
    ]
    parsed = parse_tool_calls(response_text="", native_tool_calls=native_calls)
    assert len(parsed) == 1
    assert parsed[0].name == "read_file"
    assert parsed[0].args == {"file_path": "README.md"}
    assert parsed[0].source == "native"
    assert parsed[0].call_id == "call_123"


def test_parse_tool_calls_hermes_xml_single_and_multiple():
    """Verify Hermes XML standard <tool_call> tags with single and parallel calls."""
    # Single call
    text_single = """
    I will read the configuration.
    <tool_call>
    {"name": "read_file", "arguments": {"file_path": "src/core/config.py"}}
    </tool_call>
    """
    parsed = parse_tool_calls(text_single)
    assert len(parsed) == 1
    assert parsed[0].name == "read_file"
    assert parsed[0].args == {"file_path": "src/core/config.py"}
    assert parsed[0].source == "tags"

    # Parallel multiple calls
    text_multi = """
    <tool_call>
    {"name": "read_file", "arguments": {"file_path": "a.txt"}}
    </tool_call>
    <tool_call>
    {"name": "execute_command", "arguments": {"command": "hostname"}}
    </tool_call>
    """
    parsed_multi = parse_tool_calls(text_multi)
    assert len(parsed_multi) == 2
    assert parsed_multi[0].name == "read_file"
    assert parsed_multi[1].name == "execute_command"
    assert parsed_multi[1].args == {"command": "hostname"}


def test_parse_tool_calls_hermes_xml_unclosed_and_windows_paths():
    """Verify tolerance for unclosed tags and unescaped Windows backslashes."""
    # Unclosed tag from token truncation
    text_unclosed = '<tool_call>\n{"name": "read_file", "arguments": {"file_path": "D:\\projects\\aiagent\\test.py"}}'
    parsed = parse_tool_calls(text_unclosed)
    assert len(parsed) == 1
    assert parsed[0].name == "read_file"
    assert "test.py" in parsed[0].args["file_path"]

    # Raw single backslashes in path
    text_backslashes = '<tool_call>\n{"name": "read_file", "arguments": {"file_path": "D:\\projects\\test.txt"}}\n</tool_call>'
    parsed_bs = parse_tool_calls(text_backslashes)
    assert len(parsed_bs) == 1
    assert parsed_bs[0].name == "read_file"


def test_parse_tool_calls_legacy_json_and_react():
    """Verify legacy JSON code block and ReAct Action fallback parsing."""
    # Markdown JSON
    text_json = """
    ```json
    {"tool": "execute_command", "args": {"command": "whoami"}}
    ```
    """
    parsed_json = parse_tool_calls(text_json)
    assert len(parsed_json) == 1
    assert parsed_json[0].name == "execute_command"
    assert parsed_json[0].args == {"command": "whoami"}
    assert parsed_json[0].source == "json"

    # ReAct pattern
    text_react = """
    Thought: Need to list directory.
    Action: list_directory
    Action Input: {"path": "."}
    Observation:
    """
    parsed_react = parse_tool_calls(text_react)
    assert len(parsed_react) == 1
    assert parsed_react[0].name == "list_directory"
    assert parsed_react[0].args == {"path": "."}
    assert parsed_react[0].source == "react"


# ── 3. Argument Coercion & Schema Validation ──────────────────────


def test_argument_coercion_and_validation():
    """Verify parameter type coercion and required parameter checks."""
    spec = ToolSpec(
        tool_id="math_test",
        name="calculate",
        description="Math tool",
        skills_provided=["math"],
        parameters={
            "count": {"type": "integer", "required": True},
            "ratio": {"type": "number", "required": False},
            "verbose": {"type": "boolean", "required": False},
            "items": {"type": "array", "required": False},
        },
        function=lambda **kw: "ok",
    )

    # Coercion from strings
    raw_args = {
        "count": "42",
        "ratio": "3.14",
        "verbose": "true",
        "items": '["x", "y"]',
    }
    coerced, err = coerce_and_validate_args(spec, raw_args)
    assert err is None
    assert coerced["count"] == 42
    assert coerced["ratio"] == 3.14
    assert coerced["verbose"] is True
    assert coerced["items"] == ["x", "y"]

    # Missing required parameter
    missing_args = {"ratio": 1.5}
    _, missing_err = coerce_and_validate_args(spec, missing_args)
    assert missing_err is not None
    assert "count" in missing_err


def test_tool_suggestion():
    """Verify 'Did you mean?' suggestions for misremembered tool names."""
    available = ["read_file", "write_file", "execute_command", "execute_python"]
    assert suggest_closest_tool("read_files", available) == "read_file"
    assert suggest_closest_tool("exec_command", available) == "execute_command"
    assert suggest_closest_tool("totally_unknown_gibberish", available) is None


# ── 4. Error Classification & In-Loop Reflection ──────────────────


def test_error_classification():
    """Verify deterministic rule-based error classification."""
    c_fnf = classify_tool_error("read_file", "Error: No such file or directory: 'secret.txt'", is_error=True)
    assert c_fnf.category == ErrorCategory.FILE_NOT_FOUND

    c_perm = classify_tool_error("write_file", "Error: Access is denied", is_error=True)
    assert c_perm.category == ErrorCategory.PERMISSION_DENIED

    c_syntax = classify_tool_error("execute_python", "SyntaxError: invalid syntax", is_error=True)
    assert c_syntax.category == ErrorCategory.SYNTAX_ERROR

    c_cmd = classify_tool_error("execute_command", "Command returned non-zero exit status 1", is_error=True)
    assert c_cmd.category == ErrorCategory.COMMAND_FAILED

    c_empty = classify_tool_error("web_extract", "", is_error=True)
    assert c_empty.category == ErrorCategory.EMPTY_OUTPUT

    # Non-error output returns None
    assert classify_tool_error("read_file", "Valid file content", is_error=False) is None


def test_repeat_guard():
    """Verify that RepeatGuard detects and blocks identical failing calls."""
    guard = RepeatGuard(max_identical_allowed=1)

    blocked1, warn1 = guard.record_and_check("read_file", {"file_path": "missing.txt"})
    assert not blocked1
    assert warn1 is None

    # Immediate identical call
    blocked2, warn2 = guard.record_and_check("read_file", {"file_path": "missing.txt"})
    assert blocked2
    assert "REPEAT GUARD TRIGGERED" in warn2
    assert "missing.txt" not in warn2 or "read_file" in warn2

    # Different arguments allowed
    blocked3, warn3 = guard.record_and_check("read_file", {"file_path": "other.txt"})
    assert not blocked3


def test_generate_reflection_prompt():
    """Verify structured reflection prompt formatting."""
    c = classify_tool_error("read_file", "No such file", is_error=True)
    prompt = generate_reflection_prompt(c, "read_file", "No such file", repeat_warning="Do not repeat.")
    assert "Diagnostic Reflection Required" in prompt
    assert "FILE_NOT_FOUND" in prompt
    assert "Do not repeat." in prompt


# ── 5. Supervisor Feedback Clean Path Extraction ──────────────────


def test_supervisor_feedback_path_isolation():
    """Verify supervisor evaluation prose does not poison path extraction."""
    from src.workers.universal_worker import UniversalWorkerAgent

    mock_llm = AsyncMock()
    worker = UniversalWorkerAgent(llm=mock_llm)

    task = Task(
        id="t1",
        name="Inspect Logs",
        description=(
            "Find authentication failures.\n\n"
            "### Supervisor Feedback:\n"
            "On Linux/macOS targets this would be in /var/log/auth.log, but check D:/projects/aiagent"
        ),
        required_skills=[],
    )

    # When extracting path, supervisor prose containing Linux/macOS should be stripped
    extracted = worker._extract_task_path_or_default(task, user_query="")
    assert "Linux/macOS" not in extracted
    assert "var" not in extracted
