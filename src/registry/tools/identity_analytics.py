"""
UAOS Identity Analytics Tools

Deterministic (non-LLM) analysis of authentication and identity telemetry held
in the run's evidence store.

Why these exist
---------------
Language models reliably miss *sequence* and *statistical* structure: a burst of
failures followed by one success, a rejected-prompt storm ending in an approval,
or two sign-ins too far apart to be the same human. Those are arithmetic
problems, not reasoning problems, so they are computed here and handed to the
model as facts with citation ids.

Everything is source-agnostic: the tools read normalized ``EvidenceEvent``
fields, and their outcome vocabulary comes from ``data/baselines/auth_signals.yaml``.
Every threshold comes from configuration with documented rationale.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from src.core.analytics_util import (
    cite,
    empty_store_message,
    event_time,
    haversine_km,
    has_coordinates,
    is_auth_event,
    is_failure,
    is_mfa_denial,
    is_success,
    json_block,
    no_findings_message,
    timed_events,
)
from src.core.config import get_settings
from src.core.evidence import EvidenceEvent, get_store
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

TimedEvent = tuple[datetime, EvidenceEvent]


# ── Shared loading ───────────────────────────────────────


def _auth_events(_run_id: str, user: str = "", src_ip: str = "") -> list[TimedEvent] | None:
    """Timed authentication events, or None when nothing has been ingested."""
    store = get_store(_run_id)
    if store.count() == 0:
        return None

    selected: list[EvidenceEvent] = []
    for event in store.iter_events():
        if not is_auth_event(event):
            continue
        if user and user.lower() not in f"{event.user} {event.account_domain}".lower():
            continue
        if src_ip and src_ip != event.src_ip:
            continue
        selected.append(event)
    return timed_events(selected)


def _cluster(pairs: list[TimedEvent], window_seconds: float) -> list[list[TimedEvent]]:
    """Group chronologically sorted events into bursts.

    A burst starts at an event and absorbs every following event that occurs
    within ``window_seconds`` of the burst's own start, so a slow trickle of
    attempts is not merged into a single artificial "burst".
    """
    clusters: list[list[TimedEvent]] = []
    current: list[TimedEvent] = []
    for pair in pairs:
        if not current:
            current = [pair]
            continue
        if (pair[0] - current[0][0]).total_seconds() <= window_seconds:
            current.append(pair)
        else:
            clusters.append(current)
            current = [pair]
    if current:
        clusters.append(current)
    return clusters


def _window(pairs: list[TimedEvent]) -> dict[str, str]:
    return {
        "first_seen": pairs[0][0].isoformat(),
        "last_seen": pairs[-1][0].isoformat(),
    }


# ── analyze_auth_sequences ───────────────────────────────


async def analyze_auth_sequences(user: str = "", src_ip: str = "", _run_id: str = "") -> str:
    """Classify authentication sequences into attack patterns and benign patterns."""
    pairs = _auth_events(_run_id, user=user, src_ip=src_ip)
    if pairs is None:
        return empty_store_message("authentication sequence analysis")
    if not pairs:
        return (
            "No authentication events with usable timestamps were found in the evidence "
            "store for the given filters. Report this as 'no authentication telemetry "
            "available', not as 'no attack occurred'."
        )

    settings = get_settings()
    findings: list[dict[str, Any]] = []
    benign: list[dict[str, Any]] = []

    by_source: dict[str, list[TimedEvent]] = defaultdict(list)
    by_user: dict[str, list[TimedEvent]] = defaultdict(list)
    for pair in pairs:
        if pair[1].src_ip:
            by_source[pair[1].src_ip].append(pair)
        if pair[1].user:
            by_user[pair[1].user.lower()].append(pair)

    _detect_source_patterns(by_source, findings, benign)
    _detect_mfa_fatigue(by_user, findings)

    payload = {
        "analysis": "authentication_sequence_analysis",
        "events_examined": len(pairs),
        "distinct_sources": len(by_source),
        "distinct_accounts": len(by_user),
        "thresholds": {
            "burst_window_seconds": settings.auth_burst_window_seconds,
            "spray_min_accounts": settings.auth_spray_min_accounts,
            "bruteforce_min_failures": settings.auth_bruteforce_min_failures,
            "fatigue_min_denials": settings.auth_fatigue_min_denials,
            "fatigue_max_interval_seconds": settings.auth_fatigue_max_interval_seconds,
        },
        "findings": findings,
        "benign_explanations": benign,
    }

    if not findings:
        return (
            no_findings_message("Authentication sequence analysis", len(pairs))
            + "\n"
            + json_block(payload)
        )
    return json_block(payload)


def _detect_source_patterns(
    by_source: dict[str, list[TimedEvent]],
    findings: list[dict[str, Any]],
    benign: list[dict[str, Any]],
) -> None:
    """Per-source spray / brute-force detection, plus the success that followed."""
    settings = get_settings()
    window = settings.auth_burst_window_seconds

    for source, source_pairs in by_source.items():
        failures = [p for p in source_pairs if is_failure(p[1])]
        successes = [p for p in source_pairs if is_success(p[1])]
        if not failures:
            continue

        for burst in _cluster(failures, window):
            accounts = sorted({p[1].user for p in burst if p[1].user})
            burst_end = burst[-1][0]

            # A success from the same source after the burst is the moment the
            # attempt stopped being an attempt.
            follow_on = [
                p
                for p in successes
                if 0 <= (p[0] - burst_end).total_seconds() <= window
            ]

            if len(accounts) >= settings.auth_spray_min_accounts:
                findings.append(
                    {
                        "pattern": "password_spray",
                        "description": (
                            f"Source {source} failed authentication against "
                            f"{len(accounts)} distinct accounts within "
                            f"{window}s — few attempts per account, many accounts."
                        ),
                        "source_ip": source,
                        "accounts_targeted": accounts,
                        "failure_count": len(burst),
                        **_window(burst),
                        "evidence": cite([p[1] for p in burst]),
                    }
                )
            else:
                per_account = Counter(p[1].user for p in burst if p[1].user)
                for account, count in per_account.items():
                    if count >= settings.auth_bruteforce_min_failures:
                        account_burst = [p for p in burst if p[1].user == account]
                        findings.append(
                            {
                                "pattern": "brute_force",
                                "description": (
                                    f"Source {source} produced {count} authentication "
                                    f"failures against the single account '{account}' "
                                    f"within {window}s."
                                ),
                                "source_ip": source,
                                "account": account,
                                "failure_count": count,
                                **_window(account_burst),
                                "evidence": cite([p[1] for p in account_burst]),
                            }
                        )

            # Benign explanation first: a user mistyping a password fails once
            # or twice and self-corrects immediately from the same address. That
            # shape must not be reported as "success after a failure burst".
            if len(burst) <= settings.auth_typo_max_failures and len(accounts) == 1:
                account = accounts[0]
                corrected = [
                    p
                    for p in successes
                    if p[1].user == account
                    and 0
                    <= (p[0] - burst_end).total_seconds()
                    <= settings.auth_typo_success_window_seconds
                ]
                if corrected:
                    benign.append(
                        {
                            "pattern": "credential_typo_self_corrected",
                            "description": (
                                f"Account '{account}' had {len(burst)} failure(s) then a "
                                f"success from the same source {source} within "
                                f"{settings.auth_typo_success_window_seconds}s — the "
                                f"signature of a mistyped password, not an attack."
                            ),
                            "source_ip": source,
                            "account": account,
                            "evidence": cite([p[1] for p in burst + corrected]),
                        }
                    )
                    continue

            if follow_on:
                succeeded = sorted({p[1].user for p in follow_on if p[1].user})
                findings.append(
                    {
                        "pattern": "successful_authentication_after_failure_burst",
                        "description": (
                            f"Source {source} authenticated SUCCESSFULLY as "
                            f"{', '.join(succeeded) or 'an account'} within {window}s of "
                            f"{len(burst)} failed attempt(s). This is the point at which "
                            f"the attempt became a compromise; it must appear in the "
                            f"timeline and drive containment scope."
                        ),
                        "source_ip": source,
                        "accounts_compromised": succeeded,
                        "preceding_failures": len(burst),
                        **_window(follow_on),
                        "evidence": cite([p[1] for p in follow_on]),
                    }
                )
                continue


def _detect_mfa_fatigue(
    by_user: dict[str, list[TimedEvent]], findings: list[dict[str, Any]]
) -> None:
    """Repeated rejected second-factor prompts, and whether one was finally approved."""
    settings = get_settings()
    for account, account_pairs in by_user.items():
        denials = [p for p in account_pairs if is_mfa_denial(p[1]) and is_failure(p[1])]
        if len(denials) < settings.auth_fatigue_min_denials:
            continue

        # Only rapid re-prompting counts; a user declining prompts days apart is
        # not being worn down.
        run: list[TimedEvent] = []
        runs: list[list[TimedEvent]] = []
        for pair in denials:
            if run and (pair[0] - run[-1][0]).total_seconds() > settings.auth_fatigue_max_interval_seconds:
                runs.append(run)
                run = []
            run.append(pair)
        if run:
            runs.append(run)

        for burst in runs:
            if len(burst) < settings.auth_fatigue_min_denials:
                continue
            burst_end = burst[-1][0]
            approval = [
                p
                for p in account_pairs
                if is_success(p[1])
                and 0 <= (p[0] - burst_end).total_seconds() <= settings.auth_burst_window_seconds
            ]
            if approval:
                findings.append(
                    {
                        "pattern": "mfa_fatigue_succeeded",
                        "description": (
                            f"Account '{account}' rejected {len(burst)} second-factor "
                            f"prompts in rapid succession and then APPROVED one. The "
                            f"approval is the compromise moment — the account must be "
                            f"treated as taken over from that timestamp."
                        ),
                        "account": account,
                        "denials": len(burst),
                        "approved_at": approval[0][0].isoformat(),
                        **_window(burst),
                        "evidence": cite([p[1] for p in burst + approval[:1]]),
                    }
                )
            else:
                findings.append(
                    {
                        "pattern": "mfa_fatigue_attempted",
                        "description": (
                            f"Account '{account}' received {len(burst)} rapid second-factor "
                            f"prompts, all rejected. The credential is likely known to an "
                            f"attacker even though the factor held."
                        ),
                        "account": account,
                        "denials": len(burst),
                        **_window(burst),
                        "evidence": cite([p[1] for p in burst]),
                    }
                )


AUTH_SEQUENCE_SPEC = ToolSpec(
    tool_id="analyze_auth_sequences_v1",
    name="analyze_auth_sequences",
    description=(
        "Statistically classify authentication sequences in the evidence store: password "
        "spray, brute force, MFA push fatigue, and — critically — any SUCCESS that "
        "followed a failure burst (the compromise moment). Also reports benign "
        "explanations such as a self-corrected mistyped password. Requires ingest_logs "
        "to have run first. Returns citation ids for every claim."
    ),
    skills_provided=["auth_sequence_analysis", "identity_analysis", "anomaly_detection"],
    parameters={
        "user": {
            "type": "string",
            "description": "Optional account filter. Omit to analyse all accounts.",
        },
        "src_ip": {
            "type": "string",
            "description": "Optional source IP filter. Omit to analyse all sources.",
        },
    },
    function=analyze_auth_sequences,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── analyze_identity_velocity ────────────────────────────


async def analyze_identity_velocity(user: str = "", _run_id: str = "") -> str:
    """Detect travel between sign-in locations that no human could perform."""
    pairs = _auth_events(_run_id, user=user)
    if pairs is None:
        return empty_store_message("identity velocity analysis")
    if not pairs:
        return (
            "No timestamped authentication events available for velocity analysis. "
            "Report 'no data', not 'no impossible travel'."
        )

    settings = get_settings()
    by_user: dict[str, list[TimedEvent]] = defaultdict(list)
    for pair in pairs:
        if pair[1].user:
            by_user[pair[1].user].append(pair)

    findings: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    unresolved = 0

    for account, account_pairs in by_user.items():
        located = [p for p in account_pairs if has_coordinates(p[1])]
        unresolved += len(account_pairs) - len(located)

        for previous, current in zip(located, located[1:]):
            distance = haversine_km(
                float(previous[1].geo.latitude),
                float(previous[1].geo.longitude),
                float(current[1].geo.latitude),
                float(current[1].geo.longitude),
            )
            if distance < settings.velocity_min_distance_km:
                continue

            hours = (current[0] - previous[0]).total_seconds() / 3600.0
            same_asn = bool(
                previous[1].geo.asn
                and previous[1].geo.asn == current[1].geo.asn
            )
            if same_asn and distance <= settings.velocity_same_metro_km:
                suppressed.append(
                    {
                        "reason": "same_network_operator_address_rotation",
                        "account": account,
                        "distance_km": round(distance, 1),
                        "asn": current[1].geo.asn,
                        "description": (
                            "Both sign-ins came from the same network operator within a "
                            "single region — consistent with carrier/NAT address rotation, "
                            "not travel."
                        ),
                        "evidence": cite([previous[1], current[1]]),
                    }
                )
                continue

            record = {
                "account": account,
                "from": _place(previous[1]),
                "to": _place(current[1]),
                "distance_km": round(distance, 1),
                "elapsed_hours": round(hours, 3),
                "from_time": previous[0].isoformat(),
                "to_time": current[0].isoformat(),
                "evidence": cite([previous[1], current[1]]),
            }

            if hours <= 0:
                record["pattern"] = "concurrent_sessions_distinct_locations"
                record["description"] = (
                    f"Account '{account}' authenticated from two locations "
                    f"{round(distance, 1)} km apart with no elapsed time between them. "
                    "One of the sessions is not the legitimate user."
                )
                findings.append(record)
                continue

            speed = distance / hours
            record["implied_speed_kmh"] = round(speed, 1)
            if speed > settings.velocity_impossible_kmh:
                record["pattern"] = "impossible_travel"
                record["description"] = (
                    f"Account '{account}' moved {round(distance, 1)} km in "
                    f"{round(hours, 2)} h — an implied {round(speed)} km/h, above the "
                    f"{settings.velocity_impossible_kmh} km/h threshold that already "
                    "allows for commercial aviation."
                )
                findings.append(record)

    payload = {
        "analysis": "identity_velocity_analysis",
        "accounts_examined": len(by_user),
        "events_without_geolocation": unresolved,
        "thresholds": {
            "impossible_kmh": settings.velocity_impossible_kmh,
            "min_distance_km": settings.velocity_min_distance_km,
            "same_metro_km": settings.velocity_same_metro_km,
        },
        "findings": findings,
        "suppressed_benign": suppressed,
        "note": (
            "Locations come only from fields present in the logs. Events without "
            "coordinates are counted above and were NOT geolocated by guesswork."
        ),
    }
    return json_block(payload)


def _place(event: EvidenceEvent) -> str:
    bits = [b for b in (event.geo.city, event.geo.country) if b]
    label = ", ".join(bits) if bits else "unknown location"
    return f"{label} ({event.src_ip})" if event.src_ip else label


IDENTITY_VELOCITY_SPEC = ToolSpec(
    tool_id="analyze_identity_velocity_v1",
    name="analyze_identity_velocity",
    description=(
        "Compute geographic velocity between consecutive sign-ins per account and flag "
        "impossible travel or concurrent sessions from distinct locations. Suppresses "
        "benign mobile-carrier address rotation. Uses only geo fields present in the "
        "logs — never guesses a location from an IP address."
    ),
    skills_provided=["geo_velocity_analysis", "identity_analysis", "false_positive_analysis"],
    parameters={
        "user": {
            "type": "string",
            "description": "Optional account filter. Omit to analyse all accounts.",
        },
    },
    function=analyze_identity_velocity,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── actor_pivot ──────────────────────────────────────────


async def actor_pivot(entity: str, _run_id: str = "") -> str:
    """Pivot the whole evidence store around one entity (IP, account or host)."""
    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("actor pivot")

    needle = (entity or "").strip()
    if not needle:
        return "Error: 'entity' is required — supply an IP address, account name or hostname."

    lowered = needle.lower()
    related: list[EvidenceEvent] = []
    for event in store.iter_events():
        if needle in (event.src_ip, event.dst_ip) or lowered in (
            event.user.lower(),
            event.host.lower(),
        ):
            related.append(event)

    if not related:
        return (
            f"No evidence references '{entity}'. It must NOT appear in the report as an "
            "involved entity, a compromised asset, or a containment target."
        )

    succeeded: list[EvidenceEvent] = []
    failed: list[EvidenceEvent] = []
    for event in related:
        if not is_auth_event(event):
            continue
        if is_success(event):
            succeeded.append(event)
        elif is_failure(event):
            failed.append(event)

    times = [t for t, _ in timed_events(related)]
    payload = {
        "analysis": "actor_pivot",
        "entity": entity,
        "total_events": len(related),
        "first_seen": times[0].isoformat() if times else "unknown",
        "last_seen": times[-1].isoformat() if times else "unknown",
        "source_types": sorted({e.source_type for e in related if e.source_type}),
        "accounts_seen": sorted({e.user for e in related if e.user}),
        "accounts_authenticated_successfully": sorted({e.user for e in succeeded if e.user}),
        "accounts_failed_authentication": sorted({e.user for e in failed if e.user}),
        "hosts": sorted({e.host for e in related if e.host}),
        "source_ips": sorted({e.src_ip for e in related if e.src_ip}),
        "destination_ips": sorted({e.dst_ip for e in related if e.dst_ip}),
        "destination_ports": sorted({e.dst_port for e in related if e.dst_port}),
        "processes": sorted({e.process for e in related if e.process}),
        "evidence": cite(related, limit=40),
        "note": (
            "accounts_authenticated_successfully is the blast radius for this entity. "
            "Containment must target only entities listed here."
        ),
    }
    return json_block(payload)


ACTOR_PIVOT_SPEC = ToolSpec(
    tool_id="actor_pivot_v1",
    name="actor_pivot",
    description=(
        "Pivot the entire evidence store around a single entity (IP, account or host) "
        "and return every account, host, destination and process it touched, separating "
        "successful from failed authentications. Use this to establish blast radius and "
        "to build a containment list of REAL entities only."
    ),
    skills_provided=["actor_correlation", "blast_radius", "impact_analysis"],
    parameters={
        "entity": {
            "type": "string",
            "description": "IP address, account name or hostname to pivot on.",
        },
    },
    function=actor_pivot,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── analyze_device_posture ───────────────────────────────


async def analyze_device_posture(user: str = "", _run_id: str = "") -> str:
    """Compare each sign-in's device attributes against that account's own baseline."""
    pairs = _auth_events(_run_id, user=user)
    if pairs is None:
        return empty_store_message("device posture analysis")

    with_device = [
        p
        for p in pairs
        if any(
            (
                p[1].device.os,
                p[1].device.browser,
                p[1].device.user_agent,
                p[1].device.device_id,
                p[1].device.is_managed is not None,
                p[1].device.is_compliant is not None,
            )
        )
    ]
    if not with_device:
        return (
            "No device-posture attributes are present in the ingested evidence "
            f"({len(pairs)} authentication events examined). Report device posture as "
            "'not available in the provided telemetry' rather than inferring it."
        )

    by_user: dict[str, list[TimedEvent]] = defaultdict(list)
    for pair in with_device:
        by_user[pair[1].user].append(pair)

    accounts: list[dict[str, Any]] = []
    for account, account_pairs in by_user.items():
        managed = [p for p in account_pairs if p[1].device.is_managed is True]
        unmanaged = [p for p in account_pairs if p[1].device.is_managed is False]
        noncompliant = [p for p in account_pairs if p[1].device.is_compliant is False]

        baseline_os = Counter(p[1].device.os for p in account_pairs if p[1].device.os)
        baseline_agent = Counter(
            p[1].device.user_agent for p in account_pairs if p[1].device.user_agent
        )
        known_devices = Counter(
            p[1].device.device_id for p in account_pairs if p[1].device.device_id
        )

        deviations: list[dict[str, Any]] = []

        # An account that is otherwise consistently on managed hardware signing
        # in from unmanaged hardware is a posture break worth explaining.
        if managed and unmanaged:
            deviations.append(
                {
                    "type": "unmanaged_device_for_normally_managed_account",
                    "count": len(unmanaged),
                    "description": (
                        f"'{account}' signs in from managed devices {len(managed)} time(s) "
                        f"but from unmanaged device(s) {len(unmanaged)} time(s)."
                    ),
                    "evidence": cite([p[1] for p in unmanaged]),
                }
            )
        if noncompliant:
            deviations.append(
                {
                    "type": "non_compliant_device",
                    "count": len(noncompliant),
                    "description": (
                        f"{len(noncompliant)} sign-in(s) for '{account}' came from a device "
                        "reported as non-compliant with policy."
                    ),
                    "evidence": cite([p[1] for p in noncompliant]),
                }
            )

        rare_os = [os_name for os_name, n in baseline_os.items() if n == 1 and len(baseline_os) > 1]
        if rare_os:
            deviations.append(
                {
                    "type": "unusual_platform_for_account",
                    "platforms": rare_os,
                    "description": (
                        f"'{account}' normally signs in from "
                        f"{baseline_os.most_common(1)[0][0]} but used {', '.join(rare_os)} once."
                    ),
                    "evidence": cite(
                        [p[1] for p in account_pairs if p[1].device.os in rare_os]
                    ),
                }
            )

        rare_agents = [a for a, n in baseline_agent.items() if n == 1 and len(baseline_agent) > 1]
        if rare_agents:
            deviations.append(
                {
                    "type": "unusual_client_for_account",
                    "count": len(rare_agents),
                    "description": (
                        f"'{account}' used {len(rare_agents)} client string(s) seen only once, "
                        "against a baseline of repeated clients."
                    ),
                    "evidence": cite(
                        [p[1] for p in account_pairs if p[1].device.user_agent in rare_agents]
                    ),
                }
            )

        accounts.append(
            {
                "account": account,
                "sign_ins_with_device_data": len(account_pairs),
                "managed": len(managed),
                "unmanaged": len(unmanaged),
                "non_compliant": len(noncompliant),
                "distinct_device_ids": len(known_devices),
                "deviations": deviations,
            }
        )

    accounts.sort(key=lambda a: len(a["deviations"]), reverse=True)
    payload = {
        "analysis": "device_posture_analysis",
        "accounts_examined": len(accounts),
        "events_with_device_data": len(with_device),
        "accounts": accounts,
        "note": (
            "A posture deviation is an indicator, not a verdict. Correlate it with "
            "authentication sequence and velocity findings before calling it a takeover."
        ),
    }
    return json_block(payload)


DEVICE_POSTURE_SPEC = ToolSpec(
    tool_id="analyze_device_posture_v1",
    name="analyze_device_posture",
    description=(
        "Compare device attributes (managed/compliant state, OS, client, device id) of "
        "each sign-in against that same account's own historical baseline in the "
        "evidence store, and report deviations with citations. Useful for spotting "
        "session/token replay from attacker-controlled hardware."
    ),
    skills_provided=["device_posture_analysis", "identity_analysis", "anomaly_detection"],
    parameters={
        "user": {
            "type": "string",
            "description": "Optional account filter. Omit to analyse all accounts.",
        },
    },
    function=analyze_device_posture,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)
