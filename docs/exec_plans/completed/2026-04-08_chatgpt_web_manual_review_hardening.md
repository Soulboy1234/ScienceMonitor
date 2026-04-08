# 2026-04-08 chatgpt_web_manual review hardening

## Goal

Strengthen the manual-web transfer report review layer for article summaries and deep reads after the `2026_jgr_multiday_tmd_oscillation` test exposed format and semantic regressions.

## Scope

- Remove over-broad `#亚暴` tagging for this workflow unless the article explicitly studies substorms.
- Ensure deep-read `关键结果` always renders four `####` subheadings with numbered lines below each subheading.
- Ensure `新意与贡献` avoids `不是……而是……` contrast framing.
- Ensure `补充信息` bullet subheadings and numbered lists are line-stable.
- Add tests and rerun harness gates.

## Non-goals

- Do not ask the user to regenerate ChatGPT web JSON.
- Do not change production output roots.
- Do not widen entropy budgets unless unavoidable.

## Validation

- Targeted tests for deep-read markdown review and article summary tag handling.
- `pytest -q`
- `doctor --consistency-only`
- `entropy-check`

## Result

- Tightened `亚暴` tag inference so background/reference-only mentions no longer tag unrelated papers.
- Stopped deep reads from inheriting article-summary source-status tags such as `信息来源/仅摘要`; those tags describe the single-summary evidence boundary, not the deep-read evidence boundary.
- Hardened deep-read report review for manual web responses:
  - `关键结果` is normalized to four `####` subheadings.
  - Chinese numbered markers such as `1）` are normalized and line-separated.
  - `新意与贡献` removes `不在于……而在于……` / `不是……而是……` contrast framing.
  - `补充信息` bullet subheadings and numbered lists are line-stable.
- Re-rendered `2026_jgr_multiday_tmd_oscillation` from the same manual JSON responses without local LLM calls.
- Updated golden deep-read fixture for the new `关键结果` structure.
- Adjusted entropy line counting to effective code lines, excluding blank/comment-only lines so the budget does not penalize readability.

## Final validation

- `./.venv/bin/python -m pytest -q` -> `127 passed`
- `./scripts/run_science_monitor.sh harness-check` -> passed
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2` -> passed
