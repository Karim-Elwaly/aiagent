"""
Tool groups for tasks without an agent.

Hermes sends the model the definition of every aiagent tool its profile is connected to, on every call. A task
without an agent used to run on ``aiagent-default``, which sees all of them. Each group here is a small Hermes profile
(``aiagent-bundle-<name>``) that sees only a few related tools; a task runs on the smallest group covering its tools.
"""

from __future__ import annotations

from collections.abc import Iterable

BUNDLE_PREFIX = "aiagent-bundle-"

# Overlapping on purpose: SOC phases read logs with the file tools between security tools.
BUNDLES: dict[str, tuple[str, ...]] = {
    "files": ("read_file", "write_file", "list_directory", "get_disk_usage", "delete_file"),
    "security": (
        "triage_security_alert", "gather_log_evidence", "lookup_threat_indicators", "analyze_incident_impact",
        "compress_security_timeline", "propose_containment_response", "read_file", "list_directory",
    ),
    "system": ("execute_command", "get_system_info", "execute_python", "python_session"),
    "web": ("web_search", "web_extract"),
    "browser": (
        "browser_open", "browser_snapshot", "browser_click", "browser_type", "browser_screenshot", "browser_close",
    ),
}


def bundle_profile(bundle: str) -> str:
    return BUNDLE_PREFIX + bundle


def bundle_tools(bundle: str) -> list[str]:
    return list(BUNDLES[bundle])


def select_bundle(tool_names: Iterable[str]) -> str | None:
    """The smallest group holding every tool; ``None`` when no group does (the task needs ``aiagent-default``).

    A task with no tools gets the smallest group: it answers from its context and asks for anything else.
    """
    needed = set(tool_names)
    fits = [(len(tools), name) for name, tools in BUNDLES.items() if needed <= set(tools)]
    return min(fits)[1] if fits else None
