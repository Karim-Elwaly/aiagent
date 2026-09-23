"""Unit tests for the resilience/outage-tolerance profiles."""

from src.core.resilience import (
    BRIEF,
    DEFAULT_RESILIENCE,
    EXTENDED,
    STANDARD,
    UNLIMITED,
    all_profiles,
    client_retry_budget,
    get_profile,
    normalize_level,
)


def test_normalize_level_defaults_on_unknown():
    assert normalize_level(None) == DEFAULT_RESILIENCE
    assert normalize_level("") == DEFAULT_RESILIENCE
    assert normalize_level("nonsense") == DEFAULT_RESILIENCE


def test_normalize_level_is_case_insensitive():
    assert normalize_level("BRIEF") == BRIEF
    assert normalize_level("  Standard  ") == STANDARD


def test_get_profile_returns_matching_level():
    for level in (BRIEF, STANDARD, EXTENDED, UNLIMITED):
        assert get_profile(level).level == level


def test_outage_tolerance_increases_with_level():
    brief = get_profile(BRIEF)
    standard = get_profile(STANDARD)
    extended = get_profile(EXTENDED)
    # More attempts for longer outages.
    assert brief.max_attempts < standard.max_attempts < extended.max_attempts


def test_unlimited_has_unbounded_attempts():
    assert get_profile(UNLIMITED).max_attempts == 0


def test_all_profiles_ordered_by_tolerance():
    levels = [p.level for p in all_profiles()]
    assert levels == [BRIEF, STANDARD, EXTENDED, UNLIMITED]


def test_max_interval_caps_backoff_for_every_profile():
    for p in all_profiles():
        assert p.max_interval_seconds > 0
        assert p.backoff_coefficient >= 1.0


def test_client_budget_is_smaller_than_activity_attempts():
    # The client sits inside an activity attempt, so it uses a smaller share.
    retries, initial, backoff, max_interval = client_retry_budget(STANDARD)
    assert retries >= 1
    assert retries <= get_profile(STANDARD).max_attempts
    assert initial > 0
    assert backoff >= 1.0
    assert max_interval > 0


def test_client_budget_unlimited_is_finite():
    retries, *_ = client_retry_budget(UNLIMITED)
    assert 0 < retries < 1_000
