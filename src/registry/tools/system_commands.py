"""
System Command Execution Tools

Allows running safe terminal inspection and system commands (PowerShell on Windows, bash on Linux).
Provides system-level querying capabilities (e.g. fsutil, Get-ChildItem, dir, ipconfig, processes).
"""

from __future__ import annotations

import logging
import platform
import subprocess
from typing import Any

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

MAX_COMMAND_SECONDS = 30
MAX_OUTPUT_CHARS = 4000


async def execute_command(
    command: str | None = None,
    cmd: str | None = None,
    **kwargs: Any,
) -> str:
    """Execute a system terminal command (PowerShell on Windows, Bash on Unix) and return stdout/stderr."""
    raw_cmd = command or cmd or kwargs.get("input") or kwargs.get("script") or ""
    clean_cmd = str(raw_cmd).strip().strip('"').strip("'")
    if not clean_cmd:
        return "Error: Empty command provided."

    is_windows = platform.system() == "Windows"
    if is_windows:
        cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", clean_cmd]
    else:
        cmd_args = ["/bin/bash", "-c", clean_cmd]

    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=MAX_COMMAND_SECONDS,
            check=False,
        )
        out_parts = []
        if result.stdout:
            out_parts.append(result.stdout.strip())
        if result.stderr:
            out_parts.append(f"STDERR:\n{result.stderr.strip()}")
        if result.returncode != 0:
            out_parts.append(f"(Command exited with code {result.returncode})")

        output = "\n".join(out_parts) if out_parts else "(No output returned)"
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n[...output truncated]"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {MAX_COMMAND_SECONDS} seconds."
    except Exception as e:
        logger.error("Command execution failed for '%s': %s", clean_cmd, e)
        return f"Error executing command: {e}"


EXECUTE_COMMAND_SPEC = ToolSpec(
    tool_id="system_command_v1",
    name="execute_command",
    description=(
        "Execute a system terminal command directly on the host (PowerShell on Windows, Bash on Linux). "
        "Useful for running commands like 'fsutil volume diskfree D:', 'Get-ChildItem D:\\', 'dir', "
        "or inspecting processes and files. Has a 30-second timeout."
    ),
    skills_provided=[
        "shell_command",
        "system_command",
        "command_execution",
        "powershell_execution",
        "system_inspection",
        "terminal_command",
    ],
    parameters={
        "command": {
            "type": "string",
            "description": "The shell/PowerShell command to execute on the host",
            "required": True,
        }
    },
    function=execute_command,
    risk_level=RiskLevel.MEDIUM,
)
