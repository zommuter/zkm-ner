"""Tests for zkm_ner.patterns — pattern overlay extractors."""

from __future__ import annotations

from zkm_ner._types import Entity
from zkm_ner.patterns import (
    extract_emails,
    extract_github,
    extract_linkedin,
    extract_phones,
    extract_social_handles,
    extract_urls,
    extract_gazetteer,
    load_gazetteer,
)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def test_email_basic() -> None:
    ents = extract_emails("Contact us at hello@example.com for details.")
    assert len(ents) == 1
    assert ents[0].type == "email_address"
    assert ents[0].value == "hello@example.com"


def test_email_lowercased() -> None:
    ents = extract_emails("Reach me at Alice.Smith@Company.COM")
    assert ents[0].value == "alice.smith@company.com"


def test_email_has_span() -> None:
    body = "email: foo@bar.ch"
    ents = extract_emails(body)
    assert ents[0].start == body.index("foo@bar.ch")
    assert ents[0].end == ents[0].start + len("foo@bar.ch")


def test_email_multiple() -> None:
    ents = extract_emails("a@b.com and c@d.org")
    assert {e.value for e in ents} == {"a@b.com", "c@d.org"}


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------

def test_phone_swiss_local() -> None:
    ents = extract_phones("Ruf uns an: 044 123 45 67", region="CH")
    assert len(ents) == 1
    assert ents[0].type == "phone_number"
    assert ents[0].value.startswith("+41")


def test_phone_e164_format() -> None:
    ents = extract_phones("+49 30 12345678")
    assert ents[0].value == "+493012345678"


def test_phone_has_span() -> None:
    body = "Tel: +41 44 123 45 67"
    ents = extract_phones(body, region="CH")
    assert ents[0].start >= 0
    assert ents[0].end > ents[0].start


# ---------------------------------------------------------------------------
# URLs and org_hints
# ---------------------------------------------------------------------------

def test_url_basic() -> None:
    ents = extract_urls("Visit https://example.com for info.")
    url_ents = [e for e in ents if e.type == "url"]
    assert len(url_ents) == 1
    assert url_ents[0].value == "https://example.com"


def test_url_emits_org_hint() -> None:
    ents = extract_urls("See https://hetzner.com/pricing for prices.")
    types = {e.type for e in ents}
    assert "url" in types
    assert "org_hint" in types
    hints = [e.value for e in ents if e.type == "org_hint"]
    assert "hetzner.com" in hints


def test_url_strips_www_from_org_hint() -> None:
    ents = extract_urls("Go to https://www.cloudflare.com/")
    hints = [e.value for e in ents if e.type == "org_hint"]
    assert "cloudflare.com" in hints


def test_url_does_not_emit_duplicate_for_linkedin() -> None:
    # LinkedIn URLs must NOT appear as generic "url" entities (identity-strong)
    ents = extract_urls("Profile: https://linkedin.com/in/janedoe")
    url_ents = [e for e in ents if e.type == "url"]
    assert all("linkedin" not in e.value for e in url_ents)


# ---------------------------------------------------------------------------
# LinkedIn
# ---------------------------------------------------------------------------

def test_linkedin_basic() -> None:
    ents = extract_linkedin("See https://www.linkedin.com/in/john-doe for contact.")
    assert len(ents) == 1
    assert ents[0].type == "linkedin_profile"
    assert "linkedin.com/in/john-doe" in ents[0].value


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def test_github_profile() -> None:
    ents = extract_github("Author: https://github.com/torvalds")
    assert len(ents) == 1
    assert ents[0].type == "github_profile"


def test_github_repo_not_extracted() -> None:
    # Repo URL (two-segment path) must not be treated as a profile
    ents = extract_github("Code at https://github.com/org/repo")
    assert len(ents) == 0


# ---------------------------------------------------------------------------
# Social handles
# ---------------------------------------------------------------------------

def test_telegram_url() -> None:
    ents = extract_social_handles("Reach me on https://t.me/janedoe123")
    tg = [e for e in ents if e.type == "social_handle.telegram"]
    assert len(tg) >= 1
    assert "t.me/janedoe123" in tg[0].value


def test_telegram_bare_handle() -> None:
    ents = extract_social_handles("My Telegram is @maxmuster")
    tg = [e for e in ents if e.type == "social_handle.telegram"]
    assert any("@maxmuster" in e.value for e in tg)


def test_steam_url() -> None:
    ents = extract_social_handles("Steam: https://steamcommunity.com/id/gaben")
    steam = [e for e in ents if e.type == "social_handle.steam"]
    assert len(steam) == 1


