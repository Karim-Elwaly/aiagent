"""End-to-End Architectural Verification Test Suite for Fleet Studio & aiagent.

Run with: python verify_backend.py
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path

backend_dir = os.path.abspath("backend")
daemon_dir = os.path.abspath("agents/fleetctl_daemon")
sys.path.insert(0, backend_dir)
sys.path.insert(0, daemon_dir)

from app.api.v1.router import router
from app.schemas.domain import (
    AvailableModel,
    ClarifyingQuestion,
    FleetProposal,
    HermesEstateInventory,
    InstalledSkill,
    Mission,
    MissionConstraints,
    RegisteredTool,
    RiskLevel,
)
from app.services.architect_pipeline import clarifying_questions, propose_fleet
from app.services.clarification_generator import generate_clarifying_questions
from hermes_profile_materializer import HermesProfileMaterializer


async def verify():
    print("1. Verifying ClarifyingQuestion schema...")
    q = ClarifyingQuestion(
        question_id="remediation-posture",
        prompt="What is the containment posture?",
        category="governance",
        options=["Advisory Only", "Quarantine"],
        default_answer="Advisory Only",
    )
    assert q.default_answer in q.options
    print("   Schema check PASSED.")

    print("2. Verifying Clarification Generator for K8s mission...")
    m_k8s = Mission(
        name="K8s Breakout",
        goal="Investigate pod container breakout and rootkit",
        constraints=MissionConstraints(task_complexity=4),
        competitive_benchmarking=True,
    )
    qs = await generate_clarifying_questions(m_k8s)
    assert len(qs) >= 3
    print(f"   Generated {len(qs)} domain questions (PASSED).")

    print("3. Verifying Dynamic Fleet Composer...")
    inv = HermesEstateInventory(connected=False)
    proposal = await propose_fleet(m_k8s, inv)
    assert len(proposal.agents) == 5
    for a in proposal.agents:
        assert a.assigned_llm is not None
    print(f"   Composed {len(proposal.agents)} dynamic stages (PASSED).")

    print("4. Verifying Hermes Profile Materializer...")
    test_home = Path("scratch/test_hermes").resolve()
    mat = HermesProfileMaterializer(custom_home=str(test_home), max_profiles=5)
    res = mat.materialize_blueprint(proposal.model_dump(mode="json"))
    assert res["materialized"] == 5
    shutil.rmtree(test_home, ignore_errors=True)
    print(f"   Materialized {res['materialized']} host profiles (PASSED).")

    print("\nALL VERIFICATION CHECKS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(verify())
