"""Tests for zkm_ner.verifier — LLM entity false-positive checker.

All LLM calls are mocked via unittest.mock; no network access required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_store

sys_path_patched = __import__("sys")
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from zkm_ner.verifier import _parse_verdict, verify
from zkm.extraction_cache import ExtractionCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    return resp


def _make_cache(tmp_path) -> ExtractionCache:
    store = make_store(tmp_path)
    return ExtractionCache(store, extractor_name="ner_verifier")


# ---------------------------------------------------------------------------
# _parse_verdict unit tests
# ---------------------------------------------------------------------------

def test_parse_verdict_yes_returns_keep():
    assert _parse_verdict("YES") == "keep"


def test_parse_verdict_no_returns_drop():
    assert _parse_verdict("NO") == "drop"


def test_parse_verdict_unclear_returns_unclear():
    assert _parse_verdict("UNCLEAR") == "unclear"


def test_parse_verdict_case_insensitive():
    assert _parse_verdict("yes.") == "keep"
    assert _parse_verdict("no,") == "drop"
    assert _parse_verdict("Unclear") == "unclear"


def test_parse_verdict_malformed_returns_unclear():
    assert _parse_verdict("maybe") == "unclear"
    assert _parse_verdict("") == "unclear"
    assert _parse_verdict(None) == "unclear"


def test_parse_verdict_strips_aya_control_token():
    """aya-expanse appends <|END_OF_TURN_TOKEN|>; parser must strip it."""
    assert _parse_verdict("YES<|END_OF_TURN_TOKEN|>") == "keep"
    assert _parse_verdict("NO<|END_OF_TURN_TOKEN|>") == "drop"
    assert _parse_verdict("UNCLEAR<|END_OF_TURN_TOKEN|>") == "unclear"


# ---------------------------------------------------------------------------
# verify() integration tests
# ---------------------------------------------------------------------------

def test_verify_tier1_yes_returns_keep(tmp_path):
    cache = _make_cache(tmp_path)
    with patch("httpx.post", return_value=_mock_response("YES")) as mock_post:
        result = verify("guten morgen", "person", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
    assert result == "keep"
    mock_post.assert_called_once()


def test_verify_tier1_no_returns_drop(tmp_path):
    cache = _make_cache(tmp_path)
    with patch("httpx.post", return_value=_mock_response("NO")) as mock_post:
        result = verify("guten morgen", "person", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
    assert result == "drop"
    mock_post.assert_called_once()


def test_verify_tier1_unclear_no_context_returns_unclear(tmp_path):
    """UNCLEAR with no context → unclear without escalating to Tier 2."""
    cache = _make_cache(tmp_path)
    with patch("httpx.post", return_value=_mock_response("UNCLEAR")) as mock_post:
        result = verify("XYZ", "misc", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
    assert result == "unclear"
    mock_post.assert_called_once()  # only Tier 1 called


def test_verify_tier1_unclear_with_context_escalates_to_tier2(tmp_path):
    """UNCLEAR with context → Tier 2 call; result from Tier 2 is returned."""
    cache = _make_cache(tmp_path)
    responses = [_mock_response("UNCLEAR"), _mock_response("NO")]
    with patch("httpx.post", side_effect=responses) as mock_post:
        result = verify(
            "XYZ", "misc",
            model="aya", endpoint="http://localhost:8080", api_key="",
            context="This document mentions XYZ in a boilerplate footer.",
            cache=cache,
        )
    assert result == "drop"
    assert mock_post.call_count == 2  # Tier 1 + Tier 2


def test_verify_tier2_yes_returns_keep(tmp_path):
    """Tier 2 YES → keep."""
    cache = _make_cache(tmp_path)
    with patch("httpx.post", side_effect=[_mock_response("UNCLEAR"), _mock_response("YES")]):
        result = verify(
            "Heiko", "person",
            model="aya", endpoint="http://localhost:8080", api_key="",
            context="Heiko Maas ist ein Politiker.",
            cache=cache,
        )
    assert result == "keep"


def test_verify_tier2_unclear_returns_unclear(tmp_path):
    """Tier 2 UNCLEAR → unclear."""
    cache = _make_cache(tmp_path)
    with patch("httpx.post", side_effect=[_mock_response("UNCLEAR"), _mock_response("UNCLEAR")]):
        result = verify(
            "abc", "misc",
            model="aya", endpoint="http://localhost:8080", api_key="",
            context="Some context.",
            cache=cache,
        )
    assert result == "unclear"


def test_verify_cache_hit_short_circuits_llm(tmp_path):
    """A cached verdict is returned without any LLM call."""
    cache = _make_cache(tmp_path)
    # Prime the cache
    with patch("httpx.post", return_value=_mock_response("NO")):
        verify("guten morgen", "person", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)

    # Second call: no httpx.post should be invoked
    with patch("httpx.post") as mock_post:
        result = verify("guten morgen", "person", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
    assert result == "drop"
    mock_post.assert_not_called()


def test_verify_timeout_returns_unclear(tmp_path):
    """Network timeout → 'unclear' (safe fallback — never drops on error)."""
    import httpx as _httpx
    cache = _make_cache(tmp_path)
    with patch("httpx.post", side_effect=_httpx.TimeoutException("timed out")):
        result = verify("abc", "misc", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
    assert result == "unclear"


def test_verify_http_error_returns_unclear(tmp_path):
    """HTTP error → 'unclear' (safe fallback)."""
    import httpx as _httpx
    cache = _make_cache(tmp_path)
    with patch("httpx.post", side_effect=_httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())):
        result = verify("abc", "misc", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
    assert result == "unclear"


def test_verify_different_values_have_independent_caches(tmp_path):
    """(value_A, type) and (value_B, type) are cached under different keys."""
    cache = _make_cache(tmp_path)
    with patch("httpx.post", side_effect=[_mock_response("NO"), _mock_response("YES")]):
        r1 = verify("value_a", "misc", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
        r2 = verify("value_b", "misc", model="aya", endpoint="http://localhost:8080", api_key="", cache=cache)
    assert r1 == "drop"
    assert r2 == "keep"


def test_verify_prompt_version_in_cache_key(tmp_path):
    """Cache key includes model version suffix so prompt edits invalidate it."""
    from zkm_ner.verifier import _MODEL_VERSION_SUFFIX
    assert "prompt-v1" in _MODEL_VERSION_SUFFIX
    # The hash component is non-empty
    parts = _MODEL_VERSION_SUFFIX.split("+")
    assert len(parts) == 2
    assert len(parts[1]) == 8  # 8-char hex hash
