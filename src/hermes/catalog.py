"""
Hermes toolsets and skills, as AgentHub shows and manages them.

Toolsets come from the profile's ``GET /v1/toolsets``. Skills are read from disk, because hermes 0.21.5's
``GET /v1/skills`` lists names only and carries no source, path or enabled state: the profile's own ``skills/``
folder (``builtin`` when in ``.bundled_manifest``, ``hub`` when in ``.hub/lock.json``, otherwise ``local``) and
aiagent's ``skills.external_dirs`` folder (``aiagent``). Changes go through the ``hermes`` CLI.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from src.hermes.client import HermesClient
from src.hermes.profiles import REQUIRED_TOOLSETS, HermesError, HermesProfiles, read_env_value
from src.hermes.skills import SKILL_FILE, mark_hermes_origin
from src.hermes.toolsets import BUILTIN_TOOLSETS
from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
# Hub identifiers (``source/path/name``) or an https URL to a SKILL.md.
SKILL_IDENTIFIER = re.compile(r"^(https://\S{1,500}|[A-Za-z0-9][A-Za-z0-9_.\-/@:]{0,199})$")


class CatalogError(ValueError):
    """The request names something Hermes cannot act on."""


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


class HermesCatalog:
    def __init__(self, profiles: HermesProfiles, client: HermesClient):
        self.profiles = profiles
        self.client = client

    # ── toolsets ────────────────────────────────────────────

    async def toolsets(self, profile: str) -> list[dict[str, Any]]:
        key = read_env_value(self.profiles.profile_dir(profile) / ".env", "API_SERVER_KEY")
        rows: list[dict[str, Any]] = []
        if key:
            try:
                rows = await self.client.toolsets(profile, key)
            except Exception as exc:  # Hermes offline or an older API: fall back below
                logger.info("Hermes toolsets for '%s' unavailable: %s", profile, exc)
        applied = set(self.profiles.state.get(profile).get("toolsets", []))
        if not rows:
            rows = [{"name": n, "label": n, "description": "", "enabled": n in applied, "configured": None,
                     "tools": []} for n in BUILTIN_TOOLSETS]
        allowed = set(BUILTIN_TOOLSETS)
        return [
            {**r, "required": r.get("name") in REQUIRED_TOOLSETS}
            for r in rows if r.get("name") in allowed
        ]

    # ── skills ──────────────────────────────────────────────

    def _skill_dirs(self, profile: str) -> list[tuple[Path, str]]:
        return [
            (self.profiles.profile_dir(profile) / "skills", "hermes"),
            (self.profiles.skills_root / profile, "aiagent"),
        ]

    def _disabled(self, profile: str) -> set[str]:
        try:
            config = yaml.safe_load((self.profiles.profile_dir(profile) / "config.yaml").read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return set()
        skills = (config or {}).get("skills") or {}
        platform = (skills.get("platform_disabled") or {}).get("api_server") or []
        return {str(s) for s in (skills.get("disabled") or [])} | {str(s) for s in platform}

    def skills(self, profile: str) -> list[dict[str, Any]]:
        root = self.profiles.profile_dir(profile) / "skills"
        bundled: set[str] = set()
        try:
            bundled = {ln.split(":", 1)[0].strip() for ln in (root / ".bundled_manifest").read_text(
                encoding="utf-8").splitlines() if ln.strip()}
        except OSError:
            pass
        hub: dict[str, Any] = {}
        try:
            hub = json.loads((root / ".hub" / "lock.json").read_text(encoding="utf-8")).get("installed", {})
        except (OSError, ValueError):
            pass
        disabled = self._disabled(profile)

        found: dict[str, dict[str, Any]] = {}
        for base, origin in self._skill_dirs(profile):
            if not base.is_dir():
                continue
            for path in sorted(base.rglob(SKILL_FILE)):
                rel = path.relative_to(base)
                if any(part.startswith(".") for part in rel.parts):
                    continue
                try:
                    meta = _frontmatter(path.read_text(encoding="utf-8", errors="replace")[:4000])
                except OSError:
                    continue
                name = str(meta.get("name") or path.parent.name)
                if name in found:  # Hermes loads the first one by name
                    continue
                if origin == "aiagent":
                    source = "aiagent"
                elif name in hub:
                    source = "hub"
                elif name in bundled:
                    source = "builtin"
                else:
                    source = "local"
                entry = hub.get(name, {})
                found[name] = {
                    "name": name,
                    "description": str(meta.get("description") or "")[:500],
                    "category": rel.parts[0] if len(rel.parts) >= 3 else None,
                    "source": source,
                    "trust_level": entry.get("trust_level"),
                    "scan_verdict": entry.get("scan_verdict"),
                    "enabled": name not in disabled,
                }
        return sorted(found.values(), key=lambda s: (s["source"] != "aiagent", s["category"] or "", s["name"]))

    def skill_path(self, profile: str, name: str) -> Path:
        for base, _ in self._skill_dirs(profile):
            for path in base.rglob(SKILL_FILE) if base.is_dir() else []:
                if any(part.startswith(".") for part in path.relative_to(base).parts):
                    continue
                try:
                    meta = _frontmatter(path.read_text(encoding="utf-8", errors="replace")[:4000])
                except OSError:
                    continue
                if str(meta.get("name") or path.parent.name) == name:
                    return path
        raise CatalogError(f"Hermes profile '{profile}' has no skill named '{name}'")

    def search(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        out = self.profiles._run(["skills", "search", query, "--json", "--limit", str(max(1, min(limit, 50)))])
        start = min((i for i in (out.find("["), out.find("{")) if i >= 0), default=-1)
        if start < 0:
            return []
        try:
            data = json.loads(out[start:])
        except ValueError:
            return []
        rows = data.get("results", data.get("data", [])) if isinstance(data, dict) else data
        return [r for r in rows if isinstance(r, dict)]

    def install(self, profile: str, identifier: str) -> str:
        if not SKILL_IDENTIFIER.match(identifier):
            raise CatalogError(f"Not a skill identifier: {identifier!r}")
        # No --force: a skill that Hermes's security scan blocks stays blocked.
        return self.profiles._run(["-p", profile, "skills", "install", identifier, "--yes"])[-2000:]

    def uninstall(self, profile: str, name: str) -> str:
        if not SKILL_NAME.match(name):
            raise CatalogError(f"Not a skill name: {name!r}")
        return self.profiles._run(["-p", profile, "skills", "uninstall", name, "--yes"])[-2000:]

    def import_skill(self, profile: str, name: str, registry: ToolRegistry | None) -> ToolSpec:
        """Register a Hermes skill in aiagent so agents can curate it and the Universal engine can use it."""
        from src.registry.hermes.hermes_loader import import_and_persist_hermes_skill

        content = self.skill_path(profile, name).read_text(encoding="utf-8")
        spec = import_and_persist_hermes_skill(content, name_override=name, registry=registry, persist=True)
        mark_hermes_origin(spec.name)
        return spec


__all__ = ["CatalogError", "HermesCatalog", "HermesError"]
