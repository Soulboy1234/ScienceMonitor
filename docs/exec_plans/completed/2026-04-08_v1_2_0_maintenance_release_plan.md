# 2026-04-08 v1.2.0 maintenance and release plan

## Goal

Prepare a local `v1.2.0` release candidate by consolidating recent harness improvements, checking code functionality/performance/readability, reducing code entropy where practical, and keeping UI changes out of this release after manual review.

## Scope

- Review current dirty worktree and preserve intended non-UI changes:
  - agent skill governance
  - local private path override
  - report format review governance
  - `codex_local` executable fallback for background service environments
- Run code maintenance checks and fix low-risk issues found by the harness.
- Keep runtime data, logs, caches, and local private config out of versioned source.
- Defer config UI changes to `docs/exec_plans/Todo.md`.
- Prepare local `v1.2.0` release records after validation, then push only after user approval.

## Non-goals

- Do not upload to GitHub until the user confirms.
- Do not include new `config-ui` implementation changes in `v1.2.0`.
- Do not add weekly-report strong content review yet.
- Do not move or delete `data/` runtime state.
- Do not commit `config/local.paths.json`.

## Detailed steps

1. Baseline review
   - Inspect `git status`.
   - Identify intended non-UI changes and separate current UI changes.
   - Run entropy and harness checks to identify actual failures.

2. Code maintenance
   - Fix unused imports, stale references, or obvious readability issues surfaced by checks.
   - Avoid unnecessary file splits; prefer small, local simplifications.
   - Keep entropy budget honest and do not loosen budgets unless the code structure justifies it.

3. UI deferral
   - Revert current uncommitted `config-ui` code changes from this release candidate.
   - Record UI rework in `docs/exec_plans/Todo.md`.
   - Keep existing previously released UI code in place; do not delete the feature.

4. Validation
   - `./scripts/run_science_monitor.sh entropy-check`
   - `./scripts/run_science_monitor.sh harness-check`
   - `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`
   - `./.venv/bin/python -m pytest -q`
   - `git diff --check`

5. Local release preparation
   - Update `CHANGELOG.md` and `GovernanceBoard.md` for `v1.2.0` release-candidate state.
   - Leave GitHub push for a later user-approved step.
   - Create final local commit and tag only after validation.

## Validation status

- `./scripts/run_science_monitor.sh entropy-check` -> passed
- `./scripts/run_science_monitor.sh harness-check` -> passed
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2` -> passed
- `./.venv/bin/python -m pytest -q` -> `130 passed`
- `git diff --check` -> passed

## Result

- Current UI changes were deferred and recorded in `Todo.md`.
- Existing UI feature remains in the project; only the new unsatisfactory UI edits were excluded from `v1.2.0`.
- Final validation passed.
- Release commit created: `154053d11f2bb31450896464291f3b5e0a4e5223`
- Tag created: `v1.2.0`
- GitHub push is pending.
