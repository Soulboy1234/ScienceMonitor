# 2026-04-08 report format governance

## Goal

Consolidate article-summary, daily-report, and deep-read format rules into a harness-level contract so report formatting is governed by templates, Python review loops, and tests rather than by prompt wording or conversation memory.

## Scope

- Document the boundary between runtime templates and deterministic report review.
- Add a single workflow spec for report review rules.
- Update template guides and source-of-truth documentation to point to that spec.
- Keep behavior changes minimal; this task is primarily governance and documentation.

## Non-goals

- Do not redesign the report templates.
- Do not add stronger weekly-report content review yet.
- Do not change LLM prompts unless a documentation check exposes an obvious mismatch.
- Do not touch runtime logs, data caches, or local private config.

## Steps

1. Inspect current templates and review loops.
2. Add `docs/workflow_specs/report_review_rules.md`.
3. Link the new spec from template guides, `source_of_truth_matrix.md`, and docs indexes.
4. Run lightweight validation.

## Validation

- `git diff --check`
- `./scripts/run_science_monitor.sh doctor --consistency-only`
- Targeted docs review by file diff

## Result

- Added `docs/workflow_specs/report_review_rules.md` as the central harness contract for generated-report format review.
- Clarified that runtime templates control static Markdown structure, while Python review loops enforce dynamic rules such as numbered-list line breaks, contrast-framing cleanup, abstract-only source tags, eval link semantics, and manual-web response cleanup.
- Linked the new spec from:
  - `AGENTS.md`
  - `docs/README.md`
  - `docs/workflow_specs/README.md`
  - `docs/workflow_specs/source_of_truth_matrix.md`
  - article summary, daily report, and deep reading template guides
- Kept runtime behavior unchanged; existing tests already cover the report review loops.

## Final validation

- `git diff --check` -> passed
- `./scripts/run_science_monitor.sh doctor --consistency-only` -> passed
- `./.venv/bin/python -m pytest tests/test_article_summaries.py tests/test_deep_reads.py tests/test_reporting.py -q` -> `55 passed`
- `./scripts/run_science_monitor.sh harness-check` -> passed
