"""Tests for _pos_filter — N9c-1: POS-gate on spaCy NER outputs."""

from zkm_ner._types import Entity
from zkm_ner.extract import _pos_filter


def _ent(value: str, root_pos: str) -> Entity:
    e = Entity(type="person", value=value)
    e.root_pos = root_pos
    return e


def test_propn_passes():
    assert _pos_filter(_ent("Alice", "PROPN")) is True


def test_noun_blocked():
    assert _pos_filter(_ent("Zeit", "NOUN")) is False


def test_verb_blocked():
    assert _pos_filter(_ent("wünschen", "VERB")) is False


def test_pron_blocked():
    assert _pos_filter(_ent("Du", "PRON")) is False


def test_empty_root_pos_passes():
    """Pattern-overlay entities have root_pos='' and must always pass."""
    e = Entity(type="email_address", value="alice@example.com")
    assert e.root_pos == ""
    assert _pos_filter(e) is True


def test_extract_filters_common_noun():
    """Integration: extract() with a German text should not return 'Zeit' as an entity."""
    from zkm_ner.extract import extract

    # 'Zeit' in running prose is NOUN; the POS filter should block it.
    body = "Ich habe keine Zeit für dich."
    entities = extract(body, lang="de")
    values = [e.value for e in entities]
    assert "Zeit" not in values
