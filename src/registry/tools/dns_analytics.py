"""
UAOS DNS Behaviour Analytics

Deterministic detection of DNS abuse patterns that a language model cannot
reliably see by reading query logs line-by-line:

  * DNS tunneling / covert exfiltration — payloads encoded in query labels
    produce long, high-entropy, frequently unique subdomains under one parent
    domain, often carried in TXT/NULL record types.
  * Hex-encoded exfiltration — a variant where labels are pure hexadecimal
    byte encodings.
  * DGA (domain generation algorithm) activity — many distinct high-entropy
    registered names, most of which fail to resolve (NXDOMAIN).

Everything here is statistical: label geometry, character entropy, response
code ratios and record-type distributions. No domain name, TLD or dataset-
specific string appears anywhere in this module — the same math applies to
any DNS telemetry that a log mapping normalizes (Zeek, BIND, resolver
exports, firewall DNS logs).
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from typing import Any

from src.core.analytics_util import cite, empty_store_message, json_block
from src.core.config import get_settings
from src.core.evidence import EvidenceEvent, get_store
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

_HEX_LABEL = re.compile(r"^[0-9a-fA-F]{12,}$")


def _shannon_entropy(text: str) -> float:
    """Bits per character. Human-chosen names sit near 2; encodings above 3."""
    if not text:
        return 0.0
    counts = Counter(text.lower())
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _split_domain(query: str) -> tuple[str, str]:
    """(registered_domain, subdomain_part) using a last-two-labels heuristic.

    A public-suffix list would be more precise, but the heuristic is
    source-agnostic and errs toward grouping — acceptable for statistics that
    aggregate per parent domain.
    """
    name = query.rstrip(".").lower()
    labels = [l for l in name.split(".") if l]
    if len(labels) < 2:
        return name, ""
    registered = ".".join(labels[-2:])
    sub = ".".join(labels[:-2])
    return registered, sub


def _dns_query_events(store: Any) -> list[tuple[EvidenceEvent, str]]:
    """Every event carrying a query name, from any mapped source."""
    out: list[tuple[EvidenceEvent, str]] = []
    for event in store.iter_events():
        query = str(event.extra.get("query") or "").strip()
        if not query and event.action == "dns_query":
            query = str(event.extra.get("qname") or event.extra.get("domain") or "").strip()
        if query and "." in query:
            out.append((event, query))
    return out


async def analyze_dns_patterns(domain: str = "", _run_id: str = "") -> str:
    """Statistically analyse DNS query telemetry for tunneling, hex-encoded
    exfiltration and DGA activity."""
    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("DNS pattern analysis")

    queries = _dns_query_events(store)
    if domain:
        needle = domain.rstrip(".").lower()
        queries = [(e, q) for e, q in queries if needle in q.lower()]

    if not queries:
        return (
            "No DNS query events (events carrying a query name) were found in the "
            "evidence store for the given filters. Report this as 'no DNS telemetry "
            "available', not as 'no DNS abuse'."
        )

    settings = get_settings()

    # ── per-registered-domain aggregation ────────────────
    by_domain: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "events": [],
            "fqdns": set(),
            "sub_lengths": [],
            "sub_entropies": [],
            "hex_labels": 0,
            "labelled_queries": 0,
            "record_types": Counter(),
            "failures": 0,
            "clients": set(),
        }
    )
    for event, query in queries:
        registered, sub = _split_domain(query)
        agg = by_domain[registered]
        agg["events"].append(event)
        agg["fqdns"].add(query.lower())
        if event.event_code:
            agg["record_types"][event.event_code.upper()] += 1
        if event.status == "failure":
            agg["failures"] += 1
        if event.src_ip:
            agg["clients"].add(event.src_ip)
        if sub:
            agg["labelled_queries"] += 1
            longest = max(sub.split("."), key=len)
            agg["sub_lengths"].append(len(longest))
            agg["sub_entropies"].append(_shannon_entropy(sub.replace(".", "")))
            if any(_HEX_LABEL.match(label) for label in sub.split(".")):
                agg["hex_labels"] += 1

    tunneling: list[dict[str, Any]] = []
    hex_exfil: list[dict[str, Any]] = []
    dga_candidates: list[dict[str, Any]] = []

    for registered, agg in by_domain.items():
        total = len(agg["events"])
        uniques = len(agg["fqdns"])
        mean_entropy = (
            sum(agg["sub_entropies"]) / len(agg["sub_entropies"])
            if agg["sub_entropies"]
            else 0.0
        )
        max_label = max(agg["sub_lengths"], default=0)
        hex_ratio = (
            agg["hex_labels"] / agg["labelled_queries"] if agg["labelled_queries"] else 0.0
        )
        nx_ratio = agg["failures"] / total if total else 0.0
        txt_like = sum(
            n for rt, n in agg["record_types"].items() if rt in ("TXT", "NULL", "CNAME")
        )

        base = {
            "domain": registered,
            "queries": total,
            "unique_names": uniques,
            "distinct_clients": len(agg["clients"]),
            "mean_subdomain_entropy_bits": round(mean_entropy, 2),
            "max_subdomain_label_length": max_label,
            "hex_label_ratio": round(hex_ratio, 2),
            "nxdomain_ratio": round(nx_ratio, 2),
            "record_types": dict(agg["record_types"]),
            "evidence": cite(agg["events"]),
        }

        # Tunneling: many unique names under one parent whose labels are long
        # or high-entropy — the statistical footprint of payload chunking.
        if (
            total >= settings.dns_min_queries_per_domain
            and uniques >= settings.dns_tunnel_min_unique_subdomains
            and (
                mean_entropy >= settings.dns_tunnel_min_entropy
                or max_label >= settings.dns_tunnel_min_label_length
            )
        ):
            tunneling.append(
                {
                    **base,
                    "pattern": "dns_tunneling_suspect",
                    "txt_null_cname_queries": txt_like,
                    "description": (
                        f"{uniques} unique names under {registered} with mean subdomain "
                        f"entropy {round(mean_entropy, 2)} bits/char and labels up to "
                        f"{max_label} chars. Human-chosen names do not have this shape; "
                        "payload encoding does. Corroborate with the querying host's "
                        "process activity before concluding exfiltration."
                    ),
                }
            )

        # Hex-encoded exfiltration: a majority of labels are pure hex — a
        # direct byte encoding regardless of entropy thresholds.
        if (
            agg["labelled_queries"] >= settings.dns_min_queries_per_domain
            and hex_ratio >= settings.dns_hex_label_ratio
        ):
            hex_exfil.append(
                {
                    **base,
                    "pattern": "hex_encoded_dns_exfil",
                    "description": (
                        f"{round(hex_ratio * 100)}% of subdomain labels under {registered} "
                        "are pure hexadecimal strings — a byte-level data encoding, not "
                        "naming."
                    ),
                }
            )

        # DGA candidate: a registered label that itself is high-entropy and
        # mostly fails to resolve.
        registered_label = registered.split(".")[0]
        if (
            _shannon_entropy(registered_label) >= settings.dns_dga_min_entropy
            and len(registered_label) >= 8
            and nx_ratio >= settings.dns_dga_min_nxdomain_ratio
        ):
            dga_candidates.append(
                {
                    **base,
                    "pattern": "dga_candidate",
                    "registered_label_entropy_bits": round(
                        _shannon_entropy(registered_label), 2
                    ),
                }
            )

    dga_finding: dict[str, Any] | None = None
    if len(dga_candidates) >= settings.dns_dga_min_domains:
        dga_finding = {
            "pattern": "dga_activity",
            "candidate_domains": len(dga_candidates),
            "description": (
                f"{len(dga_candidates)} distinct high-entropy registered names that "
                "mostly failed to resolve. Algorithmically generated rendezvous "
                "domains have exactly this footprint; check the querying hosts for "
                "the process responsible."
            ),
            "candidates": sorted(
                dga_candidates, key=lambda c: c["nxdomain_ratio"], reverse=True
            ),
        }

    payload = {
        "analysis": "dns_pattern_analysis",
        "dns_query_events_examined": len(queries),
        "distinct_registered_domains": len(by_domain),
        "thresholds": {
            "min_queries_per_domain": settings.dns_min_queries_per_domain,
            "tunnel_min_unique_subdomains": settings.dns_tunnel_min_unique_subdomains,
            "tunnel_min_label_length": settings.dns_tunnel_min_label_length,
            "tunnel_min_entropy_bits": settings.dns_tunnel_min_entropy,
            "hex_label_ratio": settings.dns_hex_label_ratio,
            "dga_min_domains": settings.dns_dga_min_domains,
            "dga_min_nxdomain_ratio": settings.dns_dga_min_nxdomain_ratio,
        },
        "tunneling_suspects": sorted(
            tunneling, key=lambda t: t["unique_names"], reverse=True
        ),
        "hex_encoded_exfil": hex_exfil,
        "dga": dga_finding or {"pattern": "dga_activity", "candidate_domains": len(dga_candidates), "detected": False},
        "note": (
            "Entropy and label statistics flag encodings, not intent — content "
            "distribution networks and some telemetry SDKs also use generated "
            "names. Corroborate with the querying host, volume over time and "
            "the record types before classifying."
        ),
    }
    return json_block(payload)


DNS_PATTERN_SPEC = ToolSpec(
    tool_id="analyze_dns_patterns_v1",
    name="analyze_dns_patterns",
    description=(
        "Statistically analyse DNS query telemetry in the evidence store: detect DNS "
        "tunneling (many unique long/high-entropy subdomains under one parent), "
        "hex-encoded exfiltration (labels that are raw byte encodings), and DGA "
        "activity (many high-entropy registered names that fail to resolve). Works on "
        "any ingested source that maps a query name (Zeek, BIND, resolver or firewall "
        "DNS logs). Requires ingest_logs first. Returns citation ids for every claim."
    ),
    skills_provided=[
        "dns_analysis",
        "tunneling_detection",
        "dga_detection",
        "exfiltration_analysis",
        "network_analysis",
        "anomaly_detection",
    ],
    parameters={
        "domain": {
            "type": "string",
            "description": "Optional substring filter on the query name. Omit to analyse all DNS telemetry.",
        },
    },
    function=analyze_dns_patterns,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)
