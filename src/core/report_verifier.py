"""
UAOS Report Verifier

The last line of defence against fabrication.

An investigation report is only worth what its evidence supports. This module
takes a finished report and mechanically checks every concrete claim in it
against the run's evidence store:

  * **Entity grounding** — every IP address, file hash and account named in the
    report must appear somewhere in the ingested evidence.
  * **Citation coverage** — statements asserting a fact should carry an
    ``EV-xxxxxx`` citation. Coverage below a threshold means the report is
    narrative rather than evidential.
  * **Remediation grounding** — this one is a HARD FAIL. Containment and
    remediation sections contain commands an operator may actually run. An
    invented hostname or IP address in that section is not a wording problem, it
    is an instruction to act on a machine that was never implicated.

The verifier never rewrites a conclusion. It annotates unverifiable claims and
reports a verdict, so a human sees exactly which statements the data supports.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.core.evidence import EVIDENCE_ID_PATTERN, EvidenceStore, get_store

logger = logging.getLogger(__name__)

IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)
HASH = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")

# Headings that introduce actionable instructions rather than analysis.
REMEDIATION_HEADING = re.compile(
    r"^#{1,6}\s*.*\b("
    r"containment|remediation|response|eradication|mitigation|recovery|"
    r"action plan|next steps|playbook|hardening"
    r")\b.*$",
    re.IGNORECASE,
)

# Sentences that assert a fact are the ones that need a citation. Purely
# structural lines (headings, table rules, bullets with no verb) are exempt.
_MIN_CLAIM_CHARS = 40

# Version-like dotted numbers and similar constructs that are not addresses.
_NOT_AN_IP_CONTEXT = re.compile(r"(?:v|version\s*)\d", re.IGNORECASE)

# LLMs routinely emit typographic dashes (non-breaking hyphen, en/em dash,
# minus sign) inside identifiers such as citation ids or addresses. Those are
# semantically plain hyphens; left unnormalized they make every citation
# invisible to the ASCII pattern and produce false "0 citations" verdicts.
# Only dashes BETWEEN word characters are normalized — prose punctuation
# ("text — more text") is left untouched.
_IDENTIFIER_DASH = re.compile("(?<=\\w)[\u2010\u2011\u2012\u2013\u2014\u2015\u2212](?=\\w)")


def _normalize_typography(text: str) -> str:
    return _IDENTIFIER_DASH.sub("-", text)


@dataclass
class Issue:
    """One verification problem found in the report."""

    kind: str
    severity: str  # "fail" | "warn"
    value: str
    detail: str
    line_no: int = 0

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "value": self.value,
            "detail": self.detail,
            "line": self.line_no,
        }


@dataclass
class VerificationResult:
    """Outcome of verifying a report against the evidence store."""

    verdict: str = "pass"  # "pass" | "warn" | "fail"
    issues: list[Issue] = field(default_factory=list)
    annotated_report: str = ""
    evidence_events: int = 0
    citations_found: int = 0
    invalid_citations: list[str] = field(default_factory=list)
    claim_sentences: int = 0
    cited_claim_sentences: int = 0

    @property
    def citation_coverage(self) -> float:
        if not self.claim_sentences:
            return 1.0
        return self.cited_claim_sentences / self.claim_sentences

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "evidence_events": self.evidence_events,
            "citations_found": self.citations_found,
            "invalid_citations": self.invalid_citations,
            "claim_sentences": self.claim_sentences,
            "cited_claim_sentences": self.cited_claim_sentences,
            "citation_coverage": round(self.citation_coverage, 3),
            "issues": [i.as_dict() for i in self.issues],
        }

    def summary_table(self) -> str:
        """A compact markdown summary suitable for appending to the report."""
        rows = [
            "| Check | Result |",
            "| :--- | :--- |",
            f"| Verdict | **{self.verdict.upper()}** |",
            f"| Evidence events available | {self.evidence_events} |",
            f"| Citations in report | {self.citations_found} |",
            f"| Invalid citations | {len(self.invalid_citations)} |",
            f"| Citation coverage | {self.citation_coverage:.0%} |",
            f"| Issues | {len(self.issues)} |",
        ]
        if self.issues:
            rows.append("")
            rows.append("| Severity | Issue | Value |")
            rows.append("| :--- | :--- | :--- |")
            for issue in self.issues[:40]:
                rows.append(f"| {issue.severity.upper()} | {issue.kind} | `{issue.value}` |")
        return "\n".join(rows)


def verify_report(
    report: str,
    run_id: str = "",
    *,
    store: EvidenceStore | None = None,
    min_citation_coverage: float = 0.5,
) -> VerificationResult:
    """Check a report's concrete claims against the run's evidence.

    Args:
        report: The assembled report text.
        run_id: Investigation run id used to locate the evidence store.
        store: Optional pre-built store (used by tests).
        min_citation_coverage: Fraction of factual sentences that must carry a
            citation before the report is considered evidential.

    Returns:
        A ``VerificationResult`` carrying the verdict, the issue list and an
        annotated copy of the report.
    """
    result = VerificationResult(annotated_report=report)
    if not report or not report.strip():
        result.verdict = "fail"
        result.issues.append(
            Issue("empty_report", "fail", "", "The report is empty; nothing to verify.")
        )
        return result

    # Normalize typographic dashes inside identifiers so citations and
    # addresses emitted with non-ASCII hyphens still verify. The normalized
    # text also becomes the annotated output — plain hyphens in identifiers
    # are strictly more usable downstream.
    report = _normalize_typography(report)
    result.annotated_report = report

    evidence = store or get_store(run_id)
    result.evidence_events = evidence.count()

    if result.evidence_events == 0:
        # Without evidence, no concrete claim in the report can be substantiated.
        result.verdict = "fail"
        result.issues.append(
            Issue(
                "no_evidence",
                "fail",
                "",
                "The evidence store is empty, so no claim in this report is "
                "substantiated. Ingest the logs and re-run the investigation.",
            )
        )
        return result

    known = _known_entities(evidence)
    valid_ids = {e.ev_id for e in evidence.iter_events() if e.ev_id}

    _check_citations(report, valid_ids, result)
    remediation_lines = _remediation_line_numbers(report)
    _check_entities(report, known, remediation_lines, result)
    _check_citation_consistency(report, evidence, result)
    _check_coverage(report, min_citation_coverage, result)

    result.annotated_report = _annotate(report, result)
    result.verdict = _verdict(result)
    return result


# ── Individual checks ────────────────────────────────────


def _known_entities(store: EvidenceStore) -> dict[str, Any]:
    """Collect every entity literal the evidence actually contains."""
    ips: set[str] = set()
    hashes: set[str] = set()
    accounts: set[str] = set()
    hosts: set[str] = set()
    processes: set[str] = set()
    corpus_parts: list[str] = []

    for event in store.iter_events():
        for value in (event.src_ip, event.dst_ip):
            if value:
                ips.add(value)
        for value in event.hashes.values():
            if value:
                hashes.add(value.lower())
        if event.user:
            accounts.add(event.user.lower())
        if event.host:
            hosts.add(event.host.lower())
        for value in (event.process, event.parent_process):
            if value:
                lowered = value.lower()
                processes.add(lowered)
                # Also index the basename: evidence stores full paths while
                # reports name the binary.
                base = lowered.replace("\\", "/").rsplit("/", 1)[-1]
                if base:
                    processes.add(base)
        # Raw text is authoritative too: an address mentioned inside a log line
        # is genuinely present in the source data even if no field captured it.
        raw = event.raw_excerpt or ""
        for match in IPV4.findall(raw):
            ips.add(match)
        for match in HASH.findall(raw):
            hashes.add(match.lower())
        if raw:
            corpus_parts.append(raw.lower())
        if event.command_line:
            corpus_parts.append(event.command_line.lower())

    return {
        "ips": ips,
        "hashes": hashes,
        "accounts": accounts,
        "hosts": hosts,
        "processes": processes,
        "corpus": "\n".join(corpus_parts),
    }


def _check_citations(report: str, valid_ids: set[str], result: VerificationResult) -> None:
    cited = EVIDENCE_ID_PATTERN.findall(report)
    result.citations_found = len(cited)
    for ev_id in sorted(set(cited)):
        if ev_id not in valid_ids:
            result.invalid_citations.append(ev_id)
            result.issues.append(
                Issue(
                    "invalid_citation",
                    "fail",
                    ev_id,
                    f"Citation {ev_id} does not exist in the evidence store. "
                    "A fabricated citation is worse than none.",
                )
            )


def _remediation_line_numbers(report: str) -> set[int]:
    """Line numbers that fall inside a containment/remediation section."""
    lines = report.splitlines()
    inside = False
    current_depth = 0
    flagged: set[int] = set()

    for index, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s", line)
        if heading:
            depth = len(heading.group(1))
            if REMEDIATION_HEADING.match(line):
                inside = True
                current_depth = depth
                continue
            # A heading at the same or shallower level ends the section.
            if inside and depth <= current_depth:
                inside = False
        if inside:
            flagged.add(index)

    return flagged


def _entity_name_forms(value: str) -> set[str]:
    """Lowercased comparable forms of an account or host name.

    Reports legitimately qualify names the evidence stores bare —
    ``DOMAIN\\user``, ``user@realm``, or a fully-qualified hostname where the
    evidence holds the short name (or vice versa). All of these refer to the
    same principal; flagging them as ungrounded would be a false accusation.
    """
    lowered = value.strip().lower()
    forms = {lowered}
    # DOMAIN\name  ->  name
    if "\\" in lowered:
        forms.add(lowered.rsplit("\\", 1)[-1])
    # name@realm  ->  name
    if "@" in lowered:
        forms.add(lowered.split("@", 1)[0])
    # fqdn -> first DNS label (only when it looks like a hostname, not a filename)
    if "." in lowered and "\\" not in lowered and "/" not in lowered:
        forms.add(lowered.split(".", 1)[0])
    return {f for f in forms if f}


# Structural address literals used by firewall/routing syntax (any-address
# masks, broadcast). They denote scope in a command, not a target system, so
# grounding them against the evidence is a category error.
_WILDCARD_IPS = {"0.0.0.0", "255.255.255.255"}

# The pipeline's own containment action vocabulary (propose_containment_response
# action types). Reports legitimately quote these tokens in action columns;
# they are verbs, not entities.
_ACTION_VOCABULARY = {
    "block_ip",
    "isolate_endpoint",
    "revoke_tokens",
    "quarantine_file",
    "disable_account",
    "reset_password",
    "block_domain",
    "kill_process",
}


def _is_known_principal(value: str, known: dict[str, Any]) -> bool:
    """True when any comparable form of the value matches a known entity."""
    candidate_forms = _entity_name_forms(value)
    for pool_name in ("accounts", "hosts", "processes"):
        for entity in known.get(pool_name) or set():
            if _entity_name_forms(entity) & candidate_forms:
                return True
    # Raw text is authoritative: a file or binary named verbatim inside an
    # ingested log line is genuinely present in the source data even when no
    # structured field captured it (e.g. a binary inside a command line).
    lowered = value.strip().lower()
    if len(lowered) >= 4 and lowered in (known.get("corpus") or ""):
        return True
    return False


def _contains_grounded_entity(value: str, known: dict[str, Any]) -> bool:
    """True when the identifier embeds an entity the evidence contains.

    Reports synthesize labels around grounded entities — firewall rule names
    like ``Block-<addr>`` or ``Isolate-<host>``. The label is derived from the
    evidence, not a claim about a new system, so it must not be flagged.
    """
    lowered = value.lower()
    for ip in known["ips"]:
        if ip and ip in lowered:
            return True
    for pool_name in ("accounts", "hosts", "processes"):
        for entity in known.get(pool_name) or set():
            for form in _entity_name_forms(entity):
                if len(form) >= 4 and form in lowered:
                    return True
    return False


def _check_entities(
    report: str,
    known: dict[str, Any],
    remediation_lines: set[int],
    result: VerificationResult,
) -> None:
    """Every address, hash and account named must exist in the evidence."""
    for index, line in enumerate(report.splitlines()):
        in_remediation = index in remediation_lines

        for ip in set(IPV4.findall(line)):
            if ip in _WILDCARD_IPS:
                continue
            if _NOT_AN_IP_CONTEXT.search(line) and ip not in known["ips"]:
                continue
            if ip in known["ips"]:
                continue
            result.issues.append(
                Issue(
                    "ungrounded_ip",
                    "fail" if in_remediation else "warn",
                    ip,
                    (
                        f"Address {ip} appears in a containment/remediation section but "
                        "is absent from the evidence. Acting on it would target a system "
                        "this investigation never implicated."
                        if in_remediation
                        else f"Address {ip} is not present in any ingested event."
                    ),
                    index + 1,
                )
            )

        for digest in set(HASH.findall(line)):
            if digest.lower() in known["hashes"]:
                continue
            result.issues.append(
                Issue(
                    "ungrounded_hash",
                    "fail" if in_remediation else "warn",
                    digest,
                    f"Hash {digest} does not appear in any ingested event. "
                    "Do not attribute a file to a hash the data does not contain.",
                    index + 1,
                )
            )

        if in_remediation:
            for account in _quoted_or_backticked(line):
                if not _looks_like_identifier(account):
                    continue
                # Action verbs from the pipeline's own containment vocabulary
                # are not entities.
                if account.strip().lower() in _ACTION_VOCABULARY:
                    continue
                # IP-shaped identifiers are validated by the address check
                # above against known["ips"] (which includes dst_ip and raw
                # excerpts). Re-checking them against the accounts/hosts
                # pools would falsely flag a grounded destination address
                # as an ungrounded remediation target.
                if IPV4.fullmatch(account.strip()):
                    if account.strip() in known["ips"]:
                        continue
                    # Not in evidence either — already reported as
                    # ungrounded_ip by the address check; don't double-flag.
                    continue
                if _is_known_principal(account, known):
                    continue
                # Labels constructed around grounded entities (rule names such
                # as Block-<addr>) are derived from the evidence, not new
                # targets.
                if _contains_grounded_entity(account, known):
                    continue
                result.issues.append(
                    Issue(
                        "ungrounded_remediation_target",
                        "fail",
                        account,
                        f"'{account}' is named as a remediation target but never appears "
                        "in the evidence as an account or host.",
                        index + 1,
                    )
                )


def _quoted_or_backticked(line: str) -> set[str]:
    values: set[str] = set()
    for pattern in (r"`([^`]{2,64})`", r"'([^']{2,64})'", r'"([^"]{2,64})"'):
        values.update(re.findall(pattern, line))
    return values


def _looks_like_identifier(value: str) -> bool:
    """True for account/host-shaped tokens, false for prose or commands."""
    candidate = value.strip()
    if " " in candidate or len(candidate) < 3:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\\\-]{2,63}", candidate))


_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _event_literal_pool(event) -> str:
    """Every comparable literal of one event, lowercased, for containment tests."""
    parts = [
        event.raw_excerpt,
        event.user,
        event.host,
        event.src_ip,
        event.dst_ip,
        event.process,
        event.parent_process,
        event.command_line,
        event.account_domain,
    ]
    parts.extend(str(v) for v in event.extra.values())
    parts.extend(event.hashes.values())
    return " ".join(p for p in parts if p).lower()


def _check_citation_consistency(
    report: str, store: EvidenceStore, result: VerificationResult
) -> None:
    """A line that cites events must be describing those events.

    Referential integrity alone lets a report bind a real entity to the wrong
    real event — e.g. attributing user X to a citation whose record names
    neither X nor anything like it. For every line carrying both citations and
    unambiguous entity literals (addresses, e-mail style principals), at least
    one cited event must actually contain each entity. Violations are warnings:
    prose legitimately juxtaposes entities from different sentences.
    """
    by_id = {e.ev_id: e for e in store.iter_events() if e.ev_id}
    pools: dict[str, str] = {}
    mismatches = 0

    for index, line in enumerate(report.splitlines()):
        ids = set(EVIDENCE_ID_PATTERN.findall(line))
        if not ids:
            continue
        cited = [by_id[ev_id] for ev_id in ids if ev_id in by_id]
        if not cited:
            continue
        entities = set(IPV4.findall(line)) | set(_EMAIL.findall(line))
        if not entities:
            continue

        for entity in entities:
            low = entity.lower()
            found = False
            for event in cited:
                pool = pools.get(event.ev_id)
                if pool is None:
                    pool = _event_literal_pool(event)
                    pools[event.ev_id] = pool
                if low in pool:
                    found = True
                    break
            if not found:
                mismatches += 1
                if mismatches > 20:
                    return
                cited_ids = ", ".join(sorted(ids))
                result.issues.append(
                    Issue(
                        "citation_mismatch",
                        "warn",
                        entity,
                        (
                            f"'{entity}' is attributed to citation(s) {cited_ids}, but "
                            "none of those events contain it. The entity may be real "
                            "elsewhere in the evidence — cite the event that actually "
                            "names it."
                        ),
                        index + 1,
                    )
                )


def _check_coverage(report: str, minimum: float, result: VerificationResult) -> None:
    """Measure how much of the report's factual content is cited."""
    in_code = False
    for raw_line in report.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        if line.startswith("#") or set(line) <= set("|-: "):
            continue
        if not _is_claim(line):
            continue
        result.claim_sentences += 1
        if EVIDENCE_ID_PATTERN.search(line) or "[UNVERIFIED]" in line:
            result.cited_claim_sentences += 1

    if result.claim_sentences and result.citation_coverage < minimum:
        result.issues.append(
            Issue(
                "low_citation_coverage",
                "warn",
                f"{result.citation_coverage:.0%}",
                (
                    f"Only {result.cited_claim_sentences} of {result.claim_sentences} "
                    f"factual statements carry an evidence citation (minimum "
                    f"{minimum:.0%}). Cite the EV ids that support each finding, or mark "
                    "the statement [UNVERIFIED]."
                ),
            )
        )


