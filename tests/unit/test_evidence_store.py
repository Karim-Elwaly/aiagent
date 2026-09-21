"""Unit tests for the evidence store (Phase A1).

Fixtures use documentation-range addresses and invented account names that are
unrelated to any benchmark dataset, per the anti-overfit charter.
"""

from __future__ import annotations

import pytest

from src.core.evidence import (
    EVIDENCE_ID_PATTERN,
    DeviceContext,
    EvidenceEvent,
    EvidenceStore,
    parse_timestamp,
)


@pytest.fixture()
def store(tmp_path):
    return EvidenceStore("test-run", root=tmp_path)


def _event(**kwargs) -> EvidenceEvent:
    defaults = {
        "source_file": "auth.log",
        "source_type": "generic_json",
        "timestamp": "2031-03-02T08:00:00",
        "raw_excerpt": "sample line",
    }
    defaults.update(kwargs)
    return EvidenceEvent(**defaults)


class TestAppendAndRead:
    def test_assigns_sequential_citation_ids(self, store):
        stored = store.append([_event(user="rlopez"), _event(user="tmehta")])

        assert [e.ev_id for e in stored] == ["EV-000001", "EV-000002"]
        assert all(EVIDENCE_ID_PATTERN.fullmatch(e.ev_id) for e in stored)

    def test_ids_continue_across_separate_appends(self, store):
        store.append([_event(user="rlopez")])
        second = store.append([_event(user="tmehta")])

        assert second[0].ev_id == "EV-000002"
        assert store.count() == 2

    def test_round_trip_preserves_fields(self, store):
        store.append(
            [
                _event(
                    user="rlopez",
                    host="ws-104",
                    src_ip="203.0.113.7",
                    dst_port=8443,
                    hashes={"sha256": "a" * 64},
                    device=DeviceContext(browser="Firefox", is_compliant=False),
                )
            ]
        )

        loaded = store.all_events()[0]
        assert loaded.user == "rlopez"
        assert loaded.dst_port == 8443
        assert loaded.hashes["sha256"] == "a" * 64
        assert loaded.device.is_compliant is False

    def test_append_empty_is_noop(self, store):
        assert store.append([]) == []
        assert store.count() == 0

    def test_no_record_cap(self, store):
        """Regression guard: the store must never silently drop evidence."""
        store.append([_event(user=f"user{i}") for i in range(500)])
        assert store.count() == 500


class TestQuery:
    @pytest.fixture()
    def populated(self, store):
        store.append(
            [
                _event(user="rlopez", src_ip="203.0.113.7", status="failure", event_code="4625"),
                _event(user="rlopez", src_ip="203.0.113.7", status="success", event_code="4624"),
                _event(user="tmehta", src_ip="198.51.100.8", status="success", event_code="4624"),
                _event(host="srv-analytics", dst_ip="192.0.2.30", dst_port=8443, status="allow"),
            ]
        )
        return store

    def test_filter_by_user(self, populated):
        page, total = populated.query(user="rlopez")
        assert total == 2

    def test_filter_by_ip_matches_source_or_destination(self, populated):
        _, src_total = populated.query(ip="203.0.113.7")
        _, dst_total = populated.query(ip="192.0.2.30")
        assert src_total == 2
        assert dst_total == 1

    def test_filters_are_and_combined(self, populated):
        _, total = populated.query(user="rlopez", status="failure")
        assert total == 1

    def test_filter_by_port_and_code(self, populated):
        _, port_total = populated.query(dst_port=8443)
        _, code_total = populated.query(event_code="4624")
        assert port_total == 1
        assert code_total == 2

    def test_keyword_searches_raw_text(self, populated):
        _, total = populated.query(keyword="sample line")
        assert total == 4

    def test_pagination_reports_full_total(self, populated):
        page, total = populated.query(limit=2, offset=0)
        page2, _ = populated.query(limit=2, offset=2)

        assert len(page) == 2
        assert total == 4  # total is the match count, not the page size
        assert {e.ev_id for e in page}.isdisjoint({e.ev_id for e in page2})

    def test_time_range_filter(self, store):
        store.append(
            [
                _event(timestamp="2031-03-02T08:00:00"),
                _event(timestamp="2031-03-02T12:00:00"),
            ]
        )
        _, total = store.query(time_from="2031-03-02T10:00:00")
        assert total == 1

    def test_no_match_returns_empty(self, populated):
        page, total = populated.query(user="nobody")
        assert page == [] and total == 0


