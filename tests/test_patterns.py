"""Tests for zkm_ner.patterns — pattern overlay extractors."""

from __future__ import annotations

from zkm_ner._types import Entity
from zkm_ner.patterns import (
    extract_emails,
    extract_github,
    extract_invoice_ids,
    extract_linkedin,
    extract_phones,
    extract_registration_codes,
    extract_social_handles,
    extract_tracking_ids,
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
    assert ents[0].standard == "rfc5321"
    assert ents[0].canonical is None  # already domain-lowercase, no canonical needed


def test_email_uppercase_domain_sets_canonical() -> None:
    ents = extract_emails("Reach me at Alice.Smith@Company.COM")
    assert ents[0].value == "Alice.Smith@Company.COM"  # raw preserved
    assert ents[0].canonical == "Alice.Smith@company.com"  # domain lowercased (RFC 5321)
    assert ents[0].standard == "rfc5321"


def test_email_already_normalized_no_canonical() -> None:
    ents = extract_emails("user@example.org")
    assert ents[0].value == "user@example.org"
    assert ents[0].canonical is None


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
    assert ents[0].value == "044 123 45 67"       # raw preserved
    assert ents[0].canonical is not None
    assert ents[0].canonical.startswith("+41")     # E.164
    assert ents[0].standard == "E.164"


def test_phone_e164_format() -> None:
    ents = extract_phones("+49 30 12345678")
    assert ents[0].value == "+49 30 12345678"      # raw preserved
    assert ents[0].canonical == "+493012345678"    # compact E.164
    assert ents[0].standard == "E.164"


def test_phone_already_compact_e164_no_canonical() -> None:
    ents = extract_phones("+493012345678")
    assert ents[0].value == "+493012345678"
    assert ents[0].canonical is None


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
    assert url_ents[0].standard == "rfc3986"


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


# ---------------------------------------------------------------------------
# Invoice IDs
# ---------------------------------------------------------------------------

def test_invoice_id_keyword_rechnungsnummer() -> None:
    ents = extract_invoice_ids("Rechnungsnummer: RE-2024-001234")
    assert len(ents) == 1
    assert ents[0].type == "invoice_id"
    assert ents[0].value == "RE-2024-001234"


def test_invoice_id_keyword_invoice_no() -> None:
    ents = extract_invoice_ids("Invoice No. INV-2024-001")
    assert len(ents) == 1
    assert ents[0].value == "INV-2024-001"


def test_invoice_id_no_keyword_no_match() -> None:
    ents = extract_invoice_ids("Order AB-2024-001 has been shipped.")
    assert len(ents) == 0


def test_invoice_id_has_span() -> None:
    body = "Rechnungsnr. 20240001"
    ents = extract_invoice_ids(body)
    assert len(ents) == 1
    assert ents[0].start == body.index("20240001")


def test_invoice_id_belegnummer() -> None:
    ents = extract_invoice_ids("Belegnummer: 2024-RG-0099")
    assert len(ents) == 1
    assert ents[0].value == "2024-RG-0099"


# ---------------------------------------------------------------------------
# Tracking IDs
# ---------------------------------------------------------------------------

def test_tracking_id_ups() -> None:
    ents = extract_tracking_ids("Your tracking number: 1Z999AA10123456784")
    assert len(ents) == 1
    assert ents[0].type == "tracking_id"
    assert ents[0].value == "1Z999AA10123456784"


def test_tracking_id_dhl_intl() -> None:
    ents = extract_tracking_ids("DHL tracking: JD014600006635122948")
    assert len(ents) == 1
    assert ents[0].value == "JD014600006635122948"


def test_tracking_id_swiss_post() -> None:
    ents = extract_tracking_ids("Sendungsnummer: 990002003001009052")
    assert len(ents) == 1
    assert ents[0].value == "990002003001009052"


def test_tracking_id_no_false_positive_short_number() -> None:
    ents = extract_tracking_ids("Bitte rufen Sie 044 123 45 67 an.")
    assert len(ents) == 0


def test_tracking_id_has_span() -> None:
    body = "Track: 1Z999AA10123456784 online."
    ents = extract_tracking_ids(body)
    assert ents[0].start == body.index("1Z999AA10123456784")


# ---------------------------------------------------------------------------
# Registration codes
# ---------------------------------------------------------------------------

def test_registration_code_hrb() -> None:
    ents = extract_registration_codes("Amtsgericht München, HRB 12345")
    assert len(ents) == 1
    assert ents[0].type == "registration_code"
    assert ents[0].value == "HRB 12345"


def test_registration_code_hrb_with_city() -> None:
    ents = extract_registration_codes("Registriert: HRB 98765 Frankfurt")
    assert len(ents) == 1
    assert "HRB" in ents[0].value and "98765" in ents[0].value


def test_registration_code_hra() -> None:
    ents = extract_registration_codes("HRA 555 Berlin")
    assert len(ents) == 1
    assert ents[0].value.startswith("HRA")


def test_registration_code_isbn() -> None:
    ents = extract_registration_codes("ISBN 978-3-16-148410-0")
    assert len(ents) == 1
    assert ents[0].standard == "ISBN-13"
    assert ents[0].canonical == "9783161484100"


def test_registration_code_isbn_compact() -> None:
    ents = extract_registration_codes("ISBN 9783161484100")
    assert len(ents) == 1
    assert ents[0].standard == "ISBN-13"


def test_registration_code_din() -> None:
    ents = extract_registration_codes("Zertifiziert nach DIN EN ISO 9001")
    assert len(ents) == 1
    assert ents[0].value.startswith("DIN")


def test_registration_code_ean13_keyword() -> None:
    ents = extract_registration_codes("EAN-13: 4006381333931")
    assert len(ents) == 1
    assert ents[0].value == "4006381333931"
    assert ents[0].standard == "EAN-13"


def test_registration_code_ean_no_keyword_no_match() -> None:
    ents = extract_registration_codes("Code 4006381333931 on the package")
    assert len(ents) == 0
