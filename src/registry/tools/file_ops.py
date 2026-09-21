"""
File Operations Tools

Provides file reading, writing, recursive directory listing, disk usage inspection,
and deletion capabilities directly on the host filesystem.
Delete operations are classified as CRITICAL risk (require human approval).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────
MAX_READ_CHARS = 8000  # prevent context overflow on large files


def _format_size(size_bytes: int) -> str:
    """Format bytes into clean human-readable representation."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024**3):.2f} GB"


async def read_file(
    file_path: str | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> str:
    """Read the contents of a file from the local filesystem.

    Large files are truncated to prevent context window overflow.
    """
    raw_path = file_path or path or kwargs.get("filepath") or kwargs.get("file") or ""
    clean_path = str(raw_path).strip().strip('"').strip("'")
    target = Path(clean_path)

    if not target.exists():
        return f"Error: File not found: {clean_path}"

    if not target.is_file():
        if target.is_dir():
            logger.info("read_file called on directory '%s'; delegating to list_directory", clean_path)
            return await list_directory(directory_path=clean_path)
        return f"Error: Path is not a file: {clean_path}"

    try:
        content = target.read_text(encoding="utf-8", errors="replace")

        if len(content) > MAX_READ_CHARS:
            return (
                content[:MAX_READ_CHARS]
                + f"\n\n[...truncated. File is {len(content)} chars total, "
                f"showing first {MAX_READ_CHARS}]"
            )

        return content

    except Exception as e:
        logger.error("Failed to read file '%s': %s", clean_path, e)
        return f"Error reading file: {e}"


async def write_file(
    file_path: str | None = None,
    content: str = "",
    path: str | None = None,
    **kwargs: Any,
) -> str:
    """Write content to a file. Creates parent directories if needed."""
    raw_path = file_path or path or kwargs.get("filepath") or kwargs.get("file") or ""
    raw_content = content or kwargs.get("text") or kwargs.get("data") or ""
    clean_path = str(raw_path).strip().strip('"').strip("'")
    target = Path(clean_path)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(raw_content), encoding="utf-8")
        return f"Successfully wrote {len(raw_content)} characters to {clean_path}"

    except Exception as e:
        logger.error("Failed to write file '%s': %s", clean_path, e)
        return f"Error writing file: {e}"


