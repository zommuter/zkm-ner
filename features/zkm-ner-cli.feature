# zkm-ner CLI journeys — Gherkin as a human checklist.
# All scenarios are @manual: they need a real store, spaCy models, and (for the
# verifier) a live OpenAI-compatible endpoint — none of which exist in CI.
# Automated coverage of the same logic lives in tests/ (hermetic, mocked).

@manual
Feature: NER enrichment via zkm convert
  As a knowledge-store owner
  I want entity mentions written into frontmatter automatically
  So that search and entity pages can use them

  Background:
    Given a zkm store at $ZKM_STORE with markdown documents
    And the zkm-ner plugin is installed (wheel or plugins/zkm-ner checkout)

  @manual
  Scenario: Full-store sweep
    When I run "zkm convert ner"
    Then every visible .md file gains an "entities:" frontmatter list
    And no document body is modified (git diff shows frontmatter-only changes)
    And files under dot-directories (.zkm-state/, .git/) are untouched
    And the store git log shows one auto-commit for the run

  @manual
  Scenario: Amender auto-trigger after a producer convert
    Given new mail was converted via "zkm convert eml"
    When the amender chain runs (default-on)
    Then only the newly created files are NER-processed (created= scoping)
    And running with "--no-amenders" skips NER entirely

  @manual
  Scenario: Cached re-run is I/O-only
    Given "zkm convert ner" has completed once
    When I run "zkm convert ner" again with no document changes
    Then the run finishes in seconds (cache hits, no model inference)
    And no new amendment records are emitted

@manual
Feature: Retroactive cleanup via zkm scrub
  As a knowledge-store owner
  I want to remove false-positive entities after filter improvements
  So that old extractions match current quality standards

  @manual
  Scenario: Dry-run is the default and writes nothing
    When I run "zkm scrub ner"
    Then I see counts (files_scanned, files_changed, entities_removed)
    And "git -C $ZKM_STORE status" shows a clean tree

  @manual
  Scenario: Apply removes heuristic false positives idempotently
    When I run "zkm scrub ner" in apply mode
    Then stoplist/structural/POS false positives disappear from frontmatter
    And deterministic entities (datetime, amount, iban, email, …) survive
    And a second apply run reports files_changed=0

  @manual
  Scenario: Verifier pass (requires a live LLM endpoint)
    Given an OpenAI-compatible endpoint is configured (llm.endpoint/llm.model)
    When I run "zkm scrub ner --with-verifier --dry-run"
    Then suspicious entities get LLM verdicts cached under ner_verifier
    And any network error preserves the entity (verdict "unclear" = keep)
