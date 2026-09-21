"""
Phase 0 charter enforcement (F5 anti-overfit audit).

These tests mechanically enforce the anti-overfit / no-fabrication charter so that
compliance does not depend on reviewer memory. They scan the shipped source tree
(`src/`), the shipped data tree (`data/`) and the unit-test fixtures for artifacts
copied out of the evaluation cases.

The forbidden literals below are deliberately kept in THIS FILE ONLY. This module
is the audit, not shipped logic, so the values living here are not a charter
violation - but nothing under `src/` or `data/` may contain them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
DATA = ROOT / "data"
TESTS = ROOT / "tests"

# --------------------------------------------------------------------------
# R1 - benchmark artifacts must never appear in shipped code or data
# --------------------------------------------------------------------------

FORBIDDEN_IPS = [
    "13.107.136.9",
    "185.220.101.45",
    "185.220.101.5",
    "198.51.100.240",
    "198.51.100.25",
    "198.51.100.30",
    "198.51.100.77",
    "203.0.113.119",
    "102.164.12.89",
    "185.196.220.14",
    "194.165.16.104",
    "194.26.29.110",
]

FORBIDDEN_IP_PREFIXES = ["172.56.21.", "10.200.1.", "10.20.10."]

FORBIDDEN_HOSTNAMES = [
    "WKSTN-FIN-04",
    "DC01",
    "corp.contoso.com",
]

FORBIDDEN_ACCOUNTS = [
    "jdoe",
    "da_admin",
    "svc_backup_admin",
    "david.clark",
    "john.doe",
    "alice.wang",
    "charlie.brown",
    "sarah.jenkins",
    "cfo.executive",
    "senior.engineer",
    "marketing.lead",
    "mjones",
]

FORBIDDEN_FILENAMES = [
    "Invoice_90214.docm",
    "stage2.dll",
    "cobalt.ps1",
    "PSEXESVC",
]

# Benchmark directory and ground-truth references (R9)
FORBIDDEN_PATH_TOKENS = ["Security-logs-test", "case1_ground_truth", "case3_ground_truth"]

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".js", ".html", ".css", ".txt"}

# Data files that legitimately hold evaluation input rather than shipped logic.
DATA_EXEMPT_DIRS = {"evidence", "ground_truth"}
DATA_EXEMPT_FILE_PREFIXES = ("case",)


def _iter_text_files(root: Path, skip_dirs: set[str] = frozenset()) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        parts = set(p.relative_to(root).parts)
        if parts & {"__pycache__", ".pytest_cache", "node_modules"}:
            continue
        if parts & skip_dirs:
            continue
        out.append(p)
    return out


def _shipped_data_files() -> list[Path]:
    files = _iter_text_files(DATA, skip_dirs=DATA_EXEMPT_DIRS)
    return [f for f in files if not f.name.lower().startswith(DATA_EXEMPT_FILE_PREFIXES)]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _find_literals(files: list[Path], literals: list[str], word_boundary: bool) -> list[str]:
    hits: list[str] = []
    for path in files:
        text = _read(path)
        for literal in literals:
            if word_boundary:
                pattern = r"(?<![A-Za-z0-9_.\-])" + re.escape(literal) + r"(?![A-Za-z0-9_.\-])"
                found = re.search(pattern, text) is not None
            else:
                found = literal in text
            if found:
                hits.append(f"{path.relative_to(ROOT)}: {literal}")
    return hits


@pytest.mark.parametrize(
    "literals,word_boundary,rule",
    [
        (FORBIDDEN_IPS, True, "R1 case IP address"),
        (FORBIDDEN_IP_PREFIXES, False, "R1 case IP range"),
        (FORBIDDEN_HOSTNAMES, True, "R1 case hostname"),
        (FORBIDDEN_ACCOUNTS, True, "R1 case account"),
        (FORBIDDEN_FILENAMES, True, "R1 case filename"),
        (FORBIDDEN_PATH_TOKENS, False, "R1/R9 benchmark path"),
    ],
)
def test_no_benchmark_literals_in_shipped_source(literals, word_boundary, rule):
    """R1: no evaluation-case artifact may appear anywhere under src/."""
    hits = _find_literals(_iter_text_files(SRC), literals, word_boundary)
    assert not hits, f"{rule} leaked into src/:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    "literals,word_boundary,rule",
    [
        (FORBIDDEN_IPS, True, "R1 case IP address"),
        (FORBIDDEN_IP_PREFIXES, False, "R1 case IP range"),
        (FORBIDDEN_HOSTNAMES, True, "R1 case hostname"),
        (FORBIDDEN_ACCOUNTS, True, "R1 case account"),
        (FORBIDDEN_FILENAMES, True, "R1 case filename"),
    ],
)
def test_no_benchmark_literals_in_shipped_data(literals, word_boundary, rule):
    """R1/R2: detection data files must be vendor-generic, never case-tuned."""
    hits = _find_literals(_shipped_data_files(), literals, word_boundary)
    assert not hits, f"{rule} leaked into data/:\n" + "\n".join(hits)


# --------------------------------------------------------------------------
# R2 - detection data must be rule-shaped, not literal-shaped
# --------------------------------------------------------------------------

IPV4 = re.compile(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])")


def test_benign_baseline_contains_no_address_literals():
    """R2: benign_services.yaml must describe SHAPES, never specific addresses."""
    path = DATA / "baselines" / "benign_services.yaml"
    assert path.exists(), "benign_services.yaml is required by the charter"
    found = IPV4.findall(_read(path))
    assert not found, f"benign_services.yaml must contain no IP literals, found: {found}"


def test_detection_data_files_contain_no_address_literals():
    """R2: signatures, rubrics and baselines are generic rules, not addresses."""
    offenders: list[str] = []
    for sub in ("baselines", "mitre", "log_mappings"):
        for path in _iter_text_files(DATA / sub):
            found = IPV4.findall(_read(path))
            if found:
                offenders.append(f"{path.relative_to(ROOT)}: {sorted(set(found))}")
    assert not offenders, "Detection data must not contain IP literals:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------
# R7 - persona and skill prompt content must be methodology, not case content
# --------------------------------------------------------------------------


def test_methodology_skills_are_case_free():
    """R7: hermes skills teach HOW to investigate; they carry no case artifacts."""
    skills_dir = DATA / "hermes_skills"
    methodology = [
        "forensic_grounding.md",
        "mitre_attack_mapping.md",
        "identity_attack_patterns.md",
        "network_anomaly_analysis.md",
        "lolbin_detection.md",
        "benign_baseline_patterns.md",
    ]
    missing = [n for n in methodology if not (skills_dir / n).exists()]
    assert not missing, f"Missing methodology skills: {missing}"

    offenders: list[str] = []
    for name in methodology:
        text = _read(skills_dir / name)
        found_ips = IPV4.findall(text)
        if found_ips:
            offenders.append(f"{name}: IP literals {sorted(set(found_ips))}")
        for literal in FORBIDDEN_ACCOUNTS + FORBIDDEN_HOSTNAMES + FORBIDDEN_FILENAMES:
            if re.search(r"(?<![A-Za-z0-9_.\-])" + re.escape(literal) + r"(?![A-Za-z0-9_.\-])", text):
                offenders.append(f"{name}: case artifact {literal!r}")
    assert not offenders, "R7 violation in methodology skills:\n" + "\n".join(offenders)


def test_soc_persona_carries_grounding_contract():
    """R7/C1: the SOC persona must state the citation and no-fabrication rules."""
    import json

    agent = json.loads(_read(DATA / "agents" / "soc-investigator.json"))
    prompt = agent["system_prompt_template"]

    for required in ("[EV:", "UNVERIFIED", "Remediation", "benign"):
        assert required in prompt, f"SOC persona prompt is missing {required!r}"

    for placeholder in ("{task_name}", "{task_description}", "{expected_output}", "{tools}"):
        assert placeholder in prompt, f"SOC persona prompt lost placeholder {placeholder}"

    found_ips = IPV4.findall(prompt)
    assert not found_ips, f"SOC persona prompt must not name addresses: {found_ips}"


# --------------------------------------------------------------------------
# R9 - nothing that produces a report may read the ground truth
# --------------------------------------------------------------------------


def test_no_source_module_reads_ground_truth():
    """R9: ground-truth files are scoring input only, never analysis input."""
    offenders: list[str] = []
    pattern = re.compile(r"ground_truth|Security-logs-test", re.IGNORECASE)
    for path in _iter_text_files(SRC):
        if pattern.search(_read(path)):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, "src/ must never reference ground truth or the benchmark dir:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------
# R8 - unit-test fixtures must be synthetic and independently authored
# --------------------------------------------------------------------------


def test_unit_fixtures_do_not_reuse_case_data():
    """R8: unit tests exercise pattern classes with their own synthetic data."""
    unit_files = [p for p in _iter_text_files(TESTS / "unit") if p.name != Path(__file__).name]
    literals = FORBIDDEN_IPS + FORBIDDEN_HOSTNAMES + FORBIDDEN_ACCOUNTS + FORBIDDEN_FILENAMES
    hits = _find_literals(unit_files, literals, word_boundary=True)
    hits += _find_literals(unit_files, FORBIDDEN_IP_PREFIXES, word_boundary=False)
    assert not hits, "Unit fixtures must not reuse evaluation-case data:\n" + "\n".join(hits)


# --------------------------------------------------------------------------
# R4 - detection thresholds live in config, not as literals inside analytics
# --------------------------------------------------------------------------

ANALYTICS_MODULES = [
    SRC / "registry" / "tools" / "identity_analytics.py",
    SRC / "registry" / "tools" / "network_analytics.py",
    SRC / "registry" / "tools" / "attack_analytics.py",
]

# Values that are structural rather than tunable detection thresholds.
ALLOWED_NUMERIC_LITERALS = {0, 1, 2, 3, 100, 1000, 60, 3600, 24, 2.0, 0.0, 1.0, 0.5}


def _threshold_literals(module: Path) -> list[str]:
    """Find comparison literals that look like tunable detection thresholds."""
    tree = ast.parse(_read(module))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left, *node.comparators]:
            if not isinstance(operand, ast.Constant):
                continue
            value = operand.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if value in ALLOWED_NUMERIC_LITERALS:
                continue
            offenders.append(f"{module.name}:{operand.lineno} compares against {value!r}")
    return offenders


def test_analytics_thresholds_come_from_config():
    """R4: thresholds are named settings with documented defaults, not magic numbers."""
    offenders: list[str] = []
    for module in ANALYTICS_MODULES:
        assert module.exists(), f"Expected analytics module missing: {module}"
        offenders.extend(_threshold_literals(module))
    assert not offenders, (
        "Detection thresholds must be sourced from config (get_settings()), not inlined:\n"
        + "\n".join(offenders)
    )


def test_analytics_tuning_is_externalized():
    """R4: tuning comes from config settings or declarative data files, never inline."""
    data_driven_markers = ("get_settings", "load_baseline", "_load_mitre")
    for module in ANALYTICS_MODULES:
        text = _read(module)
        assert any(marker in text for marker in data_driven_markers), (
            f"{module.name} externalizes no tuning; thresholds and signatures must come "
            f"from config or a data file"
        )


# --------------------------------------------------------------------------
# R5 - analytics operate on EvidenceEvent fields, not vendor line formats
# --------------------------------------------------------------------------


def test_analytics_are_source_agnostic():
    """R5: a new log source must work via a YAML mapping alone."""
    vendor_tokens = ["palo alto", "cisco asa", "sysmon", "azure ad", "%ASA-", "evtx"]
    offenders: list[str] = []
    for module in ANALYTICS_MODULES:
        lowered = _read(module).lower()
        for token in vendor_tokens:
            if token.lower() in lowered:
                offenders.append(f"{module.name}: vendor-specific token {token!r}")
    assert not offenders, (
        "Analytics must consume normalized EvidenceEvent fields, not vendor formats:\n"
        + "\n".join(offenders)
    )


def test_new_log_source_needs_only_a_mapping():
    """R5: ingestion formats are config; adding one must not require code edits."""
    mappings = list((DATA / "log_mappings").glob("*.yaml"))
    assert len(mappings) >= 5, "Expected a library of declarative log mappings"

    ingestion = _read(SRC / "registry" / "ingestion.py")
    for mapping in mappings:
        stem = mapping.stem
        assert stem not in ingestion, (
            f"ingestion.py hardcodes mapping {stem!r}; mappings must be discovered from data/"
        )


# --------------------------------------------------------------------------
# R3 - no synthetic or placeholder findings presented as results
# --------------------------------------------------------------------------


def test_tools_do_not_fabricate_success():
    """R3: unimplemented capabilities must say so, not emit a plausible result."""
    fabrications = [
        "executed goal constraints",
        "verified outputs",
        "returned final artifact cleanly",
        "Suspected External C2",
    ]
    hits = _find_literals(_iter_text_files(SRC), fabrications, word_boundary=False)
    assert not hits, "Tools must not fabricate successful results:\n" + "\n".join(hits)
