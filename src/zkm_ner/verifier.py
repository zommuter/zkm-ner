"""LLM-based entity verifier for residual NER false-positive cleanup.

Two-tier design:
  Tier 1: value-only prompt, cached on (sha256(value:type), model, prompt-version).
          Returns "drop", "keep", or "unclear".
  Tier 2: context-augmented call, only when Tier 1 returns "unclear" AND context
          is provided.  Result replaces the "unclear" in the cache entry so the
          Tier 2 call is made at most once per unique (value, type, model) triple.

Cache uses ExtractionCache with extractor_name="ner_verifier".
Cache key repurposes body_sha256 = sha256(f"{value}:{type}").hexdigest().
The prompt hash is baked into model_version so any prompt edit auto-invalidates.
"""

from __future__ import annotations

import hashlib
import sys
from typing import TYPE_CHECKING, Literal

import httpx

if TYPE_CHECKING:
    from zkm.extraction_cache import ExtractionCache

_TIMEOUT = 30.0
_MAX_TOKENS = 12  # YES / NO / UNCLEAR + punctuation

_TIER1_PROMPT = (
    "You are a named-entity-recognition quality checker.\n"
    "The text corpus is a personal email archive in English and German.\n\n"
    "Entity type: {entity_type}\n"
    "Entity value: \"{value}\"\n\n"
    "Is this a genuine named entity of the stated type?\n"
    "Reply with exactly one word: YES if it is a real named entity, "
    "NO if it is a false positive (common noun, greeting, template text, "
    "noise, or markdown artefact), or UNCLEAR if you cannot tell without "
    "more document context."
)

_TIER2_PROMPT = (
    "You are a named-entity-recognition quality checker.\n"
    "The text corpus is a personal email archive in English and German.\n\n"
    "Entity type: {entity_type}\n"
    "Entity value: \"{value}\"\n"
    "Document excerpt:\n---\n{context}\n---\n\n"
    "Is this a genuine named entity of the stated type?\n"
    "Reply with exactly one word: YES if it is a real named entity, "
    "NO if it is a false positive (common noun, greeting, template text, "
    "noise, or markdown artefact), or UNCLEAR if you cannot tell even "
    "with this context."
)

_PROMPT_HASH = hashlib.sha256((_TIER1_PROMPT + _TIER2_PROMPT).encode()).hexdigest()[:8]
_MODEL_VERSION_SUFFIX = f"prompt-v1+{_PROMPT_HASH}"


def _chat_url(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    if endpoint.endswith("/v1"):
        return endpoint + "/chat/completions"
    return endpoint + "/v1/chat/completions"


def _call_llm(
    prompt: str,
    *,
    model: str,
    endpoint: str,
    api_key: str,
) -> str | None:
    """Make one chat-completions call and return the raw response text.

    Returns None on any network/HTTP/timeout error.
    """
    url = _chat_url(endpoint)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": _MAX_TOKENS,
        "temperature": 0,
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""
    except httpx.TimeoutException as exc:
        print(f"zkm-ner verifier: timeout ({str(exc)[:60]})", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"zkm-ner verifier: error ({str(exc)[:60]})", file=sys.stderr)
        return None


def _parse_verdict(raw: str | None) -> Literal["drop", "keep", "unclear"]:
    """Map raw LLM response to a verdict.  Defaults to 'unclear' on any error."""
    if raw is None:
        return "unclear"
    first_word = raw.strip().split()[0].upper().rstrip(".,!?") if raw.strip() else ""
    if first_word == "YES":
        return "keep"
    if first_word == "NO":
        return "drop"
    return "unclear"


def _cache_key(model: str) -> tuple[str, str]:
    """Return (model_name, model_version) for ExtractionCache lookups."""
    return model, _MODEL_VERSION_SUFFIX


def verify(
    value: str,
    entity_type: str,
    *,
    model: str,
    endpoint: str,
    api_key: str,
    context: str | None = None,
    cache: "ExtractionCache",
) -> Literal["drop", "keep", "unclear"]:
    """Verify whether *value* of *entity_type* is a genuine entity or a false positive.

    Returns:
        "keep"    — genuine named entity; do not scrub.
        "drop"    — false positive; safe to remove.
        "unclear" — cannot determine; do not scrub (conservative default).

    On any LLM error the function returns "unclear" so the entity is preserved.
    """
    body_sha256 = hashlib.sha256(f"{value}:{entity_type}".encode()).hexdigest()
    model_name, model_version = _cache_key(model)

    cached = cache.get(body_sha256, model_name=model_name, model_version=model_version)
    if cached is not None and cached:
        return cached[0]  # type: ignore[return-value]

    # Tier 1: value-only prompt
    prompt1 = _TIER1_PROMPT.format(entity_type=entity_type, value=value)
    raw1 = _call_llm(prompt1, model=model, endpoint=endpoint, api_key=api_key)
    verdict1 = _parse_verdict(raw1)

    if verdict1 != "unclear":
        cache.put(body_sha256, [verdict1], model_name=model_name, model_version=model_version)
        return verdict1

    # Tier 2: context-augmented (only when context is available)
    if context is None:
        return "unclear"

    ctx_snippet = context[:800]
    prompt2 = _TIER2_PROMPT.format(entity_type=entity_type, value=value, context=ctx_snippet)
    raw2 = _call_llm(prompt2, model=model, endpoint=endpoint, api_key=api_key)
    verdict2 = _parse_verdict(raw2)

    cache.put(body_sha256, [verdict2], model_name=model_name, model_version=model_version)
    return verdict2
