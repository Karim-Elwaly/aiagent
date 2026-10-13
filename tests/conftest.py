"""Test-wide guards: a test never touches the developer's real Hermes install, state files or running gateway."""

from __future__ import annotations

import pytest

import src.hermes.active_runs as active_runs
import src.hermes.profiles as profiles
from src.hermes.client import HermesAPIError, HermesClient


@pytest.fixture(autouse=True)
def _isolate_hermes(monkeypatch, tmp_path_factory):
    def refuse_cli(self, args):
        raise profiles.HermesError(f"hermes {' '.join(args)}: the real CLI is disabled in tests")

    async def refuse_run(self, *args, **kwargs):
        raise HermesAPIError("the real Hermes gateway is disabled in tests")

    state_dir = tmp_path_factory.mktemp("hermes-state")
    monkeypatch.setattr(profiles.HermesProfiles, "_cli", refuse_cli)
    monkeypatch.setattr(HermesClient, "create_run", refuse_run)
    monkeypatch.setattr(profiles, "STATE_DIR", state_dir)
    monkeypatch.setattr(active_runs, "STATE_DIR", state_dir)
