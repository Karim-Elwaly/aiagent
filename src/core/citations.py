"""
Evidence citation primitives.

A single, case-agnostic mechanism for grounding investigation reports in the
logs they were built from. The ingestion tool mints a stable ``EV-xxxxxx`` id
for every concrete finding it extracts and records where that finding came from
(``source_file`` + ``line_no`` + the raw text). Those ids are threaded through
the analysis phases and required in the final report, and a deterministic
verifier confirms every cited id was actually minted.

Nothing in this module knows anything about a particular dataset: it deals only
in id formatting, a machine-readable evidence-map block, and shape-based token
detection (addresses, hashes, CVEs, domains, accounts). This is why it works for
any log ecosystem — Windows, Linux, Cloud, Web, or Network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Citation id format ───────────────────────────────────────────
# Six zero-padded digits keep ids fixed-width and sortable. The pattern is used
# both to mint ids and to find them inside free-form report text.
_EV_ID_TEMPLATE = "EV-{:06d}"
EV_ID_RE = re.compile(r"\bEV-\d{6}\b")


def format_ev_id(index: int) -> str:
    """Return the canonical ``EV-000123`` id for a 1-based finding index."""
    return _EV_ID_TEMPLATE.format(index)


@dataclass(frozen=True)
class EvidenceRecord:
    """One minted finding: a citable id bound to its source location."""

    ev_id: str
    source_file: str
    line_no: int
    text: str


# ── Evidence-map block ───────────────────────────────────────────
# The full id -> (file, line, text) map is serialized into a single fenced block
# appended to the ingestion output. Downstream phases and the verifier recover it
# by parsing that block, so the map survives across stateless activity
# boundaries without any shared store. The block is intentionally line-oriented
# and bounded by the caller.
_EVIDENCE_MAP_FENCE = "EVIDENCE_MAP"
# `EV-000123<TAB>file.log<TAB>4521<TAB>raw text`
_EVIDENCE_MAP_ROW_RE = re.compile(
    r"^(EV-\d{6})\t([^\t]*)\t(\d+)\t(.*)$"
)
_EVIDENCE_MAP_BLOCK_RE = re.compile(
    r"```" + _EVIDENCE_MAP_FENCE + r"\s*\n(.*?)\n```",
    re.DOTALL,
)


def format_evidence_map(
    records: list[EvidenceRecord],
    *,
    max_rows: int = 800,
    max_chars: int = 40000,
) -> str:
    """Serialize evidence records into one bounded, fenced ``EVIDENCE_MAP`` block.

    The block is machine-readable (tab-separated) and meant to be carried
    verbatim in the ingestion phase's output, not shown to a human. It is
    bounded on two axes — a row cap and a character cap — because the assembler
    prompt on this branch is unbounded and the model context is finite; an
    unbounded map would overflow it. Rows beyond the cap are summarized by a
    trailing marker so the verifier can report the truncation honestly.
    """
    lines: list[str] = []
    used = 0
    shown = 0
    for rec in records:
        if shown >= max_rows:
            break
        # Raw text is single-lined and clipped so one enormous log line cannot
        # blow the block budget; the id still resolves to file:line for lookup.
        raw = " ".join((rec.text or "").split())
        if len(raw) > 240:
            raw = raw[:240] + "…"
        row = f"{rec.ev_id}\t{rec.source_file}\t{rec.line_no}\t{raw}"
        if used + len(row) + 1 > max_chars:
            break
        lines.append(row)
        used += len(row) + 1
        shown += 1

    omitted = len(records) - shown
    body = "\n".join(lines)
    if omitted > 0:
        body += f"\n# ...{omitted} additional evidence records omitted from map"

    return f"```{_EVIDENCE_MAP_FENCE}\n{body}\n```"


def parse_evidence_map(text: str) -> dict[str, EvidenceRecord]:
    """Reconstruct the ``{ev_id: EvidenceRecord}`` map from text containing a block.

    Accepts the full task output (or any string) and extracts every
    ``EVIDENCE_MAP`` block it finds. Malformed rows are skipped rather than
    raising — a partially recoverable map is more useful than none.
    """
    records: dict[str, EvidenceRecord] = {}
    for block in _EVIDENCE_MAP_BLOCK_RE.findall(text or ""):
        for line in block.splitlines():
            match = _EVIDENCE_MAP_ROW_RE.match(line)
            if not match:
                continue
            ev_id, source_file, line_no, raw = match.groups()
            records[ev_id] = EvidenceRecord(
                ev_id=ev_id,
                source_file=source_file,
                line_no=int(line_no),
                text=raw,
            )
    return records


def strip_evidence_map(text: str) -> str:
    """Remove any ``EVIDENCE_MAP`` blocks from text.

    Used before showing a phase output to a human or the assembler narrative:
    the map is plumbing, not prose.
    """
    return _EVIDENCE_MAP_BLOCK_RE.sub("", text or "").strip()


def parse_cited_ids(text: str) -> set[str]:
    """Return the set of ``EV-xxxxxx`` ids referenced anywhere in ``text``."""
    return set(EV_ID_RE.findall(text or ""))


# ── Concrete-claim (IoC) detection ───────────────────────────────
# Shape-based only: these patterns recognize the KINDS of token that must be
# grounded (addresses, hashes, CVEs, domains, account-like identifiers). They
# never enumerate specific values, so the citation-coverage checks are fully
# case-agnostic.
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|net|org|io|ru|cn|info|biz|xyz|top|co|us|uk|de|fr|nl|br|gov|mil|edu)\b"
)
# DOMAIN\account or user@realm or bare service/user id with structure.
_ACCOUNT_RE = re.compile(
    r"\b[A-Za-z0-9._-]+\\[A-Za-z0-9._$-]+\b"      # DOMAIN\user
    r"|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"  # user@realm / email
    r"|\barn:aws:[A-Za-z0-9:_/-]+\b"              # AWS ARN
)

# EV ids, evidence-map bookkeeping and pure version strings are not IoCs.
_EV_ID_INLINE_RE = re.compile(r"\bEV-\d{6}\b")


def extract_ioc_tokens(line: str) -> set[str]:
    """Return concrete IoC-shaped tokens on a line (case-agnostic, shape-based).

    Domains that are actually the tail of an email/account are folded into the
    account match, and evidence ids are never counted as IoCs.
    """
    tokens: set[str] = set()
    cleaned = _EV_ID_INLINE_RE.sub("", line or "")
    for match in _ACCOUNT_RE.findall(cleaned):
        tokens.add(match)
    account_blob = " ".join(tokens)
    for ip in _IPV4_RE.findall(cleaned):
        tokens.add(ip)
    for digest in _HASH_RE.findall(cleaned):
        tokens.add(digest)
    for cve in _CVE_RE.findall(cleaned):
        tokens.add(cve)
    for domain in _DOMAIN_RE.findall(cleaned):
        # Skip a domain that only appears because it is the realm of an account
        # already captured (avoids double-counting example.com in user@example.com).
        if domain in account_blob:
            continue
        tokens.add(domain)
    return tokens


def line_has_ioc(line: str) -> bool:
    """True when a line asserts at least one concrete IoC-shaped token."""
    return bool(extract_ioc_tokens(line))


# ── Report verification ──────────────────────────────────────────
# A deterministic, case-agnostic check that every citation in a report resolves
# to a minted evidence id, and that concrete claims are actually cited. It never
# rewrites conclusions and never raises — it annotates.


@dataclass
class CitationVerification:
    """Outcome of checking a report's citations against the minted id map."""

    cited_ids: list[str]
    grounded_ids: list[str]
    missing_ids: list[str]
    uncited_claim_lines: list[str]
    coverage: float  # fraction of IoC-bearing claim lines that carry a citation
    verdict: str  # "pass" | "warn" | "fail"


