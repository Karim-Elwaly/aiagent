"""
Comprehensive verification script for Hermes Native Tools & Skills integration.
"""

from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import Settings, get_settings
from src.hermes.profiles import (
    DEFAULT_PROFILE,
    DYNAMIC_PROFILE_PREFIX,
    HermesProfiles,
    ProfileState,
)
from src.workers.hermes_agent_worker import HermesAgentWorker
from src.registry.tool_registry import ToolSpec, RiskLevel
from src.core.models import Task


def test_config():
    print("[1] Verifying config settings...")
    settings = get_settings()
    assert hasattr(settings, "hermes_enable_native_toolsets"), "Missing hermes_enable_native_toolsets in Settings"
    assert settings.hermes_enable_native_toolsets is True, "hermes_enable_native_toolsets should be True"
    for ts in ("file", "terminal", "skills", "web", "code_execution"):
        assert ts in settings.hermes_default_toolsets, f"Missing {ts} in hermes_default_toolsets"
    print("    [PASS] Config has native toolsets enabled with all default tools.")


def test_profiles_wanted_toolsets():
    print("[2] Verifying HermesProfiles.wanted_toolsets()...")
    settings = get_settings()
    profiles = HermesProfiles(settings, runner=lambda _: "")
    
    # Test dynamic profile toolset resolution
    dyn_name = f"{DYNAMIC_PROFILE_PREFIX}test1234"
    toolsets = profiles.wanted_toolsets(dyn_name, [])
    
    assert "terminal" in toolsets, "terminal toolset must be enabled for dynamic profiles"
    assert "file" in toolsets, "file toolset must be enabled for dynamic profiles"
    assert "skills" in toolsets, "skills toolset must be enabled for dynamic profiles"
    assert "code_execution" in toolsets, "code_execution must be enabled for dynamic profiles"
    print(f"    [PASS] Dynamic profile '{dyn_name}' acquired native toolsets: {toolsets}")


def test_profiles_config_external_dirs():
    print("[3] Verifying HermesProfiles.profile_config()...")
    settings = get_settings()
    profiles = HermesProfiles(settings, runner=lambda _: "")
    
    dyn_name = f"{DYNAMIC_PROFILE_PREFIX}test1234"
    cfg = profiles.profile_config(dyn_name, tools=["read_file", "write_file"])
    
    import json
    ext_dirs = json.loads(cfg["skills.external_dirs"])
    assert len(ext_dirs) >= 1, "skills.external_dirs must contain at least 1 directory"
    print(f"    [PASS] Profile config exposes external skills dirs: {ext_dirs}")


def test_match_skills_for_docs():
    print("[4] Verifying match_skills_for_task() on document/proposal tasks...")
    settings = get_settings()
    profiles = HermesProfiles(settings, runner=lambda _: "")
    
    matched = profiles.match_skills_for_task(
        tools=["read_file", "write_file"],
        skills=["document_creation"],
        task_name="Draft Technical Proposal",
        task_desc="Read RFP requirements from project_rfp.docx and write comprehensive proposal",
    )
    
    assert "docx" in matched, f"docx skill should be matched for proposal task, got: {matched}"
    print(f"    [PASS] Document task correctly matched docx skill: {matched}")


