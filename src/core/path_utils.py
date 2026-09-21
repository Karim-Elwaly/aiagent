"""
UAOS Path Utilities

Provides robust Windows and POSIX path resolution, extraction, and sanitization
for user queries, task parameters, and local file operations.
"""

from __future__ import annotations

import re
from pathlib import Path


def sanitize_raw_path(path_str: str) -> str:
    """Sanitize raw path string by removing surrounding quotes and resolving backslashes."""
    if not path_str:
        return ""
    clean = str(path_str).strip()
    # Strip leading/trailing quotation marks
    clean = clean.strip("\"'").strip()
    # Replace forward slashes on Windows drive paths if mixed
    clean = clean.replace("/", "\\") if ":" in clean else clean
    return clean


def extract_target_path(query: str) -> str:
    """Extract a Windows or POSIX filesystem path from a user query or text."""
    if not query:
        return ""

    # Match Windows drive path enclosed in quotes: "D:\path\to\dir" or 'D:\path\to\dir'
    m_quoted_win = re.search(r'["\']([a-zA-Z]:\\[^"\']+)["\']', query)
    if m_quoted_win:
        return m_quoted_win.group(1).strip()

    # Match POSIX path enclosed in quotes: "/path/to/dir"
    m_quoted_posix = re.search(r'["\'](/[^"\']+)["\']', query)
    if m_quoted_posix:
        return m_quoted_posix.group(1).strip()

    # Match unquoted Windows drive path: D:\Security-logs-test\...
    m_win = re.search(r'\b([a-zA-Z]:\\[^\s"\'<>|]+)', query)
    if m_win:
        return m_win.group(1).strip()

    # Match unquoted POSIX path: /var/log/... or /home/...
    m_posix = re.search(r'(\/(?:var|tmp|home|etc|opt|usr|Security-logs-test)[^\s"\'<>|]*)', query)
    if m_posix:
        return m_posix.group(1).strip()

    return ""


def resolve_target_path(path_str: str) -> Path | None:
    """Resolve a path string to an existing Path object, trying case and slash variants."""
    clean = sanitize_raw_path(path_str)
    if not clean:
        return None

    p = Path(clean)
    if p.exists():
        return p

    # Try forward-slash variant
    p_fwd = Path(clean.replace("\\", "/"))
    if p_fwd.exists():
        return p_fwd

    return p  # Return Path object even if not found so caller has clean path
