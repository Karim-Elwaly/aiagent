"""
Unit tests for the DNS behaviour analytics and the de-hardcoded SOC tools.

All fixtures are synthetic (RFC 6761 .test / documentation ranges). The
analytics must flag encodings by their statistical shape — never by any
specific domain, keyword table, or dataset-flavoured filter.
"""

from __future__ import annotations

import json

import pytest

from src.core.evidence import EvidenceEvent, get_store
from src.registry.tools.dns_analytics import (
    _shannon_entropy,
    _split_domain,
    analyze_dns_patterns,
)
from src.registry.tools.soc_tools import (
    _parse_event_timestamp,
    compress_security_timeline,
    triage_security_alert,
)


def _payload(text: str) -> dict:
    if "```" in text:
        text = text.split("```json")[1].split("```")[0]
    return json.loads(text)


def _dns_event(ts: str, query: str, rtype: str = "A", status: str = "success", src: str = "10.9.9.9") -> EvidenceEvent:
    return EvidenceEvent(
        timestamp=ts,
        action="dns_query",
        event_code=rtype,
        status=status,
        src_ip=src,
        extra={"query": query},
    )


# ── primitives ───────────────────────────────────────────


def test_entropy_separates_words_from_encodings():
    assert _shannon_entropy("mail") < 2.1
    assert _shannon_entropy("aGVsbG8xOTk4N3F3ZXJ0eXVpb3A") > 3.5


def test_split_domain():
    assert _split_domain("chunk1.parent.test.") == ("parent.test", "chunk1")
    assert _split_domain("deep.sub.parent.test") == ("parent.test", "deep.sub")
    assert _split_domain("bare.test") == ("bare.test", "")


# ── tunneling ────────────────────────────────────────────


async def test_tunneling_flagged_by_label_statistics():
    store = get_store("dnsa-tunnel")
    events = [
        _dns_event(f"2031-05-01T10:00:{i:02d}", f"aGVsbG8xOTk4N3F3ZXJ0e{i}XVpb3Bhc2Rm.covert.test", rtype="TXT")
        for i in range(6)
    ]
    # benign background noise
    events += [
        _dns_event("2031-05-01T10:01:00", "www.normal.test"),
        _dns_event("2031-05-01T10:01:01", "mail.normal.test"),
    ]
    store.append(events)

    data = _payload(await analyze_dns_patterns(_run_id="dnsa-tunnel"))
    suspects = {t["domain"] for t in data["tunneling_suspects"]}
    assert "covert.test" in suspects
    assert "normal.test" not in suspects
    flagged = next(t for t in data["tunneling_suspects"] if t["domain"] == "covert.test")
    assert flagged["evidence"]  # every claim cited


async def test_hex_encoding_flagged():
    store = get_store("dnsa-hex")
    store.append(
        [
            _dns_event(f"2031-05-01T11:00:{i:02d}", f"deadbeef0102030405{i:02d}.drop.test")
            for i in range(5)
        ]
    )
    data = _payload(await analyze_dns_patterns(_run_id="dnsa-hex"))
    assert any(h["domain"] == "drop.test" for h in data["hex_encoded_exfil"])


async def test_dga_needs_many_failing_high_entropy_domains():
    store = get_store("dnsa-dga")
    events = []
    for i, name in enumerate(
        ["xk2v9qzp1m", "qw8rty4unb", "zx0cvb7nml", "pl3okm9ijn", "wsx4edc8rfv"]
    ):
        events.append(
            _dns_event(f"2031-05-01T12:00:{i:02d}", f"{name}{i}.test", status="failure")
        )
        events.append(
            _dns_event(f"2031-05-01T12:00:{i + 30:02d}", f"{name}{i}.test", status="failure")
        )
    store.append(events)
    data = _payload(await analyze_dns_patterns(_run_id="dnsa-dga"))
    assert data["dga"].get("candidate_domains", 0) >= 4


async def test_benign_corpus_produces_no_findings():
    store = get_store("dnsa-benign")
    store.append(
        [
            _dns_event(f"2031-05-01T13:00:{i:02d}", name)
            for i, name in enumerate(
                ["www.shop.test", "mail.shop.test", "cdn.shop.test", "api.shop.test",
                 "www.news.test", "img.news.test"]
            )
        ]
    )
    data = _payload(await analyze_dns_patterns(_run_id="dnsa-benign"))
    assert data["tunneling_suspects"] == []
    assert data["hex_encoded_exfil"] == []
    assert not data["dga"].get("candidates")


async def test_no_dns_telemetry_is_reported_as_gap():
    store = get_store("dnsa-none")
    store.append([EvidenceEvent(timestamp="2031-05-01T14:00:00", action="logon", user="u1")])
    out = await analyze_dns_patterns(_run_id="dnsa-none")
    assert "no DNS telemetry available" in out


# ── triage: data-driven vocabulary ───────────────────────


async def test_triage_scores_from_baseline_categories():
    out = await triage_security_alert(
        "Alert: mimikatz sekurlsa::logonpasswords observed on host"
    )
    assert "credential_theft_tooling" in out
    assert "CRITICAL" in out or "HIGH" in out


async def test_triage_link_local_detected_structurally():
    # The metadata-service indicator comes from the address class (link-local),
    # not from a hardcoded literal.
    out = await triage_security_alert(
        "GET http://169.254.170.2/latest/meta-data/iam/ returned credentials"
    )
    assert "cloud_metadata_service" in out


# ── timeline compression: generic salience ───────────────


def test_syslog_month_sorts_numerically():
    april = _parse_event_timestamp("Apr 02 10:00:00 host prog: x")
    august = _parse_event_timestamp("Aug 01 10:00:00 host prog: x")
    september = _parse_event_timestamp("Sep 14 10:00:00 host prog: x")
    assert april < august < september


async def test_compress_collapses_floods_and_keeps_chronology():
    flood = "\n".join(
        f"2031-06-01T10:00:{i:02d} fw: denied connection from 192.0.2.77" for i in range(40)
    )
    text = (
        "2031-06-01T09:59:00 auth: Failed password for admin\n"
        + flood
        + "\n2031-06-01T10:05:00 av: ransomware signature detected in file\n"
    )
    out = await compress_security_timeline(text, max_timeline_events=10)
    assert "=== [COMPRESSED INCIDENT TIMELINE] ===" in out
    # 40 identical denies collapse into one milestone carrying its count
    assert "(x40 occurrences)" in out
    # chronology: the auth failure precedes the ransomware hit
    assert out.index("Failed password") < out.index("ransomware")


async def test_compress_falls_back_to_even_sampling():
    text = "\n".join(f"line {i} routine heartbeat" for i in range(100))
    out = await compress_security_timeline(text, max_timeline_events=5)
    assert "Step 01:" in out
    # even sampling spans the corpus, not just its head
    assert "line 0 " in out or "line 0\n" in out or "line 0" in out
    assert any(f"line {i}" in out for i in range(50, 100))
