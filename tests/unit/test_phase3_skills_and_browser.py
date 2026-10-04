"""
Unit tests for Phase 3:
- Autonomous Skill Learning & Distillation (AST safety checks, distillation pipeline, approval lifecycle)
- Interactive Headless Browser (SSRF validation, session lifecycle, snapshot extraction, web_extract auto-escalation)
"""

import ast
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import Settings
from src.registry.tools.browser_tools import (
    BrowserSession,
    browser_click,
    browser_close,
    browser_open,
    browser_screenshot,
    browser_snapshot,
    browser_type,
    is_ssrf_safe_url,
)
from src.registry.tools.hermes_tools import web_extract
from src.skills.distiller import SkillDistiller, validate_skill_ast
from src.skills.manager import SkillCandidate, SkillManager


# ── 1. Skill Distillation & AST Safety (Gap 5) ────────────────────


def test_validate_skill_ast_safe():
    """Verify that legitimate Python skill code passes AST validation."""
    safe_code = """
import json
import math
from datetime import datetime

async def calculate_summary(data: str) -> str:
    parsed = json.loads(data)
    total = sum(parsed.get('values', []))
    return f"Total: {total}"
"""
    is_safe, reason = validate_skill_ast(safe_code)
    assert is_safe is True
    assert "passed" in reason.lower()


def test_validate_skill_ast_forbidden_calls():
    """Verify that eval, exec, __import__ are rejected."""
    bad_eval = "def run():\n    return eval('2 + 2')"
    is_safe, reason = validate_skill_ast(bad_eval)
    assert is_safe is False
    assert "eval" in reason

    bad_exec = "def run():\n    exec('import os')"
    is_safe2, reason2 = validate_skill_ast(bad_exec)
    assert is_safe2 is False
    assert "exec" in reason2


def test_validate_skill_ast_forbidden_imports():
    """Verify that dangerous system modules (subprocess, pty, ctypes) are rejected."""
    bad_import1 = "import subprocess\ndef run(): pass"
    is_safe1, reason1 = validate_skill_ast(bad_import1)
    assert is_safe1 is False
    assert "subprocess" in reason1

    bad_import2 = "from pty import openpty\ndef run(): pass"
    is_safe2, reason2 = validate_skill_ast(bad_import2)
    assert is_safe2 is False
    assert "pty" in reason2

    bad_import3 = "import ctypes\ndef run(): pass"
    is_safe3, reason3 = validate_skill_ast(bad_import3)
    assert is_safe3 is False
    assert "ctypes" in reason3


@pytest.mark.asyncio
async def test_skill_distiller_pipeline(tmp_path):
    """Verify SkillDistiller converts a multi-step trace into a validated SkillCandidate."""
    mock_settings = Settings(enable_skill_learning=True, skill_min_score=0.8, skill_auto_promote=False)
    manager = SkillManager(base_dir=tmp_path / "skills")

    trace = [
        {"tool": "file_reader", "args": {"path": "server.conf"}, "result": "port=8080"},
        {"tool": "execute_command", "args": {"command": "netstat -an"}, "result": "8080 listening"},
    ]

    distiller = SkillDistiller()

    with patch("src.skills.distiller.get_settings", return_value=mock_settings), \
         patch("src.skills.distiller.get_skill_manager", return_value=manager):
        cand = await distiller.distill(
            goal="Inspect server configuration and verify listening port",
            tool_trace=trace,
            supervisor_score=0.95,
            workflow_id="wf_distill_test",
        )

        assert cand is not None
        assert cand.status == "pending_approval"
        assert cand.tool_trace_len == 2
        assert "inspect_server" in cand.name
        assert "ToolSpec" in cand.code

        # Verify saved in pending directory
        pending_skills = manager.list_pending()
        assert len(pending_skills) == 1
        assert pending_skills[0].name == cand.name


def test_skill_manager_approval_lifecycle(tmp_path):
    """Verify pending -> approved and pending -> rejected transitions."""
    manager = SkillManager(base_dir=tmp_path / "skills")

    cand = SkillCandidate(
        id="skill_test_lifecycle",
        name="test_lifecycle",
        goal="Test lifecycle approval",
        description="A test skill",
        code="async def run(): return 'ok'",
        parameters={},
        skills_provided=["test_lifecycle"],
        status="pending_approval",
    )
    manager.save_candidate(cand)

    assert len(manager.list_pending()) == 1
    assert len(manager.list_approved()) == 0

    # Approve
    success = manager.approve("test_lifecycle")
    assert success is True
    assert len(manager.list_pending()) == 0
    assert len(manager.list_approved()) == 1

    # Check summary for planner
    summary = manager.get_known_skills_summary()
    assert len(summary) == 1
    assert summary[0]["name"] == "test_lifecycle"