async def list_directory(
    directory_path: str | None = None,
    path: str | None = None,
    dir_path: str | None = None,
    recursive: bool = True,
    max_depth: int = 2,
    max_items: int = 150,
    **kwargs: Any,
) -> str:
    """List files and subdirectories in the given local directory path.

    Supports recursive traversal (recursive=True) up to max_depth levels to generate
    a structured tree. Shows file names, human-readable sizes, and subdirectory item counts.
    """
    raw_path = directory_path or path or dir_path or kwargs.get("directory") or kwargs.get("folder") or "D:\\"
    clean_path = str(raw_path).strip().strip('"').strip("'")
    if not clean_path or clean_path.startswith("<") or clean_path.endswith(">"):
        clean_path = "D:\\"
    if len(clean_path) == 2 and clean_path[1] == ":":
        clean_path += "\\"

    target = Path(clean_path)

    if not target.exists():
        anchor_path = Path(target.anchor) if target.anchor else Path("D:\\")
        base = target.parent if target.parent.exists() else (anchor_path if anchor_path.exists() else None)
        if base and base.exists():
            try:
                available = [p.name for p in sorted(base.iterdir()) if p.is_dir()][:30]
                available_str = ", ".join(f"'{name}'" for name in available) if available else "none"
            except Exception:
                available_str = "access restricted"
                available = []

            dirs_json = [{"name": name, "path": str(base / name), "type": "directory"} for name in available]
            lines = [
                f"# Directory Tree Inspection for '{clean_path}':",
                f"- **Status**: ⚠️ Directory '{clean_path}' does not exist on disk.",
                f"- **Inspected Root**: Base location '{base}' is mounted and active.",
                f"- **Available Subdirectories in '{base}'**: {available_str}",
                "",
                "```json",
                json.dumps(dirs_json, indent=2),
                "```",
            ]
            return "\n".join(lines)
        return f"Error: Directory not found: {clean_path}"

    if not target.is_dir():
        return f"Error: Path is not a directory: {clean_path}"

    # Handle recursive parameter from kwargs if provided as string or bool
    rec_val = kwargs.get("recursive", recursive)
    if isinstance(rec_val, str):
        rec_val = rec_val.lower() in ("true", "1", "yes")

    if rec_val:
        lines = [f"# Directory Tree for '{clean_path}' (recursive, max depth {max_depth}):"]
        item_count = 0
        dir_count = 0
        file_count = 0

        def _walk(curr: Path, prefix: str = "", depth: int = 1):
            nonlocal item_count, dir_count, file_count
            if depth > max_depth or item_count >= max_items:
                return

            try:
                entries = sorted(curr.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except (PermissionError, OSError) as e:
                lines.append(f"{prefix}└── ⚠️ (Access restricted: {e})")
                return

            total_entries = len(entries)
            for i, entry in enumerate(entries):
                if item_count >= max_items:
                    lines.append(f"{prefix}... [truncated at {max_items} items]")
                    return
                item_count += 1
                is_last = (i == total_entries - 1)
                connector = "└── " if is_last else "├── "
                next_prefix = prefix + ("    " if is_last else "│   ")

                if entry.is_dir():
                    dir_count += 1
                    child_info = ""
                    try:
                        child_count = len(list(entry.iterdir()))
                        child_info = f" ({child_count} items)"
                    except Exception:
                        pass
                    lines.append(f"{prefix}{connector}📁 {entry.name}{child_info}")
                    if depth < max_depth:
                        _walk(entry, next_prefix, depth + 1)
                else:
                    file_count += 1
                    size_info = ""
                    try:
                        size_info = f" ({_format_size(entry.stat().st_size)})"
                    except Exception:
                        pass
                    lines.append(f"{prefix}{connector}📄 {entry.name}{size_info}")

        _walk(target)
        lines.append(f"\nTotal: {item_count} items enumerated ({dir_count} directories, {file_count} files).")
        return "\n".join(lines)

    # Non-recursive listing
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = [f"# Directory Listing for '{clean_path}':"]
        dir_count = 0
        file_count = 0

        for entry in entries[:max_items]:
            if entry.is_dir():
                dir_count += 1
                child_info = ""
                try:
                    child_count = len(list(entry.iterdir()))
                    child_info = f" ({child_count} items)"
                except Exception:
                    pass
                lines.append(f"📁 {entry.name}{child_info}")
            else:
                file_count += 1
                size_info = ""
                try:
                    size_info = f" ({_format_size(entry.stat().st_size)})"
                except Exception:
                    pass
                lines.append(f"📄 {entry.name}{size_info}")

        if len(entries) > max_items:
            lines.append(f"\n[...and {len(entries) - max_items} more entries]")

        lines.append(f"\nTotal: {len(entries)} items ({dir_count} directories, {file_count} files).")

        # Machine-readable JSON array of directory paths for programmatic tasks and supervisor evaluation
        try:
            dirs_json = [{"path": str(e.resolve() if hasattr(e, "resolve") else e)} for e in entries if e.is_dir()][:60]
            lines.append("\n```json\n" + json.dumps(dirs_json, indent=2) + "\n```")
        except Exception:
            pass

        return "\n".join(lines)

    except Exception as e:
        logger.error("Failed to list directory '%s': %s", clean_path, e)
        return f"Error listing directory: {e}"


async def delete_file(
    file_path: str | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> str:
    """Delete a file from the filesystem. THIS IS IRREVERSIBLE."""
    raw_path = file_path or path or kwargs.get("filepath") or kwargs.get("file") or ""
    clean_path = str(raw_path).strip().strip('"').strip("'")
    target = Path(clean_path)

    if not target.exists():
        return f"Error: File not found: {clean_path}"

    if not target.is_file():
        return f"Error: Path is not a file (won't delete directories): {clean_path}"

    try:
        target.unlink()
        return f"Successfully deleted: {clean_path}"

    except Exception as e:
        logger.error("Failed to delete file '%s': %s", clean_path, e)
        return f"Error deleting file: {e}"


def _calc_dir_stats(dir_path: Path, max_files: int = 5000, timeout_sec: float = 1.5) -> tuple[int, int, bool]:
    """Fast directory size and file counter with timeout & file limits."""
    total_bytes = 0
    file_count = 0
    truncated = False
    start_time = time.monotonic()
    stack = [str(dir_path)]

    try:
        while stack:
            if time.monotonic() - start_time > timeout_sec or file_count >= max_files:
                truncated = True
                break
            curr = stack.pop()
            try:
                with os.scandir(curr) as it:
                    for entry in it:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                file_count += 1
                                total_bytes += entry.stat(follow_symlinks=False).st_size
                            elif entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue
    except Exception:
        pass

    return total_bytes, file_count, truncated


async def get_disk_usage(
    path: str | None = None,
    directory_path: str | None = None,
    drive: str | None = None,
    **kwargs: Any,
) -> str:
    """Inspect local filesystem drive or folder disk usage:
    total/used/free capacity in GB and bytes, plus a comprehensive breakdown table
    of each top-level entry with size in bytes, human-readable size, file count,
    and percentage of used space.
    """
    raw_path = path or directory_path or drive or kwargs.get("directory") or kwargs.get("folder") or "D:\\"
    clean_path = str(raw_path).strip().strip('"').strip("'")
    if not clean_path or clean_path.startswith("<") or clean_path.endswith(">"):
        clean_path = "D:\\"
    if len(clean_path) == 2 and clean_path[1] == ":":
        clean_path += "\\"

    target = Path(clean_path)
    drive_fallback_msg = ""
    if not target.exists():
        anchor = Path(target.anchor) if target.anchor else Path("D:\\")
        if anchor.exists():
            drive_fallback_msg = f"*(Note: Path '{clean_path}' does not exist on disk; reporting disk usage and storage breakdown for host drive '{anchor}')*"
            target = anchor
        else:
            return f"Error: Path not found: {clean_path}"

    try:
        total, used, free = shutil.disk_usage(str(target))
        pct_used = (used / total) * 100 if total > 0 else 0
        pct_free = (free / total) * 100 if total > 0 else 0

        drive_name = target.drive or str(target.anchor) or "Host Drive Partition"
        lines = [
            f"# Host Disk Partition & Directory Storage Breakdown:",
            f"- **Host Drive / Volume ({drive_name})**: Total Capacity: {total / (1024**3):.2f} GB | Free: {free / (1024**3):.2f} GB ({pct_free:.1f}% free)",
            f"- **Target Directory Inspected**: '{target}'",
        ]
        if drive_fallback_msg:
            lines.extend([drive_fallback_msg, ""])

        lines.extend([
            "",
            f"## Files & Sub-Directories inside '{target}':",
            "",
            "| Name | Type | Size (Human) | Size (Bytes) | File Count | % of Drive Used |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        if target.is_dir():
            try:
                entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                for entry in entries[:60]:
                    is_dir = entry.is_dir()
                    item_type = "📁 Directory" if is_dir else "📄 File"
                    size_bytes = 0
                    file_cnt = 0
                    trunc_flag = ""

                    if is_dir:
                        size_bytes, file_cnt, was_trunc = _calc_dir_stats(entry)
                        trunc_flag = " (partial/capped)" if was_trunc else ""
                    else:
                        try:
                            size_bytes = entry.stat().st_size
                            file_cnt = 1
                        except Exception:
                            pass

                    human_sz = _format_size(size_bytes) + trunc_flag
                    pct_item_used = (size_bytes / used * 100) if used > 0 else 0
                    pct_str = f"{pct_item_used:.2f}%" if pct_item_used >= 0.01 else "<0.01%"

                    lines.append(
                        f"| {entry.name} | {item_type} | {human_sz} | {size_bytes:,} | {file_cnt:,} | {pct_str} |"
                    )

                if len(entries) > 60:
                    lines.append(f"\n*(Table truncated: showing top 60 of {len(entries)} items)*")

            except PermissionError:
                lines.append("\n*(Permission denied listing some root directory entries)*")

        # Machine-readable JSON metrics for supervisor verification
        metrics_dict = {
            "path": str(target),
            "target_requested": clean_path,
            "exists": (clean_path == str(target)),
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "total_kilobytes": round(total / 1024, 2),
            "used_kilobytes": round(used / 1024, 2),
            "free_kilobytes": round(free / 1024, 2),
            "total_megabytes": round(total / (1024**2), 2),
            "used_megabytes": round(used / (1024**2), 2),
            "free_megabytes": round(free / (1024**2), 2),
            "total_gigabytes": round(total / (1024**3), 2),
            "used_gigabytes": round(used / (1024**3), 2),
            "free_gigabytes": round(free / (1024**3), 2),
            "percent_used": round(pct_used, 2),
            "percent_free": round(pct_free, 2),
        }
        lines.append("\n```json\n" + json.dumps(metrics_dict, indent=2) + "\n```")

        return "\n".join(lines)

    except Exception as e:
        logger.error("Failed to compute disk usage for '%s': %s", clean_path, e)
        return f"Error computing disk usage for {clean_path}: {e}"


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
        "List files and subdirectories in a given local directory path (e.g. 'D:\\' or 'C:\\Users'). "
        "Supports recursive tree generation up to max_depth levels. "
        "Shows file names, sizes, and directory item counts. Runs directly on the host machine."
    ),
    skills_provided=[
        "directory_listing",
        "file_discovery",
        "file_search",
        "filesystem_inspection",
        "file_enumeration",
        "recursive_file_listing",
        "file_tree",
        "data_processing",
    ],
    parameters={
        "directory_path": {
            "type": "string",
            "description": "Path to the local directory to list (e.g. 'D:\\')",
            "required": True,
        },
        "recursive": {
            "type": "boolean",
            "description": "If true, recursively walks subdirectories up to max_depth levels (default True)",
            "required": False,
        },
        "max_depth": {
            "type": "integer",
            "description": "Maximum recursion depth when recursive=True (default 2, max 4)",
            "required": False,
        },
        "max_items": {
            "type": "integer",
            "description": "Maximum number of items to return before truncating (default 150)",
            "required": False,
        },
    },
    function=list_directory,
    risk_level=RiskLevel.LOW,
)

DISK_USAGE_SPEC = ToolSpec(
    tool_id="disk_usage_v1",
    name="get_disk_usage",
    description=(
        "Inspect local filesystem drive or directory disk usage: total/used/free capacity in GB, "
        "plus a full table of top-level folders with size in bytes, human-readable size, file count, "
        "and percentage of used space. Executes directly on the host machine."
    ),
    skills_provided=[
        "disk_usage",
        "disk_space",
        "storage_report",
        "filesystem_capacity",
    ],
    parameters={
        "path": {
            "type": "string",
            "description": "Drive letter or directory path to inspect (e.g. 'D:\\' or 'C:\\')",
            "required": False,
        },
    },
    function=get_disk_usage,
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