def test_sync_exact_task_skills_preserves_native():
    print("[5] Verifying sync_exact_task_skills preserves native Hermes skills...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_home = Path(tmp_dir) / "hermes"
        state = ProfileState(Path(tmp_dir) / "state.json")
        settings = get_settings()
        profiles = HermesProfiles(settings, runner=lambda _: "", state=state)
        profiles.home = tmp_home
        
        dyn_name = f"{DYNAMIC_PROFILE_PREFIX}keep_native"
        p_skills = profiles.profile_dir(dyn_name) / "skills"
        p_skills.mkdir(parents=True)
        
        # Create a native Hermes skill (e.g. docx) and a synthetic aiagent skill
        native_skill = p_skills / "docx"
        native_skill.mkdir()
        (native_skill / "SKILL.md").write_text("# Docx", encoding="utf-8")
        
        old_aiagent_skill = p_skills / "aiagent-old-tool"
        old_aiagent_skill.mkdir()
        (old_aiagent_skill / "SKILL.md").write_text("# Old", encoding="utf-8")
        
        # Call sync with matched having "docx"
        profiles.sync_exact_task_skills(dyn_name, tools=["read_file"], task_name="proposal", task_desc="docx")
        
        # Native skill must be preserved; obsolete aiagent-* skill must be purged
        assert native_skill.exists(), "Native docx skill must NOT be deleted"
        assert not old_aiagent_skill.exists(), "Obsolete synthetic aiagent skill should be cleaned up"
        print("    [PASS] Native docx skill preserved; obsolete aiagent skill cleaned up.")


def test_worker_prompt_liberation():
    print("[6] Verifying HermesAgentWorker prompts are liberated...")
    settings = get_settings()
    worker = HermesAgentWorker(settings=settings)
    
    # 1. Check review message doesn't ban skill_view
    review_msg = worker._review_message("missing sections", [
        ToolSpec(tool_id="t1", name="read_file", description="", parameters={}, function=lambda: "", risk_level=RiskLevel.LOW)
    ])
    assert "do not use skill_view" not in review_msg.lower(), "Review message must NOT forbid skill_view"
    
    # 2. Check user content informs agent of native tools & skills
    task = Task(id="task_1", name="Proposal Task", description="Write a proposal from docx")
    user_content = worker._user_content(
        task=task,
        tools=[ToolSpec(tool_id="t1", name="read_file", description="", parameters={}, function=lambda: "", risk_level=RiskLevel.LOW)],
        user_query="Create proposal",
        upstream_context=None,
    )
    assert "autonomous access to your native tools" in user_content.lower(), "User content must mention autonomous native tools access"
    print("    [PASS] Worker prompts allow native tools and do not forbid skill_view.")


def test_file_ops_docx_safety_net():
    print("[7] Verifying file_ops.read_file() docx safety net...")
    import asyncio
    from src.registry.tools.file_ops import read_file
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        docx_path = Path(tmp_dir) / "test_doc.docx"
        
        # Build minimal valid .docx zip file containing document.xml with text
        doc_xml = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body>'
            b'<w:p><w:r><w:t>Project Alpha RFP Requirements</w:t></w:r></w:p>'
            b'<w:p><w:r><w:t>Scope: Design autonomous agent workspace.</w:t></w:r></w:p>'
            b'</w:body>'
            b'</w:document>'
        )
        content_types_xml = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'</Types>'
        )
        with zipfile.ZipFile(docx_path, "w") as zf:
            zf.writestr("word/document.xml", doc_xml)
            zf.writestr("[Content_Types].xml", content_types_xml)
            
        result = asyncio.run(read_file(str(docx_path)))
        assert "Project Alpha RFP Requirements" in result, f"Failed to extract docx text: {result}"
        assert "Scope: Design autonomous agent workspace" in result, f"Failed to extract docx text: {result}"
        print(f"    [PASS] read_file successfully extracted text from .docx: '{result.strip()}'")


if __name__ == "__main__":
    print("\n========================================================")
    print("  RUNNING HERMES NATIVE INTEGRATION VERIFICATION SUITE  ")
    print("========================================================\n")
    test_config()
    test_profiles_wanted_toolsets()
    test_profiles_config_external_dirs()
    test_match_skills_for_docs()
    test_sync_exact_task_skills_preserves_native()
    test_worker_prompt_liberation()
    test_file_ops_docx_safety_net()
    print("\n========================================================")
    print("  ALL 7 VERIFICATION CHECKS PASSED PERFECTLY!           ")
    print("========================================================\n")
