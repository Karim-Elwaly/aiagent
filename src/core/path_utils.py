"""
AgentHub Universal Path Healing & Resolution Utility

Provides cross-platform path resolution, repairing Python AST escape artifacts
(e.g., \\a -> 0x07 Bell, \\r -> CR, \\t -> Tab) that occur when Windows paths with single
backslashes are evaluated, and sanitizing unescaped Windows paths in JSON strings.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


_ESCAPE_REPLACEMENTS = [
    ("\a", r"\a"),
    ("\b", r"\b"),
    ("\f", r"\f"),
    ("\n", r"\n"),
    ("\r", r"\r"),
    ("\t", r"\t"),
    ("\v", r"\v"),
]


def resolve_target_path(path_input: str | Path) -> Path:
    """Resolve and heal raw, escaped, or mangled filesystem paths across platforms.
    
    Handles:
      - Path objects and string paths
      - Single backslash escape artifacts (\\a -> 0x07, \\r -> 0x0d, \\t -> 0x09)
      - Trailing punctuation and surrounding quotes
      - Leading colons or query noise (e.g. ": D:\\" -> "D:\\")
      - Windows bare drive letters ("D:" -> "D:\\")
      - Forward-slash and backslash normalization
      - Relative to absolute resolution
    """
    if isinstance(path_input, Path):
        raw_str = str(path_input)
    else:
        raw_str = str(path_input or "").strip().strip('"\'')

    if not raw_str:
        return Path(os.getcwd())

    # Clean leading colons or query noise before drive letters (e.g. ": D:\" -> "D:\")
    cleaned_lead = re.sub(r"^[a-zA-Z0-9_\s]*:\s*(?=[a-zA-Z]:)", "", raw_str).strip()
    if cleaned_lead.startswith(":") or cleaned_lead.startswith(" "):
        cleaned_lead = cleaned_lead.lstrip(": ")
    if cleaned_lead:
        raw_str = cleaned_lead

    # Windows bare drive letter like "D:" or "d:" -> normalize to root "D:\"
    if re.match(r"^[a-zA-Z]:$", raw_str):
        raw_str = f"{raw_str}\\"

    # 1. Direct check
    candidate = Path(raw_str)
    try:
        if candidate.exists():
            return candidate.resolve()
    except Exception:
        pass

    # 2. Heal escape artifacts from AST/Python evaluation (\a -> 0x07, \r -> 0x0d, etc.)
    healed_str = raw_str
    for esc_char, replacement in _ESCAPE_REPLACEMENTS:
        if esc_char in healed_str:
            healed_str = healed_str.replace(esc_char, replacement)

    candidate_healed = Path(healed_str)
    try:
        if candidate_healed.exists():
            return candidate_healed.resolve()
    except Exception:
        pass

    # 3. Clean trailing punctuation from regex captures, preserving Windows drive colons
    if re.match(r"^[a-zA-Z]:[\\/]?$", healed_str):
        stripped = healed_str if healed_str.endswith(("\\", "/")) else f"{healed_str}\\"
    else:
        stripped = healed_str.rstrip(",;.:)]}")
        if re.match(r"^[a-zA-Z]:$", stripped):
            stripped = f"{stripped}\\"

    candidate_stripped = Path(stripped)
    try:
        if candidate_stripped.exists():
            return candidate_stripped.resolve()
    except Exception:
        pass

    # 4. Try forward-slash normalization
    fwd_str = stripped.replace("\\", "/")
    candidate_fwd = Path(fwd_str)
    try:
        if candidate_fwd.exists():
            return candidate_fwd.resolve()
    except Exception:
        pass

    # 5. Check if Windows drive letter is missing colon e.g. "D\folder" -> "D:\folder"
    if re.match(r"^[a-zA-Z][\\/]", stripped):
        with_colon = f"{stripped[0]}:{stripped[1:]}"
        candidate_colon = Path(with_colon)
        try:
            if candidate_colon.exists():
                return candidate_colon.resolve()
        except Exception:
            pass

    # Fallback to candidate_stripped or original candidate
    return candidate_stripped if candidate_stripped.is_absolute() else candidate_stripped.resolve()


def _longest_existing_prefix(raw: str) -> str | None:
    """Trim whitespace-delimited tokens off the right until the path exists on disk.

    Path regexes allow spaces (for "C:\\Program Files\\..."), so a match often runs
    past the path into following prose or a second path.
    """
    tokens = raw.split(" ")
    for end in range(len(tokens), 0, -1):
        candidate = " ".join(tokens[:end]).rstrip(",;.:)]}")
        if not candidate:
            continue
        if re.match(r"^[a-zA-Z]:$", candidate):
            candidate = f"{candidate}\\"
        try:
            p = Path(candidate)
            if p.exists():
                return str(p.resolve())
        except Exception:
            continue
    return None


def extract_target_path(text: str) -> str | None:
    """Extract and heal a target filesystem path from a user query or prompt string.
    
    Looks for:
      - Windows paths (e.g. D:\\Security-logs-test\\..., C:\\Logs, D:\\, D:, D:/...)
      - Unix absolute paths (e.g. /var/log/..., /tmp/...)
    """
    if not text:
        return None

    # First heal escape artifacts in text before regex matching
    healed_text = text
    for esc_char, replacement in _ESCAPE_REPLACEMENTS:
        if esc_char in healed_text:
            healed_text = healed_text.replace(esc_char, replacement)

    # Windows drive root or subpath: e.g. D:\, D:, D:/, D:\ai_gpu
    m_win = re.search(r'([a-zA-Z]:(?:[\\/][^"\'\n\r\t<>|]*)?)', healed_text)
    if m_win:
        raw_p = m_win.group(1).rstrip(",;.:)]}")
        if re.match(r"^[a-zA-Z]:$", raw_p):
            raw_p = f"{raw_p}\\"
        existing = _longest_existing_prefix(raw_p)
        if existing:
            return existing
        resolved = resolve_target_path(raw_p)
        return str(resolved)

    # Unix absolute path: require either known unix root (/var, /tmp, /etc, /usr, /home) or at least 2 directory segments
    m_unix = re.search(r'((?:/(?:var|tmp|etc|usr|opt|home|root|bin|proc|sys|Users|private)/[a-zA-Z0-9._/-]+|/(?:[a-zA-Z0-9._-]+/){2,}[a-zA-Z0-9._-]+))', healed_text)
    if m_unix:
        raw_u = m_unix.group(1).rstrip(",;.:)]}")
        existing = _longest_existing_prefix(raw_u)
        if existing:
            return existing
        resolved = resolve_target_path(raw_u)
        return str(resolved)

    return None


def sanitize_json_string_backslashes(text: str) -> str:
    """Sanitize raw or unescaped backslashes inside JSON strings.
    
    Ensures Windows paths like "D:\\Security-logs-test\\attack-cases" can be parsed
    by standard json.loads without failing or falling back to ast.literal_eval.
    """
    def _fix_quoted_str(match: re.Match) -> str:
        content = match.group(0)
        inner = content[1:-1]
        
        # If string contains a Windows drive or path separators
        if re.search(r'[a-zA-Z]:[\\/]', inner) or "\\" in inner:
            # Replace single backslash not followed by another backslash or quote
            fixed = re.sub(r'\\(?![\\"])', r'\\\\', inner)
            return f'"{fixed}"'
        
        # General JSON escape fix
        fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', inner)
        return f'"{fixed}"'

    return re.sub(r'"(?:[^"\\]|\\.)*"', _fix_quoted_str, text)
