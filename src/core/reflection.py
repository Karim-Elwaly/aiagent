"""
UAOS In-Loop Reflection & Error Classifier (Gap 4)

Provides:
1. Deterministic error classification without extra LLM overhead.
2. RepeatGuard: prevents infinite loops of identical failing tool calls.
3. Structured reflection prompts instructing the model to diagnose errors
   and pivot rather than blindly retrying identical arguments.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    SYNTAX_ERROR = "syntax_error"
    COMMAND_FAILED = "command_failed"
    EMPTY_OUTPUT = "empty_output"
    SCHEMA_ERROR = "schema_error"
    TIMEOUT = "timeout"
    GENERAL_ERROR = "general_error"


@dataclass
class ToolErrorClassification:
    category: ErrorCategory
    summary: str
    suggested_action: str


def classify_tool_error(
    tool_name: str,
    output: str,
    is_error: bool = False,
) -> ToolErrorClassification | None:
    """Classify tool errors deterministically using keyword and pattern rules.

    Returns None if the output represents successful execution.
    """
    if not is_error and not output.startswith("Error:"):
        # Check if output contains explicit fatal crash markers
        if "Traceback (most recent call last):" not in output and "command failed" not in output.lower():
            return None

    lower_out = output.lower()

    # 1. File Not Found
    if any(m in lower_out for m in ("file not found", "no such file", "cannot find the file", "path does not exist")):
        return ToolErrorClassification(
            category=ErrorCategory.FILE_NOT_FOUND,
            summary=f"Target file or path does not exist for tool '{tool_name}'.",
            suggested_action="Verify the file path using 'list_directory' or check parent directories before retrying.",
        )

    # 2. Permission Denied
    if any(m in lower_out for m in ("permission denied", "access is denied", "operation not permitted")):
        return ToolErrorClassification(
            category=ErrorCategory.PERMISSION_DENIED,
            summary=f"Access or permission was denied executing tool '{tool_name}'.",
            suggested_action="Target resource requires elevated rights or is locked. Attempt a non-privileged query or report limitation.",
        )

    # 3. Syntax / Parsing / Arguments
    if any(m in lower_out for m in ("syntaxerror", "indentationerror", "nameerror", "jsondecodeerror", "invalid arguments")):
        return ToolErrorClassification(
            category=ErrorCategory.SYNTAX_ERROR,
            summary=f"Code or parameter syntax error in tool '{tool_name}'.",
            suggested_action="Review script syntax, escapes, and variable definitions before re-executing.",
        )

    # 4. Command Failed (non-zero exit)
    if any(m in lower_out for m in ("returned non-zero exit status", "exit code", "is not recognized as an internal or external command")):
        return ToolErrorClassification(
            category=ErrorCategory.COMMAND_FAILED,
            summary=f"Command execution failed in tool '{tool_name}'.",
            suggested_action="Check command availability for the current OS (e.g. Windows PowerShell vs Linux bash) and parameter syntax.",
        )

    # 5. Schema / Missing Parameter
    if "missing required parameter" in lower_out:
        return ToolErrorClassification(
            category=ErrorCategory.SCHEMA_ERROR,
            summary=f"Missing required parameter for tool '{tool_name}'.",
            suggested_action="Inspect the required tool schema parameters and supply all mandatory arguments.",
        )

    # 6. Empty Output
    if not output.strip() or output.strip() == "None":
        return ToolErrorClassification(
            category=ErrorCategory.EMPTY_OUTPUT,
            summary=f"Tool '{tool_name}' returned empty or null output.",
            suggested_action="Broaden search criteria, inspect directory contents, or check command flags.",
        )

    # 7. General Error Fallback
    return ToolErrorClassification(
        category=ErrorCategory.GENERAL_ERROR,
        summary=f"Tool '{tool_name}' failed during execution.",
        suggested_action="Diagnose the specific error message above and adjust your approach.",
    )


class RepeatGuard:
    """Detects and prevents loops where an agent repeats identical failing tool calls."""

    def __init__(self, max_identical_allowed: int = 1):
        self.max_identical_allowed = max_identical_allowed
        self._call_counts: dict[str, int] = {}

    def _hash_call(self, tool_name: str, args: dict[str, Any]) -> str:
        """Create a deterministic hash from tool name and normalized arguments."""
        try:
            serialized_args = json.dumps(args, sort_keys=True, default=str)
        except Exception:
            serialized_args = str(sorted(args.items()))
        return f"{tool_name}:{hashlib.sha256(serialized_args.encode('utf-8')).hexdigest()[:16]}"

    def record_and_check(self, tool_name: str, args: dict[str, Any]) -> tuple[bool, str | None]:
        """Record an attempted tool call and check if it violates the repeat guard.

        Returns:
            (is_blocked, warning_message). If is_blocked is True, repeating the call is forbidden.
        """
        key = self._hash_call(tool_name, args)
        count = self._call_counts.get(key, 0) + 1
        self._call_counts[key] = count

        if count > self.max_identical_allowed:
            warning = (
                f"REPEAT GUARD TRIGGERED: You have called tool '{tool_name}' with the EXACT same arguments "
                f"{count} times. Repeating identical failing calls is strictly prohibited. "
                f"You MUST modify your arguments, execute a different tool, or provide your "
                f"FINAL_ANSWER explaining why the task cannot proceed."
            )
            logger.warning("RepeatGuard blocked tool '%s' (hash=%s, attempts=%d)", tool_name, key, count)
            return True, warning

        return False, None


def generate_reflection_prompt(
    classification: ToolErrorClassification,
    tool_name: str,
    output: str,
    repeat_warning: str | None = None,
) -> str:
    """Generate a structured, in-loop reflection guide for the LLM."""
    lines = [
        f"### Diagnostic Reflection Required [{classification.category.value.upper()}]",
        f"The execution of `{tool_name}` encountered an error: {classification.summary}",
        f"**Suggested Strategy:** {classification.suggested_action}",
    ]
    if repeat_warning:
        lines.append(f"\n> **CRITICAL WARNING:** {repeat_warning}")
    lines.append(
        "\nAnalyze this diagnostic feedback. Formulate a new plan, adjust your parameters, "
        "or call an alternative diagnostic tool. Do not guess."
    )
    return "\n".join(lines)
