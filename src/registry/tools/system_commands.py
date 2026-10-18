"""
System Command Execution Tools

Allows running safe terminal inspection and system commands (PowerShell on Windows, bash on Linux).
Provides system-level querying capabilities (e.g. fsutil, Get-ChildItem, dir, ipconfig, processes).
"""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from typing import Any

from src.core.models import RiskLevel
from src.core.text_utils import smart_truncate
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

MAX_COMMAND_SECONDS = 30
MAX_OUTPUT_CHARS = 4000


async def execute_command(
    command: str | None = None,
    cmd: str | None = None,
    args: str | None = None,
    **extra_kwargs: Any,
) -> str:
    """Run a system command and capture stdout/stderr safely."""
    clean_cmd = command or cmd or args or ""
    if not clean_cmd.strip():
        return "Error: No command specified to execute."

    # Decide interpreter based on host OS
    is_windows = platform.system() == "Windows"
    if is_windows:
        cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", clean_cmd]
    else:
        cmd_args = ["bash", "-c", clean_cmd]

    try:
        result = await asyncio.to_thread(
            subprocess.run,
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
        return smart_truncate(output, max_chars=MAX_OUTPUT_CHARS)
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {MAX_COMMAND_SECONDS} seconds."
    except Exception as e:
        logger.error("Command execution failed for '%s': %s", clean_cmd, e)
        return f"Error executing command: {e}"


def get_system_info(**kwargs: Any) -> str:
    """Retrieve local device and host environment specifications:
    hostname, OS name and version, platform architecture, username,
    local IP address, and Python runtime.
    """
    import getpass
    import json
    import socket

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = platform.node() or "Unknown"

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    os_info = f"{platform.system()} {platform.release()} (Build {platform.version()})"
    arch = platform.machine()
    user = getpass.getuser()

    lines = [
        "# Local Device & System Information",
        "",
        "| Attribute | Value |",
        "| :--- | :--- |",
        f"| **Device Hostname** | `{hostname}` |",
        f"| **Operating System** | {os_info} |",
        f"| **Architecture** | {arch} |",
        f"| **Current User** | `{user}` |",
        f"| **Local Network IP** | `{local_ip}` |",
        f"| **Python Runtime** | {platform.python_version()} |",
        "",
        "```json",
        json.dumps({
            "hostname": hostname,
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": arch,
            "username": user,
            "local_ip": local_ip,
            "python_version": platform.python_version(),
        }, indent=2),
        "```",
    ]
    return "\n".join(lines)


EXECUTE_COMMAND_SPEC = ToolSpec(
    tool_id="system_command_v1",
    name="execute_command",
    description=(
        "Execute a system terminal command directly on the host (PowerShell on Windows, Bash on Linux). "
        "Useful for running commands like 'hostname', 'fsutil volume diskfree D:', 'Get-ChildItem D:\\', 'dir', "
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

SYSTEM_INFO_SPEC = ToolSpec(
    tool_id="system_info_v1",
    name="get_system_info",
    description=(
        "Retrieve fundamental device and host environment specifications: "
        "device hostname, operating system, machine architecture, current user, "
        "and local IP address. Instant zero-argument inspection."
    ),
    skills_provided=[
        "system_info",
        "host_info",
        "device_info",
        "hostname_lookup",
        "system_inspection",
        "environment_query",
    ],
    parameters={},
    function=get_system_info,
    risk_level=RiskLevel.LOW,
)
