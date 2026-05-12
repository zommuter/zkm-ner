"""Tests for the suspicious predicate dispatch table (E4)."""

from __future__ import annotations

import pytest

from zkm_ner.suspicious import is_suspicious


# ---------------------------------------------------------------------------
# NER-derived types — name-shape heuristics apply
# ---------------------------------------------------------------------------


def test_person_lowercase_is_suspicious():
    assert is_suspicious("person", "klicken Sie") == "person value starts lowercase"


def test_person_clean_name_not_suspicious():
    assert is_suspicious("person", "Alice Smith") is None


def test_misc_single_token_is_suspicious():
    reason = is_suspicious("misc", "Download")
    assert reason == "single-token MISC (highest noise rate)"


def test_misc_multi_word_not_flagged_for_single_token():
    assert is_suspicious("misc", "Best Regards") is None


def test_org_short_value_is_suspicious():
    reason = is_suspicious("org", "EU")
    assert reason is not None and "very short" in reason


def test_org_clean_name_not_suspicious():
    assert is_suspicious("org", "Swiss Federal Railways") is None


def test_loc_allcaps_is_suspicious():
    reason = is_suspicious("loc", "BUNDESHAUS")
    assert reason is not None and "all-caps" in reason


# ---------------------------------------------------------------------------
# Pattern-overlay types — always None
# ---------------------------------------------------------------------------


def test_email_address_not_suspicious():
    assert is_suspicious("email_address", "x@y.com") is None


@pytest.mark.parametrize("etype", [
    "phone_number",
    "url",
    "org_hint",
    "linkedin_profile",
    "github_profile",
])
def test_pattern_overlay_types_return_none(etype):
    assert is_suspicious(etype, "somevalue") is None


def test_social_handle_prefix_returns_none():
    assert is_suspicious("social_handle.discord", "@foo#1234") is None


def test_social_handle_telegram_returns_none():
    assert is_suspicious("social_handle.telegram", "https://t.me/foo") is None


# ---------------------------------------------------------------------------
# Future value-type stubs (E6/E7)
# ---------------------------------------------------------------------------


def test_iban_stub_returns_none():
    assert is_suspicious("iban", "CH56 0483 5012 3456 7800 9") is None


def test_amount_stub_returns_none():
    assert is_suspicious("amount", "CHF 1'000.00") is None


@pytest.mark.parametrize("etype", ["invoice_id", "tracking_id", "registration_code"])
def test_future_value_type_stubs_return_none(etype):
    assert is_suspicious(etype, "INV-2026-001") is None


# ---------------------------------------------------------------------------
# Unknown type fallback
# ---------------------------------------------------------------------------


def test_unknown_type_falls_back_to_name_predicate():
    reason = is_suspicious("new_type", "A")
    assert reason is not None and "very short" in reason


def test_unknown_type_clean_value_not_suspicious():
    assert is_suspicious("new_type", "Some Value") is None
