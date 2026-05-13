# zkm-ner

[zkm](https://github.com/zommuter/zkm) amender plugin that extracts named entities (persons, organisations, locations, contact details) from knowledge-store markdown files and writes them back into frontmatter.

## What it does

- Runs over all `.md` files in the store (amender pattern: returns `[]`, modifies frontmatter in place)
- Entity extraction pipeline: pattern overlay first (email, phone, URL, social handles, LinkedIn/GitHub profiles, org gazetteer), then spaCy NER (DE + EN small models with langdetect routing)
- Multi-stage false-positive filtering: markdown-artefact pre-strip, closed-set stoplists, POS-filter for common-noun false positives, LLM verifier for residual cases (`--with-verifier`)
- Extraction cache keyed by `(body_sha256, extractor, model, version)` — re-runs cost only I/O, not re-inference
- Optional GLiNER backend behind `zkm-ner[gliner]` extra and `ZKM_NER_MODEL=gliner`
- Configurable org gazetteer via `ZKM_NER_GAZETTEER` (YAML file mapping aliases → canonical names)

## Install

Clone this repo inside your zkm `plugins/` directory:

```bash
git clone https://github.com/zommuter/zkm-ner.git plugins/zkm-ner
```

Install spaCy language models on first use:

```bash
cd plugins/zkm-ner
uv run python -m spacy download de_core_news_sm
uv run python -m spacy download en_core_web_sm
```

## Configuration (in `<store>/.env`)

| Variable | Default | Description |
|---|---|---|
| `ZKM_NER_MODEL` | `spacy` | Extraction backend: `spacy` or `gliner` |
| `ZKM_NER_LANG` | *(auto)* | Force language code (`de`, `en`) — skips langdetect |
| `ZKM_NER_GAZETTEER` | *(built-in)* | Path to a custom YAML org-alias map |

## Frontmatter output

Entities are written using the γ typed-slot schema:

```yaml
entities:
  - scope: body          # body | signature | salutation
    type: person
    value: "Jane Smith"
  - scope: body
    type: amount
    value: "CHF 42.00"
    canonical: "42.00"
    unit: CHF
    standard: iso4217
  - scope: body
    type: iban
    value: "CH56 0483 5012 3456 7800 9"
    canonical: CH5604835012345678009
    standard: iso13616
  - scope: signature
    type: email_address
    value: jane@example.com
    canonical: jane@example.com
    standard: rfc5321
```

Supported types: `person`, `org`, `location`, `email_address`, `phone_number`, `url`,
`iban`, `amount`, `invoice_id`, `tracking_id`, `registration_code`, `social_handle.*`.

## Run

```bash
zkm convert ner
```

### With LLM verifier (reduces residual false positives)

```bash
zkm scrub ner --with-verifier --dry-run   # preview without writing
zkm scrub ner --with-verifier             # apply
```

Requires a running OpenAI-compatible endpoint (e.g. llama-swap). Configure `ZKM_LLM_ENDPOINT` + `ZKM_LLM_MODEL` in `<store>/.env`.

## Development

```bash
cd plugins/zkm-ner
uv sync --extra dev
uv run pytest
```

## License

MIT — see [LICENSE](LICENSE)
