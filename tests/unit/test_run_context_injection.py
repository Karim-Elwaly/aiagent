"""Unit tests for hidden run-context injection into tools (Phase A2).

The run id must reach evidence-store tools without ever being visible to the
LLM: an agent that can name a run id can point a tool at another run's
evidence, and a model that sees the parameter will try to invent values for it.
"""

from __future__ import annotations

import pytest

from src.core.models import RiskLevel, Task
from src.registry.tool_registry import ToolSpec
from src.workers.universal_worker import UniversalWorkerAgent


@pytest.fixture()
def worker():
    return UniversalWorkerAgent(llm=None, run_id="wf-alpha-123")


def _spec(needs_run_context: bool) -> ToolSpec:
    async def _fn(**kwargs):
        return "ok"

    return ToolSpec(
        tool_id="probe_v1",
        name="probe",
        description="Test probe.",
        skills_provided=["probing"],
        parameters={"target": {"type": "string", "description": "Target."}},
        function=_fn,
        risk_level=RiskLevel.LOW,
        needs_run_context=needs_run_context,
    )


class TestInjection:
    def test_injected_when_declared(self, worker):
        args = worker._inject_run_context(_spec(True), {"target": "x"})

        assert args["_run_id"] == "wf-alpha-123"
        assert args["target"] == "x"

    def test_not_injected_when_not_declared(self, worker):
        args = worker._inject_run_context(_spec(False), {"target": "x"})

        assert "_run_id" not in args

    def test_model_supplied_run_id_is_overwritten(self, worker):
        """A hallucinated run id must never win over the real one."""
        args = worker._inject_run_context(_spec(True), {"_run_id": "attacker-run"})

        assert args["_run_id"] == "wf-alpha-123"

    def test_original_args_not_mutated(self, worker):
        original = {"target": "x"}
        worker._inject_run_context(_spec(True), original)

        assert "_run_id" not in original

    def test_missing_spec_is_passthrough(self, worker):
        assert worker._inject_run_context(None, {"target": "x"}) == {"target": "x"}


class TestSchemaIsolation:
    def test_run_id_absent_from_llm_schema(self, worker):
        """The hidden parameter must not appear in the OpenAI function schema."""
        schema = worker._convert_tools_to_openai([_spec(True)])

        params = schema[0]["function"]["parameters"]
        assert "_run_id" not in params["properties"]
        assert "_run_id" not in params.get("required", [])

    def test_declared_params_still_exposed(self, worker):
        schema = worker._convert_tools_to_openai([_spec(True)])

        assert "target" in schema[0]["function"]["parameters"]["properties"]


class TestEnrichmentInteraction:
    def test_enrichment_does_not_add_run_id(self, worker):
        """_enrich_tool_args only fills schema keys; _run_id is not one of them."""
        enriched = worker._enrich_tool_args(
            _spec(True),
            {"target": "x"},
            Task(id="t1", name="probe", description="probe", required_skills=["probing"]),
            "run a probe",
            None,
            "",
        )

        assert "_run_id" not in enriched


class TestDefaults:
    def test_default_run_id_is_empty(self):
        assert UniversalWorkerAgent(llm=None).run_id == ""