def _is_claim(line: str) -> bool:
    """A line asserting something concrete, as opposed to structure or prose filler."""
    stripped = re.sub(r"^[\-\*\d\.\)\s]+", "", line)
    if len(stripped) < _MIN_CLAIM_CHARS:
        return False
    # Concrete claims contain a specific: an address, a number, a time, a code.
    return bool(re.search(r"\d", stripped))


def _annotate(report: str, result: VerificationResult) -> str:
    """Mark unverifiable values inline so a reader sees them in context."""
    flagged = {
        issue.value
        for issue in result.issues
        if issue.kind in ("ungrounded_ip", "ungrounded_hash", "ungrounded_remediation_target")
        and issue.value
    }
    if not flagged:
        return report

    annotated = report
    for value in sorted(flagged, key=len, reverse=True):
        pattern = re.compile(rf"(?<!\[UNVERIFIED: ){re.escape(value)}")
        # A callable replacement avoids re-interpreting backslashes in the
        # flagged value (e.g. DOMAIN\user) as group references.
        annotated = pattern.sub(
            lambda m: f"{m.group(0)} [UNVERIFIED: not in evidence]", annotated
        )
    return annotated


def _verdict(result: VerificationResult) -> str:
    if any(i.severity == "fail" for i in result.issues):
        return "fail"
    if result.issues:
        return "warn"
    return "pass"


def format_verification_section(result: VerificationResult) -> str:
    """Render the verification outcome as a markdown section for the report."""
    lines = ["", "---", "", "## Evidence Verification", "", result.summary_table(), ""]

    if result.verdict == "fail":
        lines.append(
            "**This report did not pass verification.** The items marked FAIL above are "
            "not supported by the ingested evidence. Ungrounded entities inside a "
            "containment or remediation section must be removed before any action is "
            "taken — they name systems this investigation never implicated."
        )
    elif result.verdict == "warn":
        lines.append(
            "Verification completed with warnings. Review the items above: each names a "
            "value or a statement the ingested evidence does not directly support."
        )
    else:
        lines.append(
            "Every address, hash and citation in this report was matched to an ingested "
            "evidence record."
        )
    return "\n".join(lines)


def collect_report_entities(report: str) -> dict[str, Iterable[str]]:
    """Extract the concrete entities a report names. Useful for diagnostics."""
    return {
        "ips": sorted(set(IPV4.findall(report))),
        "hashes": sorted({h.lower() for h in HASH.findall(report)}),
        "citations": sorted(set(EVIDENCE_ID_PATTERN.findall(report))),
    }
