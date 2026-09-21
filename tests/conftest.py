"""Shared pytest fixtures.

Keeps test runs hermetic: no test may write evidence into the repository's
``data/evidence`` directory, and no test may observe evidence left behind by a
previous test.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_evidence_root(tmp_path, monkeypatch):
    """Redirect the evidence store to a per-test temporary directory.

    Also clears the module-level store cache so each test starts from an empty
    store. Without this, tools called with no run id would share a single
    'adhoc' store and one test's evidence would become citable in another —
    the same cross-contamination risk that must never occur between real
    investigations.
    """
    monkeypatch.setenv("UAOS_EVIDENCE_DIR", str(tmp_path / "evidence"))

    from src.core import evidence

    monkeypatch.setattr(evidence, "EVIDENCE_ROOT", tmp_path / "evidence")
    evidence._stores.clear()
    yield
    evidence._stores.clear()
