"""
Unit tests for TaskDAG:
- Topological sort (linear, diamond, parallel, multi-root)
- Cycle detection and dependency validation
- Ready task resolution
- Serialization and deserialization roundtrips
- Estimated completion time calculations
"""

import pytest
from src.core.models import Task, TaskDAG, RiskLevel


def _make_task(task_id: str, name: str, dependencies: list[str] | None = None) -> Task:
    return Task(
        id=task_id,
        name=name,
        description=f"Description for {name}",
        required_skills=["general_reasoning"],
        dependencies=dependencies or [],
        risk_level=RiskLevel.LOW,
    )


class TestTaskDAGValidation:
    def test_valid_linear_dag(self):
        t1 = _make_task("t1", "Fetch Data")
        t2 = _make_task("t2", "Process Data", dependencies=["t1"])
        t3 = _make_task("t3", "Report Results", dependencies=["t2"])

        dag = TaskDAG(
            goal="Process data sequentially",
            reasoning="Linear pipeline required",
            tasks=[t1, t2, t3],
        )

        dag.validate_integrity()  # Should not raise
        assert len(dag.tasks) == 3
        assert dag.estimated_completion_seconds == 60

    def test_missing_dependency_raises_error(self):
        t1 = _make_task("t1", "Task 1", dependencies=["nonexistent_task"])
        dag = TaskDAG(
            goal="Faulty plan",
            reasoning="Missing dependency",
            tasks=[t1],
        )

        with pytest.raises(ValueError, match="depends on unknown task"):
            dag.validate_integrity()

    def test_cycle_detection_raises_error(self):
        t1 = _make_task("t1", "Task 1", dependencies=["t2"])
        t2 = _make_task("t2", "Task 2", dependencies=["t1"])
        dag = TaskDAG(
            goal="Cyclic plan",
            reasoning="Circular dependency",
            tasks=[t1, t2],
        )

        with pytest.raises(ValueError, match="Circular dependency detected"):
            dag.validate_integrity()


class TestTaskDAGTopologicalSort:
    def test_empty_dag(self):
        dag = TaskDAG(goal="Empty", reasoning="None", tasks=[])
        assert dag.topological_sort() == []

    def test_single_task(self):
        t1 = _make_task("t1", "Only Task")
        dag = TaskDAG(goal="Single", reasoning="None", tasks=[t1])
        order = dag.topological_sort()
        assert [t.id for t in order] == ["t1"]

    def test_linear_dependency_order(self):
        t1 = _make_task("t1", "Step 1")
        t2 = _make_task("t2", "Step 2", dependencies=["t1"])
        t3 = _make_task("t3", "Step 3", dependencies=["t2"])

        # Intentionally pass tasks in reverse order
        dag = TaskDAG(
            goal="Pipeline",
            reasoning="Linear",
            tasks=[t3, t1, t2],
        )

        order = dag.topological_sort()
        ids = [t.id for t in order]
        assert ids == ["t1", "t2", "t3"]

    def test_diamond_dag_ordering(self):
        #      t1
        #     /  \
        #   t2    t3
        #     \  /
        #      t4
        t1 = _make_task("t1", "Start")
        t2 = _make_task("t2", "Branch A", dependencies=["t1"])
        t3 = _make_task("t3", "Branch B", dependencies=["t1"])
        t4 = _make_task("t4", "Join", dependencies=["t2", "t3"])

        dag = TaskDAG(
            goal="Diamond graph",
            reasoning="Parallel branches with join",
            tasks=[t4, t2, t3, t1],
        )

        order = dag.topological_sort()
        ids = [t.id for t in order]

        # t1 must be first, t4 must be last
        assert ids[0] == "t1"
        assert ids[-1] == "t4"
        # t2 and t3 must be before t4 and after t1
        assert ids.index("t2") < ids.index("t4")
        assert ids.index("t3") < ids.index("t4")
        assert ids.index("t1") < ids.index("t2")
        assert ids.index("t1") < ids.index("t3")

    def test_multi_root_parallel_tasks(self):
        t1 = _make_task("t1", "Root A")
        t2 = _make_task("t2", "Root B")
        t3 = _make_task("t3", "Dependent on both", dependencies=["t1", "t2"])

        dag = TaskDAG(
            goal="Multi-root",
            reasoning="Two roots",
            tasks=[t3, t1, t2],
        )

        order = dag.topological_sort()
        ids = [t.id for t in order]
        assert ids[-1] == "t3"
        assert set(ids[:2]) == {"t1", "t2"}

    def test_topological_sort_graceful_on_cycle(self):
        # Even if cycle exists, topological_sort must return all tasks without hanging
        t1 = _make_task("t1", "A", dependencies=["t2"])
        t2 = _make_task("t2", "B", dependencies=["t1"])
        dag = TaskDAG(goal="Cyclic fallback", reasoning="Cycle", tasks=[t1, t2])

        order = dag.topological_sort()
        assert len(order) == 2
        assert {t.id for t in order} == {"t1", "t2"}


class TestTaskDAGReadyTasks:
    def test_get_ready_tasks_initial(self):
        t1 = _make_task("t1", "Task 1")
        t2 = _make_task("t2", "Task 2", dependencies=["t1"])
        dag = TaskDAG(goal="Goal", reasoning="Reason", tasks=[t1, t2])

        ready = dag.get_ready_tasks(completed=set(), failed=set())
        assert [t.id for t in ready] == ["t1"]

    def test_get_ready_tasks_after_completion(self):
        t1 = _make_task("t1", "Task 1")
        t2 = _make_task("t2", "Task 2", dependencies=["t1"])
        dag = TaskDAG(goal="Goal", reasoning="Reason", tasks=[t1, t2])

        ready = dag.get_ready_tasks(completed={"t1"}, failed=set())
        assert [t.id for t in ready] == ["t2"]

    def test_get_ready_tasks_all_resolved(self):
        t1 = _make_task("t1", "Task 1")
        t2 = _make_task("t2", "Task 2", dependencies=["t1"])
        dag = TaskDAG(goal="Goal", reasoning="Reason", tasks=[t1, t2])

        ready = dag.get_ready_tasks(completed={"t1", "t2"}, failed=set())
        assert ready == []


class TestTaskDAGSerialization:
    def test_roundtrip_serialization(self):
        t1 = _make_task("t1", "Task 1")
        t2 = _make_task("t2", "Task 2", dependencies=["t1"])
        dag = TaskDAG(
            goal="Serialize me",
            reasoning="Ensure fidelity",
            tasks=[t1, t2],
            estimated_completion_seconds=45,
        )

        serialized = dag.to_serializable()
        assert isinstance(serialized, dict)
        assert serialized["goal"] == "Serialize me"
        assert serialized["estimated_completion_seconds"] == 45
        assert len(serialized["tasks"]) == 2

        reconstructed = TaskDAG.from_serializable(serialized)
        assert reconstructed.goal == dag.goal
        assert reconstructed.reasoning == dag.reasoning
        assert reconstructed.estimated_completion_seconds == 45
        assert len(reconstructed.tasks) == 2
        assert reconstructed.tasks[1].dependencies == ["t1"]

    def test_get_task_by_id(self):
        t1 = _make_task("t1", "Task 1")
        t2 = _make_task("t2", "Task 2")
        dag = TaskDAG(goal="Lookup", reasoning="Find", tasks=[t1, t2])

        assert dag.get_task_by_id("t1") == t1
        assert dag.get_task_by_id("t2") == t2
        assert dag.get_task_by_id("nonexistent") is None