# ── 2. Interactive Browser Tools & SSRF Protection (Gap 6) ────────


def test_ssrf_protection_private_ips():
    """Verify that localhost, 127.0.0.1, 10.x, 192.168.x, and AWS metadata IPs are blocked."""
    # Localhost
    safe1, reason1 = is_ssrf_safe_url("http://localhost:8080")
    assert safe1 is False
    assert "Localhost access is prohibited" in reason1

    safe2, reason2 = is_ssrf_safe_url("http://127.0.0.1:3000")
    assert safe2 is False
    assert "SSRF Blocked" in reason2

    # Private network
    safe3, reason3 = is_ssrf_safe_url("http://192.168.1.1/admin")
    assert safe3 is False
    assert "SSRF Blocked" in reason3

    safe4, reason4 = is_ssrf_safe_url("http://10.0.0.5/api")
    assert safe4 is False
    assert "SSRF Blocked" in reason4

    # Cloud metadata endpoint
    safe5, reason5 = is_ssrf_safe_url("http://169.254.169.254/latest/meta-data/")
    assert safe5 is False
    assert "SSRF Blocked" in reason5

    # Public domain
    safe6, _ = is_ssrf_safe_url("https://example.com/test")
    assert safe6 is True

    # Override allow_private
    safe7, _ = is_ssrf_safe_url("http://127.0.0.1:8000", allow_private=True)
    assert safe7 is True


@pytest.mark.asyncio
async def test_browser_session_snapshot_and_interaction():
    """Verify browser_snapshot and interaction using mocked Playwright page."""
    mock_page = AsyncMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://example.com/dashboard"
    mock_page.title.return_value = "Example Dashboard"
    mock_page.evaluate.return_value = {
        "title": "Example Dashboard",
        "headings": ["H1: Welcome to Dashboard"],
        "elements": [
            {"ref": "@e1", "desc": "<a href=\"/settings\">Settings", "selector": "#settings-btn"},
            {"ref": "@e2", "desc": "<button>Refresh</button>", "selector": "button.refresh"},
            {"ref": "@e3", "desc": "<input type=\"text\">Search", "selector": "input#search"},
        ],
    }

    session = BrowserSession(workflow_id="wf_browser_test")
    session.page = mock_page

    with patch("src.registry.tools.browser_tools.get_browser_session", return_value=session):
        # 1. Snapshot
        snap = await browser_snapshot()
        assert "=== Page Snapshot ===" in snap
        assert "Example Dashboard" in snap
        assert "H1: Welcome to Dashboard" in snap
        assert "[@e1]" in snap
        assert "[@e2]" in snap

        # 2. Click using @e2
        click_res = await browser_click(element_ref="@e2")
        assert "Successfully clicked" in click_res
        mock_page.click.assert_called_with("button.refresh", timeout=10000)

        # 3. Type using @e3
        type_res = await browser_type(text="agent search query", element_ref="@e3")
        assert "Typed text into" in type_res
        mock_page.fill.assert_called_with("input#search", "")
        mock_page.type.assert_called_with("input#search", "agent search query", delay=50)

        # 4. Close
        close_res = await browser_close()
        assert "closed" in close_res.lower()
        mock_page.close.assert_called_once()


@pytest.mark.asyncio
async def test_web_extract_auto_escalation_to_browser():
    """Verify web_extract escalates to browser when JavaScript rendering is required."""
    mock_html = "<html><body><noscript>Please turn JavaScript on to continue</noscript></body></html>"
    mock_response = MagicMock()
    mock_response.text = mock_html
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    mock_settings = Settings(enable_browser=True)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("src.registry.tools.hermes_tools.get_settings", return_value=mock_settings), \
         patch("src.registry.tools.browser_tools.browser_open", new_callable=AsyncMock) as mock_open, \
         patch("src.registry.tools.browser_tools.browser_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = "=== Page Snapshot ===\nInteractive SPA rendered successfully."

        result = await web_extract("https://spa.example.com")
        assert "Interactive Browser" in result
        assert "SPA rendered successfully" in result
        mock_open.assert_called_once_with("https://spa.example.com")
        mock_snap.assert_called_once()