# Lines that structurally cannot be a citable claim: headers, table separators,
# fenced-code boundaries, and the evidence-map plumbing itself.
_NON_CLAIM_LINE_RE = re.compile(r"^\s*(?:#{1,6}\s|\|?\s*[-:]+\s*\|?|```)")


def verify_citations(
    report: str,
    evidence_map: dict[str, EvidenceRecord],
) -> CitationVerification:
    """Check a report's ``EV-xxxxxx`` citations against the minted id map.

    - Every id cited in the report is classified grounded (present in the map)
      or missing (cited but never minted → likely fabricated).
    - Every line asserting a concrete IoC-shaped token is checked for at least
      one citation; those without one are flagged as uncited claims.
    - Coverage is the fraction of IoC-bearing claim lines that are cited.

    Purely structural; no dataset knowledge. Never raises.
    """
    report = report or ""
    cited = sorted(parse_cited_ids(report))
    grounded = [ev for ev in cited if ev in evidence_map]
    missing = [ev for ev in cited if ev not in evidence_map]

    uncited: list[str] = []
    ioc_claim_lines = 0
    cited_claim_lines = 0
    for raw_line in report.splitlines():
        line = raw_line.strip()
        if not line or _NON_CLAIM_LINE_RE.match(line):
            continue
        if not line_has_ioc(line):
            continue
        ioc_claim_lines += 1
        if EV_ID_RE.search(line):
            cited_claim_lines += 1
        else:
            uncited.append(line[:200])

    coverage = (cited_claim_lines / ioc_claim_lines) if ioc_claim_lines else 1.0

    if missing:
        verdict = "fail"
    elif coverage < 0.5 or uncited:
        verdict = "warn"
    else:
        verdict = "pass"

    return CitationVerification(
        cited_ids=cited,
        grounded_ids=grounded,
        missing_ids=missing,
        uncited_claim_lines=uncited,
        coverage=coverage,
        verdict=verdict,
    )