def test_mastodon_handle() -> None:
    ents = extract_social_handles("Follow me: @alice@fosstodon.org")
    mastodon = [e for e in ents if e.type == "social_handle.mastodon"]
    assert len(mastodon) == 1
    assert "@alice@fosstodon.org" in mastodon[0].value


# ---------------------------------------------------------------------------
# Gazetteer
# ---------------------------------------------------------------------------

def test_gazetteer_canonical_name() -> None:
    entries = [{"canonical": "Proton AG", "type": "org", "aliases": ["Proton", "ProtonMail"]}]
    ents = extract_gazetteer("I use ProtonMail for email.", entries)
    assert any(e.value == "Proton AG" for e in ents)


def test_gazetteer_case_insensitive() -> None:
    entries = [{"canonical": "Hetzner Online GmbH", "type": "org", "aliases": ["hetzner"]}]
    ents = extract_gazetteer("Hosted on HETZNER servers.", entries)
    assert any(e.value == "Hetzner Online GmbH" for e in ents)


def test_gazetteer_no_partial_match() -> None:
    entries = [{"canonical": "Post", "type": "org", "aliases": ["Post"]}]
    # "Postfach" should not match "Post" alias due to word-boundary requirement
    ents = extract_gazetteer("Bitte an Postfach 100 senden.", entries)
    assert len(ents) == 0


def test_default_gazetteer_loads() -> None:
    entries = load_gazetteer()
    assert len(entries) > 0
    assert all("canonical" in e for e in entries)


# ---------------------------------------------------------------------------
# N9a regression — value whitespace normalization
# ---------------------------------------------------------------------------

def test_entity_value_strips_trailing_newlines() -> None:
    # Pilot surfaced values like 'sam\n\n' from spaCy ent.text spanning line ends.
    e = Entity("person", "sam\n\n")
    assert e.value == "sam"


def test_entity_value_strips_leading_and_trailing_whitespace() -> None:
    e = Entity("person", "  \n Alice Smith \n ")
    assert e.value == "Alice Smith"


# ---------------------------------------------------------------------------
# γ schema field tests
# ---------------------------------------------------------------------------

def test_entity_scope_defaults_to_body() -> None:
    e = Entity("person", "Alice")
    assert e.scope == "body"


def test_entity_scope_custom() -> None:
    e = Entity("email_address", "alice@example.com", scope="signature")
    assert e.scope == "signature"


def test_entity_canonical_none_by_default() -> None:
    e = Entity("phone_number", "+41 79 123 45 67")
    assert e.canonical is None
    assert e.standard is None
    assert e.unit is None
    assert e.valid is True


def test_entity_canonical_set_when_differs() -> None:
    e = Entity("phone_number", "079 123 45 67", canonical="+41791234567", standard="E.164")
    assert e.canonical == "+41791234567"
    assert e.standard == "E.164"


def test_entity_canonical_equals_value_raises() -> None:
    import pytest
    with pytest.raises(ValueError, match="canonical must differ from value"):
        Entity("email_address", "alice@example.com", canonical="alice@example.com")


def test_entity_valid_false() -> None:
    e = Entity("iban", "DE00123456780000000000", valid=False)
    assert e.valid is False


def test_entity_as_dict_minimal() -> None:
    e = Entity("person", "Alice")
    assert e.as_dict() == {"scope": "body", "type": "person", "value": "Alice"}


def test_entity_as_dict_with_canonical_and_standard() -> None:
    e = Entity("phone_number", "079 123 45 67", canonical="+41791234567", standard="E.164")
    d = e.as_dict()
    assert d["canonical"] == "+41791234567"
    assert d["standard"] == "E.164"
    assert "unit" not in d
    assert "valid" not in d


def test_entity_as_dict_with_unit() -> None:
    e = Entity("amount", "CHF 1'000.-", canonical="1000.00", standard="ISO 4217", unit="CHF")
    d = e.as_dict()
    assert d["unit"] == "CHF"


def test_entity_as_dict_valid_false_included() -> None:
    e = Entity("iban", "DE00123456780000000000", valid=False)
    assert e.as_dict()["valid"] is False


def test_entity_as_dict_valid_true_omitted() -> None:
    e = Entity("person", "Alice")
    assert "valid" not in e.as_dict()


def test_entity_as_dict_scope_included() -> None:
    e = Entity("person", "Alice", scope="signature")
    assert e.as_dict()["scope"] == "signature"
