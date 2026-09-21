"""
Unit tests for the identity analytics tools.

Fixtures here are synthetic and independently authored: addresses come from the
TEST-NET-1 documentation block (RFC 5737) and RFC 1918 space, with account names
and timestamps invented for these tests. They exercise pattern CLASSES (spray,
brute force, MFA fatigue, typo, impossible travel, carrier rotation) and are not
derived from any benchmark dataset.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.core.evidence import DeviceContext, EvidenceEvent, GeoContext, get_store
from src.registry.tools.identity_analytics import (
    actor_pivot,
    analyze_auth_sequences,
    analyze_device_posture,
    analyze_identity_velocity,
)

RUN = "test-identity"
BASE = datetime(2031, 5, 4, 9, 0, 0, tzinfo=timezone.utc)


def at(seconds: int) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def auth(
    *,
    offset: int,
    user: str,
    status: str,
    src_ip: str = "192.0.2.50",
    action: str = "signin",
    error_code: str = "",
    geo: GeoContext | None = None,
    device: DeviceContext | None = None,
) -> EvidenceEvent:
    return EvidenceEvent(
        timestamp=at(offset),
        user=user,
        src_ip=src_ip,
        status=status,
        action=action,
        error_code=error_code,
        source_type="synthetic_idp",
        geo=geo or GeoContext(),
        device=device or DeviceContext(),
    )


def store_with(events: list[EvidenceEvent], run: str):
    store = get_store(run)
    store.append(events)
    return store


def payload(result: str) -> dict:
    body = result.split("```json", 1)[1].rsplit("```", 1)[0]
    return json.loads(body)


# ── password spray ───────────────────────────────────────


async def test_password_spray_detected_across_accounts():
    events = [
        auth(offset=i * 20, user=f"user{i}", status="failure") for i in range(5)
    ]
    store_with(events, "spray-run")

    result = await analyze_auth_sequences(_run_id="spray-run")
    data = payload(result)

    patterns = [f["pattern"] for f in data["findings"]]
    assert "password_spray" in patterns
    spray = next(f for f in data["findings"] if f["pattern"] == "password_spray")
    assert len(spray["accounts_targeted"]) == 5
    assert all(e.startswith("EV-") for e in spray["evidence"])


async def test_success_after_failure_burst_is_reported_as_compromise():
    events = [auth(offset=i * 20, user=f"user{i}", status="failure") for i in range(5)]
    events.append(auth(offset=200, user="user3", status="success"))
    store_with(events, "spray-success-run")

    data = payload(await analyze_auth_sequences(_run_id="spray-success-run"))
    compromise = [
        f
        for f in data["findings"]
        if f["pattern"] == "successful_authentication_after_failure_burst"
    ]
    assert compromise, "the success following a failure burst must be surfaced"
    assert compromise[0]["accounts_compromised"] == ["user3"]


# ── brute force ──────────────────────────────────────────


async def test_brute_force_against_single_account():
    events = [
        auth(offset=i * 15, user="rwhitfield", status="failure") for i in range(6)
    ]
    store_with(events, "brute-run")

    data = payload(await analyze_auth_sequences(_run_id="brute-run"))
    patterns = [f["pattern"] for f in data["findings"]]
    assert "brute_force" in patterns
    assert "password_spray" not in patterns


# ── benign typo ──────────────────────────────────────────


async def test_single_failure_then_success_classified_benign():
    events = [
        auth(offset=0, user="tnguyen", status="failure"),
        auth(offset=30, user="tnguyen", status="success"),
    ]
    store_with(events, "typo-run")

    data = payload(await analyze_auth_sequences(_run_id="typo-run"))
    assert data["benign_explanations"], "a self-corrected typo must be explained as benign"
    assert data["benign_explanations"][0]["pattern"] == "credential_typo_self_corrected"


# ── MFA fatigue ──────────────────────────────────────────


async def test_mfa_fatigue_followed_by_approval():
    events = [
        auth(
            offset=i * 30,
            user="kobrien",
            status="denied",
            error_code="500121",
        )
        for i in range(4)
    ]
    events.append(auth(offset=150, user="kobrien", status="success"))
    store_with(events, "fatigue-run")

    data = payload(await analyze_auth_sequences(_run_id="fatigue-run"))
    fatigue = [f for f in data["findings"] if f["pattern"] == "mfa_fatigue_succeeded"]
    assert fatigue, "an approval after a denial storm is the compromise moment"
    assert fatigue[0]["denials"] >= 3


async def test_mfa_fatigue_without_approval_is_attempt_only():
    events = [
        auth(offset=i * 30, user="kobrien", status="denied", error_code="500121")
        for i in range(4)
    ]
    store_with(events, "fatigue-fail-run")

    data = payload(await analyze_auth_sequences(_run_id="fatigue-fail-run"))
    patterns = [f["pattern"] for f in data["findings"]]
    assert "mfa_fatigue_attempted" in patterns
    assert "mfa_fatigue_succeeded" not in patterns


# ── empty / negative results ─────────────────────────────


async def test_empty_store_refuses_to_analyse():
    result = await analyze_auth_sequences(_run_id="empty-auth-run")
    assert "ingest_logs" in result
    assert "empty" in result.lower()


# ── velocity ─────────────────────────────────────────────


def geo(lat: float, lon: float, country: str, asn: str = "") -> GeoContext:
    return GeoContext(latitude=lat, longitude=lon, country=country, asn=asn)


async def test_impossible_travel_detected():
    events = [
        auth(
            offset=0,
            user="mdelacroix",
            status="success",
            src_ip="192.0.2.11",
            geo=geo(51.5, -0.12, "GB"),
        ),
        auth(
            offset=1800,
            user="mdelacroix",
            status="success",
            src_ip="192.0.2.12",
            geo=geo(-33.87, 151.21, "AU"),
        ),
    ]
    store_with(events, "velocity-run")

    data = payload(await analyze_identity_velocity(_run_id="velocity-run"))
    assert data["findings"], "16000 km in 30 minutes must be impossible travel"
    assert data["findings"][0]["pattern"] == "impossible_travel"


async def test_same_operator_regional_rotation_is_suppressed():
    events = [
        auth(
            offset=0,
            user="jhalvorsen",
            status="success",
            src_ip="192.0.2.21",
            geo=geo(40.71, -74.0, "US", asn="AS64500"),
        ),
        auth(
            offset=600,
            user="jhalvorsen",
            status="success",
            src_ip="192.0.2.22",
            geo=geo(40.0, -75.1, "US", asn="AS64500"),
        ),
    ]
    store_with(events, "carrier-run")

    data = payload(await analyze_identity_velocity(_run_id="carrier-run"))
    assert not data["findings"], "same-operator regional rotation is not travel"
    assert data["suppressed_benign"]


async def test_events_without_geo_are_counted_not_guessed():
    events = [
        auth(offset=0, user="pfeldman", status="success"),
        auth(offset=60, user="pfeldman", status="success"),
    ]
    store_with(events, "nogeo-run")

    data = payload(await analyze_identity_velocity(_run_id="nogeo-run"))
    assert data["events_without_geolocation"] == 2
    assert not data["findings"]


# ── actor pivot ──────────────────────────────────────────


async def test_actor_pivot_separates_successful_from_failed_accounts():
    events = [
        auth(offset=0, user="a.one", status="failure", src_ip="192.0.2.77"),
        auth(offset=30, user="b.two", status="failure", src_ip="192.0.2.77"),
        auth(offset=60, user="c.three", status="success", src_ip="192.0.2.77"),
        auth(offset=90, user="d.four", status="success", src_ip="192.0.2.90"),
    ]
    store_with(events, "pivot-run")

    data = payload(await actor_pivot("192.0.2.77", _run_id="pivot-run"))
    assert data["accounts_authenticated_successfully"] == ["c.three"]
    assert set(data["accounts_failed_authentication"]) == {"a.one", "b.two"}
    assert "d.four" not in data["accounts_seen"]


async def test_actor_pivot_unknown_entity_is_refused():
    store_with([auth(offset=0, user="a.one", status="success")], "pivot-empty-run")

    result = await actor_pivot("192.0.2.254", _run_id="pivot-empty-run")
    assert "No evidence references" in result
    assert "containment target" in result


# ── device posture ───────────────────────────────────────


async def test_unmanaged_device_deviation_reported():
    managed = DeviceContext(os="Windows", is_managed=True, is_compliant=True)
    rogue = DeviceContext(os="Linux", is_managed=False, is_compliant=False)
    events = [
        auth(offset=0, user="sbalewa", status="success", device=managed),
        auth(offset=60, user="sbalewa", status="success", device=managed),
        auth(offset=120, user="sbalewa", status="success", device=rogue),
    ]
    store_with(events, "posture-run")

    data = payload(await analyze_device_posture(_run_id="posture-run"))
    account = data["accounts"][0]
    kinds = {d["type"] for d in account["deviations"]}
    assert "unmanaged_device_for_normally_managed_account" in kinds
    assert "non_compliant_device" in kinds


async def test_device_posture_absent_reports_not_available():
    store_with([auth(offset=0, user="sbalewa", status="success")], "posture-none-run")

    result = await analyze_device_posture(_run_id="posture-none-run")
    assert "not available in the provided telemetry" in result