def format_verification_table(
    report: str,
    evidence_map: dict[str, EvidenceRecord],
    result: CitationVerification,
    *,
    max_rows: int = 200,
) -> str:
    """Render the Evidence Verification table appended below a report.

    One row per cited id: its source location, a snippet of the evidence text,
    and a status (grounded / MISSING). A short summary line reports coverage and
    any uncited concrete claims, so a reader immediately sees what is and is not
    substantiated.
    """
    lines = [
        "",
        "---",
        "## 🔍 Evidence Verification",
        "",
        f"- **Verdict:** {result.verdict.upper()}",
        f"- **Citations:** {len(result.grounded_ids)} grounded / "
        f"{len(result.missing_ids)} missing / {len(result.cited_ids)} total",
        f"- **Claim citation coverage:** {result.coverage * 100:.0f}%",
    ]
    if result.missing_ids:
        lines.append(
            f"- ⚠️ **Fabricated/unknown ids (not in evidence):** "
            f"{', '.join(result.missing_ids[:40])}"
        )
    if result.uncited_claim_lines:
        lines.append(
            f"- ⚠️ **Uncited concrete claims:** {len(result.uncited_claim_lines)} "
            "(each asserts an IoC-shaped value with no EV citation)"
        )
    lines.extend(["", "| Evidence ID | Source:Line | Evidence | Status |", "| :--- | :--- | :--- | :--- |"])

    for ev_id in result.cited_ids[:max_rows]:
        record = evidence_map.get(ev_id)
        if record:
            src = f"{record.source_file}:L{record.line_no}" if record.line_no else record.source_file
            snippet = (record.text or "").replace("|", "\\|")[:80]
            status = "✅ grounded"
        else:
            src = "—"
            snippet = "not present in ingested evidence"
            status = "❌ MISSING"
        lines.append(f"| {ev_id} | {src} | {snippet} | {status} |")

    if len(result.cited_ids) > max_rows:
        lines.append(
            f"| … | | {len(result.cited_ids) - max_rows} more citations | |"
        )

    return "\n".join(lines)