class TestRetrieval:
    def test_get_by_citation_id(self, store):
        store.append([_event(user="rlopez"), _event(user="tmehta")])

        found = store.get(["EV-000002"])
        assert len(found) == 1
        assert found[0].user == "tmehta"

    def test_get_ignores_unknown_ids(self, store):
        store.append([_event(user="rlopez")])
        assert store.get(["EV-999999"]) == []


class TestStats:
    def test_counts_are_authoritative(self, store):
        store.append(
            [
                _event(source_type="a", host="ws-104", user="rlopez", status="failure"),
                _event(source_type="a", host="ws-104", user="rlopez", status="failure"),
                _event(source_type="b", host="srv-analytics", user="tmehta", status="success"),
            ]
        )

        stats = store.stats()
        assert stats["total_events"] == 3
        assert stats["events_by_source_type"] == {"a": 2, "b": 1}
        assert stats["events_by_status"] == {"failure": 2, "success": 1}
        assert stats["distinct_hosts"] == ["srv-analytics", "ws-104"]
        assert stats["distinct_users"] == ["rlopez", "tmehta"]

    def test_time_bounds(self, store):
        store.append(
            [
                _event(timestamp="2031-03-02T12:00:00"),
                _event(timestamp="2031-03-02T08:00:00"),
            ]
        )
        stats = store.stats()
        assert stats["earliest_timestamp"] == "2031-03-02T08:00:00"
        assert stats["latest_timestamp"] == "2031-03-02T12:00:00"

    def test_write_index_persists(self, store):
        store.append([_event()])
        store.write_index()
        assert store.index_path.exists()

    def test_empty_store_stats(self, store):
        assert store.stats()["total_events"] == 0


class TestKnownEntities:
    def test_collects_entities_for_verification(self, store):
        store.append(
            [
                _event(
                    host="ws-104",
                    user="rlopez",
                    src_ip="203.0.113.7",
                    hashes={"sha256": "b" * 64},
                )
            ]
        )

        entities = store.known_entities()
        assert "203.0.113.7" in entities["ips"]
        assert "ws-104" in entities["hosts"]
        assert "rlopez" in entities["users"]
        assert "b" * 64 in entities["hashes"]

    def test_absent_entity_is_not_reported_as_known(self, store):
        """This is what lets the verifier catch an invented host."""
        store.append([_event(host="ws-104")])
        assert "ws-999" not in store.known_entities()["hosts"]


class TestTimestampParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2031-03-02T08:00:00Z", "2031-03-02T08:00:00+00:00"),
            ("2031-03-02 08:00:00", "2031-03-02T08:00:00"),
            ("2031/03/02 08:00:00", "2031-03-02T08:00:00"),
        ],
    )
    def test_normalizes_known_formats(self, raw, expected):
        assert parse_timestamp(raw) == expected

    def test_unparseable_value_is_preserved_not_invented(self, store):
        assert parse_timestamp("week 14 shift B") == "week 14 shift B"

    def test_empty_input(self):
        assert parse_timestamp(None) == ""
        assert parse_timestamp("") == ""


class TestSummary:
    def test_summary_is_prefixed_with_citation_id(self, store):
        stored = store.append([_event(user="rlopez", host="ws-104")])
        assert stored[0].summary().startswith("[EV-000001]")

    def test_summary_respects_max_length(self, store):
        stored = store.append([_event(command_line="x" * 500, user="rlopez")])
        assert len(stored[0].summary(max_chars=80)) <= 80


class TestRunIsolation:
    def test_runs_do_not_share_evidence(self, tmp_path):
        first = EvidenceStore("run-a", root=tmp_path)
        second = EvidenceStore("run-b", root=tmp_path)

        first.append([_event(user="rlopez")])

        assert first.count() == 1
        assert second.count() == 0

    def test_unsafe_run_id_is_sanitized(self, tmp_path):
        store = EvidenceStore("../../escape attempt", root=tmp_path)
        store.append([_event()])

        assert store.dir.parent == tmp_path
        assert store.count() == 1
