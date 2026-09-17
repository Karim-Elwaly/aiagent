"""
File Operations Tools

Provides file reading, writing, and listing capabilities.
Delete operations are classified as CRITICAL risk (require human approval).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────
MAX_READ_CHARS = 8000  # prevent context overflow on large files


async def read_file(file_path: str) -> str:
    """Read the contents of a file from the local filesystem.

    Large files are truncated to prevent context window overflow.
    """
    path = Path(file_path)

    if not path.exists():
        return f"Error: File not found: {file_path}"

    if not path.is_file():
        return f"Error: Path is not a file: {file_path}"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")

        if len(content) > MAX_READ_CHARS:
            return (
                content[:MAX_READ_CHARS]
                + f"\n\n[...truncated. File is {len(content)} chars total, "
                f"showing first {MAX_READ_CHARS}]"
            )

        return content

    except Exception as e:
        logger.error("Failed to read file '%s': %s", file_path, e)
        return f"Error reading file: {e}"


async def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    path = Path(file_path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {file_path}"

    except Exception as e:
        logger.error("Failed to write file '%s': %s", file_path, e)
        return f"Error writing file: {e}"


async def list_directory(directory_path: str) -> str:
    """List files and directories in the given path."""
    path = Path(directory_path)

    if not path.exists():
        return f"Error: Directory not found: {directory_path}"

    if not path.is_dir():
        return f"Error: Path is not a directory: {directory_path}"

    try:
        entries = sorted(path.iterdir())
        lines = []
        for entry in entries[:100]:  # cap at 100 entries
            prefix = "📁" if entry.is_dir() else "📄"
            size = ""
            if entry.is_file():
                size_bytes = entry.stat().st_size
                if size_bytes < 1024:
                    size = f" ({size_bytes} B)"
                elif size_bytes < 1024 * 1024:
                    size = f" ({size_bytes / 1024:.1f} KB)"
                else:
                    size = f" ({size_bytes / (1024 * 1024):.1f} MB)"
            lines.append(f"{prefix} {entry.name}{size}")

        result = "\n".join(lines) if lines else "(empty directory)"

        if len(entries) > 100:
            result += f"\n\n[...and {len(entries) - 100} more entries]"

        return result

    except Exception as e:
        logger.error("Failed to list directory '%s': %s", directory_path, e)
        return f"Error listing directory: {e}"


async def delete_file(file_path: str) -> str:
    """Delete a file from the filesystem. THIS IS IRREVERSIBLE."""
    path = Path(file_path)

    if not path.exists():
        return f"Error: File not found: {file_path}"

    if not path.is_file():
        return f"Error: Path is not a file (won't delete directories): {file_path}"

    try:
        path.unlink()
        return f"Successfully deleted: {file_path}"

    except Exception as e:
        logger.error("Failed to delete file '%s': %s", file_path, e)
        return f"Error deleting file: {e}"


# ── Registration ─────────────────────────────────────────────────

READ_FILE_SPEC = ToolSpec(
    tool_id="file_reader_v1",
    name="read_file",
    description=(
        "Read the contents of a file from the local filesystem. "
        "Large files are automatically truncated."
    ),
    skills_provided=["file_reading"],
    parameters={
        "file_path": {
            "type": "string",
            "description": "Absolute or relative path to the file",
            "required": True,
        },
    },
    function=read_file,
    risk_level=RiskLevel.LOW,
)

WRITE_FILE_SPEC = ToolSpec(
    tool_id="file_writer_v1",
    name="write_file",
    description=(
        "Write content to a file. Creates parent directories if needed. "
        "Overwrites existing files."
    ),
    skills_provided=["file_writing"],
    parameters={
        "file_path": {
            "type": "string",
            "description": "Path where the file should be written",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Content to write to the file",
            "required": True,
        },
    },
    function=write_file,
    risk_level=RiskLevel.MEDIUM,
)

LIST_DIR_SPEC = ToolSpec(
    tool_id="dir_lister_v1",
    name="list_directory",
    description=(
        "List all files and subdirectories in a given path. "
        "Shows file sizes. Capped at 100 entries."
    ),
    skills_provided=["directory_listing", "file_discovery"],
    parameters={
        "directory_path": {
            "type": "string",
            "description": "Path to the directory to list",
            "required": True,
        },
    },
    function=list_directory,
    risk_level=RiskLevel.LOW,
)

DELETE_FILE_SPEC = ToolSpec(
    tool_id="file_deleter_v1",
    name="delete_file",
    description=(
        "Delete a file from the filesystem. THIS IS IRREVERSIBLE. "
        "Only deletes single files, not directories."
    ),
    skills_provided=["file_deletion"],
    parameters={
        "file_path": {
            "type": "string",
            "description": "Path to the file to delete",
            "required": True,
        },
    },
    function=delete_file,
    risk_level=RiskLevel.CRITICAL,  # triggers human approval gate
)
